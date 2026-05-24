"""
SlideSpec → .pptx renderer.

The frontend's SlideSpec lives in a 1280x720 pixel coordinate space.
PowerPoint's 16:9 canvas is 13.333x7.5 inches. The two are the same aspect
ratio so a single scale factor maps one to the other.

§0 still holds: this module is a *content renderer*, not a layout engine.
It places exactly what the SlideSpec describes — no design decisions, no
fallback geometry, no judgment. If a block has no `x/y/w/h`, it's skipped.

Block coverage:
  - text     : add_textbox
  - rect     : add_shape RECTANGLE, solid fill, no line
  - rule     : same (a thin filled rect)
  - tag      : pill — rounded rect + centered text
  - bullets  : add_textbox with one paragraph per item
  - plot     : rasterized via matplotlib (3b1b-flavored) if available;
               otherwise a labeled placeholder rect
  - chart    : rasterized bar/line chart via matplotlib if available;
               otherwise a labeled placeholder rect
"""
from __future__ import annotations
import io
import math
import re
from typing import Any

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

CANVAS_W_IN = 13.333
CANVAS_H_IN = 7.5


def _hex_to_rgb(color: str) -> RGBColor:
    """Accept '#RRGGBB', 'RRGGBB', or 'rgba(r,g,b,a)'. Drop alpha (PPT solid only)."""
    if not color:
        return RGBColor(0x00, 0x00, 0x00)
    color = color.strip()
    if color.startswith("rgba") or color.startswith("rgb"):
        nums = re.findall(r"[\d.]+", color)
        if len(nums) >= 3:
            r, g, b = int(float(nums[0])), int(float(nums[1])), int(float(nums[2]))
            return RGBColor(r, g, b)
        return RGBColor(0x00, 0x00, 0x00)
    s = color.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return RGBColor(0x00, 0x00, 0x00)
    return RGBColor(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _font_name(font_key: str | None) -> str:
    return {"serif": "Georgia", "mono": "Consolas"}.get(font_key or "sans", "Calibri")


_ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}


def _px_to_inches(px: float, canvas_px: float, canvas_in: float) -> float:
    return (px / canvas_px) * canvas_in


def _add_filled_rect(slide, x_in, y_in, w_in, h_in, fill_color, radius_px: float = 0, canvas_w_px: float = 1280):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius_px and radius_px > 0 else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _hex_to_rgb(fill_color)
    shape.line.fill.background()
    return shape


def _add_text(slide, x_in, y_in, w_in, h_in, *, text, font, size_pt, weight, italic, color,
              align, valign, line_height, letter_spacing, transform):
    tb = slide.shapes.add_textbox(Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}.get(valign, MSO_ANCHOR.TOP)

    p = tf.paragraphs[0]
    p.alignment = _ALIGN.get(align, PP_ALIGN.LEFT)
    run = p.add_run()
    run.text = text.upper() if transform == "uppercase" else text
    run.font.name = _font_name(font)
    run.font.size = Pt(size_pt)
    run.font.bold = weight is not None and weight >= 600
    run.font.italic = bool(italic)
    run.font.color.rgb = _hex_to_rgb(color)
    return tb


