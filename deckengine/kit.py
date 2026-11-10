"""kit.py — a company's kit: everything that makes a deck sound like them.

A kit is ONE FOLDER per company under `kits/`. The folder is the source of
truth. There are three ways to put things in it, and they all end up in the
same place:

  1. Upload through the UI      -> files are written into the folder
  2. Point the UI at a folder    -> files are copied in, or linked in place
  3. Move files in by hand       -> the next scan picks them up

So nothing about the kit lives anywhere but the filesystem, and a kit can be
zipped, versioned, or handed to a colleague as a directory.

    kits/<slug>/
      kit.json          name, description, linked source folders
      profile.json      scoping questions, narrative arc, style rules
      voice.md          how the company writes
      template.potx     the master (any .potx / .pptx at the top level)
      examples/         decks the company considers good (.pptx)
      assets/
        assets.csv      file,label,tags,use,license
        icons/ images/ clipart/
      learned.json      written by `learn` — what the examples taught

Conventions live here; geometry never does. A kit can name a template, which
owns its own layouts (see native.py); nothing in a kit places a box.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KITS_DIR = os.path.join(ROOT, "kits")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")

TEMPLATE_EXT = (".potx", ".pptx")
EXAMPLE_EXT = (".pptx",)
IMAGE_EXT = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp")
VOICE_EXT = (".md", ".txt")

MAX_FILE_BYTES = 60 * 1024 * 1024        # one deck or one image
MAX_IMPORT_FILES = 2000                  # one "point at a folder" run

# Words that mark a top-level .pptx as the template rather than an example.
_TEMPLATE_HINT = re.compile(r"(template|master|theme|brand)", re.I)

ASSET_COLUMNS = ("file", "label", "tags", "use", "license")


class KitError(ValueError):
    """Something about a kit we will not do — said plainly to the user."""


# ---- paths -----------------------------------------------------------------

def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:48] or "company"


def kit_dir(slug: str) -> str:
    if not _SLUG_RE.match(slug or ""):
        raise KitError(f"bad kit name {slug!r}")
    return os.path.join(KITS_DIR, slug)


def _require(slug: str) -> str:
    d = kit_dir(slug)
    if not os.path.isdir(d):
        raise KitError(f"no kit {slug!r}")
    return d


def _within(base: str, path: str) -> bool:
    base = os.path.realpath(base)
    path = os.path.realpath(path)
    return path == base or path.startswith(base + os.sep)


def _safe_name(filename: str) -> str:
    """A filename that cannot escape the folder it is written into."""
    name = os.path.basename(str(filename or "").replace("\\", "/"))
    name = re.sub(r"[^\w.\- ()&+]", "_", name).strip(" .")
    if not name or name in (".", ".."):
        raise KitError(f"unusable file name {filename!r}")
    return name[:160]


# ---- manifest --------------------------------------------------------------

def _manifest_path(slug: str) -> str:
    return os.path.join(kit_dir(slug), "kit.json")


def read_manifest(slug: str) -> dict[str, Any]:
    path = _manifest_path(slug)
    if not os.path.isfile(path):
        return {"name": slug, "description": "", "sources": {"examples": [], "assets": []}}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("name", slug)
    data.setdefault("description", "")
    src = data.setdefault("sources", {})
    src.setdefault("examples", [])
    src.setdefault("assets", [])
    return data


def write_manifest(slug: str, data: dict[str, Any]) -> None:
    with open(_manifest_path(slug), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


# ---- creating a kit --------------------------------------------------------

_STARTER_VOICE = """# How we write

Replace this with your company's writing guide. Short and specific beats long
and general. Examples of what helps:

- Lead with the conclusion. The title is the claim; the body is the evidence.
- Numbers carry a unit, a comparison, and a date.
- We say "customers", never "users". We say "revenue", never "top line".
- No exclamation marks on slides.
"""


def create_kit(name: str, description: str = "") -> str:
    """A new, empty kit with the folder structure in place. Returns its slug."""
    slug = slugify(name)
    d = kit_dir(slug)
    if os.path.exists(d):
        raise KitError(f"a kit called {slug!r} already exists")

    for sub in ("examples", "assets/icons", "assets/images", "assets/clipart"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)

    # Start from the default profile so the Scope interview works on day one.
    default = os.path.join(ROOT, "orgs", "default.json")
    profile: dict[str, Any] = {}
    if os.path.isfile(default):
        with open(default, "r", encoding="utf-8") as fh:
            profile = json.load(fh)
    profile["name"] = name.strip() or slug
    profile["tagline"] = description.strip() or f"{profile['name']}'s house style."
    profile["examples"] = []
    # The scoping interview and narrative arc are a sensible start. The style
    # rules are not: they are the company's to state, and inheriting ours
    # ("at most three points") would contradict what its own decks teach the
    # moment learning runs. Start empty; learning offers suggestions.
    style = dict(profile.get("style") or {})
    style["rules"] = []
    style["banned"] = []
    profile["style"] = style
    with open(os.path.join(d, "profile.json"), "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=2)
        fh.write("\n")

    with open(os.path.join(d, "voice.md"), "w", encoding="utf-8") as fh:
        fh.write(_STARTER_VOICE)

    with open(os.path.join(d, "assets", "assets.csv"), "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow(ASSET_COLUMNS)

    write_manifest(slug, {"name": name.strip() or slug, "description": description.strip(),
                          "sources": {"examples": [], "assets": []}})
    return slug


def list_kits() -> list[dict[str, Any]]:
    out = []
    if not os.path.isdir(KITS_DIR):
        return out
    for slug in sorted(os.listdir(KITS_DIR)):
        d = os.path.join(KITS_DIR, slug)
        if not os.path.isdir(d) or not _SLUG_RE.match(slug) or slug.startswith("_"):
            continue
        try:
            m = read_manifest(slug)
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"slug": slug, "name": m.get("name") or slug,
                    "description": m.get("description") or ""})
    return out


# ---- sorting files into the kit -------------------------------------------

def classify(filename: str, part: Optional[str] = None, *, top_level: bool = True) -> Optional[str]:
    """Where a file belongs in a kit, or None if it does not belong at all.

    `part` is the caller's explicit intent ("examples", "template", ...) and
    wins when it is compatible with the file type. Without it, the type and
    name decide: a .potx is always a template, a .pptx is an example unless
    its name says template/master/brand, an image is an asset.
    """
    base = os.path.basename(filename).lower()
    ext = os.path.splitext(base)[1]

    if part:
        allowed = {
            "template": TEMPLATE_EXT,
            "examples": EXAMPLE_EXT,
            "assets": IMAGE_EXT + (".csv",),
            "voice": VOICE_EXT,
            "profile": (".json",),
        }.get(part)
        if allowed is None:
            raise KitError(f"unknown kit part {part!r}")
        if ext not in allowed:
            return None
        if part == "assets" and ext == ".csv":
            return "assets_csv"
        return part

    if base == "profile.json":
        return "profile"
    if base == "assets.csv":
        return "assets_csv"
    if ext in VOICE_EXT and (base.startswith("voice") or base.startswith("style")
                             or base.startswith("writing")):
        return "voice"
    if ext == ".potx":
        return "template"
    if ext == ".pptx":
        if top_level and _TEMPLATE_HINT.search(base):
            return "template"
        return "examples"
    if ext in IMAGE_EXT:
        return "assets"
    return None


def _destination(slug: str, part: str, filename: str, subdir: str = "") -> str:
    d = kit_dir(slug)
    name = _safe_name(filename)
    if part == "template":
        return os.path.join(d, name)
    if part == "examples":
        return os.path.join(d, "examples", name)
    if part == "assets":
        bucket = subdir if subdir in ("icons", "images", "clipart") else (
            "icons" if name.lower().endswith(".svg") else "images")
        return os.path.join(d, "assets", bucket, name)
    if part == "assets_csv":
        return os.path.join(d, "assets", "assets.csv")
    if part == "voice":
        return os.path.join(d, "voice.md")
    if part == "profile":
        return os.path.join(d, "profile.json")
    raise KitError(f"unknown kit part {part!r}")


def _validate_payload(part: str, data: bytes, filename: str) -> None:
    if len(data) > MAX_FILE_BYTES:
        raise KitError(f"{filename} is larger than {MAX_FILE_BYTES // (1024 * 1024)}MB")
    if not data:
        raise KitError(f"{filename} is empty")
    if part in ("template", "examples") and not data.startswith(b"PK"):
        raise KitError(f"{filename} is not a PowerPoint file (.pptx/.potx are zip archives)")
    if part == "profile":
        try:
            from .org import parse_org
            parse_org(json.loads(data.decode("utf-8")), "check")
        except Exception as e:
            raise KitError(f"profile.json is not valid: {e}") from e
    if part == "assets_csv":
        parse_assets_csv(data.decode("utf-8-sig"))      # raises on a bad header


def add_files(slug: str, files: Iterable[tuple[str, bytes]], part: Optional[str] = None,
              subdir: str = "") -> dict[str, Any]:
    """Write uploaded files into the kit. Returns what went where, and why not."""
    _require(slug)
    stored, skipped = [], []
    for filename, data in files:
        try:
            where = classify(filename, part)
            if where is None:
                skipped.append({"file": filename, "reason": "not a file type a kit uses"})
                continue
            _validate_payload(where, data, filename)
            dest = _destination(slug, where, filename, subdir)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if where == "assets_csv" and os.path.isfile(dest):
                data = _merge_assets_csv(dest, data)
            with open(dest, "wb") as fh:
                fh.write(data)
            stored.append({"file": filename, "part": where,
                           "path": os.path.relpath(dest, kit_dir(slug))})
        except KitError as e:
            skipped.append({"file": filename, "reason": str(e)})
    return {"stored": stored, "skipped": skipped}


def import_path(slug: str, path: str, *, mode: str = "copy",
                part: Optional[str] = None) -> dict[str, Any]:
    """Bring in a folder on this machine — a shared drive of decks, say.

    `copy` makes the kit self-contained. `link` leaves the files where they
    are and records the folder in kit.json, which suits a large corpus that
    is already maintained somewhere else. Symlinks are never followed, and
    only file types a kit uses are touched.
    """
    _require(slug)
    if mode not in ("copy", "link"):
        raise KitError("mode must be 'copy' or 'link'")
    src = os.path.expanduser(str(path or "").strip())
    if not src or not os.path.isabs(src):
        raise KitError("give a full folder path, e.g. /Users/you/Decks")
    if os.path.islink(src):
        raise KitError("that path is a symlink; point at the real folder")
    if not os.path.isdir(src):
        raise KitError(f"no folder at {src}")
    if _within(KITS_DIR, src):
        raise KitError("that folder is already inside kits/")

    if mode == "link":
        target = part or "examples"
        if target not in ("examples", "assets"):
            raise KitError("only examples or assets can be linked in place")
        m = read_manifest(slug)
        real = os.path.realpath(src)
        if real not in m["sources"][target]:
            m["sources"][target].append(real)
        write_manifest(slug, m)
        found = sum(1 for _ in _walk(real, EXAMPLE_EXT if target == "examples" else IMAGE_EXT))
        return {"linked": real, "part": target, "files": found, "stored": [], "skipped": []}

    batch: list[tuple[str, bytes, str]] = []
    skipped: list[dict[str, str]] = []
    for full in _walk(src, None):
        if len(batch) >= MAX_IMPORT_FILES:
            skipped.append({"file": full, "reason": f"stopped after {MAX_IMPORT_FILES} files"})
            break
        rel = os.path.relpath(full, src)
        top = os.sep not in rel
        parent = os.path.basename(os.path.dirname(full)).lower()
        where = classify(full, part, top_level=top)
        if where is None:
            continue
        try:
            if os.path.getsize(full) > MAX_FILE_BYTES:
                skipped.append({"file": rel, "reason": "too large"})
                continue
            with open(full, "rb") as fh:
                batch.append((full, fh.read(), parent))
        except OSError as e:
            skipped.append({"file": rel, "reason": str(e)})

    stored = []
    for full, data, parent in batch:
        rep = add_files(slug, [(os.path.basename(full), data)], part,
                        subdir=parent if parent in ("icons", "images", "clipart") else "")
        stored.extend(rep["stored"])
        skipped.extend(rep["skipped"])
    return {"stored": stored, "skipped": skipped}


def _walk(root: str, exts: Optional[tuple[str, ...]]):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            if f.startswith(".") or f.startswith("~$"):      # Office lock files
                continue
            full = os.path.join(dirpath, f)
            if os.path.islink(full):
                continue
            if exts and os.path.splitext(f)[1].lower() not in exts:
                continue
            yield full


# ---- assets ----------------------------------------------------------------

@dataclass
class Asset:
    file: str                  # path relative to the kit (or absolute, if linked)
    label: str
    tags: list[str] = field(default_factory=list)
    use: str = ""
    license: str = ""
    labeled: bool = True
    linked: bool = False


def parse_assets_csv(text: str) -> list[dict[str, str]]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    if "file" not in header or "label" not in header:
        raise KitError("assets.csv needs at least the columns: file,label "
                       f"(full set: {','.join(ASSET_COLUMNS)})")
    out = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        rec = {h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(header)}
        if rec.get("file"):
            out.append(rec)
    return out


def _merge_assets_csv(existing_path: str, incoming: bytes) -> bytes:
    """A second assets.csv adds to the first rather than replacing it."""
    with open(existing_path, "r", encoding="utf-8-sig") as fh:
        old = parse_assets_csv(fh.read())
    new = parse_assets_csv(incoming.decode("utf-8-sig"))
    by_file = {r["file"]: r for r in old}
    for r in new:
        by_file[r["file"]] = {**by_file.get(r["file"], {}), **{k: v for k, v in r.items() if v}}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(ASSET_COLUMNS)
    for r in by_file.values():
        w.writerow([r.get(c, "") for c in ASSET_COLUMNS])
    return buf.getvalue().encode("utf-8")


def _label_from_filename(name: str) -> str:
    stem = os.path.splitext(os.path.basename(name))[0]
    return re.sub(r"[_\-]+", " ", stem).strip()


def assets(slug: str) -> list[Asset]:
    """Every asset in the kit, labelled by assets.csv where it can be.

    Files with no row in the CSV still appear, labelled from their file name
    and flagged `labeled=False` — usable, but the setup screen asks for a
    real label, because the engine finds assets by label and tag.
    """
    d = _require(slug)
    rows: dict[str, dict[str, str]] = {}
    csv_path = os.path.join(d, "assets", "assets.csv")
    if os.path.isfile(csv_path):
        with open(csv_path, "r", encoding="utf-8-sig") as fh:
            for r in parse_assets_csv(fh.read()):
                rows[os.path.normpath(r["file"])] = r

    found: list[Asset] = []
    base = os.path.join(d, "assets")
    for full in _walk(base, IMAGE_EXT) if os.path.isdir(base) else []:
        rel_kit = os.path.relpath(full, d)
        rel_assets = os.path.relpath(full, base)
        row = (rows.get(os.path.normpath(rel_assets)) or rows.get(os.path.normpath(rel_kit))
               or rows.get(os.path.basename(full)))
        found.append(_asset_from(rel_kit, row))

    for src in read_manifest(slug)["sources"]["assets"]:
        if os.path.isdir(src):
            # A linked library is kept somewhere else, so it labels itself:
            # its own assets.csv (paths relative to that folder) comes first,
            # then the kit's CSV by file name.
            own: dict[str, dict[str, str]] = {}
            own_csv = os.path.join(src, "assets.csv")
            if os.path.isfile(own_csv) and not os.path.islink(own_csv):
                try:
                    with open(own_csv, "r", encoding="utf-8-sig") as fh:
                        for r in parse_assets_csv(fh.read()):
                            own[os.path.normpath(r["file"])] = r
                except (KitError, OSError, UnicodeDecodeError):
                    own = {}
            for full in _walk(src, IMAGE_EXT):
                rel = os.path.normpath(os.path.relpath(full, src))
                row = (own.get(rel) or own.get(os.path.basename(full))
                       or rows.get(os.path.basename(full)))
                a = _asset_from(full, row)
                a.linked = True
                found.append(a)
    return found


def _asset_from(path: str, row: Optional[dict[str, str]]) -> Asset:
    if row and row.get("label"):
        tags = [t.strip().lower() for t in re.split(r"[;,|]", row.get("tags", "")) if t.strip()]
        return Asset(file=path, label=row["label"], tags=tags,
                     use=row.get("use", ""), license=row.get("license", ""))
    return Asset(file=path, label=_label_from_filename(path), labeled=False)


_STOP = set("a an the and or of to in on for with at by is are be this that we our your".split())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP and len(w) > 1}


def search_assets(slug: str, query: str, limit: int = 24) -> list[dict[str, Any]]:
    """Assets ranked by how well their label and tags match the query.

    Deterministic: a tag hit counts double a label hit, and an unlabelled
    file can only match on its file name. No embedding model, so the same
    query always returns the same order.
    """
    q = _words(query)
    scored = []
    for a in assets(slug):
        label = _words(a.label)
        tags = set()
        for t in a.tags:
            tags |= _words(t)
        score = 2 * len(q & tags) + len(q & label) if q else 0
        if q and score == 0:
            continue
        scored.append((score, a.labeled, a))
    scored.sort(key=lambda s: (-s[0], not s[1], s[2].label.lower()))
    return [asset_dict(a) | {"score": s} for s, _, a in scored[:limit]]


def asset_dict(a: Asset) -> dict[str, Any]:
    return {"file": a.file, "label": a.label, "tags": a.tags, "use": a.use,
            "license": a.license, "labeled": a.labeled, "linked": a.linked}


def asset_path(slug: str, file: str) -> str:
    """The real path of an asset, refusing anything outside the kit or its links."""
    d = _require(slug)
    candidate = file if os.path.isabs(file) else os.path.join(d, file)
    allowed = [os.path.join(d, "assets")] + list(read_manifest(slug)["sources"]["assets"])
    if not any(_within(base, candidate) for base in allowed):
        raise KitError("that asset is not part of this kit")
    if not os.path.isfile(candidate) or os.path.splitext(candidate)[1].lower() not in IMAGE_EXT:
        raise KitError("no such asset")
    return os.path.realpath(candidate)


SVG_RASTER_PX = 768


def _upscale_svg(svg: str, px: int) -> str:
    """Set the root <svg> width/height to `px` on its longer side."""
    m = re.search(r"<svg\b[^>]*>", svg, re.I)
    if not m:
        return svg
    tag = m.group(0)
    vb = re.search(r'viewBox\s*=\s*"([\d.\s,-]+)"', tag)
    w, h = px, px
    if vb:
        parts = [float(x) for x in re.split(r"[\s,]+", vb.group(1).strip()) if x]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            ratio = parts[2] / parts[3]
            w, h = (px, round(px / ratio)) if ratio >= 1 else (round(px * ratio), px)
    new = re.sub(r'\s(width|height)\s*=\s*"[^"]*"', "", tag)
    new = new[:-1].rstrip("/").rstrip() + f' width="{w}" height="{h}">' if not tag.endswith("/>") \
        else new[:-2].rstrip() + f' width="{w}" height="{h}"/>'
    return svg.replace(tag, new, 1)


def asset_png(slug: str, file: str) -> Optional[bytes]:
    """An asset as PNG bytes, ready to place on a slide.

    PowerPoint can't take an SVG through python-pptx, and an icon library is
    mostly SVG — so SVGs are rasterised once through LibreOffice (already a
    dependency for exact previews) and cached by content. Other formats are
    normalised to PNG so GIF/WebP never reach the deck.
    """
    path = asset_path(slug, file)
    ext = os.path.splitext(path)[1].lower()

    if ext in (".png", ".jpg", ".jpeg"):
        with open(path, "rb") as fh:
            return fh.read()

    cache_dir = os.path.join(kit_dir(slug), ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    cached = os.path.join(cache_dir, f"{file_digest(path)}.png")
    if os.path.isfile(cached):
        with open(cached, "rb") as fh:
            return fh.read()

    if ext in (".gif", ".webp"):
        try:
            from PIL import Image
            with Image.open(path) as im:
                im.convert("RGBA").save(cached, "PNG")
        except Exception:
            return None
    elif ext == ".svg":
        from .template import _soffice
        soffice = _soffice()
        if not soffice:
            return None
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as work:
            staged = os.path.join(work, "asset.svg")
            # LibreOffice rasterises at the SVG's own declared size, and icon
            # files declare 24 or 96px. Placed in a picture slot that is a
            # blur, so the root size is raised before converting; viewBox
            # keeps the drawing's proportions.
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                svg = fh.read()
            svg = _upscale_svg(svg, SVG_RASTER_PX)
            with open(staged, "w", encoding="utf-8") as fh:
                fh.write(svg)
            try:
                subprocess.run(
                    [soffice, "--headless", "--norestore",
                     "-env:UserInstallation=file://" + os.path.join(work, "lo"),
                     "--convert-to", "png", "--outdir", work, staged],
                    check=True, timeout=60,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (subprocess.SubprocessError, OSError):
                return None
            out = os.path.join(work, "asset.png")
            if not os.path.isfile(out):
                return None
            shutil.copyfile(out, cached)
    else:
        return None

    with open(cached, "rb") as fh:
        return fh.read()


def resolver_for(default_slug: Optional[str]):
    """A function that turns a slide's image reference into PNG bytes.

    A reference names its own kit, so a slide keeps its picture even when
    the deck is later drawn under a different organisation.
    """
    def resolve(image: dict[str, Any]) -> Optional[bytes]:
        if not isinstance(image, dict) or not image.get("file"):
            return None
        slug = image.get("kit") or default_slug
        if not slug:
            return None
        try:
            return asset_png(slug, image["file"])
        except (KitError, OSError):
            return None
    return resolve


def preferred_layouts(slug: Optional[str]) -> tuple[str, ...]:
    if not slug or not os.path.isdir(os.path.join(KITS_DIR, slug)):
        return ()
    try:
        from .kit_ingest import norms
        return tuple((norms(slug) or {}).get("preferred_layouts") or ())
    except Exception:
        return ()


# ---- examples, templates, voice -------------------------------------------

def example_files(slug: str) -> list[str]:
    d = _require(slug)
    out = sorted(_walk(os.path.join(d, "examples"), EXAMPLE_EXT)) if os.path.isdir(
        os.path.join(d, "examples")) else []
    for src in read_manifest(slug)["sources"]["examples"]:
        if os.path.isdir(src):
            out.extend(sorted(_walk(src, EXAMPLE_EXT)))
    return out


def template_files(slug: str) -> list[str]:
    d = _require(slug)
    return sorted(os.path.join(d, f) for f in os.listdir(d)
                  if f.lower().endswith(TEMPLATE_EXT) and not f.startswith(("~$", ".")))


def voice_text(slug: str) -> str:
    path = os.path.join(_require(slug), "voice.md")
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return "" if text.strip() == _STARTER_VOICE.strip() else text


def set_voice(slug: str, text: str) -> None:
    with open(os.path.join(_require(slug), "voice.md"), "w", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")


def pin_templates(slug: str) -> list[dict[str, Any]]:
    """Register the kit's template files so the deck can be drawn on them.

    Templates are content-addressed, so registering the same file again is a
    no-op and the id is stable across machines.
    """
    from .template import save_template, TemplateError

    out = []
    for path in template_files(slug):
        try:
            with open(path, "rb") as fh:
                prof = save_template(fh.read(), os.path.basename(path))
            out.append({"id": prof.id, "name": prof.name, "file": os.path.basename(path)})
        except (TemplateError, OSError) as e:
            out.append({"id": None, "name": os.path.basename(path), "file": os.path.basename(path),
                        "error": str(e)})
    return out


def learned(slug: str) -> Optional[dict[str, Any]]:
    path = os.path.join(_require(slug), "learned.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---- what generation is told ----------------------------------------------

VOICE_BUDGET_CHARS = 1500


def house_brief(slug: Optional[str]) -> str:
    """The company's conventions, in a form a model can follow.

    Works for any organisation: a built-in profile contributes its rules; a
    kit adds its writing voice and the norms its own decks taught. Kept
    short on purpose — a small local model follows five specific rules far
    better than a pasted style guide, so the voice is truncated and the
    learned norms are stated as numbers.
    """
    if not slug:
        return ""
    lines: list[str] = []
    try:
        from .org import load_org
        prof = load_org(slug)
        for r in prof.style.rules[:8]:
            lines.append(f"- {r}")
        for b in prof.style.banned[:6]:
            lines.append(f"- Never: {b}")
    except Exception:
        pass

    if os.path.isdir(os.path.join(KITS_DIR, slug)):
        try:
            from .kit_ingest import norms as learned_norms
            n = learned_norms(slug) or {}
        except Exception:
            n = {}
        if n.get("max_points"):
            lines.append(f"- At most {n['max_points']} bullets.")
        if n.get("max_words_per_point"):
            lines.append(f"- Each bullet under {n['max_words_per_point']} words.")
        if n.get("title_words"):
            lines.append(f"- Titles around {n['title_words']} words"
                         + ("; a title states a claim." if n.get("titles_argue") else "."))
        voice = voice_text(slug).strip()
        if voice:
            if len(voice) > VOICE_BUDGET_CHARS:
                voice = voice[:VOICE_BUDGET_CHARS].rsplit("\n", 1)[0] + "\n…"
            lines.append("\nHouse voice:\n" + voice)

    return "\n".join(lines).strip()


# ---- the status the setup screen shows ------------------------------------

def scan(slug: str) -> dict[str, Any]:
    """Everything the setup screen needs: each part, its state, what to fix.

    Run on every open, so a file dropped in by hand shows up without any
    step but looking.
    """
    d = _require(slug)
    m = read_manifest(slug)

    profile_ok, profile_err, profile_name = False, "", m.get("name") or slug
    rules: list[str] = []
    ppath = os.path.join(d, "profile.json")
    if os.path.isfile(ppath):
        try:
            from .org import parse_org
            with open(ppath, "r", encoding="utf-8") as fh:
                prof = parse_org(json.load(fh), slug)
            profile_ok, profile_name = True, prof.name
            rules = list(prof.style.rules)
        except Exception as e:
            profile_err = str(e)
    else:
        profile_err = "missing — the default interview and rules apply"

    templates = pin_templates(slug)
    examples = example_files(slug)
    all_assets = assets(slug)
    unlabeled = [a for a in all_assets if not a.labeled]
    voice = voice_text(slug)
    learn = learned(slug)

    newest_example = max((os.path.getmtime(p) for p in examples), default=0)
    stale = bool(learn) and newest_example > float(learn.get("generated_epoch", 0))

    parts = [
        {"key": "profile", "label": "Profile & style rules", "ok": profile_ok,
         "detail": profile_err or "scoping questions, narrative arc and house rules",
         "path": "profile.json"},
        {"key": "template", "label": "PowerPoint template", "ok": any(t.get("id") for t in templates),
         "count": len(templates),
         "detail": ", ".join(t["file"] for t in templates) or "none — slides use the built-in look",
         "problems": [f"{t['file']}: {t['error']}" for t in templates if t.get("error")],
         "path": "*.potx / *.pptx (top level)"},
        {"key": "examples", "label": "Example decks", "ok": len(examples) > 0,
         "count": len(examples),
         "detail": (f"{len(examples)} deck{'s' if len(examples) != 1 else ''}"
                    + (f", {len(m['sources']['examples'])} linked folder(s)"
                       if m["sources"]["examples"] else "")) if examples else "none yet",
         "path": "examples/"},
        {"key": "assets", "label": "Icons & images", "ok": len(all_assets) > 0,
         "count": len(all_assets),
         "detail": (f"{len(all_assets)} file(s), {len(unlabeled)} without a label"
                    if all_assets else "none yet"),
         "problems": ([f"{len(unlabeled)} asset(s) have no row in assets.csv — "
                       "they are found by file name only"] if unlabeled else []),
         "path": "assets/ + assets/assets.csv"},
        {"key": "voice", "label": "Writing voice", "ok": bool(voice.strip()),
         "detail": (f"{len(voice.split())} words" if voice.strip()
                    else "still the starter text — replace it with your guide"),
         "path": "voice.md"},
        {"key": "learned", "label": "Learned from examples", "ok": bool(learn) and not stale,
         "detail": ("out of date — examples changed since the last run" if stale else
                    f"{learn['decks']} decks, {learn['slides']} slides" if learn else
                    "not run yet"),
         "path": "learned.json"},
    ]
    ready = sum(1 for p in parts if p["ok"])
    return {
        "slug": slug, "name": profile_name, "description": m.get("description", ""),
        "path": d, "parts": parts, "ready": ready, "total": len(parts),
        "templates": templates, "learned": learn, "stale": stale,
        "sources": m["sources"],
        # What the setup screen edits in place: the house rules already in
        # profile.json (so a suggested rule already adopted is not offered
        # again) and the voice guide's text ("" while it is the starter).
        "rules": rules, "voice_text": voice,
    }


def file_digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]
