"""
Kit graph tests (deckengine/kit_graph.py).

The contract:
- The same decks give a byte-identical graph.json; moving shapes around
  gives the same graph too, because positions are never read (R0.1), and no
  geometry key is ever written.
- Each slide gets a role from what it carries; the role sequence, openers,
  closers, ask position and section sizes are counted from those roles.
- SmartArt (by its layout id), connector diagrams (by topology), chevron
  rows with dates, charts (by type) and tables are detected, and diagrams
  are named with diagram.KINDS.
- The query functions answer from the graph alone; learn() feeds the arc
  and preferred diagram kinds into the norms, the house brief, the org
  profile and the coach.
- The optional model pass keeps only claims citing slides that exist.
"""
import asyncio
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.opc.constants import CONTENT_TYPE as CT, RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.util import Inches
from lxml import etree

from deckengine import coach as C
from deckengine import kit as K
from deckengine import kit_graph as KG
from deckengine import kit_ingest as KI
from deckengine import org as O

DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Default python-pptx template layouts.
L_TITLE, L_CONTENT, L_SECTION, L_TWO, L_TITLE_ONLY = 0, 1, 2, 3, 5

GEOMETRY_KEYS = {"x", "y", "w", "h", "left", "top", "width", "height", "pos", "position",
                 "offset", "off", "ext", "cx", "cy", "coords", "size"}


@contextmanager
def sandbox():
    with tempfile.TemporaryDirectory() as d:
        kits = os.path.join(d, "kits")
        os.makedirs(kits)
        with mock.patch.object(K, "KITS_DIR", kits), mock.patch.object(O, "KITS_DIR", kits):
            yield kits


def _smartart(slide, unique_id, nodes, at):
    """A SmartArt frame: graphicFrame + dgm relIds → layout and data parts."""
    pkg = slide.part.package
    n = len(slide.shapes) + 1
    lo = Part(PackURI(f"/ppt/diagrams/layout{n}_{id(slide)}.xml"), CT.DML_DIAGRAM_LAYOUT, pkg,
              f'<dgm:layoutDef xmlns:dgm="{DGM}" uniqueId="{unique_id}"/>'.encode())
    pts = "".join(f'<dgm:pt modelId="{i}"><dgm:t><a:bodyPr/><a:p><a:r><a:t>{t}</a:t></a:r>'
                  f'</a:p></dgm:t></dgm:pt>' for i, t in enumerate(nodes))
    dm = Part(PackURI(f"/ppt/diagrams/data{n}_{id(slide)}.xml"), CT.DML_DIAGRAM_DATA, pkg,
              f'<dgm:dataModel xmlns:dgm="{DGM}" xmlns:a="{A}"><dgm:ptLst>{pts}</dgm:ptLst>'
              f'</dgm:dataModel>'.encode())
    rlo = slide.part.relate_to(lo, RT.DIAGRAM_LAYOUT)
    rdm = slide.part.relate_to(dm, RT.DIAGRAM_DATA)
    xml = (f'<p:graphicFrame xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}">'
           f'<p:nvGraphicFramePr><p:cNvPr id="{900 + n}" name="Diagram {n}"/>'
           f'<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>'
           f'<p:xfrm><a:off x="{at}" y="{at}"/><a:ext cx="4000000" cy="3000000"/></p:xfrm>'
           f'<a:graphic><a:graphicData uri="{DGM}">'
           f'<dgm:relIds xmlns:dgm="{DGM}" r:dm="{rdm}" r:lo="{rlo}" r:qs="" r:cs=""/>'
           f'</a:graphicData></a:graphic></p:graphicFrame>')
    slide.shapes._spTree.append(etree.fromstring(xml))


def _title(prs, layout, title):
    s = prs.slides.add_slide(prs.slide_layouts[layout])
    s.shapes.title.text = title
    return s


