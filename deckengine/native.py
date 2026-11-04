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

from typing import Any, Optional

from pptx import Presentation
from pptx.util import Emu

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


def render_native(slides: list[dict[str, Any]], path: str, template_path: str) -> str:
    """Render workspace slides into the template's own layouts."""
    from .render import open_base

    prs, _ = open_base(template_path, 13.333, 7.5)

    for slide in slides:
        title = (slide.get("title") or "").strip()
        body = _body_lines(slide)
        takeaway = (slide.get("takeaway") or "").strip()

        layout = pick_layout(prs, want_title=bool(title), want_body=bool(body),
                             want_subtitle=bool(takeaway))
        sl = prs.slides.add_slide(layout)
        roles = layout_roles(layout)

        used: set[int] = set()
        by_idx = {ph.placeholder_format.idx: ph for ph in sl.placeholders}

        if title and roles["title"] in by_idx:
            _fill(by_idx[roles["title"]], [title])
            used.add(roles["title"])

        # The takeaway goes in the subtitle when the layout has one; otherwise
        # it rides at the end of the body rather than being dropped.
        body_lines = list(body)
        if takeaway and roles["subtitle"] in by_idx:
            _fill(by_idx[roles["subtitle"]], [takeaway])
            used.add(roles["subtitle"])
        elif takeaway:
            body_lines.append(takeaway)

        if body_lines:
            for idx in roles["bodies"]:
                if idx in by_idx:
                    _fill(by_idx[idx], body_lines)
                    used.add(idx)
                    break

        # Anything the slide did not fill would render its prompt text.
        for ph in list(sl.placeholders):
            idx = ph.placeholder_format.idx
            if idx in used or _ph_type(ph) in PH_FURNITURE:
                continue
            _drop(ph)

    prs.save(path)
    return path
