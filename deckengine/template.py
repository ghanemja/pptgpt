"""template.py — an uploaded .pptx/.potx as a Theme plus constraints.

A template is brand, not layout. It tells the engine which colours and type
the deck speaks in, how much of the canvas is already spoken for (a logo
band, a footer), and what the slide size is. It does NOT tell the engine
where to put a stat.

That split is what keeps §0 intact:

  * extract_template() reads the file into a `TemplateProfile` — a Theme and
    a set of CONSTRAINTS (margins, reserved bands). Theme already carries
    margin_in/gap_in as constraints, so this is the same kind of value.
  * layout.py resolves every box as it always has, inside those margins.
  * render.py opens the template file as the presentation base, so masters,
    backgrounds, logos and footers come through underneath engine-placed
    shapes.

Nothing here emits a coordinate for a content box. The reserved bands are
inputs that SHRINK the area layout.py may use; they are not positions for
anything the engine draws.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from pptx import Presentation
from pptx.util import Emu

from .ir import Theme

# Where uploaded templates live. One directory, flat, content-addressed.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(ROOT, "uploads", "templates")

ALLOWED_EXT = (".pptx", ".potx")
MAX_BYTES = 40 * 1024 * 1024

_THEME_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
_COLOR_RE = re.compile(r"<a:(dk1|lt1|dk2|lt2|accent[1-6])>.*?val=\"([0-9A-Fa-f]{6})\"", re.S)
_FONT_RE = re.compile(r"<a:(majorFont|minorFont)>\s*<a:latin typeface=\"([^\"]*)\"")
_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_SLUG_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def _slug(name: str) -> str:
    """A display name that is safe to carry in a filename."""
    base = os.path.splitext(os.path.basename(name or ""))[0]
    return _SLUG_SAFE.sub("", base).strip()[:60] or "template"


class TemplateError(ValueError):
    """An upload we will not accept, or a stored template we cannot read."""


@dataclass
class ReservedBand:
    """Canvas the template has already spent — a logo strip, a footer rule.

    Expressed as an inset from one edge, in inches. This is a constraint on
    the engine's working area, not a box the engine draws into.
    """
    edge: str          # 'top' | 'bottom' | 'left' | 'right'
    inches: float


@dataclass
class TemplateProfile:
    id: str
    name: str
    slide_w: float
    slide_h: float
    theme: Theme
    reserved: list[ReservedBand] = field(default_factory=list)
    layouts: list[str] = field(default_factory=list)
    source: str = ""           # absolute path to the stored file

    def working_margins(self) -> dict[str, float]:
        """The margin the engine must respect on each edge, in inches."""
        m = {e: self.theme.margin_in for e in ("top", "bottom", "left", "right")}
        for band in self.reserved:
            if band.edge in m:
                m[band.edge] = max(m[band.edge], self.theme.margin_in + band.inches)
        return m


def _luma(hex_rgb: str) -> float:
    r, g, b = (int(hex_rgb[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _theme_xml(prs: Presentation) -> str:
    try:
        part = prs.slide_masters[0].part.part_related_by(_THEME_NS)
        return part.blob.decode("utf-8", "ignore")
    except Exception:
        return ""


def _reserved_bands(prs: Presentation, slide_w: float, slide_h: float) -> list[ReservedBand]:
    """Infer bands the master already occupies.

    Only shapes that are NOT content placeholders count — a logo, a footer
    rule, a decorative bar. A shape hugging an edge and occupying less than
    a quarter of that dimension reserves that edge.
    """
    bands: dict[str, float] = {}
    try:
        master = prs.slide_masters[0]
    except Exception:
        return []

    for shape in master.shapes:
        if getattr(shape, "is_placeholder", False):
            continue
        try:
            x, y = Emu(shape.left).inches, Emu(shape.top).inches
            w, h = Emu(shape.width).inches, Emu(shape.height).inches
        except Exception:
            continue
        if w <= 0 or h <= 0:
            continue
        if h <= slide_h / 4:
            if y <= 0.05:
                bands["top"] = max(bands.get("top", 0.0), y + h)
            elif y + h >= slide_h - 0.05:
                bands["bottom"] = max(bands.get("bottom", 0.0), slide_h - y)
        if w <= slide_w / 4:
            if x <= 0.05:
                bands["left"] = max(bands.get("left", 0.0), x + w)
            elif x + w >= slide_w - 0.05:
                bands["right"] = max(bands.get("right", 0.0), slide_w - x)

    # A band wider than a third of the canvas is not a band; ignore it rather
    # than starve the engine of room.
    return [
        ReservedBand(edge=e, inches=round(v, 3))
        for e, v in sorted(bands.items())
        if 0.05 < v < (slide_h if e in ("top", "bottom") else slide_w) / 3
    ]


def profile_from_file(path: str, *, tid: str = "", name: str = "") -> TemplateProfile:
    """Read a .pptx/.potx into a TemplateProfile. Raises TemplateError."""
    try:
        prs = Presentation(path)
    except Exception as e:
        raise TemplateError(f"could not read the template: {e}") from e

    slide_w = Emu(prs.slide_width).inches
    slide_h = Emu(prs.slide_height).inches
    xml = _theme_xml(prs)
    colors = dict(_COLOR_RE.findall(xml))
    fonts = dict(_FONT_RE.findall(xml))

    accent = colors.get("accent1", "F96167")
    primary = colors.get("dk2") or colors.get("dk1") or "1E2761"
    secondary = colors.get("lt2") or colors.get("lt1") or "CADCFC"
    dark = _luma(primary) < 0.5

    theme = Theme(
        primary=primary,
        secondary=secondary,
        accent=accent,
        header_font=fonts.get("majorFont") or "Georgia",
        body_font=fonts.get("minorFont") or "Calibri",
        dark=dark,
        name=name or os.path.splitext(os.path.basename(path))[0],
    )

    return TemplateProfile(
        id=tid,
        name=theme.name,
        slide_w=round(slide_w, 4),
        slide_h=round(slide_h, 4),
        theme=theme,
        reserved=_reserved_bands(prs, slide_w, slide_h),
        layouts=[l.name for l in prs.slide_layouts],
        source=path,
    )


def save_template(data: bytes, filename: str) -> TemplateProfile:
    """Store an uploaded template and return its profile."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise TemplateError(f"{ext or 'that file'} is not a .pptx or .potx")
    if not data:
        raise TemplateError("the file is empty")
    if len(data) > MAX_BYTES:
        raise TemplateError(f"templates are capped at {MAX_BYTES // (1024 * 1024)}MB")

    tid = hashlib.sha256(data).hexdigest()[:12]
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    # The display name rides along in the filename, so a template re-read from
    # disk is still called what the user called it.
    path = os.path.join(TEMPLATES_DIR, f"{tid}__{_slug(filename)}{ext}")
    for stale in _candidates(tid):
        if stale != path:
            try:
                os.remove(stale)
            except OSError:
                pass
    if not os.path.exists(path):
        with open(path, "wb") as fh:
            fh.write(data)

    try:
        return profile_from_file(path, tid=tid, name=_slug(filename))
    except TemplateError:
        # Don't keep a file we cannot read.
        try:
            os.remove(path)
        except OSError:
            pass
        raise