def make_deck_one(path, shift=0):
    """Ten slides covering every role. `shift` moves every placed shape."""
    o = Inches(0.5 + shift)
    prs = Presentation()
    s = _title(prs, L_TITLE, "Net retention carries the plan")
    s.placeholders[1].text = "Board review, Q3"

    _title(prs, L_SECTION, "Where we are")

    s = _title(prs, L_CONTENT, "Net retention rose in every segment")
    s.placeholders[1].text_frame.text = "Enterprise net retention reached 118 percent"
    for t in ("Mid-market churn fell to under two percent", "Expansion revenue doubled since spring"):
        s.placeholders[1].text_frame.add_paragraph().text = t

    s = _title(prs, L_TITLE_ONLY, "Expansion revenue grew each quarter")
    cd = CategoryChartData()
    cd.categories = ["Q1", "Q2", "Q3"]
    cd.add_series("Expansion", (1.0, 1.4, 2.1))
    s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, o, Inches(1.5), Inches(6), Inches(4), cd)

    s = _title(prs, L_TITLE_ONLY, "Who owns the expansion motion")
    _smartart(s, "urn:microsoft.com/office/officeart/2005/8/layout/hierarchy1",
              ["Chief revenue officer", "Enterprise lead", "Mid-market lead"], int(o))

    s = _title(prs, L_TITLE_ONLY, "How a renewal moves")
    boxes = []
    for i, t in enumerate(("Usage review", "Renewal offer", "Signed contract")):
        b = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, o + Inches(3 * i), Inches(3), Inches(2), Inches(1))
        b.text_frame.text = t
        boxes.append(b)
    for a, b in zip(boxes, boxes[1:]):
        c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, 0, 0, 1, 1)
        c.begin_connect(a, 3)
        c.end_connect(b, 1)

    s = _title(prs, L_TITLE_ONLY, "Segment results against plan")
    tb = s.shapes.add_table(2, 2, o, Inches(2), Inches(6), Inches(2)).table
    tb.cell(0, 0).text, tb.cell(0, 1).text = "Segment", "Net retention"
    tb.cell(1, 0).text, tb.cell(1, 1).text = "Enterprise", "118%"

    _title(prs, L_SECTION, "What we propose")

    s = _title(prs, L_TWO, "Enterprise and mid-market need different plays")
    s.placeholders[1].text = "Enterprise needs dedicated success managers"
    s.placeholders[2].text = "Mid-market needs a pooled support model"

    s = _title(prs, L_TITLE_ONLY, "Approve the enterprise hire plan")
    s.shapes.add_textbox(o, Inches(2), Inches(8), Inches(1)).text_frame.text = \
        "Decision today"
    prs.save(path)


def make_deck_two(path, shift=0):
    o = Inches(0.4 + shift)
    prs = Presentation()
    s = _title(prs, L_TITLE, "Expansion roadmap")
    s.placeholders[1].text = "Net retention programme"
    s = _title(prs, L_TITLE_ONLY, "The rollout")
    for i, t in enumerate(("Q1 2026: pilot", "Q2 2026: two regions", "Q3 2026: everywhere")):
        sh = s.shapes.add_shape(MSO_SHAPE.CHEVRON, o + Inches(3 * i), Inches(3), Inches(3), Inches(1))
        sh.text_frame.text = t
    s = _title(prs, L_CONTENT, "Net retention is the measure")
    s.placeholders[1].text = "Expansion revenue counts only after renewal"
    s = _title(prs, L_TITLE_ONLY, "We recommend starting in Q1")
    s.shapes.add_textbox(o, Inches(2), Inches(8), Inches(1)).text_frame.text = "Approval needed"
    prs.save(path)


@contextmanager
def fixture_kit(shift=0):
    with sandbox() as kits:
        slug = K.create_kit("Graph Co")
        ex = os.path.join(kits, slug, "examples")
        make_deck_one(os.path.join(ex, "a-board.pptx"), shift)
        make_deck_two(os.path.join(ex, "b-roadmap.pptx"), shift)
        yield kits, slug


def _graph(shift=0):
    with fixture_kit(shift) as (kits, slug):
        KI.learn(slug)
        with open(os.path.join(kits, slug, "graph.json"), "rb") as fh:
            return fh.read()


_CACHE = {}


def graph():
    if "g" not in _CACHE:
        _CACHE["g"] = json.loads(_graph())
    return _CACHE["g"]


def _roles(g, deck):
    return [n["role"] for n in g["nodes"] if n["type"] == "slide" and n["deck"] == deck]


# ── determinism and geometry ────────────────────────────────────────────

def test_same_decks_give_a_byte_identical_graph():
    with fixture_kit() as (kits, slug):
        KI.learn(slug)
        first = open(os.path.join(kits, slug, "graph.json"), "rb").read()
        KI.learn(slug)
        second = open(os.path.join(kits, slug, "graph.json"), "rb").read()
    assert first == second


def test_moving_shapes_does_not_change_the_graph():
    def strip(raw):
        g = json.loads(raw)
        g.pop("digest")
        for n in g["nodes"]:
            n.pop("digest", None)
        return g
    assert strip(_graph(0)) == strip(_graph(1.5))


def test_no_geometry_is_stored():
    def walk(node, path="$"):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k.lower() not in GEOMETRY_KEYS, f"geometry key at {path}.{k}"
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(graph())


