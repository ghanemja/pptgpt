"""
Company kit tests.

The contract:
- The FOLDER is the source of truth. Uploading, pointing at a folder, and
  dropping files in by hand all produce the same kit, and a scan shows
  whatever is on disk.
- Files are sorted by type and intent; anything a kit does not use is
  refused, never silently stored.
- Nothing escapes the kit folder: no traversal in names, no symlinks
  followed, no import of a folder already inside kits/.
- Learning measures example decks — a stat value is not a bullet — and the
  norms it writes change what the coach and the generator do.
- A kit is an organisation: it appears in the Scope picker and wins over a
  built-in profile of the same name.
"""
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckengine import coach as C
from deckengine import kit as K
from deckengine import kit_ingest as KI
from deckengine import org as O

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "frontend", "samples", "sample.pptx")
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="M4 4h16v16H4z"/></svg>'


@contextmanager
def sandbox():
    """A private kits/ folder, so tests never touch a real company kit."""
    with tempfile.TemporaryDirectory() as d:
        kits = os.path.join(d, "kits")
        os.makedirs(kits)
        with mock.patch.object(K, "KITS_DIR", kits), mock.patch.object(O, "KITS_DIR", kits):
            yield kits


def _expect(fn, needle=""):
    try:
        fn()
    except K.KitError as e:
        assert needle in str(e), f"wrong error: {e}"
        return
    raise AssertionError("expected KitError")


def _sample_bytes():
    with open(SAMPLE, "rb") as fh:
        return fh.read()


# ── creating ────────────────────────────────────────────────────────────

def test_a_new_kit_has_the_whole_structure():
    with sandbox() as kits:
        slug = K.create_kit("Acme Health", "Clinical decks")
        assert slug == "acme-health"
        d = os.path.join(kits, slug)
        for rel in ("kit.json", "profile.json", "voice.md", "examples",
                    "assets/assets.csv", "assets/icons", "assets/images", "assets/clipart"):
            assert os.path.exists(os.path.join(d, rel)), rel
        _expect(lambda: K.create_kit("Acme Health"), "already exists")


def test_a_new_kit_starts_with_no_house_rules():
    """Inheriting ours would contradict what the company's decks teach."""
    with sandbox():
        slug = K.create_kit("Acme")
        prof = O.load_org(slug)
        assert prof.style.rules == [] and prof.style.banned == []
        assert prof.scope_questions, "the interview should still work on day one"


# ── sorting ─────────────────────────────────────────────────────────────

def test_files_are_classified_by_type_and_name():
    c = K.classify
    assert c("brand.potx") == "template"
    assert c("Acme Master Template.pptx") == "template"
    assert c("q3-board-review.pptx") == "examples"
    assert c("q3-template-review.pptx", top_level=False) == "examples"
    assert c("growth.svg") == "assets" and c("photo.JPG") == "assets"
    assert c("profile.json") == "profile"
    assert c("assets.csv") == "assets_csv"
    assert c("voice.md") == "voice" and c("writing-guide.md") == "voice"
    assert c("notes.docx") is None and c("old-deck.ppt") is None
    # an explicit part wins when the type fits, and refuses when it doesn't
    assert c("brand.pptx", "examples") == "examples"
    assert c("growth.svg", "examples") is None


def test_uploads_land_in_the_right_folders():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        rep = K.add_files(slug, [
            ("q3.pptx", _sample_bytes()),
            ("brand-template.pptx", _sample_bytes()),
            ("growth.svg", SVG),
            ("notes.docx", b"nope"),
        ])
        where = {r["file"]: r["path"] for r in rep["stored"]}
        assert where["q3.pptx"] == os.path.join("examples", "q3.pptx")
        assert where["brand-template.pptx"] == "brand-template.pptx"
        assert where["growth.svg"] == os.path.join("assets", "icons", "growth.svg")
        assert [s["file"] for s in rep["skipped"]] == ["notes.docx"]


def test_bad_payloads_are_refused_with_a_reason():
    with sandbox():
        slug = K.create_kit("Acme")
        rep = K.add_files(slug, [
            ("fake.pptx", b"this is not a zip"),
            ("profile.json", b'{"tagline": "no name"}'),
            ("assets.csv", b"name,thing\na,b\n"),
            ("empty.svg", b""),
        ])
        reasons = {s["file"]: s["reason"] for s in rep["skipped"]}
        assert "not a PowerPoint" in reasons["fake.pptx"]
        assert "profile.json is not valid" in reasons["profile.json"]
        assert "file,label" in reasons["assets.csv"]
        assert "empty" in reasons["empty.svg"]
        assert rep["stored"] == []


