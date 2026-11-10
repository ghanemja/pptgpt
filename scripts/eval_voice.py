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


def measure(slide: dict, brief: str) -> dict:
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
        "bullets": len([b for b in slide.get("bullets") or [] if str(b).strip()]),
        "words": len(text.split()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="", help="comma-separated brief keys")
    args = ap.parse_args()

    if not narrative.available():
        print("no model reachable — set DECKENGINE_NARRATIVE_BACKEND / start Ollama", file=sys.stderr)
        return 2
    print(f"backend: {narrative.backend_info()}")

    briefs = [b for b in BRIEFS if not args.only or b[0] in args.only.split(",")]
    rows = []
    for rep in range(args.reps):
        for key, aud, brief in briefs:
            for voice in (False, True):
                t0 = time.time()
                slide = workspace_gen.generate_slide(feature="create", prompt=brief, audience=aud,
                                                     palette="warm", file_names=[], voice=voice)
                dt = time.time() - t0
                row = {"brief": key, "voice": voice, "rep": rep, "secs": round(dt, 1), "slide": slide}
                if slide:
                    row["m"] = measure(slide, brief)
                rows.append(row)
                tag = "ON " if voice else "OFF"
                print(f"[{tag}] {key:<11} {dt:5.1f}s  " + (
                    json.dumps(slide, ensure_ascii=False)[:160] if slide else "FAILED"), flush=True)

    def agg(voice: bool) -> dict:
        ok = [r for r in rows if r["voice"] is voice and r.get("m")]
        s = lambda k: sum(len(r["m"][k]) for r in ok)
        lenses: dict[str, int] = {}
        for r in ok:
            for l in r["m"]["lens_hits"]:
                lenses[l] = lenses.get(l, 0) + 1
        return {"slides": len(ok), "failed": sum(1 for r in rows if r["voice"] is voice and not r.get("m")),
                "banned": s("banned"), "fabricated_numbers": s("fabricated_numbers"),
                "unsupported_names": s("unsupported_names"), "placeholders": s("placeholders"),
                "lens_hits": sum(lenses.values()), "by_lens": dict(sorted(lenses.items())),
                "avg_bullets": round(sum(r["m"]["bullets"] for r in ok) / max(1, len(ok)), 2),
                "avg_words": round(sum(r["m"]["words"] for r in ok) / max(1, len(ok)), 1)}

    summary = {"off": agg(False), "on": agg(True)}
    print("\n" + json.dumps(summary, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"backend": narrative.backend_info(), "summary": summary, "rows": rows}, fh,
                      indent=2, ensure_ascii=False)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
