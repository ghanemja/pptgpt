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
from dataclasses import dataclass, replace
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
    role: str                     # "title" | "stat_value" | "stat_label" | "image" | ...
    text: str = ""
    font: str = "Calibri"
    size_pt: float = 16.0
    bold: bool = False
    color: str = "10131F"         # hex no '#'
    align: str = "left"           # left | center | right
    valign: str = "top"           # top | middle | bottom
    # Image payload — when set, the renderer emits a PICTURE shape
    # instead of a TEXTBOX. `image_path` is a filesystem path written
    # at ingest time (kind='photo'/'diagram'). `image_chart` carries
    # the {type, categories, series} payload for kind='chart' so the
    # renderer can re-draw in the engine's own style.
    image_path: Optional[str] = None
    image_chart: Optional[dict] = None


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


# ----- title_slide --------------------------------------------------------

def resolve_title_slide(slide: Slide, theme: Theme) -> ResolvedSlide:
    """
    Centerpiece title with an optional subtitle. The slide opens or closes a
    deck. Layout is intentionally calm: title vertically centered, subtitle
    immediately under it, accent rule below.
    """
    boxes: list[Box] = []
    m = theme.margin_in

    title_block = next((b for b in slide.blocks if b.kind == BlockKind.TITLE), None)
    sub_block = next((b for b in slide.blocks if b.kind == BlockKind.SUBTITLE), None)
    if title_block is None:
        raise ValueError("title_slide requires a TITLE block")

    band_h = CANVAS_H - 2 * m
    title_h = 1.6
    sub_h = 0.8
    rule_h = 0.06
    pair_h = title_h + (theme.gap_in * 0.5) + (sub_h if sub_block else 0.0) + theme.gap_in + rule_h
    top = m + (band_h - pair_h) / 2

    boxes.append(Box(
        x=m, y=top, w=CANVAS_W - 2 * m, h=title_h,
        role="title", text=title_block.text or "",
        font=theme.header_font, size_pt=64, bold=True,
        color=_fg(theme), align="left", valign="bottom",
    ))
    sub_y = top + title_h + theme.gap_in * 0.5
    if sub_block:
        boxes.append(Box(
            x=m, y=sub_y, w=CANVAS_W - 2 * m, h=sub_h,
            role="subtitle", text=sub_block.text or "",
            font=theme.body_font, size_pt=22, bold=False,
            color=_sub(theme), align="left", valign="top",
        ))
        sub_y += sub_h
    boxes.append(Box(
        x=m, y=sub_y + theme.gap_in, w=2.0, h=rule_h,
        role="accent_rule", text="",
        font=theme.body_font, size_pt=1, bold=False,
        color=theme.accent, align="left", valign="top",
    ))
    return ResolvedSlide(boxes=boxes, bg=theme.primary, archetype="title_slide")


# ----- two_column_stats ---------------------------------------------------

def resolve_two_column_stats(slide: Slide, theme: Theme) -> ResolvedSlide:
    """
    Title on top. Left column = bullets (narrative). Right column = stacked
    stat values + labels. Two columns NEVER overlap and share a top edge.
    """
    boxes: list[Box] = []
    m = theme.margin_in

    title_block = next((b for b in slide.blocks if b.kind == BlockKind.TITLE), None)
    stats = [b for b in slide.blocks if b.kind == BlockKind.STAT]
    bullets_block = next((b for b in slide.blocks if b.kind == BlockKind.BULLETS), None)
    bullet_items = list(bullets_block.items) if (bullets_block and bullets_block.items) else []
    if not stats:
        raise ValueError("two_column_stats requires at least one STAT block")

    title_h = 1.1 if title_block else 0.0
    if title_block:
        boxes.append(Box(
            x=m, y=m, w=CANVAS_W - 2 * m, h=title_h,
            role="title", text=title_block.text or "",
            font=theme.header_font, size_pt=40, bold=True,
            color=_fg(theme), align="left", valign="top",
        ))

    bx, by, bw, bh = _content_band(theme, title_h)
    col_gap = theme.gap_in
    left_w = (bw - col_gap) * 0.6
    right_w = (bw - col_gap) * 0.4

    # left column: bullets (narrative)
    if bullet_items:
        n_bul = max(1, min(len(bullet_items), 5))
        items = bullet_items[:n_bul]
        row_h = bh / n_bul
        for i, item in enumerate(items):
            boxes.append(Box(
                x=bx, y=by + i * row_h, w=left_w, h=row_h * 0.85,
                role="bullet", text=f"—  {item}",
                font=theme.body_font, size_pt=20, bold=False,
                color=_fg(theme), align="left", valign="middle",
            ))
    else:
        # blank panel keeps the geometry honest
        boxes.append(Box(
            x=bx, y=by, w=left_w, h=bh,
            role="bullet_placeholder", text="",
            font=theme.body_font, size_pt=18, bold=False,
            color=_sub(theme), align="left", valign="top",
        ))

    # right column: stacked stats
    rx = bx + left_w + col_gap
    n = len(stats)
    # vertical divider between columns
    boxes.append(Box(
        x=bx + left_w + (col_gap - 0.02) / 2, y=by, w=0.02, h=bh,
        role="divider", text="",
        font=theme.body_font, size_pt=1, bold=False,
        color=theme.accent, align="left", valign="top",
    ))
    hero_idx = next((i for i, s in enumerate(stats) if s.emphasis >= 2), 0)
    cell_h = bh / n
    for i, s in enumerate(stats):
        is_hero = (i == hero_idx)
        val_size = 56 if is_hero else 36
        val_color = theme.accent if is_hero else _fg(theme)
        cy = by + i * cell_h
        boxes.append(Box(
            x=rx, y=cy + cell_h * 0.05, w=right_w, h=cell_h * 0.55,
            role="stat_value", text=s.value or "",
            font=theme.header_font, size_pt=val_size, bold=True,
            color=val_color, align="left", valign="bottom",
        ))
        boxes.append(Box(
            x=rx, y=cy + cell_h * 0.60, w=right_w, h=cell_h * 0.30,
            role="stat_label", text=s.label or "",
            font=theme.body_font, size_pt=13, bold=False,
            color=_sub(theme), align="left", valign="top",
        ))

    return ResolvedSlide(boxes=boxes, bg=theme.primary, archetype="two_column_stats")


