"""
Condense invariants (REQUIREMENTS §7.4.2, §7.4.3).

Tests the deterministic stat-gathering fallback and the model-based path's
no-fabrication guard.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine.ir import Slide, ContentBlock, BlockKind, LayoutIntent, Deck, Theme
from deckengine.condense import condense_deterministic, condense_with_model


def _five_slide_deck() -> Deck:
    s1 = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="Q3 read"),
        ContentBlock(BlockKind.BULLETS, items=["Strong quarter", "Retention up"]),
    ], intent=LayoutIntent.BULLETS_PLAIN)
    s2 = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="The numbers"),
        ContentBlock(BlockKind.STAT, value="+14%", label="revenue vs plan"),
        ContentBlock(BlockKind.STAT, value="118%", label="net retention"),
        ContentBlock(BlockKind.STAT, value="1.8%",  label="monthly churn"),
    ], intent=LayoutIntent.STAT_CALLOUT)
    s3 = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="What's working"),
        ContentBlock(BlockKind.BULLETS, items=[
            "Enterprise close rate doubled",
            "Multi-year contracts now 60% of new ARR",
        ]),
    ], intent=LayoutIntent.BULLETS_PLAIN)
    s4 = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="What's not"),
        ContentBlock(BlockKind.BULLETS, items=["SMB CAC up 30%"]),
        ContentBlock(BlockKind.STAT, value="$42M", label="ARR"),
    ], intent=LayoutIntent.STAT_CALLOUT)
    s5 = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="Next quarter"),
        ContentBlock(BlockKind.BULLETS, items=["Pause SMB paid", "Hire enterprise AEs"]),
    ], intent=LayoutIntent.BULLETS_PLAIN)
    return Deck(slides=[s1, s2, s3, s4, s5], theme=Theme(), title="Q3 board update")


def test_deterministic_keeps_only_source_stats():
    """R7.3.5 — no fabrication. Every emitted stat exists in the source."""
    deck = _five_slide_deck()
    out = condense_deterministic(deck)
    source_vals = set()
    for s in deck.slides:
        for b in s.blocks:
            if b.value: source_vals.add(b.value)
    for s in out.slides:
        for b in s.blocks:
            if b.kind == BlockKind.STAT:
                assert b.value in source_vals, f"fabricated stat: {b.value!r}"


def test_deterministic_carries_provenance():
    """R7.3.3 — output must be reviewable. notes carry source indices."""
    deck = _five_slide_deck()
    out = condense_deterministic(deck)
    for s in out.slides:
        assert s.notes is not None, "every condensed slide must declare provenance"
        assert "Source" in s.notes or "deterministic" in s.notes


def test_deterministic_promotes_a_hero():
    deck = _five_slide_deck()
    out = condense_deterministic(deck)
    stat_slide = next((s for s in out.slides
                       if any(b.kind == BlockKind.STAT for b in s.blocks)), None)
    assert stat_slide is not None, "should produce a stat slide when stats exist"
    stats = [b for b in stat_slide.blocks if b.kind == BlockKind.STAT]
    assert any(b.emphasis >= 2 for b in stats), "no hero promoted"


def test_deterministic_max_slides_respected():
    deck = _five_slide_deck()
    out2 = condense_deterministic(deck, max_slides=2)
    assert len(out2.slides) <= 2


def test_deterministic_insufficient_content_is_truthful():
    """R7.3.5 — return truthful 'insufficient content' rather than invent."""
    empty = Deck(
        slides=[Slide(blocks=[ContentBlock(BlockKind.TITLE, text="Cover")],
                      intent=LayoutIntent.TITLE_SLIDE)],
        theme=Theme(),
        title="Tiny deck",
    )
    out = condense_deterministic(empty)
    # output has the cover plus a truthful "insufficient" slide; no stats invented
    has_stat = any(b.kind == BlockKind.STAT for s in out.slides for b in s.blocks)
    assert not has_stat, "deterministic condense fabricated stats from empty source"
    insufficient = any("nsufficient" in (s.blocks[0].text or "")
                       for s in out.slides if s.blocks and s.blocks[0].kind == BlockKind.TITLE)
    assert insufficient, "condense should announce insufficient content"


def test_model_path_falls_back_when_no_model():
    """When no model is provided, behavior matches deterministic + label."""
    deck = _five_slide_deck()
    out = condense_with_model(deck, model_fn=None)
    assert any("deterministic" in (s.notes or "") for s in out.slides)


def test_model_path_filters_fabrications():
    """R7.3.5 — model output containing values absent from source is dropped."""
    deck = _five_slide_deck()

    # A "model" that fabricates: emits a stat value not in the source.
    def liar(_prompt: str) -> str:
        return json.dumps({
            "slides": [
                {
                    "blocks": [
                        {"kind": "title", "text": "Fabricated cover"},
                        {"kind": "stat", "value": "+99%", "label": "made up"},
                    ],
                    "intent": "stat_callout",
                    "notes": "model invented this",
                }
            ]
        })

    out = condense_with_model(deck, model_fn=liar)
    # the fabricated stat must not survive; nor the unanchored title
    for s in out.slides:
        for b in s.blocks:
            if b.kind == BlockKind.STAT:
                assert b.value != "+99%", "fabricated stat reached output"


def test_model_path_keeps_anchored_content():
    """Output validity: a model can return a valid subset of the source."""
    deck = _five_slide_deck()

    def honest(_prompt: str) -> str:
        return json.dumps({
            "slides": [
                {
                    "blocks": [
                        {"kind": "title", "text": "The numbers"},
                        {"kind": "stat", "value": "+14%", "label": "revenue vs plan", "emphasis": 2},
                    ],
                    "intent": "stat_callout",
                    "notes": "Source: slide 2",
                }
            ]
        })

    out = condense_with_model(deck, model_fn=honest)
    assert len(out.slides) == 1
    assert any(b.kind == BlockKind.STAT and b.value == "+14%" for b in out.slides[0].blocks)


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
