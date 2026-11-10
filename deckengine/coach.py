"""coach.py — a configurable critic, with the structure in the engine.

A critique is only useful if it is specific, repeatable, and says what to do
next. So this is not a model asked to "be harsh". It is a set of LENSES —
each one a named thing that can be wrong with a slide, found by rule — and a
PERSONA that decides which lenses matter, how hard to push, and in whose
voice the note is written.

That split keeps the useful properties:

  * the same slide and persona always produce the same critique, so a note
    that appears is a property of the slide and not of a sampling seed;
  * every note carries the lens it came from and, where the fix is
    mechanical, what to do;
  * a persona is config (`coaches/*.json`), so "my VP of Sales" is a file
    rather than a code change.

Personas are content and conventions, never geometry. R0.1 holds: a note may
say a slide is too dense; it never says where a box goes.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COACHES_DIR = os.path.join(ROOT, "coaches")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")

# Severity, in the order a reader should take them.
BLOCKER, PUSH, NIT = "blocker", "push", "nit"
SEVERITY_ORDER = {BLOCKER: 0, PUSH: 1, NIT: 2}

STRICTNESS = {"soft": 1, "normal": 0, "hard": -1}   # shifts severity up/down


@dataclass
class Voice:
    opening: str = ""
    register: str = "plain"
    signature: str = ""


@dataclass
class Persona:
    slug: str
    name: str
    tagline: str = ""
    voice: Voice = field(default_factory=Voice)
    lenses: dict[str, int] = field(default_factory=dict)
    strictness: str = "normal"


class CoachError(ValueError):
    """A persona file we will not load."""


# ---- the lenses ------------------------------------------------------------
#
# Each returns a note dict or None. They look only at CONTENT.

# A digit inside a token is not a figure: "Q3" is a period, not a number, and
# treating it as data made the analyst demand a source for the word "Q3".
_NUM = re.compile(r"(?<![A-Za-z])\d")
_CLAIM = re.compile(r"\b(grew|growth|improv\w+|better|best|strong\w*|lead\w*|up|down|fell|rose|beat|outperform\w*|record)\b", re.I)
_HEDGE = re.compile(r"\b(might|may|could|perhaps|maybe|possibly|we think|we believe|seems|appears|roughly|about|fairly|somewhat)\b", re.I)
_JARGON = re.compile(r"\b(synerg\w+|leverage|holistic|paradigm|best.in.class|world.class|robust|seamless|frictionless|unlock|double.down|north.star|move the needle|low.hanging)\b", re.I)
_SOURCE = re.compile(r"\b(source|per |according to|as of|\bFY\d|\bQ[1-4]\b|dataset|ledger|survey|n\s*=)\b", re.I)
_COMPARE = re.compile(r"\b(vs\.?|versus|compared|against|year.over.year|yoy|qoq|baseline|plan|target|last (?:year|quarter|month))\b", re.I)
_OWNER = re.compile(r"\b(owner|owns|lead|accountable|responsible|by [A-Z]\w+|team will|we will|I will)\b")
_VERB = re.compile(r"\b(is|are|was|were|beat|grew|fell|drove|wins?|needs?|should|must|can|will|cut|doubled|halved|holds?|leads?|costs?|means?|proves?|shows?)\b", re.I)


def _text_of(slide: dict[str, Any]) -> str:
    parts = [slide.get("title"), slide.get("metric"), slide.get("metricSub"),
             slide.get("takeaway"), slide.get("eyebrow")]
    parts.extend(slide.get("bullets") or [])
    chart = slide.get("chart") or {}
    parts.append(chart.get("title"))
    parts.extend(str(r.get("label", "")) for r in (chart.get("data") or []))
    parts.extend(slide.get("diagram", {}).get("steps") or [])
    return " ".join(str(p) for p in parts if p)


# ---- what a note is about ---------------------------------------------------
#
# A note names the CONTENT it is about — "the title", "the third bullet" —
# so a reader can see it pinned to the slide. That is a reference into the
# slide's fields, never a position: where the title sits on the page is the
# renderer's business, and the UI finds it there (R0.1).

def _fields(slide: dict[str, Any]):
    """(target, text) for each piece of content, in reading order."""
    def one(field):
        v = slide.get(field)
        if v:
            yield {"field": field}, str(v)
    yield from one("eyebrow")
    yield from one("title")
    yield from one("metric")
    yield from one("metricSub")
    for i, b in enumerate(slide.get("bullets") or []):
        if str(b).strip():
            yield {"field": "bullets", "index": i}, str(b)
    chart = slide.get("chart") or {}
    chart_text = " ".join([str(chart.get("title") or "")]
                          + [str(r.get("label", "")) for r in (chart.get("data") or [])])
    if chart_text.strip():
        yield {"field": "chart"}, chart_text
    steps = (slide.get("diagram") or {}).get("steps") or []
    if steps:
        yield {"field": "diagram"}, " ".join(str(s) for s in steps)
    yield from one("takeaway")


def _locate(slide: dict[str, Any], rx: re.Pattern) -> Optional[dict[str, Any]]:
    """The first piece of content the pattern matches, or None."""
    for target, text in _fields(slide):
        if rx.search(text):
            return target
    return None


def _note(lens, severity, note, ask="", fix=None, target=None):
    return {"lens": lens, "severity": severity, "note": note, "ask": ask, "fix": fix,
            "target": target or {"field": "slide"}}


def lens_ask(slide, ctx):
    if not (slide.get("takeaway") or "").strip():
        return _note("ask", BLOCKER,
                     "This slide states facts and stops. Nothing tells me what to do with them.",
                     "What should I conclude, decide or approve here?",
                     {"field": "takeaway"}, {"field": "takeaway", "missing": True})
    return None


def lens_title(slide, ctx):
    title = (slide.get("title") or "").strip()
    if not title:
        return _note("title", BLOCKER, "There is no headline.", "What is this slide about?",
                     {"field": "title"}, {"field": "title", "missing": True})
    if not _VERB.search(title):
        return _note("title", PUSH,
                     f"“{title}” names a topic rather than making a point.",
                     "What does this slide assert about that topic?",
                     {"field": "title"}, {"field": "title"})
    return None


def lens_evidence(slide, ctx):
    text = _text_of(slide)
    if _CLAIM.search(text) and not _NUM.search(text):
        return _note("evidence", PUSH,
                     "There is a claim of movement here with no number behind it.",
                     "By how much, and from what?", target=_locate(slide, _CLAIM))
    return None


def lens_source(slide, ctx):
    text = _text_of(slide)
    if _NUM.search(text) and not _SOURCE.search(text):
        return _note("source", PUSH,
                     "Numbers appear with nothing saying where they came from or as of when.",
                     "What is the source and the cut date?", target=_locate(slide, _NUM))
    return None


def lens_comparison(slide, ctx):
    text = _text_of(slide)
    if _NUM.search(text) and not _COMPARE.search(text):
        return _note("comparison", PUSH,
                     "A number on its own is not an argument — there is nothing to compare it to.",
                     "Compared to what: plan, last quarter, the market?",
                     target=_locate(slide, _NUM))
    return None


def lens_density(slide, ctx):
    """Too much on one slide — judged by the company's own decks when known.

    With a kit that has learned from its examples, the threshold is the
    upper quartile of what that company's good decks actually carry, and the
    note says so. "Denser than your own decks" is an argument a team takes;
    "more than four bullets" is ours, and invites a debate about ours.
    """
    norms = (ctx or {}).get("norms") or {}
    limit = norms.get("max_points") or 4
    word_limit = norms.get("max_words_per_point")
    bullets = [b for b in (slide.get("bullets") or []) if str(b).strip()]

    if len(bullets) > limit:
        why = (f"Your own decks usually carry {limit} or fewer."
               if norms.get("max_points") else "The room will read, not listen.")
        return _note("density", PUSH, f"{len(bullets)} points on one slide. {why}",
                     "Which could go in the appendix or the next slide?",
                     target={"field": "bullets"})

    if word_limit:
        long = [i for i, b in enumerate(slide.get("bullets") or [])
                if str(b).strip() and len(str(b).split()) > word_limit]
        if long:
            return _note("density", NIT,
                         f"{len(long)} point(s) run past {word_limit} words, "
                         "longer than your decks usually allow.",
                         f"Can it be said in {word_limit} words or fewer?",
                         target={"field": "bullets", "index": long[0]})
    elif max((len(str(b)) for b in bullets), default=0) > 140:
        para = next(i for i, b in enumerate(slide.get("bullets") or []) if len(str(b)) > 140)
        return _note("density", NIT,
                     "At least one point is a paragraph.",
                     "Can that be said in under fifteen words?",
                     target={"field": "bullets", "index": para})
    return None


def lens_hedge(slide, ctx):
    m = _HEDGE.search(_text_of(slide))
    if m:
        return _note("hedge", NIT,
                     f"“{m.group(0)}” softens the claim.",
                     "Do you believe it or not? Say which.", target=_locate(slide, _HEDGE))
    return None


def lens_jargon(slide, ctx):
    m = _JARGON.search(_text_of(slide))
    if m:
        return _note("jargon", NIT,
                     f"“{m.group(0)}” is doing no work.",
                     "What does that mean in plain words?", target=_locate(slide, _JARGON))
    return None


def lens_ownership(slide, ctx):
    text = _text_of(slide)
    action_rx = re.compile(r"\b(should|must|need to|propose|recommend|approve|fund|hire)\b", re.I)
    asks_action = action_rx.search(text)
    if asks_action and not _OWNER.search(text):
        return _note("ownership", PUSH,
                     "Something is being proposed with nobody attached to it.",
                     "Who owns this, and what do they stop doing to make room?",
                     target=_locate(slide, action_rx))
    return None


def lens_handoff(slide, ctx):
    nxt = (ctx or {}).get("next")
    if not nxt:
        return None
    bumper = (slide.get("takeaway") or "").strip()
    if not bumper:
        return None
    words = {w for w in re.findall(r"[a-z]{4,}", bumper.lower())}
    following = {w for w in re.findall(r"[a-z]{4,}", (nxt.get("title") or "").lower())}
    if words and following and not (words & following):
        return _note("handoff", NIT,
                     "This slide's closing line shares nothing with the next slide's headline.",
                     "Does the order still hold, or is one of them in the wrong place?",
                     target={"field": "takeaway"})
    return None


LENSES = {
    "ask": lens_ask, "title": lens_title, "evidence": lens_evidence,
    "source": lens_source, "comparison": lens_comparison, "density": lens_density,
    "hedge": lens_hedge, "jargon": lens_jargon, "ownership": lens_ownership,
    "handoff": lens_handoff,
}


# ---- personas --------------------------------------------------------------

def _path_for(slug: str) -> str:
    if not _SLUG_RE.match(slug or ""):
        raise CoachError(f"bad coach slug {slug!r}")
    path = os.path.join(COACHES_DIR, f"{slug}.json")
    if not os.path.isfile(path):
        raise CoachError(f"no coach {slug!r}")
    return path


def parse_persona(raw: dict[str, Any], slug: str) -> Persona:
    if not isinstance(raw, dict):
        raise CoachError("persona must be a JSON object")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise CoachError("persona needs a name")

    lenses_raw = raw.get("lenses") or {}
    if not isinstance(lenses_raw, dict) or not lenses_raw:
        raise CoachError("persona needs at least one lens")
    lenses: dict[str, int] = {}
    for key, weight in lenses_raw.items():
        if key not in LENSES:
            raise CoachError(f"unknown lens {key!r}; known: {sorted(LENSES)}")
        lenses[key] = max(0, min(3, int(weight)))

    strict = str(raw.get("strictness") or "normal")
    if strict not in STRICTNESS:
        raise CoachError(f"strictness {strict!r} not in {sorted(STRICTNESS)}")

    v = raw.get("voice") or {}
    return Persona(slug=slug, name=name, tagline=str(raw.get("tagline") or ""),
                   voice=Voice(opening=str(v.get("opening") or ""),
                               register=str(v.get("register") or "plain"),
                               signature=str(v.get("signature") or "")),
                   lenses=lenses, strictness=strict)


def load_persona(slug: str) -> Persona:
    with open(_path_for(slug), "r", encoding="utf-8") as fh:
        return parse_persona(json.load(fh), slug)


def list_personas() -> list[dict[str, str]]:
    out = []
    if not os.path.isdir(COACHES_DIR):
        return out
    for fname in sorted(os.listdir(COACHES_DIR)):
        if not fname.endswith(".json"):
            continue
        slug = fname[: -len(".json")]
        try:
            p = load_persona(slug)
        except (CoachError, json.JSONDecodeError, OSError):
            continue
        out.append({"slug": p.slug, "name": p.name, "tagline": p.tagline,
                    "signature": p.voice.signature})
    return out


# ---- the critique ----------------------------------------------------------

def _shift(severity: str, strictness: str, weight: int) -> str:
    """Strictness bends severity, but only where the persona actually cares.

    A hard critic promoting every nit to a blocker says nothing — if
    everything is a blocker, the word has no content. So escalation applies
    only to the lenses this persona weights most; a soft critic softens
    across the board, which is what being soft means.
    """
    order = [BLOCKER, PUSH, NIT]
    shift = STRICTNESS.get(strictness, 0)
    if shift < 0 and weight < 3:
        return severity
    i = order.index(severity) + shift
    return order[max(0, min(len(order) - 1, i))]


def critique_slide(slide: dict[str, Any], persona: Persona,
                   *, context: Optional[dict] = None) -> dict[str, Any]:
    """Every note this persona would raise about this slide, worst first."""
    notes = []
    for lens, weight in persona.lenses.items():
        if weight <= 0:
            continue
        found = LENSES[lens](slide, context or {})
        if not found:
            continue
        found = dict(found)
        found["weight"] = weight
        # A lens the persona barely cares about cannot be a blocker for them.
        if weight == 1 and found["severity"] == BLOCKER:
            found["severity"] = PUSH
        found["severity"] = _shift(found["severity"], persona.strictness, weight)
        notes.append(found)

    notes.sort(key=lambda n: (SEVERITY_ORDER[n["severity"]], -n["weight"], n["lens"]))
    verdict = ("blocker" if any(n["severity"] == BLOCKER for n in notes)
               else "push" if notes else "clear")
    return {
        "coach": {"slug": persona.slug, "name": persona.name,
                  "opening": persona.voice.opening, "signature": persona.voice.signature},
        "verdict": verdict,
        "notes": notes,
    }


def apply_overrides(persona: Persona, overrides: Optional[dict[str, Any]]) -> Persona:
    """A persona tuned for one sitting, without editing its file.

    The shipped personas are starting points. Someone preparing for a
    specific room wants to say "this one, but harder, and I do not care
    about jargon today" — so strictness and lens weights can be overridden
    per run. The override is validated the same way the file is: an unknown
    lens is an error rather than a silently ignored key.
    """
    if not overrides:
        return persona

    lenses = dict(persona.lenses)
    for key, weight in (overrides.get("lenses") or {}).items():
        if key not in LENSES:
            raise CoachError(f"unknown lens {key!r}; known: {sorted(LENSES)}")
        w = max(0, min(3, int(weight)))
        if w == 0:
            lenses.pop(key, None)
        else:
            lenses[key] = w
    if not lenses:
        raise CoachError("an override cannot switch every lens off")

    strict = overrides.get("strictness") or persona.strictness
    if strict not in STRICTNESS:
        raise CoachError(f"strictness {strict!r} not in {sorted(STRICTNESS)}")

    return Persona(slug=persona.slug, name=persona.name, tagline=persona.tagline,
                   voice=persona.voice, lenses=lenses, strictness=strict)


def critique_deck(slides: list[dict[str, Any]], persona: Persona,
                  norms: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    out = []
    for i, slide in enumerate(slides):
        ctx = {"index": i, "next": slides[i + 1] if i + 1 < len(slides) else None,
               "norms": norms}
        result = critique_slide(slide, persona, context=ctx)
        result["slideId"] = slide.get("id")
        result["index"] = i
        out.append(result)
    return out


def review_deck(slides: list[dict[str, Any]], persona: Persona,
                overrides: Optional[dict[str, Any]] = None,
                norms: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The whole deck read end to end, with the deck-level counts.

    Per-slide notes answer "what is wrong here". A review also has to answer
    "where is this deck weakest" — which is a property of the set, not of any
    one slide, so the tally lives here rather than in the UI.
    """
    tuned = apply_overrides(persona, overrides)
    results = critique_deck(slides, tuned, norms)

    by_severity = {BLOCKER: 0, PUSH: 0, NIT: 0}
    by_lens: dict[str, int] = {}
    for r in results:
        for n in r["notes"]:
            by_severity[n["severity"]] += 1
            by_lens[n["lens"]] = by_lens.get(n["lens"], 0) + 1

    worst = sorted(
        results,
        key=lambda r: (-sum(1 for n in r["notes"] if n["severity"] == BLOCKER),
                       -len(r["notes"]), r["index"]),
    )
    weakest = [r["index"] for r in worst if r["notes"]][:3]

    return {
        "coach": {"slug": tuned.slug, "name": tuned.name,
                  "opening": tuned.voice.opening, "signature": tuned.voice.signature,
                  "strictness": tuned.strictness,
                  "lenses": dict(sorted(tuned.lenses.items(), key=lambda kv: -kv[1]))},
        "results": results,
        "summary": {
            "slides": len(results),
            "clear": sum(1 for r in results if not r["notes"]),
            "severities": by_severity,
            "lenses": dict(sorted(by_lens.items(), key=lambda kv: -kv[1])),
            "weakest": weakest,
            "verdict": ("blocker" if by_severity[BLOCKER] else
                        "push" if by_severity[PUSH] else
                        "nit" if by_severity[NIT] else "clear"),
        },
    }


def to_dict(p: Persona) -> dict[str, Any]:
    return asdict(p)
