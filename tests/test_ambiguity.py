"""
Ambiguity scorer tests — verify the principled tie-detection.

The scorer's contract:
- Stat-heavy text scores stat_callout high, others low. No question.
- Balanced stats + bullets ties stat_callout vs two_column_stats. Question.
- Text-only with no stats scores bullets_plain/icon_rows. May ask 'visual?'.
- Empty/title-only scores title_slide.
- choose_archetype is deterministic given (slide, answers).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine.ir import Slide, ContentBlock, BlockKind, LayoutIntent
from deckengine.ambiguity import (
    score_archetypes, detect, choose_archetype, EPSILON,
)


def test_stat_heavy_picks_stat_callout_no_question():
    s = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="The numbers"),
        ContentBlock(BlockKind.STAT, value="99.97%", label="uptime"),
        ContentBlock(BlockKind.STAT, value="14m", label="downtime"),
        ContentBlock(BlockKind.STAT, value="3", label="incidents"),
    ], intent=LayoutIntent.AUTO)
    assert choose_archetype(s, {}) == "stat_callout"
    qs = detect(s)
    # no tie because stats dominate without bullets
    assert not any(q.id == "focus" for q in qs), "no focus question expected"


def test_balanced_mix_triggers_focus_question():
    """User-agency rule: when both stats and bullets present, focus question
    is offered regardless of the scorer's lean."""
    s = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="Q3"),
        ContentBlock(BlockKind.STAT, value="+14%", label="revenue"),
        ContentBlock(BlockKind.STAT, value="118%", label="retention"),
        ContentBlock(BlockKind.BULLETS, items=[
            "Enterprise close rate doubled",
            "Multi-year contracts 60% of new ARR",
        ]),
    ], intent=LayoutIntent.AUTO)
    qs = detect(s)
    assert any(q.id == "focus" for q in qs), "expected focus question for stats+bullets"


def test_principled_tie_within_epsilon():
    """3 stats + 1 bullet creates a scorer-detected tie within EPSILON."""
    s = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="Q3"),
        ContentBlock(BlockKind.STAT, value="+14%", label="revenue"),
        ContentBlock(BlockKind.STAT, value="118%", label="retention"),
        ContentBlock(BlockKind.STAT, value="1.8%", label="churn"),
        ContentBlock(BlockKind.BULLETS, items=["Enterprise close rate doubled"]),
    ])
    scored = score_archetypes(s)
    top, runner = scored[0], scored[1]
    assert top[1] - runner[1] <= EPSILON, f"expected scorer tie, got {scored[:3]}"


def test_focus_answer_swings_archetype():
    s = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="Q3"),
        ContentBlock(BlockKind.STAT, value="+14%", label="revenue"),
        ContentBlock(BlockKind.STAT, value="118%", label="retention"),
        ContentBlock(BlockKind.BULLETS, items=["Enterprise close rate doubled", "Multi-year contracts 60%"]),
    ])
    assert choose_archetype(s, {"focus": "Story leads"}) == "two_column_stats"
    assert choose_archetype(s, {"focus": "Stats lead"}) == "stat_callout"


def test_text_only_picks_bullets_or_icons():
    s = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="Decisions"),
        ContentBlock(BlockKind.BULLETS, items=["Pause SMB paid", "Hire two enterprise AEs", "Ship the onboarding flow"]),
    ])
    arch = choose_archetype(s, {})
    assert arch in ("bullets_plain", "icon_rows"), f"got {arch}"


def test_visual_question_offered_on_text_only_slide():
    s = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="Decisions"),
        ContentBlock(BlockKind.BULLETS, items=["Pause SMB", "Hire AEs", "Ship onboarding"]),
    ])
    qs = detect(s)
    # bullets_plain wins, but the 'visual' affordance should still be offered
    # (either via visual_pick tie or the visual fallback)
    assert any(q.id in ("visual", "visual_pick") for q in qs), \
        "text-only slide should offer a visual-anchor option"


def test_density_question_when_many_bullets():
    s = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="Many points"),
        ContentBlock(BlockKind.BULLETS, items=[f"point {i}" for i in range(6)]),
    ])
    qs = detect(s)
    assert any(q.id == "density" for q in qs), "expected density question"


def test_empty_slide_picks_title_slide():
    s = Slide(blocks=[ContentBlock(BlockKind.TITLE, text="A bare cover")])
    assert choose_archetype(s, {}) == "title_slide"


def test_scorer_deterministic():
    """Same IR ⇒ identical scores. R2.4.2 in spirit, applied to the scorer."""
    s = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="X"),
        ContentBlock(BlockKind.STAT, value="14%", label="growth"),
        ContentBlock(BlockKind.BULLETS, items=["a", "b"]),
    ])
    a = score_archetypes(s)
    b = score_archetypes(s)
    assert a == b, "scorer must be deterministic"


def test_answered_question_not_re_asked():
    s = Slide(blocks=[
        ContentBlock(BlockKind.TITLE, text="Q3"),
        ContentBlock(BlockKind.STAT, value="14%", label="revenue"),
        ContentBlock(BlockKind.STAT, value="118%", label="retention"),
        ContentBlock(BlockKind.BULLETS, items=["a", "b"]),
    ])
    qs_first = detect(s)
    assert any(q.id == "focus" for q in qs_first)
    qs_after = detect(s, answers={"focus": "Stats lead"})
    assert not any(q.id == "focus" for q in qs_after), "should not re-ask answered question"


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
