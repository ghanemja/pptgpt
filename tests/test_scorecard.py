"""
Scorecard tests.

The contract:
- Scores are the coach's notes, counted: same deck, panel, audience and
  purpose give the same scores, so a score that moves moved because the
  deck did.
- Fixing what a reviewer raised raises that reviewer's score in that aspect.
- A reviewer is only scored on aspects they read for.
- Density is judged against the room: the same slide is dense for a
  conference and fine for a standup.
- A deck that never asks for its purpose loses on clear messaging.
- A kit's own rules are scored as House rules.
- No geometry anywhere in the output (R0.1).
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine import coach as C
from deckengine import scorecard as S

C.SAVED_DIR = tempfile.mkdtemp()

WEAK = {"id": "a", "title": "Q3 results",
        "bullets": ["Revenue grew strongly", "Churn improved", "We might expand",
                    "Pipeline looks robust", "Enterprise is best in class"],
        "takeaway": ""}
FIXED = {"id": "a", "title": "Enterprise drove the Q3 beat",
         "metric": "+14%", "metricSub": "vs plan, per the FY26 ledger as of 30 Jun",
         "bullets": ["Net retention 118% vs 104% last year", "Churn 1.8%, down from 2.6%"],
         "takeaway": "Approve two enterprise AEs; Sales owns the ramp."}
TECHY = {"id": "t", "title": "Latency fell 40% after the CDN move",
         "bullets": ["p99 down to 210ms, per Datadog as of 1 Oct",
                     "The API tier now runs on 12 nodes"],
         "takeaway": "Approve the CDN contract; Infra owns rollout."}


def _panel(slides, slugs=("board-chair", "skeptical-analyst"), **kw):
    return S.score_panel(slides, [C.load_persona(s) for s in slugs], **kw)


def _walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def test_scores_are_deterministic():
    a = json.dumps(_panel([WEAK, FIXED], purpose="Approve two enterprise AEs"), sort_keys=True)
    b = json.dumps(_panel([WEAK, FIXED], purpose="Approve two enterprise AEs"), sort_keys=True)
    assert a == b


def test_every_reviewer_gets_a_card_and_scores_are_bounded():
    out = _panel([WEAK, FIXED])
    assert [c["coach"]["slug"] for c in out["cards"]] == ["board-chair", "skeptical-analyst"]
    for card in out["cards"]:
        assert 0 <= card["overall"] <= 100
        for d in card["dims"].values():
            assert 0 <= d["score"] <= 100


def test_fixing_the_slide_raises_the_scores():
    before = _panel([WEAK])["cards"][0]
    after = _panel([FIXED])["cards"][0]
    assert after["overall"] > before["overall"]
    assert after["dims"]["messaging"]["score"] > before["dims"]["messaging"]["score"]
    assert after["dims"]["language"]["score"] > before["dims"]["language"]["score"]


def test_a_reviewer_is_scored_only_on_what_they_read_for():
    p = C.Persona(slug="t", name="T", lenses={"title": 3, "ask": 2})
    card = S.score_panel([WEAK], [p])["cards"][0]
    assert set(card["dims"]) == {"messaging"}


def test_density_is_judged_against_the_room():
    conf = _panel([TECHY], audience="conf")["cards"][0]["dims"]["density"]
    standup = _panel([TECHY], audience="standup")["cards"][0]["dims"]["density"]
    assert conf["score"] < standup["score"]
    assert any("Conference room" in i["label"] for i in conf["issues"])
    n = S.technical_items(TECHY)
    assert S.AUDIENCES["conf"].tech[1] < n <= S.AUDIENCES["standup"].tech[1], n


def test_the_eyebrow_is_not_technical_detail():
    assert S.technical_items({"eyebrow": "EXEC REVIEW", "title": "We won"}) == 0


def test_a_deck_that_never_asks_for_its_purpose_loses_on_messaging():
    asked = _panel([FIXED], purpose="Approve two enterprise AEs")
    missed = _panel([FIXED], purpose="Sunset the legacy billing platform")
    assert asked["purposeMet"] is True and missed["purposeMet"] is False
    a = asked["cards"][0]["dims"]["messaging"]
    m = missed["cards"][0]["dims"]["messaging"]
    assert m["score"] == a["score"] - 20
    assert any("legacy billing" in i["label"] for i in m["issues"])
    assert _panel([FIXED])["purposeMet"] is None        # no purpose, nothing to judge


def test_kit_rules_are_scored_as_house_rules():
    crits = C.parse_criteria({"criteria": [
        {"id": "codenames", "kind": "banned", "label": "No codenames",
         "words": ["Project Falcon"], "severity": "blocker"}]})
    p = C.Persona(slug="t", name="T", lenses={"title": 2, "kit:codenames": 3})
    out = S.score_panel([dict(FIXED, title="Project Falcon drove the beat")], [p], criteria=crits)
    assert "house" in [d["id"] for d in out["dimensions"]]
    house = out["cards"][0]["dims"]["house"]
    assert house["score"] < 100 and house["issues"][0]["label"] == "No codenames"
    # without the kit, the rule has nothing to run and no aspect to score
    assert "house" not in S.score_panel([FIXED], [p])["cards"][0]["dims"]


def test_the_audience_limit_tightens_density():
    four = dict(FIXED, bullets=["a 1", "b 2", "c 3", "d 4"])
    p = C.Persona(slug="t", name="T", lenses={"density": 3})
    exec_ = S.score_panel([four], [p], audience="exec")["cards"][0]["dims"]["density"]
    stand = S.score_panel([four], [p], audience="standup")["cards"][0]["dims"]["density"]
    assert any("points on one slide" not in i["label"] for i in exec_["issues"])
    assert exec_["score"] < stand["score"]


def test_no_geometry_in_a_scorecard():
    keys = set(_walk(_panel([WEAK, FIXED, TECHY], purpose="Approve the plan")))
    assert not (keys & {"x", "y", "w", "h", "left", "top", "width", "height"}), keys


def test_an_unknown_audience_falls_back_to_exec():
    assert _panel([FIXED], audience="martians")["audience"]["key"] == "exec"


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
