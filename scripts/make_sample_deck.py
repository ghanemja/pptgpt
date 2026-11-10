"""Render frontend/samples/sample.pptx.

The sample deck is a reference, not decoration: it is what /workspace's
ingest, condense and "follow an existing format" paths are demonstrated
against. It is produced BY the engine — IR in, layout.resolve for geometry,
render_deck for the .pptx — so the shipped file always reflects the current
layout rules rather than drifting into a hand-built artifact.

    python3 scripts/make_sample_deck.py

Regenerate it after any layout change; it is committed so the UI has a
sample to load with no backend.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine.ir import BlockKind, ContentBlock, LayoutIntent, PALETTES, Slide
from deckengine.layout import resolve
from deckengine.render import render_deck

OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "samples", "sample.pptx",
)

# A six-slide board review that follows the default profile's arc:
# Situation -> Complication -> Question -> Answer -> Ask.
SLIDES: list[Slide] = [
    Slide(
        intent=LayoutIntent.TITLE_SLIDE,
        notes="Opening. The ask is named on the title slide so nobody waits for it.",
        blocks=[
            ContentBlock(BlockKind.TITLE, text="Double down on enterprise"),
            ContentBlock(BlockKind.SUBTITLE, text="Q3 board review · decision requested"),
        ],
    ),
    Slide(
        intent=LayoutIntent.STAT_CALLOUT,
        notes="Situation. One hero number, two supports. No commentary yet.",
        blocks=[
            ContentBlock(BlockKind.TITLE, text="Q3 beat plan on every line"),
            ContentBlock(BlockKind.STAT, value="+14%", label="revenue vs plan", emphasis=2),
            ContentBlock(BlockKind.STAT, value="118%", label="net retention"),
            ContentBlock(BlockKind.STAT, value="1.8%", label="logo churn"),
        ],
    ),
    Slide(
        intent=LayoutIntent.TWO_COLUMN_STATS,
        notes="Complication. The beat is concentrated, which is the real story.",
        blocks=[
            ContentBlock(BlockKind.TITLE, text="The beat came from one segment"),
            ContentBlock(BlockKind.STAT, value="71%", label="of new ARR from enterprise", emphasis=2),
            ContentBlock(BlockKind.STAT, value="9%", label="of accounts"),
            ContentBlock(BlockKind.BULLETS, items=[
                "Mid-market grew 3% — flat against plan",
                "Enterprise cycle is 2.4x the contract value",
                "Two of three expansions came from the same motion",
            ]),
        ],
    ),
    Slide(
        intent=LayoutIntent.BULLETS_PLAIN,
        notes="Question. State the objection before the room does.",
        blocks=[
            ContentBlock(BlockKind.TITLE, text="Is this structural or seasonal?"),
            ContentBlock(BlockKind.BULLETS, items=[
                "Seasonal read: Q3 renewals cluster, so retention flatters",
                "Structural read: expansion came from new seats, not renewals",
                "Cohort evidence: the Q1 enterprise cohort is still net-expanding",
                "Test: if Q4 expansion holds above 110%, it is structural",
            ]),
        ],
    ),
    Slide(
        intent=LayoutIntent.ICON_ROWS,
        notes="Answer. Three moves, each tied to a number above.",
        blocks=[
            ContentBlock(BlockKind.TITLE, text="Three moves for Q1"),
            ContentBlock(BlockKind.ICON_ROW, items=[
                "Hire two enterprise AEs against the proven motion",
                "Fund the security review that gates six open deals",
                "Hold mid-market spend flat until the cohort read lands",
            ]),
        ],
    ),
    Slide(
        intent=LayoutIntent.STAT_CALLOUT,
        notes="Ask. One number, one decision, no new information.",
        blocks=[
            ContentBlock(BlockKind.TITLE, text="The ask"),
            ContentBlock(BlockKind.STAT, value="$1.4M", label="Q1 investment", emphasis=2),
            ContentBlock(BlockKind.STAT, value="4.2x", label="modelled return by FY27"),
            ContentBlock(BlockKind.CAPTION, text="Approve the enterprise hire plan today."),
        ],
    ),
]


def build(path: str = OUT) -> str:
    theme = PALETTES["bold"]
    resolved = [resolve(s, theme) for s in SLIDES]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    render_deck(resolved, path)
    return path


if __name__ == "__main__":
    out = build()
    print(f"[sample] {len(SLIDES)} slides -> {out} ({os.path.getsize(out) // 1024}KB)")
