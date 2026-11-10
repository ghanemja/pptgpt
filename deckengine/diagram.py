"""diagram.py — diagrams as content, laid out by the engine.

A flowchart, a cycle, an org tree, a timeline, a 2x2, a funnel, a swimlane.
Each is CONTENT first: what the boxes say and what connects to what. The
model (or a person, or `extract`) supplies that and nothing else — no
positions, sizes or colours. `resolve` turns it into geometry inside a box,
deterministically, the same way `layout.py` resolves a slide:

    content (Diagram)  +  box (inches)  ->  ResolvedDiagram (inches)

Everything that draws a diagram reads a ResolvedDiagram: the .pptx renderer
(`render.add_diagram`, native shapes and connectors you can edit in
PowerPoint), the template cast (`native.py`) and the workspace preview
(through `boundary.diagram_to_px`, drawn verbatim as SVG). One layout, three
consumers — the preview and the export cannot disagree about where a box is.

Layout rules, kind by kind:

  flow       layered (Sugiyama-style): break cycles, longest-path layers,
             barycenter ordering, orthogonal edges. Edges that skip a layer
             or run backwards travel in channels outside the node band, so
             no edge ever crosses a box. A long single chain wraps into two
             rows rather than shrinking to unreadable.
  swimlane   flow layering on x, one band per lane on y.
  hierarchy  tidy tree, top-down (left-right when it is wide and shallow),
             bus-style elbows from parent to children.
  cycle      nodes evenly round an ellipse, arcs between neighbours.
  timeline   events evenly along an axis, labels alternating sides when
             crowded, dates beside the marker.
  matrix     a 2x2: four quadrants, optional axis names.
  funnel     stacked stages, each narrower than the last.

Text is measured, not guessed per call: one font size is chosen for the
whole diagram, the largest that lets every label wrap inside its box in at
most three lines. The UI never wraps a label itself — it gets the lines.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

KINDS = ("flow", "swimlane", "hierarchy", "cycle", "timeline", "matrix", "funnel")

_ALIASES = {
    "process": "flow", "flowchart": "flow", "flow chart": "flow", "decision": "flow",
    "pipeline": "flow", "workflow": "flow", "steps": "flow", "sequence": "flow",
    "tree": "hierarchy", "org": "hierarchy", "orgchart": "hierarchy", "org chart": "hierarchy",
    "loop": "cycle", "flywheel": "cycle", "circle": "cycle",
    "roadmap": "timeline", "milestones": "timeline",
    "2x2": "matrix", "quadrant": "matrix", "quadrants": "matrix",
    "lanes": "swimlane", "swimlanes": "swimlane", "swim lane": "swimlane",
}

# How many nodes a kind can carry on one slide and stay readable. Past this
# the honest answer is two slides, not a smaller font.
MAX_NODES = {"flow": 12, "swimlane": 12, "hierarchy": 13, "cycle": 8,
             "timeline": 8, "matrix": 4, "funnel": 6}

ROLES = ("step", "start", "end", "decision", "hero")

# Keys that would smuggle geometry or styling into content (R0.1).
_GEOMETRY_KEYS = {"x", "y", "w", "h", "width", "height", "left", "top", "pos",
                  "position", "coords", "size", "font_size", "fontsize",
                  "color", "colour", "fill", "points"}

# Type and spacing constants (inches / points). Constraints, not suggestions.
FONT_MAX_PT = 18.0
FONT_MIN_PT = 9.0
MAX_LINES = 3
LINE_H = 1.18            # line height as a multiple of the font size
CHAR_W = 0.56            # average glyph width as a fraction of the em (bold sans)
PAD_X_IN = 0.10          # text inset inside a node
PAD_Y_IN = 0.07
NODE_W_MAX_IN = 2.4
MIN_NODE_H_IN = 0.62     # a box shorter than this reads as a label, not a box
EDGE_GAP_IN = 0.02       # arrowheads stop just short of the box they point at


class DiagramError(ValueError):
    """Content that cannot be drawn as asked (too many nodes, bad ids)."""


# ── content ───────────────────────────────────────────────────────────────


@dataclass
class Node:
    id: str
    label: str
    sub: str = ""              # a second, smaller line: a date, an owner, a number
    group: str = ""            # swimlane lane
    role: str = "step"         # step | start | end | decision | hero


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""


@dataclass
class Diagram:
    kind: str = "flow"
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    x_axis: str = ""           # matrix only: what left→right means
    y_axis: str = ""           # matrix only: what bottom→top means


def _check_no_geometry(obj: Any, where: str) -> None:
    if isinstance(obj, dict):
        bad = sorted(k for k in obj if str(k).lower() in _GEOMETRY_KEYS)
        if bad:
            raise DiagramError(f"{where} carries geometry/styling ({', '.join(bad)}); "
                               "diagram content may not position or colour anything")


def normalize_kind(kind: Any) -> str:
    k = str(kind or "flow").strip().lower()
    k = _ALIASES.get(k, k)
    return k if k in KINDS else "flow"


def from_dict(raw: dict[str, Any]) -> Diagram:
    """Content dict (from the UI, the model, or a stored slide) → Diagram.

    Accepts the legacy `{kind, steps: [...]}` shape: steps become a chain.
    Rejects anything that tries to carry geometry.
    """
    if not isinstance(raw, dict):
        raise DiagramError("diagram must be an object")
    _check_no_geometry(raw, "diagram")
    kind = normalize_kind(raw.get("kind"))

    nodes: list[Node] = []
    seen: set[str] = set()
    raw_nodes = raw.get("nodes")
    if not raw_nodes and raw.get("steps"):
        raw_nodes = [{"label": s} for s in raw.get("steps") or []]
    for i, rn in enumerate(raw_nodes or []):
        if isinstance(rn, str):
            rn = {"label": rn}
        if not isinstance(rn, dict):
            continue
        _check_no_geometry(rn, f"node {i}")
        label = " ".join(str(rn.get("label") or "").split())
        if not label:
            continue
        nid = str(rn.get("id") or f"n{i + 1}")
        if nid in seen:
            nid = f"{nid}_{i + 1}"
        seen.add(nid)
        role = str(rn.get("role") or "step").lower()
        if role not in ROLES:
            role = "step"
        if role == "step" and label.endswith("?") and kind in ("flow", "swimlane"):
            role = "decision"
        nodes.append(Node(id=nid, label=label, sub=" ".join(str(rn.get("sub") or "").split()),
                          group=str(rn.get("group") or rn.get("lane") or "").strip(), role=role))

    if not nodes:
        raise DiagramError("diagram has no nodes")
    limit = MAX_NODES[kind]
    if len(nodes) > limit:
        raise DiagramError(f"a {kind} holds at most {limit} boxes on one slide "
                           f"({len(nodes)} given) — split it across two slides")

    ids = {n.id for n in nodes}
    edges: list[Edge] = []
    raw_edges = raw.get("edges")
    if raw_edges is None:
        raw_edges = []
        if kind in ("flow", "swimlane", "cycle"):
            raw_edges = [{"from": a.id, "to": b.id} for a, b in zip(nodes, nodes[1:])]
            if kind == "cycle" and len(nodes) > 2:
                raw_edges.append({"from": nodes[-1].id, "to": nodes[0].id})
    for i, re_ in enumerate(raw_edges or []):
        if not isinstance(re_, dict):
            continue
        _check_no_geometry(re_, f"edge {i}")
        s = str(re_.get("from") if re_.get("from") is not None else re_.get("src", ""))
        d = str(re_.get("to") if re_.get("to") is not None else re_.get("dst", ""))
        if s not in ids or d not in ids:
            raise DiagramError(f"edge {i} connects unknown node ({s!r} → {d!r})")
        if s == d:
            continue
        edges.append(Edge(src=s, dst=d, label=" ".join(str(re_.get("label") or "").split())))

    return Diagram(kind=kind, nodes=nodes, edges=edges,
                   x_axis=str(raw.get("x_axis") or raw.get("xAxis") or "").strip(),
                   y_axis=str(raw.get("y_axis") or raw.get("yAxis") or "").strip())


def to_dict(d: Diagram) -> dict[str, Any]:
    out: dict[str, Any] = {
        "kind": d.kind,
        "nodes": [{k: v for k, v in asdict(n).items() if v not in ("", None) or k in ("id", "label")}
                  for n in d.nodes],
        "edges": [{"from": e.src, "to": e.dst, **({"label": e.label} if e.label else {})}
                  for e in d.edges],
    }
    if d.x_axis:
        out["x_axis"] = d.x_axis
    if d.y_axis:
        out["y_axis"] = d.y_axis
    return out


def labels(raw: Optional[dict[str, Any]]) -> list[str]:
    """Every piece of text a diagram puts on the slide (for the coach)."""
    if not raw:
        return []
    try:
        d = from_dict(raw)
    except DiagramError:
        return [str(s) for s in (raw.get("steps") or []) if str(s).strip()]
    out = []
    for n in d.nodes:
        out.append(n.label)
        if n.sub:
            out.append(n.sub)
    out.extend(e.label for e in d.edges if e.label)
    return out


# ── resolved geometry ─────────────────────────────────────────────────────


@dataclass
class RNode:
    id: str
    x: float
    y: float
    w: float
    h: float
    shape: str                  # rect | diamond | hexagon | dot | poly
    fill: str                   # palette role: hero | step | decision | muted | none
    lines: list[str] = field(default_factory=list)
    sub_lines: list[str] = field(default_factory=list)
    points: list[tuple[float, float]] = field(default_factory=list)   # poly only


@dataclass
class REdge:
    src: str
    dst: str
    points: list[tuple[float, float]]
    arrow: bool = True
    label: str = ""
    label_box: Optional[tuple[float, float, float, float]] = None     # x, y, w, h


@dataclass
class RText:
    text: str
    x: float
    y: float
    w: float
    h: float
    align: str = "center"       # left | center | right
    role: str = "muted"         # ink | muted
    scale: float = 0.85         # relative to the diagram's font size


@dataclass
class RBand:
    label: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class ResolvedDiagram:
    kind: str
    box: tuple[float, float, float, float]
    font_pt: float
    nodes: list[RNode] = field(default_factory=list)
    edges: list[REdge] = field(default_factory=list)
    texts: list[RText] = field(default_factory=list)
    bands: list[RBand] = field(default_factory=list)
    guides: list[list[tuple[float, float]]] = field(default_factory=list)  # axis lines
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── text measurement ──────────────────────────────────────────────────────


def text_w_in(text: str, pt: float) -> float:
    return len(text) * CHAR_W * pt / 72.0


def line_h_in(pt: float) -> float:
    return pt * LINE_H / 72.0


def wrap(text: str, width_in: float, pt: float, max_lines: int = MAX_LINES) -> Optional[list[str]]:
    """Greedy word wrap. None when a word or the line count does not fit."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    cur = ""
    for w in words:
        if text_w_in(w, pt) > width_in:
            return None
        cand = f"{cur} {w}" if cur else w
        if text_w_in(cand, pt) <= width_in:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines if len(lines) <= max_lines else None


