"""
Storyboard view bundle — the shape the new `/storyboard` page expects.

Builds one response payload from /api/thread_map + /api/narrative output so
the page does ONE fetch per outline edit. The shape matches the design's
hand-rolled INITIAL_THREADS / INITIAL_SUGGESTIONS exactly, plus extras
(spine sentence, tensions, engine badge) that surface the LLM tier when
it ran.

Architectural placement: content-layer adapter. Stateless function of
(outline + LLM availability). No geometry, no colors that aren't already
in the upstream data.
"""
from __future__ import annotations
from typing import Iterable, Optional


# Stable color palette for thread tracks. The spine ribbon gets gold; the
# rest cycle through a soft-but-distinguishable palette tuned to the design.
_PALETTE = [
    "#0E5B36",  # green   — revenue / momentum / growth
    "#E26A2C",  # orange  — engine / drivers
    "#5468C9",  # blue    — gtm / strategy
    "#C99A2E",  # gold    — decisions
    "#C4502B",  # rust    — risks
    "#3D8B97",  # teal
    "#7A5BA1",  # purple
    "#6E7F3D",  # olive
]
_SPINE_COLOR = "#C99A2E"


def compute_storyboard_view(
    outline: list[dict],
    *,
    audience: Optional[str] = None,
    mode: Optional[str] = None,
) -> dict:
    """Bundle threads + suggestions + spine + tensions in the new design shape.

    Cascade: narrative LLM → semantic embeddings → lexical token overlap.
    The cascade lives inside threadmap.compute_thread_map; we just call it
    and call narrative.analyze_narrative in parallel, then adapt.
    """
    from .threadmap import compute_thread_map
    from . import narrative

    # Always produce a threadmap view (cascades automatically)
    tm = compute_thread_map(outline)
    before = tm.get("before") or {}
    graph = before.get("graph") or {}
    ribbons = before.get("ribbons") or []
    stats = before.get("stats") or {}
    engine = before.get("engine") or "empty"

    # When the LLM tier ran, also get the narrative analysis directly so we
    # can surface spine + tensions + structured recommendations.
    narr: Optional[dict] = None
    if narrative.available():
        try:
            narr = narrative.analyze_narrative(outline, audience=audience, mode=mode)
        except Exception:
            narr = None

    threads = _ribbons_to_threads(ribbons, outline, spine_word=stats.get("spine_word"))
    suggestions = _build_suggestions(narr, graph, outline)
    spine = _build_spine(narr, graph)
    tensions = _build_tensions(narr, graph, outline)
    role_map = _build_role_map(narr)

    # apply role_map to outline (returned alongside so the UI can pick it up)
    enriched_outline = [
        {**s, "role": role_map.get(s.get("id")) or s.get("role")}
        for s in outline
    ]

    return {
        "outline":     enriched_outline,
        "threads":     threads,
        "suggestions": suggestions,
        "spine":       spine,
        "tensions":    tensions,
        "engine":      engine,
        "backend":     (narr or {}).get("backend") if narr else None,
        "model":       (narr or {}).get("model")   if narr else None,
        "stats": {
            "slides":    stats.get("slides", len(outline)),
            "orphans":   stats.get("orphans", 0),
            "gaps":      stats.get("gaps", 0),
            "edges":     stats.get("edges", 0),
            "messiness": stats.get("messiness", 0.0),
        },
    }


# ---- ribbon-to-thread adapter -------------------------------------------

