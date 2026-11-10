"""
Template tests.

The contract (R0 still binding):
- A template yields a Theme + CONSTRAINTS. It never yields a content box.
- Reserved bands only shrink the engine's working area.
- Rendering onto a template keeps the template's master and drops its slides.
- Geometry is identical with and without a template at the same Theme:
  the template changes the backdrop and the brand, never a position.
- Bad uploads are refused, and a refused upload leaves nothing behind.
"""
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pptx import Presentation

from deckengine import template as T
from deckengine.ir import BlockKind, ContentBlock, LayoutIntent, PALETTES, Slide
from deckengine.layout import resolve
from deckengine.render import render_deck

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "frontend", "samples", "sample.pptx")

DECK = [
    Slide(intent=LayoutIntent.STAT_CALLOUT, blocks=[
        ContentBlock(BlockKind.TITLE, text="Q3 beat plan"),
        ContentBlock(BlockKind.STAT, value="+14%", label="vs plan", emphasis=2),
        ContentBlock(BlockKind.STAT, value="118%", label="retention"),
    ]),
    Slide(intent=LayoutIntent.BULLETS_PLAIN, blocks=[
        ContentBlock(BlockKind.TITLE, text="Why"),
        ContentBlock(BlockKind.BULLETS, items=["Enterprise", "Expansion", "Churn down"]),
    ]),
]


def _expect_error(fn, needle=""):
    try:
        fn()
    except T.TemplateError as e:
        assert needle in str(e), f"wrong error: {e}"
        return
    raise AssertionError("expected TemplateError")


def test_profile_carries_theme_and_constraints_only():
    p = T.profile_from_file(SAMPLE, tid="a" * 12, name="sample")
    assert p.theme.accent and p.theme.header_font
    assert p.slide_w > 0 and p.slide_h > 0
    d = T.to_dict(p)
    # No content geometry anywhere in what we hand the UI.
    for key in ("x", "y", "w", "h", "boxes"):
        assert key not in d, f"template profile leaked {key}"
    assert set(d["margins"]) == {"top", "bottom", "left", "right"}


def test_reserved_bands_only_shrink_the_working_area():
    p = T.profile_from_file(SAMPLE, tid="a" * 12)
    base = p.theme.margin_in
    assert all(v >= base for v in p.working_margins().values())
    p.reserved = [T.ReservedBand(edge="top", inches=0.8)]
    m = p.working_margins()
    assert m["top"] == base + 0.8
    assert m["bottom"] == base and m["left"] == base


def test_render_onto_template_keeps_master_drops_its_slides():
    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(T, "TEMPLATES_DIR", d):
            prof = T.save_template(open(SAMPLE, "rb").read(), "House Deck.pptx")
            out = os.path.join(d, "out.pptx")
            resolved = [resolve(s, prof.theme) for s in DECK]
            render_deck(resolved, out, template_path=T.template_path(prof.id))

            src, got = Presentation(SAMPLE), Presentation(out)
            assert len(got.slides) == len(DECK), "template's own slides must not survive"
            assert len(got.slide_masters) == len(src.slide_masters)
            assert all(len(s.shapes) > 0 for s in got.slides)


def test_template_changes_brand_not_geometry():
    """R1.6.1 in spirit: same Theme, same boxes, with or without a template."""
    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(T, "TEMPLATES_DIR", d):
            prof = T.save_template(open(SAMPLE, "rb").read(), "House.pptx")
            theme = prof.theme
            plain = [resolve(s, theme) for s in DECK]
            a = os.path.join(d, "a.pptx")
            b = os.path.join(d, "b.pptx")
            render_deck(plain, a)
            render_deck([resolve(s, theme) for s in DECK], b,
                        template_path=T.template_path(prof.id))

            for rs_a, rs_b in zip(Presentation(a).slides, Presentation(b).slides):
                pos_a = sorted((sh.left, sh.top, sh.width, sh.height) for sh in rs_a.shapes)
                pos_b = sorted((sh.left, sh.top, sh.width, sh.height) for sh in rs_b.shapes)
                assert pos_a == pos_b, "template moved a box — layout.py must own geometry"


def test_name_survives_a_round_trip_through_disk():
    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(T, "TEMPLATES_DIR", d):
            prof = T.save_template(open(SAMPLE, "rb").read(), "Northwind House Deck.pptx")
            assert T.load_template(prof.id).name == "Northwind House Deck"
            assert [t["name"] for t in T.list_templates()] == ["Northwind House Deck"]


