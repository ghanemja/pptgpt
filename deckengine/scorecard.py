"""scorecard.py — a panel of reviewers, each scoring the deck by aspect.

A review says what is wrong. A scorecard says how far there is to go, per
aspect, for the room this deck is actually for — so it can be watched while
the deck is edited and seen to move.

The scores are not a model's opinion. They are the coach's notes, counted:
every note a reviewer raises costs its slide points in the aspect the note
belongs to, weighted by how much that reviewer cares and how severe it is.
Two things are judged against the deck's purpose rather than any reviewer:

  * the AUDIENCE sets how much a slide may carry — the technical detail an
    exec room takes is not what a standup takes — and density is scored
    against that band, not a universal one;
  * the PURPOSE (the decision the deck is for, from scoping) has to be asked
    for somewhere, or clear messaging is marked down however good each
    headline is.

Same deck, same panel, same audience: same scores. Conventions only; no
geometry (R0.1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from . import coach as C


# ---- the rooms -------------------------------------------------------------

@dataclass(frozen=True)
class Audience:
    key: str
    label: str
    why: str
    max_points: int          # points a slide may carry before it is dense for this room
    tech: tuple[int, int]    # figures + technical terms per slide this room takes


AUDIENCES: dict[str, Audience] = {
    "exec": Audience("exec", "Exec", "numbers-forward, sparse, decision-oriented", 3, (1, 4)),
    "customer": Audience("customer", "Customer", "narrative-first, light on internals", 4, (0, 2)),
    "conf": Audience("conf", "Conference", "one idea per slide, minimal supporting text", 3, (0, 2)),
    "standup": Audience("standup", "Standup", "dense and practical, detail welcome", 6, (0, 8)),
}
DEFAULT_AUDIENCE = "exec"


# ---- the aspects -----------------------------------------------------------

@dataclass(frozen=True)
class Dimension:
    id: str
    label: str
    means: str
    lenses: tuple[str, ...]


DIMENSIONS: tuple[Dimension, ...] = (
    Dimension("messaging", "Clear messaging",
              "Headlines argue, each slide asks for something, the story flows to the decision.",
              ("title", "ask", "handoff")),
    Dimension("evidence", "Evidence",
              "Claims carry numbers, and the numbers are sourced and compared.",
              ("evidence", "source", "comparison")),
    Dimension("density", "Content density",
              "As much on each slide as this audience can take — no more, no less.",
              ("density",)),
    Dimension("language", "Plain language",
              "Said plainly: no hedging, no buzzwords.",
              ("hedge", "jargon")),
    Dimension("ownership", "Ownership",
              "Whatever is proposed has someone attached to it.",
              ("ownership",)),
    Dimension("house", "House rules",
              "The company kit's own rules.",
              ()),               # every kit:<id> rule lands here
)

SEVERITY_POINTS = {C.BLOCKER: 45, C.PUSH: 22, C.NIT: 8}


def dimension_of(lens: str) -> str:
    if lens.startswith(C.KIT_PREFIX):
        return "house"
    for d in DIMENSIONS:
        if lens in d.lenses:
            return d.id
    return "messaging"


# ---- technical density -----------------------------------------------------
#
# What a room has to decode: figures, and terms of art. Counted, not judged.

_FIGURE = re.compile(r"(?<![A-Za-z])[+\-−]?\$?\d[\d,.]*\s?(%|x|×|pts?|bps|[kKmMbB]\b)?")
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,5}s?\b")
_NOT_TECH = {"Q1", "Q2", "Q3", "Q4", "H1", "H2", "FY", "OK", "US", "UK", "EU", "AI", "I"}


def technical_items(slide: dict[str, Any]) -> int:
    # The eyebrow is set in capitals by style; its words are not acronyms.
    text = " ".join(t for target, t in C._fields(slide) if target["field"] != "eyebrow")
    figures = len(_FIGURE.findall(text))
    terms = {m for m in _ACRONYM.findall(text) if m.rstrip("s") not in _NOT_TECH and not m.isdigit()}
    return figures + len(terms)


def _fit_penalty(n: int, band: tuple[int, int]) -> int:
    lo, hi = band
    if n < lo:
        return min(40, (lo - n) * 12)
    if n > hi:
        return min(60, (n - hi) * 10)
    return 0


# ---- purpose ---------------------------------------------------------------

_STOP = {"that", "this", "with", "from", "have", "will", "into", "they", "them", "their",
         "what", "when", "should", "would", "could", "about", "there", "these", "those",
         "approve", "decide", "agree", "please", "need", "want"}


def _key_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in _STOP}


def purpose_met(slides: list[dict[str, Any]], purpose: str) -> Optional[bool]:
    """Does any one slide ask for what the deck is for?

    Asking can be spread over a slide — "Approve the hire plan" in the
    closing line, the security review it depends on in a bullet — but not
    over the deck: some slide has to put it together. None when no purpose
    was given — nothing to judge against.
    """
    want = _key_words(purpose)
    if not want:
        return None
    need = max(1, min(2, len(want)))
    for s in slides:
        parts = [str(s.get(k) or "") for k in ("title", "takeaway")]
        parts.extend(str(b) for b in (s.get("bullets") or []))
        got = _key_words(" ".join(parts))
        if len(want & got) >= need:
            return True
    return False


# ---- the card --------------------------------------------------------------

def _norms_for(audience: Audience, norms: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The stricter of the house's learned limit and this room's."""
    out = dict(norms or {})
    learned = out.get("max_points")
    out["max_points"] = min(learned, audience.max_points) if learned else audience.max_points
    return out


