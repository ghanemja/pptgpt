"""
IR → smaller IR (REQUIREMENTS §7.3).

R7.1.1: condense is a content-layer transform. It MUST NOT live in layout.py
or render.py. Downstream — the engine, tests, renderer — is unchanged.

R7.3.4: a deterministic, no-model fallback exists for the "collect all the
stats into one summary slide" case. It is offline, predictable, and shipped.
The model-based path is the richer-but-fuzzier option and is a separate
function below (`condense_with_model`), invoked only when a model handle is
supplied.

R7.3.3: condensation is REVIEWABLE. The output Deck carries `notes` on each
condensed slide listing the source slide indices it drew from. The original
deck is not mutated; condense returns a new Deck.

R7.3.5: condensation never fabricates facts. The deterministic path only
copies blocks from the source IR.
"""
from __future__ import annotations
from collections import OrderedDict
from typing import Callable, Optional

from .ir import Slide, Deck, ContentBlock, BlockKind, LayoutIntent, Theme


# ---- deterministic stat-gathering fallback (R7.3.4) ----------------------

def condense_deterministic(deck: Deck, max_slides: int = 3) -> Deck:
    """Pure, offline summarizer. Two slides out: a cover and a stat_callout
    that aggregates the deck's most prominent stats. Plus, when there's
    enough room, a takeaways slide built from the original first bullets.

    Cannot fabricate (R7.3.5) — every block in the output exists in the
    input. The `notes` field documents provenance per slide.
    """
    if not deck.slides:
        return Deck(slides=[], theme=deck.theme, title=deck.title)

    # 1) gather every STAT block, dedupe by value+label
    seen: "OrderedDict[tuple[str, str], tuple[int, ContentBlock]]" = OrderedDict()
    for i, s in enumerate(deck.slides):
        for b in s.blocks:
            if b.kind == BlockKind.STAT and (b.value or b.label):
                key = ((b.value or "").strip(), (b.label or "").strip().lower())
                if key not in seen:
                    seen[key] = (i, b)

    stats: list[tuple[int, ContentBlock]] = list(seen.values())
    # 2) pick the top stats by parse._stat_weight
    from .parse import _stat_weight
    stats.sort(key=lambda iv: _stat_weight(iv[1]), reverse=True)
    chosen = stats[:5]

    # 3) gather the first non-stat bullet from each source slide (for takeaways)
    bullets: list[str] = []
    bullet_sources: list[int] = []
    for i, s in enumerate(deck.slides):
        for b in s.blocks:
            if b.kind == BlockKind.BULLETS and b.items:
                for item in b.items:
                    if item not in bullets:
                        bullets.append(item)
                        bullet_sources.append(i)
                    if len(bullets) >= 3:
                        break
            if len(bullets) >= 3:
                break
        if len(bullets) >= 3:
            break

    # 4) cover slide: title + subtitle taken verbatim from the source
    cover_title = deck.title or "Summary"
    first_title = next(
        (b.text for s in deck.slides for b in s.blocks
         if b.kind == BlockKind.TITLE and b.text),
        cover_title,
    )
    cover = Slide(
        blocks=[
            ContentBlock(BlockKind.TITLE, text=first_title or cover_title),
            ContentBlock(BlockKind.SUBTITLE,
                         text=f"A condensation of {len(deck.slides)} slides"),
        ],
        intent=LayoutIntent.TITLE_SLIDE,
        notes=f"Source: slides 1..{len(deck.slides)} (cover)",
    )

    # 5) stat slide
    stat_blocks: list[ContentBlock] = [
        ContentBlock(BlockKind.TITLE, text="The numbers that matter"),
    ]
    # promote a hero — the top-weighted is already first
    for j, (src_i, b) in enumerate(chosen):
        new_b = ContentBlock(
            BlockKind.STAT, value=b.value, label=b.label,
            emphasis=2 if j == 0 else 0,
        )
        stat_blocks.append(new_b)
    stat_provenance = sorted(set(src_i + 1 for src_i, _ in chosen))
    stat_slide = Slide(
        blocks=stat_blocks,
        intent=LayoutIntent.STAT_CALLOUT if chosen else LayoutIntent.AUTO,
        notes=f"Source: slide(s) {stat_provenance}" if stat_provenance else None,
    )

    # 6) takeaways slide — only when there are real bullets
    out_slides: list[Slide] = [cover]
    if chosen:
        out_slides.append(stat_slide)
    if bullets and len(out_slides) < max_slides:
        takeaways = Slide(
            blocks=[
                ContentBlock(BlockKind.TITLE, text="What to take away"),
                ContentBlock(BlockKind.BULLETS, items=list(bullets)),
            ],
            intent=LayoutIntent.BULLETS_PLAIN,
            notes=f"Source: slide(s) {sorted(set(i+1 for i in bullet_sources))}",
        )
        out_slides.append(takeaways)

    # R7.3.5 guard: if neither stats nor bullets exist, return cover + a
    # truthful "insufficient content" slide rather than inventing material.
    if len(out_slides) == 1:
        out_slides.append(Slide(
            blocks=[
                ContentBlock(BlockKind.TITLE, text="Insufficient content to summarize"),
                ContentBlock(BlockKind.PARAGRAPH,
                             text="The source deck has no stats or bullets the deterministic summarizer can carry forward. Use the model-based path or add structure to the source."),
            ],
            intent=LayoutIntent.TITLE_SLIDE,
            notes="No stats or bullets in source",
        ))

    return Deck(slides=out_slides[:max_slides], theme=deck.theme, title=deck.title)


