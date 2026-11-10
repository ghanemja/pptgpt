#!/usr/bin/env python3
"""A/B the humanplease slide voice: the same briefs, drafted with and without it.

    DECKENGINE_NARRATIVE_BACKEND=ollama OLLAMA_MODEL=gemma3:4b \\
        .venv/bin/python scripts/eval_voice.py --reps 2 --out /tmp/voice.json

For every brief and condition it drafts one slide through the real
workspace_gen path (feature "create") and measures:

  - coach lens hits      — deckengine.coach lenses that fire on the slide
  - banned-phrase hits   — the voice block's banned words, "not just X, it's Y",
                           em dashes, exclamation marks
  - fabricated numbers   — numeric tokens on the slide that are not in the brief
  - unsupported names    — capitalised words on the slide that are not in the
                           brief (a heuristic: listed so a person can judge)
  - placeholders         — visible "[add …]" gaps, which are the honest
                           alternative to a fabricated fact
  - prompt leaks         — prompt text copied onto the slide: a schema rule
                           ("ALL CAPS context <=5 words"), a field rule, or the
                           voice block's own example ("[add Q3 revenue]").
                           Any 4 words in a row that the prompt's instructions
                           have and the brief does not count, plus the old
                           templates' known rule phrases.
  - lowercase titles     — titles that start lowercase. The names heuristic
                           only sees capitalised words, so a voice that writes
                           lowercase titles looks better on it than it is.

The summary is printed twice: pooled (every slide that came back), and
PAIRED, per brief, over only the briefs where both conditions produced a
slide, so a condition that fails on the hard briefs does not look cleaner
for it. Judge by the paired table.

If fabrication goes UP with the voice on, the voice is wrong.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from deckengine import narrative, workspace_gen  # noqa: E402
from deckengine.coach import LENSES  # noqa: E402

BRIEFS = [
    ("pitch", "exec",
     "Seed pitch for Ledgerline. We automate month-end close for restaurant groups. "
     "14 paying customers, $38k MRR, grew 22% month over month since June. "
     "Raising $2.5M to hire 4 engineers and expand from Chicago to Austin."),
    ("quarterly", "exec",
     "Q3 review for the EMEA sales team. Revenue $4.1M against a $3.8M plan. "
     "Churn rose from 1.9% to 2.6% after the price change in August. "
     "Two enterprise deals, Siemens Healthineers and Allianz, slipped to Q4."),
    ("lecture", "conf",
     "Intro lecture on the central limit theorem for first-year stats students. "
     "Show that averages of 30 dice rolls look normal even though one roll is uniform. "
     "Common mistake: thinking the data itself becomes normal."),
    ("standup", "standup",
     "Standup for the payments squad, Tuesday. Priya finished the Stripe webhook retry fix. "
     "Marco is blocked on the PCI audit evidence for the card vault. "
     "Release 3.14 goes out Thursday if QA signs off on the refund flow."),
    ("customer", "customer",
     "QBR with Northwind Health. Since rollout in March their nurses file shift notes in "
     "4 minutes instead of 11. 212 of 260 nurses are active weekly. "
     "Ask: extend to the two outpatient clinics in Q1."),
    ("board-hire", "exec",
     "Board update: we beat Q3 plan by 14%. Net retention in enterprise is 118%. "
     "40 enterprise deals have been untouched for 30 days because one AE covers 120 accounts. "
     "Ask: approve two enterprise AEs for Q1."),
    ("launch", "customer",
     "Launch slide for Tidepool 2.0, our open-source tide prediction library. "
     "New: offline mode and a Rust core that is 9x faster on the NOAA benchmark. "
     "Breaking change: Python 3.9 support dropped."),
    ("postmortem", "standup",
     "Postmortem for the 47-minute checkout outage on Oct 3. A config push set the "
     "Redis pool size to 0. Detected by a customer tweet, not alerting. "
     "Fixes: config validation in CI, an alert on checkout error rate above 2%."),
]

_BANNED = [
    "delve", "tapestry", "landscape", "realm", "testament to", "navigate", "dive deep",
    "unpack", "leverage", "leveraging", "robust", "seamless", "game-changer", "game changer",
    "supercharge", "unlock", "elevate", "curate", "journey", "synergy", "holistic",
    "empower", "cutting-edge", "transformative",
]
_BANNED_RE = re.compile(r"\b(" + "|".join(re.escape(b) for b in _BANNED) + r")\w*", re.I)
_NOT_JUST = re.compile(r"\bnot (just|only|merely) [^.]{1,60}?\b(it's|it is|but)\b", re.I)
_NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s*(?:%|x|k|m|b|mrr)?", re.I)
_CAP = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b")
_GENERIC_CAPS = {"Q1", "Q2", "Q3", "Q4", "I", "We", "Our", "The", "A", "An", "AE", "AEs",
                 "MRR", "ARR", "CI", "QA", "QBR", "PCI", "EMEA", "API"}


def fields(slide: dict) -> list[tuple[str, str]]:
    out = []
    for k in ("eyebrow", "title", "metric", "metricSub", "takeaway"):
        v = slide.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            out.append((k, str(v)))
    for b in slide.get("bullets") or []:
        if isinstance(b, str) and b.strip():
            out.append(("bullet", b))
    return out


def _norm_num(t: str) -> str:
    t = t.lower().replace("$", "").replace(",", "").strip()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"(%|x|k|m|b|mrr)$", "", t)
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t


# Rule text the pre-fix templates put inside the JSON slots, which a small
# model copied verbatim; kept so a leak is caught against either template.
_OLD_RULE_PHRASES = re.compile(
    r"ALL CAPS|<=\s*\d|takeaway-first|hero number|or null\b|\bwords conversational|"
    r"context <=|axis/unit label|\[add Q3 revenue\]", re.I)
_WORD = re.compile(r"[a-z0-9\[\]<=']+")


def _grams(text: str, n: int = 4) -> set[tuple[str, ...]]:
    w = _WORD.findall(text.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def _instructions(brief: str, aud: str, voice) -> str:
    """The prompt the model saw, minus the brief itself."""
    p = workspace_gen._build_prompt("create", brief, aud, None, [], "", voice)
    return p.replace(brief, "")


def prompt_leaks(slide: dict, brief: str, instructions: str) -> list[str]:
    out = []
    instr, own = _grams(instructions), _grams(brief)
    for k, v in fields(slide):
        if _OLD_RULE_PHRASES.search(v):
            out.append(f"{k}: {v}")
            continue
        if v.strip().lower() in ("null", "none", "...", "\u2026"):
            out.append(f"{k}: {v}")
            continue
        if (_grams(v) & instr) - own:
            out.append(f"{k}: {v}")
    return out


def measure(slide: dict, brief: str, instructions: str = "") -> dict:
    text = " ".join(v for _, v in fields(slide))
    brief_nums = {_norm_num(m.group(0)) for m in _NUM.finditer(brief)}
    brief_l = brief.lower()

    nums = []
    for m in _NUM.finditer(text):
        n = _norm_num(m.group(0))
        if n and n not in brief_nums and not re.fullmatch(r"[1-4]", n):   # "Q3", "3 asks"
            nums.append(m.group(0).strip())
    # Q-numbers and years are numbers too
    nums = [n for n in nums if not re.fullmatch(r"q[1-4]", n.lower())]

    names = []
    for k, v in fields(slide):
        if k == "eyebrow":
            continue                       # ALL CAPS by design
        for m in _CAP.finditer(v):
            w = m.group(0)
            if m.start() == 0 and " " not in w:
                continue                   # sentence-initial capital
            if w in _GENERIC_CAPS or w.lower() in brief_l:
                continue
            names.append(w)

    lens_hits = []
    for name, fn in LENSES.items():
        try:
            if fn(slide, {}):
                lens_hits.append(name)
        except Exception:
            pass

    return {
        "banned": [m.group(0) for m in _BANNED_RE.finditer(text)]
                  + (["em dash"] * text.count("—"))
                  + (["not-just"] if _NOT_JUST.search(text) else [])
                  + (["!"] * text.count("!")),
        "fabricated_numbers": nums,
        "unsupported_names": names,
        "placeholders": re.findall(r"\[add [^\]]+\]", text, re.I),
        "lens_hits": lens_hits,
        "prompt_leaks": prompt_leaks(slide, brief, instructions),
        "lowercase_title": bool(re.match(r"[a-z]", str(slide.get("title") or "").strip())),
        "bullets": len([b for b in slide.get("bullets") or [] if str(b).strip()]),
        "words": len(text.split()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="", help="comma-separated brief keys")
    ap.add_argument("--on-form", default="auto", choices=("auto", "full", "short"),
                    help="voice form for the ON condition (auto = picked by model size)")
    args = ap.parse_args()
    on_voice = True if args.on_form == "auto" else args.on_form

    if not narrative.available():
        print("no model reachable — set DECKENGINE_NARRATIVE_BACKEND / start Ollama", file=sys.stderr)
        return 2
    print(f"backend: {narrative.backend_info()}  ON voice form: "
          f"{workspace_gen.voice_form(on_voice)}")

    briefs = [b for b in BRIEFS if not args.only or b[0] in args.only.split(",")]
    rows = []
    for rep in range(args.reps):
        for key, aud, brief in briefs:
            for on in (False, True):
                voice = on_voice if on else False
                t0 = time.time()
                slide = workspace_gen.generate_slide(feature="create", prompt=brief, audience=aud,
                                                     palette="warm", file_names=[], voice=voice)
                dt = time.time() - t0
                row = {"brief": key, "voice": on, "rep": rep, "secs": round(dt, 1), "slide": slide,
                       "backend_used": narrative.last_used_backend()}
                if slide:
                    row["m"] = measure(slide, brief, _instructions(brief, aud, voice))
                rows.append(row)
                tag = "ON " if on else "OFF"
                print(f"[{tag}] {key:<11} {dt:5.1f}s  " + (
                    json.dumps(slide, ensure_ascii=False)[:160] if slide else "FAILED"), flush=True)

    def agg(voice: bool, only: set | None = None) -> dict:
        ok = [r for r in rows if r["voice"] is voice and r.get("m")
              and (only is None or r["brief"] in only)]
        s = lambda k: sum(len(r["m"][k]) for r in ok)
        lenses: dict[str, int] = {}
        for r in ok:
            for l in r["m"]["lens_hits"]:
                lenses[l] = lenses.get(l, 0) + 1
        return {"slides": len(ok), "failed": sum(1 for r in rows if r["voice"] is voice and not r.get("m")),
                "banned": s("banned"), "fabricated_numbers": s("fabricated_numbers"),
                "unsupported_names": s("unsupported_names"), "placeholders": s("placeholders"),
                "prompt_leaks": s("prompt_leaks"),
                "lowercase_titles": sum(1 for r in ok if r["m"]["lowercase_title"]),
                "avg_secs": round(sum(r["secs"] for r in ok) / max(1, len(ok)), 1),
                "lens_hits": sum(lenses.values()), "by_lens": dict(sorted(lenses.items())),
                "avg_bullets": round(sum(r["m"]["bullets"] for r in ok) / max(1, len(ok)), 2),
                "avg_words": round(sum(r["m"]["words"] for r in ok) / max(1, len(ok)), 1)}

    summary = {"off": agg(False), "on": agg(True)}
    print("\npooled (every slide that came back):\n" + json.dumps(summary, indent=2))

    # Paired: per brief, mean per slide in each condition, over only the
    # briefs where both conditions produced at least one slide.
    keys = ("fabricated_numbers", "unsupported_names", "banned", "prompt_leaks", "lens_hits")
    def per_slide(key: str, voice: bool) -> dict:
        ok = [r for r in rows if r["brief"] == key and r["voice"] is voice and r.get("m")]
        if not ok:
            return {}
        d = {k: sum(len(r["m"][k]) for r in ok) / len(ok) for k in keys}
        d["slides"] = len(ok)
        d["failed"] = sum(1 for r in rows if r["brief"] == key and r["voice"] is voice and not r.get("m"))
        return d
    paired, table = [], []
    print("\nper brief, mean per slide (OFF -> ON); '-' = no slide in that condition")
    print(f"{'brief':<11} {'ok off/on':>9}  " + "  ".join(f"{k[:10]:>12}" for k in keys))
    for key in dict.fromkeys(r["brief"] for r in rows):
        off, on = per_slide(key, False), per_slide(key, True)
        nf = lambda v: sum(1 for r in rows if r["brief"] == key and r["voice"] is v and r.get("m"))
        cell = lambda k: (f"{off[k]:.1f}->{on[k]:.1f}" if off and on else
                          f"{off.get(k, 0):.1f}->-" if off else f"-->{on.get(k, 0):.1f}" if on else "-")
        print(f"{key:<11} {nf(False):>4}/{nf(True):<4}  " + "  ".join(f"{cell(k):>12}" for k in keys))
        if off and on:
            paired.append(key)
        table.append({"brief": key, "off": off, "on": on})
    p = set(paired)
    summary["paired"] = {"briefs": paired, "off": agg(False, p), "on": agg(True, p)}
    summary["per_brief"] = table
    print(f"\npaired over {len(paired)} brief(s) where both conditions produced a slide:\n"
          + json.dumps({k: {m: summary['paired'][k][m] for m in
                            ('slides', 'fabricated_numbers', 'unsupported_names', 'banned',
                             'prompt_leaks', 'lens_hits', 'lowercase_titles')}
                        for k in ('off', 'on')}, indent=2))
    fb = [r for r in rows if r.get("backend_used") not in ("ollama", "", None) and r.get("m")]
    if fb:
        print(f"note: {len(fb)} slide(s) came from a fallback backend: "
              + ", ".join(f"{r['brief']}/{r['backend_used']}" for r in fb))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"backend": narrative.backend_info(), "summary": summary, "rows": rows}, fh,
                      indent=2, ensure_ascii=False)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