# ----- icon_rows ----------------------------------------------------------

def resolve_icon_rows(slide: Slide, theme: Theme) -> ResolvedSlide:
    """
    Title on top. Numbered/marker rows under it. Each row: marker on the left
    (a circle drawn as accent-colored number text), label on the right. Rows
    are evenly spaced vertically.
    """
    boxes: list[Box] = []
    m = theme.margin_in

    title_block = next((b for b in slide.blocks if b.kind == BlockKind.TITLE), None)
    # accept either BlockKind.BULLETS or BlockKind.ICON_ROW; take the first
    # block whose items field is populated.
    src = next(
        (b for b in slide.blocks
         if b.kind in (BlockKind.ICON_ROW, BlockKind.BULLETS) and b.items),
        None,
    )
    items: list[str] = list(src.items) if (src and src.items) else []
    if not items:
        raise ValueError("icon_rows requires an ICON_ROW or BULLETS block with items")

    title_h = 1.1 if title_block else 0.0
    if title_block:
        boxes.append(Box(
            x=m, y=m, w=CANVAS_W - 2 * m, h=title_h,
            role="title", text=title_block.text or "",
            font=theme.header_font, size_pt=40, bold=True,
            color=_fg(theme), align="left", valign="top",
        ))

    bx, by, bw, bh = _content_band(theme, title_h)
    n = min(len(items), 6)  # cap for legibility
    items = items[:n]
    row_h_total = bh / n
    row_h = row_h_total * 0.78  # leave breathing room
    row_pad_y = (row_h_total - row_h) / 2

    marker_w = 0.9
    gap = theme.gap_in
    label_x = bx + marker_w + gap
    label_w = bw - marker_w - gap

    for i, label in enumerate(items):
        cy = by + i * row_h_total + row_pad_y
        # numeric marker
        boxes.append(Box(
            x=bx, y=cy, w=marker_w, h=row_h,
            role="row_marker", text=f"{i+1:02d}",
            font=theme.header_font, size_pt=34, bold=True,
            color=theme.accent, align="left", valign="middle",
        ))
        # row label
        boxes.append(Box(
            x=label_x, y=cy, w=label_w, h=row_h,
            role="row_label", text=label,
            font=theme.body_font, size_pt=20, bold=False,
            color=_fg(theme), align="left", valign="middle",
        ))

    return ResolvedSlide(boxes=boxes, bg=theme.primary, archetype="icon_rows")


# ----- bullets_plain ------------------------------------------------------

def resolve_bullets_plain(slide: Slide, theme: Theme) -> ResolvedSlide:
    """
    Title on top. Single left-aligned bullet list filling the content band.
    Each bullet is one row; rows are evenly distributed.
    """
    boxes: list[Box] = []
    m = theme.margin_in

    title_block = next((b for b in slide.blocks if b.kind == BlockKind.TITLE), None)
    src = next(
        (b for b in slide.blocks if b.kind == BlockKind.BULLETS and b.items),
        None,
    )
    items: list[str] = list(src.items) if (src and src.items) else []
    if not items:
        raise ValueError("bullets_plain requires a BULLETS block with items")

    title_h = 1.1 if title_block else 0.0
    if title_block:
        boxes.append(Box(
            x=m, y=m, w=CANVAS_W - 2 * m, h=title_h,
            role="title", text=title_block.text or "",
            font=theme.header_font, size_pt=40, bold=True,
            color=_fg(theme), align="left", valign="top",
        ))

    bx, by, bw, bh = _content_band(theme, title_h)
    n = min(len(items), 7)
    items = items[:n]
    row_h_total = bh / n
    row_h = row_h_total * 0.78

    for i, item in enumerate(items):
        cy = by + i * row_h_total + (row_h_total - row_h) / 2
        boxes.append(Box(
            x=bx, y=cy, w=bw, h=row_h,
            role="bullet", text=f"•  {item}",
            font=theme.body_font, size_pt=22, bold=False,
            color=_fg(theme), align="left", valign="middle",
        ))

    return ResolvedSlide(boxes=boxes, bg=theme.primary, archetype="bullets_plain")


