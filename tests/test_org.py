"""
Org profile tests.

The contract:
- Every shipped profile under orgs/ loads and validates.
- A profile is content + convention only: geometry is rejected (R0.1).
- Malformed questions are rejected rather than half-loaded.
- Bad slugs never reach the filesystem.
- list_orgs() skips a broken file instead of failing the whole install.
"""
import json
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine.org import (
    ORGS_DIR, OrgError, list_orgs, load_org, parse_org, to_dict,
)


def _expect_error(fn, needle=""):
    try:
        fn()
    except OrgError as e:
        assert needle in str(e), f"wrong error: {e}"
        return
    raise AssertionError("expected OrgError")


def test_every_shipped_profile_loads():
    slugs = [f[:-5] for f in os.listdir(ORGS_DIR) if f.endswith(".json")]
    assert slugs, "no org profiles shipped"
    for slug in slugs:
        p = load_org(slug)
        assert p.slug == slug and p.name


def test_default_profile_has_required_questions():
    p = load_org("default")
    ids = [q.id for q in p.scope_questions]
    assert "audience" in ids and "decision" in ids
    assert any(q.required for q in p.scope_questions)


def test_choice_questions_carry_options():
    for slug in [f[:-5] for f in os.listdir(ORGS_DIR) if f.endswith(".json")]:
        for q in load_org(slug).scope_questions:
            if q.kind == "choice":
                assert q.options, f"{slug}.{q.id} is a choice with no options"


def test_geometry_is_rejected_anywhere_in_the_profile():
    """R0.1 — a profile may name a theme, never a box."""
    _expect_error(lambda: parse_org({"name": "X", "style": {"width": 4.5}}, "x"), "geometry")
    _expect_error(
        lambda: parse_org({"name": "X", "scope_questions": [
            {"id": "a", "prompt": "p", "box": [1, 2, 3, 4]}]}, "x"),
        "geometry",
    )


def test_malformed_questions_are_rejected():
    _expect_error(lambda: parse_org({"name": "X", "scope_questions": [{"prompt": "p"}]}, "x"), "id")
    _expect_error(
        lambda: parse_org({"name": "X", "scope_questions": [
            {"id": "a", "prompt": "p", "kind": "slider"}]}, "x"),
        "kind",
    )
    _expect_error(
        lambda: parse_org({"name": "X", "scope_questions": [
            {"id": "a", "prompt": "p", "kind": "choice"}]}, "x"),
        "options",
    )
    _expect_error(
        lambda: parse_org({"name": "X", "scope_questions": [
            {"id": "a", "prompt": "p"}, {"id": "a", "prompt": "q"}]}, "x"),
        "duplicate",
    )
    _expect_error(lambda: parse_org({"tagline": "no name"}, "x"), "name")


def test_bad_slug_never_touches_the_filesystem():
    for slug in ["../secrets", "a/b", "", "UPPER", "x" * 60]:
        _expect_error(lambda s=slug: load_org(s), "slug")
    _expect_error(lambda: load_org("no-such-org"), "no org profile")


def test_list_orgs_skips_a_broken_file():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "good.json"), "w") as fh:
            json.dump({"name": "Good"}, fh)
        with open(os.path.join(d, "broken.json"), "w") as fh:
            fh.write("{not json")
        with open(os.path.join(d, "geometric.json"), "w") as fh:
            json.dump({"name": "Nope", "style": {"x": 1}}, fh)
        with mock.patch("deckengine.org.ORGS_DIR", d):
            got = [o["slug"] for o in list_orgs()]
    assert got == ["good"], got


def test_profile_serializes_for_the_json_boundary():
    d = to_dict(load_org("default"))
    assert d["scope_questions"][0]["id"]
    assert set(d) >= {"slug", "name", "scope_questions", "narrative", "style", "examples"}
    json.dumps(d)  # must be JSON-clean for /api/orgs


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
