"""
Diagram engine invariants (deckengine/diagram.py).

Measured, not eyeballed — the same contract layout.py keeps:
- Content carries no geometry; content that tries is refused.
- Every box lies inside the box it was given (margins).
- No two boxes overlap.
- No connector passes through a box it does not start or end at.
- Connectors start and end on (or just short of) their own boxes.
- Every label fits: the engine's own line breaks, at its own font size.
- Same content + box → same geometry (deterministic).
- The .pptx export draws native shapes, the preview gets the same geometry.
- Text → diagram reads structure and invents nothing.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches

from deckengine import diagram as D
from deckengine.boundary import diagram_to_px
from deckengine.render import add_diagram
from scripts.diagram_gallery import CASES

BOXES = [(0.6, 1.5, 12.1, 5.4), (0.5, 2.0, 8.0, 3.2), (6.8, 1.6, 5.9, 4.8)]
EPS = 1e-6


def _all():
    for name, content in CASES.items():
        for box in BOXES:
            yield name, content, box, D.resolve(content, box)


def _inside(r, box, tol=0.02):
    x, y, w, h = r
    bx, by, bw, bh = box
    return x >= bx - tol and y >= by - tol and x + w <= bx + bw + tol and y + h <= by + bh + tol


def _overlap(a, b, pad=0.0):
    return (a[0] < b[0] + b[2] - pad and b[0] < a[0] + a[2] - pad and
            a[1] < b[1] + b[3] - pad and b[1] < a[1] + a[3] - pad)


def _seg_hits_rect(p, q, r, shrink=0.03):
    """Does the axis-aligned (or general) segment pq enter r's interior?"""
    x0, y0, x1, y1 = r[0] + shrink, r[1] + shrink, r[0] + r[2] - shrink, r[1] + r[3] - shrink
    if x1 <= x0 or y1 <= y0:
        return False
    steps = 40
    for i in range(steps + 1):
        t = i / steps
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if x0 < x < x1 and y0 < y < y1:
            return True
    return False


def test_content_refuses_geometry():
    for bad in ({"kind": "flow", "nodes": [{"label": "a", "x": 1}]},
                {"kind": "flow", "nodes": ["a", "b"], "edges": [{"from": "n1", "to": "n2", "points": []}]},
                {"kind": "flow", "steps": ["a", "b"], "color": "#fff"}):
        try:
            D.from_dict(bad)
        except D.DiagramError:
            continue
        raise AssertionError(f"geometry accepted: {bad}")


def test_round_trip_carries_no_geometry():
    for content in CASES.values():
        out = D.to_dict(D.from_dict(content))
        text = json.dumps(out)
        for key in ('"x"', '"y"', '"w"', '"h"', '"points"', '"width"', '"height"'):
            assert key not in text, f"{key} leaked into content"
        assert D.to_dict(D.from_dict(out)) == out, "content does not round-trip"


def test_boxes_inside_their_frame():
    for name, _, box, rd in _all():
        for n in rd.nodes:
            assert _inside((n.x, n.y, n.w, n.h), box), f"{name}: {n.id} leaves the frame {box}"
        for t in rd.texts:
            assert _inside((t.x, t.y, t.w, t.h), box), f"{name}: text {t.text!r} leaves the frame"


def test_no_two_boxes_overlap():
    for name, _, box, rd in _all():
        rects = [(n.id, (n.x, n.y, n.w, n.h)) for n in rd.nodes if n.shape != "dot"]
        for i, (a, ra) in enumerate(rects):
            for b, rb in rects[i + 1:]:
                assert not _overlap(ra, rb, pad=0.01), f"{name} {box}: {a} overlaps {b}"


def test_connectors_never_cross_a_box():
    for name, _, box, rd in _all():
        if rd.kind in ("cycle",):
            continue        # arcs are sampled curves, covered by the endpoint test
        rects = {n.id: (n.x, n.y, n.w, n.h) for n in rd.nodes}
        for e in rd.edges:
            for p, q in zip(e.points, e.points[1:]):
                for nid, r in rects.items():
                    if nid in (e.src, e.dst):
                        continue
                    assert not _seg_hits_rect(p, q, r), \
                        f"{name} {box}: edge {e.src}->{e.dst} crosses {nid}"


def test_connectors_touch_their_own_boxes():
    for name, _, box, rd in _all():
        rects = {n.id: (n.x, n.y, n.w, n.h) for n in rd.nodes}
        for e in rd.edges:
            assert len(e.points) >= 2, f"{name}: edge with one point"
            near = lambda p, r, tol: (r[0] - tol <= p[0] <= r[0] + r[2] + tol and
                                      r[1] - tol <= p[1] <= r[1] + r[3] + tol)
            tol = 0.25 if rd.kind == "cycle" else 0.05
            assert near(e.points[0], rects[e.src], tol), f"{name}: {e.src}->{e.dst} starts away from {e.src}"
            assert near(e.points[-1], rects[e.dst], tol), f"{name}: {e.src}->{e.dst} ends away from {e.dst}"