def score_card(slides: list[dict[str, Any]], persona: C.Persona, *,
               audience: Audience, purpose: str = "",
               norms: Optional[dict[str, Any]] = None,
               criteria: Optional[list[C.Criterion]] = None) -> dict[str, Any]:
    """One reviewer's scores, 0–100 per aspect they read for, and overall."""
    results = C.critique_deck(slides, persona, _norms_for(audience, norms), criteria)
    n = max(1, len(slides))
    labels = {c.id: c.label for c in C.criteria_for(criteria)}

    weight: dict[str, int] = {}
    for lens, w in persona.lenses.items():
        if w > 0 and (not lens.startswith(C.KIT_PREFIX) or lens in labels):
            d = dimension_of(lens)
            weight[d] = weight.get(d, 0) + w

    penalty = {d.id: [0.0] * len(slides) for d in DIMENSIONS}
    issues: dict[str, dict[str, dict[str, Any]]] = {d.id: {} for d in DIMENSIONS}

    for r in results:
        for note in r["notes"]:
            d = dimension_of(note["lens"])
            pts = SEVERITY_POINTS[note["severity"]] * (0.6 + 0.2 * note.get("weight", 2))
            penalty[d][r["index"]] += pts
            key = note.get("label") or note["lens"]
            it = issues[d].setdefault(key, {"label": key, "severity": note["severity"], "slides": []})
            it["slides"].append(r["index"])
            if C.SEVERITY_ORDER[note["severity"]] < C.SEVERITY_ORDER[it["severity"]]:
                it["severity"] = note["severity"]

    # Density is judged against the room, for every reviewer who reads for it.
    if "density" in weight:
        heavy, light = [], []
        for i, s in enumerate(slides):
            t = technical_items(s)
            p = _fit_penalty(t, audience.tech)
            penalty["density"][i] += p
            if p and t > audience.tech[1]:
                heavy.append(i)
            elif p:
                light.append(i)
        lo, hi = audience.tech
        a_room = ("an " if audience.label[:1].lower() in "aeiou" else "a ") + audience.label + " room"
        if heavy:
            issues["density"]["__heavy"] = {
                "label": f"More technical detail than {a_room} takes "
                         f"({lo}–{hi} figures or terms a slide)",
                "severity": C.PUSH, "slides": heavy}
        if light:
            issues["density"]["__light"] = {
                "label": f"Too little for {a_room} to go on "
                         f"(at least {lo} figure{'s' if lo != 1 else ''} a slide)",
                "severity": C.NIT, "slides": light}

    dims: dict[str, Any] = {}
    for d in DIMENSIONS:
        if d.id not in weight:
            continue
        per_slide = [max(0.0, 100.0 - p) for p in penalty[d.id]] or [100.0]
        score = sum(per_slide) / n
        if d.id == "messaging":
            met = purpose_met(slides, purpose)
            if met is False:
                score -= 20
                issues["messaging"]["__purpose"] = {
                    "label": f"Nothing in the deck asks for “{purpose.strip()[:80]}”",
                    "severity": C.BLOCKER, "slides": []}
        found = sorted(issues[d.id].values(),
                       key=lambda it: (C.SEVERITY_ORDER[it["severity"]], -len(it["slides"])))
        dims[d.id] = {"score": int(round(max(0.0, min(100.0, score)))), "weight": weight[d.id],
                      "issues": [dict(it, slides=sorted(set(it["slides"]))) for it in found]}

    total_w = sum(v["weight"] for v in dims.values())
    overall = (int(round(sum(v["score"] * v["weight"] for v in dims.values()) / total_w))
               if total_w else None)
    return {
        "coach": {"slug": persona.slug, "name": persona.name, "saved": persona.saved,
                  "strictness": persona.strictness},
        "overall": overall,
        "dims": dims,
    }


def score_panel(slides: list[dict[str, Any]], personas: list[C.Persona], *,
                audience: str = DEFAULT_AUDIENCE, purpose: str = "",
                norms: Optional[dict[str, Any]] = None,
                criteria: Optional[list[C.Criterion]] = None) -> dict[str, Any]:
    """Every reviewer on the panel, scored against the same room and purpose."""
    aud = AUDIENCES.get(audience) or AUDIENCES[DEFAULT_AUDIENCE]
    kit_rules = any(c.kind != "lens" for c in (criteria or []))
    return {
        "audience": {"key": aud.key, "label": aud.label, "why": aud.why,
                     "max_points": aud.max_points, "tech": list(aud.tech)},
        "purpose": (purpose or "").strip(),
        "purposeMet": purpose_met(slides, purpose),
        "dimensions": [{"id": d.id, "label": d.label, "means": d.means}
                       for d in DIMENSIONS if d.id != "house" or kit_rules],
        "cards": [score_card(slides, p, audience=aud, purpose=purpose,
                             norms=norms, criteria=criteria) for p in personas],
    }
