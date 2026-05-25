"""
Ambiguity detection — the bridge to the canvas UI.

A principled scorer: each archetype receives a numeric score from the IR's
content. When the top two scores are within `EPSILON`, there are two
plausible designs and the engine MUST NOT guess — it surfaces the choice
to the user as a taste question whose answer breaks the tie deterministically.

This replaces the older if-statement pile. The scoring is content-driven,
not magic-numbers-and-vibes, so adding a new archetype is just adding a
score function (and an option label).
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional

from .ir import Slide, BlockKind


EPSILON = 0.15  # archetype scores within this band are "tied"


@dataclass
class Question:
    id: str
    region: str               # "top" | "bottom" | "left" | "right"
    text: str
    options: list[str]


# ---- archetype scorers ---------------------------------------------------

def _score_stat_callout(slide: Slide) -> float:
    stats = [b for b in slide.blocks if b.kind == BlockKind.STAT]
    bullets = _bullets(slide)
    if not stats:
        return 0.0
    base = 0.45 + min(len(stats), 4) * 0.12
    # bullets pull score down: stat_callout is best when stats dominate
    if bullets:
        base -= 0.10 * min(len(bullets), 4)
    return max(0.0, min(1.0, base))


def _score_two_column_stats(slide: Slide) -> float:
    stats = [b for b in slide.blocks if b.kind == BlockKind.STAT]
    bullets = _bullets(slide)
    if not stats or not bullets:
        return 0.0
    # peak when both are present in roughly equal weight
    s_count = min(len(stats), 4)
    b_count = min(len(bullets), 4)
    balance = 1.0 - abs(s_count - b_count) / max(s_count, b_count, 1)
    return 0.40 + 0.35 * balance + 0.05 * min(s_count, b_count)


def _score_icon_rows(slide: Slide) -> float:
    icon_blocks = [b for b in slide.blocks if b.kind == BlockKind.ICON_ROW and b.items]
    bullets = _bullets(slide)
    if icon_blocks:
        return 0.75 + 0.05 * min(len(icon_blocks[0].items or []), 5)
    # text-only slide can present nicely as icon rows when bullets are short
    if bullets and not _has_stats(slide):
        short = all(len(b) <= 50 for b in bullets[:6])
        if short and 2 <= len(bullets) <= 6:
            return 0.55
    return 0.0


def _score_bullets_plain(slide: Slide) -> float:
    bullets = _bullets(slide)
    if not bullets:
        return 0.0
    if _has_stats(slide):
        # bullets-plain is a poor fit when stats also exist
        return 0.20
    n = len(bullets)
    # peak around 3-5 bullets
    if 3 <= n <= 5:
        return 0.65
    if 2 <= n <= 6:
        return 0.55
    return 0.40


def _score_title_slide(slide: Slide) -> float:
    has_title = any(b.kind == BlockKind.TITLE and b.text for b in slide.blocks)
    has_sub = any(b.kind == BlockKind.SUBTITLE and b.text for b in slide.blocks)
    bullets = _bullets(slide)
    stats = [b for b in slide.blocks if b.kind == BlockKind.STAT]
    if not has_title:
        return 0.0
    if bullets or stats:
        return 0.10  # not really a title slide if there's substance
    return 0.50 + (0.25 if has_sub else 0.10)


SCORERS = {
    "stat_callout":     _score_stat_callout,
    "two_column_stats": _score_two_column_stats,
    "icon_rows":        _score_icon_rows,
    "bullets_plain":    _score_bullets_plain,
    "title_slide":      _score_title_slide,
}


# ---- helpers -------------------------------------------------------------

def _bullets(slide: Slide) -> list[str]:
    for b in slide.blocks:
        if b.kind == BlockKind.BULLETS and b.items:
            return list(b.items)
    return []


def _has_stats(slide: Slide) -> bool:
    return any(b.kind == BlockKind.STAT for b in slide.blocks)


# ---- public API ----------------------------------------------------------

def score_archetypes(slide: Slide) -> list[tuple[str, float]]:
    """Return (archetype, score) sorted descending. Pure function of IR."""
    scored = [(name, fn(slide)) for name, fn in SCORERS.items()]
    scored.sort(key=lambda kv: -kv[1])
    return scored


def detect(slide: Slide, answers: Optional[dict] = None) -> list[Question]:
    """Surface taste questions for genuine ties (top-2 within EPSILON).

    The map from a tie pair → question label/region is deliberate. Tying
    archetypes ARE the forks the UX names, so adding archetypes just means
    extending this table.
    """
    answers = answers or {}
    qs: list[Question] = []

    scored = score_archetypes(slide)
    if len(scored) < 2 or scored[0][1] == 0.0:
        return qs

    top_name, top_score = scored[0]
    runner_name, runner_score = scored[1]

    # genuine tie?
    if top_score - runner_score <= EPSILON and runner_score > 0.0:
        q = _tie_question(top_name, runner_name)
        if q and q.id not in answers:
            qs.append(q)

    # User-agency rule: when BOTH stats and bullets carry real weight, the
    # focus fork ALWAYS belongs to the user, even if the scorer has a lean.
    # The scorer says "best fit"; this question says "your call."
    stats = [b for b in slide.blocks if b.kind == BlockKind.STAT]
    bullets_list = _bullets(slide)
    if len(stats) >= 2 and len(bullets_list) >= 1 and "focus" not in answers:
        if not any(q.id == "focus" for q in qs):
            qs.append(Question(
                id="focus", region="right",
                text="Numbers or narrative — what leads?",
                options=["Stats lead", "Story leads"],
            ))

    # density question: bullets overflow the practical max regardless of archetype
    bullets = _bullets(slide)
    if len(bullets) > 4 and "density" not in answers:
        qs.append(Question(
            id="density", region="left",
            text=f"{len(bullets)} points is a lot for one slide.",
            options=["Tighten to one", "Split to two"],
        ))

    # visual anchor: pure text with no stats — ask if a visual would help
    if bullets and not _has_stats(slide) and "visual" not in answers:
        # only offer this question if neither tie nor an existing answer settled it
        if not any(q.id in ("focus", "visual_pick") for q in qs):
            qs.append(Question(
                id="visual", region="bottom",
                text="Text-only. Add a visual?",
                options=["Numbered icons", "Keep text"],
            ))

    return qs


_TIE_LABELS = {
    frozenset({"stat_callout", "two_column_stats"}): (
        "focus", "right",
        "Numbers or narrative — what leads?",
        ["Stats lead", "Story leads"],
    ),
    frozenset({"bullets_plain", "icon_rows"}): (
        "visual_pick", "bottom",
        "Plain bullets, or numbered icons?",
        ["Keep plain", "Numbered icons"],
    ),
    frozenset({"bullets_plain", "two_column_stats"}): (
        "focus", "right",
        "Lead with numbers, or stay with the story?",
        ["Stats lead", "Story leads"],
    ),
    frozenset({"title_slide", "bullets_plain"}): (
        "open", "top",
        "Open quietly, or get right to the points?",
        ["Open quietly", "Lead with bullets"],
    ),
}


def _tie_question(a: str, b: str) -> Optional[Question]:
    entry = _TIE_LABELS.get(frozenset({a, b}))
    if not entry:
        return None
    qid, region, text, options = entry
    return Question(id=qid, region=region, text=text, options=options)


def choose_archetype(slide: Slide, answers: dict) -> str:
    """Pick the archetype, honoring any answered ties.

    Pure deterministic function of (IR, answers). The scorer picks the
    winner; an answered tie question overrides the runner-up vs leader
    decision when the answer says so.
    """
    answers = answers or {}
    scored = score_archetypes(slide)
    if not scored:
        return "bullets_plain"

    top_name, top_score = scored[0]
    if top_score == 0.0:
        # no resolver fits — degrade gracefully
        return "title_slide"

    # User-agency override: an explicit focus answer wins over the scorer
    # when both stats and bullets are present.
    stats = [b for b in slide.blocks if b.kind == BlockKind.STAT]
    bullets_list = _bullets(slide)
    if len(stats) >= 2 and bullets_list:
        if answers.get("focus") == "Story leads":
            return "two_column_stats"
        if answers.get("focus") == "Stats lead":
            return "stat_callout"

    if len(scored) >= 2:
        runner_name, runner_score = scored[1]
        if top_score - runner_score <= EPSILON and runner_score > 0.0:
            # tie — answers can flip
            if frozenset({top_name, runner_name}) == frozenset({"stat_callout", "two_column_stats"}):
                if answers.get("focus") == "Story leads":
                    return "two_column_stats"
                return "stat_callout"
            if frozenset({top_name, runner_name}) == frozenset({"bullets_plain", "icon_rows"}):
                if answers.get("visual_pick") == "Numbered icons" or answers.get("visual") == "Numbered icons":
                    return "icon_rows"
                return "bullets_plain"
            if frozenset({top_name, runner_name}) == frozenset({"bullets_plain", "two_column_stats"}):
                if answers.get("focus") == "Stats lead":
                    return "two_column_stats"
                return "bullets_plain"
            if frozenset({top_name, runner_name}) == frozenset({"title_slide", "bullets_plain"}):
                if answers.get("open") == "Open quietly":
                    return "title_slide"
                return "bullets_plain"

    return top_name


def to_dict(q: Question) -> dict:
    return asdict(q)
