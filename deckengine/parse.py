"""
parse_to_ir — text -> Slide IR.

This is the model-layer boundary. In v1 it is a deterministic regex
classifier; in v2 it is replaced by a local LLM call (Ollama / LM Studio /
gemma) that emits IR JSON. §0 still applies: this layer produces CONTENT +
fuzzy INTENT only — no geometry, no colors, no point sizes.

Swap surface (single function):
    parse_to_ir(text: str) -> Slide

Anything that swaps to a local model only needs to keep the signature and
produce a valid `Slide`. Everything downstream (ambiguity, layout, render)
is unchanged.

Heuristics, all deterministic and offline:
- The first non-blank line is the TITLE.
- A line containing a stat token (e.g. "99.97%", "+14%", "$42M", "3x")
  becomes a STAT block with `value`+`label`.
- A short, all-caps-ish line right after the title becomes a SUBTITLE.
- Other lines (and lines after a colon-prefixed label) become BULLETS items.
- An "icons:" or "icon rows:" prefix routes the items into an ICON_ROW block.
- Multi-slide source is split on `---` separators (handled at the deck level
  in `parse_deck_to_ir`).
"""
from __future__ import annotations
import re
from typing import Iterable

from .ir import Slide, ContentBlock, BlockKind, LayoutIntent, Deck, Theme


# ---- stat detection ------------------------------------------------------

# A single token that looks like a number worth highlighting as a stat.
# Order matters: longer/more-specific tokens first so "$42M" beats "$42".
_STAT_TOKEN = re.compile(
    r"""
    (?:
        [+\-]?\$?\d+(?:\.\d+)?[MBK]\b         |  # $42M, 1.2B, 850K
        [+\-]?\d+(?:\.\d+)?%                  |  # 14%, +14%, 1.8%
        [+\-]?\d+(?:\.\d+)?x\b                |  # 3x, 2.5x
        \$\d+(?:[\.,]\d+)+                    |  # $1,200 or $1.2
        [+\-]?\d+(?:\.\d+)+\b                    # 99.97
    )
    """,
    re.VERBOSE,
)


def _extract_stat(line: str) -> tuple[str, str] | None:
    """
    Return (value, label) if the line is best read as a single stat,
    else None. Heuristic: the line contains exactly one stat token AND the
    rest of the line reads like a label (3-12 words).
    """
    matches = list(_STAT_TOKEN.finditer(line))
    if len(matches) != 1:
        return None
    value = matches[0].group(0)
    rest = (line[: matches[0].start()] + " " + line[matches[0].end():]).strip(" :,-—")
    # strip a leading "value of", "value:" style prefix
    rest = re.sub(r"^(?:revenue|growth|retention|churn|uptime|incidents|users|signups|cost|risk|margin|conversions?|sessions?)\b\s*[:\-]?\s*",
                  "", rest, flags=re.I)
    rest = rest.strip(" :,.-—")
    if not rest:
        # if the stat is alone, the label is empty; allow it
        return value, ""
    words = rest.split()
    if len(words) > 14:
        return None
    return value, rest


# ---- single-slide parse --------------------------------------------------

_SECTION_TAG = re.compile(r"^\s*(icons?|icon[_\s-]?rows?|bullets?|stats?)\s*:\s*$", re.I)


