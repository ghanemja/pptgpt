"""
Semantic layer — sentence-transformer embeddings, lazily loaded and cached.

Architectural note: this is the *meaning* layer. It lives next to parse.py
and threadmap.py at the content layer, never inside the engine or renderer.
Embeddings carry no geometry, no color, no point sizes.

Design choices:
- The model (all-MiniLM-L6-v2, ~80MB) is loaded LAZILY on first use, so the
  server boots in <1s instead of paying the model-load tax up front.
- All embeddings are normalized at encode time, so similarity is just a dot
  product — fast and stable.
- A content-hashed in-process cache means re-edits don't re-embed unchanged
  slides on every keystroke.
- When sentence-transformers isn't installed, every public function returns
  `None` and callers fall back to the lexical path. We never crash.
- The model is NEVER downloaded at runtime. `scripts/fetch_models.py` saves it
  under models/ once; here it loads from that folder with local_files_only and
  the Hugging Face libraries forced offline. No folder → lexical fallback.

Public API:
    available()                    -> bool   — is the embedding stack usable?
    embed_text(text)               -> ndarray | None
    embed_slide(slide_dict)        -> ndarray | None
    embed_outline(outline)         -> list[ndarray] | None
    cosine_sim(a, b)               -> float                 (a, b already unit)
    pairwise_sim(slides)           -> 2d list[list[float]]  (None on failure)
    extract_candidate_phrases(s)   -> list[str]
"""
from __future__ import annotations
import hashlib
import os
import re
import sys
import threading
from pathlib import Path
from typing import Iterable, Optional


_MODEL_NAME = "all-MiniLM-L6-v2"
MODEL_REPO = f"sentence-transformers/{_MODEL_NAME}"
# Where scripts/fetch_models.py puts it. git-ignored.
MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / _MODEL_NAME
_model = None
_model_lock = threading.Lock()
_model_failed = False  # remembered so we don't retry on every call

_cache: dict[str, "object"] = {}  # content-hash -> ndarray
_MAX_CACHE = 4096


def _get_model():
    """Lazy-load the sentence-transformer model. Returns None if unavailable."""
    global _model, _model_failed
    if _model is not None:
        return _model
    if _model_failed:
        return None
    with _model_lock:
        if _model is not None:
            return _model
        if _model_failed:
            return None
        if not model_present():
            _model_failed = True
            _notice(f"no model at {MODEL_DIR} (run: python scripts/fetch_models.py)")
            return None
        # Forced, not defaulted: whatever the shell says, this process does
        # not reach the model hub. Set before the HF libraries are imported,
        # which is when they read it.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            _model = SentenceTransformer(str(MODEL_DIR), local_files_only=True)
        except Exception as e:
            _model_failed = True
            _notice(str(e))
            return None
        return _model


def _notice(why: str) -> None:
    """One terse log line so operators know, printed once per process."""
    try:
        print(f"[semantics] model unavailable, falling back to lexical: {why}",
              file=sys.stderr)
    except Exception:
        pass


def model_present() -> bool:
    """Has scripts/fetch_models.py put the model on disk?"""
    return (MODEL_DIR / "modules.json").is_file() and any(
        (MODEL_DIR / f).is_file() for f in ("model.safetensors", "pytorch_model.bin"))


def reset_model() -> None:
    """Forget the loaded (or failed) model so the next call tries again."""
    global _model, _model_failed
    with _model_lock:
        _model, _model_failed = None, False


def available() -> bool:
    """Is the embedding stack ready (or loadable)?"""
    return _get_model() is not None


def _hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def embed_text(text: str):
    """Return a 1D unit vector for `text`. None if embeddings unavailable."""
    if not text or not text.strip():
        text = "empty"
    m = _get_model()
    if m is None:
        return None
    h = _hash(text)
    cached = _cache.get(h)
    if cached is not None:
        return cached
    try:
        vec = m.encode(text, normalize_embeddings=True, show_progress_bar=False)
    except Exception:
        return None
    # crude LRU: drop the oldest insert if the cache is full
    if len(_cache) >= _MAX_CACHE:
        try:
            _cache.pop(next(iter(_cache)))
        except StopIteration:
            pass
    _cache[h] = vec
    return vec


def _slide_text(slide: dict) -> str:
    """Concatenate the parts of a storyboard outline slide that carry meaning."""
    parts = [slide.get("title", "") or ""]
    parts.extend(slide.get("messages") or [])
    if slide.get("bumper"): parts.append(slide["bumper"])
    return " · ".join(p for p in parts if p)


def embed_slide(slide: dict):
    """Embed one storyboard slide. None if embeddings unavailable."""
    return embed_text(_slide_text(slide))


def embed_outline(outline: list[dict]):
    """Embed each slide in an outline. None if embeddings unavailable."""
    if not outline:
        return []
    if not available():
        return None
    out = []
    for s in outline:
        v = embed_slide(s)
        if v is None:
            return None
        out.append(v)
    return out


def cosine_sim(a, b) -> float:
    """Cosine similarity. Assumes both vectors are already L2-normalized."""
    import numpy as np
    return float(np.dot(a, b))


def pairwise_sim(slide_vecs) -> Optional[list[list[float]]]:
    """N×N similarity matrix as nested lists. None if any vec is None."""
    if not slide_vecs:
        return []
    if any(v is None for v in slide_vecs):
        return None
    import numpy as np
    M = np.stack(slide_vecs)
    sim = (M @ M.T).tolist()
    return sim


# ---- phrase extraction (for ribbon labels) ------------------------------

# We don't have a parser, but a tight regex catches most useful candidates:
# 1-3 word phrases, ending in a noun-y token, no stop-word starts.
_STOPS = {
    "the","a","an","and","or","of","to","for","in","on","at","is","it","this",
    "that","with","from","as","by","be","are","was","were","but","so","if",
    "we","our","you","your","their","they","will","can","have","has","had",
    "about","into","than","then","what","which","who","one","more","less",
    "most","any","some","no","up","down","off","out","over","under","across",
}


def extract_candidate_phrases(text: str, max_phrases: int = 12) -> list[str]:
    """Extract 1-3 word noun-ish phrases. Cheap and lossy on purpose."""
    if not text:
        return []
    # split into rough sentences/lines first so phrases don't cross boundaries
    chunks = re.split(r"[.\n,;:]+", text.lower())
    out: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        words = [w for w in re.findall(r"[a-z][a-z0-9\-]+", chunk) if len(w) >= 3]
        # build 1-, 2-, 3-grams, dropping any that start/end on a stopword
        for n in (3, 2, 1):
            for i in range(len(words) - n + 1):
                ng = words[i:i+n]
                if ng[0] in _STOPS or ng[-1] in _STOPS:
                    continue
                phrase = " ".join(ng)
                if phrase in seen:
                    continue
                seen.add(phrase)
                out.append(phrase)
                if len(out) >= max_phrases:
                    return out
    return out


# ---- cache controls (mostly for tests) ----------------------------------

def cache_size() -> int:
    return len(_cache)


def reset_cache() -> None:
    _cache.clear()
