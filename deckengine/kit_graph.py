"""kit_graph.py — a company's example decks, read once, as a queryable graph.

`kit_ingest.learn` measures the examples into a few numbers (learned.json).
This module reads the same decks in the same pass and keeps their STRUCTURE:
what role each slide plays, which roles follow which, where the ask lands,
which terms recur and where, how big sections run, and which charts,
tables and diagrams the company reaches for. It is written to
`kits/<slug>/graph.json`, and from then on the engine and the model look a
convention up here instead of rereading decks. A question like "which slides
use a timeline" or "how do their decks open" is a dictionary lookup.

    nodes   deck · slide · role · term · visual
    edges   contains  deck → slide
            follows   slide → slide (reading order); role → role (count)
            is        slide → role
            uses      slide → visual
            mentions  slide → term

Everything is MEASURED and deterministic: the same decks give a
byte-identical graph (no timestamps inside; a content digest instead), and
every count can be checked against the decks by hand. Positions and sizes
of shapes are never read, let alone stored (R0.1): roles come from
placeholder types and text, diagrams from SmartArt layout ids, connector
topology, shape kinds and words. The template owns geometry.

`describe` is the one optional model pass: it may LABEL what the measured
graph shows, and every claim it makes must cite slide ids that exist, or it
is dropped. With no model it returns the measured facts themselves.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
from collections import Counter, defaultdict
from typing import Any, Callable, Iterable, Optional, Union

from lxml import etree

from . import native
from .diagram import KINDS as DIAGRAM_KINDS, _ALIASES as _DIAGRAM_ALIASES

GRAPH_VERSION = 1
GRAPH_FILE = "graph.json"

# Slide roles. The text roles are native.py's own (so a learned role can be
# handed straight to pick_layout_for); chart, table and diagram split
# native's "picture" because a company's habit of charting vs tabulating vs
# drawing a process is exactly what generation needs to know.
ROLE_COVER = native.ROLE_COVER
ROLE_SECTION = native.ROLE_SECTION
ROLE_STATEMENT = native.ROLE_STATEMENT
ROLE_BULLETS = native.ROLE_BULLETS
ROLE_TWO = native.ROLE_TWO
ROLE_CHART, ROLE_TABLE, ROLE_PICTURE, ROLE_DIAGRAM = "chart", "table", native.ROLE_PICTURE, "diagram"
ROLES = (ROLE_COVER, ROLE_SECTION, ROLE_STATEMENT, ROLE_BULLETS, ROLE_TWO,
         ROLE_CHART, ROLE_TABLE, ROLE_PICTURE, ROLE_DIAGRAM)
START, END = "start", "end"

# Where in a deck a slide sits, in fifths. The arc is the most common role
# at each stage, which reads as the company's narrative shape.
STAGES = ("open", "early", "middle", "late", "close")

_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
}
SMARTART_URI = _NS["dgm"]

# SmartArt layout ids (e.g. "urn:microsoft.com/office/officeart/2005/8/layout/
# hierarchy1") name their family. Checked in order: the first word found wins,
# so the specific families come before the generic "process"/"arrow".
_SMARTART_KIND = (
    ("timeline", "timeline"), ("hierarchy", "hierarchy"), ("orgchart", "hierarchy"),
    ("cycle", "cycle"), ("funnel", "funnel"), ("pyramid", "funnel"),
    ("matrix", "matrix"), ("chevron", "flow"), ("process", "flow"), ("arrow", "flow"),
)

# Autoshape kinds that, repeated on one slide, draw a diagram. Read from the
# shape's preset name, never its position.
_SHAPE_KIND = {
    "chevron": "flow", "pentagon": "flow", "homeplate": "flow", "rightarrow": "flow",
    "flowchartprocess": "flow", "flowchartdecision": "flow",
    "circulararrow": "cycle", "blockarc": "cycle",
    "trapezoid": "funnel", "funnel": "funnel",
}
_SHAPE_MIN = {"flow": 3, "cycle": 1, "funnel": 3}

_TITLE_TYPES = {1, 3}
_CENTER_TITLE, _SUBTITLE = 3, 4
_FURNITURE = {13, 15, 16}
_BODY_TYPES = {2, 7}
_PICTURE_TYPE = 13

_ASK = re.compile(
    r"\b(asks?|decisions?|decide|approv\w*|sign[- ]?off|recommend\w*|propos\w*|"
    r"next steps|requests?|go/no[- ]go|green[- ]?light|funding|budget ask)\b", re.I)
_DATE = re.compile(
    r"\b(Q[1-4]|H[12]|FY\s?\d{2,4}|(19|20)\d{2}|jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|"
    r"may|june?|july?|aug(ust)?|sept?(ember)?|oct(ober)?|nov(ember)?|dec(ember)?|"
    r"week \d+|month \d+|day \d+)\b", re.I)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9&'’\-]*")
_ACRONYM = re.compile(r"^[A-Z][A-Z0-9&]{1,5}$")

_STOP = frozenset("""
a about above after again against all also am an and any are as at be because been
before being below between both but by can could did do does doing down during each
few for from further had has have having he her here hers herself him himself his how
i if in into is it its itself just let me more most my myself no nor not now of off on
once only or other our ours ourselves out over own same she should so some such than
that the their theirs them themselves then there these they this those through to too
under until up very was we were what when where which while who whom why will with
would you your yours yourself yourselves via per vs etc new one two three four five
get got make made use used using us were weve we're we'll it's that's there's
came come comes went goes going need needs take takes keep keeps
""".split())

MAX_TERMS = 40
TITLE_CHARS = 90


# ---- reading one slide -----------------------------------------------------

def _ph_type(shape) -> int:
    try:
        return int(shape.placeholder_format.type)
    except (AttributeError, TypeError, ValueError):
        return -1


def _walk(shapes) -> Iterable[Any]:
    """Every shape, groups opened. Order is the slide's own z-order."""
    for sh in shapes:
        yield sh
        if int(getattr(sh, "shape_type", 0) or 0) == 6:      # GROUP
            yield from _walk(sh.shapes)


