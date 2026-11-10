"""
Narrative-module tests with a stub LLM.

These verify the orchestration, not LLM quality:
- happy path: stub returns valid JSON, result is shaped correctly
- anti-fabrication: stub references a slide_id not in source, recommendation is dropped
- cache hit: same outline twice = one stub call
- JSON-in-prose: stub wraps JSON in ```json fences, extractor still works
- parse failure: stub returns garbage = analyze_narrative returns None
- LLM raises: returns None, never crashes the caller
- to_storyboard_recs adapter shape
- to_threadmap_view adapter shape (edges come from the LLM's groupings, not similarity)
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine import narrative


SAMPLE_OUTLINE = [
    {"id": "s1", "title": "Q3 board update",
     "messages": ["Revenue beat plan", "Retention strong", "Enterprise pull-forward"],
     "bumper": ""},
    {"id": "s2", "title": "The numbers",
     "messages": ["+14% YoY", "NRR 118%", "Churn 1.8%"], "bumper": ""},
    {"id": "s3", "title": "Pricing strategy",
     "messages": ["Tier review", "Volume discounts", "Annual commitment"], "bumper": ""},
    {"id": "s4", "title": "What we'll do",
     "messages": ["Pause SMB", "Double down enterprise", "Hire two AEs"], "bumper": ""},
]


def _stub(payload):
    """Return a callable that always returns the given payload as JSON text."""
    def fn(_prompt):
        if isinstance(payload, str):
            return payload
        return json.dumps(payload)
    return fn


def setup_function():
    narrative.reset_cache()
    narrative.set_llm(None)


def teardown_function():
    narrative.set_llm(None)


# ---- happy path ----------------------------------------------------------

GOOD_RESPONSE = {
    "spine": "The deck argues that Q3 reliability and revenue both improved, justifying a doubling-down on enterprise GTM.",
    "arc": "claim→evidence→takeaway",
    "orphans": [
        {"slide_id": "s3",
         "reason": "Pricing strategy is unrelated to the Q3-momentum through-line."}
    ],
    "gaps": [
        {"from": "s2", "to": "s3",
         "missing": "no bridge between the numbers and the pricing tangent",
         "bridge_suggestion": "Move pricing out of this deck or tie it to ARR growth."}
    ],
    "tensions": [
        {"slides": ["s1", "s4"],
         "issue": "Slide 1 frames the quarter as strong, slide 4 calls for a pause — the narrative needs to reconcile.",
         "kind": "contradiction"}
    ],
    "recommendations": [
        {"id": "spine-1", "kind": "spine",
         "text": "Lead with the through-line: Q3 worked, here's why, here's what changes.",
         "target_slide_ids": ["s1", "s2", "s4"], "advisory": True,
         "suggested_edit": "Open with: 'Q3 worked. Here's why, and what changes next.'"},
        {"id": "drop-3", "kind": "orphan",
         "text": "Drop slide 3 or merge into slide 4 with a one-line pricing note.",
         "target_slide_ids": ["s3"], "advisory": True}
    ]
}


def test_happy_path_returns_shaped_dict():
    narrative.set_llm(_stub(GOOD_RESPONSE))
    out = narrative.analyze_narrative(SAMPLE_OUTLINE)
    assert out is not None
    assert out["spine"].startswith("The deck argues")
    assert out["arc"] == "claim→evidence→takeaway"
    assert len(out["orphans"]) == 1 and out["orphans"][0]["slide_id"] == "s3"
    assert len(out["gaps"]) == 1
    assert len(out["tensions"]) == 1
    assert len(out["recommendations"]) == 2
    assert out["model"] == "stub"
    assert out["cached"] is False


def test_anti_fabrication_drops_unknown_slide_id():
    bad = dict(GOOD_RESPONSE)
    bad["orphans"] = [{"slide_id": "s99-fake", "reason": "made up"}]
    bad["recommendations"] = [
        {"id": "r1", "kind": "spine", "text": "fine", "target_slide_ids": ["s1"]},
        {"id": "r2", "kind": "orphan", "text": "drop", "target_slide_ids": ["s99-fake"]},
    ]
    narrative.set_llm(_stub(bad))
    out = narrative.analyze_narrative(SAMPLE_OUTLINE)
    assert out is not None
    assert out["orphans"] == [], "fabricated orphan slide_id slipped through validation"
    # the rec with the fake slide_id should have its target stripped, but the
    # rec itself can survive (it's still actionable text). Verify the target
    # list is filtered.
    bad_rec = next((r for r in out["recommendations"] if r["id"] == "r2"), None)
    if bad_rec:
        assert bad_rec["target_slide_ids"] == [], \
            f"fabricated slide_id leaked through: {bad_rec['target_slide_ids']}"


def test_cache_hit_avoids_second_llm_call():
    calls = {"n": 0}
    def counting(_p):
        calls["n"] += 1
        return json.dumps(GOOD_RESPONSE)
    narrative.set_llm(counting)
    a = narrative.analyze_narrative(SAMPLE_OUTLINE)
    b = narrative.analyze_narrative(SAMPLE_OUTLINE)
    assert calls["n"] == 1, f"expected 1 LLM call, got {calls['n']}"
    assert b.get("cached") is True


def test_cache_miss_on_outline_edit():
    calls = {"n": 0}
    def counting(_p):
        calls["n"] += 1
        return json.dumps(GOOD_RESPONSE)
    narrative.set_llm(counting)
    narrative.analyze_narrative(SAMPLE_OUTLINE)
    edited = [{**SAMPLE_OUTLINE[0], "title": "Different title"}] + SAMPLE_OUTLINE[1:]
    narrative.analyze_narrative(edited)
    assert calls["n"] == 2, f"edited outline should trigger a fresh call, got {calls['n']}"


def test_json_in_fences_extracts_cleanly():
    fenced = "Sure, here you go:\n```json\n" + json.dumps(GOOD_RESPONSE) + "\n```\nLet me know if you want changes."
    narrative.set_llm(_stub(fenced))
    out = narrative.analyze_narrative(SAMPLE_OUTLINE)
    assert out is not None
    assert "Q3" in out["spine"]


def test_garbage_response_returns_none():
    narrative.set_llm(_stub("not JSON at all, sorry"))
    out = narrative.analyze_narrative(SAMPLE_OUTLINE)
    assert out is None


def test_llm_raises_returns_none_does_not_crash():
    def boom(_p):
        raise RuntimeError("simulated 500")
    narrative.set_llm(boom)
    out = narrative.analyze_narrative(SAMPLE_OUTLINE)
    assert out is None


def test_to_storyboard_recs_adapter():
    """The adapter that turns narrative output into storyboard-tab rec shape."""
    narrative.set_llm(_stub(GOOD_RESPONSE))
    narr = narrative.analyze_narrative(SAMPLE_OUTLINE)
    recs = narrative.to_storyboard_recs(narr)
    kinds = [r["kind"] for r in recs]
    assert "spine"   in kinds
    assert "orphan"  in kinds
    assert "gap"     in kinds
    assert "tension" in kinds
    for r in recs:
        assert r.get("advisory") is True
        # every rec must reference real slide ids (or none at all for spine)
        for sid in (r.get("slideIds") or []):
            assert sid in {s["id"] for s in SAMPLE_OUTLINE}


def test_to_threadmap_view_adapter_builds_edges_from_groupings():
    """Edges come from the LLM's groupings of slides, not from similarity."""
    narrative.set_llm(_stub(GOOD_RESPONSE))
    narr = narrative.analyze_narrative(SAMPLE_OUTLINE)
    view = narrative.to_threadmap_view(narr, SAMPLE_OUTLINE)
    # tension binds s1 + s4, recommendation 'spine-1' binds s1+s2+s4 → edges between
    # all those pairs should exist
    edge_pairs = {tuple(sorted([e["from"], e["to"]])) for e in view["graph"]["edges"]}
    assert ("s1", "s2") in edge_pairs
    assert ("s1", "s4") in edge_pairs
    assert ("s2", "s4") in edge_pairs
    # orphan reasons surfaced for the UI
    assert view["graph"]["orphan_reasons"]["s3"].startswith("Pricing")
    # tensions surface untouched
    assert len(view["graph"]["tensions"]) == 1
    # spine carries the full sentence, not a token
    assert view["graph"]["spine"]["word"].startswith("The deck argues")


