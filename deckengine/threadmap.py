"""
Thread map: visualize the messiness of a deck's narrative.

Given a storyboard outline (and optionally its recommendations), this module
computes two views — "current" and "simulated" — each containing:

  - graph  : nodes (slides) + edges (shared-meaning links) + orphans + spine + gaps
  - ribbons: sequence of concept threads (phrases that span multiple slides)

The graph view is the input to a force-directed layout; the ribbons view
is the input to a Sankey-flavored film strip. Both are pure data — the UI
draws.

Two implementations live here:
  1. SEMANTIC (preferred): uses sentence-transformer embeddings. "Shared
     meaning" is cosine similarity between slide embeddings — so paraphrase
     and synonym link as expected (revenue / ARR / top-line are one thread).
  2. LEXICAL (fallback): bag-of-words token overlap. Used only when the
     embedding model is unavailable. Loud about the limitation.

Architectural placement: content-layer transform. No geometry, no colors.

R7.3.5 spirit: when computing the "simulated" state, the simulator only
weaves tokens/concepts already present in the source. It does not invent.
"""
from __future__ import annotations
import re
from typing import Iterable, Optional

from . import semantics, narrative


# Semantic thresholds — tuned for all-MiniLM-L6-v2 normalized vectors. These
# are CONSTRAINTS the engine treats as hard floors, not soft hints.
SIM_LINK_THRESHOLD    = 0.42   # two slides "share meaning" above this
SIM_GAP_THRESHOLD     = 0.35   # adjacent slides under this are a hard cut
SIM_ORPHAN_THRESHOLD  = 0.32   # no peer above this -> orphan
SIM_RIBBON_THRESHOLD  = 0.40   # a phrase "touches" a slide above this


# ---- lexical helpers (used by fallback path) ---------------------------

_STOPS = {
    "the","a","an","and","or","of","to","for","in","on","at","is","it","this",
    "that","with","from","as","by","be","are","was","were","but","so","if",
    "we","our","you","your","their","they","will","can","have","has","had",
    "about","into","than","then","what","which","who","one","more","less",
    "most","any","some","no",
}


def _tok(s: str) -> set[str]:
    return {w for w in re.findall(r"\b[a-z][a-z0-9]+\b", (s or "").lower())
            if w not in _STOPS and len(w) >= 3}


def _slide_text(slide: dict) -> str:
    parts = [slide.get("title", "") or ""]
    parts.extend(slide.get("messages") or [])
    parts.append(slide.get("bumper", "") or "")
    return " ".join([p for p in parts if p])


# ---- core computation ----------------------------------------------------

def compute_thread_map(
    outline: list[dict],
    *,
    recommendations: Optional[list[dict]] = None,
    accepted_ids: Optional[Iterable[str]] = None,
    mode: str = "potential",  # 'potential' (all advisories) | 'accepted'
    engine: str = "auto",     # 'auto' (LLM first) | 'fast' (skip the LLM tier)
    sides: str = "both",      # 'both' | 'before' (skip the simulation)
) -> dict:
    """Return {'before': view, 'after': view}.

    - `before` is the raw outline as it stands.
    - `after` is the simulated outline with advisories applied:
        * mode='potential' applies every advisory in `recommendations`.
        * mode='accepted'  applies only those whose id is in `accepted_ids`.
    """
    recs = recommendations or []
    accepted = set(accepted_ids or [])

    before = _view(outline, engine=engine)
    if mode == "accepted":
        applicable = [r for r in recs if r.get("id") in accepted]
    else:
        applicable = list(recs)

    # The simulated side costs as much as the real one — on the LLM tier that
    # is a second model call. A caller that only wants to read the deck as it
    # stands asks for `sides='before'` and pays once.
    if sides == "before":
        after, diff, applicable = None, None, []
    else:
        after_outline = _apply_advisories(outline, applicable)
        after = _view(after_outline, engine=engine)
        # Carry across the diff so the UI can highlight what changed
        diff = _diff_views(before, after)

    return {
        "before": before,
        "after": after,
        "diff": diff,
        "applied": [r.get("id") for r in applicable],
        "mode": mode,
    }


# ---- view (graph + ribbons) ---------------------------------------------

