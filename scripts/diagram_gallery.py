"""Render one slide per diagram kind to a .pptx (and a PNG contact sheet if
LibreOffice + pdftoppm are installed), for looking at the diagram engine's
output the way PowerPoint will show it.

    python scripts/diagram_gallery.py [out_dir]
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pptx import Presentation
from pptx.util import Inches, Pt

from deckengine import diagram as D
from deckengine.render import add_diagram

CASES: dict[str, dict] = {
    "flow with a decision, a loop and a skip": {
        "kind": "flow",
        "nodes": [{"id": "a", "label": "Request comes in"}, {"id": "b", "label": "Approved?"},
                  {"id": "c", "label": "Ship it"}, {"id": "d", "label": "Rework the draft"},
                  {"id": "e", "label": "Done", "role": "end"}],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c", "label": "yes"},
                  {"from": "b", "to": "d", "label": "no"}, {"from": "d", "to": "b"},
                  {"from": "c", "to": "e"}, {"from": "a", "to": "e", "label": "fast track"}],
    },
    "long chain wraps": {"kind": "flow", "steps": ["Lead", "Qualify", "Demo", "Proposal",
                                                   "Negotiate", "Sign", "Onboard", "Renew"]},
    "swimlane": {
        "kind": "swimlane",
        "nodes": [{"id": "1", "label": "Submit request", "group": "Sales"},
                  {"id": "2", "label": "Review terms", "group": "Legal"},
                  {"id": "3", "label": "Approve spend", "group": "Finance"},
                  {"id": "4", "label": "Notify customer", "group": "Sales"}],
        "edges": [{"from": "1", "to": "2"}, {"from": "2", "to": "3"}, {"from": "3", "to": "4"},
                  {"from": "1", "to": "3", "label": "under $10k"}],
    },
    "hierarchy": {
        "kind": "hierarchy",
        "nodes": [{"id": "ceo", "label": "CEO"}, {"id": "a", "label": "Engineering"},
                  {"id": "b", "label": "Sales"}, {"id": "c", "label": "Platform"},
                  {"id": "d", "label": "Apps"}, {"id": "e", "label": "Enterprise"}],
        "edges": [{"from": "ceo", "to": "a"}, {"from": "ceo", "to": "b"}, {"from": "a", "to": "c"},
                  {"from": "a", "to": "d"}, {"from": "b", "to": "e"}],
    },
    "cycle": {"kind": "cycle", "steps": ["Plan the sprint", "Build", "Measure usage",
                                         "Learn and adjust", "Ship"]},
    "timeline": {"kind": "timeline", "nodes": [
        {"label": "Pilot with two clinics", "sub": "Q1 2026"}, {"label": "Regional rollout", "sub": "Q2 2026"},
        {"label": "Billing integration", "sub": "Q3 2026"}, {"label": "National launch", "sub": "Q4 2026"},
        {"label": "Renewal", "sub": "Q1 2027"}]},
    "matrix": {"kind": "matrix", "x_axis": "Effort", "y_axis": "Impact", "nodes": [
        {"label": "Big bets"}, {"label": "Quick wins", "role": "hero", "sub": "do these first"},
        {"label": "Money pits"}, {"label": "Fill-ins"}]},
    "funnel": {"kind": "funnel", "nodes": [
        {"label": "Visitors", "sub": "12,000"}, {"label": "Sign-ups", "sub": "2,400"},
        {"label": "Active", "sub": "900"}, {"label": "Paid", "sub": "210"}]},
}

BOX = (0.6, 1.5, 12.1, 5.4)


def build(path: str, pal: dict[str, str] | None = None) -> str:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    pal = pal or D.palette("FFFFFF", "1E2761", "11120E", "F96167")
    for name, content in CASES.items():
        s = prs.slides.add_slide(prs.slide_layouts[6])
        tb = s.shapes.add_textbox(Inches(0.6), Inches(0.5), Inches(12), Inches(0.7))
        tb.text_frame.text = name
        tb.text_frame.paragraphs[0].runs[0].font.size = Pt(24)
        add_diagram(s, D.resolve(content, BOX), pal)
    prs.save(path)
    return path


def sheet(pptx: str, out_dir: str) -> str | None:
    if not (shutil.which("soffice") and shutil.which("pdftoppm")):
        return None
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, pptx],
                   check=True, capture_output=True)
    pdf = os.path.splitext(pptx)[0] + ".pdf"
    for f in glob.glob(os.path.join(out_dir, "gallery-*.png")):
        os.remove(f)
    subprocess.run(["pdftoppm", "-png", "-r", "48", pdf, os.path.join(out_dir, "gallery")], check=True)
    from PIL import Image
    pages = [Image.open(f) for f in sorted(glob.glob(os.path.join(out_dir, "gallery-*.png")))]
    w, h = pages[0].size
    cols = 2
    rows = (len(pages) + cols - 1) // cols
    out = Image.new("RGB", (w * cols, h * rows), "white")
    for i, im in enumerate(pages):
        out.paste(im, ((i % cols) * w, (i // cols) * h))
    path = os.path.join(out_dir, "diagram-gallery.png")
    out.save(path)
    return path


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out_dir, exist_ok=True)
    p = build(os.path.join(out_dir, "diagram-gallery.pptx"))
    print(p)
    print(sheet(p, out_dir) or "(no soffice/pdftoppm: skipped PNG sheet)")
