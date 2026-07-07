"""
workspace_gen tests with a stub LLM — mirrors tests/test_narrative.py's style.

Verifies orchestration, not model quality:
- happy path for each of the 4 features
- condense returns a list
- malformed JSON -> None
- LLM exception -> None (never raises to the caller)
- unavailable backend -> None without calling the LLM
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine import narrative, workspace_gen


def _stub(payload):
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


CREATE_RESPONSE = {
    "kind": "text", "eyebrow": "Q3 RESULTS", "title": "Revenue beat plan by 14%",
    "metric": "+14%", "metricSub": "vs plan", "bullets": ["Retention 118%", "Churn 1.8%"],
    "takeaway": "The trend keeps compounding.",
}


def test_create_happy_path():
    narrative.set_llm(_stub(CREATE_RESPONSE))
    result = workspace_gen.generate_slide(
        feature="create", prompt="We beat Q3 plan by 14%", audience="exec",
        current=None, palette="warm", file_names=[],
    )
    assert result["title"] == "Revenue beat plan by 14%"
    assert result["kind"] == "text"
    assert result["palette"] == "warm"


def test_data_happy_path():
    resp = {"kind": "chart", "eyebrow": "RESULTS", "title": "Quarterly revenue",
            "takeaway": "Up and to the right.",
            "chart": {"title": "in $M", "data": [{"label": "Q1", "value": 32, "hi": False}]}}
    narrative.set_llm(_stub(resp))
    result = workspace_gen.generate_slide(
        feature="data", prompt="Q1 32, Q2 38", audience="exec",
        current=None, palette="warm", file_names=[],
    )
    assert result["kind"] == "chart"
    assert result["chart"]["data"][0]["label"] == "Q1"


def test_refine_happy_path():
    resp = {"kind": "text", "eyebrow": "UPDATE", "title": "Sharper title",
            "metric": None, "metricSub": None, "bullets": ["a", "b"], "takeaway": "Landed."}
    narrative.set_llm(_stub(resp))
    current = {"id": "sl_abc", "title": "Old title", "metric": None, "bullets": [], "takeaway": ""}
    result = workspace_gen.generate_slide(
        feature="refine", prompt="sharpen the title", audience="exec",
        current=current, palette="warm", file_names=[],
    )
    assert result["title"] == "Sharper title"


def test_condense_returns_list():
    resp = [
        {"kind": "text", "eyebrow": "01", "title": "Spine one", "bullets": ["a"], "takeaway": "t1"},
        {"kind": "text", "eyebrow": "02", "title": "Spine two", "bullets": ["b"], "takeaway": "t2"},
    ]
    narrative.set_llm(_stub(resp))
    result = workspace_gen.generate_slide(
        feature="condense", prompt="slide 1 --- slide 2", audience="exec",
        current=None, palette="warm", file_names=[],
    )
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["title"] == "Spine one"


def test_condense_non_list_response_returns_none():
    narrative.set_llm(_stub(CREATE_RESPONSE))   # an object, not an array
    result = workspace_gen.generate_slide(
        feature="condense", prompt="deck text", audience="exec",
        current=None, palette="warm", file_names=[],
    )
    assert result is None


def test_malformed_json_returns_none():
    narrative.set_llm(_stub("not json at all"))
    result = workspace_gen.generate_slide(
        feature="create", prompt="anything", audience="exec",
        current=None, palette="warm", file_names=[],
    )
    assert result is None


def test_llm_exception_returns_none():
    def boom(_prompt):
        raise RuntimeError("network error")
    narrative.set_llm(boom)
    result = workspace_gen.generate_slide(
        feature="create", prompt="anything", audience="exec",
        current=None, palette="warm", file_names=[],
    )
    assert result is None


def test_unavailable_backend_returns_none_without_calling_llm():
    # Force "no model configured" regardless of this machine's real env
    # (e.g. a real ANTHROPIC_API_KEY), rather than relying on ambient state.
    orig_available = narrative.available
    calls = []
    narrative.available = lambda: False
    try:
        result = workspace_gen.generate_slide(
            feature="create", prompt="anything", audience="exec",
            current=None, palette="warm", file_names=[],
        )
    finally:
        narrative.available = orig_available
    assert result is None
    assert calls == []


def test_empty_object_returns_none():
    narrative.set_llm(_stub({"kind": "text"}))   # no title, no bullets
    result = workspace_gen.generate_slide(
        feature="create", prompt="anything", audience="exec",
        current=None, palette="warm", file_names=[],
    )
    assert result is None


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    tests = [f for name, f in inspect.getmembers(mod) if name.startswith("test_")]
    passed = 0
    for t in tests:
        setup_function()
        try:
            t()
            passed += 1
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
        finally:
            teardown_function()
    print(f"{passed}/{len(tests)} passed")
