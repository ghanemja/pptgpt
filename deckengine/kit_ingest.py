"""kit_ingest.py — what a company's example decks teach, measured.

A first pass over the decks a company considers good, producing a small,
readable `learned.json` beside them. Everything here is MEASURED from the
.pptx files — counts, medians, which layouts get used — so the result can be
checked against the decks by hand, and the same decks always teach the same
thing. Nothing is inferred by a model.

What it is used for, and why it matters:

  * the coach stops judging density by our threshold and starts judging it
    by theirs — "denser than your own decks usually are" is an argument a
    team accepts where "more than four bullets" is not;
  * generation is told the company's norms (points per slide, words per
    point, how titles are written);
  * casting into the template prefers the layouts the company actually uses.

It reads content and conventions only. The positions of anything on those
slides are never recorded (R0.1); the template owns geometry.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import time
from collections import Counter
from typing import Any, Optional

from pptx import Presentation
from pptx.util import Emu

from .kit import example_files, kit_dir

# A title that makes a claim has a verb in it. The coach's title lens uses
# the same test, so "your titles argue 30% of the time" and the coach
# flagging a title as a label are the same judgement.
_VERB = re.compile(r"\b(is|are|was|were|beat|grew|fell|drove|wins?|needs?|should|must|can|will|"
                   r"cut|doubled|halved|holds?|leads?|costs?|means?|proves?|shows?|rose|drop\w*|"
                   r"increas\w*|decreas\w*|improv\w*|reduc\w*|delivers?|makes?|gets?|has|have)\b", re.I)

_TITLE_TYPES = {1, 3}            # TITLE, CENTER_TITLE
MIN_POINT_WORDS = 3
_STAT = re.compile(r"^[+\-−~≈$€£]?\s?\d[\d,.]*\s?(%|x|k|m|bn|b|pts?|pp)?$", re.I)
_IGNORED_TYPES = {13, 15, 16}    # slide number, footer, date


def _ph_type(shape) -> int:
    try:
        return int(shape.placeholder_format.type)
    except (AttributeError, TypeError, ValueError):
        return -1


def _pct(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "median": None, "p75": None, "max": None}
    return {"n": len(values), "median": round(statistics.median(values), 2),
            "p75": _pct(values, 0.75), "max": round(max(values), 2)}


def _slide_title(slide) -> str:
    try:
        t = slide.shapes.title
        if t is not None and t.has_text_frame and t.text_frame.text.strip():
            return t.text_frame.text.strip()
    except Exception:
        pass
    # No title placeholder: the first non-empty text is the best guess.
    for sh in slide.shapes:
        if getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip():
            return sh.text_frame.text.strip().split("\n")[0]
    return ""


def read_slide(slide) -> dict[str, Any]:
    """The conventions one slide shows. No positions are kept."""
    title = _slide_title(slide)
    points: list[str] = []
    title_pts: list[float] = []
    body_pts: list[float] = []
    fonts: Counter = Counter()
    has_chart = has_picture = has_table = False
    prev_was_stat = False

    for sh in slide.shapes:
        kind = _ph_type(sh)
        if kind in _IGNORED_TYPES:
            continue
        if getattr(sh, "has_chart", False) and sh.has_chart:
            has_chart = True
        if getattr(sh, "has_table", False) and sh.has_table:
            has_table = True
        if int(getattr(sh, "shape_type", 0) or 0) == 13 or kind == 18:
            has_picture = True
        if not getattr(sh, "has_text_frame", False):
            continue

        is_title = kind in _TITLE_TYPES or (sh.text_frame.text.strip() == title and title)
        for para in sh.text_frame.paragraphs:
            text = "".join(r.text for r in para.runs).strip()
            for r in para.runs:
                if r.font.name:
                    fonts[r.font.name] += 1
                if r.font.size:
                    (title_pts if is_title else body_pts).append(Emu(r.font.size).pt)
            # A point is a phrase someone wrote to be read. Stat values and
            # their labels ("118%", "net retention") are text too, but
            # counting them as points would make a stat slide look like a
            # wall of bullets and inflate every density norm.
            if text and not is_title and len(text.split()) >= MIN_POINT_WORDS \
                    and not prev_was_stat:
                points.append(text)
            # The text right after a bare number labels it ("+14%" then
            # "revenue vs plan") — a caption, not a point, however long.
            if text:
                prev_was_stat = bool(_STAT.match(text))

    return {
        "layout": (slide.slide_layout.name or "").strip() or "(unnamed)",
        "title": title,
        "title_words": len(title.split()),
        "title_argues": bool(_VERB.search(title)),
        "points": len(points),
        "words_per_point": [len(p.split()) for p in points],
        "has_chart": has_chart, "has_picture": has_picture, "has_table": has_table,
        "title_pt": title_pts, "body_pt": body_pts, "fonts": fonts,
    }


def read_deck(path: str) -> dict[str, Any]:
    return _read(path)[0]


def _read(path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """One open of the file, two readings: the measured conventions for
    learned.json and the structure for graph.json."""
    from . import kit_graph
    from .kit import file_digest
    prs = Presentation(path)
    slides = [read_slide(s) for s in prs.slides]
    name = os.path.basename(path)
    return ({"file": name, "slides": slides},
            kit_graph.read_deck(prs, name, slides, digest=file_digest(path)))


def learn(slug: str) -> dict[str, Any]:
    """Read every example deck in the kit; write learned.json and graph.json."""
    from . import kit_graph
    files = example_files(slug)
    decks, structure, failed = [], [], []
    for path in files:
        try:
            measured, graphed = _read(path)
            decks.append(measured)
            structure.append(graphed)
        except Exception as e:                       # one bad file must not sink the run
            failed.append({"file": os.path.basename(path), "reason": str(e)[:160]})
    graph = kit_graph.build(structure)

    slides = [s for d in decks for s in d["slides"]]
    content = [s for s in slides if s["points"] or s["title"]]

    layouts = Counter(s["layout"] for s in slides)
    fonts: Counter = Counter()
    for s in slides:
        fonts.update(s["fonts"])

    points = [s["points"] for s in content if s["points"]]
    wpp = [w for s in content for w in s["words_per_point"]]
    title_words = [s["title_words"] for s in content if s["title_words"]]
    argue = [s["title_argues"] for s in content if s["title"]]
    per_deck = [len(d["slides"]) for d in decks]
    n = max(1, len(slides))

    result: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "generated_epoch": time.time(),
        "decks": len(decks),
        "slides": len(slides),
        "files": [d["file"] for d in decks],
        "failed": failed,
        "layouts": [{"name": name, "share": round(c / n, 3), "count": c}
                    for name, c in layouts.most_common()],
        "density": {
            "points_per_slide": _summary(points),
            "words_per_point": _summary(wpp),
            "slides_per_deck": _summary(per_deck),
        },
        "titles": {
            "words": _summary(title_words),
            "argue_share": round(sum(argue) / len(argue), 3) if argue else None,
        },
        "visuals": {
            "chart_share": round(sum(s["has_chart"] for s in slides) / n, 3),
            "picture_share": round(sum(s["has_picture"] for s in slides) / n, 3),
            "table_share": round(sum(s["has_table"] for s in slides) / n, 3),
            "text_only_share": round(sum(not (s["has_chart"] or s["has_picture"] or s["has_table"])
                                         for s in slides) / n, 3),
        },
        "type": {
            "fonts": [{"name": f, "runs": c} for f, c in fonts.most_common(6)],
            "title_pt": _summary([p for s in slides for p in s["title_pt"]]),
            "body_pt": _summary([p for s in slides for p in s["body_pt"]]),
        },
    }
    result["norms"] = {**norms_from(result), **kit_graph.norms_from_graph(graph)}
    result["graph"] = {"path": kit_graph.GRAPH_FILE, "digest": graph["digest"],
                       "nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
                       "roles": graph["summary"]["roles"],
                       "preferred_diagram_kinds": graph["summary"]["preferred_diagram_kinds"]}
    result["suggested_rules"] = suggested_rules(result)

    kit_graph.write(slug, graph)
    path = os.path.join(kit_dir(slug), "learned.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")
    return result


def norms_from(result: dict[str, Any]) -> dict[str, Any]:
    """The few numbers other parts of the engine act on.

    Upper quartiles, not maxima: one 14-bullet appendix slide should not
    license 14 bullets everywhere. Clamped to sane ranges so a tiny or odd
    corpus cannot produce a nonsense norm.
    """
    d = result["density"]
    pps = d["points_per_slide"]["p75"]
    wpp = d["words_per_point"]["p75"]
    tw = result["titles"]["words"]["median"]
    return {
        "max_points": int(min(8, max(2, round(pps)))) if pps is not None else None,
        "max_words_per_point": int(min(30, max(4, round(wpp)))) if wpp is not None else None,
        "title_words": int(round(tw)) if tw is not None else None,
        "titles_argue": (result["titles"]["argue_share"] or 0) >= 0.5,
        "preferred_layouts": [l["name"] for l in result["layouts"][:5]],
    }


def suggested_rules(result: dict[str, Any]) -> list[str]:
    """House rules the examples imply, worded the way profile.json words them.

    Suggestions, not edits: the setup screen offers them and a person
    decides which become rules.
    """
    out = []
    n = result["norms"]
    if n.get("max_points"):
        out.append(f"At most {n['max_points']} points per slide.")
    if n.get("max_words_per_point"):
        out.append(f"Keep each point under {n['max_words_per_point']} words.")
    share = result["titles"]["argue_share"]
    if share is not None:
        if share >= 0.5:
            out.append("Titles state a claim, not a topic.")
        else:
            out.append("Titles name the topic; the takeaway carries the claim.")
    v = result["visuals"]
    if v["chart_share"] >= 0.25:
        out.append("Show numbers as charts where you can.")
    if v["text_only_share"] >= 0.8:
        out.append("Text-led slides are the norm; save visuals for the evidence.")
    arc = n.get("arc") or {}
    if (arc.get("ask_share") or 0) >= 0.5 and (arc.get("ask_position") or 0) >= 0.8:
        out.append("End on the ask: the last slides say what needs deciding.")
    kinds = n.get("preferred_diagram_kinds") or []
    if kinds:
        out.append(f"Draw processes as {' or '.join(kinds[:2])} diagrams.")
    return out


def norms(slug: str) -> Optional[dict[str, Any]]:
    path = os.path.join(kit_dir(slug), "learned.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh).get("norms")
    except (OSError, json.JSONDecodeError):
        return None
