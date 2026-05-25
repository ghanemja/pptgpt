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


# ============================================================
# Per-archetype invariant tests (R3.2: margins + no-overlap for every resolver)
# ============================================================

def _peer_overlap_violations(boxes, role):
    peers = [b for b in boxes if b.role == role]
    bad = []
    for i in range(len(peers)):
        for j in range(i + 1, len(peers)):
            if _overlap(peers[i], peers[j]):
                bad.append((peers[i].role, i, j))
    return bad


def _within_margins(boxes, theme):
    m = theme.margin_in
    for b in boxes:
        if b.x < m - 1e-6: return False, f"{b.role} left"
        if b.y < m - 1e-6: return False, f"{b.role} top"
        if b.x + b.w > CANVAS_W - m + 1e-6: return False, f"{b.role} right"
        if b.y + b.h > CANVAS_H - m + 1e-6: return False, f"{b.role} bottom"
    return True, ""


# ---- title_slide ---------------------------------------------------------

def _title_slide():
    return Slide(
        blocks=[
            ContentBlock(BlockKind.TITLE, text="A slide that asks before it draws"),
            ContentBlock(BlockKind.SUBTITLE, text="local-first slide generation"),
        ],
        intent=LayoutIntent.TITLE_SLIDE,
    )


def test_title_slide_margins():
    rs = resolve(_title_slide(), Theme())
    ok, why = _within_margins(rs.boxes, Theme())
    assert ok, f"title_slide breaks {why}"


def test_title_slide_no_overlap_between_title_and_subtitle():
    rs = resolve(_title_slide(), Theme())
    title = next(b for b in rs.boxes if b.role == "title")
    sub = next(b for b in rs.boxes if b.role == "subtitle")
    assert not _overlap(title, sub), "title/subtitle overlap"


def test_title_slide_title_dominates_subtitle():
    rs = resolve(_title_slide(), Theme())
    title = next(b for b in rs.boxes if b.role == "title")
    sub = next(b for b in rs.boxes if b.role == "subtitle")
    # R2.5.3 style: title commands the slide
    assert title.size_pt >= sub.size_pt * 2, "title/subtitle contrast weak"


# ---- two_column_stats ----------------------------------------------------

def _two_col_slide():
    return Slide(
        blocks=[
            ContentBlock(BlockKind.TITLE, text="Q3 — momentum AND moderation"),
            ContentBlock(BlockKind.BULLETS, items=[
                "Enterprise close rate doubled",
                "Multi-year contracts now 60% of new ARR",
                "SMB CAC up 30% — pause the channel",
            ]),
            ContentBlock(BlockKind.STAT, value="+14%", label="revenue vs plan", emphasis=2),
            ContentBlock(BlockKind.STAT, value="118%", label="net retention"),
            ContentBlock(BlockKind.STAT, value="1.8%", label="monthly churn"),
        ],
        intent=LayoutIntent.TWO_COLUMN_STATS,
    )


def test_two_column_stats_margins():
    rs = resolve(_two_col_slide(), Theme())
    ok, why = _within_margins(rs.boxes, Theme())
    assert ok, f"two_column_stats breaks {why}"


def test_two_column_stats_columns_no_overlap():
    """Left bullet column must not overlap right stat column."""
    rs = resolve(_two_col_slide(), Theme())
    left = [b for b in rs.boxes if b.role == "bullet"]
    right = [b for b in rs.boxes if b.role in ("stat_value", "stat_label")]
    for l in left:
        for r in right:
            assert not _overlap(l, r), "left bullet overlaps a right stat"


def test_two_column_stats_stat_peers_no_overlap():
    rs = resolve(_two_col_slide(), Theme())
    for role in ("stat_value", "stat_label", "bullet"):
        assert not _peer_overlap_violations(rs.boxes, role), f"{role} peers overlap"


def test_two_column_stats_hero_dominance():
    rs = resolve(_two_col_slide(), Theme())
    vals = [b for b in rs.boxes if b.role == "stat_value"]
    hero = max(vals, key=lambda b: b.size_pt)
    others = [b for b in vals if b is not hero]
    assert all(hero.size_pt >= o.size_pt * 1.3 for o in others), "hero too quiet"


# ---- icon_rows -----------------------------------------------------------

def _icon_rows_slide(n=4):
    items = ["Reduce sync latency", "Add iPad pencil", "Open public API", "Ship offline mode", "Multi-region", "On-prem option"][:n]
    return Slide(
        blocks=[
            ContentBlock(BlockKind.TITLE, text="What we're shipping"),
            ContentBlock(BlockKind.ICON_ROW, items=items),
        ],
        intent=LayoutIntent.ICON_ROWS,
    )


def test_icon_rows_margins():
    rs = resolve(_icon_rows_slide(), Theme())
    ok, why = _within_margins(rs.boxes, Theme())
    assert ok, f"icon_rows breaks {why}"


def test_icon_rows_peer_no_overlap():
    rs = resolve(_icon_rows_slide(), Theme())
    for role in ("row_marker", "row_label"):
        assert not _peer_overlap_violations(rs.boxes, role), f"{role} peers overlap"