def test_graph_has_the_declared_node_and_edge_types():
    g = graph()
    assert {n["type"] for n in g["nodes"]} == {"deck", "slide", "role", "term", "visual"}
    assert {e["type"] for e in g["edges"]} == {"contains", "follows", "is", "uses", "mentions"}
    ids = {n["id"] for n in g["nodes"]}
    for e in g["edges"]:
        assert e["from"] in ids and e["to"] in ids, e


# ── roles, arc, sections ────────────────────────────────────────────────

def test_role_sequence_is_read_from_what_each_slide_carries():
    g = graph()
    assert _roles(g, "d1") == ["cover", "section", "bullets", "chart", "diagram", "diagram",
                               "table", "section", "two", "statement"]
    assert _roles(g, "d2") == ["cover", "diagram", "bullets", "statement"]


def test_transitions_openers_closers_and_ask_are_counted():
    a = KG.arc(graph())
    t = {(x["from"], x["to"]): x["count"] for x in a["transitions"]}
    assert t[("start", "cover")] == 2
    assert t[("diagram", "diagram")] == 1
    assert t[("statement", "end")] == 2
    assert t[("section", "bullets")] == 1 and t[("section", "two")] == 1
    assert a["first"] == [{"value": "cover", "count": 2}]
    assert a["last"] == [{"value": "statement", "count": 2}]
    assert a["ask"]["slides"] == ["d1.s10", "d2.s4"]
    assert a["ask"]["position_median"] == 1.0
    assert [s["stage"] for s in a["stages"]] == list(KG.STAGES)
    assert a["stages"][0]["role"] == "cover"


def test_role_follows_edges_carry_counts():
    g = graph()
    e = next(e for e in g["edges"] if e["type"] == "follows"
             and e["from"] == "role:cover" and e["to"] == "role:section")
    assert e["count"] == 1


def test_section_sizes():
    s = KG.sections(graph())
    d1 = s["decks"][0]
    assert d1["breaks"] == ["d1.s2", "d1.s8"]
    assert d1["sizes"] == [5, 2]
    assert d1["before_first"] == 1
    assert s["decks_with_sections"] == 1


# ── visual vocabulary ───────────────────────────────────────────────────

def test_smartart_is_detected_and_classified_by_its_layout():
    sl = KG.slide(graph(), "d1.s5")
    assert "smartart" in sl["visuals"] and "diagram:hierarchy" in sl["visuals"]
    assert sl["evidence"] == ["smartart:hierarchy1"]


def test_connected_boxes_are_a_flow_diagram():
    sl = KG.slide(graph(), "d1.s6")
    assert "connector" in sl["visuals"] and "diagram:flow" in sl["visuals"]
    assert sl["evidence"] == ["connectors:2"]


def test_connector_topology_names_the_kind():
    assert KG._topology_kind([("a", "b"), ("b", "c"), ("c", "a")], {}) == "cycle"
    assert KG._topology_kind([("a", "b"), ("a", "c"), ("b", "d")], {}) == "hierarchy"
    assert KG._topology_kind([("a", "b"), ("b", "c")],
                             {"a": "Q1", "b": "Q2", "c": "launch"}) == "timeline"
    assert KG._topology_kind([("a", "b"), ("b", "c")], {}) == "flow"


def test_dated_chevrons_are_a_timeline():
    sl = KG.slide(graph(), "d2.s2")
    assert "diagram:timeline" in sl["visuals"]
    assert sl["evidence"] == ["shapes:flowx3", "dates"]


def test_charts_are_recorded_by_type_and_tables_found():
    assert KG.slide(graph(), "d1.s4")["visuals"] == ["chart:column"]
    assert KG.slide(graph(), "d1.s7")["visuals"] == ["table"]


def test_preferred_diagram_kinds_use_the_diagram_engine_names():
    from deckengine.diagram import KINDS
    kinds = KG.preferred_kinds(graph())
    assert set(kinds) == {"hierarchy", "flow", "timeline"}
    assert all(k in KINDS for k in kinds)


# ── queries ─────────────────────────────────────────────────────────────

def test_slides_using_answers_roles_visuals_kinds_and_terms():
    g = graph()
    assert KG.slides_using(g, "chart") == ["d1.s4"]
    assert KG.slides_using(g, "chart:column") == ["d1.s4"]
    assert KG.slides_using(g, "smartart") == ["d1.s5"]
    assert KG.slides_using(g, "timeline") == ["d2.s2"]
    assert KG.slides_using(g, "roadmap") == ["d2.s2"]          # an alias of timeline
    assert KG.slides_using(g, "diagram") == ["d1.s5", "d1.s6", "d2.s2"]
    assert KG.slides_using(g, "section") == ["d1.s2", "d1.s8"]
    assert KG.slides_using(g, "nothing-like-this") == []


