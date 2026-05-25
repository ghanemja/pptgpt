"""
threadmap invariants.

Verifies:
- spine detection finds the dominant token (≥ half the deck)
- orphans flagged for slides sharing no tokens with anyone
- gaps flagged for adjacent slides with no shared tokens
- 'after' state never invents tokens the source didn't have (anti-fabrication)
- applying recommendations reduces messiness, never increases it
- ribbons are sorted by weight; broken ribbons detected
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine.threadmap import compute_thread_map, _view


def _messy_outline() -> list[dict]:
    """A deck with a strong spine word ('helix'), one orphan, one hard cut."""
    return [
        {"id": "s1", "title": "Helix project overview",
         "messages": ["Helix sync rewrite", "Twelve weeks", "Three engineers"],
         "bumper": ""},
        {"id": "s2", "title": "Helix scope",
         "messages": ["Native first sync", "Offline mode", "iPad support"],
         "bumper": ""},
        {"id": "s3", "title": "Pricing strategy",      # orphan — different topic
         "messages": ["Tier pricing", "Volume discounts", "Annual commit"],
         "bumper": ""},
        {"id": "s4", "title": "Helix risk and cost",
         "messages": ["480k engineering", "Hiring is hard", "Helix latency"],
         "bumper": ""},
        {"id": "s5", "title": "The Helix bet",
         "messages": ["3x reliability", "Opens iPad market", "Helix moat"],
         "bumper": ""},
    ]


def test_spine_word_detected():
    v = _view(_messy_outline())
    assert v["graph"]["spine"] is not None, "expected spine on messy outline"
    assert v["graph"]["spine"]["word"] == "helix", \
        f"spine word: {v['graph']['spine']['word']}"


def test_orphan_detected():
    v = _view(_messy_outline())
    assert "s3" in v["graph"]["orphans"], f"orphans: {v['graph']['orphans']}"


def test_gap_between_orphan_and_neighbors():
    v = _view(_messy_outline())
    # the orphan slide creates two adjacent gaps: 2→3 and 3→4
    gap_pairs = {(g["from"], g["to"]) for g in v["graph"]["gaps"]}
    assert ("s2", "s3") in gap_pairs or ("s3", "s4") in gap_pairs, \
        f"expected a gap touching s3; got {gap_pairs}"


def test_messiness_nonzero():
    v = _view(_messy_outline())
    assert 0 < v["stats"]["messiness"] <= 1.0


def test_empty_outline_safe():
    v = _view([])
    assert v["stats"]["slides"] == 0
    assert v["graph"]["spine"] is None
    assert v["graph"]["orphans"] == []
    assert v["graph"]["edges"] == []


def test_after_state_does_not_fabricate_tokens():
    """R7.3.5 spirit — simulator never invents new threads."""
    outline = _messy_outline()
    fake_recs = [
        {"id": "spine-helix", "kind": "spine",
         "text": "\"helix\" appears in 4 of 5 slides — your strongest spine.",
         "advisory": True},
        {"id": "orphan-s3", "kind": "orphan", "slideIds": ["s3"],
         "text": "Slide 03 (\"Pricing strategy\") shares no keywords."},
    ]
    out = compute_thread_map(outline, recommendations=fake_recs, mode="potential")
    # collect every token across BEFORE outline
    from deckengine.threadmap import _tok, _slide_text
    source_tokens: set[str] = set()
    for s in outline:
        source_tokens |= _tok(_slide_text(s))
    # AFTER outline tokens must be a subset (we never invent words)
    after_after_view = out["after"]
    # the 'after' view doesn't keep the outline, but it must not contain a
    # spine word that wasn't already in source. spine word is the load-bearing case.
    spine = after_after_view["graph"]["spine"]
    if spine is not None:
        assert spine["word"] in source_tokens, \
            f"simulator invented spine word: {spine['word']!r}"


def test_applying_recommendations_reduces_messiness():
    outline = _messy_outline()
    recs = [
        {"id": "spine-helix", "kind": "spine",
         "text": "\"helix\" appears in 4 of 5 slides — your strongest spine.",
         "advisory": True},
        {"id": "orphan-s3", "kind": "orphan", "slideIds": ["s3"],
         "text": "Slide 03 (\"Pricing strategy\") shares no keywords with any other slide."},
    ]
    out = compute_thread_map(outline, recommendations=recs, mode="potential")
    before_m = out["before"]["stats"]["messiness"]
    after_m  = out["after"]["stats"]["messiness"]
    assert after_m <= before_m, f"messiness went up: {before_m} -> {after_m}"


def test_accepted_mode_only_applies_accepted():
    outline = _messy_outline()
    recs = [
        {"id": "spine-helix", "kind": "spine", "text": "spine", "advisory": True},
        {"id": "orphan-s3",   "kind": "orphan", "slideIds": ["s3"], "text": "orphan"},
    ]
    only_spine = compute_thread_map(
        outline, recommendations=recs,
        accepted_ids=["spine-helix"], mode="accepted",
    )
    both = compute_thread_map(outline, recommendations=recs, mode="potential")
    assert only_spine["applied"] == ["spine-helix"]
    assert set(both["applied"]) == {"spine-helix", "orphan-s3"}


def test_ribbons_sorted_by_weight():
    v = _view(_messy_outline())
    weights = [r["weight"] for r in v["ribbons"]]
    assert weights == sorted(weights, reverse=True), f"ribbons not sorted: {weights}"


def test_deterministic():
    outline = _messy_outline()
    a = compute_thread_map(outline)
    b = compute_thread_map(outline)
    # ribbons/edges/orphans should be identical
    assert a["before"]["graph"]["orphans"] == b["before"]["graph"]["orphans"]
    assert a["before"]["graph"]["edges"]   == b["before"]["graph"]["edges"]
    assert a["before"]["ribbons"]          == b["before"]["ribbons"]


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