RESOLVERS = {
    "stat_callout":      resolve_stat_callout,
    "title_slide":       resolve_title_slide,
    "two_column_stats":  resolve_two_column_stats,
    "icon_rows":         resolve_icon_rows,
    "bullets_plain":     resolve_bullets_plain,
}


def _attach_hero_image(slide: Slide, theme: Theme, rs: ResolvedSlide) -> ResolvedSlide:
    """Bolt a hero image onto an already-resolved slide.

    Takes the first ImageRef on the slide (photo / diagram / chart) and
    appends a Box at a fixed right-side slot inside the canvas margins.
    Text boxes that previously spanned the full content width are
    shrunken in-place so they don't run under the image.

    This is intentionally lightweight: per-archetype tuned image
    placements live in their own follow-up. For the demo we just want
    the source visuals to actually appear on the rendered slide.
    """
    if not slide.images:
        return rs
    img = slide.images[0]
    is_chart = (img.kind == "chart") and bool(img.chart_data)
    # For server-side render we need a filesystem path. Public URL
    # alone isn't enough — render.py can't fetch over HTTP.
    fs_path = getattr(img, "fs_path", None) or img.path
    if not is_chart and not fs_path:
        return rs  # nothing to embed

    m = theme.margin_in
    # Right-side slot: ~5" wide × ~4.3" tall, vertically centered in the
    # content band (below the title row).
    img_w = 5.0
    img_h = 4.3
    img_x = CANVAS_W - m - img_w
    img_y = max(m + 1.2, (CANVAS_H - img_h) / 2)

    # Shrink any wide text Box that would underlay the image.
    shrunken: list[Box] = []
    for b in rs.boxes:
        # Title spans full width by convention; leave it alone unless it
        # would visibly intersect the image vertically.
        intersects_v = not (b.y + b.h <= img_y or b.y >= img_y + img_h)
        intersects_h = not (b.x + b.w <= img_x or b.x >= img_x + img_w)
        if intersects_v and intersects_h:
            # Trim the box to end before the image, with a small gap.
            new_w = max(1.0, img_x - b.x - theme.gap_in)
            shrunken.append(replace(b, w=new_w))
        else:
            shrunken.append(b)

    image_box = Box(
        x=img_x, y=img_y, w=img_w, h=img_h, role="image",
        image_path=(None if is_chart else fs_path),
        image_chart=(img.chart_data if is_chart else None),
    )
    shrunken.append(image_box)
    return ResolvedSlide(boxes=shrunken, bg=rs.bg, archetype=rs.archetype)


def resolve(slide: Slide, theme: Theme, archetype: Optional[str] = None) -> ResolvedSlide:
    """
    Dispatch: explicit `archetype` wins; else `slide.intent`; else a content-
    driven fallback that picks the best-fit resolver from what the IR carries.
    R1.3.2: fallback is deterministic and documented here.
    """
    if archetype and archetype in RESOLVERS:
        rs = RESOLVERS[archetype](slide, theme)
        return _attach_hero_image(slide, theme, rs)

    intent_arch = slide.intent.value if slide.intent.value in RESOLVERS else None
    if intent_arch:
        # honor the intent unless the content can't support it
        try:
            rs = RESOLVERS[intent_arch](slide, theme)
            return _attach_hero_image(slide, theme, rs)
        except ValueError:
            pass  # fall through to content-driven pick

    # content-driven fallback (R1.3.2)
    arch = _pick_archetype(slide)
    rs = RESOLVERS[arch](slide, theme)
    return _attach_hero_image(slide, theme, rs)


def _pick_archetype(slide: Slide) -> str:
    stats = [b for b in slide.blocks if b.kind == BlockKind.STAT]
    bullets = next((b for b in slide.blocks if b.kind == BlockKind.BULLETS and b.items), None)
    icon = next((b for b in slide.blocks if b.kind == BlockKind.ICON_ROW and b.items), None)
    title = next((b for b in slide.blocks if b.kind == BlockKind.TITLE), None)
    sub = next((b for b in slide.blocks if b.kind == BlockKind.SUBTITLE), None)

    if stats and bullets:
        return "two_column_stats"
    if stats:
        return "stat_callout"
    if icon:
        return "icon_rows"
    if bullets:
        return "bullets_plain"
    if title and sub:
        return "title_slide"
    if title:
        return "title_slide"
    # last resort — give the user something
    return "bullets_plain"
