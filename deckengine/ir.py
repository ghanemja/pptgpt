"""
Slide IR — the content/layout/theme separation.

The model emits CONTENT + fuzzy INTENT. The engine resolves geometry.
Nothing here carries coordinates; geometry lives downstream in `layout.py`.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BlockKind(str, Enum):
    TITLE = "title"
    SUBTITLE = "subtitle"
    PARAGRAPH = "paragraph"
    BULLETS = "bullets"
    STAT = "stat"          # value + label, the focus of v1
    QUOTE = "quote"
    IMAGE = "image"
    ICON_ROW = "icon_row"
    CAPTION = "caption"


@dataclass
class ContentBlock:
    kind: BlockKind
    text: Optional[str] = None
    items: Optional[list[str]] = None
    value: Optional[str] = None      # stat value, e.g. "99.97%"
    label: Optional[str] = None      # stat label / image alt
    emphasis: int = 0                # 0 normal, 1 emphasized, 2 hero


class LayoutIntent(str, Enum):
    AUTO = "auto"
    TITLE_SLIDE = "title_slide"
    STAT_CALLOUT = "stat_callout"
    TWO_COLUMN_STATS = "two_column_stats"
    ICON_ROWS = "icon_rows"
    BULLETS_PLAIN = "bullets_plain"


@dataclass
class Slide:
    blocks: list[ContentBlock]
    intent: LayoutIntent = LayoutIntent.AUTO
    notes: Optional[str] = None


@dataclass
class Theme:
    # hex without '#'
    primary: str = "1E2761"
    secondary: str = "CADCFC"
    accent: str = "F96167"
    fg_on_dark: str = "FFFFFF"
    fg_on_light: str = "10131F"
    sub_on_dark: str = "CADCFC"
    sub_on_light: str = "5A6072"
    header_font: str = "Georgia"
    body_font: str = "Calibri"
    dark: bool = True               # dark background for this slide?
    # spacing constants (inches) — these are CONSTRAINTS, not suggestions
    margin_in: float = 0.6
    gap_in: float = 0.35
    name: str = "Midnight Executive"


# named palettes -> "directions" come for free by swapping theme
PALETTES: dict[str, Theme] = {
    "bold": Theme(primary="1E2761", accent="F96167", dark=True, name="Bold / dark"),
    "clean": Theme(primary="FFFFFF", accent="028090", dark=False,
                   secondary="E6EEF2", name="Clean / light"),
    "warm": Theme(primary="B85042", accent="A7BEAE", dark=True,
                  secondary="E7E8D1", sub_on_dark="E7E8D1", name="Warm / editorial"),
}


@dataclass
class Deck:
    slides: list[Slide]
    theme: Theme = field(default_factory=Theme)
    title: str = "Untitled Deck"
