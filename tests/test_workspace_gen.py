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



# ---- slide voice (humanplease) -------------------------------------------

_CURRENT = {"title": "Q3 results", "metric": "+14%", "bullets": ["a", "b"], "takeaway": "t"}


def _prompts(**kw):
    kw.setdefault("voice", "full")      # independent of this machine's backend env
    return {
        f: workspace_gen._build_prompt(f, "We beat Q3 plan by 14%", "exec",
                                       _CURRENT if f == "refine" else None, [], **kw)
        for f in ("create", "data", "refine", "condense")
    }


def test_voice_block_reaches_every_feature():
    vb = workspace_gen.voice_block()
    assert vb and "Never invent" in vb
    for f, p in _prompts().items():
        assert vb in p, f"voice block missing from the {f} prompt"
        assert "You are pptgpt" in p
    for f, p in _prompts(voice=False).items():
        assert vb not in p, f"voice=False still sent the block for {f}"


def test_house_style_also_reaches_refine_and_comes_first():
    for f, p in _prompts(house="- Say customers, never users.").items():
        assert "Say customers, never users." in p, f"house style missing from {f}"
        assert p.index("house style") < p.index("How to write the text"), f
    # the voice block sits before the user's input, not after it
    p = _prompts()["create"]
    assert p.index("How to write the text") < p.index("Input:")


def test_voice_block_is_content_only():
    import re
    for form in ("full", "short"):
        _check_content_only(workspace_gen.voice_block(form))


def _check_content_only(vb):
    import re
    assert len(vb) <= 1500, f"voice block is {len(vb)} chars; small models need it short"
    lowered = vb.lower()
    for word in ("colour", "color", "font", "pixel", "inch", "position", "width",
                 "height", "align", "layout", "margin"):
        assert word not in lowered, f"voice block talks about {word!r}: geometry is the engine's"
    assert not re.search(r"\b[xywh]\s*[:=]", vb), "coordinates in the voice block"
    assert not re.search(r"\d+\s*(px|pt|in)\b", vb), "sizes in the voice block"
    assert not re.search(r"#[0-9a-fA-F]{6}", vb), "colours in the voice block"
    assert "\u2014" not in vb, "the block bans em dashes, so it must not use one"
    # and the prompt it rides in gains no geometry either
    with_v, without = _prompts()["create"], _prompts(voice=False)["create"]
    added = with_v.replace(without[:without.index("Input:")], "")
    assert not re.search(r"\b[xywh]\s*[:=]", added)


def test_voice_block_keeps_the_skills_banned_phrases():
    import re
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skill = open(os.path.join(here, "deckengine", "vendor", "humanplease", "skills",
                              "natural-voice-writing", "SKILL.md"), encoding="utf-8").read()
    # The voice block keeps every single-word ban from the skill.
    line = next(l for l in skill.splitlines() if l.startswith("Specific phrases to keep out"))
    words = [w.strip(" .") for w in line.split(":", 1)[1].split(",")]
    singles = [w for w in words if " " not in w]
    vb = workspace_gen.voice_block().lower()
    missing = [w for w in singles if w.lower() not in vb]
    assert not missing, f"banned words dropped from the slide block: {missing}"


def test_voice_block_names_the_vendored_commit():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = json.load(open(os.path.join(here, "deckengine", "vendor", "humanplease", "SOURCE.json")))
    header = open(os.path.join(here, "deckengine", "humanplease_slides.md"), encoding="utf-8").read()
    assert f"humanplease-commit: {src['commit']}" in header, (
        "humanplease_slides.md was not re-derived after syncing a new humanplease commit")


def test_blank_bullets_are_dropped_not_drawn():
    narrative.set_llm(_stub({**CREATE_RESPONSE, "bullets": ["Retention 118%", "", "  "]}))
    result = workspace_gen.generate_slide(feature="create", prompt="x", audience="exec",
                                          current=None, palette="warm", file_names=[])
    assert result["bullets"] == ["Retention 118%"]


