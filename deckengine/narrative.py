"""
Narrative analysis — an LLM reads the deck and identifies story structure.

This is the layer the user actually means when they say "look at the deck
and figure out the through-line." It does NOT compute vector similarity
between slides. It asks a model to *read*: what is the deck arguing? where
does the argument break? which slides contradict each other? what's missing
between slide 2 and 3?

The model swap point is one function: `_llm_call(prompt) -> str`. Today
it calls Claude via the Anthropic API; later it calls Ollama/Gemma. The
rest of the module — prompt construction, JSON validation, anti-fabrication
checks, caching, graceful fallback — is unchanged across that swap.

Public API:
    available() -> bool
    analyze_narrative(outline, audience=None, mode=None) -> dict | None

Return shape:
    {
        "spine":   "natural-language statement of the through-line",
        "arc":     "problem→evidence→takeaway" | "before→after" | ... ,
        "orphans": [{"slide_id": str, "reason": str}],
        "gaps":    [{"from": str, "to": str, "missing": str,
                     "bridge_suggestion": str}],
        "tensions":[{"slides": [str, ...], "issue": str,
                     "kind": "contradiction" | "redundancy" | "unsupported"}],
        "recommendations": [
            {"id": str, "kind": "spine|orphan|gap|bridge|tension|tighten",
             "text": str, "target_slide_ids": [str], "advisory": bool,
             "suggested_edit": str?}
        ],
        "model": "claude-sonnet-4-6" | "gemma" | "stub"
    }

Returns `None` when the model is unavailable. Callers should cascade to the
semantic embedder or the lexical fallback.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import threading
import time
from typing import Callable, Optional


# ---- caching -------------------------------------------------------------

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()
_MAX_CACHE = 256


def _outline_hash(outline: list[dict], audience: str | None, mode: str | None) -> str:
    """Stable hash over the outline's text content (id/title/messages/bumper)
    plus the audience and mode. Geometry-free; matches the §0 invariant."""
    payload = []
    for s in outline:
        payload.append({
            "id":       s.get("id") or "",
            "title":    (s.get("title") or "").strip(),
            "messages": [m for m in (s.get("messages") or []) if m],
            "bumper":   (s.get("bumper") or "").strip(),
        })
    body = json.dumps(
        {"outline": payload, "audience": audience or "", "mode": mode or ""},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---- model swap point ---------------------------------------------------
#
# Two production backends are wired here, selectable by env var:
#
#   DECKENGINE_NARRATIVE_BACKEND=anthropic   (default)
#     Calls api.anthropic.com via the `anthropic` SDK.
#     Requires ANTHROPIC_API_KEY.
#     Configurable via DECKENGINE_NARRATIVE_MODEL (default claude-sonnet-4-6).
#
#   DECKENGINE_NARRATIVE_BACKEND=ollama
#     Calls a local Ollama server (default http://localhost:11434).
#     Requires `ollama serve` running locally and the model pulled:
#         ollama pull gemma4              # E4B, 9.6 GB on disk (default)
#         ollama pull gemma4:e2b          # E2B, 7.2 GB — works on 8 GB Macs
#         ollama pull gemma4:26b          # 26B MoE, 18 GB — needs 32 GB Mac
#         ollama pull gemma4:31b          # 31B Dense, 20 GB — needs 32 GB Mac
#     Configurable via OLLAMA_HOST and OLLAMA_MODEL.
#     Fully offline — no key, no outbound network.
#
# Both share the same prompt, the same JSON-extraction logic, and the same
# anti-fabrication validator. The swap is one env var.

_BACKEND     = os.environ.get("DECKENGINE_NARRATIVE_BACKEND", "anthropic").lower()
_MODEL_NAME  = os.environ.get("DECKENGINE_NARRATIVE_MODEL", "claude-sonnet-4-6")
_API_KEY     = os.environ.get("ANTHROPIC_API_KEY", "")
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
# Gemma via an OpenAI-compatible /v1 endpoint (the shared HF Inference
# Endpoint). Reuses the same LOCAL_LLM_* env as Brain University, so one
# config wires both apps to the same hosted Gemma.
#   DECKENGINE_NARRATIVE_BACKEND=gemma
#   LOCAL_LLM_BASE=https://<endpoint>.endpoints.huggingface.cloud/v1
#   LOCAL_LLM_KEY=<hf token>   LOCAL_LLM_MODEL=gemma
_GEMMA_BASE  = os.environ.get("LOCAL_LLM_BASE", "").rstrip("/")
_GEMMA_KEY   = os.environ.get("LOCAL_LLM_KEY", "")
_GEMMA_MODEL = os.environ.get("LOCAL_LLM_MODEL", "gemma")

# A pluggable callable so tests (and ad-hoc swaps) can inject a custom LLM.
_llm_override: Optional[Callable[[str], str]] = None


def set_llm(fn: Optional[Callable[[str], str]]) -> None:
    """Inject a custom LLM caller. Pass None to restore the default."""
    global _llm_override
    _llm_override = fn


def available() -> bool:
    """Is *some* narrative model usable, right now?"""
    if _llm_override is not None:
        return True
    if _BACKEND == "gemma":
        return bool(_GEMMA_BASE)
    if _BACKEND == "ollama":
        # cheap reachability check, swallow any error
        try:
            import urllib.request
            req = urllib.request.Request(f"{_OLLAMA_HOST}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as r:
                return 200 <= r.status < 300
        except Exception:
            return False
    # anthropic
    if _API_KEY:
        try:
            import anthropic  # noqa: F401
            return True
        except Exception:
            return False
    return False


def _llm_call_anthropic(prompt: str, system: str = "") -> str:
    """Anthropic API. Requires anthropic SDK + ANTHROPIC_API_KEY."""
    import anthropic
    client = anthropic.Anthropic(api_key=_API_KEY)
    resp = client.messages.create(
        model=_MODEL_NAME,
        max_tokens=2048,
        temperature=0.2,
        system=system or _SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = []
    for blk in resp.content:
        if getattr(blk, "type", None) == "text":
            parts.append(blk.text)
        else:
            txt = getattr(blk, "text", None)
            if txt: parts.append(txt)
    return "\n".join(parts)


def _llm_call_ollama(prompt: str, system: str = "") -> str:
    """Local Ollama. Hits the /api/chat HTTP endpoint — no SDK dependency.

    The prompt is wrapped with the same system message used for Anthropic so
    Gemma sees identical instructions. Output format is identical.
    """
    import json as _json
    import urllib.request
    payload = {
        "model": _OLLAMA_MODEL,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 2048,
        },
        "messages": [
            {"role": "system", "content": system or _SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        # Ollama supports JSON-mode for compliant models; nudges Gemma to emit
        # parseable JSON instead of conversational text.
        "format": "json",
    }
    req = urllib.request.Request(
        f"{_OLLAMA_HOST}/api/chat",
        data=_json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read().decode("utf-8", errors="replace")
    data = _json.loads(body)
    msg = data.get("message") or {}
    return str(msg.get("content") or "")


def _llm_call_gemma(prompt: str, system: str = "") -> str:
    """Gemma via an OpenAI-compatible /v1/chat/completions endpoint (the shared
    HF Inference Endpoint). Bearer auth, reasoning-model token headroom, and
    cold-start retry for a scale-to-zero endpoint."""
    import json as _json
    import time as _time
    import urllib.request, urllib.error
    if not _GEMMA_BASE:
        raise RuntimeError("LOCAL_LLM_BASE not set")
    url = f"{_GEMMA_BASE}/chat/completions"
    payload = {
        "model": _GEMMA_MODEL,
        "messages": [
            {"role": "system", "content": system or _SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": 4000,   # reasoning model spends budget thinking first
        "temperature": 0.2,
    }
    headers = {"Content-Type": "application/json"}
    if _GEMMA_KEY:
        headers["Authorization"] = f"Bearer {_GEMMA_KEY}"
    data = _json.dumps(payload).encode("utf-8")
    last: Exception | None = None
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=300) as r:
                body = r.read().decode("utf-8", errors="replace")
            obj = _json.loads(body)
            msg = (obj.get("choices") or [{}])[0].get("message") or {}
            content = (msg.get("content") or "").strip()
            if not content:  # reasoning model may put it here if truncated
                content = (msg.get("reasoning_content") or "").strip()
            if content:
                return content
            last = RuntimeError("empty content from gemma")
        except urllib.error.HTTPError as e:
            if e.code in (502, 503, 504):   # endpoint cold-starting
                last = e; _time.sleep(min(30, 10 * (attempt + 1))); continue
            raise
        except Exception as e:
            last = e; _time.sleep(5 * (attempt + 1))
    raise last or RuntimeError("gemma call failed")


def _backend_chain() -> list[str]:
    """Pick the order to try backends. Primary first, then any other backend
    that *looks* configured. This means a configured fallback never silently
    activates — but if you set both, we'll try the other one before giving up."""
    chain = [_BACKEND]
    if _BACKEND == "gemma":
        # gemma is self-contained; only fall back to anthropic if a key exists.
        other = "anthropic" if _API_KEY else None
    else:
        other = "anthropic" if _BACKEND == "ollama" else "ollama"
    # only add 'other' if its prerequisites look set
    if other == "anthropic" and _API_KEY:
        chain.append("anthropic")
    elif other == "ollama":
        # cheap ping
        try:
            import urllib.request
            req = urllib.request.Request(f"{_OLLAMA_HOST}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=0.5) as r:
                if 200 <= r.status < 300:
                    chain.append("ollama")
        except Exception:
            pass
    # dedupe while preserving order
    seen, out = set(), []
    for b in chain:
        if b not in seen:
            seen.add(b); out.append(b)
    return out


# The backend that actually answered the last call. /api/narrative reads this
# so the UI can show what really ran (not what was *configured*).
_last_used: str = ""


def last_used_backend() -> str:
    return _last_used


def _llm_call_default(prompt: str, system: str = "") -> str:
    """Try each backend in the chain. First one that returns text wins. The
    last exception is re-raised only if every backend fails."""
    global _last_used
    last_err: Exception | None = None
    for b in _backend_chain():
        try:
            if b == "ollama":
                text = _llm_call_ollama(prompt, system)
            elif b == "gemma":
                text = _llm_call_gemma(prompt, system)
            else:
                text = _llm_call_anthropic(prompt, system)
            if text and text.strip():
                _last_used = b
                return text
        except Exception as e:
            last_err = e
            try:
                import sys
                print(f"[narrative] {b} backend failed, trying next: {e}", file=sys.stderr)
            except Exception:
                pass
    if last_err is not None:
        raise last_err
    raise RuntimeError("no narrative backend produced output")


def _llm_call(prompt: str, system: str = "") -> str:
    if _llm_override is not None:
        global _last_used
        _last_used = "override"
        return _llm_override(prompt)
    return _llm_call_default(prompt, system)


def call(prompt: str, system: str) -> str:
    """Public swap point for callers outside narrative analysis (e.g. the
    workspace slide generator). Same backend chain, override, and
    caching-free semantics as `_llm_call` — just with an explicit system
    prompt instead of the narrative-analysis one."""
    return _llm_call(prompt, system)


def backend_info() -> dict:
    """For the /api/narrative health response and the engine badge tooltip."""
    if _llm_override is not None:
        return {"backend": "override", "model": "custom"}
    if _BACKEND == "gemma":
        return {"backend": "gemma", "model": _GEMMA_MODEL, "base": _GEMMA_BASE}
    if _BACKEND == "ollama":
        return {"backend": "ollama", "model": _OLLAMA_MODEL, "host": _OLLAMA_HOST}
    return {"backend": "anthropic", "model": _MODEL_NAME}


# ---- prompt -------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a deck-narrative editor. You read a slide outline and identify:

1. The actual through-line (the one argument or question the deck is making).
2. The arc shape (problem→cause→solution, before→after, claim→evidence→takeaway, etc.).
3. A role for each slide — does it set up the question, summarize, dig
   deep on a finding, name a risk, or call for a decision?
4. Orphan slides — slides that don't serve the through-line, with WHY.
5. Gaps — adjacent slides that don't connect, with WHAT'S MISSING and a
   concrete bridge suggestion.
6. Tensions — contradictions, redundancies, or claims not supported by other
   slides in the deck.
7. Concrete recommendations — specific edits, each tied to slide IDs that
   actually exist in the input.

Output STRICT JSON only (no commentary, no markdown fences). Schema:

{
  "spine": "<one sentence stating the through-line>",
  "arc": "<one of: problem→evidence→takeaway | before→after | claim→evidence→takeaway | setup→escalation→resolution | status→risk→ask | other>",
  "roles": {"<slide_id>": "summary|setup|deep-dive|decision|risk"},
  "orphans": [{"slide_id": "<id>", "reason": "<one-sentence why>"}],
  "gaps": [{"from": "<id>", "to": "<id>", "missing": "<what's missing>",
            "bridge_suggestion": "<concrete sentence to add>"}],
  "tensions": [{"slides": ["<id>", ...],
                "issue": "<one-sentence description>",
                "kind": "contradiction|redundancy|unsupported"}],
  "recommendations": [
    {"id": "<short-stable-id>",
     "kind": "spine|orphan|gap|bridge|tension|tighten",
     "text": "<one sentence the user can act on>",
     "target_slide_ids": ["<id>", ...],
     "advisory": true,
     "suggested_edit": "<optional: the concrete edit text>"
    }
  ]
}

Rules you MUST follow:
- Every slide_id you reference MUST appear in the input outline.
- Never invent facts not present in the slides. If you don't have evidence
  for a claim, omit it. Honesty over completeness.
- Quote NOTHING from outside the input.
- "spine" is one sentence in plain English. Not a single word.
- If the deck has no clear through-line, say so in `spine` ("No through-line
  detected — the deck reads as disconnected") and leave recommendations to
  guide the user toward picking one.
- Recommendations should be ACTIONABLE — "tighten slide 3 to one message"
  beats "consider tightening".
- 3–6 recommendations is right for most decks; cap at 8."""


_USER_TEMPLATE = """\
Audience: {audience}
Mode: {mode}

Deck outline (JSON):
{outline_json}

Return your analysis as a single JSON object matching the schema in the
system prompt. No preamble, no markdown — JSON only."""


def _build_prompt(outline: list[dict], audience: str | None, mode: str | None) -> str:
    payload = []
    for s in outline:
        payload.append({
            "id":       s.get("id") or "",
            "title":    s.get("title") or "",
            "messages": s.get("messages") or [],
            "bumper":   s.get("bumper") or "",
        })
    return _USER_TEMPLATE.format(
        audience=audience or "general",
        mode=mode or "draft",
        outline_json=json.dumps(payload, ensure_ascii=False, indent=2),
    )


# ---- public entrypoint --------------------------------------------------

def analyze_narrative(
    outline: list[dict],
    *,
    audience: str | None = None,
    mode: str | None = None,
) -> Optional[dict]:
    """LLM-based narrative analysis. Returns structured dict or None."""
    if not outline:
        return None
    if not available():
        return None

    key = _outline_hash(outline, audience, mode)
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None:
        # mark cached results so the UI can show staleness if it wants
        return {**cached, "cached": True}

    prompt = _build_prompt(outline, audience, mode)
    try:
        raw = _llm_call(prompt)
    except Exception as e:
        # API errors, network errors, missing key — never crash callers
        import sys
        print(f"[narrative] LLM call failed, falling back: {e}", file=sys.stderr)
        return None

    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return None

    validated = _validate(parsed, outline)
    # report the backend that actually answered (may differ from _BACKEND
    # when within-tier fallback kicked in)
    used = _last_used or _BACKEND
    if used == "override":
        validated["model"]   = "stub"
        validated["backend"] = "override"
    elif used == "ollama":
        validated["model"]   = _OLLAMA_MODEL
        validated["backend"] = "ollama"
    else:
        validated["model"]   = _MODEL_NAME
        validated["backend"] = "anthropic"
    validated["configured_backend"] = _BACKEND   # for the UI: "you asked for X, got Y"
    validated["cached"] = False

    with _cache_lock:
        if len(_cache) >= _MAX_CACHE:
            try:
                _cache.pop(next(iter(_cache)))
            except StopIteration:
                pass
        _cache[key] = validated

    return validated


def reset_cache() -> None:
    with _cache_lock:
        _cache.clear()


# ---- JSON extraction + validation ---------------------------------------

def _extract_json(text: str) -> Optional[dict]:
    """LLMs sometimes wrap JSON in ```json fences or add preamble. Pull the
    first balanced JSON object out of the response."""
    if not text:
        return None
    # strip fenced blocks
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        candidate = fence.group(1)
    else:
        # find the first { and balanced match
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if esc:
                esc = False; continue
            if ch == "\\" and in_str:
                esc = True; continue
            if ch == '"':
                in_str = not in_str; continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end < 0:
            return None
        candidate = text[start:end]
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _validate(payload: dict, outline: list[dict]) -> dict:
    """Drop anything referencing a slide_id that isn't in the source
    (anti-fabrication). Normalize shape — every field gets a default."""
    valid_ids = {s.get("id") for s in outline if s.get("id")}

    def keep_ids(ids):
        if not isinstance(ids, list):
            return []
        return [i for i in ids if isinstance(i, str) and i in valid_ids]

    out: dict = {
        "spine":   str(payload.get("spine") or "").strip(),
        "arc":     str(payload.get("arc")   or "").strip(),
        "orphans": [],
        "gaps":    [],
        "tensions":[],
        "recommendations": [],
        "roles":   {},
    }

    # roles — only keep entries whose slide_id is in the source outline
    raw_roles = payload.get("roles") or {}
    if isinstance(raw_roles, dict):
        for sid, role in raw_roles.items():
            if isinstance(sid, str) and sid in valid_ids and isinstance(role, str):
                out["roles"][sid] = role.strip().lower()

    for o in payload.get("orphans") or []:
        sid = o.get("slide_id") if isinstance(o, dict) else None
        if isinstance(sid, str) and sid in valid_ids:
            out["orphans"].append({
                "slide_id": sid,
                "reason":   str(o.get("reason") or "")[:280],
            })

    for g in payload.get("gaps") or []:
        if not isinstance(g, dict): continue
        a, b = g.get("from"), g.get("to")
        if a in valid_ids and b in valid_ids:
            out["gaps"].append({
                "from": a, "to": b,
                "missing":           str(g.get("missing") or "")[:280],
                "bridge_suggestion": str(g.get("bridge_suggestion") or "")[:280],
            })

    for t in payload.get("tensions") or []:
        if not isinstance(t, dict): continue
        sids = keep_ids(t.get("slides"))
        if len(sids) >= 2:
            out["tensions"].append({
                "slides": sids,
                "issue":  str(t.get("issue") or "")[:280],
                "kind":   t.get("kind") if t.get("kind") in ("contradiction","redundancy","unsupported") else "unsupported",
            })

    for r in (payload.get("recommendations") or [])[:8]:
        if not isinstance(r, dict): continue
        targets = keep_ids(r.get("target_slide_ids"))
        kind = r.get("kind") if r.get("kind") in {"spine","orphan","gap","bridge","tension","tighten"} else "tighten"
        text = str(r.get("text") or "").strip()
        if not text:
            continue
        rec = {
            "id":               str(r.get("id") or f"r-{len(out['recommendations'])}"),
            "kind":             kind,
            "text":             text[:600],
            "target_slide_ids": targets,
            "advisory":         True,
        }
        if r.get("suggested_edit"):
            rec["suggested_edit"] = str(r["suggested_edit"])[:600]
        out["recommendations"].append(rec)

    return out


# ---- adapter: convert narrative analysis to the existing rec/threadmap shapes
#
# The storyboard "recommendations" rendering and the threadmap visualization
# already understand a certain shape. We adapt the narrative output to that
# shape so the existing UI keeps working — and gets visibly smarter.

def to_storyboard_recs(narr: dict) -> list[dict]:
    """Map narrative.recommendations -> storyboard's rec shape."""
    out: list[dict] = []

    if narr.get("spine"):
        out.append({
            "id":       "narr-spine",
            "kind":     "spine",
            "advisory": True,
            "text":     narr["spine"],
        })

    for o in narr.get("orphans") or []:
        out.append({
            "id":        f"narr-orphan-{o['slide_id']}",
            "kind":      "orphan",
            "advisory":  True,
            "text":      o["reason"],
            "slideIds":  [o["slide_id"]],
        })

    for g in narr.get("gaps") or []:
        text = g["missing"]
        if g.get("bridge_suggestion"):
            text += f"  Try: “{g['bridge_suggestion']}”"
        out.append({
            "id":        f"narr-gap-{g['from']}-{g['to']}",
            "kind":      "gap",
            "advisory":  True,
            "text":      text,
            "slideIds":  [g["from"], g["to"]],
        })

    for t in narr.get("tensions") or []:
        out.append({
            "id":        f"narr-tension-{'-'.join(t['slides'])}",
            "kind":      "tension",   # new kind — UI will render generically if unknown
            "advisory":  True,
            "text":      t["issue"],
            "slideIds":  t["slides"],
        })

    # surface any extra recs (tighten etc.) the LLM produced
    seen_ids = {r["id"] for r in out}
    for r in narr.get("recommendations") or []:
        if r["id"] in seen_ids:
            continue
        out.append({
            "id":        r["id"],
            "kind":      r["kind"],
            "advisory":  True,
            "text":      r["text"],
            "slideIds":  r.get("target_slide_ids") or [],
        })
    return out


def to_threadmap_view(narr: dict, outline: list[dict]) -> dict:
    """Build a threadmap-compatible view from the narrative analysis.

    Edges = pairs of slides that the LLM links via shared inclusion in a
    tension/gap/recommendation OR via the same arc segment.
    Spine   = narr.spine (natural-language string, not a token).
    Orphans = narr.orphans (with reasons attached for the UI to surface).
    Gaps    = narr.gaps.
    Ribbons = the recommendations as named threads — each rec is a thread
              whose slides are its target_slide_ids.
    """
    nodes = []
    for i, s in enumerate(outline):
        nodes.append({
            "id":             s.get("id") or f"s{i}",
            "index":          i,
            "title":          (s.get("title") or "").strip() or f"Slide {i+1}",
            "concept_count":  0,
        })
    by_id = {n["id"]: n for n in nodes}

    # build edges by pair-union: any group of >=2 slide ids the LLM bound
    # together (via tension, gap, or recommendation) becomes pairwise edges.
    edges: dict[tuple[str, str], dict] = {}
    def add_link(a: str, b: str, label: str):
        if a == b: return
        if a not in by_id or b not in by_id: return
        key = (a, b) if a < b else (b, a)
        if key in edges:
            edges[key]["shared"].append(label)
            edges[key]["weight"] += 1
        else:
            edges[key] = {
                "from":     key[0],
                "to":       key[1],
                "weight":   1,
                "shared":   [label],
                "adjacent": (abs(by_id[a]["index"] - by_id[b]["index"]) == 1),
            }
    for r in narr.get("recommendations") or []:
        targets = r.get("target_slide_ids") or []
        for i in range(len(targets)):
            for j in range(i + 1, len(targets)):
                add_link(targets[i], targets[j], r["text"][:80])
    for t in narr.get("tensions") or []:
        sids = t.get("slides") or []
        for i in range(len(sids)):
            for j in range(i + 1, len(sids)):
                add_link(sids[i], sids[j], f"tension: {t['issue'][:60]}")

    edge_list = list(edges.values())

    orphan_ids = [o["slide_id"] for o in (narr.get("orphans") or [])
                  if o["slide_id"] in by_id]
    orphan_reasons = {o["slide_id"]: o["reason"]
                      for o in (narr.get("orphans") or [])
                      if o["slide_id"] in by_id}

    spine = None
    if narr.get("spine"):
        # spine "slides" = every slide not flagged as orphan
        spine_slides = [n["id"] for n in nodes if n["id"] not in set(orphan_ids)]
        spine = {
            "word":   narr["spine"],   # full sentence — the UI label changed accordingly
            "count":  len(spine_slides),
            "slides": spine_slides,
        }

    gaps = []
    gap_details = {}
    for g in narr.get("gaps") or []:
        if g["from"] in by_id and g["to"] in by_id:
            gaps.append({"from": g["from"], "to": g["to"]})
            gap_details[(g["from"], g["to"])] = g

    # ribbons — each recommendation is a "thread" of the slides it spans
    ribbons: list[dict] = []
    for r in (narr.get("recommendations") or [])[:8]:
        sids = [s for s in (r.get("target_slide_ids") or []) if s in by_id]
        if len(sids) < 2: continue
        indices = sorted(by_id[s]["index"] for s in sids)
        ribbons.append({
            "token":    r["text"][:60],
            "slides":   indices,
            "weight":   float(len(indices)),
            "broken":   (max(indices) - min(indices) + 1) != len(indices),
            "is_spine": r.get("kind") == "spine",
            "kind":     r.get("kind"),
        })

    n = len(outline)
    orphan_rate = (len(orphan_ids) / n) if n else 0
    gap_rate = (len(gaps) / max(1, n - 1)) if n else 0
    spine_penalty = 0.0 if spine else 0.35
    messiness = round(min(1.0, 0.45 * orphan_rate + 0.35 * gap_rate + spine_penalty), 3)

    return {
        "graph": {
            "nodes": nodes,
            "edges": edge_list,
            "orphans": orphan_ids,
            "spine": spine,
            "gaps": gaps,
            "orphan_reasons": orphan_reasons,
            "gap_details":    {f"{k[0]}|{k[1]}": v for k, v in gap_details.items()},
            "tensions":       narr.get("tensions") or [],
        },
        "ribbons": ribbons,
        "stats": {
            "slides":     n,
            "orphans":    len(orphan_ids),
            "gaps":       len(gaps),
            "edges":      len(edge_list),
            "ribbons":    len(ribbons),
            "spine_word": (spine["word"] if spine else None),
            "messiness":  messiness,
        },
    }