def _tag(sh) -> str:
    return etree.QName(sh._element).localname


def _chart_family(chart) -> str:
    try:
        name = chart.chart_type.name.lower()
    except Exception:                                 # combo or unknown plot
        return "other"
    name = name.replace("three_d_", "")
    head = name.split("_")[0]
    return {"xy": "scatter", "doughnut": "doughnut", "radar": "radar"}.get(head, head)


def _smartart(slide, frame) -> tuple[Optional[str], list[str], str]:
    """(kind, node texts, layout id) for one SmartArt frame. Best effort: a
    frame whose parts cannot be read still counts as SmartArt, kind unknown."""
    rel = frame._element.find(".//dgm:relIds", _NS)
    if rel is None:
        return None, [], ""
    layout_id, texts = "", []
    lo = rel.get(f"{{{_NS['r']}}}lo")
    dm = rel.get(f"{{{_NS['r']}}}dm")
    try:
        root = etree.fromstring(slide.part.related_part(lo).blob)
        layout_id = root.get("uniqueId") or ""
    except Exception:
        pass
    try:
        root = etree.fromstring(slide.part.related_part(dm).blob)
        texts = [t.text.strip() for t in root.iter(f"{{{_NS['a']}}}t") if t.text and t.text.strip()]
    except Exception:
        pass
    low = layout_id.lower()
    kind = next((k for word, k in _SMARTART_KIND if word in low), None)
    return kind, texts, layout_id


def _connections(cxn) -> tuple[Optional[str], Optional[str]]:
    st = cxn.find(".//a:stCxn", _NS)
    en = cxn.find(".//a:endCxn", _NS)
    return (st.get("id") if st is not None else None,
            en.get("id") if en is not None else None)


