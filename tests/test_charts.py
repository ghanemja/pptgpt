"""
Chart model tests.

The contract:
- Order and emphasis are decisions about the CHART, resolved one way, so the
  preview and the exported file cannot disagree.
- Every chart kind renders; an unknown kind falls back rather than failing.
- The option toggles actually reach the renderer.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine.spec_render import _render_chart_png, chart_rows

ROWS = [
    {"label": "SMB", "value": 1.2},
    {"label": "Mid", "value": 2.1},
    {"label": "Ent", "value": 8.4},
    {"label": "Partner", "value": 3.3},
]


def _block(**over):
    b = {"w": 900, "h": 520, "data": [dict(r) for r in ROWS],
         "bg": "#353D2D", "primaryColor": "#FFFFFF", "highlightColor": "#C9A227",
         "labelColor": "#FFFFFF", "axisColor": "#FFFFFF"}
    b.update(over)
    return b


def test_source_order_is_left_alone():
    assert [r["label"] for r in chart_rows(_block())] == ["SMB", "Mid", "Ent", "Partner"]


def test_sorting_orders_by_value():
    desc = [r["label"] for r in chart_rows(_block(sort="desc"))]
    asc = [r["label"] for r in chart_rows(_block(sort="asc"))]
    assert desc == ["Ent", "Partner", "Mid", "SMB"]
    assert asc == list(reversed(desc))


def test_highlight_marks_exactly_one_row():
    rows = chart_rows(_block(highlight="Ent"))
    assert [r["label"] for r in rows if r.get("hi")] == ["Ent"]
    assert sum(1 for r in rows if r.get("hi")) == 1


def test_highlight_survives_sorting():
    rows = chart_rows(_block(sort="desc", highlight="Mid"))
    assert rows[0]["label"] == "Ent", "sort did not apply"
    assert [r["label"] for r in rows if r.get("hi")] == ["Mid"]


def test_a_missing_highlight_marks_nothing():
    rows = chart_rows(_block(highlight="Nowhere"))
    assert not any(r.get("hi") for r in rows)


def test_every_kind_renders():
    for kind in ("column", "bar", "line", "area", "pie", "unknown-kind"):
        png = _render_chart_png(_block(kind=kind))
        assert png and png[:4] == b"\x89PNG", f"{kind} produced no image"


def test_toggles_change_the_image():
    """A control that renders identically either way is not a control."""
    base = _render_chart_png(_block(kind="column", showValueLabels=True, gridlines=False))
    no_values = _render_chart_png(_block(kind="column", showValueLabels=False, gridlines=False))
    gridded = _render_chart_png(_block(kind="column", showValueLabels=True, gridlines=True))
    sorted_ = _render_chart_png(_block(kind="column", showValueLabels=True, sort="desc"))
    assert base != no_values, "hiding values changed nothing"
    assert base != gridded, "gridlines changed nothing"
    assert base != sorted_, "sorting changed nothing"


def test_pie_renders_with_and_without_values():
    for show in (True, False):
        assert _render_chart_png(_block(kind="pie", showValueLabels=show))


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
