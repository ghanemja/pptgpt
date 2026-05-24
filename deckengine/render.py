"""
Renderer — translates ResolvedSlide boxes into a real .pptx.

Deliberately dumb: it places exactly what the engine resolved, no judgment.
All design decisions happened upstream in layout.py.
"""
from __future__ import annotations

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from .layout import ResolvedSlide, CANVAS_W, CANVAS_H


_ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
_ANCHOR = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}


def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str.upper())


def render_deck(resolved_slides: list[ResolvedSlide], path: str) -> str:
    prs = Presentation()
    prs.slide_width = Inches(CANVAS_W)
    prs.slide_height = Inches(CANVAS_H)
    blank = prs.slide_layouts[6]  # truly blank layout

    for rs in resolved_slides:
        slide = prs.slides.add_slide(blank)

        # background fill
        bg = slide.background
        bg.fill.solid()
        bg.fill.fore_color.rgb = _rgb(rs.bg)

        for b in rs.boxes:
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