def test_empty_outline_returns_none():
    narrative.set_llm(_stub(GOOD_RESPONSE))
    assert narrative.analyze_narrative([]) is None



def _backend_in_subprocess(env):
    """narrative reads its env at import, so check a config in a fresh process."""
    import json, subprocess
    code = ("import json; from deckengine import narrative as n; "
            "print(json.dumps([n._BACKEND, n.backend_info()]))")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    clean = {k: v for k, v in os.environ.items()
             if not k.startswith(("OPENAI_", "LOCAL_LLM_", "DECKENGINE_NARRATIVE_"))}
    out = subprocess.check_output([sys.executable, "-c", code], cwd=root,
                                  env={**clean, **env}, text=True)
    return json.loads(out.strip().splitlines()[-1])


def test_openai_is_an_alias_for_the_compatible_backend():
    backend, info = _backend_in_subprocess({
        "DECKENGINE_NARRATIVE_BACKEND": "OpenAI",
        "OPENAI_BASE_URL": "http://127.0.0.1:1234/v1/", "OPENAI_MODEL": "llama-3.1-8b"})
    assert backend == "gemma"
    assert info == {"backend": "openai-compatible", "model": "llama-3.1-8b",
                    "base": "http://127.0.0.1:1234/v1"}


def test_local_llm_names_still_work_and_win():
    backend, info = _backend_in_subprocess({
        "DECKENGINE_NARRATIVE_BACKEND": "gemma",
        "LOCAL_LLM_BASE": "https://hf.example/v1", "LOCAL_LLM_MODEL": "gemma",
        "OPENAI_BASE_URL": "https://ignored/v1"})
    assert backend == "gemma" and info["base"] == "https://hf.example/v1"

if __name__ == "__main__":
    # No pytest. Run each test_ with manual setup/teardown so cache state is clean.
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for name, fn in fns:
        try:
            setup_function()
            fn()
            teardown_function()
            print(f"PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {name}: {e}")
        except Exception as e:
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
