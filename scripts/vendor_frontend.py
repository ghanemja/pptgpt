#!/usr/bin/env python3
"""Vendor the browser libraries and web fonts into frontend/vendor/.

pptgpt makes no network calls at runtime, so the pages cannot load React,
Babel, pdf.js, JSZip or their fonts from a CDN. This script fetches them ONCE,
here, and the result is committed. Run it again only to change a version:

    python scripts/vendor_frontend.py           # fetch, verify, write
    python scripts/vendor_frontend.py --check   # verify committed files only

Libraries are fetched from BOTH unpkg and jsDelivr. Each mirror serves the
same npm tarball, so the bytes must match exactly; if they do not, the script
refuses to write anything. Fonts come from Google Fonts (they have one
origin), latin and latin-ext subsets only.

Every file's SHA-384 is recorded in frontend/vendor/MANIFEST.json, and
--check re-hashes the committed files against it (no network).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "frontend" / "vendor"
FONTS = VENDOR / "fonts"
MANIFEST = VENDOR / "MANIFEST.json"

UNPKG = "https://unpkg.com/{pkg}@{ver}/{path}"
JSDELIVR = "https://cdn.jsdelivr.net/npm/{pkg}@{ver}/{path}"


@dataclass(frozen=True)
class Lib:
    pkg: str
    ver: str
    path: str      # path inside the npm package
    dest: str      # path under frontend/vendor/
    license: str


LIBS: list[Lib] = [
    Lib("react", "18.3.1", "umd/react.production.min.js",
        "react-18.3.1/react.production.min.js", "MIT"),
    Lib("react-dom", "18.3.1", "umd/react-dom.production.min.js",
        "react-dom-18.3.1/react-dom.production.min.js", "MIT"),
    Lib("@babel/standalone", "7.29.0", "babel.min.js",
        "babel-standalone-7.29.0/babel.min.js", "MIT"),
    Lib("pdfjs-dist", "3.11.174", "legacy/build/pdf.min.js",
        "pdfjs-dist-3.11.174/pdf.min.js", "Apache-2.0"),
    Lib("pdfjs-dist", "3.11.174", "legacy/build/pdf.worker.min.js",
        "pdfjs-dist-3.11.174/pdf.worker.min.js", "Apache-2.0"),
    Lib("jszip", "3.10.1", "dist/jszip.min.js",
        "jszip-3.10.1/jszip.min.js", "MIT OR GPL-3.0"),
]

# Every family and weight the stylesheets imported from Google Fonts (the old
# pages are deleted; workspace.css is the one left). One request, one fonts.css.
FONT_FAMILIES = [
    "IBM+Plex+Sans:wght@400;500;600;700",
    "IBM+Plex+Mono:wght@400;500;600",
    "IBM+Plex+Serif:ital,wght@0,400;0,500;0,600;1,400;1,500",
    "Lato:ital,wght@0,300;0,400;0,700;0,900;1,400;1,700",
    "Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600",
    "Space+Grotesk:wght@400;500;600;700",
    "Manrope:wght@300;400;500;600;700;800",
]
FONT_CSS = ("https://fonts.googleapis.com/css2?"
            + "&".join("family=" + f for f in FONT_FAMILIES) + "&display=swap")
FONT_SUBSETS = ("latin", "latin-ext")
# Google Fonts picks the format from the User-Agent; a current Chrome gets woff2.
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        return r.read()


def sha384(data: bytes) -> str:
    return "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode()


def fetch_lib(lib: Lib) -> bytes:
    a_url = UNPKG.format(pkg=lib.pkg, ver=lib.ver, path=lib.path)
    b_url = JSDELIVR.format(pkg=lib.pkg, ver=lib.ver, path=lib.path)
    a, b = fetch(a_url), fetch(b_url)
    if a != b:
        raise SystemExit(
            f"REFUSED: {lib.pkg}@{lib.ver}/{lib.path} differs between mirrors\n"
            f"  unpkg    {sha384(a)}  ({len(a)} bytes)\n"
            f"  jsDelivr {sha384(b)}  ({len(b)} bytes)\n"
            "Nothing was written.")
    if not a:
        raise SystemExit(f"REFUSED: {a_url} is empty")
    return a


_FACE = re.compile(r"/\*\s*([\w-]+)\s*\*/\s*(@font-face\s*\{[^}]*\})")


def _prop(block: str, name: str) -> str:
    m = re.search(rf"{name}\s*:\s*([^;]+);", block)
    return m.group(1).strip() if m else ""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def fetch_fonts() -> tuple[str, dict[str, bytes], list[dict]]:
    """Return (fonts.css text, {filename: bytes}, manifest entries)."""
    css = fetch(FONT_CSS).decode("utf-8")
    faces = [(subset, block) for subset, block in _FACE.findall(css)
             if subset in FONT_SUBSETS]
    if not faces:
        raise SystemExit("REFUSED: Google Fonts returned no latin @font-face rules")

    # A variable font is one file serving every weight; name it once.
    by_url: dict[str, list[tuple[str, str]]] = {}
    for subset, block in faces:
        url = re.search(r"url\(([^)]+)\)", block).group(1).strip("'\"")
        by_url.setdefault(url, []).append((subset, block))

    names: dict[str, str] = {}
    files: dict[str, bytes] = {}
    entries: list[dict] = []
    for url, uses in by_url.items():
        subset, block = uses[0]
        family = _prop(block, "font-family").strip("'\"")
        style = _prop(block, "font-style")
        weights = sorted({_prop(b, "font-weight") for _, b in uses})
        weight = weights[0] if len(weights) == 1 else "var"
        name = f"{_slug(family)}-{style}-{_slug(weight)}-{subset}.woff2"
        if not url.endswith(".woff2"):
            raise SystemExit(f"REFUSED: {family} {weight} is not woff2: {url}")
        data = fetch(url)
        names[url] = name
        files[name] = data
        entries.append({"file": f"fonts/{name}", "source": url,
                        "family": family, "style": style,
                        "weight": " ".join(weights), "subset": subset,
                        "license": "OFL-1.1", "bytes": len(data),
                        "sha384": sha384(data)})

    out = ["/* Generated by scripts/vendor_frontend.py from Google Fonts. Do not edit.",
           " * Families are under the SIL Open Font License 1.1 (see PROVENANCE.md).",
           " * Subsets: " + ", ".join(FONT_SUBSETS) + ". */", ""]
    for subset, block in faces:
        url = re.search(r"url\(([^)]+)\)", block).group(1).strip("'\"")
        out.append(f"/* {subset} */")
        out.append(block.replace(url, names[url]))
    return "\n".join(out) + "\n", files, entries


def check() -> int:
    manifest = json.loads(MANIFEST.read_text())
    bad = 0
    for e in manifest["files"]:
        p = VENDOR / e["file"]
        if not p.is_file():
            print(f"MISSING  {e['file']}"); bad += 1
        elif sha384(p.read_bytes()) != e["sha384"]:
            print(f"CHANGED  {e['file']}"); bad += 1
    print(f"{len(manifest['files']) - bad}/{len(manifest['files'])} vendored files match MANIFEST.json")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="verify the committed files against MANIFEST.json; no network")
    args = ap.parse_args()
    if args.check:
        return check()

    # Fetch and verify everything before writing anything.
    libs = [(lib, fetch_lib(lib)) for lib in LIBS]
    font_css, font_files, font_entries = fetch_fonts()

    entries: list[dict] = []
    for lib, data in libs:
        dest = VENDOR / lib.dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        entries.append({"file": lib.dest, "package": lib.pkg, "version": lib.ver,
                        "path": lib.path, "license": lib.license,
                        "sources": [UNPKG.format(pkg=lib.pkg, ver=lib.ver, path=lib.path),
                                    JSDELIVR.format(pkg=lib.pkg, ver=lib.ver, path=lib.path)],
                        "bytes": len(data), "sha384": sha384(data)})
        print(f"ok  {lib.dest}  ({len(data):,} bytes, unpkg == jsDelivr)")

    FONTS.mkdir(parents=True, exist_ok=True)
    for old in FONTS.glob("*.woff2"):
        if old.name not in font_files:
            old.unlink()
    for name, data in font_files.items():
        (FONTS / name).write_bytes(data)
    (FONTS / "fonts.css").write_text(font_css)
    css_bytes = font_css.encode()
    entries.extend(font_entries)
    entries.append({"file": "fonts/fonts.css", "source": FONT_CSS,
                    "note": "generated: Google's CSS, latin + latin-ext only, urls made local",
                    "bytes": len(css_bytes), "sha384": sha384(css_bytes)})
    print(f"ok  fonts/  ({len(font_files)} woff2 files + fonts.css)")

    MANIFEST.write_text(json.dumps({
        "generated_by": "scripts/vendor_frontend.py",
        "verify": "python scripts/vendor_frontend.py --check",
        "files": entries,
    }, indent=2) + "\n")
    print(f"wrote {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