def test_a_filename_cannot_escape_the_kit():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        rep = K.add_files(slug, [("../../../evil.svg", SVG)])
        stored = rep["stored"][0]["path"]
        full = os.path.realpath(os.path.join(kits, slug, stored))
        assert full.startswith(os.path.realpath(os.path.join(kits, slug)) + os.sep)
        assert ".." not in stored


def test_a_second_assets_csv_adds_rather_than_replaces():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        K.add_files(slug, [("assets.csv", b"file,label,tags\nicons/a.svg,Alpha,one\n")])
        K.add_files(slug, [("assets.csv", b"file,label,tags\nicons/b.svg,Beta,two\n")])
        with open(os.path.join(kits, slug, "assets", "assets.csv")) as fh:
            rows = list(csv.DictReader(fh))
        assert {r["file"] for r in rows} == {"icons/a.svg", "icons/b.svg"}


# ── pointing at a folder ────────────────────────────────────────────────

def test_import_copies_a_folder_and_sorts_it():
    with sandbox() as kits, tempfile.TemporaryDirectory() as src:
        slug = K.create_kit("Acme")
        os.makedirs(os.path.join(src, "decks"))
        os.makedirs(os.path.join(src, "icons"))
        shutil.copyfile(SAMPLE, os.path.join(src, "decks", "fy26.pptx"))
        shutil.copyfile(SAMPLE, os.path.join(src, "Acme Template.pptx"))
        with open(os.path.join(src, "icons", "team.svg"), "wb") as fh:
            fh.write(SVG)
        with open(os.path.join(src, "~$fy26.pptx"), "wb") as fh:        # Office lock file
            fh.write(b"lock")
        with open(os.path.join(src, ".DS_Store"), "wb") as fh:
            fh.write(b"x")

        rep = K.import_path(slug, src)
        got = {r["path"] for r in rep["stored"]}
        assert os.path.join("examples", "fy26.pptx") in got
        assert "Acme Template.pptx" in got
        assert os.path.join("assets", "icons", "team.svg") in got
        assert not any("~$" in p or "DS_Store" in p for p in got)


def test_import_never_follows_a_symlink():
    with sandbox(), tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as outside:
        slug = K.create_kit("Acme")
        secret = os.path.join(outside, "secret.svg")
        with open(secret, "wb") as fh:
            fh.write(SVG)
        os.symlink(secret, os.path.join(src, "linked.svg"))
        os.symlink(outside, os.path.join(src, "linked-dir"))
        rep = K.import_path(slug, src)
        assert rep["stored"] == []


def test_import_refuses_bad_paths():
    with sandbox() as kits, tempfile.TemporaryDirectory() as real:
        slug = K.create_kit("Acme")
        _expect(lambda: K.import_path(slug, "relative/path"), "full folder path")
        _expect(lambda: K.import_path(slug, "/definitely/not/here"), "no folder")
        _expect(lambda: K.import_path(slug, os.path.join(kits, slug)), "inside kits")
        link = os.path.join(real, "alias")
        os.symlink(real, link)
        _expect(lambda: K.import_path(slug, link), "symlink")
        _expect(lambda: K.import_path(slug, real, mode="move"), "mode")


def test_link_mode_reads_decks_in_place():
    with sandbox(), tempfile.TemporaryDirectory() as shared:
        slug = K.create_kit("Acme")
        shutil.copyfile(SAMPLE, os.path.join(shared, "a.pptx"))
        rep = K.import_path(slug, shared, mode="link")
        assert rep["files"] == 1
        assert K.read_manifest(slug)["sources"]["examples"] == [os.path.realpath(shared)]
        assert any(p.endswith("a.pptx") for p in K.example_files(slug))
        # nothing was copied in
        assert not os.listdir(os.path.join(K.kit_dir(slug), "examples"))


# ── the folder is the source of truth ───────────────────────────────────