def _add_bullets(slide, x_in, y_in, w_in, h_in, *, items, font, size_pt, weight, italic, color,
                 marker, marker_color, gap_px, line_height):
    tb = slide.shapes.add_textbox(Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    for i, item in enumerate(items or []):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if marker == "number":
            prefix = f"{i+1:02d}  "
        elif marker == "dash":
            prefix = "—  "
        elif marker == "none":
            prefix = ""
        else:
            prefix = "•  "
        if prefix:
            r1 = p.add_run()
            r1.text = prefix
            r1.font.name = _font_name(font)
            r1.font.size = Pt(size_pt)
            r1.font.color.rgb = _hex_to_rgb(marker_color or color)
            r1.font.bold = weight is not None and weight >= 600
        r2 = p.add_run()
        r2.text = item
        r2.font.name = _font_name(font)
        r2.font.size = Pt(size_pt)
        r2.font.color.rgb = _hex_to_rgb(color)
        r2.font.italic = bool(italic)
        r2.font.bold = weight is not None and weight >= 600
    return tb


# ---- optional rasterizers (matplotlib) ----------------------------------

def _have_mpl() -> bool:
    try:
        import matplotlib  # noqa: F401
        return True
    except Exception:
        return False


def _eval_curve(fn: str, xs, params: dict) -> list[float]:
    p = params
    A = p.get("A", 1.0); omega = p.get("omega", 1.0); phi = p.get("phi", 0.0)
    gamma = p.get("gamma", 0.0); mu = p.get("mu", 0.0); sigma = p.get("sigma", 1.0)
    k = p.get("k", 1.0); x0 = p.get("x0", 0.0)
    a, b, c, d = p.get("a", 0.0), p.get("b", 0.0), p.get("c", 0.0), p.get("d", 0.0)
    out: list[float] = []
    for x in xs:
        if fn == "sine":
            out.append(A * math.sin(omega * x + phi))
        elif fn == "cosine":
            out.append(A * math.cos(omega * x + phi))
        elif fn == "damped":
            out.append(A * math.exp(-gamma * x) * math.cos(omega * x))
        elif fn == "gaussian":
            z = (x - mu) / max(sigma, 1e-9)
            out.append(A * math.exp(-(z * z) / 2.0))
        elif fn == "exponential":
            out.append(A * math.exp(k * x))
        elif fn == "polynomial":
            out.append(a * x ** 3 + b * x ** 2 + c * x + d)
        elif fn == "sigmoid":
            out.append(A / (1.0 + math.exp(-k * (x - x0))))
        else:
            out.append(0.0)
    return out


def _render_plot_png(block: dict) -> bytes | None:
    if not _have_mpl():
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bg = block.get("bg") or "#0F0F1E"
    xR = block.get("xRange") or [-1, 1]
    yR = block.get("yRange") or [-1, 1]
    fig = plt.figure(figsize=(block["w"] / 100.0, block["h"] / 100.0), dpi=200)
    ax = fig.add_subplot(111)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.set_xlim(xR); ax.set_ylim(yR)

    if block.get("showGrid", True):
        ax.grid(True, color=(1, 1, 1, 0.08), linewidth=0.6)
    if not block.get("showAxes", True):
        for s in ax.spines.values():
            s.set_visible(False)
    else:
        for s in ax.spines.values():
            s.set_color((1, 1, 1, 0.4))
    ax.tick_params(colors=(1, 1, 1, 0.55) if block.get("showTickLabels", True) else (0, 0, 0, 0))
    if not block.get("showTickLabels", True):
        ax.set_xticklabels([]); ax.set_yticklabels([])

    n = 400
    xs = [xR[0] + (xR[1] - xR[0]) * i / (n - 1) for i in range(n)]
    for curve in block.get("curves", []):
        ys = _eval_curve(curve.get("fn", "sine"), xs, curve.get("params") or {})
        ax.plot(xs, ys, color=curve.get("color") or "#4ec5ff", linewidth=curve.get("width") or 3)

    if block.get("xLabel"):
        ax.set_xlabel(block["xLabel"], color=(1, 1, 1, 0.7))
    if block.get("yLabel"):
        ax.set_ylabel(block["yLabel"], color=(1, 1, 1, 0.7))

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=bg, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return buf.getvalue()


def _render_chart_png(block: dict) -> bytes | None:
    if not _have_mpl():
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bg = block.get("bg") or "#FFFFFF"
    primary = block.get("primaryColor") or "#1E2761"
    fig = plt.figure(figsize=(block["w"] / 100.0, block["h"] / 100.0), dpi=200)
    ax = fig.add_subplot(111)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)

    rows = block.get("data") or []
    labels = [str(r.get("label", "")) for r in rows]
    values = [r.get("value", 0) for r in rows]

    if block.get("kind") == "line":
        ax.plot(range(len(values)), values, color=primary, linewidth=3, marker="o")
    else:
        ax.bar(range(len(values)), values, color=primary)
    ax.set_xticks(range(len(values)))
    ax.set_xticklabels(labels)

    label_color = block.get("labelColor") or "#6C7A89"
    ax.tick_params(colors=label_color)
    grid_color = block.get("gridColor") or "#F1F5F9"
    ax.grid(True, color=grid_color, linewidth=0.6)
    for s in ax.spines.values():
        s.set_color(block.get("axisColor") or "#E5E7EB")

    if block.get("showValueLabels"):
        for i, v in enumerate(values):
            ax.text(i, v, str(v), ha="center", va="bottom", color=label_color, fontsize=9)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=bg, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return buf.getvalue()


# ---- main entry ----------------------------------------------------------