def _ribbons_to_threads(
    ribbons: list[dict],
    outline: list[dict],
    *,
    spine_word: Optional[str] = None,
) -> list[dict]:
    """Map threadmap ribbons -> design-shaped threads.

    Ribbon shape:   {token, slides:[index,...], weight, broken, is_spine}
    Thread shape:   {id, label, color, slideIds:[id,...], strength, type}
    """
    threads: list[dict] = []
    palette_i = 0
    for i, r in enumerate(ribbons):
        slide_indices = r.get("slides") or []
        slide_ids = [outline[idx].get("id") for idx in slide_indices
                     if 0 <= idx < len(outline) and outline[idx].get("id")]
        if not slide_ids:
            continue
        is_spine = bool(r.get("is_spine"))
        color = _SPINE_COLOR if is_spine else _PALETTE[palette_i % len(_PALETTE)]
        if not is_spine:
            palette_i += 1
        # weight from threadmap is mean-similarity (0..1) for semantic/LLM,
        # raw count for lexical. Normalize to a 0..1 strength.
        w = float(r.get("weight") or 0)
        strength = max(0.0, min(1.0, w if w <= 1.0 else min(1.0, w / 5.0)))
        threads.append({
            "id":         f"t{i+1}",
            "label":      _truncate_label(r.get("token") or "", 28),
            "color":      color,
            "slideIds":   slide_ids,
            "strength":   round(strength, 2),
            "type":       "core" if is_spine else "arc",
            "broken":     bool(r.get("broken")),
        })
    return threads


