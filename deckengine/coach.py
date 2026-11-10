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
from .diagram import labels as diagram_labels

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COACHES_DIR = os.path.join(ROOT, "coaches")
# Reviewers someone tuned and kept. Same file format as the shipped ones, so
# a saved reviewer loads anywhere a persona does; kept apart so the shipped
# set stays what the project ships, and never committed (see .gitignore).
SAVED_DIR = os.environ.get("DECKENGINE_SAVED_COACHES") or os.path.join(COACHES_DIR, "saved")

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
    saved: bool = False          # a reviewer someone kept, not one the project ships
    based_on: str = ""           # the shipped persona a saved one was tuned from


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
    parts.extend(diagram_labels(slide.get("diagram")))
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
    steps = diagram_labels(slide.get("diagram"))
    if steps:
        yield {"field": "diagram"}, " ".join(steps)
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
    norms = dict((ctx or {}).get("norms") or {})
    # A limit the company wrote down beats one inferred from its decks.
    crit = _param(ctx, "density")
    if crit and crit.max_points:
        norms["max_points"] = crit.max_points
    if crit and crit.max_words:
        norms["max_words_per_point"] = crit.max_words
    limit = norms.get("max_points") or 4
    word_limit = norms.get("max_words_per_point")
    bullets = [b for b in (slide.get("bullets") or []) if str(b).strip()]

    if len(bullets) > limit:
        why = (f"Your own decks usually carry {limit} or fewer."
               if norms.get("max_points") else "The room will read, not listen.")
        kinds = norms.get("preferred_diagram_kinds") or []
        ask = ("Which could go in the appendix or the next slide"
               + (f" — or is this a {kinds[0]}, drawn the way your decks draw one?"
                  if kinds else "?"))
        return _note("density", PUSH, f"{len(bullets)} points on one slide. {why}", ask,
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


def _words_rx(words: list[str]) -> re.Pattern:
    """A phrase list as one pattern: whole words, any case, longest first so
    "north star metric" wins over "north star"."""
    alts = sorted({w.strip() for w in words if w.strip()}, key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in alts) + r")(?!\w)", re.I)


def _param(ctx, lens: str) -> Optional["Criterion"]:
    """The company's own definition of a lens, when its kit gives one."""
    return ((ctx or {}).get("criteria") or {}).get(lens)


def lens_hedge(slide, ctx):
    crit = _param(ctx, "hedge")
    rx = _words_rx(crit.words) if crit and crit.words else _HEDGE
    m = rx.search(_text_of(slide))
    if m:
        return _note("hedge", NIT,
                     f"“{m.group(0)}” softens the claim.",
                     "Do you believe it or not? Say which.", target=_locate(slide, rx))
    return None


def lens_jargon(slide, ctx):
    crit = _param(ctx, "jargon")
    rx = _words_rx(crit.words) if crit and crit.words else _JARGON
    m = rx.search(_text_of(slide))
    if m:
        return _note("jargon", NIT,
                     f"“{m.group(0)}” is doing no work.",
                     "What does that mean in plain words?", target=_locate(slide, rx))
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


# ---- criteria: the lenses, in words a reader recognises ----------------------
#
# A lens is how a check runs; a criterion is how it reads in the configurator:
# a label, and what meeting it looks like. A company kit can restate any of
# them in its own terms, tune its parameters (its own jargon list, its own
# bullet limit), and add rules of its own — a list of phrases its decks must
# not use. Kit rules are named `kit:<id>` so they can never collide with a
# lens. Criteria are convention; like everything in a kit, never geometry.

KIT_PREFIX = "kit:"
KIT_KINDS = ("banned",)
_GEOMETRY_KEYS = {"x", "y", "w", "h", "left", "top", "width", "height", "position"}


@dataclass
class Criterion:
    id: str                          # a lens name, or "kit:<id>" for a kit's own rule
    label: str
    means: str = ""                  # what meeting it looks like
    kind: str = "lens"               # "lens" | "banned"
    words: list[str] = field(default_factory=list)
    severity: str = PUSH             # kit rules only; a lens keeps its own
    max_points: Optional[int] = None # density only
    max_words: Optional[int] = None  # density only
    on: bool = True                  # ticked by default when a kit is in use
    source: str = "engine"           # "engine" | "kit"