def test_a_file_dropped_in_by_hand_shows_up_on_scan():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        before = {p["key"]: p for p in K.scan(slug)["parts"]}
        assert not before["examples"]["ok"]

        shutil.copyfile(SAMPLE, os.path.join(kits, slug, "examples", "dropped.pptx"))
        after = {p["key"]: p for p in K.scan(slug)["parts"]}
        assert after["examples"]["ok"] and after["examples"]["count"] == 1


def test_scan_reports_what_is_missing():
    with sandbox():
        slug = K.create_kit("Acme")
        parts = {p["key"]: p for p in K.scan(slug)["parts"]}
        assert parts["profile"]["ok"]
        assert not parts["template"]["ok"]
        assert not parts["voice"]["ok"], "starter voice text should not count as a voice"
        assert not parts["learned"]["ok"]


def test_scan_carries_the_rules_and_voice_the_setup_screen_edits():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        s = K.scan(slug)
        assert s["rules"] == [] and s["voice_text"] == "", "a new kit starts empty"
        path = os.path.join(kits, slug, "profile.json")
        prof = json.load(open(path))
        prof["style"]["rules"] = ["Say customers, never users."]
        json.dump(prof, open(path, "w"))
        K.set_voice(slug, "We write short.")
        s = K.scan(slug)
        assert s["rules"] == ["Say customers, never users."]
        assert s["voice_text"].strip() == "We write short."


def test_a_template_in_the_kit_is_registered_with_a_stable_id():
    with sandbox() as kits, tempfile.TemporaryDirectory() as tpl:
        from deckengine import template as T
        with mock.patch.object(T, "TEMPLATES_DIR", tpl):
            slug = K.create_kit("Acme")
            shutil.copyfile(SAMPLE, os.path.join(kits, slug, "acme-template.pptx"))
            a = K.pin_templates(slug)
            b = K.pin_templates(slug)
            assert a[0]["id"] and a[0]["id"] == b[0]["id"]


# ── assets ──────────────────────────────────────────────────────────────

def test_unlabelled_assets_are_usable_but_flagged():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        with open(os.path.join(kits, slug, "assets", "icons", "data_center.svg"), "wb") as fh:
            fh.write(SVG)
        [a] = K.assets(slug)
        assert a.label == "data center" and a.labeled is False
        parts = {p["key"]: p for p in K.scan(slug)["parts"]}
        assert parts["assets"]["problems"], "an unlabelled asset should be reported"


def test_a_linked_asset_folder_is_labelled_by_its_own_csv():
    with sandbox(), tempfile.TemporaryDirectory() as lib:
        slug = K.create_kit("Acme")
        os.makedirs(os.path.join(lib, "icons"))
        with open(os.path.join(lib, "icons", "up.svg"), "wb") as fh:
            fh.write(SVG)
        with open(os.path.join(lib, "assets.csv"), "w") as fh:
            fh.write("file,label,tags,use,license\nicons/up.svg,Growth,revenue;up,,internal\n")
        K.import_path(slug, lib, mode="link", part="assets")
        [a] = K.assets(slug)
        assert a.linked and a.labeled and a.label == "Growth" and "revenue" in a.tags
        assert K.search_assets(slug, "revenue")[0]["label"] == "Growth"


def test_search_ranks_a_tag_above_a_label():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        for name in ("a.svg", "b.svg"):
            with open(os.path.join(kits, slug, "assets", "icons", name), "wb") as fh:
                fh.write(SVG)
        K.add_files(slug, [("assets.csv",
                            b"file,label,tags\nicons/a.svg,Revenue chart,finance\n"
                            b"icons/b.svg,Arrow,revenue;growth\n")])
        hits = [h["label"] for h in K.search_assets(slug, "revenue")]
        assert hits == ["Arrow", "Revenue chart"], hits
        assert K.search_assets(slug, "zebra") == []


def test_an_asset_outside_the_kit_cannot_be_served():
    with sandbox():
        slug = K.create_kit("Acme")
        _expect(lambda: K.asset_path(slug, "../../../../etc/passwd"), "not part of this kit")
        _expect(lambda: K.asset_path(slug, "/etc/hosts"), "not part of this kit")


def test_an_svg_is_rasterised_large_enough_to_place():
    from deckengine.template import backdrop_available
    if not backdrop_available():
        print("SKIP  no LibreOffice on this host")
        return
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        with open(os.path.join(kits, slug, "assets", "icons", "box.svg"), "wb") as fh:
            fh.write(SVG)
        png = K.asset_png(slug, "assets/icons/box.svg")
        from PIL import Image
        w, h = Image.open(io.BytesIO(png)).size
        assert min(w, h) >= 500, (w, h)