def test_bad_uploads_are_refused_and_leave_nothing_behind():
    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(T, "TEMPLATES_DIR", d):
            _expect_error(lambda: T.save_template(b"x", "notes.txt"), "not a .pptx")
            _expect_error(lambda: T.save_template(b"", "empty.pptx"), "empty")
            _expect_error(lambda: T.save_template(b"x" * 10, "broken.pptx"), "could not read")
            assert os.listdir(d) == [], "a refused upload left a file behind"
            _expect_error(lambda: T.save_template(b"x" * (T.MAX_BYTES + 1), "big.pptx"), "capped")


def test_bad_ids_never_touch_the_filesystem():
    for tid in ["../../etc/passwd", "zz", "", "A" * 12, "a" * 40]:
        _expect_error(lambda t=tid: T.load_template(t), "bad template id")
    _expect_error(lambda: T.load_template("abcdef123456"), "no template")
    assert T.template_path(None) is None
    assert T.template_path("abcdef123456") is None


def test_backdrop_is_a_picture_of_the_master():
    """The preview backdrop must show the master, not just its colours."""
    if not T.backdrop_available():
        print("SKIP  no LibreOffice on this host")
        return
    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(T, "TEMPLATES_DIR", d):
            prof = T.save_template(open(SAMPLE, "rb").read(), "House.pptx")
            png = T.backdrop_png(prof.id)
            assert png and os.path.isfile(png)

            from PIL import Image
            with Image.open(png) as im:
                assert im.size[0] > 600 and im.size[1] > 300, f"tiny backdrop {im.size}"
                assert abs(im.size[0] / im.size[1] - 16 / 9) < 0.02, "backdrop is not 16:9"

            # Second call is served from cache, not re-rendered.
            before = os.path.getmtime(png)
            assert T.backdrop_png(prof.id) == png
            assert os.path.getmtime(png) == before


def test_background_is_sampled_from_the_render_not_the_theme():
    """A navy brand colour on white paper must not yield white-on-white."""
    if not T.backdrop_available():
        print("SKIP  no LibreOffice on this host")
        return
    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(T, "TEMPLATES_DIR", d):
            prof = T.save_template(open(SAMPLE, "rb").read(), "House.pptx")
            sampled = T.sample_backdrop(prof.id)
            assert sampled and "bg" in sampled and "dark" in sampled
            # This template renders on white, whatever its theme's dk2 says.
            assert sampled["dark"] is False, sampled
            d2 = T.to_dict(T.load_template(prof.id))
            assert d2["theme"]["dark"] is sampled["dark"], "profile ignored the sample"


def test_delete_takes_the_cached_backdrop_with_it():
    if not T.backdrop_available():
        print("SKIP  no LibreOffice on this host")
        return
    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(T, "TEMPLATES_DIR", d):
            prof = T.save_template(open(SAMPLE, "rb").read(), "House.pptx")
            png = T.backdrop_png(prof.id)
            T.delete_template(prof.id)
            assert not os.path.exists(png), "cached backdrop outlived its template"


def test_slides_carry_no_empty_placeholders():
    """An unfilled placeholder renders its prompt text — "Double-click to add
    an Image" — in the middle of the deck. The engine fills none of them."""
    from pptx import Presentation as _P
    from deckengine.render import open_base, add_slide, _content_placeholders

    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(T, "TEMPLATES_DIR", d):
            prof = T.save_template(open(SAMPLE, "rb").read(), "House.pptx")
            out = os.path.join(d, "out.pptx")
            render_deck([resolve(s, prof.theme) for s in DECK], out,
                        template_path=T.template_path(prof.id))
            for slide in _P(out).slides:
                assert not _content_placeholders(slide.shapes), \
                    "an empty content placeholder reached the deck"


def test_blankest_layout_prefers_the_quietest_one():
    """Real templates rarely ship a layout called Blank; picking by count of
    CONTENT placeholders avoids landing on title+picture."""
    from pptx import Presentation as _P
    from deckengine.render import _blankest_layout, _content_placeholders

    prs = _P(SAMPLE)
    chosen = _blankest_layout(prs)
    fewest = min(len(_content_placeholders(l.placeholders)) for l in prs.slide_layouts)
    assert len(_content_placeholders(chosen.placeholders)) == fewest


def test_delete_removes_it():
    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(T, "TEMPLATES_DIR", d):
            prof = T.save_template(open(SAMPLE, "rb").read(), "House.pptx")
            assert T.delete_template(prof.id) is True
            assert T.list_templates() == []


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
