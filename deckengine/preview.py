"""preview.py — exact slide previews, rendered the way they export.

The workspace preview was HTML pretending to be PowerPoint: a div with the
template's colours, its font NAMES, and a picture of its master behind. That
approximation drifts for a reason no amount of CSS fixes — the browser can
only use fonts installed on the viewer's machine, so a template built in
Bookman Old Style silently renders in Lato and the preview quietly disagrees
with the file it exports.

So this does not emulate. It renders the real artefact: the slide goes
through the same spec_render path the export uses, onto the same template
master, and LibreOffice rasterises it. What you see is what the .pptx is,
including how the fonts actually resolve.

Cached by content: the same slide and template never render twice.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from typing import Any, Optional

from .template import TEMPLATES_DIR, _soffice, template_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREVIEW_DIR = os.path.join(ROOT, "uploads", "previews")
RENDER_TIMEOUT_S = 90

# Previews are cheap to regenerate and there is no value in an unbounded
# cache of superseded drafts.
MAX_CACHED = 400


def available() -> bool:
    return _soffice() is not None


def cache_key(spec: dict[str, Any], template_id: Optional[str]) -> str:
    payload = json.dumps({"spec": spec, "template": template_id or ""},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _trim_cache() -> None:
    try:
        files = [os.path.join(PREVIEW_DIR, f) for f in os.listdir(PREVIEW_DIR)
                 if f.endswith(".png")]
    except OSError:
        return
    if len(files) <= MAX_CACHED:
        return
    files.sort(key=os.path.getmtime)
    for path in files[:len(files) - MAX_CACHED]:
        try:
            os.remove(path)
        except OSError:
            pass


def native_png(slide: dict[str, Any], template_id: str,
               *, org: Optional[str] = None, force: bool = False) -> Optional[str]:
    """Render ONE workspace slide cast into the template's own layouts.

    `org` brings the company's learned layout preferences and its asset
    library; it is part of the cache key because it changes the render.
    """
    return _render(("native", slide, template_id, org or ""), force=force,
                   build=lambda out: _build_native(slide, template_id, out, org))


def _build_native(slide: dict[str, Any], template_id: str, out_pptx: str,
                  org: Optional[str] = None) -> None:
    from .kit import preferred_layouts, resolver_for
    from .native import render_native
    src = template_path(template_id)
    if not src:
        raise ValueError("no such template")
    render_native([slide], out_pptx, src,
                  preferred_layouts=preferred_layouts(org),
                  asset_resolver=resolver_for(org))


def slide_png(spec: dict[str, Any], template_id: Optional[str] = None,
              *, org: Optional[str] = None, force: bool = False) -> Optional[str]:
    """Render ONE slide spec to a PNG exactly as it would export.

    Returns the cached path, or None when LibreOffice is unavailable or the
    render fails — callers fall back to the HTML preview rather than showing
    a broken image.
    """
    return _render(("spec", spec, template_id, org or ""), force=force,
                   build=lambda out: _build_spec(spec, template_id, out, org))


def _build_spec(spec: dict[str, Any], template_id: Optional[str], out_pptx: str,
                org: Optional[str] = None) -> None:
    from .kit import resolver_for
    from .spec_render import render_specs
    render_specs([spec], out_pptx, template_path=template_id and template_path(template_id),
                 asset_resolver=resolver_for(org))


def _render(key_parts, *, build, force: bool = False) -> Optional[str]:
    """Build a one-slide .pptx and rasterise it, cached by content."""
    key = hashlib.sha256(
        json.dumps(key_parts, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()[:20]
    out_png = os.path.join(PREVIEW_DIR, f"{key}.png")
    if os.path.isfile(out_png) and not force:
        os.utime(out_png, None)          # keep hot entries from being trimmed
        return out_png

    soffice = _soffice()
    if not soffice:
        return None

    with tempfile.TemporaryDirectory() as work:
        staged = os.path.join(work, "slide.pptx")
        try:
            build(staged)
        except Exception:
            return None
        try:
            subprocess.run(
                [soffice, "--headless", "--norestore",
                 "-env:UserInstallation=file://" + os.path.join(work, "lo-profile"),
                 "--convert-to", "png:impress_png_Export", "--outdir", work, staged],
                check=True, timeout=RENDER_TIMEOUT_S,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (subprocess.SubprocessError, OSError):
            return None

        produced = os.path.join(work, "slide.png")
        if not os.path.isfile(produced):
            return None
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        shutil.copyfile(produced, out_png)

    _trim_cache()
    return out_png
