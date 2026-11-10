"""
Coach tests.

The contract:
- A critique is deterministic: the same slide and persona give the same
  notes, so a note is a property of the slide, not of a sampling seed.
- Personas genuinely differ — a lens one obsesses over is one another barely
  raises — and strictness bends severity only where they care, because if
  everything is a blocker the word means nothing.
- A slide that holds up comes back clear. A critic that always finds fault
  is not giving information.
- Personas are config and are validated; a bad one is refused.
- No note carries geometry (R0.1).
"""
import json
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine import coach as C

WEAK = {
    "title": "Q3 results",
    "bullets": ["Revenue grew strongly", "Churn improved",
                "Enterprise is best in class", "Pipeline looks robust",
                "We might expand"],
    "takeaway": "",
}
STRONG = {
    "title": "Enterprise drove the Q3 beat",
    "metric": "+14%",
    "metricSub": "vs plan, per the FY26 ledger as of 30 Jun",
    "bullets": ["Net retention 118% vs 104% last year", "Churn 1.8%, down from 2.6%"],
    "takeaway": "Approve two enterprise AEs; Sales owns the ramp.",
}


def _expect_error(fn, needle=""):
    try:
        fn()
    except C.CoachError as e:
        assert needle in str(e), f"wrong error: {e}"
        return
    raise AssertionError("expected CoachError")


def test_every_shipped_persona_loads():
    slugs = [f[:-5] for f in os.listdir(C.COACHES_DIR) if f.endswith(".json")]
    assert slugs, "no personas shipped"
    for slug in slugs:
        p = C.load_persona(slug)
        assert p.name and p.lenses


def test_a_critique_is_deterministic():
    p = C.load_persona("board-chair")
    first = C.critique_slide(WEAK, p)
    for _ in range(4):
        assert C.critique_slide(WEAK, p) == first


def test_a_slide_that_holds_up_comes_back_clear():
    for slug in ("board-chair", "skeptical-analyst", "friendly-editor"):
        got = C.critique_slide(STRONG, C.load_persona(slug))
        assert got["verdict"] == "clear", f"{slug} found fault: {got['notes']}"


def test_personas_disagree_about_the_same_slide():
    chair = C.critique_slide(WEAK, C.load_persona("board-chair"))
    analyst = C.critique_slide(WEAK, C.load_persona("skeptical-analyst"))
    editor = C.critique_slide(WEAK, C.load_persona("friendly-editor"))

    def blockers(r):
        return {n["lens"] for n in r["notes"] if n["severity"] == C.BLOCKER}

    assert blockers(chair) == {"ask"}, blockers(chair)
    assert "evidence" in blockers(analyst), blockers(analyst)
    # The soft critic raises the same things without calling them blockers.
    assert not blockers(editor), blockers(editor)
    assert editor["notes"], "a soft critic should still have something to say"


def test_strictness_only_escalates_what_the_persona_cares_about():
    """If everything is a blocker, the word carries no information."""
    chair = C.critique_slide(WEAK, C.load_persona("board-chair"))
    sev = {n["lens"]: n["severity"] for n in chair["notes"]}
    assert sev.get("ask") == C.BLOCKER            # weight 3
    assert sev.get("jargon") == C.NIT             # weight 1 — not escalated


def test_notes_are_ordered_worst_first():
    notes = C.critique_slide(WEAK, C.load_persona("skeptical-analyst"))["notes"]
    ranks = [C.SEVERITY_ORDER[n["severity"]] for n in notes]
    assert ranks == sorted(ranks), ranks


def test_a_period_reference_is_not_a_number():
    """"Q3" is a period; demanding a source for it is noise."""
    slide = {"title": "Q3 plan", "bullets": ["Shipped the new onboarding"],
             "takeaway": "We hold the line."}
    notes = {n["lens"] for n in C.critique_slide(slide, C.load_persona("skeptical-analyst"))["notes"]}
    assert "source" not in notes and "comparison" not in notes, notes


