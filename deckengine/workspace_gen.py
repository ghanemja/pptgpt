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
import os
import re
from typing import Any, Optional

from . import narrative

# How many bullets a slide gets is the input's call, not the template's.
# The template used to show three slots ("bullets":["","",""]), which cued
# three on every slide: real two-point slides got a filler third, and
# four-point ones lost one. The examples now show two items so no count is
# implied, and this line states the rule. Kept OUTSIDE the JSON so a small
# model does not copy it into a bullet.
_BULLET_RULE = ("bullets: 0 to 4 items, one per real point in the input. "
                "Never pad to reach three and never drop a real point.")

_WORKSPACE_SYSTEM = (
    "You are pptgpt, a slide-drafting assistant. Follow the user's formatting "
    "instructions exactly: output exactly what is requested, JSON only, no "
    "prose, no code fences."
)

_AUDIENCE_TONE = {
    "exec": "numbers-forward, sparse, decision-oriented; the hero number leads and a decision anchors the lower right",
    "customer": "narrative-first, warmer, a little more visual, ends with a single ask",
    "conf": "one idea, big typography, takeaway-first, minimal supporting text",
    "standup": (
        "dense and practical, action items stated plainly; name an owner only when "
        "the input, the user or the source material names one, otherwise write [owner]"
    ),
}


# The slide voice: a short block derived from the humanplease writing skill
# (see the header of humanplease_slides.md). Read once from the file; only
# the text after its HTML-comment header reaches the model.
_VOICE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "humanplease_slides.md")
_voice_cache: Optional[str] = None


def voice_block() -> str:
    """The slide-voice rules sent with every prompt ("" if the file is gone)."""
    global _voice_cache
    if _voice_cache is None:
        try:
            with open(_VOICE_PATH, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            raw = ""
        _voice_cache = re.sub(r"<!--.*?-->", "", raw, flags=re.S).strip()
    return _voice_cache


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
                   current: Optional[dict], file_names: list[str] | None,
                   house: str = "", voice: bool = True) -> str:
    tone = _tone(audience)
    # The company's conventions and the slide voice ride along with the file
    # note, so every feature's prompt carries them without each one being
    # rewritten. House style first: a company's own rule wins a conflict.
    style = (f"\n\nFollow this company's house style:\n{house}" if house else "")
    vb = voice_block() if voice else ""
    style += (f"\n\nHow to write the text:\n{vb}" if vb else "")
    note = _file_note(file_names) + style
    text = prompt or ""

    if feature == "condense":
        return (
            "You are pptgpt. Condense the pasted deck into its 3-5 load-bearing slides.\n"
            'Return ONLY a JSON array (no prose, no code fences). Each item:\n'
            '{"kind":"text","eyebrow":"ALL CAPS <=4 words","title":"takeaway-first, 4-8 words",'
            '"metric":"hero number or null","metricSub":"<=5 words or null",'
            '"bullets":["<=8 words","<=8 words"],"takeaway":"<=12 words"}\n'
            f"{_BULLET_RULE}\n"
            f"Slides should feel: {tone}. No fabricated numbers.{note}\n\nDeck:\n\"\"\"{text}\"\"\""
        )
    if feature == "refine" and current:
        cur = {
            "title": current.get("title"), "metric": current.get("metric"),
            "bullets": current.get("bullets"), "takeaway": current.get("takeaway"),
        }
        return (
            "You are pptgpt. Rework the current slide keeping its bones: fix the buried "
            "point, sharpen the title, put the takeaway where it lands. Apply the user's note.\n"
            'Return ONLY a JSON object (no prose/fences):\n'
            '{"kind":"text|chart|plot","eyebrow":"ALL CAPS","title":"","metric":"or null",'
            '"metricSub":"or null","bullets":["",""],"takeaway":""}\n'
            f"{_BULLET_RULE}\n"
            f"Audience feel: {tone}.{style}\n"
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
        '"bullets":["<=9 words","<=9 words"],"takeaway":"<=14 words conversational"}\n'
        f"{_BULLET_RULE}\n"
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
    house: str = "",
    voice: bool = True,
) -> Optional[dict] | Optional[list]:
    """Generate one slide (dict) or, for `condense`, a list of slides.
    Returns None on any failure — callers must degrade gracefully.
    `voice=False` drops the humanplease block (for A/B comparison only)."""
    if not narrative.available():
        return None

    user_prompt = _build_prompt(feature, prompt, audience, current, file_names, house, voice)
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
            out.append(_drop_blank_bullets({"kind": item.get("kind") or "text", "palette": palette, **item}))
        return out or None

    if not isinstance(parsed, dict):
        return None
    if not parsed.get("title") and not parsed.get("bullets"):
        return None
    return _drop_blank_bullets({"kind": parsed.get("kind") or "text", "palette": palette, **parsed})


_TEXT_FIELDS = ("eyebrow", "title", "metric", "metricSub", "takeaway")
# What a small model sometimes leaves stuck to the end of a JSON string: the
# closing quote/brace of the object it was writing, markdown bold, a fence.
_TRAILING_JUNK = re.compile(r"""(?:```.*|[\s"\u201c\u201d}*`])+$""", re.S)


def _tidy(text: str) -> str:
    out = _TRAILING_JUNK.sub("", text).strip()
    # Keep a quote mark that closes one opened inside the text.
    if out.count("\u201c") > out.count("\u201d"):
        out += "\u201d"
    return out


def _drop_blank_bullets(slide: dict) -> dict:
    """Tidy what the model wrote: drop empty bullets (the voice rules let it
    leave them empty rather than pad to three, and an empty string would
    still draw as a dash) and strip JSON debris off the end of text fields."""
    b = slide.get("bullets")
    if isinstance(b, list):
        slide["bullets"] = [_tidy(x) for x in b if isinstance(x, str) and x.strip()]
        slide["bullets"] = [x for x in slide["bullets"] if x]
    for k in _TEXT_FIELDS:
        if isinstance(slide.get(k), str):
            slide[k] = _tidy(slide[k])
    return slide
