"""
Native casting tests.

The contract when a template is applied:
- Geometry comes from the TEMPLATE's placeholders, not from our own boxes.
- Text is set without writing any font/size/colour, so every style inherits.
- Layout choice is deterministic for the same slide + template.
- Unfilled content placeholders never survive (they render prompt text).
- Footer/date/slide-number furniture does survive — it is the template's.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pptx import Presentation
from pptx.util import Emu

from deckengine.native import (
    PH_FURNITURE, layout_roles, pick_layout, render_native, _ph_type,
)

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "frontend", "v2-assets", "samples", "sample.pptx")

SLIDE = {
    "title": "We beat Q3 plan by 14%",
    "bullets": ["Net retention 118%", "Churn down to 1.8%"],
    "takeaway": "Approve the hire plan.",
}


def _render(tmp="/tmp/deckengine-native-test.pptx", slides=None):
    render_native(slides or [SLIDE], tmp, SAMPLE)
    return Presentation(tmp)


def test_geometry_comes_from_the_template():
    prs = _render()
    src = Presentation(SAMPLE)
    layout = pick_layout(src, want_title=True, want_body=True, want_subtitle=True)
    want = {(ph.placeholder_format.idx): (ph.left, ph.top, ph.width, ph.height)
            for ph in layout.placeholders}

    got = prs.slides[0]
    assert got.shapes, "nothing rendered"
    for shape in got.shapes:
        idx = shape.placeholder_format.idx
        assert idx in want, f"shape {shape.name} is not one of the template's placeholders"
        assert (shape.left, shape.top, shape.width, shape.height) == want[idx], \
            "a cast slide moved the template's placeholder"


def test_text_is_set_without_overriding_style():
    """No run may carry its own size/colour/font — all of it inherits."""
    prs = _render()
    for shape in prs.slides[0].shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                assert run.font.size is None, "a run hardcoded a size"
                assert run.font.name is None, "a run hardcoded a typeface"
                assert run.font.color.type is None, "a run hardcoded a colour"


def test_content_lands_where_the_roles_say():
    prs = _render()
    texts = {}
    src_layout = pick_layout(Presentation(SAMPLE), want_title=True, want_body=True,
                             want_subtitle=True)
    roles = layout_roles(src_layout)
    for shape in prs.slides[0].shapes:
        texts[shape.placeholder_format.idx] = shape.text_frame.text

    assert texts.get(roles["title"]) == SLIDE["title"]
    body_idx = next((i for i in roles["bodies"] if i in texts), None)
    assert body_idx is not None, "no body was filled"
    body = texts[body_idx]
    for bullet in SLIDE["bullets"]:
        assert bullet in body
    # The takeaway rides in the subtitle when there is one, else in the body.
    assert SLIDE["takeaway"] in body or SLIDE["takeaway"] in texts.get(roles["subtitle"], "")


def test_no_empty_content_placeholder_survives():
    prs = _render(slides=[{"title": "Title only"}])
    for shape in prs.slides[0].shapes:
        if _ph_type(shape) in PH_FURNITURE:
            continue
        assert shape.text_frame.text.strip(), "an empty placeholder would render its prompt"


def test_layout_choice_is_deterministic():
    src = Presentation(SAMPLE)
    picks = {pick_layout(src, want_title=True, want_body=True, want_subtitle=False).name
             for _ in range(5)}
    assert len(picks) == 1, picks


def test_a_slide_with_no_body_does_not_demand_one():
    src = Presentation(SAMPLE)
    chosen = pick_layout(src, want_title=True, want_body=False, want_subtitle=False)
    roles = layout_roles(chosen)
    assert roles["title"] is not None
    assert not roles["pictures"], "picked a layout with an unfillable picture slot"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