def test_the_handoff_lens_needs_the_next_slide():
    a = {"title": "Churn fell", "bullets": ["x"], "takeaway": "Retention is the story."}
    b = {"title": "Hiring plan for Q1"}
    alone = C.critique_slide(a, C.load_persona("friendly-editor"))
    paired = C.critique_slide(a, C.load_persona("friendly-editor"), context={"next": b})
    assert "handoff" not in {n["lens"] for n in alone["notes"]}
    assert "handoff" in {n["lens"] for n in paired["notes"]}


def test_notes_carry_no_geometry():
    for slug in ("board-chair", "frontline-skeptic"):
        for n in C.critique_slide(WEAK, C.load_persona(slug))["notes"]:
            assert not ({"x", "y", "w", "h"} & set(n)), n
            assert set(n) >= {"lens", "severity", "note"}


def test_every_note_names_the_content_it_is_about():
    """A note is pinned to a field of the slide, so the UI can draw it there.

    The target is a reference into the content — never a position (R0.1).
    """
    fields = {"slide", "eyebrow", "title", "metric", "metricSub", "bullets",
              "chart", "diagram", "takeaway"}
    for slug in ("board-chair", "frontline-skeptic"):
        for slide in (WEAK, STRONG):
            for n in C.critique_slide(slide, C.load_persona(slug))["notes"]:
                t = n["target"]
                assert t["field"] in fields, t
                assert not ({"x", "y", "w", "h", "left", "top"} & set(t)), t
                if "index" in t:
                    assert t["field"] == "bullets"
                    assert 0 <= t["index"] < len(slide["bullets"]), t


def test_a_note_points_at_the_words_that_raised_it():
    p = C.Persona(slug="t", name="T",
                  lenses={"hedge": 3, "jargon": 3, "ask": 3, "title": 3})
    notes = {n["lens"]: n["target"] for n in C.critique_slide(WEAK, p)["notes"]}
    assert notes["hedge"] == {"field": "bullets", "index": 4}      # "We might expand"
    assert notes["jargon"] == {"field": "bullets", "index": 2}     # "best in class"
    assert notes["ask"] == {"field": "takeaway", "missing": True}  # nothing there to point at
    assert notes["title"] == {"field": "title"}


def test_bad_personas_are_refused():
    _expect_error(lambda: C.parse_persona({"lenses": {"ask": 3}}, "x"), "name")
    _expect_error(lambda: C.parse_persona({"name": "X"}, "x"), "lens")
    _expect_error(lambda: C.parse_persona({"name": "X", "lenses": {"vibes": 3}}, "x"), "unknown lens")
    _expect_error(lambda: C.parse_persona(
        {"name": "X", "lenses": {"ask": 1}, "strictness": "brutal"}, "x"), "strictness")
    for slug in ["../etc", "UPPER", ""]:
        _expect_error(lambda s=slug: C.load_persona(s), "bad coach slug")
    _expect_error(lambda: C.load_persona("no-such-coach"), "no coach")


def test_listing_skips_a_broken_file():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "good.json"), "w") as fh:
            json.dump({"name": "Good", "lenses": {"ask": 3}}, fh)
        with open(os.path.join(d, "broken.json"), "w") as fh:
            fh.write("{nope")
        with mock.patch.object(C, "COACHES_DIR", d):
            assert [c["slug"] for c in C.list_personas()] == ["good"]


def test_deck_critique_carries_slide_ids_and_handoffs():
    slides = [dict(STRONG, id="a"), dict(WEAK, id="b")]
    out = C.critique_deck(slides, C.load_persona("board-chair"))
    assert [r["slideId"] for r in out] == ["a", "b"]
    assert out[1]["verdict"] == "blocker"


# ── deck-level review ───────────────────────────────────────────────