def _view(outline: list[dict], *, engine: str = "auto") -> dict:
    """Compute one graph + ribbon view for an outline.

    Cascade: narrative (LLM) > semantic (embeddings) > lexical (tokens).
    The returned shape is identical across all three so the UI doesn't care
    which path ran — but `engine` field tells it, and `graph.orphan_reasons`
    / `graph.tensions` only exist on the LLM path.
    """
    if not outline:
        return {
            "graph": {"nodes": [], "edges": [], "orphans": [], "spine": None, "gaps": []},
            "ribbons": [], "stats": {"slides": 0, "messiness": 0.0},
            "engine": "empty",
        }

    # Tier 1: real model — reads the deck and reasons about narrative. It is
    # the best read and by far the slowest (a local 4B model takes tens of
    # seconds), so an interactive caller can ask to start below it.
    if engine != "fast" and narrative.available():
        narr = narrative.analyze_narrative(outline)
        if narr is not None:
            view = narrative.to_threadmap_view(narr, outline)
            view["engine"] = "narrative"
            view["narrative_spine"] = narr.get("spine")
            view["narrative_arc"]   = narr.get("arc")
            return view

    # Tier 2: embedding similarity — catches synonyms/paraphrase
    if semantics.available():
        view = _view_semantic(outline)
        if view is not None:
            view["engine"] = "semantic"
            return view

    # Tier 3: bag-of-words token overlap — last resort, honest about it
    view = _view_lexical(outline)
    view["engine"] = "lexical"
    return view


