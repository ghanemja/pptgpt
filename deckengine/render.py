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

    return prs, _blankest_layout(prs)


# Footer/date/slide-number placeholders are furniture: they carry the
# template's own branding and should survive. Content placeholders are the
# ones that render "Click to add title" / "Double-click to add an Image"
# when left empty, and the engine never fills them — it places its own boxes.
_FURNITURE_PH = {15, 16, 13}          # FOOTER, DATE, SLIDE_NUMBER


def _content_placeholders(shapes) -> list:
    out = []
    for shape in shapes:
        if not getattr(shape, "is_placeholder", False):
            continue
        try:
            kind = int(shape.placeholder_format.type)
        except (TypeError, ValueError):
            kind = -1
        if kind not in _FURNITURE_PH:
            out.append(shape)
    return out


def _blankest_layout(prs):
    """The layout that adds least of its own content furniture.

    A real template often has no layout literally called "Blank" — the one
    this project's own sample has. Counting CONTENT placeholders (not footers)
    picks the quietest layout in any template, instead of landing on one whose
    only two placeholders happen to be a title and a picture.
    """
    for layout in prs.slide_layouts:
        if (layout.name or "").strip().lower() == "blank":
            return layout
    return min(prs.slide_layouts, key=lambda l: len(_content_placeholders(l.placeholders)))


def add_slide(prs, layout):
    """A slide on `layout` with its empty content placeholders removed.

    python-pptx clones the layout's placeholders onto the new slide, and an
    empty one renders its prompt text — "Double-click to add an Image" in the
    middle of the deck. The engine fills none of them (it places its own
    boxes, R0.2), so they are dropped; the layout's non-placeholder graphics
    and the master underneath are untouched.
    """
    slide = prs.slides.add_slide(layout)
    for shape in _content_placeholders(list(slide.shapes)):
        shape._element.getparent().remove(shape._element)
    return slide


def render_deck(resolved_slides: list[ResolvedSlide], path: str,
                template_path: str | None = None) -> str:
    prs, blank = open_base(template_path, CANVAS_W, CANVAS_H)

    for rs in resolved_slides:
        slide = add_slide(prs, blank)

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


# ── diagrams ──────────────────────────────────────────────────────────────
#
# A ResolvedDiagram (deckengine/diagram.py) drawn as native PowerPoint shapes:
# boxes you can click and retype, connectors as lines with arrowheads. Every
# position, size, line break, font size and colour role was decided upstream;
# this only draws them.


def _emu(v_in: float) -> int:
    return int(round(v_in * 914400))


def _polyline(slide, pts, color: str, width_pt: float, arrow: bool, closed: bool = False, fill: str | None = None):
    from pptx.oxml.ns import qn
    from lxml import etree
    (x0, y0), rest = pts[0], pts[1:]
    fb = slide.shapes.build_freeform(_emu(x0), _emu(y0), scale=1.0)
    fb.add_line_segments([(_emu(x), _emu(y)) for x, y in rest], close=closed)
    shp = fb.convert_to_shape()
    if fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = _rgb(fill)
        shp.line.fill.background()
    else:
        shp.fill.background()
        shp.line.color.rgb = _rgb(color)
        shp.line.width = Pt(width_pt)
        if arrow:
            ln = shp.line._get_or_add_ln()
            etree.SubElement(ln, qn("a:tailEnd"), type="triangle", w="med", len="med")
    shp.shadow.inherit = False
    return shp


def _write_lines(shp, lines: list[str], sub_lines: list[str], size_pt: float, color: str,
                 font: str | None, bold: bool = True, align: str = "center") -> None:
    from .diagram import PAD_X_IN, PAD_Y_IN
    tf = shp.text_frame
    # The engine already broke the lines (measured against the box); letting
    # PowerPoint re-wrap would break them again inside a diamond's inset.
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = Inches(PAD_X_IN)
    tf.margin_top = tf.margin_bottom = Inches(PAD_Y_IN)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    first = True
    for text, size, b in [(t, size_pt, bold) for t in lines] + [(t, size_pt * 0.8, False) for t in sub_lines]:
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        para.alignment = _ALIGN.get(align, PP_ALIGN.CENTER)
        run = para.add_run()
        run.text = text
        run.font.size = Pt(round(size * 2) / 2)
        run.font.bold = b
        run.font.color.rgb = _rgb(color)
        if font:
            run.font.name = font


def add_diagram(slide, rd, pal: dict[str, str], font: str | None = None) -> None:
    """Draw a ResolvedDiagram onto a python-pptx slide. Judgment-free."""
    from pptx.enum.shapes import MSO_SHAPE

    for b in rd.bands:
        r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(b.x), Inches(b.y), Inches(b.w), Inches(b.h))
        r.fill.solid()
        r.fill.fore_color.rgb = _rgb(pal["band"])
        r.line.color.rgb = _rgb(pal["band_line"])
        r.line.width = Pt(0.5)
        r.shadow.inherit = False
    for g in rd.guides:
        _polyline(slide, g, pal["line"], 1.5, arrow=True)
    for e in rd.edges:
        if len(e.points) >= 2:
            _polyline(slide, e.points, pal["line"], 1.25, arrow=e.arrow)
    for n in rd.nodes:
        fill = pal.get(n.fill, pal["step"])
        on = pal.get(f"on_{n.fill}", pal["on_step"])
        if n.shape in ("poly", "hexagon") and n.points:
            shp = _polyline(slide, n.points, fill, 0, arrow=False, closed=True, fill=fill)
        else:
            kind = {"diamond": MSO_SHAPE.DIAMOND, "dot": MSO_SHAPE.OVAL,
                    "pill": MSO_SHAPE.ROUNDED_RECTANGLE}.get(n.shape, MSO_SHAPE.ROUNDED_RECTANGLE)
            shp = slide.shapes.add_shape(kind, Inches(n.x), Inches(n.y), Inches(n.w), Inches(n.h))
            if n.shape == "rect":
                shp.adjustments[0] = min(0.5, 0.08 / max(0.01, min(n.w, n.h)))
            shp.fill.solid()
            shp.fill.fore_color.rgb = _rgb(fill)
            shp.line.fill.background()
            shp.shadow.inherit = False
        if n.lines or n.sub_lines:
            _write_lines(shp, n.lines, n.sub_lines, rd.font_pt, on, font)
    for e in rd.edges:
        if e.label and e.label_box:
            x, y, w, h = e.label_box
            tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
            _write_lines(tb, [e.label], [], rd.font_pt * 0.8, pal["text_muted"], font, bold=False)
            tb.text_frame.margin_left = tb.text_frame.margin_right = 0
            tb.text_frame.margin_top = tb.text_frame.margin_bottom = 0
    for t in rd.texts:
        tb = slide.shapes.add_textbox(Inches(t.x), Inches(t.y), Inches(t.w), Inches(t.h))
        _write_lines(tb, [t.text], [], rd.font_pt * t.scale,
                     pal["text"] if t.role == "ink" else pal["text_muted"], font,
                     bold=t.role == "ink", align=t.align)
        tb.text_frame.margin_left = tb.text_frame.margin_right = 0