DEFAULT_CRITERIA: dict[str, tuple[str, str]] = {
    "ask":        ("There is an ask", "Each slide says what to conclude, decide or approve."),
    "title":      ("Headlines argue", "The title makes a point rather than naming a topic."),
    "evidence":   ("Claims have numbers", "Any claim of movement says by how much, and from what."),
    "source":     ("Numbers are sourced", "A figure says where it came from and as of when."),
    "comparison": ("Numbers are compared", "A figure sits next to plan, last period or the market."),
    "density":    ("One idea per slide", "Few points, each short enough to say aloud."),
    "hedge":      ("No hedging", "Claims are stated, not softened with might, maybe, roughly."),
    "jargon":     ("Plain words", "No buzzwords doing the work an argument should."),
    "ownership":  ("Someone owns it", "Anything proposed has a named owner."),
    "handoff":    ("It flows", "Each closing line leads into the next slide's headline."),
}


def _default_criterion(lens: str) -> Criterion:
    label, means = DEFAULT_CRITERIA[lens]
    return Criterion(id=lens, label=label, means=means)


def _small_int(v: Any, what: str) -> Optional[int]:
    if v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise CoachError(f"{what} must be a whole number")
    if not 1 <= n <= 50:
        raise CoachError(f"{what} must be between 1 and 50")
    return n


def _word_list(v: Any, what: str) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(w, str) for w in v):
        raise CoachError(f"{what} must be a list of phrases")
    words = [w.strip() for w in v if w.strip()]
    if len(words) > 200 or any(len(w) > 80 for w in words):
        raise CoachError(f"{what}: at most 200 phrases, each under 80 characters")
    return words


def parse_criteria(raw: Any) -> list[Criterion]:
    """A kit's `criteria.json`, validated the way a persona file is.

        {"criteria": [
          {"lens": "source", "label": "Every number is sourced",
           "means": "Names the system of record and the cut date."},
          {"lens": "jargon", "label": "House words only", "words": ["synergy", "unlock"]},
          {"lens": "density", "label": "Three points, tops", "max_points": 3},
          {"id": "codenames", "kind": "banned", "label": "No internal codenames",
           "words": ["Project Falcon"], "severity": "blocker"}
        ]}
    """
    if isinstance(raw, dict):
        raw = raw.get("criteria")
    if not isinstance(raw, list):
        raise CoachError("criteria must be a list")
    out: list[Criterion] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        where = f"criterion {i + 1}"
        if not isinstance(item, dict):
            raise CoachError(f"{where} must be an object")
        if _GEOMETRY_KEYS & set(item):
            raise CoachError(f"{where} carries geometry; criteria say what, never where")
        label = str(item.get("label") or "").strip()[:80]
        means = str(item.get("means") or "").strip()[:240]
        on = bool(item.get("on", True))

        if item.get("lens"):
            lens = str(item["lens"])
            if lens not in LENSES:
                raise CoachError(f"{where}: unknown lens {lens!r}; known: {sorted(LENSES)}")
            words = _word_list(item.get("words"), f"{where} words")
            if words and lens not in ("jargon", "hedge"):
                raise CoachError(f"{where}: only jargon and hedge take a word list")
            mp = _small_int(item.get("max_points"), f"{where} max_points")
            mw = _small_int(item.get("max_words"), f"{where} max_words")
            if (mp or mw) and lens != "density":
                raise CoachError(f"{where}: only density takes max_points / max_words")
            base = _default_criterion(lens)
            c = Criterion(id=lens, label=label or base.label, means=means or base.means,
                          words=words, max_points=mp, max_words=mw, on=on, source="kit")
        else:
            kind = str(item.get("kind") or "")
            if kind not in KIT_KINDS:
                raise CoachError(f"{where}: needs a lens, or a kind in {list(KIT_KINDS)}")
            ident = str(item.get("id") or "")
            if not _SLUG_RE.match(ident):
                raise CoachError(f"{where}: id must be lower-case letters, digits and dashes")
            if not label:
                raise CoachError(f"{where}: a kit rule needs a label")
            words = _word_list(item.get("words"), f"{where} words")
            if not words:
                raise CoachError(f"{where}: a banned rule needs words")
            sev = str(item.get("severity") or PUSH)
            if sev not in SEVERITY_ORDER:
                raise CoachError(f"{where}: severity must be one of {list(SEVERITY_ORDER)}")
            c = Criterion(id=KIT_PREFIX + ident, label=label, means=means, kind=kind,
                          words=words, severity=sev, on=on, source="kit")
        if c.id in seen:
            raise CoachError(f"{where}: {c.id!r} is listed twice")
        seen.add(c.id)
        out.append(c)
    return out