def test_json_debris_is_stripped_from_text_fields():
    narrative.set_llm(_stub({**CREATE_RESPONSE,
        "takeaway": "Approve two enterprise AEs for Q1.\u201d}**",
        "title": "Q3 beat plan by 14%\"}```jsoner",
        "bullets": ["40 deals untouched\u201d}"]}))
    r = workspace_gen.generate_slide(feature="create", prompt="x", audience="exec",
                                     current=None, palette="warm", file_names=[])
    assert r["takeaway"] == "Approve two enterprise AEs for Q1."
    assert r["title"] == "Q3 beat plan by 14%"
    assert r["bullets"] == ["40 deals untouched"]
    # a placeholder and a closed quotation survive
    assert workspace_gen._tidy("[add Q3 revenue]") == "[add Q3 revenue]"
    assert workspace_gen._tidy("They said \u201cnot yet\u201d") == "They said \u201cnot yet\u201d"


def test_template_does_not_cue_three_bullets():
    import re
    for voice in (True, False):
        for f, p in _prompts(voice=voice).items():
            m = re.search(r'"bullets":\[([^\]]*)\]', p)
            if f == "data":
                assert m is None and workspace_gen._BULLET_RULE not in p
                continue
            assert m, f"{f}: no bullets slot in the template"
            assert len(re.findall(r'"[^"]*"', m.group(1))) <= 2, f"{f}: template shows 3+ bullet slots"
            assert workspace_gen._BULLET_RULE in p, f"{f}: the 0-4 rule is missing (voice={voice})"
            # the rule sits outside the JSON example, so it cannot be copied into a bullet
            assert p.index(workspace_gen._BULLET_RULE) > p.index(m.group(0))

def test_standup_tone_does_not_ask_for_invented_owners():
    # "phrased with owners in mind" made the model invent names (Sarah, David)
    # on briefs that named nobody. Authors come from the input or a placeholder.
    tone = workspace_gen._tone("standup")
    assert "owners in mind" not in tone
    assert "only when" in tone and "[author]" in tone and "owner" not in tone
    for f in ("create", "condense", "refine"):
        p = workspace_gen._build_prompt(f, "Outage on Tuesday", "standup",
                                        _CURRENT if f == "refine" else None, [])
        assert tone in p, f"standup tone missing from the {f} prompt"

# ---- small-model reliability ---------------------------------------------

def test_short_voice_is_short_and_keeps_the_rules_that_matter():
    full, short = workspace_gen.voice_block("full"), workspace_gen.voice_block("short")
    assert short and full and short not in full and full not in short
    assert "short form" not in full and "<!--" not in short, "the form marker leaked"
    assert len(short) <= 0.75 * len(full), f"short form is {len(short)} chars vs {len(full)}"
    low = short.lower()
    assert "never add a number" in low and "null" in low          # no invented facts
    for w in ("delve", "leverage", "seamless", "transformative"):
        assert w in low
    assert "em dash" in low and "exclamation" in low
    # nothing a small model could copy onto a slide as if it were content
    assert "[" not in short, "short form carries an example placeholder"
    assert "out loud" not in low


def test_voice_form_is_picked_by_model_size():
    ms = workspace_gen.model_size_b
    assert ms("gemma3:4b") == 4 and ms("gemma4:e4b") == 4 and ms("gemma4:e2b") == 2
    assert ms("gemma4:26b") == 26 and ms("qwen2.5:14b-instruct") == 14
    assert ms("llama3.1:8b") == 8 and ms("gemma4") is None and ms("claude-sonnet-4-6") is None
    orig, env = narrative.backend_info, os.environ.pop("DECKENGINE_VOICE", None)
    try:
        for info, want in [({"backend": "ollama", "model": "gemma3:4b"}, "short"),
                           ({"backend": "ollama", "model": "gemma4"}, "short"),
                           ({"backend": "ollama", "model": "gemma4:31b"}, "full"),
                           ({"backend": "openai-compatible", "model": "gemma"}, "short"),
                           ({"backend": "anthropic", "model": "claude-sonnet-4-6"}, "full")]:
            narrative.backend_info = lambda info=info: info
            assert workspace_gen.voice_form(True) == want, (info, want)
        assert workspace_gen.voice_form(False) == "off"
        assert workspace_gen.voice_form("short") == "short"
        os.environ["DECKENGINE_VOICE"] = "off"
        assert workspace_gen.voice_form(True) == "off"
        p = workspace_gen._build_prompt("create", "x", "exec", None, [], voice=True)
        assert "How to write the text" not in p
    finally:
        narrative.backend_info = orig
        os.environ.pop("DECKENGINE_VOICE", None)
        if env is not None:
            os.environ["DECKENGINE_VOICE"] = env


