"""native.py — render a slide INTO the template's own placeholders.

Why this exists, and what it means for §0.

The engine's own renderer draws text boxes it positions itself. That is the
right behaviour with no template: `layout.py` owns geometry and its
invariants (margins, no overlap) are measured. But a real .pptx template is
not a palette with a logo on it — its design IS its layouts. The template
this was built against puts its title at (4.06, 2.70) in a 5.22in column
with the content stack to its right. Approximating that with our own boxes
produced a deck that used the template's colours and ignored its design, no
matter how carefully the colours and fonts were copied across.

So when a template is applied, the template owns geometry and type, and the
engine's job changes from PLACING content to CASTING it: pick the layout
whose roles fit what this slide carries, then fill that layout's
placeholders. Everything a placeholder does not have set — position, size,
font, size ramp, colour, alignment, bullet glyphs — inherits from the layout
and master exactly as PowerPoint intends.

§0 still holds where it matters: the MODEL never chooses geometry, and
neither does the UI. The choice is a deterministic function of the slide's
content and the template's layout inventory, made here. Without a template
nothing changes — `layout.py` resolves as before.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from pptx import Presentation
from pptx.util import Emu

from .template import profile_from_file, sample_backdrop

# Placeholder type ids (MSO_PLACEHOLDER) we care about.
PH_TITLE, PH_BODY, PH_CENTER_TITLE, PH_SUBTITLE = 1, 2, 3, 4
PH_OBJECT, PH_PICTURE = 7, 18
PH_FURNITURE = {13, 15, 16}          # slide number, footer, date

_TITLE_TYPES = {PH_TITLE, PH_CENTER_TITLE}
_BODY_TYPES = {PH_BODY, PH_OBJECT}


def _ph_type(shape) -> int:
    try:
        return int(shape.placeholder_format.type)
    except (TypeError, ValueError, AttributeError):
        return -1


def layout_roles(layout) -> dict[str, Any]:
    """What this layout offers: a title, body slots, a subtitle, a picture."""
    roles: dict[str, Any] = {"title": None, "bodies": [], "subtitle": None,
                             "pictures": [], "furniture": []}
    for ph in layout.placeholders:
        kind = _ph_type(ph)
        if kind in _TITLE_TYPES:
            roles["title"] = ph.placeholder_format.idx
        elif kind == PH_SUBTITLE:
            roles["subtitle"] = ph.placeholder_format.idx
        elif kind in _BODY_TYPES:
            roles["bodies"].append(ph.placeholder_format.idx)
        elif kind == PH_PICTURE:
            roles["pictures"].append(ph.placeholder_format.idx)
        elif kind in PH_FURNITURE:
            roles["furniture"].append(ph.placeholder_format.idx)
    return roles


# ---- roles -----------------------------------------------------------------
#
# A template carries more than one kind of slide: an opener, a section break,
# a two-column comparison, a picture slide. Casting everything as
# title-plus-bullets used one layout and left the rest of the template unused.
# A slide's role is read off what it CARRIES — deterministically, here, not by
# the model and not by the UI.

ROLE_COVER = "cover"            # the opener: big title, maybe a subtitle
ROLE_SECTION = "section"        # a break between acts: a title and nothing else
ROLE_STATEMENT = "statement"    # one line that is the whole slide
ROLE_PICTURE = "picture"        # carries an image or a rendered chart
ROLE_TWO = "two"                # enough points to read as two columns
ROLE_BULLETS = "bullets"        # the ordinary case

# Layout names are the template author's own labels. Matching them is a hint,
# never the decision — structure is checked first and a name only breaks ties.
_NAME_HINTS = {
    ROLE_COVER: ("title slide", "cover", "opening", "opener"),
    ROLE_SECTION: ("section", "divider", "chapter", "part", "break"),
    ROLE_STATEMENT: ("statement", "quote", "big", "title only"),
    ROLE_PICTURE: ("picture", "image", "photo", "media"),
    ROLE_TWO: ("two content", "two-content", "comparison", "compare", "split"),
    ROLE_BULLETS: ("title + content", "title and content", "content", "bullets"),
}

TWO_COLUMN_MIN_POINTS = 4


def classify(slide: dict[str, Any]) -> str:
    """Which kind of slide this is, from its content alone."""
    kind = (slide.get("kind") or "text").lower()
    points = [b for b in (slide.get("bullets") or []) if str(b).strip()]
    has_title = bool((slide.get("title") or "").strip())
    has_takeaway = bool((slide.get("takeaway") or "").strip())

    if kind == "cover":
        return ROLE_COVER
    if kind in ("chart", "plot", "diagram") or slide.get("image") or slide.get("images"):
        return ROLE_PICTURE
    if not points and not slide.get("metric"):
        # A title alone is a section break; a title plus one line is a
        # statement slide. Neither wants a bullet list.
        return ROLE_STATEMENT if (has_title and has_takeaway) else ROLE_SECTION
    if len(points) >= TWO_COLUMN_MIN_POINTS:
        return ROLE_TWO
    return ROLE_BULLETS


def _wants(role: str, slide: dict[str, Any]) -> dict[str, Any]:
    """What this role needs from a layout."""
    points = [b for b in (slide.get("bullets") or []) if str(b).strip()]
    has_takeaway = bool((slide.get("takeaway") or "").strip())
    return {
        ROLE_COVER:     {"title": True, "bodies": 0, "subtitle": True, "picture": False},
        ROLE_SECTION:   {"title": True, "bodies": 0, "subtitle": False, "picture": False},
        ROLE_STATEMENT: {"title": True, "bodies": 0, "subtitle": has_takeaway, "picture": False},
        ROLE_PICTURE:   {"title": True, "bodies": 1 if points else 0,
                         "subtitle": False, "picture": True},
        ROLE_TWO:       {"title": True, "bodies": 2, "subtitle": False, "picture": False},
        ROLE_BULLETS:   {"title": True, "bodies": 1, "subtitle": has_takeaway, "picture": False},
    }[role]


def score_layout(layout, want: dict[str, Any], role: str, index: int) -> float:
    """Lower is better. Structure dominates; the layout's name breaks ties."""
    roles = layout_roles(layout)
    have_bodies = len(roles["bodies"])
    have_pics = len(roles["pictures"])

    missing = 0
    if want["title"] and roles["title"] is None:
        missing += 1
    missing += max(0, want["bodies"] - have_bodies)
    if want["picture"] and not have_pics:
        missing += 1

    spare = max(0, have_bodies - want["bodies"])
    spare += max(0, have_pics - (1 if want["picture"] else 0))
    if roles["subtitle"] is not None and not want["subtitle"]:
        spare += 1
    if want["subtitle"] and roles["subtitle"] is None:
        spare += 1          # usable, but the takeaway has to ride in the body

    name = (layout.name or "").strip().lower()
    hinted = any(h in name for h in _NAME_HINTS.get(role, ()))
    return missing * 100 + spare * 10 + (0 if hinted else 1) + index * 0.001


