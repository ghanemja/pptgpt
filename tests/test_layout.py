"""
Layout constraint tests — the proof that 'good layout' is measurable.

These assert design INVARIANTS, not pixel-exact output. If a future engine
change violates a margin or overlaps two boxes, these fail. This is what
lets you refactor the engine fearlessly and what makes the approach
defensible: layout soundness is checkable, not a matter of taste.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine.ir import Slide, ContentBlock, BlockKind, LayoutIntent, PALETTES, Theme
from deckengine.layout import resolve, CANVAS_W, CANVAS_H


def _stat_slide(n=3, hero=0):
    blocks = [ContentBlock(BlockKind.TITLE, text="Q3 Reliability Review")]
    data = [("99.97%", "uptime"), ("14m", "downtime"), ("3", "incidents"), ("6x", "faster")]
    for i in range(n):
        v, l = data[i]
        blocks.append(ContentBlock(BlockKind.STAT, value=v, label=l, emphasis=2 if i == hero else 0))
    return Slide(blocks=blocks, intent=LayoutIntent.STAT_CALLOUT)


def _overlap(a, b):
    return not (a.x + a.w <= b.x or b.x + b.w <= a.x or
                a.y + a.h <= b.y or b.y + b.h <= a.y)


def test_margins_respected():
    theme = Theme()
    rs = resolve(_stat_slide(3), theme)
    m = theme.margin_in
    for box in rs.boxes:
        assert box.x >= m - 1e-6, f"{box.role} breaks left margin"
        assert box.y >= m - 1e-6, f"{box.role} breaks top margin"
        assert box.x + box.w <= CANVAS_W - m + 1e-6, f"{box.role} breaks right margin"
        assert box.y + box.h <= CANVAS_H - m + 1e-6, f"{box.role} breaks bottom margin"


def test_no_overlap_between_stat_columns():
    rs = resolve(_stat_slide(3), Theme())
    values = [b for b in rs.boxes if b.role == "stat_value"]
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            assert not _overlap(values[i], values[j]), "stat columns overlap"


def test_hero_contrast_enforced():
    rs = resolve(_stat_slide(3, hero=1), Theme())
    values = [b for b in rs.boxes if b.role == "stat_value"]
    hero = max(values, key=lambda b: b.size_pt)
    others = [b for b in values if b is not hero]
    # hero must be meaningfully larger than the rest
    assert all(hero.size_pt >= o.size_pt * 1.3 for o in others), "hero size contrast too weak"


def test_title_body_size_contrast():
    rs = resolve(_stat_slide(3), Theme())
    title = next(b for b in rs.boxes if b.role == "title")
    label = next(b for b in rs.boxes if b.role == "stat_label")
    assert title.size_pt >= label.size_pt * 2, "title/label contrast too weak"


def test_even_distribution():
    rs = resolve(_stat_slide(3), Theme())
    values = sorted([b for b in rs.boxes if b.role == "stat_value"], key=lambda b: b.x)
    gaps = [values[i+1].x - values[i].x for i in range(len(values) - 1)]
    assert max(gaps) - min(gaps) < 1e-6, "stat columns not evenly distributed"


def test_directions_share_geometry_differ_in_color():
    """Multiple 'directions' = same geometry, different theme. Cheap by design."""
    s = _stat_slide(3)
    geoms = {}
    bgs = {}
    for key, theme in PALETTES.items():
        rs = resolve(s, theme)
        geoms[key] = [(round(b.x, 4), round(b.y, 4), round(b.w, 4)) for b in rs.boxes]
        bgs[key] = rs.bg
    # geometry identical across palettes
    ref = geoms["bold"]
    assert all(geoms[k] == ref for k in geoms), "palettes should not change geometry"
    # backgrounds differ
    assert len(set(bgs.values())) > 1, "palettes should differ in color"


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