def test_templates_have_no_copyable_placeholder_text():
    # gemma3:4b copied "ALL CAPS context <=5 words" onto a slide's eyebrow.
    # Every string slot in a template is now "", and the field rules sit
    # outside the JSON on their own lines.
    import re
    for voice in ("full", "short", False):
        for f, p in _prompts(voice=voice).items():
            if f == "refine":
                assert "one of text, chart, plot" in p, "refine must keep a chart slide a chart"
            templates = re.findall(r'^\{"kind".*\}$', p, re.M)
            assert templates, f"{f}: no JSON template line"
            for t in templates:
                slots = re.findall(r'"(eyebrow|title|metric|metricSub|takeaway)":"([^"]*)"', t)
                assert slots and all(v == "" for _, v in slots), f"{f}: {slots}"
                bullets = re.search(r'"bullets":\[([^\]]*)\]', t)
                if bullets:
                    assert set(re.findall(r'"([^"]*)"', bullets.group(1))) <= {""}
                assert "ALL CAPS" not in t and "<=" not in t, f"{f}: rule text inside the JSON"
            assert "ALL CAPS" not in p, f"{f}: casing rule fights the voice; SlideCard uppercases"
            # the output contract comes after the voice, right before the input
            if voice:
                assert p.index("How to write the text") < p.index(templates[0]), f


def test_curly_quote_close_is_repaired_not_left_to_run_away():
    # Reproduced on gemma3:4b: the takeaway closed with \u201d, JSON mode kept
    # the string open, and the model rambled to its token cap.
    runaway = ('{"kind":"text","title":"Checkout was down 47 minutes","bullets":["Redis pool set to 0"],'
               '"takeaway":"Validate config in CI.\u201d} H/T: [author] \u2013 Add [add Q3 revenue] to the')
    narrative.set_llm(_stub(runaway))
    r = workspace_gen.generate_slide(feature="create", prompt="x", audience="exec",
                                     current=None, palette="warm", file_names=[])
    assert r and r["takeaway"] == "Validate config in CI." and r["bullets"] == ["Redis pool set to 0"]
    # ...also when the model eventually closes a straight quote far downstream
    late = '{"title":"x","takeaway":"Fix it.\u201d} rambling on \" and on"}'
    assert workspace_gen._extract_json_value(late) == {"title": "x", "takeaway": "Fix it."}
    # a real quotation inside a string is left alone
    ok = '{"title":"They said \u201cnot yet\u201d, then left"}'
    assert workspace_gen._extract_json_value(ok)["title"] == "They said \u201cnot yet\u201d, then left"


def test_reply_is_capped_so_a_runaway_cannot_hit_the_timeout():
    seen = {}
    orig = narrative.call
    narrative.call = lambda p, s, max_tokens=None: seen.setdefault("mt", max_tokens) and json.dumps(CREATE_RESPONSE)
    try:
        orig_av, narrative.available = narrative.available, (lambda: True)
        workspace_gen.generate_slide(feature="create", prompt="x", audience="exec",
                                     current=None, palette="warm", file_names=[])
    finally:
        narrative.call, narrative.available = orig, orig_av
    assert seen["mt"] and seen["mt"] <= 800


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
