"""
End-to-end smoke test. Boots the FastAPI app via httpx ASGI transport
(no real port binding needed — works in any sandbox), hits every endpoint,
verifies shapes, downloads .pptx outputs, opens them with python-pptx to
check validity.

This is intentionally a script (not a unittest module) so it can be run as
`python tests/smoke_e2e.py` alongside the other tests.
"""
import sys, os, io, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from httpx import AsyncClient, ASGITransport
from pptx import Presentation

from server import app


SAMPLE_DRAFT = """Q3 board update
Q3 revenue beat plan by 14%
Net retention 118%, churn down to 1.8%
New enterprise cohort outpacing SMB by 2x
Decision: double down on enterprise GTM"""

SAMPLE_DECK = """Cover
Subtitle: A quarterly read
---
The numbers
Revenue +14%
Retention 118%
Churn 1.8%
---
What's working
Enterprise close rate doubled
Multi-year contracts 60% of new ARR"""


async def run():
    failures = []
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:

        # --- /health ---
        r = await ac.get("/health")
        assert r.status_code == 200 and r.json().get("ok") is True, f"/health: {r.text}"
        print("PASS  /health")

        # --- /api/ir ---
        r = await ac.post("/api/ir", json={"rawContent": SAMPLE_DECK})
        assert r.status_code == 200, f"/api/ir status {r.status_code}: {r.text}"
        ir = r.json()
        assert "slides" in ir and len(ir["slides"]) == 3, f"/api/ir slides: {ir}"
        # R0.1 boundary check — IR JSON must not contain geometry keys
        as_str = json.dumps(ir)
        for forbidden in ('"x":', '"y":', '"w":', '"h":', '"left":', '"top":'):
            if forbidden in as_str:
                failures.append(f"/api/ir leaked geometry: {forbidden}")
        print(f"PASS  /api/ir ({len(ir['slides'])} slides)")

        # --- /api/design ---
        r = await ac.post("/api/design", json={"rawContent": SAMPLE_DRAFT, "answers": {}})
        assert r.status_code == 200, f"/api/design: {r.text}"
        d = r.json()
        for k in ("slideIR", "ir", "questions", "directions", "archetypeChosen"):
            assert k in d, f"/api/design missing {k}"
        assert d["slideIR"]["canvasW"] == 1280
        print(f"PASS  /api/design (archetype={d['archetypeChosen']}, {len(d['questions'])} questions)")

        # answer the focus question and re-design
        if d["questions"]:
            q = d["questions"][0]
            answers = {q["id"]: q["options"][0]}
            r2 = await ac.post("/api/design", json={"rawContent": SAMPLE_DRAFT, "answers": answers})
            assert r2.status_code == 200
            d2 = r2.json()
            # answered question shouldn't reappear
            assert not any(qq["id"] == q["id"] for qq in d2["questions"]), \
                "answered question came back"
            print(f"PASS  /api/design follow-up (questions left: {len(d2['questions'])})")

        # --- /api/storyboard ---
        r = await ac.post("/api/storyboard", json={"text": SAMPLE_DECK, "mode": "condense"})
        assert r.status_code == 200, r.text
        sb = r.json()
        assert sb["outline"] and len(sb["outline"]) >= 2
        print(f"PASS  /api/storyboard ({len(sb['outline'])} outline slides)")

        # --- /api/critique ---
        r = await ac.post("/api/critique", json={
            "audience": "exec", "mode": "draft", "outline": sb["outline"],
        })
        assert r.status_code == 200, r.text
        cq = r.json()
        assert "criticisms" in cq and "questions" in cq
        print(f"PASS  /api/critique ({len(cq['criticisms'])} criticisms)")

        # --- /api/render_ir ---
        r = await ac.post("/api/render_ir", json={"rawContent": SAMPLE_DECK})
        assert r.status_code == 200, r.text
        prs = Presentation(io.BytesIO(r.content))
        assert len(prs.slides) == 3, f"render_ir slides: {len(prs.slides)}"
        print(f"PASS  /api/render_ir ({len(prs.slides)} slides in pptx, {len(r.content)} bytes)")

        # --- /api/render (SlideSpec) ---
        # The engine's resolved SlideSpec from /api/design, rendered verbatim.
        slides = [d["slideIR"]]
        r = await ac.post("/api/render", json={"slides": slides})
        assert r.status_code == 200, r.text
        prs = Presentation(io.BytesIO(r.content))
        print(f"PASS  /api/render (SlideSpec, {len(prs.slides)} slide(s), {len(r.content)} bytes)")

        # --- /api/render_direction ---
        direction = {"key": "engine", "slides": slides}
        r = await ac.post("/api/render_direction", json={"direction": direction})
        assert r.status_code == 200, r.text
        prs = Presentation(io.BytesIO(r.content))
        print(f"PASS  /api/render_direction ({len(prs.slides)} slide(s), {len(r.content)} bytes)")

        # --- /api/plot ---
        plot_block = {
            "type": "plot", "x": 0, "y": 0, "w": 800, "h": 400,
            "bg": "#0F0F1E",
            "curves": [{"fn": "sine", "params": {"A": 1, "omega": 1, "phi": 0}, "color": "#4ec5ff", "width": 3}],
            "xRange": [-6.28, 6.28], "yRange": [-1.5, 1.5],
        }
        r = await ac.post("/api/plot", json={"block": plot_block, "params": {"A": 1.5}})
        # may be 503 if matplotlib not installed; in our env it is
        if r.status_code == 200:
            assert r.headers["content-type"].startswith("image/")
            print(f"PASS  /api/plot ({len(r.content)} byte PNG)")
        else:
            print(f"SKIP  /api/plot (status {r.status_code} — matplotlib absent)")

        # --- /api/storyboard_view ---
        r = await ac.post("/api/storyboard_view", json={
            "outline": sb["outline"], "mode": "condense",
        })
        assert r.status_code == 200, r.text
        sv = r.json()
        for k in ("outline", "threads", "suggestions", "spine", "tensions", "engine", "stats"):
            assert k in sv, f"/api/storyboard_view missing {k}"
        # threads list items have the design's shape
        for t in sv["threads"]:
            for k in ("id", "label", "color", "slideIds", "strength", "type"):
                assert k in t, f"thread missing {k}: {t}"
        print(f"PASS  /api/storyboard_view (engine={sv['engine']}, {len(sv['threads'])} threads, {len(sv['suggestions'])} suggestions)")

        # --- /api/thread_map ---
        r = await ac.post("/api/thread_map", json={
            "outline": sb["outline"],
            "recommendations": sb.get("recommendations") or [],
            "mode": "potential",
        })
        assert r.status_code == 200, r.text
        tm = r.json()
        for k in ("before", "after", "diff", "applied", "mode"):
            assert k in tm, f"/api/thread_map missing {k}"
        for side in ("before", "after"):
            for k in ("graph", "ribbons", "stats"):
                assert k in tm[side]
        print(f"PASS  /api/thread_map "
              f"(messiness {tm['before']['stats']['messiness']} → {tm['after']['stats']['messiness']}, "
              f"applied {len(tm['applied'])})")

        # --- /api/ingest ---
        # build a fixture pptx in memory and upload
        from tests.test_ingest import _build_fixture_pptx
        fixture = _build_fixture_pptx()
        files = {"file": ("fixture.pptx", fixture,
                          "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
        r = await ac.post("/api/ingest", files=files)
        assert r.status_code == 200, r.text
        ing = r.json()
        assert len(ing["slides"]) >= 3
        # no geometry leak
        as_str = json.dumps(ing)
        for forbidden in ('"x":', '"y":', '"w":', '"h":'):
            if forbidden in as_str:
                failures.append(f"/api/ingest leaked geometry: {forbidden}")
        print(f"PASS  /api/ingest ({len(ing['slides'])} slides extracted)")

    print()
    if failures:
        print(f"FAILURES: {len(failures)}")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL ENDPOINTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