def _topology_kind(edges: list[tuple[str, str]], texts: dict[str, str]) -> str:
    """flow / cycle / hierarchy / timeline from who connects to whom."""
    nodes = sorted({n for e in edges for n in e})
    out_deg, in_deg = Counter(a for a, _ in edges), Counter(b for _, b in edges)
    if nodes and all(out_deg[n] == 1 and in_deg[n] == 1 for n in nodes):
        return "cycle"
    if any(out_deg[n] >= 2 for n in nodes) and all(in_deg[n] <= 1 for n in nodes):
        return "hierarchy"
    dated = sum(1 for n in nodes if _DATE.search(texts.get(n, "")))
    if nodes and dated * 2 >= len(nodes):
        return "timeline"
    return "flow"


def _title_kind(title: str) -> Optional[str]:
    low = title.lower()
    for word in sorted(set(DIAGRAM_KINDS) | set(_DIAGRAM_ALIASES), key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", low):
            return _DIAGRAM_ALIASES.get(word, word)
    return None


def _layout_hint(name: str, role: str) -> bool:
    low = name.lower()
    return any(re.search(rf"(?<!\w){re.escape(h)}(?!\w)", low)
               for h in native._NAME_HINTS.get(role, ()))


def read_slide(slide, index: int, measured: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """One slide's structure: role, visuals, text for terms. No geometry.

    `measured` is kit_ingest.read_slide's result for the same slide, so a
    "point" means the same thing here as in the density norms.
    """
    if measured is None:
        from .kit_ingest import read_slide as measure
        measured = measure(slide)
    title = measured.get("title") or ""
    layout = measured.get("layout") or ""

    lines: list[str] = []                 # non-title text, for the takeaway and terms
    texts_by_id: dict[str, str] = {}
    bodies_with_text = 0
    has_center_title = has_subtitle = False
    charts: list[str] = []
    has_table = has_picture = False
    smartart: list[tuple[Optional[str], str]] = []
    extra_text: list[str] = []            # SmartArt nodes and table cells
    edges: list[tuple[str, str]] = []
    connectors = 0
    shape_kinds: Counter = Counter()
    groups_of_boxes = 0

    for sh in _walk(slide.shapes):
        kind = _ph_type(sh)
        if kind in _FURNITURE:
            continue
        tag = _tag(sh)
        if kind == _CENTER_TITLE:
            has_center_title = True
        if tag == "graphicFrame":
            gd = sh._element.find(".//a:graphicData", _NS)
            if gd is not None and gd.get("uri") == SMARTART_URI:
                k, nodes, lid = _smartart(slide, sh)
                smartart.append((k, lid))
                extra_text.extend(nodes)
                continue
        if getattr(sh, "has_chart", False) and sh.has_chart:
            charts.append(_chart_family(sh.chart))
            continue
        if getattr(sh, "has_table", False) and sh.has_table:
            has_table = True
            for row in sh.table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        extra_text.append(cell.text.strip())
            continue
        if tag == "cxnSp":
            connectors += 1
            a, b = _connections(sh._element)
            if a and b:
                edges.append((a, b))
            continue
        if tag == "grpSp":
            boxes = [c for c in sh.shapes if getattr(c, "has_text_frame", False)
                     and c.text_frame.text.strip()]
            if len(boxes) >= 3:
                groups_of_boxes += 1
            continue
        if int(getattr(sh, "shape_type", 0) or 0) == _PICTURE_TYPE or kind == 18:
            has_picture = True
        try:
            preset = sh.auto_shape_type.name.lower().replace("_", "") \
                if int(getattr(sh, "shape_type", 0) or 0) == 1 else ""
        except Exception:
            preset = ""
        if preset in _SHAPE_KIND:
            shape_kinds[_SHAPE_KIND[preset]] += 1
        if not getattr(sh, "has_text_frame", False):
            continue
        text = sh.text_frame.text.strip()
        if not text:
            continue
        texts_by_id[str(sh.shape_id)] = text
        if kind in _TITLE_TYPES or (title and text == title):
            continue
        if kind == _SUBTITLE:
            has_subtitle = True
        if kind in _BODY_TYPES:
            bodies_with_text += 1
        lines.extend(l.strip() for l in text.splitlines() if l.strip())

    # Diagrams: what kind, and why we think so (kept, so it can be checked).
    diagram_kinds: list[str] = []
    evidence: list[str] = []
    hint = _title_kind(title)
    for k, lid in smartart:
        diagram_kinds.append(k or "other")
        evidence.append(f"smartart:{lid.rsplit('/', 1)[-1] or '?'}")
    structural: Optional[str] = None
    if edges:
        structural = _topology_kind(edges, texts_by_id)
        evidence.append(f"connectors:{len(edges)}")
    elif connectors >= 2:
        structural = "flow"
        evidence.append(f"connectors:{connectors}")
    else:
        for k in ("cycle", "funnel", "flow"):
            if shape_kinds[k] >= _SHAPE_MIN[k]:
                structural = k
                evidence.append(f"shapes:{k}x{shape_kinds[k]}")
                break
    if structural is None and groups_of_boxes:
        structural = "other"
        evidence.append(f"group:{groups_of_boxes}")
    if structural is not None:
        if structural in ("flow", "other"):
            dated = sum(1 for t in texts_by_id.values() if _DATE.search(t) and t != title)
            if dated >= 3:
                structural = "timeline"
                evidence.append("dates")
            elif hint:
                structural = hint
                evidence.append(f"title:{hint}")
        diagram_kinds.append(structural)

    visuals: set[str] = {f"chart:{c}" for c in charts}
    if has_table:
        visuals.add("table")
    if has_picture:
        visuals.add("picture")
    if smartart:
        visuals.add("smartart")
    if edges or connectors >= 2:
        visuals.add("connector")
    if groups_of_boxes:
        visuals.add("group")
    visuals.update(f"diagram:{k}" for k in diagram_kinds)

    points = int(measured.get("points") or 0)
    if index == 0 and not (charts or has_table or diagram_kinds) and \
            (has_center_title or has_subtitle or points <= 1 or _layout_hint(layout, ROLE_COVER)):
        role = ROLE_COVER
    elif diagram_kinds:
        role = ROLE_DIAGRAM
    elif charts:
        role = ROLE_CHART
    elif has_table:
        role = ROLE_TABLE
    elif has_picture:
        role = ROLE_PICTURE
    elif points == 0 and _layout_hint(layout, ROLE_SECTION):
        role = ROLE_SECTION
    else:
        # Text slides: native.classify decides section vs statement vs list,
        # so a learned role and a cast role are the same judgement. Its
        # "two" is a casting rule (four points or more); here two means the
        # source itself was set in two columns.
        role = native.classify({"title": title, "kind": "text",
                                "bullets": ["·"] * points,
                                "takeaway": lines[0] if (lines and not points) else ""})
        if role in (ROLE_TWO, ROLE_BULLETS):
            role = ROLE_TWO if (bodies_with_text >= 2 or _layout_hint(layout, ROLE_TWO)) \
                else ROLE_BULLETS

    words = " ".join([title] + lines + extra_text)
    return {
        "title": title[:TITLE_CHARS], "layout": layout, "role": role,
        "points": points, "ask": bool(_ASK.search(words)),
        "visuals": sorted(visuals),
        "diagram_kinds": diagram_kinds, "evidence": evidence,
        "text": [title] + lines + extra_text,       # for terms; not stored
    }


def read_deck(prs, file: str, measured: Optional[list[dict[str, Any]]] = None,
              digest: str = "") -> dict[str, Any]:
    slides = list(prs.slides)
    m = measured or [None] * len(slides)
    return {"file": file, "digest": digest,
            "slides": [read_slide(s, i, m[i]) for i, s in enumerate(slides)]}


# ---- terms -------------------------------------------------------------------

def _tokens(line: str) -> list[tuple[str, bool, bool]]:
    """(word, kept, capitalised-mid-sentence). Stop words break bigrams."""
    out = []
    for i, m in enumerate(_WORD.finditer(line)):
        w = m.group(0).strip("-'’")
        low = w.lower()
        acronym = bool(_ACRONYM.match(w))
        kept = (low not in _STOP and len(low) >= 3) or acronym
        out.append((w, kept, i > 0 and w[:1].isupper()))
    return out


def _terms(decks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slides_of: dict[str, set[str]] = defaultdict(set)
    decks_of: dict[str, set[str]] = defaultdict(set)
    forms: dict[str, Counter] = defaultdict(Counter)
    caps: Counter = Counter()
    lower: Counter = Counter()
    for di, d in enumerate(decks, 1):
        for si, s in enumerate(d["slides"], 1):
            sid = f"d{di}.s{si}"
            seen: set[str] = set()
            for line in s["text"]:
                toks = _tokens(line)
                grams: list[tuple[str, str, bool]] = []
                for j, (w, kept, cap) in enumerate(toks):
                    if not kept or w.replace(",", "").replace(".", "").isdigit():
                        continue
                    grams.append((w.lower(), w, cap or bool(_ACRONYM.match(w))))
                    if j + 1 < len(toks) and toks[j + 1][1]:
                        w2 = toks[j + 1][0]
                        grams.append((f"{w.lower()} {w2.lower()}", f"{w} {w2}", cap))
                for key, form, cap in grams:
                    forms[key][form] += 1
                    (caps if cap else lower)[key] += 1
                    seen.add(key)
            for key in seen:
                slides_of[key].add(sid)
                decks_of[key].add(f"d{di}")

    min_decks = 2 if len(decks) >= 2 else 1
    keep = [k for k in slides_of if len(slides_of[k]) >= 2 and len(decks_of[k]) >= min_decks]
    # A word that only ever appears inside a recurring phrase is that phrase.
    bigrams = {k for k in keep if " " in k}
    keep = [k for k in keep if " " in k or not any(
        slides_of[b] == slides_of[k] and k in b.split() for b in bigrams)]
    keep.sort(key=lambda k: (-len(decks_of[k]), -len(slides_of[k]), -k.count(" "), k))
    out = []
    for k in keep[:MAX_TERMS]:
        label = sorted(forms[k].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        entity = all(_ACRONYM.match(p) for p in label.split()) or (caps[k] > 0 and lower[k] == 0)
        out.append({"term": k, "label": label, "entity": bool(entity),
                    "decks": len(decks_of[k]), "slides": sorted(slides_of[k], key=_sid_key)})
    return out


def _sid_key(sid: str) -> tuple[int, int]:
    d, s = sid.split(".")
    return int(d[1:]), int(s[1:])


# ---- the graph ---------------------------------------------------------------

def _median(xs: list[float]) -> Optional[float]:
    return round(statistics.median(xs), 3) if xs else None


def _ranked(c: Counter) -> list[dict[str, Any]]:
    return [{"value": k, "count": v} for k, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]


def _arc(decks: list[dict[str, Any]]) -> dict[str, Any]:
    transitions: Counter = Counter()
    first, last, opens, closes = Counter(), Counter(), Counter(), Counter()
    stage_roles: dict[str, Counter] = {s: Counter() for s in STAGES}
    ask_at: list[float] = []
    ask_slides: list[str] = []
    for di, d in enumerate(decks, 1):
        roles = [s["role"] for s in d["slides"]]
        n = len(roles)
        if not n:
            continue
        seq = [START] + roles + [END]
        transitions.update(zip(seq, seq[1:]))
        first[roles[0]] += 1
        last[roles[-1]] += 1
        opens[" > ".join(roles[:2])] += 1
        closes[" > ".join(roles[-2:])] += 1
        for i, r in enumerate(roles):
            stage_roles[STAGES[min(len(STAGES) - 1, i * len(STAGES) // n)]][r] += 1
        asks = [i for i, s in enumerate(d["slides"]) if s["ask"]]
        if asks:
            i = asks[-1]                       # where the decision lands
            ask_at.append(round(i / (n - 1), 3) if n > 1 else 1.0)
            ask_slides.append(f"d{di}.s{i + 1}")
    stages = []
    for st in STAGES:
        c = stage_roles[st]
        if c:
            role, cnt = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            stages.append({"stage": st, "role": role, "share": round(cnt / sum(c.values()), 3)})
    return {
        "stages": stages,
        "first": _ranked(first), "last": _ranked(last),
        "opens": _ranked(opens), "closes": _ranked(closes),
        "transitions": [{"from": a, "to": b, "count": c} for (a, b), c in
                        sorted(transitions.items(), key=lambda kv: (-kv[1], kv[0]))],
        "ask": {"decks_with_ask": len(ask_at), "decks": len(decks),
                "position_median": _median(ask_at), "positions": ask_at,
                "slides": ask_slides},
    }


def _sections(decks: list[dict[str, Any]]) -> dict[str, Any]:
    per_deck, sizes = [], []
    for di, d in enumerate(decks, 1):
        roles = [s["role"] for s in d["slides"]]
        breaks = [i for i, r in enumerate(roles) if r == ROLE_SECTION]
        bounds = breaks + [len(roles)]
        sz = [bounds[k + 1] - bounds[k] - 1 for k in range(len(breaks))]
        sizes.extend(sz)
        per_deck.append({"deck": f"d{di}", "breaks": [f"d{di}.s{i + 1}" for i in breaks],
                         "sizes": sz, "before_first": breaks[0] if breaks else len(roles)})
    return {"decks": per_deck,
            "decks_with_sections": sum(1 for p in per_deck if p["breaks"]),
            "sections_per_deck": _median([len(p["breaks"]) for p in per_deck]),
            "size_median": _median(sizes), "size_max": max(sizes) if sizes else None}


def preferred_diagram_kinds_of(decks: list[dict[str, Any]]) -> list[str]:
    c: Counter = Counter()
    for d in decks:
        for s in d["slides"]:
            c.update({k for k in s["diagram_kinds"] if k in DIAGRAM_KINDS})
    return [k for k, _ in sorted(c.items(), key=lambda kv: (-kv[1], DIAGRAM_KINDS.index(kv[0])))]


def build(decks: list[dict[str, Any]]) -> dict[str, Any]:
    """Deck records (from read_deck) → the graph. Pure and deterministic."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    role_count: Counter = Counter()
    visual_slides: dict[str, list[str]] = defaultdict(list)

    for di, d in enumerate(decks, 1):
        did = f"d{di}"
        nodes.append({"id": did, "type": "deck", "file": d["file"],
                      "digest": d.get("digest", ""), "slides": len(d["slides"])})
        prev = None
        for si, s in enumerate(d["slides"], 1):
            sid = f"{did}.s{si}"
            nodes.append({"id": sid, "type": "slide", "deck": did, "n": si,
                          "title": s["title"], "layout": s["layout"], "role": s["role"],
                          "points": s["points"], "ask": s["ask"], "visuals": s["visuals"],
                          "evidence": s["evidence"]})
            edges.append({"type": "contains", "from": did, "to": sid})
            edges.append({"type": "is", "from": sid, "to": f"role:{s['role']}"})
            if prev:
                edges.append({"type": "follows", "from": prev, "to": sid})
            prev = sid
            role_count[s["role"]] += 1
            for v in s["visuals"]:
                visual_slides[v].append(sid)
                edges.append({"type": "uses", "from": sid, "to": f"visual:{v}"})

    arc = _arc(decks)
    for r in ROLES:
        if role_count[r]:
            nodes.append({"id": f"role:{r}", "type": "role", "slides": role_count[r]})
    for t in arc["transitions"]:
        if t["from"] in (START, END) or t["to"] in (START, END):
            continue
        edges.append({"type": "follows", "from": f"role:{t['from']}", "to": f"role:{t['to']}",
                      "count": t["count"]})
    for v in sorted(visual_slides):
        nodes.append({"id": f"visual:{v}", "type": "visual", "slides": len(visual_slides[v])})

    terms = _terms(decks)
    for t in terms:
        tid = f"term:{t['term']}"
        nodes.append({"id": tid, "type": "term", "label": t["label"], "entity": t["entity"],
                      "decks": t["decks"], "slides": len(t["slides"])})
        edges.extend({"type": "mentions", "from": sid, "to": tid} for sid in t["slides"])

    digest = hashlib.sha256("|".join(f"{d['file']}:{d.get('digest', '')}" for d in decks)
                            .encode()).hexdigest()[:16]
    return {
        "version": GRAPH_VERSION, "digest": digest,
        "decks": len(decks), "slides": sum(len(d["slides"]) for d in decks),
        "summary": {
            "roles": _ranked(role_count),
            "arc": arc,
            "sections": _sections(decks),
            "visuals": [{"value": v, "count": len(visual_slides[v])}
                        for v in sorted(visual_slides, key=lambda v: (-len(visual_slides[v]), v))],
            "preferred_diagram_kinds": preferred_diagram_kinds_of(decks),
            "terms": [{k: t[k] for k in ("term", "label", "entity", "decks")} |
                      {"slides": len(t["slides"])} for t in terms],
        },
        "nodes": nodes, "edges": edges,
    }


def dumps(graph: dict[str, Any]) -> str:
    return json.dumps(graph, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def write(slug: str, graph: dict[str, Any]) -> str:
    from .kit import kit_dir
    path = os.path.join(kit_dir(slug), GRAPH_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps(graph))
    return path


def norms_from_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """The few graph facts other parts of the engine act on (into learned norms)."""
    s = graph["summary"]
    arc = s["arc"]
    return {
        "preferred_diagram_kinds": s["preferred_diagram_kinds"][:4],
        "arc": {
            "stages": [st["role"] for st in arc["stages"]],
            "opens": arc["first"][0]["value"] if arc["first"] else None,
            "closes": arc["last"][0]["value"] if arc["last"] else None,
            "ask_position": arc["ask"]["position_median"],
            "ask_share": (round(arc["ask"]["decks_with_ask"] / arc["ask"]["decks"], 3)
                          if arc["ask"]["decks"] else None),
        },
        "section_size": s["sections"]["size_median"],
    }


# ---- query API ---------------------------------------------------------------

Graphish = Union[str, dict]


def load(slug: str) -> Optional[dict[str, Any]]:
    from .kit import kit_dir
    path = os.path.join(kit_dir(slug), GRAPH_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _g(x: Graphish) -> dict[str, Any]:
    g = load(x) if isinstance(x, str) else x
    if not g:
        raise LookupError("no graph yet — run learning on the kit's examples")
    return g


def arc(x: Graphish) -> dict[str, Any]:
    """How the company's decks run: stage roles, openers, closers, the ask."""
    return _g(x)["summary"]["arc"]


def sections(x: Graphish) -> dict[str, Any]:
    return _g(x)["summary"]["sections"]


def preferred_kinds(x: Graphish) -> list[str]:
    """Diagram kinds the decks use, most used first (diagram.KINDS names)."""
    return list(_g(x)["summary"]["preferred_diagram_kinds"])


def terms(x: Graphish, limit: int = 20, entities: Optional[bool] = None) -> list[dict[str, Any]]:
    """Recurring terms, with the slides each appears on."""
    g = _g(x)
    where: dict[str, list[str]] = defaultdict(list)
    for e in g["edges"]:
        if e["type"] == "mentions":
            where[e["to"]].append(e["from"])
    out = []
    for n in g["nodes"]:
        if n["type"] != "term" or (entities is not None and n["entity"] != entities):
            continue
        out.append({"term": n["id"][5:], "label": n["label"], "entity": n["entity"],
                    "decks": n["decks"], "slides": where[n["id"]]})
    return out[:limit]


def slide(x: Graphish, sid: str) -> Optional[dict[str, Any]]:
    return next((n for n in _g(x)["nodes"] if n["type"] == "slide" and n["id"] == sid), None)


def slides_using(x: Graphish, what: str) -> list[str]:
    """Slide ids that use `what`: a role ("chart"), a visual ("smartart",
    "chart:column", "table"), a diagram kind ("timeline"), a chart family
    prefix ("chart") or a recurring term ("net retention")."""
    g = _g(x)
    w = what.strip().lower()
    targets = {f"role:{w}", f"visual:{w}", f"term:{w}"}
    if w in DIAGRAM_KINDS or w in _DIAGRAM_ALIASES:
        targets.add(f"visual:diagram:{_DIAGRAM_ALIASES.get(w, w)}")
    prefix = f"visual:{w}:" if w in ("chart", "diagram") else None
    out: list[str] = []
    for e in g["edges"]:
        if e["type"] in ("is", "uses", "mentions") and (
                e["to"] in targets or (prefix and e["to"].startswith(prefix))):
            if e["from"] not in out:
                out.append(e["from"])
    return sorted(out, key=_sid_key)


def summary(x: Graphish) -> dict[str, Any]:
    g = _g(x)
    return {"version": g["version"], "digest": g["digest"], "decks": g["decks"],
            "slides": g["slides"],
            "files": [{"id": n["id"], "file": n["file"], "slides": n["slides"]}
                      for n in g["nodes"] if n["type"] == "deck"],
            **g["summary"]}


# ---- optional model pass: label, never invent -------------------------------

_DESCRIBE_SYSTEM = (
    "You label patterns in a company's slide decks. You are given measured facts "
    "with slide ids. Reply with JSON only: {\"claims\": [{\"text\": str, \"slides\": "
    "[slide ids]}]}. At most 6 claims, each under 25 words, each citing only slide "
    "ids from the facts. Say nothing the facts do not show.")


def _facts(g: dict[str, Any]) -> list[dict[str, Any]]:
    """The measured claims, each with its slide ids. Also the no-model answer."""
    out = []
    a = g["summary"]["arc"]
    by_role: dict[str, list[str]] = defaultdict(list)
    for n in g["nodes"]:
        if n["type"] == "slide":
            by_role[n["role"]].append(n["id"])
    if a["first"]:
        r = a["first"][0]["value"]
        out.append({"text": f"Decks open with a {r} slide.",
                    "slides": [s for s in by_role[r] if s.endswith(".s1")]})
    if a["ask"]["slides"]:
        pos = a["ask"]["position_median"]
        out.append({"text": f"The ask lands about {round(pos * 100)}% of the way through.",
                    "slides": list(a["ask"]["slides"])})
    for k in g["summary"]["preferred_diagram_kinds"][:2]:
        out.append({"text": f"The decks draw {k} diagrams.",
                    "slides": slides_using(g, k)})
    for t in terms(g, limit=3):
        out.append({"text": f"“{t['label']}” recurs across {t['decks']} deck(s).",
                    "slides": t["slides"]})
    return [f for f in out if f["slides"]]


def _validate_claims(raw: Any, ids: set[str]) -> list[dict[str, Any]]:
    claims = raw.get("claims") if isinstance(raw, dict) else None
    out = []
    for c in claims or []:
        if not isinstance(c, dict):
            continue
        text = str(c.get("text") or "").strip()
        cited = [str(s) for s in (c.get("slides") or []) if isinstance(s, str)]
        if not text or len(text) > 240 or not cited or any(s not in ids for s in cited):
            continue                              # an uncited or miscited claim is dropped
        out.append({"text": text, "slides": cited})
    return out[:6]


def describe(x: Graphish, llm: Optional[Callable[[str, str], str]] = None) -> dict[str, Any]:
    """Short labelled claims about the decks, every one citing real slide ids.

    The model only names what the measured facts already show; any claim
    citing a slide that does not exist (or none) is dropped. No model, or
    nothing valid back, and the measured facts are the answer.
    """
    g = _g(x)
    facts = _facts(g)
    ids = {n["id"] for n in g["nodes"] if n["type"] == "slide"}
    if llm is None:
        from . import narrative
        if not narrative.available():
            return {"source": "measured", "claims": facts}
        llm = narrative.call
    prompt = json.dumps({"facts": facts, "roles": g["summary"]["roles"],
                         "stages": g["summary"]["arc"]["stages"]}, ensure_ascii=False)
    try:
        text = llm(prompt, _DESCRIBE_SYSTEM)
        m = re.search(r"\{.*\}", text or "", re.S)
        claims = _validate_claims(json.loads(m.group(0)) if m else None, ids)
    except Exception:
        claims = []
    if not claims:
        return {"source": "measured", "claims": facts}
    return {"source": "model", "claims": claims}