def test_connectors_are_orthogonal_where_promised():
    for name, _, box, rd in _all():
        if rd.kind not in ("flow", "swimlane", "hierarchy"):
            continue
        for e in rd.edges:
            for p, q in zip(e.points, e.points[1:]):
                assert abs(p[0] - q[0]) < EPS or abs(p[1] - q[1]) < EPS, \
                    f"{name}: {e.src}->{e.dst} has a diagonal run"


def test_labels_fit_their_boxes():
    for name, _, box, rd in _all():
        assert D.FONT_MIN_PT <= rd.font_pt <= D.FONT_MAX_PT
        for n in rd.nodes:
            if not n.lines:
                continue
            width = D._inner_w(n.w if n.shape != "poly" else n.w * 0.36, n.shape)
            for ln in n.lines:
                assert D.text_w_in(ln, rd.font_pt) <= width + 0.02 or ln.endswith("…"), \
                    f"{name}: {ln!r} wider than {n.id}"
            assert len(n.lines) <= D.MAX_LINES


def test_deterministic():
    for name, content in CASES.items():
        a = D.resolve(content, BOXES[0]).to_dict()
        b = D.resolve(json.loads(json.dumps(content)), BOXES[0]).to_dict()
        assert a == b, f"{name} is not deterministic"


def test_too_many_boxes_is_an_honest_error():
    try:
        D.resolve({"kind": "matrix", "steps": list("abcde")}, BOXES[0])
    except D.DiagramError as e:
        assert "split" in str(e)
        return
    raise AssertionError("a 2x2 with five quadrants was accepted")


def test_decisions_are_diamonds_and_loops_route_outside():
    rd = D.resolve(CASES["flow with a decision, a loop and a skip"], BOXES[0])
    shapes = {n.id: n.shape for n in rd.nodes}
    assert shapes["b"] == "diamond"
    loop = next(e for e in rd.edges if (e.src, e.dst) == ("d", "b"))
    lowest = max(n.y + n.h for n in rd.nodes)
    assert max(p[1] for p in loop.points) > lowest, "the loop back should run below the boxes"


def test_long_chain_wraps_instead_of_shrinking():
    rd = D.resolve(CASES["long chain wraps"], BOXES[0])
    rows = {round(n.y, 3) for n in rd.nodes}
    assert len(rows) == 2, "an eight-step chain should read as two rows"
    assert rd.font_pt >= 14


def test_pptx_export_is_native_shapes():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rd = D.resolve(CASES["flow with a decision, a loop and a skip"], BOXES[0])
    add_diagram(s, rd, D.palette("FFFFFF", "1E2761", "11120E", "F96167"))
    kinds = [sh.shape_type for sh in s.shapes]
    assert MSO_SHAPE_TYPE.PICTURE not in kinds, "diagram exported as a picture"
    texts = [sh.text_frame.text for sh in s.shapes if sh.has_text_frame and sh.text_frame.text]
    for label in ("Request comes in", "Approved?", "Ship it", "Rework the draft", "Done", "yes", "no"):
        assert label in texts, f"{label!r} missing from the export"
    buf = io.BytesIO()
    prs.save(buf)
    Presentation(io.BytesIO(buf.getvalue()))   # opens


def test_preview_gets_the_same_geometry():
    rd = D.resolve(CASES["swimlane"], (0, 0, 11.556, 3.111))
    px = diagram_to_px(rd, 54.0)
    for n_in, n_px in zip(rd.nodes, px["nodes"]):
        assert abs(n_in.x * 54 - n_px["x"]) < 0.01 and abs(n_in.w * 54 - n_px["w"]) < 0.01
        assert n_px["lines"] == n_in.lines, "the preview must not re-wrap labels"


def test_palette_reads_on_both_backgrounds():
    for bg in ("FFFFFF", "12130F"):
        pal = D.palette(bg, "0E5B36", "11120E" if bg == "FFFFFF" else "FAF7EF", "E26A2C")
        for role in ("hero", "step", "muted"):
            fill, on = pal[role], pal[f"on_{role}"]
            assert abs(D._luma(fill) - D._luma(on)) > 0.3, f"{role} text unreadable on {bg}"
    # an accent that matches the background must not vanish
    pal = D.palette("1F497D", "1F497D", "FFFFFF")
    assert abs(D._luma(pal["step"]) - D._luma("1F497D")) > 0.2