# ── learning ────────────────────────────────────────────────────────────

def test_learning_measures_the_examples():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        shutil.copyfile(SAMPLE, os.path.join(kits, slug, "examples", "q3.pptx"))
        out = KI.learn(slug)
        assert out["decks"] == 1 and out["slides"] == 6
        assert out["layouts"] and out["norms"]["preferred_layouts"]
        assert 2 <= out["norms"]["max_points"] <= 8
        assert out["suggested_rules"]
        assert os.path.isfile(os.path.join(kits, slug, "learned.json"))


def test_a_stat_value_is_not_a_bullet():
    """'118%' and 'net retention' are text, but they are not points."""
    from pptx import Presentation
    prs = Presentation(SAMPLE)
    stat_slide = KI.read_slide(prs.slides[1])        # three stats, no bullets
    assert stat_slide["points"] == 0, stat_slide["points"]


def test_one_bad_deck_does_not_sink_the_run():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        shutil.copyfile(SAMPLE, os.path.join(kits, slug, "examples", "good.pptx"))
        with open(os.path.join(kits, slug, "examples", "broken.pptx"), "wb") as fh:
            fh.write(b"PK not really a deck")
        out = KI.learn(slug)
        assert out["decks"] == 1
        assert [f["file"] for f in out["failed"]] == ["broken.pptx"]


def test_learning_goes_stale_when_examples_change():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        ex = os.path.join(kits, slug, "examples")
        shutil.copyfile(SAMPLE, os.path.join(ex, "a.pptx"))
        KI.learn(slug)
        assert not K.scan(slug)["stale"]
        time.sleep(0.05)
        shutil.copyfile(SAMPLE, os.path.join(ex, "b.pptx"))
        assert K.scan(slug)["stale"]


# ── what the kit changes elsewhere ─────────────────────────────────────

def test_learned_norms_set_the_coach_threshold():
    slide = {"title": "Five things drove the beat",
             "bullets": ["one point here", "two point here", "three point here"],
             "takeaway": "Approve it; Sales owns it."}
    persona = C.load_persona("friendly-editor")
    loose = C.critique_slide(slide, persona, context={"norms": {"max_points": 4}})
    tight = C.critique_slide(slide, persona, context={"norms": {"max_points": 2}})
    assert "density" not in {n["lens"] for n in loose["notes"]}
    dense = [n for n in tight["notes"] if n["lens"] == "density"]
    assert dense and "your own decks" in dense[0]["note"].lower()


def test_the_house_brief_carries_rules_norms_and_voice():
    with sandbox() as kits:
        slug = K.create_kit("Acme")
        path = os.path.join(kits, slug, "profile.json")
        prof = json.load(open(path))
        prof["style"]["rules"] = ["Say customers, never users."]
        json.dump(prof, open(path, "w"))
        assert "starter" not in K.house_brief(slug).lower()     # starter voice excluded
        K.set_voice(slug, "We write short.")
        shutil.copyfile(SAMPLE, os.path.join(kits, slug, "examples", "q3.pptx"))
        KI.learn(slug)
        brief = K.house_brief(slug)
        assert "Say customers, never users." in brief
        assert "We write short." in brief
        assert "bullets" in brief


def test_a_kit_is_an_organisation_and_wins_a_name_clash():
    with sandbox() as kits:
        slug = K.create_kit("Default", "Our own default")
        listed = {o["slug"]: o for o in O.list_orgs()}
        assert listed["default"]["kit"] is True
        assert O.load_org("default").tagline == "Our own default"


def test_learned_layouts_break_ties_but_never_beat_structure():
    from pptx import Presentation
    from deckengine.native import layout_roles, pick_layout_for
    prs = Presentation(SAMPLE)
    slide = {"title": "Compare", "bullets": list("abcdef")}            # wants two bodies
    two = pick_layout_for(prs, slide)
    assert len(layout_roles(two)["bodies"]) >= 2
    # preferring a one-body layout must not win a slide that needs two
    one_body = next(l.name for l in prs.slide_layouts if len(layout_roles(l)["bodies"]) == 1)
    still = pick_layout_for(prs, slide, preferred=(one_body,))
    assert len(layout_roles(still)["bodies"]) >= 2


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