def test_recurring_terms_span_decks_with_their_slides():
    ts = {t["term"]: t for t in KG.terms(graph(), limit=40)}
    assert "net retention" in ts, sorted(ts)
    nr = ts["net retention"]
    assert nr["decks"] == 2
    assert {"d1.s1", "d1.s3", "d2.s1", "d2.s3"} <= set(nr["slides"])
    # a word that only ever appears inside the phrase is folded into it
    assert "retention" not in ts
    assert KG.slides_using(graph(), "net retention") == nr["slides"]


def test_queries_accept_a_slug():
    with fixture_kit() as (kits, slug):
        KI.learn(slug)
        assert KG.preferred_kinds(slug)
        assert KG.arc(slug)["first"][0]["value"] == "cover"
    try:
        KG.arc({})
    except LookupError:
        return
    raise AssertionError("an empty graph should raise LookupError")


# ── the graph feeds the engine ──────────────────────────────────────────

def test_learn_feeds_norms_brief_profile_and_coach():
    with fixture_kit() as (kits, slug):
        out = KI.learn(slug)
        n = out["norms"]
        assert n["preferred_diagram_kinds"][0] in ("hierarchy", "flow", "timeline")
        assert n["arc"]["opens"] == "cover" and n["arc"]["ask_position"] == 1.0
        assert out["graph"]["path"] == "graph.json"
        assert "End on the ask: the last slides say what needs deciding." in out["suggested_rules"]
        assert KI.norms(slug) == n

        brief = K.house_brief(slug)
        assert "Diagrams this house uses:" in brief
        assert "the ask lands about 100% through" in brief

        assert O.load_org(slug).narrative.learned["opens"] == "cover"

        persona = C.load_persona(C.list_personas()[0]["slug"])
        note = C.lens_density({"bullets": list("abcdefghij")}, {"norms": n})
        assert n["preferred_diagram_kinds"][0] in note["ask"]
        assert persona  # personas still load with the new norms


# ── optional model pass ─────────────────────────────────────────────────

def test_describe_without_a_model_returns_measured_facts():
    g = graph()
    ids = {n["id"] for n in g["nodes"] if n["type"] == "slide"}
    with mock.patch("deckengine.narrative.available", return_value=False):
        out = KG.describe(g)
    assert out["source"] == "measured" and out["claims"]
    for c in out["claims"]:
        assert c["slides"] and set(c["slides"]) <= ids


def test_describe_drops_claims_that_cite_missing_slides():
    g = graph()
    reply = json.dumps({"claims": [
        {"text": "Org charts show ownership.", "slides": ["d1.s5"]},
        {"text": "Invented pattern.", "slides": ["d9.s1"]},
        {"text": "Uncited pattern.", "slides": []},
    ]})
    out = KG.describe(g, llm=lambda prompt, system: reply)
    assert out == {"source": "model",
                   "claims": [{"text": "Org charts show ownership.", "slides": ["d1.s5"]}]}

    def broken(prompt, system):
        raise RuntimeError("model down")
    assert KG.describe(g, llm=broken)["source"] == "measured"
    assert KG.describe(g, llm=lambda p, s: "not json")["source"] == "measured"


# ── endpoint ────────────────────────────────────────────────────────────

def test_graph_endpoint():
    from httpx import ASGITransport, AsyncClient
    from server import app

    async def go(slug):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.get(f"/api/kits/{slug}/graph")
            assert r.status_code == 404, r.text
            r = await ac.post(f"/api/kits/{slug}/learn")
            assert r.status_code == 200, r.text
            r = await ac.get(f"/api/kits/{slug}/graph")
            body = r.json()
            assert body["decks"] == 2 and "arc" in body and "nodes" not in body
            r = await ac.get(f"/api/kits/{slug}/graph", params={"uses": "smartart"})
            assert [s["id"] for s in r.json()["slides"]] == ["d1.s5"]
            r = await ac.get(f"/api/kits/{slug}/graph", params={"full": "1"})
            assert "nodes" in r.json()
            with mock.patch("deckengine.narrative.available", return_value=False):
                r = await ac.post(f"/api/kits/{slug}/graph/describe")
            assert r.json()["source"] == "measured"
            r = await ac.get("/api/kits/BAD!/graph")
            assert r.status_code >= 400

    with fixture_kit() as (kits, slug):
        asyncio.run(go(slug))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