def parse_to_ir(text: str) -> Slide:
    """Parse one slide's worth of raw text into a Slide.

    Idempotent + deterministic — no clocks, no randomness. Same input ⇒ same
    output. This is the function a local LLM replaces.
    """
    lines = [l.rstrip() for l in (text or "").splitlines()]
    # drop fully blank top/bottom
    while lines and not lines[0].strip(): lines.pop(0)
    while lines and not lines[-1].strip(): lines.pop()

    if not lines:
        return Slide(
            blocks=[ContentBlock(BlockKind.TITLE, text="Untitled slide")],
            intent=LayoutIntent.AUTO,
        )

    blocks: list[ContentBlock] = []
    notes: str | None = None

    # title: first non-blank line, stripped of leading markdown markers
    title_line = lines[0].strip()
    title_line = re.sub(r"^[#*\-•]+\s*", "", title_line)
    blocks.append(ContentBlock(BlockKind.TITLE, text=title_line))

    body = lines[1:]
    # SUBTITLE detection: ONLY on an explicit "Subtitle:" prefix. The
    # auto-promote heuristic was too eager and ate bullet lines like
    # "Pause SMB". Users who want a subtitle ask for one.
    for i, l in enumerate(body):
        s = l.strip()
        if not s:
            continue
        m = re.match(r"^(?:subtitle|tagline)\s*:\s*(.+)$", s, re.I)
        if m:
            blocks.append(ContentBlock(BlockKind.SUBTITLE, text=m.group(1).strip()))
            body = body[:i] + body[i+1:]
        break

    # walk the remaining body
    current_section: str | None = None     # "bullets" | "icons" | "stats" | None
    icon_items: list[str] = []
    bullet_items: list[str] = []
    speaker_notes: list[str] = []

    for raw in body:
        s = raw.strip()
        if not s:
            continue

        # speaker notes line
        if re.match(r"^(?:notes?|speaker[_\s-]?notes?)\s*:", s, re.I):
            speaker_notes.append(re.sub(r"^[^:]*:\s*", "", s, count=1))
            continue

        # section heading
        m = _SECTION_TAG.match(s)
        if m:
            tag = m.group(1).lower()
            current_section = "icons" if tag.startswith("icon") else (
                "stats" if tag.startswith("stat") else "bullets")
            continue

        # strip markdown bullet markers
        s_clean = re.sub(r"^[#*\-•]+\s*", "", s)
        s_clean = re.sub(r"^\d+[\.\)]\s+", "", s_clean)

        # stat candidate
        stat = _extract_stat(s_clean) if current_section != "icons" else None
        if stat is not None and current_section != "bullets":
            value, label = stat
            blocks.append(ContentBlock(
                BlockKind.STAT, value=value, label=label, emphasis=0,
            ))
            continue

        # otherwise -> route to current section, default bullets
        if current_section == "icons":
            icon_items.append(s_clean)
        else:
            bullet_items.append(s_clean)

    if bullet_items:
        blocks.append(ContentBlock(BlockKind.BULLETS, items=bullet_items))
    if icon_items:
        blocks.append(ContentBlock(BlockKind.ICON_ROW, items=icon_items))

    # promote the most prominent stat to hero (largest absolute value); if
    # ties or all percentages, the first stat wins. R1.2.1: model-layer
    # advisory only, engine still controls geometry.
    stats = [b for b in blocks if b.kind == BlockKind.STAT]
    if stats:
        hero = max(stats, key=_stat_weight)
        hero.emphasis = 2

    if speaker_notes:
        notes = "\n".join(speaker_notes)

    return Slide(blocks=blocks, intent=LayoutIntent.AUTO, notes=notes)


def _stat_weight(b: ContentBlock) -> float:
    """Numeric weight for picking the hero stat — used inside parse only."""
    if not b.value:
        return 0.0
    m = re.search(r"[+\-]?\d+(?:\.\d+)?", b.value)
    if not m:
        return 0.0
    n = abs(float(m.group(0)))
    # percentages and ratios scale differently; nudge multipliers up
    if "x" in b.value.lower():
        return n * 100
    if "%" in b.value:
        return n
    if "M" in b.value: return n * 1_000_000
    if "B" in b.value: return n * 1_000_000_000
    if "K" in b.value: return n * 1_000
    return n


# ---- multi-slide deck parse ----------------------------------------------

def parse_deck_to_ir(text: str, theme: Theme | None = None, title: str | None = None) -> Deck:
    """Split `---`-separated sections, parse each section to a Slide, wrap
    in a Deck. The model swap replaces parse_to_ir; this function stays."""
    parts = [p.strip() for p in re.split(r"^\s*-{3,}\s*$", text or "", flags=re.M)]
    parts = [p for p in parts if p]
    if not parts:
        parts = [text or ""]
    slides = [parse_to_ir(p) for p in parts]
    deck_title = title or ""
    if not deck_title and slides and slides[0].blocks:
        first = next((b for b in slides[0].blocks if b.kind == BlockKind.TITLE), None)
        if first and first.text:
            deck_title = first.text
    return Deck(slides=slides, theme=theme or Theme(), title=deck_title or "Untitled Deck")
