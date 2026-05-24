"""
Ambiguity detection — the bridge to the canvas UI.

An under-constrained slide has more than one sound design. Instead of the
engine guessing (the AUTO problem), it surfaces the genuine forks as
"taste questions," each anchored to the slide REGION it governs. The user's
answers ARE the missing constraints. This is what makes the interactive
front end principled rather than a pile of if-statements: a question exists
exactly when the content admits >1 valid resolution.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional

from .ir import Slide, BlockKind


@dataclass
class Question:
    id: str
    region: str               # "top" | "bottom" | "left" | "right"
    text: str
    options: list[str]


def detect(slide: Slide, answers: Optional[dict] = None) -> list[Question]:
    answers = answers or {}
    qs: list[Question] = []

    stats = [b for b in slide.blocks if b.kind == BlockKind.STAT]
    bullets = [b for b in slide.blocks if b.kind == BlockKind.BULLETS]
    bullet_items = bullets[0].items if bullets and bullets[0].items else []

    # fork 1: numbers vs narrative — only a real fork if BOTH are present
    if len(stats) >= 2 and bullet_items and "focus" not in answers:
        qs.append(Question(
            id="focus", region="right",
            text="Numbers or narrative — what leads?",
            options=["Stats lead", "Story leads"],
        ))

    # fork 2: too many bullets for one slide
    if len(bullet_items) > 4 and "density" not in answers:
        qs.append(Question(
            id="density", region="left",
            text=f"{len(bullet_items)} points is a lot for one slide.",
            options=["Tighten to one", "Split to two"],
        ))

    # fork 3: text-only slide, no visual anchor
    if bullet_items and not stats and "visual" not in answers:
        qs.append(Question(
            id="visual", region="bottom",
            text="Text-only. Add a visual?",
            options=["Numbered icons", "Keep text"],
        ))

    return qs


def choose_archetype(slide: Slide, answers: dict) -> str:
    """Map resolved answers -> archetype. Deterministic once forks are settled."""
    stats = [b for b in slide.blocks if b.kind == BlockKind.STAT]
    bullets = [b for b in slide.blocks if b.kind == BlockKind.BULLETS]
    has_bullets = bool(bullets and bullets[0].items)

    if len(stats) >= 2:
        if has_bullets and answers.get("focus") == "Story leads":
            return "two_column_stats"
        return "stat_callout"
    if has_bullets:
        return "icon_rows" if answers.get("visual") == "Numbered icons" else "bullets_plain"
    return "title_slide"


def to_dict(q: Question) -> dict:
    return asdict(q)