def _truncate_label(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# ---- narrative recommendations -> design "suggestions" -------------------

# Map narrative.kind -> design.kind. Lossy by design — the design has fewer
# kinds. New kinds (tension, tighten) map to 'thin' as a sensible default.
_KIND_MAP = {
    "spine":   "spine",      # design has no explicit 'spine' card kind; we
                              # surface the spine separately in the spine bar
    "orphan":  "thin",
    "gap":     "merge",      # bridging a gap = merge adjacent slides or add bumper
    "bridge":  "merge",
    "tension": "order",      # tensions usually become reorder/cut decisions
    "tighten": "thin",
}


def _build_suggestions(
    narr: Optional[dict],
    graph: dict,
    outline: list[dict],
) -> list[dict]:
    """Build the 'AI noticed' cards.

    Preference order:
      1. narrative.recommendations (LLM-authored, concrete edits)
      2. narrative.orphans / gaps (LLM-detected structural issues)
      3. threadmap graph.orphans / gaps (semantic/lexical fallback)
    """
    out: list[dict] = []
    used_kinds: set[str] = set()

    if narr is not None:
        for r in (narr.get("recommendations") or [])[:6]:
            kind = r.get("kind") or "tighten"
            if kind == "spine":
                # spine recs surface in the spine bar — skip from cards
                continue
            design_kind = _KIND_MAP.get(kind, "thin")
            text = r.get("text") or ""
            if r.get("suggested_edit"):
                text = f"{text}  Try: \"{r['suggested_edit']}\""
            out.append({
                "id":       r.get("id") or f"r{len(out)+1}",
                "kind":     design_kind,
                "text":     text,
                "slideIds": r.get("target_slide_ids") or [],
                "actions":  _actions_for_kind(design_kind),
                "advisory": True,
            })
            used_kinds.add(design_kind)

        # surface orphan reasons that didn't get into a recommendation
        for o in (narr.get("orphans") or []):
            sid = o.get("slide_id")
            already = any(sid in (s.get("slideIds") or []) for s in out)
            if already:
                continue
            out.append({
                "id":       f"orphan-{sid}",
                "kind":     "thin",
                "text":     o.get("reason") or "Slide doesn't tie to the spine.",
                "slideIds": [sid] if sid else [],
                "actions":  _actions_for_kind("thin"),
                "advisory": True,
            })

        # surface gap bridge suggestions
        for g in (narr.get("gaps") or []):
            a, b = g.get("from"), g.get("to")
            text = g.get("missing") or "Hard cut between slides."
            if g.get("bridge_suggestion"):
                text = f"{text}  Try: \"{g['bridge_suggestion']}\""
            out.append({
                "id":       f"gap-{a}-{b}",
                "kind":     "merge",
                "text":     text,
                "slideIds": [a, b] if a and b else [],
                "actions":  _actions_for_kind("merge"),
                "advisory": True,
            })

    else:
        # Lexical / semantic fallback — synthesize from threadmap graph.
        orphans = graph.get("orphans") or []
        for sid in orphans[:3]:
            title = next((s.get("title") for s in outline if s.get("id") == sid), "slide")
            out.append({
                "id":       f"orphan-{sid}",
                "kind":     "thin",
                "text":     f"\"{title}\" doesn't share a concept with any other slide.",
                "slideIds": [sid],
                "actions":  _actions_for_kind("thin"),
                "advisory": True,
            })
        for g in (graph.get("gaps") or [])[:3]:
            out.append({
                "id":       f"gap-{g['from']}-{g['to']}",
                "kind":     "merge",
                "text":     f"Hard cut between adjacent slides — no shared concept.",
                "slideIds": [g["from"], g["to"]],
                "actions":  _actions_for_kind("merge"),
                "advisory": True,
            })

    return out[:6]


def _actions_for_kind(kind: str) -> list[str]:
    if kind == "merge": return ["merge", "dismiss"]
    if kind == "order": return ["reorder", "dismiss"]
    if kind == "thin":  return ["develop", "dismiss"]
    return ["accept", "dismiss"]


# ---- spine surface ------------------------------------------------------

def _build_spine(narr: Optional[dict], graph: dict) -> Optional[dict]:
    """The spine card payload."""
    if narr is not None and narr.get("spine"):
        return {
            "text":    narr["spine"],
            "arc":     narr.get("arc") or "",
            "kind":    "narrative",
        }
    g_spine = graph.get("spine")
    if g_spine and g_spine.get("word"):
        # semantic/lexical spine is just a phrase, not a sentence — present it honestly
        return {
            "text":    f"Recurring concept: \"{g_spine['word']}\".",
            "arc":     "",
            "kind":    "concept",
        }
    return None


# ---- tensions surface ---------------------------------------------------

def _build_tensions(
    narr: Optional[dict],
    graph: dict,
    outline: list[dict],
) -> list[dict]:
    """Pass-through tensions when present. Map slide IDs to their indices
    for compact display ('slides 02 · 04')."""
    raw = (narr or {}).get("tensions") or graph.get("tensions") or []
    id_to_idx = {s.get("id"): i + 1 for i, s in enumerate(outline)}
    out = []
    for t in raw:
        sids = t.get("slides") or []
        idxs = [str(id_to_idx.get(sid) or "?").zfill(2) for sid in sids]
        out.append({
            "slides":    sids,
            "slide_idx": idxs,
            "issue":     t.get("issue") or "",
            "kind":      t.get("kind") or "unsupported",
        })
    return out


# ---- role assignment ----------------------------------------------------

# Valid roles the design renders as colored badges. We accept either the
# design's exact strings or common synonyms the LLM might emit.
_ROLE_ALIASES = {
    "summary":     "summary",
    "intro":       "summary",
    "overview":    "summary",
    "setup":       "setup",
    "context":     "setup",
    "deep-dive":   "deep-dive",
    "deep_dive":   "deep-dive",
    "deepdive":    "deep-dive",
    "evidence":    "deep-dive",
    "analysis":    "deep-dive",
    "decision":    "decision",
    "action":      "decision",
    "ask":         "decision",
    "recommendation": "decision",
    "risk":        "risk",
    "concern":     "risk",
    "warning":     "risk",
}


def _build_role_map(narr: Optional[dict]) -> dict:
    """Pull `roles` (slide_id -> role) out of the narrative payload if the
    LLM provided them. The narrative prompt asks for these but they aren't
    required — we tolerate absence."""
    if not narr:
        return {}
    raw = narr.get("roles") or {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for sid, role in raw.items():
        if not isinstance(role, str):
            continue
        canonical = _ROLE_ALIASES.get(role.strip().lower())
        if canonical and isinstance(sid, str):
            out[sid] = canonical
    return out
