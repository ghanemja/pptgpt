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
        "dense and practical, action items stated plainly; name an author only when "
        "the input, the user or the source material names one, otherwise write [author]"
    ),
}


# The slide voice: a short block derived from the humanplease writing skill
# (see the header of humanplease_slides.md). The file holds two forms: the
# full one, and after a "short form" comment a cut-down one for small local
# models, which follow long rule lists badly (on gemma3:4b the full form
# raised failures from 2/16 to 7/16). Only the text outside HTML comments
# reaches the model.
_VOICE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "humanplease_slides.md")
_SHORT_MARK = "<!-- short form"
_voice_cache: dict[str, str] = {}
# Local models at or under this many billion parameters get the short form.
_SMALL_MODEL_B = 12.0


def voice_block(form: str = "full") -> str:
    """The slide-voice rules for `form` ("full" | "short"); "" if the file is gone."""
    if form not in _voice_cache:
        try:
            with open(_VOICE_PATH, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            raw = ""
        full, _, short = raw.partition(_SHORT_MARK)
        part = short if form == "short" else full
        if form == "short":
            part = part.split("-->", 1)[1] if "-->" in part else ""
        _voice_cache[form] = re.sub(r"<!--.*?-->", "", part, flags=re.S).strip()
    return _voice_cache[form]


def model_size_b(name: str) -> Optional[float]:
    """Parameter count in billions from a model tag ("gemma3:4b" -> 4,
    "gemma4:e4b" -> 4, "qwen2.5:14b-instruct" -> 14); None if it names none."""
    m = re.search(r"(?:^|[:\-_/e])(\d+(?:\.\d+)?)b(?![a-z0-9])", (name or "").lower())
    return float(m.group(1)) if m else None


def voice_form(voice: "bool | str" = True) -> str:
    """Which voice form a prompt gets: "full", "short" or "off".

    `voice` may name the form outright; True means pick by model:
    DECKENGINE_VOICE=full|short|off wins, then a local model (Ollama, or an
    OpenAI-compatible endpoint) at or under _SMALL_MODEL_B gets "short", as
    does a local one whose tag names no size. Hosted Anthropic gets "full"."""
    if voice is False:
        return "off"
    if isinstance(voice, str) and voice in ("full", "short", "off"):
        return voice
    env = os.environ.get("DECKENGINE_VOICE", "").strip().lower()
    if env in ("full", "short", "off"):
        return env
    info = narrative.backend_info()
    if info.get("backend") in ("ollama", "openai-compatible"):
        size = model_size_b(str(info.get("model", "")))
        return "short" if size is None or size <= _SMALL_MODEL_B else "full"
    return "full"


def _tone(audience: Optional[str]) -> str:
    return _AUDIENCE_TONE.get(audience or "exec", _AUDIENCE_TONE["exec"])


def _file_note(file_names: list[str] | None) -> str:
    if not file_names:
        return ""
    return (
        f"\nThe user attached {len(file_names)} file(s): {', '.join(file_names)}. "
        "Use the names as a hint for the material type; do not fabricate contents."
    )


# The output contract. Every string slot in a JSON template is "" and every
# rule about a field is stated OUTSIDE the JSON, one line per field. The old
# templates put the rule in the slot ("eyebrow":"ALL CAPS context <=5
# words"), and gemma3:4b copied it onto the slide verbatim. An empty slot
# has nothing to copy. No casing rule either: SlideCard uppercases the
# eyebrow itself, so asking the model for capitals only fought the voice.
_TEXT_SLIDE_JSON = ('{"kind":"text","eyebrow":"","title":"","metric":"","metricSub":"",'
                    '"bullets":["",""],"takeaway":""}')
_TEXT_FIELD_RULES = (
    "- eyebrow: the topic in 2 to 5 words\n"
    "- title: the main point as a headline, {title_words} words, sentence case\n"
    "- metric: the input's most important number exactly as written, or null\n"
    "- metricSub: what that number measures in up to 6 words, or null\n"
    "- {bullet_rule} Each bullet up to 9 words.\n"
    "- takeaway: one plain sentence of up to 14 words"
)
_CONTRACT_TAIL = ('Fill every "" from the input. Use straight double quotes (") '
                  "in the JSON, and nothing outside it.")


def _text_contract(title_words: str = "4 to 9", array: bool = False,
                   keep_kind: bool = False) -> str:
    tpl = _TEXT_SLIDE_JSON
    rules = _TEXT_FIELD_RULES.format(title_words=title_words, bullet_rule=_BULLET_RULE)
    if keep_kind:   # refine: a chart or plot slide stays one
        tpl = tpl.replace('"kind":"text"', '"kind":""')
        rules = '- kind: the current slide\'s kind, one of text, chart, plot\n' + rules
    shape = (f"a JSON array of 3 to 5 objects, each shaped like:\n{tpl}"
             if array else f"ONE JSON object, exactly:\n{tpl}")
    return f"Return {shape}\nFields:\n{rules}\n{_CONTRACT_TAIL}"


def _build_prompt(feature: str, prompt: str, audience: Optional[str],
                   current: Optional[dict], file_names: list[str] | None,
                   house: str = "", voice: "bool | str" = True) -> str:
    tone = _tone(audience)
    # Order: the task, then how to write (house style first, so a company's
    # own rule wins a conflict, then the voice), then the output contract
    # last before the input, so the JSON shape is the freshest instruction
    # a small model has read when it starts writing.
    style = (f"\n\nFollow this company's house style:\n{house}" if house else "")
    form = voice_form(voice)
    vb = voice_block(form) if form != "off" else ""
    style += (f"\n\nHow to write the text:\n{vb}" if vb else "")
    files = _file_note(file_names)
    text = prompt or ""

    if feature == "condense":
        return (
            "You are pptgpt. Condense the pasted deck into its 3-5 load-bearing slides."
            f"{files}{style}\n\n"
            f"Slides should feel: {tone}. No fabricated numbers.\n\n"
            f"{_text_contract('4 to 8', array=True)}\n\nDeck:\n\"\"\"{text}\"\"\""
        )
    if feature == "refine" and current:
        cur = {
            "kind": current.get("kind") or "text",
            "title": current.get("title"), "metric": current.get("metric"),
            "bullets": current.get("bullets"), "takeaway": current.get("takeaway"),
        }
        return (
            "You are pptgpt. Rework the current slide keeping its bones: fix the buried "
            "point, sharpen the title, put the takeaway where it lands. Apply the user's note."
            f"{style}\n\n"
            f"Audience feel: {tone}.\n\n"
            f"{_text_contract(keep_kind=True)}\n\n"
            f"Current slide JSON: {json.dumps(cur, ensure_ascii=False)}\n"
            f'User note: """{text or "tighten it"}"""'
        )
    if feature == "data":
        return (
            "You are pptgpt. Turn the input data into ONE slide that is a chart or a plot."
            f"{files}{style}\n\n"
            "Return ONE JSON object, exactly one of these two shapes:\n"
            '{"kind":"chart","eyebrow":"","title":"","takeaway":"",'
            '"chart":{"title":"","data":[{"label":"","value":0,"hi":false}]}}\n'
            '{"kind":"plot","eyebrow":"","title":"","takeaway":"",'
            '"plot":{"fn":"damped","eq":"","params":{}}}\n'
            "Fields:\n"
            "- kind: \"plot\" for a formula or continuous function, else \"chart\"\n"
            "- eyebrow: the topic in 2 to 5 words\n"
            "- title: the main point as a headline, 4 to 8 words, sentence case\n"
            "- takeaway: one plain sentence of up to 14 words\n"
            "- chart.title: the axis or unit label; chart.data: one item per value in the "
            "input, with hi:true on the most important one\n"
            "- plot.fn: one of damped, sine, gaussian\n"
            f"Do not invent numbers not present. {_CONTRACT_TAIL}\n\n"
            f'Input:\n"""{text}"""'
        )
    return (
        "You are pptgpt. Draft ONE polished TEXT slide from the input (no charts)."
        f"{files}{style}\n\n"
        f"Slide should feel: {tone}. No hedging; don't invent numbers.\n\n"
        f"{_text_contract()}\n\n"
        f'Input:\n"""{text}"""'
    )


# A curly quote where a JSON string should close: `...alert.”}` or
# `...alert.”,"next"`. JSON mode accepts ” as string content, so the
# string never closes and a small model writes on to its token cap.
_CURLY_CLOSE = re.compile(r'[\u201c\u201d](\s*(?:[,}\]]|$))')
_DEBRIS_IN_STRING = re.compile(r'\u201d\s*[,}\]]')


def _has_debris(v: Any) -> bool:
    if isinstance(v, str):
        return bool(_DEBRIS_IN_STRING.search(v))
    if isinstance(v, dict):
        return any(_has_debris(x) for x in v.values())
    if isinstance(v, list):
        return any(_has_debris(x) for x in v)
    return False


def _extract_json_value(text: str) -> Any:
    """Pull the first balanced JSON object OR array out of a response,
    tolerating ```json fences. Unlike `narrative._extract_json`, this also
    accepts a top-level array (needed for `condense`).

    If the strict read fails, or succeeds only by swallowing a curly-quote
    close and everything after it into one string, the curly close is
    straightened and the read retried."""
    strict = _extract_json_strict(text)
    if strict is not None and not _has_debris(strict):
        return strict
    if text and ("\u201d" in text or "\u201c" in text):
        repaired = _extract_json_strict(_CURLY_CLOSE.sub(r'"\1', text))
        if repaired is not None:
            return repaired
    return strict


def _extract_json_strict(text: str) -> Any:
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


# Reply budgets. A slide is ~150 tokens, condense's 3-5 are ~800. The cap
# turns a runaway reply into a fast, repairable one instead of a 180 s
# timeout (see `_CURLY_CLOSE`).
_MAX_TOKENS = {"create": 600, "refine": 600, "data": 800, "condense": 1600}


def generate_slide(
    *,
    feature: str,
    prompt: str,
    audience: Optional[str] = None,
    current: Optional[dict] = None,
    palette: Optional[str] = None,
    file_names: list[str] | None = None,
    house: str = "",
    voice: "bool | str" = True,
) -> Optional[dict] | Optional[list]:
    """Generate one slide (dict) or, for `condense`, a list of slides.
    Returns None on any failure — callers must degrade gracefully.
    `voice` True picks the voice form by model (see `voice_form`); "full",
    "short" or False/"off" force one (False is for A/B comparison only)."""
    if not narrative.available():
        return None

    user_prompt = _build_prompt(feature, prompt, audience, current, file_names, house, voice)
    try:
        raw = narrative.call(user_prompt, _WORKSPACE_SYSTEM, max_tokens=_MAX_TOKENS.get(feature, 600))
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
