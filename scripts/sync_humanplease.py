#!/usr/bin/env python3
"""Vendor a pinned copy of the humanplease writing skills into pptgpt.

    python3 scripts/sync_humanplease.py --commit 7f7f2d0
    python3 scripts/sync_humanplease.py --commit <sha> --repo /path/to/humanplease

pptgpt never fetches humanplease at runtime: it is offline-first, and a live
fetch would let a change in that repo silently change everyone's slides. This
script copies the skill files from ONE commit into
deckengine/vendor/humanplease/ and records the full SHA in SOURCE.json.

What the model actually sees is NOT these files — it is the short slide
block in deckengine/humanplease_slides.md, written by hand from them (the
full skill is for prose and too long for a small model). So after syncing a
new commit, re-read the skills and update that block and its header; the
test suite fails until the header names the vendored commit.

It only reads the humanplease repo; it never writes to it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "deckengine", "vendor", "humanplease")
DEFAULT_REPO = "https://github.com/ghanemja/humanplease.git"
FILES = (
    "skills/natural-voice-writing/SKILL.md",
    "skills/natural-word-choice/SKILL.md",
)


def git(repo: str, *args: str) -> str:
    return subprocess.check_output(["git", "-C", repo, *args], text=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", required=True, help="humanplease commit to vendor (short or full SHA)")
    ap.add_argument("--repo", default=DEFAULT_REPO,
                    help="a local clone or a git URL (default: the GitHub repo)")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        repo = args.repo
        if not os.path.isdir(repo):
            print(f"cloning {repo} …")
            subprocess.check_call(["git", "clone", "-q", repo, os.path.join(tmp, "hp")])
            repo = os.path.join(tmp, "hp")
        sha = git(repo, "rev-parse", f"{args.commit}^{{commit}}").strip()
        subject = git(repo, "log", "-1", "--format=%s", sha).strip()

        os.makedirs(DEST, exist_ok=True)
        for rel in FILES:
            text = git(repo, "show", f"{sha}:{rel}")
            out = os.path.join(DEST, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"  {rel}")

    prev = None
    src_path = os.path.join(DEST, "SOURCE.json")
    if os.path.isfile(src_path):
        with open(src_path, encoding="utf-8") as fh:
            prev = json.load(fh).get("commit")
    with open(src_path, "w", encoding="utf-8") as fh:
        json.dump({
            "repo": "github.com/ghanemja/humanplease",
            "commit": sha,
            "subject": subject,
            "files": list(FILES),
            "synced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }, fh, indent=2)
        fh.write("\n")

    print(f"vendored humanplease @ {sha[:7]} ({subject}) -> {os.path.relpath(DEST, ROOT)}")
    if prev and prev != sha:
        print(f"\nThe pinned commit changed ({prev[:7]} -> {sha[:7]}). Re-derive "
              "deckengine/humanplease_slides.md from the new skills and update its header.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