def test_template_cast_draws_inside_the_templates_slot():
    """With a template, the template decides WHERE (its slot); the engine
    decides the boxes inside it. Placeholders the slide keeps never move."""
    from deckengine.native import render_native, layout_roles
    sample = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "frontend", "samples", "sample.pptx")
    out = "/tmp/deckengine-diagram-native.pptx"
    slide = {"kind": "diagram", "title": "How approvals work",
             "diagram": CASES["flow with a decision, a loop and a skip"]}
    render_native([slide], out, sample)
    sl = Presentation(out).slides[0]
    placeholders = [sh for sh in sl.shapes if sh.is_placeholder]
    drawn = [sh for sh in sl.shapes if not sh.is_placeholder]
    assert drawn, "nothing drawn"
    assert all(sh.shape_type != MSO_SHAPE_TYPE.PICTURE for sh in drawn), "diagram cast as a picture"
    texts = {" ".join(sh.text_frame.text.split()) for sh in drawn if sh.has_text_frame}
    assert {"Request comes in", "Approved?", "Done"} <= texts
    assert not any("…" in t for t in texts), f"a label was cut short in the template's slot: {texts}"
    layout = sl.slide_layout
    slots = [ph for ph in layout.placeholders if int(ph.placeholder_format.type) in (18, 2, 7)]
    assert slots, "sample layout has no slot"
    x0 = min(ph.left for ph in slots); y0 = min(ph.top for ph in slots)
    x1 = max(ph.left + ph.width for ph in slots); y1 = max(ph.top + ph.height for ph in slots)
    tol = Inches(0.05)
    for sh in drawn:
        assert sh.left >= x0 - tol and sh.top >= y0 - tol and \
            sh.left + sh.width <= x1 + tol and sh.top + sh.height <= y1 + tol, \
            f"{sh.name} drawn outside the template's slot"
    by_idx = {ph.placeholder_format.idx: ph for ph in layout.placeholders}
    for ph in placeholders:
        src = by_idx.get(ph.placeholder_format.idx)
        if src is not None:
            assert (ph.left, ph.top, ph.width, ph.height) == (src.left, src.top, src.width, src.height), \
                "a cast slide moved the template's placeholder"


# ── text → diagram ────────────────────────────────────────────────────────


def test_extract_arrows_with_decision_and_loop():
    d = D.extract("show the approval flow: Request -> Approved? -(yes)-> Ship; "
                  "Approved? -(no)-> Rework -> Approved?")
    assert d["kind"] == "flow"
    labels = [n["label"] for n in d["nodes"]]
    assert labels == ["Request", "Approved?", "Ship", "Rework"]
    pairs = {(e["from"], e["to"], e.get("label", "")) for e in d["edges"]}
    assert ("n2", "n3", "yes") in pairs and ("n2", "n4", "no") in pairs and ("n4", "n2", "") in pairs
    assert D.from_dict(d).nodes[1].role == "decision"


def test_extract_kinds():
    assert D.extract("Roadmap:\n- Q1 2026: Pilot\n- Q2 2026: Rollout\n- Q3 2026: Launch")["kind"] == "timeline"
    assert D.extract("Sales: qualify lead\nLegal: review terms\nFinance: approve\nSales: close")["kind"] == "swimlane"
    tree = D.extract("org chart:\n- CEO\n  - CTO\n    - Platform\n  - CFO")
    assert tree["kind"] == "hierarchy" and len(tree["edges"]) == 3
    loop = D.extract("draw the flywheel: more users, then more data, then better model, then more users")
    assert loop["kind"] == "cycle" and len(loop["nodes"]) == 3, "a cycle that names its start again closes, not repeats"
    assert D.extract("make a 2x2: quick wins, big bets, fill-ins, money pits")["kind"] == "matrix"
    assert D.extract("our funnel: visitors, sign-ups, active users and paying customers")["kind"] == "funnel"
    assert D.extract("How onboarding works:\n1. Sign\n2. Kickoff\n3. Import\n4. Go live")["kind"] == "flow"


def test_extract_invents_nothing():
    text = "Lead -> Qualify -> Demo -> Close"
    d = D.extract(text)
    assert D.grounded(d, text)
    fake = {"kind": "flow", "nodes": [{"label": "Lead"}, {"label": "Procurement security review"}]}
    assert not D.grounded(fake, text)
    # a model that invents a step is overruled by the deterministic reading
    invented = lambda prompt, system: json.dumps(fake)
    assert D.extract_with_model(text, invented) == D.extract(text)


if __name__ == "__main__":
    tests = [(k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