def pick_layout_for(prs, slide: dict[str, Any], role: Optional[str] = None):
    """The layout this slide should be cast into. Deterministic."""
    role = role or classify(slide)
    want = _wants(role, slide)
    return min(
        (l for l in prs.slide_layouts),
        key=lambda l: score_layout(l, want, role, list(prs.slide_layouts).index(l)),
    )


def pick_layout(prs, *, want_title: bool, want_body: bool, want_subtitle: bool):
    """The layout that fits this slide's content with least left over.

    Deterministic: layouts are scored, ties break on the earlier layout, so
    the same slide against the same template always casts the same way.
    """
    best, best_score = None, None
    for i, layout in enumerate(prs.slide_layouts):
        roles = layout_roles(layout)
        has_title = roles["title"] is not None
        has_body = bool(roles["bodies"])
        has_sub = roles["subtitle"] is not None

        # Missing something we need is disqualifying unless nothing else fits.
        missing = (want_title and not has_title) + (want_body and not has_body)
        # Slots we would leave empty are clutter the slide has to carry.
        spare = (len(roles["pictures"])
                 + max(0, len(roles["bodies"]) - (1 if want_body else 0))
                 + (1 if has_sub and not want_subtitle else 0))
        subtitle_fit = 0 if (want_subtitle and has_sub) else (1 if want_subtitle else 0)

        score = (missing * 100) + (spare * 10) + subtitle_fit + (i * 0.001)
        if best_score is None or score < best_score:
            best, best_score = layout, score
    return best


