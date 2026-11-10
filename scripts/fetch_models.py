#!/usr/bin/env python3
"""One-time setup: download the semantic model into models/.

pptgpt never downloads anything while it runs. The sentence-transformers model
behind the storyboard and thread map (deckengine/semantics.py) is fetched here,
once, after `pip install -r requirements.txt`:

    .venv/bin/python scripts/fetch_models.py

It lands in models/all-MiniLM-L6-v2/ (git-ignored, about 90 MB) and the
server loads it from there with local_files_only. Without it, the app still
works: semantics falls back to word overlap and says so once in the terminal.

To install on a machine with no internet, run this on one that has it and
copy the models/ folder across.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deckengine import semantics  # noqa: E402  (MODEL_REPO, MODEL_DIR)

# Pinned so every machine gets the same weights.
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

# What sentence-transformers needs to load the model, and its licence (in
# README.md). The repo also carries ONNX, OpenVINO, TF and Rust copies of the
# same weights; those are skipped.
FILES = [
    "README.md",
    "modules.json",
    "config.json",
    "config_sentence_transformers.json",
    "sentence_bert_config.json",
    "1_Pooling/config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Download the semantic model into models/.")
    ap.add_argument("--revision", default=REVISION, help="model repo commit (default: pinned)")
    ap.add_argument("--force", action="store_true", help="download again even if present")
    args = ap.parse_args()

    dest = semantics.MODEL_DIR
    if semantics.model_present() and not args.force:
        print(f"Already there: {dest.relative_to(ROOT)}  (use --force to download again)")
    else:
        # This is the one step that is meant to go online, even from a shell
        # that exported HF_HUB_OFFLINE=1 for the server.
        os.environ["HF_HUB_OFFLINE"] = "0"
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print("huggingface_hub is missing. Run: .venv/bin/pip install -r requirements.txt",
                  file=sys.stderr)
            return 1
        print(f"Downloading {semantics.MODEL_REPO} @ {args.revision[:12]} -> {dest.relative_to(ROOT)}")
        snapshot_download(repo_id=semantics.MODEL_REPO, revision=args.revision,
                          allow_patterns=FILES, local_dir=str(dest))

    # Prove it loads the way the server will load it: offline, from disk.
    semantics.reset_model()
    vec = semantics.embed_text("pptgpt offline check")
    if vec is None:
        print("The model downloaded but does not load; see the message above.", file=sys.stderr)
        return 1
    print(f"OK: loads offline from {dest.relative_to(ROOT)} ({len(vec)}-dim embeddings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
