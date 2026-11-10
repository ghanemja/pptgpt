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



def _counting_model():
    """A model that is 'available' and records every call it gets. It fails
    each call, so the cascade falls through and nothing is cached — the
    count is exactly how many times the slow tier was asked."""
    from deckengine import narrative
    calls = []

    def fn(prompt):
        calls.append(prompt)
        raise RuntimeError("stub model: refuse so the cascade falls through")

    narrative.reset_cache()
    narrative.set_llm(fn)
    return narrative, calls


def test_fast_engine_never_asks_the_model():
    narrative, calls = _counting_model()
    try:
        out = compute_thread_map(_messy_outline(), engine="fast")
        assert calls == [], f"fast read called the model {len(calls)}x"
        assert out["before"]["engine"] in ("semantic", "lexical")
        assert out["after"]["engine"] in ("semantic", "lexical")
    finally:
        narrative.set_llm(None)


def test_auto_engine_asks_the_model_first():
    narrative, calls = _counting_model()
    try:
        compute_thread_map(_messy_outline())
        assert len(calls) == 2, f"auto/both should read both sides, got {len(calls)}"
    finally:
        narrative.set_llm(None)


def test_before_only_pays_for_one_read_and_simulates_nothing():
    narrative, calls = _counting_model()
    try:
        recs = [{"id": "r1", "action": "merge", "slide_ids": ["s1", "s2"]}]
        out = compute_thread_map(_messy_outline(), recommendations=recs, sides="before")
        assert len(calls) == 1, f"sides='before' should be one model read, got {len(calls)}"
        assert out["after"] is None and out["diff"] is None
        assert out["applied"] == []
        assert out["before"]["graph"]["nodes"], "the deck as it stands is still read"
    finally:
        narrative.set_llm(None)


def test_fast_and_auto_agree_when_no_model_is_reachable():
    """Without a model the two engines are the same read — so the UI's fast
    first paint is never contradicted by the upgrade."""
    from deckengine import narrative
    narrative.set_llm(None)
    if narrative.available():
        return                      # a real model is configured here; nothing to compare
    a = compute_thread_map(_messy_outline(), engine="fast", sides="before")["before"]
    b = compute_thread_map(_messy_outline(), sides="before")["before"]
    assert a["graph"]["edges"] == b["graph"]["edges"] and a["engine"] == b["engine"]


def _hiring_outline() -> list[dict]:
    """A hiring ask with one stray message (slide 3) and one off-topic slide
    (slide 4) that the deck walks into and out of without a handoff."""
    rows = [
        ("t1", "We beat Q3 plan by 14%", ["Enterprise revenue drove the beat", "Net retention 118%", "Pipeline doubled"], "Enterprise is where the growth is."),
        ("t2", "Enterprise accounts expand fastest", ["Net retention 118% in enterprise", "SMB retention flat at 96%", "Expansion comes from seat growth"], "But we cannot cover the enterprise pipeline."),
        ("t3", "The enterprise pipeline is ageing", ["40 enterprise deals untouched for 30 days", "One AE covers 120 accounts", "Our new logo is ready"], "Two more enterprise AEs close the gap."),
        ("t4", "Office plants and kitchen refresh", ["New plants on floor 3", "Coffee machine replaced", "Snack budget unchanged"], ""),
        ("t5", "Two enterprise AEs pay back in two quarters", ["Each AE carries 1.2M quota", "Ramp is one quarter", "Payback by Q3"], "The risk is waiting."),
    ]
    return [{"id": i, "title": t, "messages": m, "bumper": b} for i, t, m, b in rows]


def _msg(flow, sid, text):
    sl = next(s for s in flow["slides"] if s["id"] == sid)
    return next(m for m in sl["messages"] if m["text"] == text)


def _handoff(flow, a, b):
    return next(h for h in flow["handoffs"] if h["from"] == a and h["to"] == b)


def test_flow_flags_a_stray_message():
    from deckengine.threadmap import flow
    f = flow(_hiring_outline())
    stray = _msg(f, "t3", "Our new logo is ready")
    assert stray["status"] == "orphan", f"stray message read as {stray['status']} ({f['engine']})"
    assert stray["picks_up"] is None
    # a message another slide picks up is linked, and says which slide
    pipe = _msg(f, "t1", "Pipeline doubled")
    assert pipe["status"] == "linked" and pipe["picks_up"] in ("t2", "t3")


def test_flow_ignores_generic_words_when_linking():
    # "new" is shared by "Our new logo" and "New plants" — not an idea.
    from deckengine.threadmap import flow
    stray = _msg(flow(_hiring_outline()), "t3", "Our new logo is ready")
    assert stray["picks_up"] != "t4"


def test_flow_marks_abrupt_and_smooth_handoffs():
    from deckengine.threadmap import flow
    f = flow(_hiring_outline())
    assert _handoff(f, "t2", "t3")["status"] == "smooth"
    assert _handoff(f, "t3", "t4")["status"] == "abrupt", "walking into the off-topic slide is a cut"
    assert _handoff(f, "t4", "t5")["status"] == "abrupt", "and out of it"


def test_flow_says_when_there_is_no_bumper():
    from deckengine.threadmap import flow
    h = _handoff(flow(_hiring_outline()), "t4", "t5")
    assert h["no_bumper"] is True and h["source"] == "Snack budget unchanged"
    assert _handoff(flow(_hiring_outline()), "t1", "t2")["no_bumper"] is False


def test_flow_is_data_only_and_rides_on_every_view():
    from deckengine.threadmap import flow
    out = compute_thread_map(_hiring_outline(), engine="fast", sides="before")
    f = out["before"]["flow"]
    assert f == flow(_hiring_outline()), "flow is deterministic and engine-independent"
    banned = {"x", "y", "w", "h", "color", "colour", "left", "top", "width", "height"}
    def walk(o):
        if isinstance(o, dict):
            assert not (banned & set(o)), f"geometry/colour leaked into flow: {banned & set(o)}"
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(f)
    assert compute_thread_map([], sides="before")["before"]["flow"]["slides"] == []

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