def criteria_for(kit: Optional[list[Criterion]] = None) -> list[Criterion]:
    """What the configurator lists: the kit's criteria first, in its order,
    then every lens it did not mention, in the engine's own words."""
    kit = list(kit or [])
    named = {c.id for c in kit}
    return kit + [_default_criterion(l) for l in DEFAULT_CRITERIA if l not in named]


def criterion_dict(c: Criterion) -> dict[str, Any]:
    d = {"id": c.id, "label": c.label, "means": c.means, "kind": c.kind,
         "on": c.on, "source": c.source}
    if c.words:
        d["words"] = list(c.words)
    if c.max_points:
        d["max_points"] = c.max_points
    if c.max_words:
        d["max_words"] = c.max_words
    if c.kind != "lens":
        d["severity"] = c.severity
    return d


def _kit_rule(c: Criterion, slide: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Run one of a kit's own rules. Only "banned" exists so far."""
    rx = _words_rx(c.words)
    m = rx.search(_text_of(slide))
    if not m:
        return None
    # The label already names the rule beside the note; the note says what tripped it.
    return _note(c.id, c.severity, f"“{m.group(0)}” is on the company's list for this.",
                 c.means or "Can it come out?", target=_locate(slide, rx))


def _valid_lens_key(key: str) -> bool:
    """A lens, or a kit rule's id — which a persona may name without the kit
    being loaded; it then simply has nothing to run."""
    return key in LENSES or (key.startswith(KIT_PREFIX) and bool(_SLUG_RE.match(key[len(KIT_PREFIX):])))


# ---- personas --------------------------------------------------------------

def _path_for(slug: str) -> str:
    """The file for a persona: a shipped one first, then a saved one.

    A saved reviewer can never shadow a shipped one — `save_persona` refuses
    the name — so the order only matters for files dropped in by hand.
    """
    if not _SLUG_RE.match(slug or ""):
        raise CoachError(f"bad coach slug {slug!r}")
    for folder in (COACHES_DIR, SAVED_DIR):
        path = os.path.join(folder, f"{slug}.json")
        if os.path.isfile(path):
            return path
    raise CoachError(f"no coach {slug!r}")


def _is_saved(path: str) -> bool:
    return os.path.dirname(os.path.abspath(path)) == os.path.abspath(SAVED_DIR)


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
        if not _valid_lens_key(key):
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
                   lenses=lenses, strictness=strict,
                   based_on=str(raw.get("basedOn") or ""))


def load_persona(slug: str) -> Persona:
    path = _path_for(slug)
    with open(path, "r", encoding="utf-8") as fh:
        p = parse_persona(json.load(fh), slug)
    p.saved = _is_saved(path)
    return p


def _summary(p: Persona) -> dict[str, Any]:
    """What a picker needs: who they are, and how they are set up to read,
    so choosing a reviewer shows their real strictness and lenses."""
    return {"slug": p.slug, "name": p.name, "tagline": p.tagline,
            "signature": p.voice.signature, "strictness": p.strictness,
            "lenses": dict(p.lenses), "saved": p.saved, "basedOn": p.based_on}


def list_personas() -> list[dict[str, Any]]:
    """Shipped personas, then saved ones, each in name order."""
    out = []
    seen = set()
    for folder in (COACHES_DIR, SAVED_DIR):
        if not os.path.isdir(folder):
            continue
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(".json"):
                continue
            slug = fname[: -len(".json")]
            if slug in seen:
                continue
            try:
                p = load_persona(slug)
            except (CoachError, json.JSONDecodeError, OSError):
                continue
            seen.add(slug)
            out.append(_summary(p))
    return out


# ---- saved reviewers -------------------------------------------------------

def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48].strip("-")
    if not slug:
        raise CoachError("a saved reviewer needs a name with letters or digits in it")
    return slug