def test_icon_rows_marker_and_label_align_per_row():
    """A marker and its label should be next to each other, not stacked."""
    rs = resolve(_icon_rows_slide(), Theme())
    markers = sorted([b for b in rs.boxes if b.role == "row_marker"], key=lambda b: b.y)
    labels  = sorted([b for b in rs.boxes if b.role == "row_label"],  key=lambda b: b.y)
    assert len(markers) == len(labels), "row count mismatch"
    for m_, l_ in zip(markers, labels):
        # share approximately the same vertical band
        assert abs(m_.y - l_.y) < 0.05, "marker and label not in same row"
        # marker is to the left of label
        assert m_.x + m_.w <= l_.x + 1e-6, "marker not left of label"


def test_icon_rows_evenly_distributed():
    rs = resolve(_icon_rows_slide(5), Theme())
    labels = sorted([b for b in rs.boxes if b.role == "row_label"], key=lambda b: b.y)
    gaps = [labels[i+1].y - labels[i].y for i in range(len(labels) - 1)]
    assert max(gaps) - min(gaps) < 1e-6, "icon rows not evenly distributed"


# ---- bullets_plain -------------------------------------------------------

def _bullets_slide(n=4):
    items = [
        "Net retention strong at 118%",
        "Churn down to 1.8%",
        "Enterprise close rate doubled",
        "Multi-year contracts 60% of new ARR",
        "Two design-partner wins in public sector",
    ][:n]
    return Slide(
        blocks=[
            ContentBlock(BlockKind.TITLE, text="What's working"),
            ContentBlock(BlockKind.BULLETS, items=items),
        ],
        intent=LayoutIntent.BULLETS_PLAIN,
    )


def test_bullets_plain_margins():
    rs = resolve(_bullets_slide(), Theme())
    ok, why = _within_margins(rs.boxes, Theme())
    assert ok, f"bullets_plain breaks {why}"


def test_bullets_plain_no_peer_overlap():
    rs = resolve(_bullets_slide(5), Theme())
    assert not _peer_overlap_violations(rs.boxes, "bullet"), "bullets overlap"


def test_bullets_plain_evenly_distributed():
    rs = resolve(_bullets_slide(5), Theme())
    bullets = sorted([b for b in rs.boxes if b.role == "bullet"], key=lambda b: b.y)
    gaps = [bullets[i+1].y - bullets[i].y for i in range(len(bullets) - 1)]
    assert max(gaps) - min(gaps) < 1e-6, "bullets not evenly distributed"


def test_bullets_plain_left_aligned():
    """R2.5.6 — body bullets must be left-aligned."""
    rs = resolve(_bullets_slide(), Theme())
    for b in rs.boxes:
        if b.role == "bullet":
            assert b.align == "left", "bullets must be left-aligned"


# ---- cross-archetype regression: palettes don't change geometry ----------

def test_all_archetypes_geometry_stable_across_palettes():
    """R3.6 across every archetype — direction = palette swap, not geometry."""
    cases = [
        ("stat_callout",      _stat_slide(3)),
        ("two_column_stats",  _two_col_slide()),
        ("icon_rows",         _icon_rows_slide()),
        ("bullets_plain",     _bullets_slide()),
        ("title_slide",       _title_slide()),
    ]
    for name, slide in cases:
        geoms = {}
        for key, theme in PALETTES.items():
            rs = resolve(slide, theme)
            geoms[key] = [(round(b.x, 4), round(b.y, 4), round(b.w, 4), round(b.h, 4)) for b in rs.boxes]
        ref = next(iter(geoms.values()))
        for k, g in geoms.items():
            assert g == ref, f"{name}: palette '{k}' changed geometry"


# ---- intent fallback (R1.3.2) --------------------------------------------

def test_intent_fallback_when_content_misses():
    """If a slide is tagged STAT_CALLOUT but has no stats, resolver falls back."""
    s = Slide(
        blocks=[
            ContentBlock(BlockKind.TITLE, text="Plans for the quarter"),
            ContentBlock(BlockKind.BULLETS, items=["A", "B", "C"]),
        ],
        intent=LayoutIntent.STAT_CALLOUT,
    )
    rs = resolve(s, Theme())
    assert rs.archetype != "stat_callout", "should have fallen back away from stat_callout"
    # and the result is still valid
    ok, why = _within_margins(rs.boxes, Theme())
    assert ok, f"fallback violates margins: {why}"


def test_auto_picks_two_column_when_mixed_content():
    s = Slide(
        blocks=[
            ContentBlock(BlockKind.TITLE, text="Q3 read"),
            ContentBlock(BlockKind.STAT, value="+14%", label="revenue"),
            ContentBlock(BlockKind.STAT, value="118%", label="retention"),
            ContentBlock(BlockKind.BULLETS, items=["narrative one", "narrative two"]),
        ],
        intent=LayoutIntent.AUTO,
    )
    rs = resolve(s, Theme())
    assert rs.archetype == "two_column_stats", f"expected two_column_stats, got {rs.archetype}"


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
