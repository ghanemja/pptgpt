"""
Workspace slide generation — the real backend for the pptgpt workspace UI's
Create / Data / Refine / Condense composer.

Ports the four per-feature system prompts that `ws-slide.jsx`'s client-side
`aiGenerate()` sends to `window.claude.complete` (browser-only, absent
outside the design tool) to a real LLM call via `narrative.call`, which
already carries the Ollama/Gemma/Anthropic swap. Content only — no x/y/w/h,
no colors; the returned dict mirrors ws-slide's own slide JSON shape, which
the frontend's fixed-template `SlideCard` renders.

Returns `None` on any failure (model unavailable, bad JSON, empty response)
so the caller falls back to the client's canned generator — same posture as
`narrative.analyze_narrative`.
"""
from __future__ import annotations
import json
from typing import Any, Optional

from . import narrative

_WORKSPACE_SYSTEM = (
    "You are pptgpt, a slide-drafting assistant. Follow the user's formatting "
    "instructions exactly — output exactly what is requested, JSON only, no "
    "prose, no code fences."
)

_AUDIENCE_TONE = {
    "exec": "numbers-forward, sparse, decision-oriented; the hero number leads and a decision anchors the lower right",
    "customer": "narrative-first, warmer, a little more visual, ends with a single ask",
    "conf": "one idea, big typography, takeaway-first, minimal supporting text",
    "standup": "dense and practical, action items phrased with owners in mind",
}


def _tone(audience: Optional[str]) -> str:
    return _AUDIENCE_TONE.get(audience or "exec", _AUDIENCE_TONE["exec"])


def _file_note(file_names: list[str] | None) -> str:
    if not file_names:
        return ""
    return (
        f"\nThe user attached {len(file_names)} file(s): {', '.join(file_names)}. "
        "Use the names as a hint for the material type; do not fabricate contents."
    )


def _build_prompt(feature: str, prompt: str, audience: Optional[str],
                   current: Optional[dict], file_names: list[str] | None) -> str:
    tone = _tone(audience)
    note = _file_note(file_names)
    text = prompt or ""

    if feature == "condense":
        return (
            "You are pptgpt. Condense the pasted deck into its 3-5 load-bearing slides.\n"
            'Return ONLY a JSON array (no prose, no code fences). Each item:\n'
            '{"kind":"text","eyebrow":"ALL CAPS <=4 words","title":"takeaway-first, 4-8 words",'
            '"metric":"hero number or null","metricSub":"<=5 words or null",'
            '"bullets":["<=8 words","",""],"takeaway":"<=12 words"}\n'
            f"Slides should feel: {tone}. No fabricated numbers.{note}\n\nDeck:\n\"\"\"{text}\"\"\""
        )
    if feature == "refine" and current:
        cur = {
            "title": current.get("title"), "metric": current.get("metric"),
            "bullets": current.get("bullets"), "takeaway": current.get("takeaway"),
        }
        return (
            "You are pptgpt. Rework the current slide keeping its bones — fix the buried "
            "point, sharpen the title, put the takeaway where it lands. Apply the user's note.\n"
            'Return ONLY a JSON object (no prose/fences):\n'
            '{"kind":"text|chart|plot","eyebrow":"ALL CAPS","title":"","metric":"or null",'
            '"metricSub":"or null","bullets":["",""],"takeaway":""}\n'
            f"Audience feel: {tone}.\n"
            f"Current slide JSON: {json.dumps(cur, ensure_ascii=False)}\n"
            f'User note: """{text or "tighten it"}"""'
        )
    if feature == "data":
        return (
            "You are pptgpt. Turn the input data into ONE slide that is a chart or a plot.\n"
            'Return ONLY a JSON object (no prose, no code fences):\n'
            '{"kind":"chart|plot","eyebrow":"ALL CAPS <=4 words","title":"takeaway-first 4-8 words",'
            '"takeaway":"<=14 words","chart":{"title":"axis/unit label",'
            '"data":[{"label":"","value":0,"hi":false}]}|null,'
            '"plot":{"fn":"damped|sine|gaussian","eq":"","params":{}}|null}\n'
            "Use \"plot\" for a formula/continuous function, else \"chart\". Highlight the most "
            f"important bar with hi:true. Do not invent numbers not present.{note}\n\n"
            f'Input:\n"""{text}"""'
        )
    return (
        "You are pptgpt. Draft ONE polished TEXT slide from the input (no charts).\n"
        'Return ONLY a JSON object (no prose, no code fences):\n'
        '{"kind":"text","eyebrow":"ALL CAPS context <=5 words","title":"takeaway-first headline 4-9 words",'
        '"metric":"hero number/phrase or null","metricSub":"<=6 words or null",'
        '"bullets":["<=9 words","",""],"takeaway":"<=14 words conversational"}\n'
        f"Slide should feel: {tone}. No hedging; don't invent numbers.{note}\n\n"
        f'Input:\n"""{text}"""'
    )


def _extract_json_value(text: str) -> Any:
    """Pull the first balanced JSON object OR array out of a response,
    tolerating ```json fences. Unlike `narrative._extract_json`, this also
    accepts a top-level array (needed for `condense`)."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[: -3]
        t = t.strip()

    start = None
    for i, ch in enumerate(t):
        if ch in "{[":
            start = i
            break
    if start is None:
        return None
    open_ch = t[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    end = -1
    for i in range(start, len(t)):
        ch = t[i]
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return None
    try:
        return json.loads(t[start:end])
    except Exception:
        return None


def generate_slide(
    *,
    feature: str,
    prompt: str,
    audience: Optional[str] = None,
    current: Optional[dict] = None,
    palette: Optional[str] = None,
    file_names: list[str] | None = None,
) -> Optional[dict] | Optional[list]:
    """Generate one slide (dict) or, for `condense`, a list of slides.
    Returns None on any failure — callers must degrade gracefully."""
    if not narrative.available():
        return None

    user_prompt = _build_prompt(feature, prompt, audience, current, file_names)
    try:
        raw = narrative.call(user_prompt, _WORKSPACE_SYSTEM)
    except Exception as e:
        import sys as _sys
        print(f"[workspace_gen] LLM call failed, falling back: {e}", file=_sys.stderr)
        return None

    parsed = _extract_json_value(raw)

    if feature == "condense":
        if not isinstance(parsed, list) or not parsed:
            return None
        out = []
        for item in parsed[:5]:
            if not isinstance(item, dict):
                continue
            out.append({"kind": item.get("kind") or "text", "palette": palette, **item})
        return out or None

    if not isinstance(parsed, dict):
        return None
    if not parsed.get("title") and not parsed.get("bullets"):
        return None
    return {"kind": parsed.get("kind") or "text", "palette": palette, **parsed}
