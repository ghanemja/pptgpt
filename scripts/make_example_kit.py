"""Build kits/example-co/ — a complete, working company kit to copy from.

Every part a real kit has is filled in, so a new company can open this
folder, see what each file looks like, and replace them with their own:

    python3 scripts/make_example_kit.py

Re-running rebuilds it from scratch.
"""

from __future__ import annotations

import copy
import csv
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pptx import Presentation                       # noqa: E402
from pptx.dml.color import RGBColor                 # noqa: E402
from pptx.util import Inches, Pt                    # noqa: E402

from deckengine import kit as K                     # noqa: E402

SLUG = "example-co"
NAME = "Example Co"

# A handful of line icons. Real kits bring hundreds; four is enough to show
# how labels and tags make them findable.
ICONS = {
    "growth.svg": ('<path d="M4 18l6-6 4 4 6-8" /><path d="M14 8h6v6" />',
                   "Growth", "growth;revenue;up;increase;trend", "Results that went up"),
    "team.svg": ('<circle cx="9" cy="8" r="3" /><circle cx="17" cy="9" r="2.5" />'
                 '<path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" /><path d="M15 20c0-2.5 1.2-4.4 3-5" />',
                 "Team", "team;people;hiring;customers;staff", "Anything about people"),
    "shield.svg": ('<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" /><path d="M9 12l2 2 4-4" />',
                   "Security", "security;risk;compliance;trust;safety", "Risk and compliance"),
    "rocket.svg": ('<path d="M5 19c1-3 3-5 5-6M14 4c3 0 6 3 6 6-2 4-6 7-9 8l-5-5c1-3 4-7 8-9z" />'
                   '<circle cx="15" cy="9" r="1.5" />',
                   "Launch", "launch;ship;release;new;product", "A launch or a first"),
}


def _svg(body: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 24 24" '
            'fill="none" stroke="#0E5B36" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round">{body}</svg>\n')


def _template(path: str) -> None:
    """A small house template: a brand band and a wordmark on the master."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    scratch = prs.slides.add_slide(prs.slide_layouts[6])
    band = scratch.shapes.add_shape(1, Inches(0), Inches(7.1), Inches(13.333), Inches(0.4))
    band.fill.solid()
    band.fill.fore_color.rgb = RGBColor(0x0E, 0x5B, 0x36)
    band.line.fill.background()
    mark = scratch.shapes.add_textbox(Inches(11.2), Inches(7.12), Inches(2.0), Inches(0.36))
    run = mark.text_frame.paragraphs[0].add_run()
    run.text = "EXAMPLE CO"
    run.font.size, run.font.bold = Pt(11), True
    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    master = prs.slide_masters[0]
    for sh in (band, mark):
        master.shapes._spTree.append(copy.deepcopy(sh._element))
    ids = prs.slides._sldIdLst
    for sld in list(ids):
        prs.part.drop_rel(sld.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"))
        ids.remove(sld)
    prs.save(path)


def build() -> str:
    d = os.path.join(K.KITS_DIR, SLUG)
    if os.path.isdir(d):
        shutil.rmtree(d)
    K.create_kit(NAME, "A worked example. Copy this folder and replace each file with your own.")

    # template
    _template(os.path.join(d, "example-co-template.pptx"))

    # examples: the engine's own sample deck stands in for a company's past work
    sample = os.path.join(ROOT, "frontend", "samples", "sample.pptx")
    shutil.copyfile(sample, os.path.join(d, "examples", "q3-board-review.pptx"))

    # assets + their labels
    rows = []
    for fname, (body, label, tags, use) in ICONS.items():
        with open(os.path.join(d, "assets", "icons", fname), "w", encoding="utf-8") as fh:
            fh.write(_svg(body))
        rows.append([f"icons/{fname}", label, tags, use, "CC0 — drawn for this example"])
    with open(os.path.join(d, "assets", "assets.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(K.ASSET_COLUMNS)
        w.writerows(rows)

    # voice
    K.set_voice(SLUG, """# How Example Co writes

- Lead with the conclusion. The title is the claim; the slide is the evidence.
- Every number carries a unit, a comparison and a date: "118% net retention, up from 104% in FY25".
- Say "customers", never "users". Say "revenue", never "top line".
- One idea per slide. If it needs "and also", it is two slides.
- End every deck on the decision you need, stated as a yes/no question.
""")

    # house rules, stated the way profile.json states them
    import json
    ppath = os.path.join(d, "profile.json")
    with open(ppath, "r", encoding="utf-8") as fh:
        prof = json.load(fh)
    prof["style"]["rules"] = [
        "Lead with the conclusion; the title is the claim.",
        "Every number carries a unit, a comparison and a date.",
        "One idea per slide.",
    ]
    prof["style"]["banned"] = ["stock photography of handshakes", "3-D charts"]
    with open(ppath, "w", encoding="utf-8") as fh:
        json.dump(prof, fh, indent=2)
        fh.write("\n")

    from deckengine.kit_ingest import learn
    learn(SLUG)
    return d


if __name__ == "__main__":
    path = build()
    status = K.scan(SLUG)
    print(f"[example kit] {path}")
    for p in status["parts"]:
        print(f"  {'✓' if p['ok'] else '·'} {p['label']:<26} {p['detail']}")
