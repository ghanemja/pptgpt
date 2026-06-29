"""
Deck ingest: .pptx -> IR.

R7.1.1: Ingest is a *content* operation. It MUST NOT live in layout.py or
render.py. This module sits at the model/content layer next to parse.py.

R7.2.2: **Geometry is intentionally lossy.** Positions, sizes, themes,
exact fonts are discarded by design. The engine re-resolves layout
downstream.

R7.2.3: We classify conservatively. When in doubt, prefer paragraph/bullets
over inventing a STAT.

R7.2.4 (revised 2026-06-29): Images and charts ARE content, not geometry.
We persist image blobs to `uploads_dir` (when provided) and attach
ImageRef entries to `slide.images`. Chart shapes are decoded into a data
payload (`chart_data`) so the engine can re-render them in its own style.
Geometry — where the image sat in the source slide — still does not
survive ingest.

R7.2.5: Graceful degradation — a slide we can't parse becomes a best-effort
title+paragraph IR, never a crash.
"""
from __future__ import annotations
import io
import os
import re
import uuid
from typing import Iterable, Optional

from .ir import Slide, ContentBlock, BlockKind, LayoutIntent, Deck, Theme, ImageRef
from .parse import _STAT_TOKEN, _extract_stat


def ingest_pptx_bytes(data: bytes, *, uploads_dir: Optional[str] = None,
                      url_prefix: str = "/uploads") -> Deck:
    """Read a .pptx (in-memory bytes) and emit a content+visuals Deck.

    Uses python-pptx to walk shapes. Geometry (positions, sizes, themes,
    exact fonts) does NOT come out of this function (R7.2.2). Images and
    chart data DO — they are content (R7.2.4 revised).

    If `uploads_dir` is provided, persist each image blob to a fresh
    subdirectory under it and attach an ImageRef whose `path` is the
    public URL (uploads_dir basename joined with url_prefix). When None,
    images are still detected and listed in `slide.images` but with an
    empty `path` — so the IR shape is the same, the bytes just aren't
    persisted.
    """
    from pptx import Presentation  # local import — keeps this lazy
    prs = Presentation(io.BytesIO(data))
    slides: list[Slide] = []
    deck_title = ""

    deck_subdir: Optional[str] = None
    deck_url_prefix: Optional[str] = None
    if uploads_dir:
        deck_id = uuid.uuid4().hex[:10]
        deck_subdir = os.path.join(uploads_dir, deck_id)
        os.makedirs(deck_subdir, exist_ok=True)
        deck_url_prefix = f"{url_prefix.rstrip('/')}/{deck_id}"

    for idx, sl in enumerate(prs.slides):
        try:
            slide_ir, slide_title = _slide_to_ir(
                sl, idx,
                save_dir=deck_subdir, url_prefix=deck_url_prefix,
            )
        except Exception:
            # R7.2.5: never crash on a malformed slide
            slide_ir = Slide(
                blocks=[ContentBlock(BlockKind.TITLE, text=f"Slide {idx+1}"),
                        ContentBlock(BlockKind.PARAGRAPH, text="(unparseable — content dropped)")],
                intent=LayoutIntent.AUTO,
            )
            slide_title = ""
        slides.append(slide_ir)
        if idx == 0 and slide_title:
            deck_title = slide_title

    if not slides:
        # empty deck — return a single empty slide so downstream code doesn't crash
        slides = [Slide(
            blocks=[ContentBlock(BlockKind.TITLE, text="Empty deck")],
            intent=LayoutIntent.AUTO,
        )]

    return Deck(slides=slides, theme=Theme(), title=deck_title or "Imported Deck")


