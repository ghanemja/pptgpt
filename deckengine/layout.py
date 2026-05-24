"""
Layout engine — the deterministic core. The contribution lives here.

Given a Slide (content + intent) and a Theme (constraints), produce a
ResolvedSlide: a flat list of positioned, sized, styled boxes in INCHES.
No model. Pure geometry. Fully testable against constraints.

Design philosophy (lifted from hard-won slide-design rules):
  - margins are a hard floor, never violated
  - one element dominates (hero), others recede
  - even distribution within the content band
  - left-align text, center only titles
  - size contrast between title and body is enforced, not hoped for

The 16:9 canvas is 13.333 x 7.5 inches (standard PowerPoint widescreen).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from .ir import Slide, Theme, BlockKind, ContentBlock

CANVAS_W = 13.333
CANVAS_H = 7.5


@dataclass
class Box:
    """A resolved, positioned element. All units in INCHES."""
    x: float
    y: float
    w: float
    h: float
    role: str                     # "title" | "stat_value" | "stat_label" | ...
    text: str = ""
    font: str = "Calibri"
    size_pt: float = 16.0
    bold: bool = False
    color: str = "10131F"         # hex no '#'
    align: str = "left"           # left | center | right
    valign: str = "top"           # top | middle | bottom


@dataclass
class ResolvedSlide:
    boxes: list[Box]
    bg: str                       # hex no '#'
    archetype: str


# ----- constraint helpers -------------------------------------------------

def _content_band(theme: Theme, title_h: float) -> tuple[float, float, float, float]:
    """The rectangle below the title, inside margins. (x, y, w, h)."""
    m = theme.margin_in
    x = m
    y = m + title_h + theme.gap_in
    w = CANVAS_W - 2 * m
    h = CANVAS_H - y - m
    return x, y, w, h


def _fg(theme: Theme) -> str:
    return theme.fg_on_dark if theme.dark else theme.fg_on_light


def _sub(theme: Theme) -> str:
    return theme.sub_on_dark if theme.dark else theme.sub_on_light


# ----- archetype resolvers ------------------------------------------------

def resolve_stat_callout(slide: Slide, theme: Theme) -> ResolvedSlide:
    """
    Title at top. Stats distributed evenly across the content band.
    The hero stat (emphasis==2, else the first) renders larger.
    """
    boxes: list[Box] = []
    m = theme.margin_in

    title_block = next((b for b in slide.blocks if b.kind == BlockKind.TITLE), None)
    stats = [b for b in slide.blocks if b.kind == BlockKind.STAT]
    if not stats:
        raise ValueError("stat_callout requires at least one STAT block")

    # title
    title_h = 1.1
    if title_block:
        boxes.append(Box(
            x=m, y=m, w=CANVAS_W - 2 * m, h=title_h,
            role="title", text=title_block.text or "",
            font=theme.header_font, size_pt=40, bold=True,
            color=_fg(theme), align="left", valign="top",
        ))
    else:
        title_h = 0.0

    bx, by, bw, bh = _content_band(theme, title_h)

    # even horizontal distribution with gaps between cells
    n = len(stats)
    gap = theme.gap_in
    cell_w = (bw - gap * (n - 1)) / n

    # decide hero: explicit emphasis==2 wins, else first stat
    hero_idx = next((i for i, s in enumerate(stats) if s.emphasis >= 2), 0)

    for i, s in enumerate(stats):
        cx = bx + i * (cell_w + gap)
        is_hero = (i == hero_idx)
        val_size = 60 if is_hero else 40        # enforced size contrast
        val_color = theme.accent if is_hero else _fg(theme)
        # value sits in the upper part of the band, label just under it
        val_h = bh * 0.55
        lbl_h = bh * 0.30
        # vertically center the value+label pair within the band
        pair_h = val_h + lbl_h
        top = by + (bh - pair_h) / 2
        boxes.append(Box(
            x=cx, y=top, w=cell_w, h=val_h,
            role="stat_value", text=s.value or "",
            font=theme.header_font, size_pt=val_size, bold=True,
            color=val_color, align="center", valign="bottom",
        ))
        boxes.append(Box(
            x=cx, y=top + val_h, w=cell_w, h=lbl_h,
            role="stat_label", text=s.label or "",
            font=theme.body_font, size_pt=14, bold=False,
            color=_sub(theme), align="center", valign="top",
        ))

    return ResolvedSlide(boxes=boxes, bg=theme.primary, archetype="stat_callout")


RESOLVERS = {
    "stat_callout": resolve_stat_callout,
}


def resolve(slide: Slide, theme: Theme, archetype: Optional[str] = None) -> ResolvedSlide:
    arch = archetype or (slide.intent.value if slide.intent.value in RESOLVERS else "stat_callout")
    if arch not in RESOLVERS:
        raise ValueError(f"no resolver for archetype '{arch}'")
    return RESOLVERS[arch](slide, theme)