def _view_lexical(outline: list[dict]) -> dict:
    """Bag-of-words token-overlap analysis. Fallback path only.

    Honest limitation: this misses paraphrase and synonym entirely — two
    slides about "revenue" and "ARR" look like orphans of each other here.
    The semantic path corrects that.
    """
    slide_tokens: list[set[str]] = [_tok(_slide_text(s)) for s in outline]

    # Nodes — one per slide, carries title + count
    nodes = []
    for i, s in enumerate(outline):
        nodes.append({
            "id": s.get("id") or f"s{i}",
            "index": i,
            "title": (s.get("title") or "").strip() or f"Slide {i+1}",
            "concept_count": len(slide_tokens[i]),
        })

    # Edges — pairwise overlap (only when there's at least one shared concept)
    edges = []
    for i in range(len(slide_tokens)):
        for j in range(i + 1, len(slide_tokens)):
            shared = slide_tokens[i] & slide_tokens[j]
            if not shared:
                continue
            edges.append({
                "from":   nodes[i]["id"],
                "to":     nodes[j]["id"],
                "weight": len(shared),
                "shared": sorted(shared)[:6],   # cap for UI
                "adjacent": (j - i == 1),
            })

    # Orphans — slides whose token set shares nothing with ANY other slide
    orphan_ids = []
    for i, ts in enumerate(slide_tokens):
        if not ts:
            orphan_ids.append(nodes[i]["id"]); continue
        shares_anything = any(j != i and (ts & slide_tokens[j])
                              for j in range(len(slide_tokens)))
        if not shares_anything:
            orphan_ids.append(nodes[i]["id"])

    # Spine — single most-shared token across the deck
    counts: dict[str, int] = {}
    for ts in slide_tokens:
        for w in ts:
            counts[w] = counts.get(w, 0) + 1
    spine_pairs = sorted(
        [(w, c) for w, c in counts.items() if c >= 2],
        key=lambda x: (-x[1], x[0]),
    )
    if spine_pairs and spine_pairs[0][1] >= max(3, (len(outline) + 1) // 2):
        word, count = spine_pairs[0]
        spine = {
            "word": word,
            "count": count,
            "slides": [nodes[i]["id"] for i, ts in enumerate(slide_tokens) if word in ts],
        }
    else:
        spine = None

    # Gaps — adjacent slide pairs that share nothing
    gaps = []
    for i in range(len(slide_tokens) - 1):
        a, b = slide_tokens[i], slide_tokens[i + 1]
        if a and b and not (a & b):
            gaps.append({
                "from": nodes[i]["id"],
                "to":   nodes[i + 1]["id"],
            })

    # Ribbons — token-thread tracks for the Sankey-style view.
    # A ribbon is a token, plus the indices of slides it appears in. We only
    # keep tokens present in >=2 slides — single-slide tokens aren't threads.
    ribbons = []
    for word, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < 2:
            continue
        slides_in = [i for i, ts in enumerate(slide_tokens) if word in ts]
        # gap == there's an index between min and max where the word is absent
        has_gap = (max(slides_in) - min(slides_in) + 1) != len(slides_in)
        ribbons.append({
            "token": word,
            "slides": slides_in,
            "weight": count,
            "broken": has_gap,
            "is_spine": (spine is not None and word == spine["word"]),
        })
        if len(ribbons) >= 8:
            break  # cap for UI legibility

    # Messiness score — a single number the UI can show in a header.
    # Higher = messier. Compose from: orphan rate, gap rate, spine absence.
    n = len(outline)
    orphan_rate = len(orphan_ids) / n
    gap_rate = len(gaps) / max(1, n - 1)
    spine_penalty = 0.0 if spine else 0.35
    messiness = round(min(1.0, 0.45 * orphan_rate + 0.35 * gap_rate + spine_penalty), 3)

    return {
        "graph": {
            "nodes": nodes,
            "edges": edges,
            "orphans": orphan_ids,
            "spine": spine,
            "gaps": gaps,
        },
        "ribbons": ribbons,
        "stats": {
            "slides":     n,
            "orphans":    len(orphan_ids),
            "gaps":       len(gaps),
            "edges":      len(edges),
            "ribbons":    len(ribbons),
            "spine_word": spine["word"] if spine else None,
            "messiness":  messiness,
        },
    }


# ---- semantic view (preferred path) -------------------------------------

def _view_semantic(outline: list[dict]) -> Optional[dict]:
    """Semantic version: cosine similarity between slide embeddings.

    Two slides about the same idea but written in different vocabulary
    still link here. Returns None on any embedding failure so the caller
    falls back to lexical.
    """
    vecs = semantics.embed_outline(outline)
    if vecs is None or len(vecs) == 0:
        return None

    sim = semantics.pairwise_sim(vecs)
    if sim is None:
        return None

    nodes = []
    for i, s in enumerate(outline):
        nodes.append({
            "id": s.get("id") or f"s{i}",
            "index": i,
            "title": (s.get("title") or "").strip() or f"Slide {i+1}",
            "concept_count": 0,  # not used in semantic view
        })

    # Edges — every pair above the link threshold. The 'shared' list now
    # carries the candidate phrases from EITHER slide that best explain why
    # the slides match (top-3 closest phrases to the other slide's embedding).
    edges = []
    n = len(outline)
    for i in range(n):
        for j in range(i + 1, n):
            s = sim[i][j]
            if s < SIM_LINK_THRESHOLD:
                continue
            shared = _explain_link(outline[i], outline[j], vecs[i], vecs[j])
            edges.append({
                "from": nodes[i]["id"],
                "to":   nodes[j]["id"],
                "weight":   round(s, 3),     # continuous, not a count
                "shared":   shared[:6],
                "adjacent": (j - i == 1),
            })

    # Orphans — slides whose nearest peer is below the orphan threshold
    orphan_ids = []
    for i in range(n):
        best = max((sim[i][j] for j in range(n) if j != i), default=0.0)
        if best < SIM_ORPHAN_THRESHOLD:
            orphan_ids.append(nodes[i]["id"])

    # Gaps — adjacent slides under the gap threshold
    gaps = []
    for i in range(n - 1):
        if sim[i][i + 1] < SIM_GAP_THRESHOLD:
            gaps.append({"from": nodes[i]["id"], "to": nodes[i + 1]["id"]})

    # Spine — the central concept of the deck.
    # 1. Compute the centroid of all slide embeddings.
    # 2. Find the candidate phrase across the entire deck whose embedding
    #    is closest to the centroid.
    # 3. The slides where that phrase semantically appears (>= ribbon
    #    threshold) form the spine's slide list.
    import numpy as np
    centroid = np.mean(np.stack(vecs), axis=0)
    centroid /= max(1e-9, float(np.linalg.norm(centroid)))

    deck_text = "  ".join(_slide_text(s) for s in outline)
    candidates = semantics.extract_candidate_phrases(deck_text, max_phrases=24)
    phrase_vecs = []
    for p in candidates:
        v = semantics.embed_text(p)
        if v is None:
            return None
        phrase_vecs.append((p, v))

    spine = None
    if phrase_vecs:
        # phrase closest to centroid AND that semantically touches >= half
        scored = sorted(
            phrase_vecs,
            key=lambda pv: -float(np.dot(centroid, pv[1])),
        )
        threshold = max(2, (n + 1) // 2)
        for word, pv in scored:
            in_slides = [i for i, sv in enumerate(vecs)
                         if float(np.dot(sv, pv)) >= SIM_RIBBON_THRESHOLD]
            if len(in_slides) >= threshold:
                spine = {
                    "word":   word,
                    "count":  len(in_slides),
                    "slides": [nodes[i]["id"] for i in in_slides],
                }
                break

    # Ribbons — semantic threads. For each candidate phrase, the slides it
    # semantically touches. We dedupe and keep the strongest 8.
    seen_keys: set[str] = set()
    ribbons: list[dict] = []
    if phrase_vecs:
        scored = []
        for word, pv in phrase_vecs:
            in_slides = [i for i, sv in enumerate(vecs)
                         if float(np.dot(sv, pv)) >= SIM_RIBBON_THRESHOLD]
            if len(in_slides) < 2:
                continue
            mean_sim = sum(float(np.dot(vecs[i], pv)) for i in in_slides) / len(in_slides)
            scored.append((word, in_slides, mean_sim))
        # rank by reach * strength, dedupe phrases whose slide sets duplicate
        scored.sort(key=lambda x: (-len(x[1]) * x[2]))
        for word, in_slides, mean_sim in scored:
            key = ",".join(str(i) for i in in_slides)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            ribbons.append({
                "token":   word,
                "slides":  in_slides,
                "weight":  round(mean_sim, 3),
                "broken":  (max(in_slides) - min(in_slides) + 1) != len(in_slides),
                "is_spine": bool(spine and word == spine["word"]),
            })
            if len(ribbons) >= 8:
                break

    # Messiness — same headline metric, computed off semantic signals.
    orphan_rate = len(orphan_ids) / n
    gap_rate = len(gaps) / max(1, n - 1)
    spine_penalty = 0.0 if spine else 0.35
    messiness = round(min(1.0, 0.45 * orphan_rate + 0.35 * gap_rate + spine_penalty), 3)

    return {
        "graph": {
            "nodes": nodes,
            "edges": edges,
            "orphans": orphan_ids,
            "spine": spine,
            "gaps": gaps,
        },
        "ribbons": ribbons,
        "stats": {
            "slides":     n,
            "orphans":    len(orphan_ids),
            "gaps":       len(gaps),
            "edges":      len(edges),
            "ribbons":    len(ribbons),
            "spine_word": spine["word"] if spine else None,
            "messiness":  messiness,
        },
    }


def _explain_link(slide_a: dict, slide_b: dict, vec_a, vec_b) -> list[str]:
    """Return phrases that semantically connect two slides — the top phrases
    from either side that score highly against the other side's embedding."""
    import numpy as np
    cands = (semantics.extract_candidate_phrases(_slide_text(slide_a), 8)
             + semantics.extract_candidate_phrases(_slide_text(slide_b), 8))
    seen: set[str] = set()
    scored: list[tuple[float, str]] = []
    for p in cands:
        if p in seen: continue
        seen.add(p)
        pv = semantics.embed_text(p)
        if pv is None:
            continue
        # how well does this phrase explain BOTH slides? min of the two sims
        score = min(float(np.dot(vec_a, pv)), float(np.dot(vec_b, pv)))
        if score >= 0.30:
            scored.append((score, p))
    scored.sort(reverse=True)
    return [p for _, p in scored[:6]]


# ---- advisory application (the "after" simulator) -----------------------

def _apply_advisories(outline: list[dict], recs: list[dict]) -> list[dict]:
    """Return a *new* outline with advisories applied. NEVER invents tokens;
    only weaves existing concepts through more slides (R7.3.5 spirit)."""
    # deep-ish copy
    out = [
        {**s,
         "title": s.get("title", "") or "",
         "messages": list(s.get("messages") or []),
         "bumper": s.get("bumper", "") or ""}
        for s in outline
    ]
    if not out or not recs:
        return out

    slide_tokens = [_tok(_slide_text(s)) for s in out]

    # 1) spine: promote the spine word into every title that doesn't carry it.
    #    Only if the spine word actually appears somewhere in the source —
    #    we never make up a thread.
    spine_recs = [r for r in recs if r.get("kind") == "spine"]
    if spine_recs:
        word = _spine_word(slide_tokens)
        if word:
            for i, s in enumerate(out):
                if word not in slide_tokens[i]:
                    s["title"] = (s["title"] + (" — " if s["title"] else "") + word).strip()
                    slide_tokens[i].add(word)

    # 2) orphan: tag orphan titles with the spine word (same anti-fabrication
    #    guard); if no spine exists, leave them alone.
    word = _spine_word(slide_tokens)
    orphan_recs = [r for r in recs if r.get("kind") == "orphan"]
    if orphan_recs and word:
        for r in orphan_recs:
            sid = (r.get("slideIds") or [None])[0] if r.get("slideIds") else None
            i = _idx_for_sid(out, sid) if sid else _idx_for_id_in_text(out, r.get("text", ""))
            if i is None:
                continue
            if word not in slide_tokens[i]:
                out[i]["title"] = (out[i]["title"] + (" · " if out[i]["title"] else "") + word).strip()
                slide_tokens[i].add(word)

    # 3) gap: bridge a hard cut by inserting the spine word into the latter
    #    slide's bumper. Again, only an existing token.
    gap_recs = [r for r in recs if r.get("kind") == "gap"]
    for r in gap_recs:
        m = re.search(r"slide\s+(\d+)\s+and\s+(\d+)", r.get("text", ""), re.I)
        if not m:
            continue
        a = int(m.group(1)) - 1
        b = int(m.group(2)) - 1
        if 0 <= b < len(out) and word:
            if word not in slide_tokens[b]:
                out[b]["bumper"] = (out[b]["bumper"] + (" · " if out[b]["bumper"] else "") + word).strip()
                slide_tokens[b].add(word)

    # 4) bridge: weave a skipped concept through the middle slide. The recommendation
    #    text mentions the concept in quotes; extract it.
    bridge_recs = [r for r in recs if r.get("kind") == "bridge"]
    for r in bridge_recs:
        text = r.get("text", "")
        m_concept = re.search(r'"([^"]+)"', text)
        m_slides = re.search(r"slides?\s+(\d+)\s+and\s+(\d+)", text, re.I)
        m_mid = re.search(r"slide\s+(\d+)\s+drops", text, re.I)
        if not (m_concept and (m_mid or m_slides)):
            continue
        concept = m_concept.group(1).lower()
        if m_mid:
            mid_i = int(m_mid.group(1)) - 1
        else:
            mid_i = int(m_slides.group(1)) - 1 + 1
        # only weave if the concept exists somewhere in the source already
        in_source = any(concept in ts for ts in slide_tokens)
        if not (in_source and 0 <= mid_i < len(out)):
            continue
        if concept not in slide_tokens[mid_i]:
            out[mid_i]["bumper"] = (out[mid_i]["bumper"] + (" · " if out[mid_i]["bumper"] else "") + concept).strip()
            slide_tokens[mid_i].add(concept)

    # 5) merge: collapse duplicate-title slides into one (the first). Only if
    #    we have at least two slides left after.
    merge_recs = [r for r in recs if r.get("kind") == "merge"]
    drop_ids: set[str] = set()
    for r in merge_recs:
        ids = r.get("slideIds") or []
        if len(ids) >= 2 and len(out) - len(drop_ids) > 2:
            for sid in ids[1:]:
                drop_ids.add(sid)
    if drop_ids:
        out = [s for s in out if s.get("id") not in drop_ids]

    return out


def _spine_word(slide_tokens: list[set[str]]) -> Optional[str]:
    if not slide_tokens:
        return None
    counts: dict[str, int] = {}
    for ts in slide_tokens:
        for w in ts:
            counts[w] = counts.get(w, 0) + 1
    pairs = sorted(
        [(w, c) for w, c in counts.items() if c >= 2],
        key=lambda x: (-x[1], x[0]),
    )
    if not pairs:
        return None
    word, count = pairs[0]
    if count < max(2, (len(slide_tokens) + 1) // 2):
        return None
    return word


def _idx_for_sid(outline: list[dict], sid: str) -> Optional[int]:
    for i, s in enumerate(outline):
        if s.get("id") == sid:
            return i
    return None


def _idx_for_id_in_text(outline: list[dict], text: str) -> Optional[int]:
    m = re.search(r"slide\s+(\d+)", text or "", re.I)
    if not m:
        return None
    i = int(m.group(1)) - 1
    if 0 <= i < len(outline):
        return i
    return None


# ---- diff (for UI highlights) -------------------------------------------

def _diff_views(before: dict, after: dict) -> dict:
    """Return per-metric deltas so the UI can show 'cleaner by X%' confidently."""
    bs, as_ = before["stats"], after["stats"]
    return {
        "orphans_delta":   as_["orphans"]   - bs["orphans"],
        "gaps_delta":      as_["gaps"]      - bs["gaps"],
        "edges_delta":     as_["edges"]     - bs["edges"],
        "ribbons_delta":   as_["ribbons"]   - bs["ribbons"],
        "messiness_delta": round(as_["messiness"] - bs["messiness"], 3),
        "spine_appeared":  bool(after["graph"]["spine"]) and not before["graph"]["spine"],
        "engine":          before.get("engine", "lexical"),
    }
