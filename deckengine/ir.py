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
class ImageRef:
    """A visual asset carried alongside a slide's content. Geometry from
    the source file is STILL discarded (R7.2.2) — only the bytes + a
    minimal description survive ingest. The layout engine decides where
    to place the image; the renderer decides how to scale it.

    `kind`:
      - 'photo'   raw image (PNG/JPEG) from a picture shape
      - 'diagram' grouped vector/SmartArt rendered to PNG at ingest time
      - 'chart'   bar/line/pie — `chart_data` carries the categories +
                  series so the engine can re-render in its own style;
                  `path` is also set to a snapshot PNG fallback.
    """
    path: str                            # filesystem path or /samples-style URL
    alt: str = ""                        # title / a11y label
    source_idx: int = 0                  # source slide index this came from
    kind: str = "photo"                  # 'photo' | 'diagram' | 'chart'
    chart_data: Optional[dict] = None    # {type, categories, series:[{name, values}]}


@dataclass
class Slide:
    blocks: list[ContentBlock]
    intent: LayoutIntent = LayoutIntent.AUTO
    notes: Optional[str] = None
    # Images are CONTENT, not geometry — keep them across the ingest
    # boundary so the engine can re-place them under its own layout rules.
    images: list[ImageRef] = field(default_factory=list)


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