# ---- model-based path (R7.3.1, R7.3.5, R7.3.3) ---------------------------

def condense_with_model(
    deck: Deck,
    *,
    max_slides: int = 3,
    model_fn: Optional[Callable[[str], str]] = None,
) -> Deck:
    """Model-based condensation. `model_fn(prompt) -> json_string` is the
    swap point for a local LLM. When no model is provided, we cleanly fall
    back to `condense_deterministic` and label the output as such.

    The model contract:
      - Input: a prompt containing the source deck's IR (no geometry).
      - Output: a JSON object {"slides": [{"blocks": [...], "intent": ...}]}.
      - Forbidden: any block whose `value`/`label`/`text` doesn't already
        appear in the source (R7.3.5 — no fabrication). We validate this
        post-hoc; any unanchored stat is dropped.
    """
    if model_fn is None:
        # No model available — be honest. Deterministic path it is.
        out = condense_deterministic(deck, max_slides=max_slides)
        # mark provenance
        for s in out.slides:
            s.notes = (s.notes or "") + " (deterministic — no model)"
        return out

    # Build a compact prompt the model can act on. We deliberately exclude
    # any styling/theme info; this is content-only.
    from .boundary import deck_to_dict
    import json as _json
    src = deck_to_dict(deck)
    prompt = (
        "You are condensing a slide deck IR. Output JSON ONLY:\n"
        '{"slides":[{"blocks":[...], "intent":"...", "notes":"source: slide(s) ..."}]}\n'
        "Rules:\n"
        "1. Only use stats/text/labels that appear in the source.\n"
        "2. No new facts, no rephrasing of numbers.\n"
        "3. Each output slide must list the source slide indices in `notes`.\n"
        f"4. Maximum {max_slides} output slides.\n\n"
        f"Source IR: {_json.dumps(src['slides'])}\n"
    )
    try:
        raw = model_fn(prompt)
        parsed = _json.loads(raw)
    except Exception:
        # Model failed — fall back, do not crash, do not invent
        out = condense_deterministic(deck, max_slides=max_slides)
        for s in out.slides:
            s.notes = (s.notes or "") + " (deterministic fallback after model error)"
        return out

    # Validate against fabrication (R7.3.5)
    source_atoms = _source_atoms(deck)
    from .boundary import dict_to_ir_slide
    slides: list[Slide] = []
    for raw_slide in (parsed.get("slides") or [])[:max_slides]:
        try:
            sl = dict_to_ir_slide(raw_slide)
        except Exception:
            continue
        sl.blocks = [b for b in sl.blocks if _block_is_anchored(b, source_atoms)]
        if not sl.blocks:
            continue
        slides.append(sl)

    if not slides:
        return condense_deterministic(deck, max_slides=max_slides)
    return Deck(slides=slides, theme=deck.theme, title=deck.title)


def _source_atoms(deck: Deck) -> set[str]:
    atoms: set[str] = set()
    for s in deck.slides:
        for b in s.blocks:
            for v in (b.text, b.value, b.label):
                if v:
                    atoms.add(v.strip().lower())
            for item in (b.items or []):
                atoms.add(item.strip().lower())
    return atoms


def _block_is_anchored(b: ContentBlock, atoms: set[str]) -> bool:
    """R7.3.5: every text-bearing field must be present in the source."""
    if b.text and b.text.strip().lower() not in atoms:
        return False
    if b.value and b.value.strip().lower() not in atoms:
        return False
    if b.label and b.label.strip().lower() not in atoms:
        return False
    if b.items:
        for item in b.items:
            if item.strip().lower() not in atoms:
                return False
    return True
