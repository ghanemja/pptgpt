"""org.py — per-organization profiles.

An organization brings its own *conventions*, not its own engine: which
questions you must answer before a deck is worth building, which narrative
arc its decks follow, which style rules its reviewers enforce, and which
past decks count as reference. All of that is content and convention, so it
lives in a JSON file under ``orgs/`` and is loaded here.

§0 still binds. A profile may name a theme or a palette; it may NOT carry
geometry. ``load_org`` rejects any profile that tries to ship coordinates —
boxes are resolved by ``layout.py`` and nowhere else.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORGS_DIR = os.path.join(ROOT, "orgs")

# Keys that would smuggle layout decisions into a config file.
_GEOMETRY_KEYS = {"x", "y", "w", "h", "width", "height", "top", "left",
                  "right", "bottom", "inches", "px", "coords", "box"}

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")

QUESTION_KINDS = ("choice", "text", "longtext")


@dataclass
class ScopeQuestion:
    """One question in the org's scoping interview (its 'grill me' set)."""
    id: str
    prompt: str
    kind: str = "text"
    options: list[str] = field(default_factory=list)
    placeholder: str = ""
    why: str = ""
    required: bool = False


@dataclass
class Narrative:
    """The arc an org's decks are expected to follow."""
    guide: str = ""
    beats: list[str] = field(default_factory=list)
    bumper_rule: str = ""
    messages_per_slide: int = 3


@dataclass
class Style:
    """House style. Names a theme/palette; never geometry."""
    theme: str = "bolt"
    palette: str = "warm"
    rules: list[str] = field(default_factory=list)
    banned: list[str] = field(default_factory=list)


@dataclass
class Example:
    """A reference deck the org considers exemplary."""
    label: str
    path: str = ""
    note: str = ""


@dataclass
class OrgProfile:
    slug: str
    name: str
    tagline: str = ""
    scope_questions: list[ScopeQuestion] = field(default_factory=list)
    narrative: Narrative = field(default_factory=Narrative)
    style: Style = field(default_factory=Style)
    examples: list[Example] = field(default_factory=list)


class OrgError(ValueError):
    """A profile that cannot be trusted — malformed, or carrying geometry."""


def _reject_geometry(node: Any, path: str = "") -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() in _GEOMETRY_KEYS:
                raise OrgError(
                    f"org profile carries geometry at {path or '<root>'}.{k} — "
                    "layout belongs to layout.py (R0.1)"
                )
            _reject_geometry(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _reject_geometry(v, f"{path}[{i}]")


def _question(raw: dict[str, Any], i: int) -> ScopeQuestion:
    qid = str(raw.get("id") or "").strip()
    prompt = str(raw.get("prompt") or "").strip()
    if not qid or not prompt:
        raise OrgError(f"scope_questions[{i}] needs both an id and a prompt")
    kind = str(raw.get("kind") or "text")
    if kind not in QUESTION_KINDS:
        raise OrgError(f"scope_questions[{i}].kind {kind!r} not in {QUESTION_KINDS}")
    options = [str(o) for o in raw.get("options") or []]
    if kind == "choice" and not options:
        raise OrgError(f"scope_questions[{i}] is a choice with no options")
    return ScopeQuestion(
        id=qid, prompt=prompt, kind=kind, options=options,
        placeholder=str(raw.get("placeholder") or ""),
        why=str(raw.get("why") or ""),
        required=bool(raw.get("required")),
    )


def parse_org(raw: dict[str, Any], slug: str) -> OrgProfile:
    """Validate a decoded profile. Raises OrgError on anything suspect."""
    if not isinstance(raw, dict):
        raise OrgError("profile must be a JSON object")
    _reject_geometry(raw)

    name = str(raw.get("name") or "").strip()
    if not name:
        raise OrgError("profile needs a name")

    questions = [_question(q, i) for i, q in enumerate(raw.get("scope_questions") or [])]
    seen: set[str] = set()
    for q in questions:
        if q.id in seen:
            raise OrgError(f"duplicate scope question id {q.id!r}")
        seen.add(q.id)

    n = raw.get("narrative") or {}
    narrative = Narrative(
        guide=str(n.get("guide") or ""),
        beats=[str(b) for b in n.get("beats") or []],
        bumper_rule=str(n.get("bumper_rule") or ""),
        messages_per_slide=int(n.get("messages_per_slide") or 3),
    )

    s = raw.get("style") or {}
    style = Style(
        theme=str(s.get("theme") or "bolt"),
        palette=str(s.get("palette") or "warm"),
        rules=[str(r) for r in s.get("rules") or []],
        banned=[str(b) for b in s.get("banned") or []],
    )

    examples = [
        Example(label=str(e.get("label") or "reference deck"),
                path=str(e.get("path") or ""),
                note=str(e.get("note") or ""))
        for e in raw.get("examples") or []
    ]

    return OrgProfile(slug=slug, name=name, tagline=str(raw.get("tagline") or ""),
                      scope_questions=questions, narrative=narrative,
                      style=style, examples=examples)


KITS_DIR = os.path.join(ROOT, "kits")


def _path(slug: str) -> str:
    """Where a profile lives. A company kit wins over a built-in profile.

    Built-ins under `orgs/` ship with the project; a kit under `kits/<slug>/`
    is a company's own, so when both exist the company's is the one meant.
    """
    if not _SLUG_RE.match(slug or ""):
        raise OrgError(f"bad org slug {slug!r}")
    kit_profile = os.path.join(KITS_DIR, slug, "profile.json")
    if os.path.isfile(kit_profile):
        return kit_profile
    return os.path.join(ORGS_DIR, f"{slug}.json")


def load_org(slug: str = "default") -> OrgProfile:
    path = _path(slug)
    if not os.path.exists(path):
        raise OrgError(f"no org profile {slug!r}")
    with open(path, "r", encoding="utf-8") as fh:
        return parse_org(json.load(fh), slug)


def list_orgs() -> list[dict[str, Any]]:
    """Every readable profile — company kits first, then built-ins.

    Each entry is `{slug, name, tagline, kit}`. Unreadable files are
    skipped rather than failing the list, so one broken kit cannot hide the
    others.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    if os.path.isdir(KITS_DIR):
        for slug in sorted(os.listdir(KITS_DIR)):
            if slug.startswith("_") or not _SLUG_RE.match(slug):
                continue
            if not os.path.isfile(os.path.join(KITS_DIR, slug, "profile.json")):
                continue
            try:
                p = load_org(slug)
            except (OrgError, json.JSONDecodeError, OSError):
                continue
            out.append({"slug": p.slug, "name": p.name, "tagline": p.tagline, "kit": True})
            seen.add(slug)

    if os.path.isdir(ORGS_DIR):
        for fname in sorted(os.listdir(ORGS_DIR)):
            if not fname.endswith(".json"):
                continue
            slug = fname[: -len(".json")]
            if slug in seen:
                continue
            try:
                p = load_org(slug)
            except (OrgError, json.JSONDecodeError, OSError):
                continue
            out.append({"slug": p.slug, "name": p.name, "tagline": p.tagline, "kit": False})
    return out


def to_dict(profile: OrgProfile) -> dict[str, Any]:
    return asdict(profile)