def _fill(ph, lines: list[str]) -> None:
    """Put text in a placeholder without touching how it is styled.

    Only the text is set: no font, size, colour or alignment is written, so
    every one of those inherits from the layout and master. The first
    paragraph is reused (it carries the placeholder's own level-0 style) and
    the rest are added at the same level.
    """
    tf = ph.text_frame
    tf.clear()
    # The template sized this box for its own copy, not ours. Shrink-to-fit
    # keeps a long list inside the design instead of running off it; the
    # placeholder's own type ramp still decides where it starts from.
    from .spec_render import _shrink_on_overflow
    _shrink_on_overflow(tf)
    first, *rest = lines or [""]
    tf.paragraphs[0].text = first
    for line in rest:
        para = tf.add_paragraph()
        para.text = line
        para.level = 0


def _drop(shape) -> None:
    shape._element.getparent().remove(shape._element)


def _body_lines(slide: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    metric, sub = slide.get("metric"), slide.get("metricSub")
    if metric:
        lines.append(f"{metric} — {sub}" if sub else str(metric))
    lines.extend([str(b) for b in (slide.get("bullets") or []) if str(b).strip()])
    return lines


def _chart_palette(profile) -> dict[str, str]:
    """Chart colours taken from the template, not from the engine.

    A chart drawn in the engine's own emerald on white sits on a brand
    template looking like it was pasted in from somewhere else — which is
    what it was. The bars take the template's accent, the plate takes the
    background its master actually renders, and the labels take whatever
    reads against that.
    """
    theme = getattr(profile, "theme", None)
    accent = getattr(theme, "accent", None) or "1E2761"
    sampled = sample_backdrop(profile.id) if getattr(profile, "id", "") else None
    bg = (sampled or {}).get("bg") or getattr(theme, "primary", None) or "FFFFFF"
    dark = (sampled or {}).get("dark")
    if dark is None:
        dark = bool(getattr(theme, "dark", False))
    ink = "FFFFFF" if dark else "11120E"

    # A brand accent is chosen to sit beside the background, not to be read
    # against it: this template's accent1 is olive on an olive master, which
    # draws bars you cannot see. Fall back to the text colour when the
    # contrast is too thin to carry data.
    from .template import _luma
    if abs(_luma(accent) - _luma(bg)) < 0.22:
        accent = ink

    return {
        "bg": f"#{bg}",
        "primaryColor": f"#{accent}",
        "highlightColor": f"#{getattr(theme, 'secondary', None) or accent}",
        "labelColor": f"#{ink}",
        "axisColor": f"#{ink}",
        "gridColor": f"#{ink}",
    }


def _visual_png(slide: dict[str, Any], profile=None) -> Optional[bytes]:
    """The slide's visual as PNG bytes, if it has one.

    A chart or a plot is content, and a template usually has somewhere
    designed to put a picture. Rendering it here lets the cast slide use
    that slot instead of dropping the visual on the floor.
    """
    chart = slide.get("chart")
    if chart and chart.get("data"):
        from .spec_render import _render_chart_png
        rows = [r for r in chart["data"] if r.get("label") is not None]
        if rows:
            opts = chart.get("options") or {}
            block = {
                "w": 900, "h": 520,
                "kind": chart.get("kind") or "column",
                "data": [{"label": str(r.get("label")), "value": r.get("value") or 0,
                          "hi": bool(r.get("hi"))} for r in rows],
                "sort": opts.get("sort") or "source",
                "highlight": opts.get("highlight"),
                "gridlines": bool(opts.get("gridlines")),
                "showValueLabels": opts.get("valueLabels") is not False,
            }
            if profile is not None:
                block.update(_chart_palette(profile))
            return _render_chart_png(block)
    diagram = slide.get("diagram")
    if diagram and diagram.get("steps"):
        from .spec_render import _render_diagram_png
        block = {"w": 900, "h": 420, "kind": diagram.get("kind") or "flow",
                 "steps": diagram.get("steps") or []}
        if profile is not None:
            block.update(_chart_palette(profile))
        return _render_diagram_png(block)

    plot = slide.get("plot")
    if plot:
        from .spec_render import _render_plot_png
        return _render_plot_png({"plot": plot, "fn": plot.get("fn"),
                                 "params": plot.get("params") or {}})
    return None


def _place_picture(sl, ph, png: bytes) -> bool:
    """Put an image where the template says images go.

    A PICTURE placeholder takes one directly and keeps the template's crop
    and frame. Any other slot is replaced by a picture at its own bounds, so
    the image still lands where the design put it.
    """
    import tempfile as _tempfile

    with _tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        fh.write(png)
        tmp = fh.name
    try:
        if _ph_type(ph) == PH_PICTURE:
            frame = (ph.left, ph.top, ph.width, ph.height)
            pic = ph.insert_picture(tmp)
            # insert_picture fills the frame and CROPS the overflow, which is
            # right for a photo and wrong for a chart — it eats the axis. Clear
            # the crop and letterbox inside the frame the template drew.
            pic.crop_left = pic.crop_right = pic.crop_top = pic.crop_bottom = 0
            _fit_inside(pic, *frame)
            return True
        left, top, width, height = ph.left, ph.top, ph.width, ph.height
        _drop(ph)
        pic = sl.shapes.add_picture(tmp, left, top)
        _fit_inside(pic, left, top, width, height)
        return True
    except Exception:
        return False
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _fit_inside(pic, left: int, top: int, width: int, height: int) -> None:
    """Scale a picture to fit a frame whole, centred, aspect preserved."""
    native_w, native_h = pic.image.size
    if not native_w or not native_h or not width or not height:
        return
    k = min(width / native_w, height / native_h)
    pic.width = int(native_w * k)
    pic.height = int(native_h * k)
    pic.left = int(left + (width - pic.width) / 2)
    pic.top = int(top + (height - pic.height) / 2)


def _split(points: list[str]) -> tuple[list[str], list[str]]:
    """Halve a list for a two-column layout, heavier column first."""
    half = (len(points) + 1) // 2
    return points[:half], points[half:]


def render_native(slides: list[dict[str, Any]], path: str, template_path: str) -> str:
    """Render workspace slides into the template's own layouts.

    Each slide is classified, matched to the layout that fits that role, and
    its content filled into that layout's placeholders. Only text and images
    are written; everything about how they look is the template's.
    """
    from .render import open_base

    prs, _ = open_base(template_path, 13.333, 7.5)
    try:
        profile = profile_from_file(template_path)
    except Exception:
        profile = None

    for slide in slides:
        role = classify(slide)
        layout = pick_layout_for(prs, slide, role)
        sl = prs.slides.add_slide(layout)
        roles = layout_roles(layout)
        by_idx = {ph.placeholder_format.idx: ph for ph in sl.placeholders}
        used: set[int] = set()

        title = (slide.get("title") or "").strip()
        takeaway = (slide.get("takeaway") or "").strip()
        subtitle = (slide.get("subtitle") or "").strip()
        points = _body_lines(slide)

        if title and roles["title"] in by_idx:
            _fill(by_idx[roles["title"]], [title])
            used.add(roles["title"])

        # A cover's deck-level line is its subtitle; every other role uses the
        # takeaway there, because that is the line the slide is making.
        second = subtitle if role == ROLE_COVER and subtitle else takeaway
        if second and roles["subtitle"] in by_idx:
            _fill(by_idx[roles["subtitle"]], [second])
            used.add(roles["subtitle"])
            second = ""

        # The visual goes in the designed slot before the text claims it.
        if role == ROLE_PICTURE:
            png = _visual_png(slide, profile)
            slots = [i for i in roles["pictures"] if i in by_idx] or \
                    [i for i in roles["bodies"] if i in by_idx]
            if png and slots:
                if _place_picture(sl, by_idx[slots[0]], png):
                    used.add(slots[0])

        bodies = [i for i in roles["bodies"] if i in by_idx and i not in used]
        lines = list(points)
        if second:
            lines.append(second)        # no subtitle slot: it rides in the body

        if lines and bodies:
            if role == ROLE_TWO and len(bodies) >= 2:
                left, right = _split(lines)
                _fill(by_idx[bodies[0]], left)
                _fill(by_idx[bodies[1]], right)
                used.update({bodies[0], bodies[1]})
            else:
                _fill(by_idx[bodies[0]], lines)
                used.add(bodies[0])

        # Anything the slide did not fill would render its prompt text.
        for ph in list(sl.placeholders):
            idx = ph.placeholder_format.idx
            if idx in used or _ph_type(ph) in PH_FURNITURE:
                continue
            _drop(ph)

    prs.save(path)
    return path