def save_persona(name: str, based_on: str, *, strictness: Optional[str] = None,
                 lenses: Optional[dict[str, int]] = None, tagline: str = "") -> dict[str, Any]:
    """Keep a tuned reviewer under a name, to pick again later.

    It starts from an existing persona — its voice is that persona's — and
    keeps the strictness and lens weights it was tuned to, validated exactly
    as a shipped persona file is. Saving under a name that is already saved
    updates it; a shipped persona's name is refused, so "Board chair" always
    means the one the project ships.
    """
    name = str(name or "").strip()[:80]
    if not name:
        raise CoachError("a saved reviewer needs a name")
    slug = _slugify(name)
    if os.path.isfile(os.path.join(COACHES_DIR, f"{slug}.json")):
        raise CoachError(f"{name!r} is a built-in reviewer; pick another name")

    base = load_persona(based_on)
    root = base.based_on if base.saved and base.based_on else base.slug
    overrides: dict[str, Any] = {}
    if strictness:
        overrides["strictness"] = strictness
    if lenses is not None:
        # Every known lens is stated: one left out is switched off, so what
        # is saved is exactly what was on screen. Kit rules ride along.
        for k in lenses:
            if not _valid_lens_key(k):
                raise CoachError(f"unknown lens {k!r}; known: {sorted(LENSES)}")
        overrides["lenses"] = {k: int(lenses.get(k, 0) or 0) for k in LENSES}
        overrides["lenses"].update({k: int(v or 0) for k, v in lenses.items()
                                    if k.startswith(KIT_PREFIX)})
    tuned = apply_overrides(base, overrides)

    raw = {
        "name": name,
        "tagline": str(tagline or "").strip()[:140] or f"Tuned from {base.name}.",
        "basedOn": root,
        "voice": asdict(tuned.voice),
        "lenses": tuned.lenses,
        "strictness": tuned.strictness,
    }
    parse_persona(raw, slug)                      # refuse anything we could not load back

    os.makedirs(SAVED_DIR, exist_ok=True)
    path = os.path.join(SAVED_DIR, f"{slug}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    return _summary(load_persona(slug))


def delete_persona(slug: str) -> None:
    """Forget a saved reviewer. Shipped personas cannot be deleted from here."""
    if not _SLUG_RE.match(slug or ""):
        raise CoachError(f"bad coach slug {slug!r}")
    path = os.path.join(SAVED_DIR, f"{slug}.json")
    if not os.path.isfile(path):
        if os.path.isfile(os.path.join(COACHES_DIR, f"{slug}.json")):
            raise CoachError(f"{slug!r} is a built-in reviewer and cannot be deleted")
        raise CoachError(f"no saved reviewer {slug!r}")
    os.remove(path)


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
    crits = (context or {}).get("criteria") or {}
    for lens, weight in persona.lenses.items():
        if weight <= 0:
            continue
        if lens in LENSES:
            found = LENSES[lens](slide, context or {})
        elif lens in crits:
            found = _kit_rule(crits[lens], slide)
        else:
            continue                  # a kit rule whose kit is not loaded
        if not found:
            continue
        found = dict(found)
        found["weight"] = weight
        # The note reads in the company's words when its kit restates the lens.
        c = crits.get(lens) or (_default_criterion(lens) if lens in DEFAULT_CRITERIA else None)
        found["label"] = c.label if c else lens
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
        if not _valid_lens_key(key):
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
                   voice=persona.voice, lenses=lenses, strictness=strict,
                   saved=persona.saved, based_on=persona.based_on)


def _criteria_ctx(criteria: Optional[list[Criterion]]) -> dict[str, Criterion]:
    return {c.id: c for c in (criteria or [])}


def critique_deck(slides: list[dict[str, Any]], persona: Persona,
                  norms: Optional[dict[str, Any]] = None,
                  criteria: Optional[list[Criterion]] = None) -> list[dict[str, Any]]:
    crits = _criteria_ctx(criteria)
    out = []
    for i, slide in enumerate(slides):
        ctx = {"index": i, "next": slides[i + 1] if i + 1 < len(slides) else None,
               "norms": norms, "criteria": crits}
        result = critique_slide(slide, persona, context=ctx)
        result["slideId"] = slide.get("id")
        result["index"] = i
        out.append(result)
    return out


def review_deck(slides: list[dict[str, Any]], persona: Persona,
                overrides: Optional[dict[str, Any]] = None,
                norms: Optional[dict[str, Any]] = None,
                criteria: Optional[list[Criterion]] = None) -> dict[str, Any]:
    """The whole deck read end to end, with the deck-level counts.

    Per-slide notes answer "what is wrong here". A review also has to answer
    "where is this deck weakest" — which is a property of the set, not of any
    one slide, so the tally lives here rather than in the UI.
    """
    tuned = apply_overrides(persona, overrides)
    results = critique_deck(slides, tuned, norms, criteria)

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
