"""
Deck ingest: .pptx -> IR.

R7.1.1: Ingest is a *content* operation. It MUST NOT live in layout.py or
render.py. This module sits at the model/content layer next to parse.py.

R7.2.2: **Ingest is intentionally lossy.** Geometry, themes, exact fonts,
and positioning are discarded by design. The imported deck's layout is
not preserved — the engine re-resolves layout from the extracted content.
A round-trip through ingest → engine WILL look different from the original.

R7.2.3: We classify conservatively. When in doubt, prefer paragraph/bullets
over inventing a STAT.

R7.2.4: No image/face data extraction. Embedded images are recorded as an
IMAGE block with an empty/alt label only; no binary data leaves this module.

R7.2.5: Graceful degradation — a slide we can't parse becomes a best-effort
title+paragraph IR, never a crash.
"""
from __future__ import annotations
import io
import re
from typing import Iterable

from .ir import Slide, ContentBlock, BlockKind, LayoutIntent, Deck, Theme
from .parse import _STAT_TOKEN, _extract_stat


def ingest_pptx_bytes(data: bytes) -> Deck:
    """Read a .pptx (in-memory bytes) and emit a content-only Deck.

    Uses python-pptx to walk shapes. R7.2.2: no positions, no colors, no
    fonts come out of this function.
    """
    from pptx import Presentation  # local import — keeps this lazy
    prs = Presentation(io.BytesIO(data))
    slides: list[Slide] = []
    deck_title = ""

    for idx, sl in enumerate(prs.slides):
        try:
            slide_ir, slide_title = _slide_to_ir(sl, idx)
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


def _slide_to_ir(sl, idx: int) -> tuple[Slide, str]:
    """Walk one python-pptx Slide, return (Slide IR, title-string)."""
    title_text = ""
    paragraphs: list[str] = []      # ordered body text (non-title shapes)
    bullet_items: list[str] = []    # flat list — placeholder type drives this
    notes_text = ""
    saw_image = False

    for shape in sl.shapes:
        # R7.2.4: presence-only image record, no binary
        if getattr(shape, "shape_type", None) == 13:  # MSO_SHAPE_TYPE.PICTURE
            saw_image = True
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

    if saw_image:
        blocks.append(ContentBlock(BlockKind.IMAGE, label="(image present in source — not embedded)"))

    # promote a hero (largest stat, parse.py-style)
    if stats:
        from .parse import _stat_weight
        hero = max(stats, key=_stat_weight)
        hero.emphasis = 2

    return Slide(
        blocks=blocks,
        intent=LayoutIntent.AUTO,
        notes=notes_text or None,
    ), title_text