# The strong slide goes LAST: in the middle it collects a handoff note,
# because the slide after it does not follow from it. See the test below.
DECK = [dict(WEAK, id="a"), dict(WEAK, id="b"), dict(STRONG, id="c")]


def test_review_counts_the_whole_deck():
    r = C.review_deck(DECK, C.load_persona("board-chair"))
    s = r["summary"]
    assert s["slides"] == 3
    assert s["clear"] == 1, [x["notes"] for x in r["results"]]
    assert s["severities"]["blocker"] >= 1
    assert s["verdict"] == "blocker"
    assert sum(s["severities"].values()) == sum(len(x["notes"]) for x in r["results"])


def test_review_names_the_weakest_slides_worst_first():
    r = C.review_deck(DECK, C.load_persona("board-chair"))
    weakest = r["summary"]["weakest"]
    assert 2 not in weakest, "the clear slide cannot be weakest"
    assert weakest[0] in (0, 1)
    assert len(weakest) <= 3


def test_a_slide_can_be_clear_alone_and_flagged_in_sequence():
    """A review reads the deck as one argument, not as a pile of slides.

    The strong slide passes on its own; placed before a slide that does not
    follow from it, the handoff lens has something to say. That is the
    difference between the Coach and a review.
    """
    persona = C.load_persona("board-chair")
    assert not C.critique_slide(STRONG, persona)["notes"]

    middle = C.review_deck([dict(WEAK, id="a"), dict(STRONG, id="b"), dict(WEAK, id="c")], persona)
    flagged = {n["lens"] for n in middle["results"][1]["notes"]}
    assert flagged == {"handoff"}, flagged


def test_results_carry_slide_identity():
    r = C.review_deck(DECK, C.load_persona("friendly-editor"))
    assert [x["slideId"] for x in r["results"]] == ["a", "b", "c"]
    assert [x["index"] for x in r["results"]] == [0, 1, 2]


def test_an_override_tunes_a_persona_without_editing_it():
    base = C.load_persona("board-chair")
    tuned = C.apply_overrides(base, {"strictness": "soft", "lenses": {"jargon": 0, "density": 3}})
    assert "jargon" not in tuned.lenses
    assert tuned.lenses["density"] == 3
    assert tuned.strictness == "soft"
    # the file on disk is untouched
    assert C.load_persona("board-chair").lenses == base.lenses
    assert "jargon" in C.load_persona("board-chair").lenses


def test_switching_a_lens_off_removes_its_notes():
    persona = C.load_persona("board-chair")
    with_jargon = C.review_deck(DECK, persona)
    without = C.review_deck(DECK, persona, {"lenses": {"jargon": 0}})
    assert "jargon" in with_jargon["summary"]["lenses"]
    assert "jargon" not in without["summary"]["lenses"]


def test_strictness_override_changes_the_verdict_not_the_findings():
    persona = C.load_persona("board-chair")
    hard = C.review_deck(DECK, persona, {"strictness": "hard"})
    soft = C.review_deck(DECK, persona, {"strictness": "soft"})
    count = lambda r: sum(len(x["notes"]) for x in r["results"])
    assert count(hard) == count(soft), "strictness must not invent or hide findings"
    assert hard["summary"]["severities"]["blocker"] >= soft["summary"]["severities"]["blocker"]


def test_a_bad_override_is_refused():
    persona = C.load_persona("board-chair")
    _expect_error(lambda: C.apply_overrides(persona, {"lenses": {"vibes": 2}}), "unknown lens")
    _expect_error(lambda: C.apply_overrides(persona, {"strictness": "brutal"}), "strictness")
    allzero = {k: 0 for k in persona.lenses}
    _expect_error(lambda: C.apply_overrides(persona, {"lenses": allzero}), "every lens off")


def test_an_empty_deck_reviews_clean():
    r = C.review_deck([], C.load_persona("board-chair"))
    assert r["summary"]["verdict"] == "clear"
    assert r["summary"]["weakest"] == []


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