def _slide_to_ir(sl, idx: int, *, save_dir: Optional[str] = None,
                 url_prefix: Optional[str] = None) -> tuple[Slide, str]:
    """Walk one python-pptx Slide, return (Slide IR, title-string).

    When `save_dir` is set, picture-shape blobs are persisted there and
    chart shapes are recorded with their underlying data; both are
    attached to slide.images as ImageRef entries.
    """
    title_text = ""
    paragraphs: list[str] = []      # ordered body text (non-title shapes)
    bullet_items: list[str] = []    # flat list — placeholder type drives this
    notes_text = ""
    image_refs: list[ImageRef] = []
    img_seq = 0
    # Fallback title candidate: highest text shape on the slide. Many
    # custom decks use plain textboxes (not title placeholders) for
    # their headlines, so the placeholder check alone misses them.
    fallback_title_candidate: tuple[float, str] = (10**9, "")  # (top_y, text)

    for shape in sl.shapes:
        # ── Pictures: extract blob, persist, attach ImageRef ──────
        if getattr(shape, "shape_type", None) == 13:  # MSO_SHAPE_TYPE.PICTURE
            try:
                blob = shape.image.blob
                ext = (shape.image.ext or "png").lstrip(".")
                fname = f"slide{idx:02d}_{img_seq:02d}.{ext}"
                img_seq += 1
                path = ""
                if save_dir is not None and url_prefix is not None:
                    fs_path = os.path.join(save_dir, fname)
                    with open(fs_path, "wb") as f:
                        f.write(blob)
                    path = f"{url_prefix}/{fname}"
                alt = (getattr(shape, "name", "") or "").strip()
                image_refs.append(ImageRef(
                    path=path, alt=alt, source_idx=idx, kind="photo",
                ))
            except Exception:
                pass
            continue
        # ── Charts: decode categories + series, attach as ImageRef
        # of kind 'chart' so the renderer can re-draw in its own style.
        if getattr(shape, "has_chart", False):
            try:
                chart = shape.chart
                cdata = _chart_to_data(chart)
                image_refs.append(ImageRef(
                    path="", alt=(getattr(shape, "name", "") or "Chart"),
                    source_idx=idx, kind="chart",
                    chart_data=cdata,
                ))
            except Exception:
                pass
            continue
        if not shape.has_text_frame:
            continue

        is_title = False
        try:
            ph = shape.placeholder_format
            if ph is not None and ph.idx == 0:
                is_title = True
            # placeholder type 13/14/15 = "title" family; idx 0 is the standard
        except Exception:
            pass

        text = "\n".join(p.text for p in shape.text_frame.paragraphs).strip()
        if not text:
            continue

        if is_title and not title_text:
            title_text = text.split("\n", 1)[0].strip()
            continue

        # Track the topmost short-ish text as a fallback title candidate.
        # Geometry is otherwise discarded, but `top` is read once here
        # only to pick the title-like shape — the value never leaves
        # this function.
        try:
            first_line = text.split("\n", 1)[0].strip()
            if 0 < len(first_line) <= 90 and "." not in first_line.rstrip("?!"):
                top_y = float(getattr(shape, "top", 0) or 0)
                if top_y < fallback_title_candidate[0]:
                    fallback_title_candidate = (top_y, first_line)
        except Exception:
            pass

        # bullet-y? heuristic — multiple short lines or "- " prefixes
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        looks_bullets = (
            len(lines) >= 2
            and sum(1 for l in lines if len(l) <= 120) == len(lines)
        )
        if looks_bullets:
            for l in lines:
                l = re.sub(r"^[#*\-•]+\s*", "", l)
                l = re.sub(r"^\d+[\.\)]\s+", "", l)
                if l:
                    bullet_items.append(l)
        else:
            paragraphs.append(text)

    # speaker notes
    try:
        if sl.has_notes_slide:
            notes_text = sl.notes_slide.notes_text_frame.text.strip()
    except Exception:
        notes_text = ""

    # Build the IR
    # Fall back to the topmost short text shape if no placeholder title
    # was found — many custom decks don't use placeholders for titles.
    if not title_text and fallback_title_candidate[1]:
        title_text = fallback_title_candidate[1]
        # also pop it from paragraphs so we don't double-render it
        paragraphs = [p for p in paragraphs if p.split("\n", 1)[0].strip() != title_text]
    blocks: list[ContentBlock] = []
    blocks.append(ContentBlock(BlockKind.TITLE, text=title_text or f"Slide {idx+1}"))

    # split paragraphs into stat vs paragraph using parse.py's helpers
    stats: list[ContentBlock] = []
    leftover: list[str] = []
    for p in paragraphs:
        # if the paragraph is one short line containing a single stat token, promote
        single = p.strip()
        if "\n" not in single:
            extracted = _extract_stat(single)
            if extracted:
                v, lbl = extracted
                stats.append(ContentBlock(BlockKind.STAT, value=v, label=lbl, emphasis=0))
                continue
        leftover.append(p)

    # also scan bullet items for stat-only entries — keep conservative
    refined_bullets: list[str] = []
    for item in bullet_items:
        e = _extract_stat(item)
        if e and len(item.split()) <= 8:
            stats.append(ContentBlock(BlockKind.STAT, value=e[0], label=e[1], emphasis=0))
        else:
            refined_bullets.append(item)

    blocks.extend(stats)
    if refined_bullets:
        blocks.append(ContentBlock(BlockKind.BULLETS, items=refined_bullets))
    for p in leftover:
        blocks.append(ContentBlock(BlockKind.PARAGRAPH, text=p))

    # Record a presence-only IMAGE block per asset so downstream code
    # that only reads `blocks` still knows the slide carries visuals.
    for ref in image_refs:
        blocks.append(ContentBlock(
            BlockKind.IMAGE,
            label=ref.alt or f"({ref.kind} from source)",
        ))

    # promote a hero (largest stat, parse.py-style)
    if stats:
        from .parse import _stat_weight
        hero = max(stats, key=_stat_weight)
        hero.emphasis = 2

    return Slide(
        blocks=blocks,
        intent=LayoutIntent.AUTO,
        notes=notes_text or None,
        images=image_refs,
    ), title_text


def _chart_to_data(chart) -> dict:
    """Decode a python-pptx Chart object into a JSON-safe data payload.

    Catches type names defensively — python-pptx chart-type enums vary
    between versions. We return the lower-cased name string instead of
    the enum so the renderer can do a simple string match.
    """
    try:
        ctype = str(chart.chart_type).split('.')[-1].lower()
    except Exception:
        ctype = "unknown"
    categories: list[str] = []
    try:
        # The first plot's categories are the x-axis labels.
        cats = list(chart.plots[0].categories)
        categories = [str(c) for c in cats]
    except Exception:
        categories = []
    series_out: list[dict] = []
    try:
        for s in chart.series:
            name = ""
            try: name = str(s.name)
            except Exception: pass
            try:
                values = [None if v is None else float(v) for v in list(s.values)]
            except Exception:
                values = []
            series_out.append({"name": name, "values": values})
    except Exception:
        pass
    return {
        "type": ctype,
        "categories": categories,
        "series": series_out,
    }
