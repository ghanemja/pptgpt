"""
Ingest invariants (REQUIREMENTS §7.4.1).

These tests verify the architectural contract, not the heuristics:
- content is extracted (R7.2.1)
- geometry is NOT carried into the IR (R7.2.2) — anti-leak test
- unparseable input degrades, never crashes (R7.2.5)
- image binary data does not flow into the IR (R7.2.4)
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine.ingest import ingest_pptx_bytes
from deckengine.ir import BlockKind, ContentBlock, Slide, Theme
from deckengine.parse import parse_deck_to_ir
from deckengine.render import render_deck
from deckengine.layout import resolve


def _build_fixture_pptx() -> bytes:
    """Build a small in-memory .pptx with known content for round-trip tests."""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()
    blank = prs.slide_layouts[6]  # blank
    layout_title = prs.slide_layouts[5]  # title-only

    # slide 1: title + body
    s1 = prs.slides.add_slide(layout_title)
    s1.shapes.title.text = "Q3 board update"
    tb = s1.shapes.add_textbox(Inches(0.5), Inches(2), Inches(8), Inches(3))
    tf = tb.text_frame
    tf.text = "Retention up 4 points"
    tf.add_paragraph().text = "Churn down to 1.8%"
    tf.add_paragraph().text = "New cohort LTV +22%"

    # slide 2: a stat-heavy slide
    s2 = prs.slides.add_slide(layout_title)
    s2.shapes.title.text = "The numbers"
    body = s2.shapes.add_textbox(Inches(0.5), Inches(2), Inches(8), Inches(3))
    body.text_frame.text = "+14%"
    p = body.text_frame.add_paragraph(); p.text = "118%"
    p = body.text_frame.add_paragraph(); p.text = "$42M"

    # slide 3: empty body
    s3 = prs.slides.add_slide(blank)

    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


def test_ingest_extracts_content():
    deck = ingest_pptx_bytes(_build_fixture_pptx())
    assert len(deck.slides) == 3, f"expected 3 slides, got {len(deck.slides)}"
    titles = [next((b.text for b in s.blocks if b.kind == BlockKind.TITLE), None) for s in deck.slides]
    assert titles[0] == "Q3 board update"
    assert titles[1] == "The numbers"


def test_ingest_does_not_carry_geometry():
    """R7.2.2 — anti-leak. No ContentBlock should have positional data."""
    deck = ingest_pptx_bytes(_build_fixture_pptx())
    for s in deck.slides:
        for b in s.blocks:
            # the ContentBlock dataclass has no x/y/w/h fields by design;
            # this test guards against future violations.
            for forbidden in ("x", "y", "w", "h", "left", "top", "width", "height"):
                assert not hasattr(b, forbidden), f"ingest leaked geometry: {forbidden}"


def test_ingest_classifies_stats():
    deck = ingest_pptx_bytes(_build_fixture_pptx())
    stats_per_slide = [
        [b for b in s.blocks if b.kind == BlockKind.STAT] for s in deck.slides
    ]
    # slide 2 should have surfaced at least one stat
    assert len(stats_per_slide[1]) >= 2, f"expected stats on slide 2, got {stats_per_slide[1]}"
    # hero promoted
    has_hero = any(b.emphasis >= 2 for b in stats_per_slide[1])
    assert has_hero, "ingest should promote a hero stat"


def test_ingest_degrades_on_empty():
    """R7.2.5 — empty / odd slide should not crash."""
    deck = ingest_pptx_bytes(_build_fixture_pptx())
    # the 3rd (blank) slide should still produce an IR slide
    assert len(deck.slides) >= 3
    s = deck.slides[2]
    # at minimum has a title block
    assert any(b.kind == BlockKind.TITLE for b in s.blocks)


def test_ingest_no_image_binary_in_ir():
    """R7.2.4 — image content stays as a presence marker, never binary."""
    deck = ingest_pptx_bytes(_build_fixture_pptx())
    for s in deck.slides:
        for b in s.blocks:
            # no field on ContentBlock can carry bytes
            for v in (b.text, b.value, b.label):
                assert not isinstance(v, (bytes, bytearray)), "binary leaked into IR"


def test_ingest_round_trip_renders():
    """Ingest → engine → render produces an openable .pptx."""
    data = _build_fixture_pptx()
    deck = ingest_pptx_bytes(data)
    resolved = [resolve(s, Theme()) for s in deck.slides]
    import tempfile
    fd, out_path = tempfile.mkstemp(prefix="ingest-roundtrip-", suffix=".pptx")
    os.close(fd)
    render_deck(resolved, out_path)
    assert os.path.exists(out_path) and os.path.getsize(out_path) > 1000, "round-trip pptx too small"
    os.unlink(out_path)


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