def render_specs(specs: list[dict], path: str) -> str:
    """Render a list of SlideSpec dicts (frontend shape) to a `.pptx` at `path`."""
    prs = Presentation()
    prs.slide_width = Inches(CANVAS_W_IN)
    prs.slide_height = Inches(CANVAS_H_IN)
    blank = prs.slide_layouts[6]

    for spec in specs:
        slide = prs.slides.add_slide(blank)
        canvas_w = spec.get("canvasW", 1280)
        canvas_h = spec.get("canvasH", 720)
        palette = spec.get("palette") or {}

        # background
        bg = slide.background
        bg.fill.solid()
        bg.fill.fore_color.rgb = _hex_to_rgb(palette.get("bg") or "#FFFFFF")

        for b in spec.get("blocks") or []:
            t = b.get("type")
            x_in = _px_to_inches(b.get("x", 0), canvas_w, CANVAS_W_IN)
            y_in = _px_to_inches(b.get("y", 0), canvas_h, CANVAS_H_IN)
            w_in = _px_to_inches(b.get("w", 0), canvas_w, CANVAS_W_IN)
            h_in = _px_to_inches(b.get("h", 0), canvas_h, CANVAS_H_IN)

            if t == "rect":
                _add_filled_rect(slide, x_in, y_in, w_in, h_in, b.get("fill") or "#000000",
                                 radius_px=b.get("radius", 0), canvas_w_px=canvas_w)
            elif t == "rule":
                _add_filled_rect(slide, x_in, y_in, w_in, h_in, b.get("color") or "#000000")
            elif t == "tag":
                radius_in = _px_to_inches(b.get("size", 12) or 12, canvas_w, CANVAS_W_IN)
                _add_filled_rect(slide, x_in, y_in, w_in, h_in, b.get("fill") or "#000000",
                                 radius_px=12, canvas_w_px=canvas_w)
                _add_text(slide, x_in, y_in, w_in, h_in, text=b.get("text", ""),
                          font="sans", size_pt=b.get("size") or 11, weight=600, italic=False,
                          color=b.get("color") or "#FFFFFF", align="center", valign="middle",
                          line_height=1.1, letter_spacing=0, transform="uppercase")
            elif t == "text":
                _add_text(slide, x_in, y_in, w_in, h_in,
                          text=b.get("text", ""),
                          font=b.get("font"),
                          size_pt=b.get("size") or 16,
                          weight=b.get("weight"),
                          italic=b.get("italic"),
                          color=b.get("color") or palette.get("ink") or "#000000",
                          align=b.get("align") or "left",
                          valign=b.get("valign") or "top",
                          line_height=b.get("lineHeight"),
                          letter_spacing=b.get("letterSpacing"),
                          transform=b.get("transform"))
            elif t == "bullets":
                _add_bullets(slide, x_in, y_in, w_in, h_in,
                             items=b.get("items") or [],
                             font=b.get("font"),
                             size_pt=b.get("size") or 18,
                             weight=b.get("weight"),
                             italic=b.get("italic"),
                             color=b.get("color") or palette.get("ink") or "#000000",
                             marker=b.get("marker") or "dot",
                             marker_color=b.get("markerColor"),
                             gap_px=b.get("gap"),
                             line_height=b.get("lineHeight"))
            elif t == "plot":
                png = _render_plot_png(b)
                if png:
                    pic = slide.shapes.add_picture(io.BytesIO(png),
                                                   Inches(x_in), Inches(y_in),
                                                   width=Inches(w_in), height=Inches(h_in))
                else:
                    _add_filled_rect(slide, x_in, y_in, w_in, h_in, b.get("bg") or "#0F0F1E")
                    _add_text(slide, x_in, y_in, w_in, h_in,
                              text="(plot — install matplotlib to render)",
                              font="mono", size_pt=12, weight=400, italic=False,
                              color="#FFFFFF", align="center", valign="middle",
                              line_height=1.2, letter_spacing=0, transform=None)
            elif t == "chart":
                png = _render_chart_png(b)
                if png:
                    slide.shapes.add_picture(io.BytesIO(png),
                                             Inches(x_in), Inches(y_in),
                                             width=Inches(w_in), height=Inches(h_in))
                else:
                    _add_filled_rect(slide, x_in, y_in, w_in, h_in, b.get("bg") or "#FFFFFF")
                    _add_text(slide, x_in, y_in, w_in, h_in,
                              text="(chart — install matplotlib to render)",
                              font="mono", size_pt=12, weight=400, italic=False,
                              color="#000000", align="center", valign="middle",
                              line_height=1.2, letter_spacing=0, transform=None)
            # unknown types ignored — judgment-free

    prs.save(path)
    return path
