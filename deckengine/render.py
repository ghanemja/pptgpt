"""
Renderer — translates ResolvedSlide boxes into a real .pptx.

Deliberately dumb: it places exactly what the engine resolved, no judgment.
All design decisions happened upstream in layout.py. The only thing this
file decides is HOW to draw each box kind — text vs picture vs chart.
"""
from __future__ import annotations

import io
import os

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from .layout import ResolvedSlide, CANVAS_W, CANVAS_H


_ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
_ANCHOR = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}


def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str.upper())


def _render_chart_png(chart_data: dict) -> bytes | None:
    """Re-render a chart from extracted {type, categories, series} data
    using matplotlib in the engine's own style (clean white bg, emerald
    bars, no chart-junk). Returns None if matplotlib isn't installed —
    caller falls back to text placeholder."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    ctype = (chart_data.get("type") or "bar").lower()
    cats = chart_data.get("categories") or []
    series = chart_data.get("series") or []
    if not cats or not series:
        return None
    fig, ax = plt.subplots(figsize=(7, 5), dpi=140)
    palette = ["#0E5B36", "#2E7D5A", "#56A37A", "#88C5A4", "#B6E0C8"]
    if ctype in ("line", "linemarkers"):
        for i, s in enumerate(series):
            ax.plot(cats, s.get("values") or [], marker="o",
                    color=palette[i % len(palette)], label=s.get("name") or f"Series {i+1}")
    elif ctype == "pie":
        vals = (series[0].get("values") or [])[:len(cats)]
        ax.pie(vals, labels=cats, colors=palette[:len(cats)],
               autopct="%1.0f%%", textprops={"fontsize": 9})
    else:  # default bar
        import numpy as np
        x = np.arange(len(cats))
        n = max(1, len(series))
        w = 0.8 / n
        for i, s in enumerate(series):
            vals = s.get("values") or []
            ax.bar(x + i * w - 0.4 + w / 2, vals, w,
                   color=palette[i % len(palette)], label=s.get("name") or f"Series {i+1}")
        ax.set_xticks(x)
        ax.set_xticklabels(cats, rotation=0, ha="center", fontsize=9)
    if len(series) > 1:
        ax.legend(loc="best", fontsize=8, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=9)
    fig.tight_layout(pad=0.5)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def open_base(template_path: str | None, w: float, h: float):
    """The presentation to draw into, and the blank layout to add slides with.

    With a template, we open THAT file so its masters, backgrounds, logos and
    footers come through underneath whatever the engine places. Its own
    example slides are dropped — we keep the master, not its content. The
    engine still resolves every box itself (R0.2); the template supplies the
    backdrop and the brand, never a position.
    """
    prs = Presentation(template_path) if template_path else Presentation()

    if template_path:
        # Strip the template's sample slides; keep its masters and layouts.
        xml_slides = prs.slides._sldIdLst
        for sld in list(xml_slides):
            rId = sld.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            if rId:
                prs.part.drop_rel(rId)
            xml_slides.remove(sld)
    else:
        prs.slide_width = Inches(w)
        prs.slide_height = Inches(h)

    # Prefer a truly blank layout; fall back to the emptiest one available.
    blank = None
    for layout in prs.slide_layouts:
        if (layout.name or "").strip().lower() == "blank":
            blank = layout
            break
    if blank is None:
        blank = min(prs.slide_layouts, key=lambda l: len(l.placeholders._element))
    return prs, blank


def render_deck(resolved_slides: list[ResolvedSlide], path: str,
                template_path: str | None = None) -> str:
    prs, blank = open_base(template_path, CANVAS_W, CANVAS_H)

    for rs in resolved_slides:
        slide = prs.slides.add_slide(blank)

        # background fill — skipped under a template, whose master already
        # carries the background the brand expects.
        if not template_path:
            bg = slide.background
            bg.fill.solid()
            bg.fill.fore_color.rgb = _rgb(rs.bg)

        for b in rs.boxes:
            # ── Picture branch (photo / diagram) ─────────────────
            if b.image_path and os.path.isfile(b.image_path):
                try:
                    slide.shapes.add_picture(
                        b.image_path,
                        Inches(b.x), Inches(b.y),
                        width=Inches(b.w), height=Inches(b.h),
                    )
                except Exception:
                    pass
                continue
            # ── Chart branch (re-render from data via matplotlib) ─
            if b.image_chart:
                png = _render_chart_png(b.image_chart)
                if png:
                    slide.shapes.add_picture(
                        io.BytesIO(png),
                        Inches(b.x), Inches(b.y),
                        width=Inches(b.w), height=Inches(b.h),
                    )
                    continue
                # matplotlib missing — fall through to text placeholder
            # ── Default text branch ──────────────────────────────
            tb = slide.shapes.add_textbox(Inches(b.x), Inches(b.y), Inches(b.w), Inches(b.h))
            tf = tb.text_frame
            tf.word_wrap = True
            tf.margin_left = 0
            tf.margin_right = 0
            tf.margin_top = 0
            tf.margin_bottom = 0
            tf.vertical_anchor = _ANCHOR.get(b.valign, MSO_ANCHOR.TOP)

            p = tf.paragraphs[0]
            p.alignment = _ALIGN.get(b.align, PP_ALIGN.LEFT)
            run = p.add_run()
            run.text = b.text
            run.font.name = b.font
            run.font.size = Pt(b.size_pt)
            run.font.bold = b.bold
            run.font.color.rgb = _rgb(b.color)

    prs.save(path)
    return path
