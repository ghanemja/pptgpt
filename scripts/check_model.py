#!/usr/bin/env python3
"""Check that the model pptgpt is configured to use actually answers.

    .venv/bin/python scripts/check_model.py

Reads the same environment the server does (scripts/start.sh loads .env
first). Makes one cheap, free request — a model list, never a generation —
so a wrong key, URL or model name shows up at start-up instead of as
generic fallback slides later. Prints one line per finding; exits 1 if the
configured backend will not work.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

OK, WARN, FAIL = "\033[32m✓\033[0m", "\033[33m!\033[0m", "\033[31m✗\033[0m"


def say(mark: str, msg: str) -> None:
    print(f"  {mark} {msg}")


def get(url: str, headers: dict[str, str], timeout: float = 6) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:                      # DNS, refused, timeout, TLS
        return 0, str(e)


def check_ollama() -> bool:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
    code, body = get(f"{host}/api/tags", {}, timeout=4)
    if code != 200:
        say(WARN, f"Ollama not reachable at {host} ({body or code}). Start the Ollama app or run: ollama serve")
        return False
    names = [m.get("name", "") for m in json.loads(body).get("models", [])]
    if model not in names and f"{model}:latest" not in names:
        say(WARN, f"Ollama is running but {model} is not pulled. Run: ollama pull {model}")
        return False
    say(OK, f"Ollama at {host} with {model}")
    return True


def check_anthropic() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    model = os.environ.get("DECKENGINE_NARRATIVE_MODEL", "claude-sonnet-4-6")
    ok = True
    try:
        import anthropic  # noqa: F401
    except ImportError:
        say(FAIL, "The anthropic package is not installed. Run: .venv/bin/pip install anthropic")
        ok = False
    if not key:
        say(FAIL, "ANTHROPIC_API_KEY is not set. Put it in .env (see .env.example)")
        return False
    code, body = get(f"https://api.anthropic.com/v1/models/{model}",
                     {"x-api-key": key, "anthropic-version": "2023-06-01"})
    if code == 200:
        say(OK, f"Anthropic key works, model {model}")
    elif code == 401:
        say(FAIL, "Anthropic rejected the key (401). Check ANTHROPIC_API_KEY")
        ok = False
    elif code == 404:
        say(FAIL, f"Anthropic has no model {model!r}. Check DECKENGINE_NARRATIVE_MODEL")
        ok = False
    else:
        say(WARN, f"Could not confirm the Anthropic key ({code or body}). Generation may still work")
    return ok


def check_openai_compatible() -> bool:
    base = (os.environ.get("LOCAL_LLM_BASE") or os.environ.get("OPENAI_BASE_URL", "")).rstrip("/")
    key = os.environ.get("LOCAL_LLM_KEY") or os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("LOCAL_LLM_MODEL") or os.environ.get("OPENAI_MODEL", "")
    if not base:
        say(FAIL, "OPENAI_BASE_URL is not set. Put the endpoint's base URL (ending in /v1) in .env")
        return False
    if base.endswith("/chat/completions"):
        say(FAIL, f"OPENAI_BASE_URL should end in /v1, not /chat/completions: {base}")
        return False
    if not model:
        say(FAIL, "OPENAI_MODEL is not set. Use the model name your endpoint expects")
        return False
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    code, body = get(f"{base}/models", headers)
    if code == 200:
        try:
            ids = [m.get("id") for m in json.loads(body).get("data", [])]
        except Exception:
            ids = []
        if ids and model not in ids:
            say(WARN, f"{base} answers, but does not list {model!r}. It offers: {', '.join(ids[:8])}")
        else:
            say(OK, f"OpenAI-compatible endpoint {base}, model {model}")
        return True
    if code in (401, 403):
        say(FAIL, f"{base} rejected the key ({code}). Check OPENAI_API_KEY")
        return False
    if code == 404:
        # Some gateways do not implement /models; the chat call may still work.
        say(WARN, f"{base} has no /models list, so the model could not be checked. If slides look generic, check the URL")
        return True
    say(FAIL, f"Could not reach {base}: {body or code}")
    return False


def main() -> int:
    backend = os.environ.get("DECKENGINE_NARRATIVE_BACKEND", "anthropic").strip().lower()
    if backend == "ollama":
        # Ollama missing is a warning, not a stop: it is the default, and the
        # built-in writer still produces slides without it.
        check_ollama()
        return 0
    if backend == "anthropic":
        return 0 if check_anthropic() else 1
    if backend in ("openai", "gemma"):
        return 0 if check_openai_compatible() else 1
    say(FAIL, f"Unknown DECKENGINE_NARRATIVE_BACKEND={backend!r}. Use ollama, anthropic or openai")
    return 1


if __name__ == "__main__":
    sys.exit(main())