def _force_wrap(text: str, width_in: float, pt: float) -> list[str]:
    """Last resort at the minimum size: wrap, then ellipsize the last line."""
    max_chars = max(3, int(width_in / (CHAR_W * pt / 72.0)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        w = w if len(w) <= max_chars else w[: max_chars - 1] + "…"
        cand = f"{cur} {w}" if cur else w
        if len(cand) <= max_chars:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        lines[-1] = (lines[-1][: max_chars - 1]).rstrip() + "…"
    return lines


def _text_height(n_lines: int, n_sub: int, pt: float) -> float:
    return n_lines * line_h_in(pt) + n_sub * line_h_in(pt * 0.8) + 2 * PAD_Y_IN


def _inner_w(w: float, shape: str) -> float:
    # A diamond's usable text width at mid-height is about half its width;
    # a hexagon (the fallback decision shape) loses only its pointed ends.
    factor = {"diamond": 0.58, "hexagon": 0.78}.get(shape, 1.0)
    return max(0.1, w * factor - 2 * PAD_X_IN)


def fit_font(items: list[tuple[str, str, float, str]], max_h: float) -> tuple[float, dict, bool]:
    """Largest common size that fits every (key, label, width, shape) item.

    Returns (pt, {key: (lines, sub_lines)}, fitted). `items` labels are the
    main label; sub text rides in the label after a '\\n'.
    """
    pt = FONT_MAX_PT
    while pt >= FONT_MIN_PT - 1e-9:
        out, ok = {}, True
        for key, text, width, shape in items:
            main, _, sub = text.partition("\n")
            iw = _inner_w(width, shape)
            ml = wrap(main, iw, pt)
            sl = wrap(sub, iw, pt * 0.8, 2) if sub else []
            if ml is None or sl is None or _text_height(len(ml), len(sl), pt) > max_h + 1e-9:
                ok = False
                break
            out[key] = (ml, sl)
        if ok:
            return pt, out, True
        pt -= 0.5
    pt = FONT_MIN_PT
    out = {}
    for key, text, width, shape in items:
        main, _, sub = text.partition("\n")
        iw = _inner_w(width, shape)
        out[key] = (_force_wrap(main, iw, pt), _force_wrap(sub, iw, pt * 0.8)[:2] if sub else [])
    return pt, out, False


def _needed_h(lines_map: dict, pt: float, shape_of: Callable[[str], str]) -> float:
    h = 0.0
    for key, (ml, sl) in lines_map.items():
        need = _text_height(len(ml), len(sl), pt)
        if shape_of(key) == "diamond":
            need *= 1.6
        h = max(h, need)
    return h


def _label_text(n: Node) -> str:
    return f"{n.label}\n{n.sub}" if n.sub else n.label


def _fill_for(n: Node, hero_default: bool) -> str:
    if n.role == "hero" or (hero_default and n.role == "start"):
        return "hero"
    if n.role == "decision":
        return "decision"
    if n.role == "end":
        return "muted"
    return "step"


# ── layered layout (flow, swimlane) ───────────────────────────────────────


def _layering(d: Diagram) -> tuple[dict[str, int], set[tuple[str, str]]]:
    """Longest-path layers after DFS cycle breaking. Returns (layer, back_edges)."""
    order = [n.id for n in d.nodes]
    out: dict[str, list[str]] = {i: [] for i in order}
    for e in d.edges:
        out[e.src].append(e.dst)

    back: set[tuple[str, str]] = set()
    state: dict[str, int] = {}

    def dfs(v: str) -> None:
        state[v] = 1
        for w in out[v]:
            if state.get(w) == 1:
                back.add((v, w))
            elif w not in state:
                dfs(w)
        state[v] = 2

    for v in order:
        if v not in state:
            dfs(v)

    fwd = [(e.src, e.dst) for e in d.edges if (e.src, e.dst) not in back]
    layer = {v: 0 for v in order}
    for _ in range(len(order)):
        changed = False
        for s, t in fwd:
            if layer[t] < layer[s] + 1:
                layer[t] = layer[s] + 1
                changed = True
        if not changed:
            break
    return layer, back


def _order_layers(d: Diagram, layer: dict[str, int]) -> list[list[str]]:
    n_layers = max(layer.values()) + 1
    layers: list[list[str]] = [[] for _ in range(n_layers)]
    for n in d.nodes:
        layers[layer[n.id]].append(n.id)
    nbrs: dict[str, list[str]] = {n.id: [] for n in d.nodes}
    for e in d.edges:
        nbrs[e.src].append(e.dst)
        nbrs[e.dst].append(e.src)

    def pos_map() -> dict[str, float]:
        return {v: i for L in layers for i, v in enumerate(L)}

    for sweep in range(4):
        rng = range(1, n_layers) if sweep % 2 == 0 else range(n_layers - 2, -1, -1)
        for li in rng:
            ref = li - 1 if sweep % 2 == 0 else li + 1
            p = pos_map()
            def bary(v: str) -> float:
                ns = [p[u] for u in nbrs[v] if layer[u] == ref]
                return sum(ns) / len(ns) if ns else p[v]
            layers[li] = sorted(layers[li], key=lambda v: (bary(v), p[v]))
    return layers


@dataclass
class _Lay:
    """Node placement in layer space: u along layers, v across them."""
    u: float
    v: float
    su: float      # size along u
    sv: float      # size along v


def _route_layered(d: Diagram, layer: dict[str, int], back: set, place: dict[str, _Lay],
                   gaps: list[tuple[float, float]], shapes: dict[str, str],
                   chan_lo: float, chan_hi: float, corridor: Optional[Callable[[str, int], float]] = None
                   ) -> list[tuple[Edge, list[tuple[float, float]]]]:
    """Orthogonal routes in (u, v). `gaps[i]` is the free u-interval after layer i
    (gaps[-1]... handled by index i+1 offset: gaps[0] is BEFORE layer 0)."""
    # Ports: spread edges along a node's in/out side, ordered by the other end.
    outs: dict[str, list[Edge]] = {n.id: [] for n in d.nodes}
    ins: dict[str, list[Edge]] = {n.id: [] for n in d.nodes}
    for e in d.edges:
        outs[e.src].append(e)
        ins[e.dst].append(e)

    def port_v(nid: str, e: Edge, side: dict[str, list[Edge]], other: Callable[[Edge], str]) -> float:
        p = place[nid]
        if shapes[nid] in ("diamond", "hexagon"):
            return p.v + p.sv / 2
        lst = sorted(side[nid], key=lambda x: (place[other(x)].v, d.edges.index(x)))
        k, n = lst.index(e), len(lst)
        span = p.sv * 0.6
        return p.v + p.sv / 2 - span / 2 + span * (k + 1) / (n + 1)

    # Vertical segments claim a track inside a gap; tracks are spread so two
    # elbows in the same gap never share a line.
    claims: dict[int, list[Edge]] = {}

    def claim(g: int, e: Edge) -> None:
        claims.setdefault(g, []).append(e)

    plan = []
    lo_k, hi_k = 0, 0
    for e in d.edges:
        a, b = layer[e.src], layer[e.dst]
        is_back = (e.src, e.dst) in back or b <= a
        if not is_back and b == a + 1:
            plan.append((e, "adj", a + 1, None))
            claim(a + 1, e)
        elif not is_back:
            plan.append((e, "long", (a + 1, b), lo_k))
            claim(a + 1, e)
            claim(b, e)
            lo_k += 1
        else:
            plan.append((e, "back", (a + 1, b), hi_k))
            claim(a + 1, e)
            claim(b, e)
            hi_k += 1

    def track(g: int, e: Edge, key: Callable[[Edge], float]) -> float:
        lst = sorted(claims[g], key=lambda x: (key(x), d.edges.index(x)))
        k, n = lst.index(e), len(lst)
        g0, g1 = gaps[g]
        return g0 + (g1 - g0) * (k + 1) / (n + 1)

    routes = []
    for e, mode, g, k in plan:
        ps, pd = place[e.src], place[e.dst]
        u1 = ps.u + ps.su
        u2 = pd.u - EDGE_GAP_IN
        v1 = port_v(e.src, e, outs, lambda x: x.dst)
        v2 = port_v(e.dst, e, ins, lambda x: x.src)
        if mode == "adj":
            if abs(v1 - v2) < 0.15 and ps.v + 0.06 < v2 < ps.v + ps.sv - 0.06:
                v1 = v2           # nearly level: run straight rather than jog
            if abs(v1 - v2) < 0.01:
                pts = [(u1, v1), (u2, v1)]
            else:
                um = track(g, e, lambda x: place[x.dst].v)
                pts = [(u1, v1), (um, v1), (um, v2), (u2, v2)]
        else:
            ga, gb = g
            um1 = track(ga, e, lambda x: place[x.dst].v)
            um2 = track(gb, e, lambda x: place[x.src].v)
            if corridor is not None:
                vc = corridor(e.dst if mode == "long" else e.src, k)
            elif mode == "long":
                vc = chan_lo - 0.12 * k
            else:
                vc = chan_hi + 0.12 * k
            pts = [(u1, v1), (um1, v1), (um1, vc), (um2, vc), (um2, v2), (u2, v2)]
        routes.append((e, _dedupe(pts)))
    return routes


def _dedupe(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or abs(out[-1][0] - p[0]) > 1e-6 or abs(out[-1][1] - p[1]) > 1e-6:
            out.append(p)
    # drop collinear midpoints
    i = 1
    while i < len(out) - 1:
        (ax, ay), (bx, by), (cx, cy) = out[i - 1], out[i], out[i + 1]
        if (abs(ax - bx) < 1e-6 and abs(bx - cx) < 1e-6) or (abs(ay - by) < 1e-6 and abs(by - cy) < 1e-6):
            out.pop(i)
        else:
            i += 1
    return out


def _edge_label_box(pts: list[tuple[float, float]], text: str, pt: float) -> tuple[float, float, float, float]:
    """Edge label: above the longest horizontal run when there is room for
    it, otherwise beside the last segment on the side the route did not come
    from — never on top of a line."""
    w = text_w_in(text, pt * 0.8) + 0.08
    h = line_h_in(pt * 0.8)
    runs = [(abs(q[0] - p[0]), i) for i, (p, q) in enumerate(zip(pts, pts[1:]))
            if abs(p[1] - q[1]) < 1e-6]
    if runs:
        length, i = max(runs)
        if length >= w + 0.5 and i > 0:
            (px, py), (qx, qy) = pts[i], pts[i + 1]
            return ((px + qx) / 2 - w / 2, py - h - 0.03, w, h)
    (ax, ay), (bx, by) = pts[-2], pts[-1]
    if abs(ay - by) < 1e-6:     # horizontal
        cx = bx - min(abs(bx - ax) / 2, 0.08 + w / 2) * (1 if bx > ax else -1)
        # Sit on the side the route did NOT arrive from, so the label never
        # lands on the vertical run that feeds this segment.
        came_from_above = len(pts) >= 3 and pts[-3][1] < ay - 1e-6
        y = ay + 0.03 if came_from_above else ay - h - 0.03
        return (cx - w / 2, y, w, h)
    cy = by - min(abs(by - ay) / 2, 0.08 + h / 2) * (1 if by > ay else -1)
    return (ax + 0.05, cy - h / 2, w, h)


def _resolve_layered(d: Diagram, box: tuple[float, float, float, float],
                     rd: ResolvedDiagram) -> None:
    bx, by, bw, bh = box
    swim = d.kind == "swimlane"
    layer, back = _layering(d)

    lanes: list[str] = []
    if swim:
        for n in d.nodes:
            if n.group not in lanes:
                lanes.append(n.group)
        # Two boxes cannot share a lane in the same column: push the later one
        # a column right, then re-propagate so edges still run forward.
        fwd = [(e.src, e.dst) for e in d.edges if (e.src, e.dst) not in back]
        grp = {n.id: n.group for n in d.nodes}
        for _ in range(len(d.nodes) * 2):
            taken: dict[tuple[str, int], str] = {}
            moved = False
            for n in d.nodes:
                key = (grp[n.id], layer[n.id])
                if key in taken:
                    layer[n.id] += 1
                    moved = True
                else:
                    taken[key] = n.id
            for _ in range(len(d.nodes)):
                ch = False
                for s, t in fwd:
                    if layer[t] < layer[s] + 1:
                        layer[t] = layer[s] + 1
                        ch = True
                if not ch:
                    break
            if not moved:
                break

    n_layers = max(layer.values()) + 1
    chain = (not swim and len(d.edges) == len(d.nodes) - 1 and n_layers == len(d.nodes)
             and all(layer[e.dst] == layer[e.src] + 1 for e in d.edges))

    if chain and len(d.nodes) > 5:
        _resolve_snake(d, box, rd)
        return

    layers = _order_layers(d, layer) if not swim else \
        [[n.id for n in d.nodes if layer[n.id] == li] for li in range(n_layers)]
    widest = max(len(L) for L in layers)
    shapes = {n.id: ("diamond" if n.role == "decision" else "rect") for n in d.nodes}
    by_id = {n.id: n for n in d.nodes}

    horizontal = swim or n_layers <= 6 and (n_layers >= widest or widest <= 3) or n_layers <= 2
    has_long = any(layer[e.dst] - layer[e.src] >= 2 for e in d.edges if (e.src, e.dst) not in back)
    has_back = bool(back) or any(layer[e.dst] <= layer[e.src] for e in d.edges)

    lane_label_w = 0.0
    if swim:
        lane_label_w = min(1.4, max(0.7, max(text_w_in(l or "—", 11) for l in lanes) + 0.25))

    # main axis = along layers, cross axis = across them
    main_len = (bw - lane_label_w) if horizontal else bh
    cross_len = bh if horizontal else bw
    margin = 0.22 if has_back else 0.0
    gap_main = max(0.32, min(0.6, main_len * 0.07))
    node_main = (main_len - 2 * margin - (n_layers - 1) * gap_main) / n_layers
    node_main = min(node_main, NODE_W_MAX_IN if horizontal else 1.1)
    used_main = n_layers * node_main + (n_layers - 1) * gap_main
    start_main = (bx + lane_label_w if horizontal else by) + (main_len - used_main) / 2

    lo_chan = 0.09 * sum(1 for e in d.edges if (e.src, e.dst) not in back
                         and layer[e.dst] - layer[e.src] >= 2) + (0.08 if has_long else 0)
    hi_chan = 0.09 * sum(1 for e in d.edges if (e.src, e.dst) in back
                         or layer[e.dst] <= layer[e.src]) + (0.08 if has_back else 0)
    if swim:
        lo_chan = hi_chan = 0.0
    lo_chan = lo_chan and lo_chan + 0.25
    hi_chan = hi_chan and hi_chan + 0.25
    band_cross = cross_len - lo_chan - hi_chan
    cross0 = (by if horizontal else bx) + lo_chan

    if swim:
        slot_cross = band_cross / max(1, len(lanes))
        node_cross_max = slot_cross * 0.62
    else:
        gap_cross = 0.22
        node_cross_max = (band_cross - (widest - 1) * gap_cross) / widest

    # Node width/height in real x/y for text fitting. A decision is a
    # diamond when its words fit one at a readable size; when they do not
    # (a narrow column, a long question) it becomes a hexagon — still a
    # different shape from a step, and it holds nearly a full line.
    def fit_with(shp: dict[str, str], width: float, cap: float):
        its = [(n.id, _label_text(n), width, shp[n.id]) for n in d.nodes]
        return fit_font(its, cap / (1.6 if "diamond" in shp.values() else 1.0))

    if horizontal:
        node_w = node_main
        h_cap = min(node_cross_max, 1.4)
        pt, lines_map, fitted = fit_with(shapes, node_w, h_cap)
        if "diamond" in shapes.values() and (not fitted or pt < 12):
            shapes = {k: ("hexagon" if v == "diamond" else v) for k, v in shapes.items()}
            pt, lines_map, fitted = fit_with(shapes, node_w, h_cap)
        # Fill the room a little: sparse diagrams get chunkier boxes, never
        # taller than the text needs by more than a comfortable margin.
        roomy = min(1.1, 0.34 * band_cross / max(1, widest))
        node_h = min(h_cap, max(MIN_NODE_H_IN, roomy, _needed_h(lines_map, pt, shapes.get)))
        su, sv = node_w, node_h
    else:
        node_h = node_main
        node_w = min(node_cross_max, NODE_W_MAX_IN)
        pt, lines_map, fitted = fit_with(shapes, node_w, node_h)
        if "diamond" in shapes.values() and (not fitted or pt < 12):
            shapes = {k: ("hexagon" if v == "diamond" else v) for k, v in shapes.items()}
            pt, lines_map, fitted = fit_with(shapes, node_w, node_h)
        su, sv = node_h, node_w
    if not fitted:
        rd.warnings.append("labels shortened to fit — consider fewer words per box")
    rd.font_pt = pt

    place: dict[str, _Lay] = {}
    lane_band: dict[str, tuple[float, float]] = {}
    if swim:
        for i, ln in enumerate(lanes):
            lane_band[ln] = (cross0 + i * slot_cross, slot_cross)
            rd.bands.append(RBand(label=ln, x=bx, y=cross0 + i * slot_cross, w=bw, h=slot_cross))
            rd.texts.append(RText(text=ln, x=bx + 0.08, y=cross0 + i * slot_cross,
                                  w=lane_label_w - 0.12, h=slot_cross, align="left", role="ink",
                                  scale=0.8))
    for li, L in enumerate(layers):
        u = start_main + li * (node_main + gap_main)
        if swim:
            for nid in L:
                c0, cs = lane_band[by_id[nid].group]
                place[nid] = _Lay(u=u, v=c0 + (cs - sv) / 2, su=su, sv=sv)
        else:
            gap_c = 0.22 if len(L) > 1 else 0.0
            total = len(L) * sv + (len(L) - 1) * gap_c
            spare = band_cross - total
            v = cross0 + spare / 2
            for nid in L:
                place[nid] = _Lay(u=u, v=v, su=su, sv=sv)
                v += sv + gap_c

    gaps = [(start_main - margin, start_main - 0.04)]
    for li in range(n_layers - 1):
        a = start_main + li * (node_main + gap_main) + node_main
        gaps.append((a, a + gap_main))
    end = start_main + used_main
    gaps.append((end + 0.04, end + margin))

    corridor = None
    if swim:
        def corridor(nid: str, k: int) -> float:
            c0, _ = lane_band[by_id[nid].group]
            room = max(0.08, (cs - sv) / 2)
            return c0 + min(0.22, room * 0.5) + 0.07 * (k % 3)

    v_lo = min(p.v for p in place.values())
    v_hi = max(p.v + p.sv for p in place.values())
    routes = _route_layered(d, layer, back, place, gaps, shapes,
                            chan_lo=max(cross0 - lo_chan + 0.02, v_lo - 0.22) if lo_chan else v_lo,
                            chan_hi=min(cross0 + band_cross + hi_chan - 0.02, v_hi + 0.22) if hi_chan else v_hi,
                            corridor=corridor)

    def xy(u: float, v: float) -> tuple[float, float]:
        return (u, v) if horizontal else (v, u)

    for n in d.nodes:
        p = place[n.id]
        x, y = xy(p.u, p.v)
        w, h = (p.su, p.sv) if horizontal else (p.sv, p.su)
        ml, sl = lines_map[n.id]
        pts: list[tuple[float, float]] = []
        if shapes[n.id] == "hexagon":
            k = min(h * 0.4, w * 0.11)
            pts = [(x + k, y), (x + w - k, y), (x + w, y + h / 2), (x + w - k, y + h),
                   (x + k, y + h), (x, y + h / 2)]
        rd.nodes.append(RNode(id=n.id, x=x, y=y, w=w, h=h, shape=shapes[n.id],
                              fill=_fill_for(n, hero_default=True), lines=ml, sub_lines=sl,
                              points=pts))
    for e, pts in routes:
        real = [xy(u, v) for u, v in pts]
        lb = _edge_label_box(real, e.label, pt) if e.label else None
        rd.edges.append(REdge(src=e.src, dst=e.dst, points=real, label=e.label, label_box=lb))


def _resolve_snake(d: Diagram, box: tuple[float, float, float, float], rd: ResolvedDiagram) -> None:
    """A long single chain in two rows, read left to right, then left to right again."""
    bx, by, bw, bh = box
    n = len(d.nodes)
    per = math.ceil(n / 2)
    gap_x = max(0.3, min(0.55, bw * 0.06))
    node_w = min(NODE_W_MAX_IN, (bw - (per - 1) * gap_x) / per)
    row_gap = 0.38
    h_cap = min(1.3, (bh - row_gap) / 2)
    items = [(x.id, _label_text(x), node_w, "rect") for x in d.nodes]
    pt, lines_map, fitted = fit_font(items, h_cap)
    if not fitted:
        rd.warnings.append("labels shortened to fit — consider fewer words per box")
    rd.font_pt = pt
    node_h = min(h_cap, max(MIN_NODE_H_IN, _needed_h(lines_map, pt, lambda _: "rect")))
    used_w = per * node_w + (per - 1) * gap_x
    x0 = bx + (bw - used_w) / 2
    y0 = by + (bh - (2 * node_h + row_gap)) / 2
    pos = {}
    for i, nd in enumerate(d.nodes):
        r, c = divmod(i, per)
        x = x0 + c * (node_w + gap_x)
        y = y0 + r * (node_h + row_gap)
        pos[nd.id] = (x, y)
        ml, sl = lines_map[nd.id]
        rd.nodes.append(RNode(id=nd.id, x=x, y=y, w=node_w, h=node_h, shape="rect",
                              fill=_fill_for(nd, hero_default=True), lines=ml, sub_lines=sl))
    for e in d.edges:
        (sx, sy), (tx, ty) = pos[e.src], pos[e.dst]
        if abs(sy - ty) < 1e-6:
            pts = [(sx + node_w, sy + node_h / 2), (tx - EDGE_GAP_IN, ty + node_h / 2)]
        else:     # row turn: down out of the last box, back along the gap, down into the first
            ym = sy + node_h + row_gap / 2
            pts = [(sx + node_w / 2, sy + node_h), (sx + node_w / 2, ym),
                   (tx + node_w / 2, ym), (tx + node_w / 2, ty - EDGE_GAP_IN)]
        lb = _edge_label_box(pts, e.label, pt) if e.label else None
        rd.edges.append(REdge(src=e.src, dst=e.dst, points=_dedupe(pts), label=e.label, label_box=lb))


# ── hierarchy ─────────────────────────────────────────────────────────────


def _resolve_hierarchy(d: Diagram, box: tuple[float, float, float, float], rd: ResolvedDiagram) -> None:
    bx, by, bw, bh = box
    ids = [n.id for n in d.nodes]
    parent: dict[str, str] = {}
    kids: dict[str, list[str]] = {i: [] for i in ids}
    for e in d.edges:
        if e.dst in parent or e.dst == e.src:
            rd.warnings.append(f"{e.src}→{e.dst} dropped: a tree box has one parent")
            continue
        # refuse an edge that would close a loop
        a = e.src
        loop = False
        while a in parent:
            a = parent[a]
            if a == e.dst:
                loop = True
                break
        if loop or e.src == e.dst:
            rd.warnings.append(f"{e.src}→{e.dst} dropped: it would make a loop")
            continue
        parent[e.dst] = e.src
        kids[e.src].append(e.dst)
    roots = [i for i in ids if i not in parent]

    depth: dict[str, int] = {}
    slot: dict[str, float] = {}
    counter = [0]

    def walk(v: str, dep: int) -> None:
        depth[v] = dep
        if not kids[v]:
            slot[v] = counter[0]
            counter[0] += 1
            return
        for c in kids[v]:
            walk(c, dep + 1)
        slot[v] = (slot[kids[v][0]] + slot[kids[v][-1]]) / 2

    for r in roots:
        walk(r, 0)
    n_slots = max(1, counter[0])
    n_levels = max(depth.values()) + 1
    horizontal = n_slots > 6 and n_levels <= 4      # wide and shallow: grow left to right

    main_len, cross_len = (bw, bh) if horizontal else (bh, bw)
    gap_main = max(0.3, min(0.55, main_len * 0.08))
    node_main = (main_len - (n_levels - 1) * gap_main) / n_levels
    node_main = min(node_main, NODE_W_MAX_IN if horizontal else 1.0)
    cell = cross_len / n_slots
    node_cross = min(cell * 0.86, NODE_W_MAX_IN if not horizontal else 1.0)

    w = node_main if horizontal else node_cross
    h_cap = node_cross if horizontal else node_main
    items = [(n.id, _label_text(n), w, "rect") for n in d.nodes]
    pt, lines_map, fitted = fit_font(items, h_cap)
    if not fitted:
        rd.warnings.append("labels shortened to fit — consider fewer words per box")
    rd.font_pt = pt
    h = min(h_cap, max(MIN_NODE_H_IN, _needed_h(lines_map, pt, lambda _: "rect")))
    su, sv = (w, h) if horizontal else (h, w)
    used_main = n_levels * su + (n_levels - 1) * gap_main
    m0 = (bx if horizontal else by) + (main_len - used_main) / 2
    c0 = by if horizontal else bx

    place = {}
    for n in d.nodes:
        u = m0 + depth[n.id] * (su + gap_main)
        v = c0 + (slot[n.id] + 0.5) * cell - sv / 2
        place[n.id] = (u, v)

    def xy(u: float, v: float) -> tuple[float, float]:
        return (u, v) if horizontal else (v, u)

    for n in d.nodes:
        u, v = place[n.id]
        x, y = xy(u, v)
        ml, sl = lines_map[n.id]
        rd.nodes.append(RNode(id=n.id, x=x, y=y, w=w, h=h, shape="rect",
                              fill="hero" if n.id in roots else _fill_for(n, hero_default=False),
                              lines=ml, sub_lines=sl))
    for c, p in parent.items():
        (pu, pv), (cu, cv) = place[p], place[c]
        um = pu + su + gap_main / 2
        pts = [(pu + su, pv + sv / 2), (um, pv + sv / 2), (um, cv + sv / 2), (cu - EDGE_GAP_IN, cv + sv / 2)]
        real = _dedupe([xy(a, b) for a, b in pts])
        e = next(x for x in d.edges if x.src == p and x.dst == c)
        lb = _edge_label_box(real, e.label, pt) if e.label else None
        rd.edges.append(REdge(src=p, dst=c, points=real, label=e.label, label_box=lb))


# ── cycle ─────────────────────────────────────────────────────────────────


def _resolve_cycle(d: Diagram, box: tuple[float, float, float, float], rd: ResolvedDiagram) -> None:
    bx, by, bw, bh = box
    n = len(d.nodes)
    cx, cy = bx + bw / 2, by + bh / 2
    node_w = min(NODE_W_MAX_IN, bw * (0.3 if n <= 4 else 0.24))
    node_h = 0.0
    pt, lines_map = FONT_MAX_PT, {}
    for _ in range(40):
        h_cap = min(1.1, bh * 0.3)
        items = [(x.id, _label_text(x), node_w, "rect") for x in d.nodes]
        pt, lines_map, fitted = fit_font(items, h_cap)
        node_h = min(h_cap, max(MIN_NODE_H_IN, _needed_h(lines_map, pt, lambda _: "rect")))
        rx, ry = bw / 2 - node_w / 2, bh / 2 - node_h / 2
        th = [-math.pi / 2 + 2 * math.pi * i / n for i in range(n)]
        centers = [(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in th]
        clash = any(abs(centers[i][0] - centers[(i + 1) % n][0]) < node_w + 0.12 and
                    abs(centers[i][1] - centers[(i + 1) % n][1]) < node_h + 0.12
                    for i in range(n)) if n > 1 else False
        if not clash:
            break
        node_w *= 0.92
    if not fitted:
        rd.warnings.append("labels shortened to fit — consider fewer words per box")
    rd.font_pt = pt
    rects = {}
    for nd, (x, y) in zip(d.nodes, centers):
        r = (x - node_w / 2, y - node_h / 2, node_w, node_h)
        rects[nd.id] = r
        ml, sl = lines_map[nd.id]
        rd.nodes.append(RNode(id=nd.id, x=r[0], y=r[1], w=node_w, h=node_h, shape="rect",
                              fill=_fill_for(nd, hero_default=False), lines=ml, sub_lines=sl))
    idx = {nd.id: i for i, nd in enumerate(d.nodes)}

    def inside(p: tuple[float, float], r: tuple[float, float, float, float], pad: float = 0.06) -> bool:
        return r[0] - pad <= p[0] <= r[0] + r[2] + pad and r[1] - pad <= p[1] <= r[1] + r[3] + pad

    for e in d.edges:
        i, j = idx[e.src], idx[e.dst]
        t0, t1 = th[i], th[j]
        if j == (i + 1) % n:
            if t1 <= t0:
                t1 += 2 * math.pi
            samples = [t0 + (t1 - t0) * k / 48 for k in range(49)]
            arc = [(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in samples]
            pts = [p for p in arc if not inside(p, rects[e.src]) and not inside(p, rects[e.dst])]
        else:   # a chord: straight, clipped to the two boxes
            (ax, ay), (bx2, by2) = centers[i], centers[j]
            line = [(ax + (bx2 - ax) * k / 48, ay + (by2 - ay) * k / 48) for k in range(49)]
            pts = [p for p in line if not inside(p, rects[e.src]) and not inside(p, rects[e.dst])]
        if len(pts) < 2:
            continue
        pts = pts[::4] + ([pts[-1]] if (len(pts) - 1) % 4 else [])
        lb = _edge_label_box(pts, e.label, pt) if e.label else None
        rd.edges.append(REdge(src=e.src, dst=e.dst, points=pts, label=e.label, label_box=lb))


# ── timeline ──────────────────────────────────────────────────────────────


def _resolve_timeline(d: Diagram, box: tuple[float, float, float, float], rd: ResolvedDiagram) -> None:
    bx, by, bw, bh = box
    n = len(d.nodes)
    alternate = n >= 5
    cell = bw / n
    # Alternating sides lets a label borrow its neighbours' width — but only
    # up to 1.6 cells: the first and last labels are pushed inward by the
    # frame edge, and wider than 5/3 of a cell they would hit the label two
    # along on the same side.
    label_w = min(NODE_W_MAX_IN, cell * (1.6 if alternate else 0.9))
    axis_y = by + bh / 2
    date_h = 0.26
    side_h = bh / 2 - date_h - 0.12
    items = [(x.id, x.label, label_w, "rect") for x in d.nodes]
    pt, lines_map, fitted = fit_font(items, min(1.2, side_h))
    if not fitted:
        rd.warnings.append("labels shortened to fit — consider fewer words per box")
    rd.font_pt = pt
    node_h = min(side_h, max(0.5, _needed_h(lines_map, pt, lambda _: "rect")))
    rd.guides.append([(bx, axis_y), (bx + bw, axis_y)])
    dot = 0.14
    for i, nd in enumerate(d.nodes):
        cxi = bx + cell * (i + 0.5)
        below = (i % 2 == 0) if alternate else True
        rd.nodes.append(RNode(id=f"{nd.id}__dot", x=cxi - dot / 2, y=axis_y - dot / 2, w=dot, h=dot,
                              shape="dot", fill="hero" if nd.role == "hero" else "step"))
        ly = axis_y + date_h + 0.06 if below else axis_y - date_h - 0.06 - node_h
        lx = min(max(bx, cxi - label_w / 2), bx + bw - label_w)
        ml, _ = lines_map[nd.id]
        rd.nodes.append(RNode(id=nd.id, x=lx, y=ly, w=label_w, h=node_h, shape="rect",
                              fill=_fill_for(nd, hero_default=False), lines=ml))
        if nd.sub:
            ty = axis_y + 0.06 if below else axis_y - date_h - 0.02
            dw = min(cell * 0.96 if not alternate else 2 * cell - 0.1, text_w_in(nd.sub, pt) + 0.2)
            rd.texts.append(RText(text=nd.sub, x=cxi - dw / 2, y=ty, w=dw, h=date_h,
                                  align="center", role="ink", scale=0.85))
        y_from = axis_y + dot / 2 if below else axis_y - dot / 2
        y_to = ly if below else ly + node_h
        if not nd.sub:
            rd.edges.append(REdge(src=f"{nd.id}__dot", dst=nd.id,
                                  points=[(cxi, y_from), (cxi, y_to)], arrow=False))


# ── matrix ────────────────────────────────────────────────────────────────


def _resolve_matrix(d: Diagram, box: tuple[float, float, float, float], rd: ResolvedDiagram) -> None:
    bx, by, bw, bh = box
    axis_band = 0.3 if (d.x_axis or d.y_axis) else 0.0
    gx, gy, gw, gh = bx, by + axis_band, bw, bh - 2 * axis_band
    gap = 0.1
    qw, qh = (gw - gap) / 2, (gh - gap) / 2
    items = [(x.id, _label_text(x), qw, "rect") for x in d.nodes]
    pt, lines_map, fitted = fit_font(items, qh)
    if not fitted:
        rd.warnings.append("labels shortened to fit — consider fewer words per box")
    rd.font_pt = pt
    any_hero = any(n.role == "hero" for n in d.nodes)
    for i, nd in enumerate(d.nodes):
        r, c = divmod(i, 2)
        ml, sl = lines_map[nd.id]
        rd.nodes.append(RNode(id=nd.id, x=gx + c * (qw + gap), y=gy + r * (qh + gap), w=qw, h=qh,
                              shape="rect", fill=("hero" if nd.role == "hero" else "muted") if any_hero
                              else "step", lines=ml, sub_lines=sl))
    if d.y_axis:
        rd.texts.append(RText(text=f"↑ {d.y_axis}", x=bx, y=by, w=bw / 2, h=axis_band,
                              align="left", role="muted"))
    if d.x_axis:
        rd.texts.append(RText(text=f"{d.x_axis} →", x=bx + bw / 2, y=by + bh - axis_band,
                              w=bw / 2, h=axis_band, align="right", role="muted"))


# ── funnel ────────────────────────────────────────────────────────────────


def _resolve_funnel(d: Diagram, box: tuple[float, float, float, float], rd: ResolvedDiagram) -> None:
    bx, by, bw, bh = box
    n = len(d.nodes)
    gap = 0.06
    band = (bh - (n - 1) * gap) / n
    cx = bx + bw / 2
    top_w, bot_w = min(bw, 7.5) * 0.96, min(bw, 7.5) * 0.36
    widths = [top_w - (top_w - bot_w) * i / n for i in range(n + 1)]
    items = [(x.id, _label_text(x), widths[i + 1] * 0.8, "rect") for i, x in enumerate(d.nodes)]
    pt, lines_map, fitted = fit_font(items, band)
    if not fitted:
        rd.warnings.append("labels shortened to fit — consider fewer words per box")
    rd.font_pt = pt
    for i, nd in enumerate(d.nodes):
        y0 = by + i * (band + gap)
        w0, w1 = widths[i], widths[i + 1]
        pts = [(cx - w0 / 2, y0), (cx + w0 / 2, y0), (cx + w1 / 2, y0 + band), (cx - w1 / 2, y0 + band)]
        ml, sl = lines_map[nd.id]
        rd.nodes.append(RNode(id=nd.id, x=cx - w0 / 2, y=y0, w=w0, h=band, shape="poly",
                              fill="hero" if i == 0 and nd.role != "end" else _fill_for(nd, False),
                              lines=ml, sub_lines=sl, points=pts))


# ── entry point ───────────────────────────────────────────────────────────

_RESOLVERS = {
    "flow": _resolve_layered,
    "swimlane": _resolve_layered,
    "hierarchy": _resolve_hierarchy,
    "cycle": _resolve_cycle,
    "timeline": _resolve_timeline,
    "matrix": _resolve_matrix,
    "funnel": _resolve_funnel,
}


def resolve(content: Diagram | dict[str, Any], box: tuple[float, float, float, float]) -> ResolvedDiagram:
    """Content + box (x, y, w, h in inches) → geometry. Deterministic."""
    d = content if isinstance(content, Diagram) else from_dict(content)
    x, y, w, h = (float(v) for v in box)
    if w <= 0.5 or h <= 0.3:
        raise DiagramError("box too small for a diagram")
    rd = ResolvedDiagram(kind=d.kind, box=(x, y, w, h), font_pt=FONT_MAX_PT)
    _RESOLVERS[d.kind](d, (x, y, w, h), rd)
    return rd


# ── text → diagram (deterministic first, model second) ────────────────────

_BULLET = re.compile(r"^\s*(?:[-*•▪◦]|\d+[.)]|[a-z][.)])\s+", re.I)
_DATE = re.compile(r"^\s*((?:Q[1-4]\s*'?\d{2,4})|(?:H[12]\s*'?\d{2,4})|(?:FY\s?'?\d{2,4})|(?:\d{4}(?:[-/]\d{1,2})?)|"
                   r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*'?\d{2,4})|"
                   r"(?:(?:week|wk|month|day|phase|sprint)\s*\d+))\s*[:—–\-]\s*(.+)$", re.I)
_LANE = re.compile(r"^\s*([A-Z][\w &/]{1,22}?)\s*:\s*(.+)$")
_CYCLE_WORDS = re.compile(r"\b(cycle|loop|flywheel|repeat|repeats|circular|iterat\w*)\b", re.I)
_FUNNEL_WORDS = re.compile(r"\bfunnel\b", re.I)
_MATRIX_WORDS = re.compile(r"\b(2x2|2 ?× ?2|quadrants?|matrix)\b", re.I)
_TREE_WORDS = re.compile(r"\b(org(?:anization|anisation)? ?chart|hierarchy|reports? to|tree)\b", re.I)
_TIMELINE_WORDS = re.compile(r"\b(timeline|roadmap|milestones?)\b", re.I)
_LEADIN = re.compile(r"^\s*(?:show|make|add|draw|give|include|build|create|put)\b.*?:\s*", re.I)


def _clean(s: str) -> str:
    return " ".join(_BULLET.sub("", s).strip().strip(".;,").split())


def extract(text: str) -> Optional[dict[str, Any]]:
    """Read a diagram out of plain text. Returns content or None.

    Understands, without a model:
      A -> B -> C            arrows (→ => > also), "A -(yes)-> B" labels an edge
      Is it approved? -> ...  a label ending in "?" is a decision
      1. a / - b             a list is a chain
      Sales: qualify         "Lane: step" lines with 2+ lanes are a swimlane
      Q1 2025: launch        dated lines are a timeline
      indented bullets        an indented list is a hierarchy
      "funnel" / "cycle" / "2x2" / "org chart" in the ask pick the kind
    Nothing is invented: every label comes from the text.
    """
    raw = str(text or "")
    if not raw.strip():
        return None
    ask = raw.split("\n", 1)[0]
    lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]

    # Explicit arrows anywhere.
    arrow_lines = [ln for ln in lines if re.search(r"->|→|=>|⇒", ln)]
    if arrow_lines:
        ids: dict[str, str] = {}
        nodes, edges = [], []

        def nid(label: str) -> str:
            key = label.lower()
            if key not in ids:
                ids[key] = f"n{len(ids) + 1}"
                nodes.append({"id": ids[key], "label": label})
            return ids[key]

        statements = [st for ln in arrow_lines for st in _LEADIN.sub("", _BULLET.sub("", ln)).split(";")]
        for ln in statements:
            # Tokens alternate: text, arrow, text, arrow, ... An arrow may carry
            # a label: "-(yes)->" or "--yes-->". Text after an arrow may fan
            # out: "A -> B, C" is A→B and A→C; the next arrow leaves both.
            parts = re.split(r"(-{1,2}\s*\([^()]{1,24}\)\s*-{0,2}>|--\s*[^<>\-]{1,24}?\s*-->|->|→|=>|⇒)", ln)
            prev: list[str] = []
            pending = ""
            for part in parts:
                tok = (part or "").strip()
                if not tok:
                    continue
                if tok in ("->", "→", "=>", "⇒"):
                    pending = ""
                    continue
                m = re.fullmatch(r"-{1,2}\s*\(([^()]{1,24})\)\s*-{0,2}>|--\s*([^<>\-]{1,24}?)\s*-->", tok)
                if m:
                    pending = (m.group(1) or m.group(2) or "").strip()
                    continue
                pieces = [p for p in re.split(r"\s*,\s*|\s*;\s*", tok)] if prev else [tok]
                cur = [nid(lbl) for lbl in (_clean(p) for p in pieces) if lbl]
                for s in prev:
                    for t in cur:
                        if s != t:
                            edges.append({"from": s, "to": t, **({"label": pending} if pending else {})})
                prev = cur or prev
                pending = ""
        if len(nodes) >= 2:
            kind = "cycle" if _CYCLE_WORDS.search(ask) else "flow"
            return {"kind": kind, "nodes": nodes[: MAX_NODES[kind]],
                    "edges": [e for e in edges if int(e["from"][1:]) <= MAX_NODES[kind]
                              and int(e["to"][1:]) <= MAX_NODES[kind]]}

    body = lines[1:] if len(lines) > 1 and not _BULLET.match(lines[0]) and lines[0].rstrip().endswith(":") else lines
    if len(lines) > 1 and _LEADIN.match(lines[0]) and not _BULLET.match(lines[0]):
        body = lines[1:]

    # Dated lines → timeline.
    dated = [m for m in (_DATE.match(_BULLET.sub("", ln)) for ln in body) if m]
    if len(dated) >= 2 and len(dated) >= len(body) * 0.6:
        return {"kind": "timeline",
                "nodes": [{"label": _clean(m.group(2)), "sub": m.group(1).strip()} for m in dated][:MAX_NODES["timeline"]]}

    # "Lane: step" lines → swimlane.
    laned = [m for m in (_LANE.match(_BULLET.sub("", ln)) for ln in body) if m]
    if len(laned) >= 3 and len({m.group(1).strip().lower() for m in laned}) >= 2 and len(laned) == len(body):
        nodes = [{"id": f"n{i + 1}", "label": _clean(m.group(2)), "group": m.group(1).strip()}
                 for i, m in enumerate(laned)][: MAX_NODES["swimlane"]]
        return {"kind": "swimlane", "nodes": nodes,
                "edges": [{"from": a["id"], "to": b["id"]} for a, b in zip(nodes, nodes[1:])]}

    # Indented list → hierarchy.
    bullets = [ln for ln in body if _BULLET.match(ln) or ln.startswith(("  ", "\t"))]
    indents = {len(ln) - len(ln.lstrip()) for ln in bullets}
    if len(bullets) >= 3 and len(indents) >= 2:
        nodes, edges, stack = [], [], []
        for i, ln in enumerate(bullets[: MAX_NODES["hierarchy"]]):
            ind = len(ln.replace("\t", "    ")) - len(ln.replace("\t", "    ").lstrip())
            nid_ = f"n{i + 1}"
            nodes.append({"id": nid_, "label": _clean(ln)})
            while stack and stack[-1][0] >= ind:
                stack.pop()
            if stack:
                edges.append({"from": stack[-1][1], "to": nid_})
            stack.append((ind, nid_))
        return {"kind": "hierarchy", "nodes": nodes, "edges": edges}

    # A flat list, or "a, then b, then c" → the kind the ask names (flow by default).
    items = [_clean(ln) for ln in body if _BULLET.match(ln)]
    if len(items) < 2:
        inline = _LEADIN.sub("", ask)
        parts = re.split(r"\s*(?:,\s*then\s+|\bthen\b|;|\s>\s|,\s*and finally\s+|,\s*finally\s+)\s*", inline)
        if len(parts) < 3:
            parts = re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", inline.split(":", 1)[-1])
        items = [_clean(p) for p in parts if _clean(p)]
    # A repeated label is the same box: drop runs, and a cycle that names its
    # start again at the end is closing the loop, not adding a step.
    items = [s for i, s in enumerate(items) if i == 0 or s.lower() != items[i - 1].lower()]
    if len(items) > 2 and items[-1].lower() == items[0].lower():
        items = items[:-1]
    if len(items) < 2:
        return None
    if _MATRIX_WORDS.search(ask):
        kind = "matrix"
    elif _FUNNEL_WORDS.search(ask):
        kind = "funnel"
    elif _CYCLE_WORDS.search(ask):
        kind = "cycle"
    elif _TIMELINE_WORDS.search(ask):
        kind = "timeline"
    elif _TREE_WORDS.search(ask):
        kind = "hierarchy"
        nodes = [{"id": f"n{i + 1}", "label": s} for i, s in enumerate(items[: MAX_NODES[kind]])]
        return {"kind": kind, "nodes": nodes,
                "edges": [{"from": "n1", "to": n["id"]} for n in nodes[1:]]}
    else:
        kind = "flow"
    return {"kind": kind, "nodes": [{"label": s} for s in items[: MAX_NODES[kind]]]}


_MODEL_SYSTEM = (
    "You turn a request into diagram CONTENT as JSON. Never positions, sizes or colours. "
    'Return only: {"kind": one of flow|swimlane|hierarchy|cycle|timeline|matrix|funnel, '
    '"nodes": [{"id","label","sub"?,"group"?,"role"?: step|start|end|decision|hero}], '
    '"edges": [{"from","to","label"?}], "x_axis"?, "y_axis"?}. '
    "Labels are 1-5 words copied or shortened from the text. Do not add steps the text does not contain."
)


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 2}


def grounded(content: dict[str, Any], source: str, min_share: float = 0.6) -> bool:
    """Anti-fabrication: most of each label's words must appear in the source."""
    src = _tokens(source)
    for n in content.get("nodes") or []:
        toks = _tokens(str(n.get("label") or ""))
        if toks and len(toks & src) / len(toks) < min_share:
            return False
    return True


def extract_with_model(text: str, call: Callable[[str, str], str]) -> Optional[dict[str, Any]]:
    """The model reads relationships prose implies (branches, loops, owners);
    the result is validated and grounded before it is trusted. Falls back to
    `extract` on anything doubtful."""
    import json
    try:
        raw = call(text, _MODEL_SYSTEM)
        m = re.search(r"\{.*\}", raw or "", re.S)
        content = json.loads(m.group(0)) if m else None
        if not isinstance(content, dict):
            return extract(text)
        d = from_dict(content)
        out = to_dict(d)
        return out if grounded(out, text) else extract(text)
    except Exception:
        return extract(text)


# ── colour roles (engine decides; renderers only apply) ───────────────────


def _hex(c: str) -> str:
    c = str(c or "").strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return c.upper() if re.fullmatch(r"[0-9a-fA-F]{6}", c) else "000000"


def _luma(c: str) -> float:
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _mix(a: str, b: str, t: float) -> str:
    """t=0 → a, t=1 → b."""
    pa = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    pb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(pa, pb))


def _on(fill: str, bg: str, ink: str) -> str:
    """Text colour that reads on `fill`: whichever of bg/ink contrasts more."""
    return bg if abs(_luma(bg) - _luma(fill)) > abs(_luma(ink) - _luma(fill)) else ink


def palette(bg: str, accent: str, ink: str, highlight: Optional[str] = None) -> dict[str, str]:
    """Palette roles for a diagram from a slide's colours. Hex without '#'.

    hero = the box the eye should land on first; step = every other box;
    muted = an end state or a quadrant that is not the point; band = lane
    backgrounds; line = connectors, quieter than text.
    """
    bg, accent, ink = _hex(bg), _hex(accent), _hex(ink)
    hero = _hex(highlight) if highlight else accent
    if abs(_luma(accent) - _luma(bg)) < 0.2:     # accent vanishes on this background
        accent = ink
    if abs(_luma(hero) - _luma(bg)) < 0.2:
        hero = accent
    muted = _mix(bg, accent, 0.28)
    return {
        "bg": bg, "ink": ink,
        "hero": hero, "step": accent, "decision": accent, "muted": muted,
        "on_hero": _on(hero, bg, ink), "on_step": _on(accent, bg, ink),
        "on_decision": _on(accent, bg, ink), "on_muted": _on(muted, bg, ink),
        "band": _mix(bg, accent, 0.07), "band_line": _mix(bg, ink, 0.18),
        "line": _mix(bg, ink, 0.62), "text": ink, "text_muted": _mix(bg, ink, 0.65),
    }