def _candidates(tid: str) -> list[str]:
    """Stored files for this id, newest naming scheme first."""
    if not os.path.isdir(TEMPLATES_DIR):
        return []
    out = []
    for fname in sorted(os.listdir(TEMPLATES_DIR)):
        stem, ext = os.path.splitext(fname)
        if ext.lower() in ALLOWED_EXT and (stem == tid or stem.startswith(f"{tid}__")):
            out.append(os.path.join(TEMPLATES_DIR, fname))
    return out


def _path_for(tid: str) -> str:
    if not _ID_RE.match(tid or ""):
        raise TemplateError(f"bad template id {tid!r}")
    found = _candidates(tid)
    if found:
        return found[0]
    raise TemplateError(f"no template {tid!r}")


def _name_from_path(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.split("__", 1)[1] if "__" in stem else stem


def load_template(tid: str) -> TemplateProfile:
    path = _path_for(tid)
    return profile_from_file(path, tid=tid, name=_name_from_path(path))


def list_templates() -> list[dict[str, Any]]:
    """Every stored template. An unreadable file is skipped, not fatal."""
    out: list[dict[str, Any]] = []
    if not os.path.isdir(TEMPLATES_DIR):
        return out
    for fname in sorted(os.listdir(TEMPLATES_DIR)):
        stem, ext = os.path.splitext(fname)
        if ext.lower() not in ALLOWED_EXT:
            continue
        tid = stem.split("__", 1)[0]
        try:
            p = load_template(tid)
        except TemplateError:
            continue
        out.append(to_dict(p))
    return out


def delete_template(tid: str) -> bool:
    path = _path_for(tid)
    os.remove(path)
    cached = os.path.join(TEMPLATES_DIR, f"{tid}.backdrop.png")
    if os.path.isfile(cached):
        try:
            os.remove(cached)
        except OSError:
            pass
    return True


# ---- backdrop rasterisation ------------------------------------------------
#
# A palette is not a template. Showing one as a few colours in the preview
# while the export carries the master's logo, picture background and footer
# is a preview that lies. So we render the template's own master to a PNG —
# one empty slide through LibreOffice, which is the same engine PowerPoint
# files round-trip through everywhere else — and show THAT behind the
# engine-placed text.
#
# This is a picture of the template, not a source of layout: no coordinate
# from it reaches layout.py (R0.1). It is the backdrop, exactly as the
# template file is the backdrop at render time.

SOFFICE_CANDIDATES = (
    "soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
)
BACKDROP_TIMEOUT_S = 90


def _soffice() -> Optional[str]:
    """The LibreOffice binary, or None when this machine has none."""
    found = shutil.which(SOFFICE_CANDIDATES[0])
    if found:
        return found
    for path in SOFFICE_CANDIDATES[1:]:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def backdrop_available() -> bool:
    return _soffice() is not None


def _empty_deck_from(template_src: str, out_pptx: str) -> None:
    """One slide, no content, on the template's own master."""
    from .render import open_base
    prs, blank = open_base(template_src, 13.333, 7.5)
    prs.slides.add_slide(blank)
    prs.save(out_pptx)


def backdrop_png(tid: str, *, force: bool = False) -> Optional[str]:
    """Path to a PNG of the template's master, or None if we cannot make one.

    Cached beside the template and keyed by it, so the cost is paid once per
    upload rather than per preview.
    """
    src = _path_for(tid)
    out_png = os.path.join(TEMPLATES_DIR, f"{tid}.backdrop.png")
    if os.path.isfile(out_png) and not force:
        return out_png

    soffice = _soffice()
    if not soffice:
        return None

    with tempfile.TemporaryDirectory() as work:
        staged = os.path.join(work, "backdrop.pptx")
        try:
            _empty_deck_from(src, staged)
        except Exception:
            return None
        try:
            subprocess.run(
                [soffice, "--headless", "--norestore",
                 "-env:UserInstallation=file://" + os.path.join(work, "lo-profile"),
                 "--convert-to", "png:impress_png_Export", "--outdir", work, staged],
                check=True, timeout=BACKDROP_TIMEOUT_S,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (subprocess.SubprocessError, OSError):
            return None

        produced = os.path.join(work, "backdrop.png")
        if not os.path.isfile(produced):
            return None
        os.makedirs(TEMPLATES_DIR, exist_ok=True)
        shutil.copyfile(produced, out_png)
    return out_png


def sample_backdrop(tid: str) -> Optional[dict[str, Any]]:
    """The master's REAL background colour, read off the rendered backdrop.

    The theme's dk1/dk2 says what the brand's dark colour is, not what the
    slide's background actually looks like: a template can use a navy accent
    on white paper. Inferring "this is a dark template" from the theme put
    white type on a white master. The rasterised master is the ground truth,
    so the background is sampled from the middle band of it — away from the
    logo strips at the edges — and the text colour follows from that.
    """
    png = backdrop_png(tid)
    if not png:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(png) as im:
            im = im.convert("RGB")
            w, h = im.size
            band = im.crop((int(w * 0.15), int(h * 0.25), int(w * 0.85), int(h * 0.75)))
            counts = band.getcolors(band.size[0] * band.size[1]) or []
    except Exception:
        return None
    if not counts:
        return None

    _, (r, g, b) = max(counts, key=lambda c: c[0])
    hex_rgb = f"{r:02X}{g:02X}{b:02X}"
    return {"bg": hex_rgb, "dark": _luma(hex_rgb) < 0.5}


def to_dict(p: TemplateProfile) -> dict[str, Any]:
    d = asdict(p)
    d.pop("source", None)          # a filesystem path is not the UI's business
    d["margins"] = p.working_margins()
    d["hasBackdrop"] = bool(p.id) and os.path.isfile(
        os.path.join(TEMPLATES_DIR, f"{p.id}.backdrop.png"))
    if d["hasBackdrop"]:
        sampled = sample_backdrop(p.id)
        if sampled:
            # The rendered master wins over the theme's idea of itself.
            d["backdrop"] = sampled
            d["theme"]["dark"] = sampled["dark"]
    return d


def template_path(tid: Optional[str]) -> Optional[str]:
    """The .pptx to open as a render base, or None for the engine's own."""
    if not tid:
        return None
    try:
        return _path_for(tid)
    except TemplateError:
        return None
