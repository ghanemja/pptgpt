#!/usr/bin/env python3
"""
Deploy the PPTGPT (DeckEngine) backend to a public Hugging Face Space and wire
it to the shared Gemma endpoint + shared auth.

You run this (your HF token has the perms mine doesn't):

    python3 scripts/deploy_hf_space.py
    # or, with the venv that has huggingface_hub:
    ~/.hfvenv/bin/python scripts/deploy_hf_space.py

It: creates jang0294/pptgpt (Docker Space), uploads the backend, and sets the
env so narrative analysis runs on your Gemma endpoint with the same login as
Brain University.
"""
from __future__ import annotations

import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_ID   = "jang0294/pptgpt"
API_BASE  = "https://jang0294-pptgpt.hf.space"
GEMMA_BASE = "https://gr68sv7qu88n5pwk.us-east-1.aws.endpoints.huggingface.cloud/v1"

# Shared with Brain University so one login works across both apps.
BU_AUTH_USER     = "admin"
BU_AUTH_PASSWORD = "MJiqvzRqd9SVfw2kmI65og"
BU_AUTH_SECRET   = "-qLRPjwndg7PvJFWW9a8lRDYXVkEGQkG6eqF1hyKCFyOesGCycU3s3k3jGrP24B3"
NETLIFY_ORIGIN   = "https://pptgpt.netlify.app"

SPACE_README = """---
title: PPTGPT DeckEngine API
emoji: 📊
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: FastAPI backend for PPTGPT (narrative deck analysis)
---

# PPTGPT — DeckEngine backend

FastAPI service. Narrative analysis runs on the shared Gemma HF Inference
Endpoint (DECKENGINE_NARRATIVE_BACKEND=gemma + LOCAL_LLM_*). Login uses the
same BU_AUTH_* secret as Brain University.
"""


def _token() -> str:
    c = Path.home() / ".cache" / "huggingface" / "token"
    return c.read_text().strip() if c.exists() else ""


def main() -> int:
    try:
        from huggingface_hub import HfApi, create_repo
    except ImportError:
        print("pip install huggingface_hub first", file=sys.stderr); return 1
    tok = _token()
    api = HfApi(token=tok)
    try:
        print("auth:", api.whoami(token=tok).get("name"))
    except Exception as e:
        print("HF auth failed — run: huggingface-cli login", e, file=sys.stderr); return 1

    url = create_repo(REPO_ID, repo_type="space", space_sdk="docker",
                      exist_ok=True, token=tok)
    print("space:", url)

    readme = REPO_ROOT / ".space_readme.md"
    readme.write_text(SPACE_README)

    # Backend code the Dockerfile COPYs: server.py, deckengine/, frontend/,
    # requirements.txt — plus auth.py + Dockerfile.
    for d in ["deckengine", "frontend"]:
        p = REPO_ROOT / d
        if p.exists():
            api.upload_folder(folder_path=str(p), path_in_repo=d, repo_id=REPO_ID,
                              repo_type="space", token=tok,
                              ignore_patterns=["__pycache__/*", "*.pyc", ".DS_Store"])
            print("  uploaded", d + "/")
    for f in ["server.py", "auth.py", "requirements.txt", "Dockerfile"]:
        if (REPO_ROOT / f).exists():
            api.upload_file(path_or_fileobj=str(REPO_ROOT / f), path_in_repo=f,
                            repo_id=REPO_ID, repo_type="space", token=tok)
            print("  uploaded", f)
    api.upload_file(path_or_fileobj=str(readme), path_in_repo="README.md",
                    repo_id=REPO_ID, repo_type="space", token=tok)
    readme.unlink(missing_ok=True)

    # Wire env: Gemma backend + shared auth + CORS.
    vars_ = {
        "DECKENGINE_NARRATIVE_BACKEND": "gemma",
        "LOCAL_LLM_BASE":  GEMMA_BASE,
        "LOCAL_LLM_MODEL": "gemma",
        "BU_AUTH_USER":    BU_AUTH_USER,
        "CORS_ORIGINS":    NETLIFY_ORIGIN,
    }
    for k, v in vars_.items():
        api.add_space_variable(REPO_ID, k, v, token=tok)
    for k, v in {"LOCAL_LLM_KEY": tok,
                 "BU_AUTH_PASSWORD": BU_AUTH_PASSWORD,
                 "BU_AUTH_SECRET": BU_AUTH_SECRET}.items():
        api.add_space_secret(REPO_ID, k, v, token=tok)
    print("env wired: gemma backend + shared BU_AUTH + CORS")

    print("\nDONE — building ~5-10 min.")
    print("  Space: https://huggingface.co/spaces/" + REPO_ID)
    print("  API:   " + API_BASE)
    print("  Then set BU_API_BASE=" + API_BASE + " on the pptgpt Netlify site.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
