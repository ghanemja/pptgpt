"""
Storyboard extraction + adversarial critique.

Python port of `extractStoryboard` and `generateCritique` from
`frontend/mockBackend.js`. Same shapes, same heuristics.
"""
from __future__ import annotations
import re
import secrets
from typing import Any


# ---- extractStoryboard ---------------------------------------------------

def _split_on_headings(text: str) -> list[str]:
    lines = text.split("\n")
    out: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            out.append("\n".join(buf).strip())
            buf.clear()

    def is_heading(line: str) -> bool:
        t = line.strip()
        if not t:
            return False
        if len(t) > 80:
            return False
        if re.search(r"[.!?,;:]$", t):
            return False
        if re.match(r"^(?:\d+[\.\)]|section|slide|chapter|part)\s", t, re.I):
            return True
        words = [w for w in re.split(r"\s+", t) if w]
        if not words:
            return False
        cap = sum(1 for w in words if re.match(r"^[A-Z]", w))
        return (cap / len(words) >= 0.6) and (2 <= len(words) <= 10)

    for line in lines:
        if is_heading(line) and buf:
            flush()
        if line.strip():
            buf.append(line)
    flush()

    if len(out) > 8:
        recombined: list[str] = []
        group: list[str] = []
        step = max(1, (len(out) + 4) // 5)
        for c in out:
            group.append(c)
            if len(group) >= step:
                recombined.append("\n\n".join(group))
                group = []
        if group:
            recombined.append("\n\n".join(group))
        return recombined
    if not out:
        return [text]
    return out


def _text_to_slide(chunk: str, n: int) -> dict:
    lines = [l.strip() for l in chunk.split("\n") if l.strip()]
    title = lines[0] if lines else "Untitled slide"
    body = lines[1:]
    sentences = []
    for l in body:
        sentences += [s.strip() for s in re.split(r"(?<=[.!?])\s+", l) if s.strip() and len(s.strip()) >= 12]
    all_msgs = sentences if sentences else body
    messages = list(all_msgs[:3])
    while len(messages) < 3:
        messages.append("")

    bumper = ""
    if len(all_msgs) > 3:
        bumper = all_msgs[-1]
    elif len(all_msgs) == 3 and len(all_msgs[2]) < 60:
        bumper = all_msgs[2]

    def trunc(s: str, lim: int) -> str:
        return s[: lim - 1] + "…" if len(s) > lim else s

    return {
        "id": f"s{n}-{secrets.token_hex(2)}",
        "title": trunc(title, 100),
        "messages": [trunc(m, 180) for m in messages],
        "bumper": trunc(bumper, 140),
    }


def _empty_slide(n: int) -> dict:
    return {"id": f"s{n}-{secrets.token_hex(2)}", "title": "", "messages": ["", "", ""], "bumper": ""}


def _slides_order_of(a: dict, b: dict, chunks: list[str]) -> int:
    def idx(s):
        key = (s.get("title") or "")[:12]
        for i, c in enumerate(chunks):
            if key and key in c:
                return i
        return 1 << 30
    return idx(a) - idx(b)


def _recommendations(outline: list[dict], mode: str, audience: str | None) -> list[dict]:
    recs: list[dict] = []
    if mode == "condense" and len(outline) >= 2:
        titles = [(s.get("title") or "").lower().strip() for s in outline]
        for i, t in enumerate(titles):
            if not t:
                continue
            for j in range(i + 1, len(titles)):
                if titles[j] == t:
                    recs.append({
                        "id": f"dup-{i}-{j}", "kind": "merge",
                        "text": f"Slides {i+1:02d} and {j+1:02d} repeat \"{outline[i]['title']}\". Merge them?",
                        "slideIds": [outline[i]["id"], outline[j]["id"]],
                    })
                    break
        first = outline[0]
        if first and re.search(r"\b\d", first.get("title", "")) and not re.search(
            r"intro|overview|context|setup|summary", first.get("title", ""), re.I):
            recs.append({"id": "add-setup", "kind": "add-setup",
                         "text": "No setup slide — the deck opens cold on a number. Add a context slide at the start?"})
        if audience == "exec" and len(outline) > 5:
            recs.append({
                "id": "exec-shorter", "kind": "trim",
                "text": f"Execs typically need 3–4 slides. Drop the weakest {len(outline) - 4}?",
                "slideIds": [s["id"] for s in outline[4:]],
            })
        if audience == "conference" and any(
            sum(1 for m in (s.get("messages") or []) if m) > 2 for s in outline):
            recs.append({"id": "conf-thin", "kind": "thin",
                         "text": "Conference talks land best with 1–2 messages per slide. Thin out the dense ones?"})
        if audience == "status" and outline and not any(
            re.search(r"action|next|todo|owner|by:|by \w", s.get("title", "") + " " + " ".join(s.get("messages") or []), re.I)
            for s in outline):
            recs.append({"id": "status-actions", "kind": "add-actions",
                         "text": "No action items detected. Add a closing slide with next steps and owners?"})

    # Thread / narrative analysis
    if len(outline) >= 2:
        stops = {"the","a","an","and","or","of","to","for","in","on","at","is","it","this","that","with","from","as","by","be","are","was","were","but","so","if","we","our","you","your","their","they","will","can","have","has","had","about","into","than","then","what","which","who","one","more","less","most","any","some","no"}
        def tok(s: str) -> set[str]:
            return {w for w in re.findall(r"\b[a-z][a-z0-9]+\b", (s or "").lower()) if w not in stops}
        slide_tokens = [tok(" ".join([s.get("title", ""), *(s.get("messages") or []), s.get("bumper", "")])) for s in outline]

        counts: dict[str, int] = {}
        for ts in slide_tokens:
            for w in ts:
                counts[w] = counts.get(w, 0) + 1
        candidates = sorted([(w, c) for w, c in counts.items() if c >= 3], key=lambda x: -x[1])
        if candidates and len(outline) >= 3:
            word, count = candidates[0]
            recs.append({"id": f"spine-{word}", "kind": "spine", "advisory": True,
                         "text": f"\"{word}\" appears in {count} of {len(outline)} slides — your strongest spine candidate. Promote it into every slide title to make the through-line obvious."})

        for i, t in enumerate(slide_tokens):
            if not t:
                continue
            shares = any(j != i and (t & slide_tokens[j]) for j in range(len(slide_tokens)))
            if not shares:
                recs.append({"id": f"orphan-{outline[i]['id']}", "kind": "orphan", "advisory": True,
                             "text": f"Slide {i+1:02d} (\"{(outline[i].get('title') or 'untitled')[:40]}\") shares no keywords with any other slide. It reads as an orphan — add a thread that ties it in."})

        for i in range(len(outline) - 1):
            a, b = slide_tokens[i], slide_tokens[i + 1]
            if not a or not b:
                continue
            if not (a & b):
                recs.append({"id": f"gap-{i}", "kind": "gap", "advisory": True,
                             "text": f"Hard cut between slide {i+1:02d} and {i+2:02d} — no shared concepts. Add a bridging bumper or rework the next title."})

        bridge_count = 0
        for i in range(len(outline) - 2):
            a, b, c = slide_tokens[i], slide_tokens[i + 1], slide_tokens[i + 2]
            skipped = [w for w in a if (w in c) and (w not in b)]
            if skipped and bridge_count < 3:
                recs.append({"id": f"bridge-{i}", "kind": "bridge", "advisory": True,
                             "text": f"Slides {i+1:02d} and {i+3:02d} share \"{skipped[0]}\" but slide {i+2:02d} drops it. Weave \"{skipped[0]}\" through the middle slide to bridge the idea."})
                bridge_count += 1
    return recs


def extract_storyboard(req: dict) -> dict:
    """Equivalent of `window.extractStoryboard(req)`."""
    text = (req.get("text") or "").strip()
    mode = req.get("mode") or "draft"
    audience = req.get("audience")

    if not text:
        return {"outline": [_empty_slide(1)], "recommendations": []}

    chunks = [s.strip() for s in re.split(r"^\s*---+\s*$", text, flags=re.M) if s.strip()]
    if len(chunks) == 1:
        chunks = _split_on_headings(text)

    if mode in ("visualize", "synthesize", "refine"):
        single = [_text_to_slide("\n".join(chunks), 1)]
        return {"outline": single, "recommendations": _recommendations(single, mode, audience)}

    if mode == "draft":
        target = max(1, min(6, req.get("targetCount") or 1))
        if target == 1:
            single = [_text_to_slide("\n".join(chunks), 1)]
            return {"outline": single, "recommendations": _recommendations(single, mode, audience)}
        src = chunks[:target] if len(chunks) >= target else chunks
        slides = [_text_to_slide(c, i + 1) for i, c in enumerate(src)]
        while len(slides) < target:
            slides.append(_empty_slide(len(slides) + 1))
        return {"outline": slides, "recommendations": _recommendations(slides, mode, audience)}

    # condense
    target = max(2, min(10, req.get("targetCount") or 5))
    slides = [_text_to_slide(c, i + 1) for i, c in enumerate(chunks)]
    if len(slides) > target:
        slides.sort(key=lambda s: -len(" ".join(s.get("messages") or [])))
        slides = slides[:target]
        slides.sort(key=lambda s: chunks.index(next((c for c in chunks if (s.get("title") or "")[:12] in c), chunks[0])))
    elif len(slides) < target:
        while len(slides) < target:
            slides.append(_empty_slide(len(slides) + 1))
    if not slides:
        slides.append(_empty_slide(1))
    return {"outline": slides, "recommendations": _recommendations(slides, mode, audience)}


# ---- generateCritique ----------------------------------------------------

CRITIQUES_BY_AUDIENCE = {
    "exec": {
        "voice": "an Exec",
        "criticisms": [
            {"id": "a-exec-1", "sev": "high", "text": "There’s no bottom-line on the title slide. Execs scan the title + slide 1 — both should already say \"do X\"."},
            {"id": "a-exec-2", "sev": "med",  "text": "Three messages per slide is dense for exec attention. Two would land harder."},
            {"id": "a-exec-3", "sev": "med",  "text": "Numbers without comparison framing (\"vs plan\", \"vs last quarter\") read as bragging instead of evidence."},
        ],
        "questions": [
            {"id": "q-exec-1", "text": "What does this change in next quarter’s plan?"},
            {"id": "q-exec-2", "text": "Who owns the next step, and by when?"},
            {"id": "q-exec-3", "text": "What’s the cost of not acting on this?"},
            {"id": "q-exec-4", "text": "Where do you need me to clear a blocker?"},
        ],
    },
    "customer": {
        "voice": "a Customer",
        "criticisms": [
            {"id": "a-cust-1", "sev": "high", "text": "Speaks in your team’s language, not the customer’s. Translate \"GTM\" → \"what we’re shipping\"."},
            {"id": "a-cust-2", "sev": "med",  "text": "No before/after the customer can see. They want \"what changes for me\"."},
            {"id": "a-cust-3", "sev": "low",  "text": "Heavy on metrics, light on stories. One customer name lands harder than three percentages."},
        ],
        "questions": [
            {"id": "q-cust-1", "text": "When will this be available to us?"},
            {"id": "q-cust-2", "text": "What does my team need to do to use it?"},
            {"id": "q-cust-3", "text": "Is there a price or contract change?"},
            {"id": "q-cust-4", "text": "What support comes with this?"},
        ],
    },
    "conference": {
        "voice": "a Conference room",
        "criticisms": [
            {"id": "a-conf-1", "sev": "high", "text": "No clear contribution statement. A senior researcher will ask \"what’s new here\" within 90 seconds."},
            {"id": "a-conf-2", "sev": "med",  "text": "Missing prior-art comparison. The first question will be \"how does this differ from X\"."},
            {"id": "a-conf-3", "sev": "med",  "text": "Middle slides read like internal status. Cut them or reframe as method/result."},
        ],
        "questions": [
            {"id": "q-conf-1", "text": "How does this compare to the baseline published at last year’s venue?"},
            {"id": "q-conf-2", "text": "What’s your ablation? Which component matters most?"},
            {"id": "q-conf-3", "text": "Is the dataset and code available?"},
            {"id": "q-conf-4", "text": "What’s the failure mode?"},
        ],
    },
    "status": {
        "voice": "a Status meeting",
        "criticisms": [
            {"id": "a-stat-1", "sev": "high", "text": "No actions, owners, or dates. A status without those is a story without a plot."},
            {"id": "a-stat-2", "sev": "med",  "text": "Risk slide is missing — every status reader scans for \"what could blow up\"."},
            {"id": "a-stat-3", "sev": "low",  "text": "Too many wins, not enough surface area on the blockers."},
        ],
        "questions": [
            {"id": "q-stat-1", "text": "What’s blocked right now, and who can unblock it?"},
            {"id": "q-stat-2", "text": "What slipped since last week?"},
            {"id": "q-stat-3", "text": "Are we still on the original date?"},
            {"id": "q-stat-4", "text": "What needs a decision from this group?"},
        ],
    },
    "oneonone": {
        "voice": "your 1:1 partner",
        "criticisms": [
            {"id": "a-1on1-1", "sev": "med", "text": "This reads like a deck, not a conversation. A 1:1 hangs on one chart and two questions."},
            {"id": "a-1on1-2", "sev": "med", "text": "No \"I need\" or \"I’d like your input on…\". The other person leaves unsure what to do."},
            {"id": "a-1on1-3", "sev": "low", "text": "Too polished — your manager will ask \"what’s the rough draft?\" if it looks final."},
        ],
        "questions": [
            {"id": "q-1on1-1", "text": "What do you actually want from me here?"},
            {"id": "q-1on1-2", "text": "What’s your gut say, before you show me the data?"},
            {"id": "q-1on1-3", "text": "Which of these are you not sure about?"},
        ],
    },
    "technical": {
        "voice": "a Technical reviewer",
        "criticisms": [
            {"id": "a-tech-1", "sev": "high", "text": "Result first, derivation second. Engineers won’t trust a result until they see the math behind it."},
            {"id": "a-tech-2", "sev": "med",  "text": "Numbers without uncertainty (error bars / CI) — the room will discount them."},
            {"id": "a-tech-3", "sev": "med",  "text": "No \"I considered approach X and rejected it because Y\". Without that, \"why this approach\" is the first question."},
        ],
        "questions": [
            {"id": "q-tech-1", "text": "What’s the failure mode at the extremes?"},
            {"id": "q-tech-2", "text": "Did you try the obvious alternative? Why not?"},
            {"id": "q-tech-3", "text": "How robust is this to noise or adversarial input?"},
            {"id": "q-tech-4", "text": "Can you reproduce this with the same parameters?"},
        ],
    },
}

CRITIQUES_BY_MODE = {
    "draft":      [{"id": "m-draft-1",  "sev": "low",  "kind": "criticism", "text": "One slide is brave. Make sure it earns that — every other concept gets cut."}],
    "refine":     [{"id": "m-refine-1", "sev": "med",  "kind": "criticism", "text": "Did the rework actually fix the gap you flagged, or just polish?"}],
    "condense":   [{"id": "m-cond-1",   "sev": "med",  "kind": "criticism", "text": "What got cut, and does the full deck still exist for follow-up?"}],
    "visualize":  [
        {"id": "m-vis-1", "sev": "med", "kind": "criticism", "text": "Parameter ranges define the story. Pick ranges that show the edge cases, not just the comfortable zone."},
        {"id": "m-vis-2", "sev": "low", "kind": "question",  "text": "What happens outside this plot range?"},
    ],
    "synthesize": [
        {"id": "m-syn-1", "sev": "high", "kind": "criticism", "text": "Where is this data from, and what window was selected? Pick that window honestly or someone will ask."},
        {"id": "m-syn-2", "sev": "med",  "kind": "question",  "text": "What’s the sample size and confidence interval?"},
    ],
}


def generate_critique(req: dict) -> dict:
    """Equivalent of `window.generateCritique(req)`."""
    audience = req.get("audience") or "exec"
    mode = req.get("mode") or "draft"
    outline = req.get("outline") or []
    aud = CRITIQUES_BY_AUDIENCE.get(audience) or CRITIQUES_BY_AUDIENCE["exec"]

    criticisms = [{**c, "source": "audience", "kind": "criticism"} for c in aud["criticisms"]]
    questions = [{**q, "source": "audience", "kind": "question"} for q in aud["questions"]]

    for m in CRITIQUES_BY_MODE.get(mode, []):
        target = questions if m.get("kind") == "question" else criticisms
        target.append({**m, "source": "mode"})

    def joined(s: dict) -> str:
        return (s.get("title", "") + " " + " ".join(s.get("messages") or []) + " " + s.get("bumper", ""))

    if audience == "status" and outline and not any(
        re.search(r"action|next step|owner|by:|by \w", joined(s), re.I) for s in outline):
        criticisms.append({
            "id": "c-content-1", "sev": "high", "source": "content", "kind": "criticism",
            "text": "No action items detected anywhere in the deck. A status meeting will ask \"who, by when\" within 30 seconds.",
        })
    if audience == "exec" and len(outline) > 4:
        criticisms.append({
            "id": "c-content-2", "sev": "med", "source": "content", "kind": "criticism",
            "text": f"{len(outline)} slides for an exec is a lot. They want 3 — slide 01 telling them what to do, 02 why, 03 the anchor number.",
        })
    cells = [t for s in outline for t in [s.get("title", ""), *(s.get("messages") or [])] if t]
    numeric = sum(1 for t in cells if re.search(r"\b\d", t))
    if cells and numeric / len(cells) > 0.55:
        criticisms.append({
            "id": "c-content-3", "sev": "med", "source": "content", "kind": "criticism",
            "text": "The deck is dense with numbers — most cells contain a digit. Each needs a sentence telling the room what it means.",
        })
    if outline and all(sum(1 for m in (s.get("messages") or []) if m) >= 3 for s in outline):
        criticisms.append({
            "id": "c-content-4", "sev": "low", "source": "content", "kind": "criticism",
            "text": "Every slide carries the maximum 3 messages. Some should breathe — a single message slide is a power move.",
        })
    return {"voice": aud["voice"], "criticisms": criticisms, "questions": questions}
