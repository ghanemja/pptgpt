#!/usr/bin/env bash
# Start pptgpt on this machine.
#
#   scripts/start.sh            # http://127.0.0.1:8000/
#   PORT=8010 scripts/start.sh  # another port
#
# Binds to 127.0.0.1 ONLY. pptgpt has no login, so this is what keeps it
# private: no other computer can reach the server. Do not change the host to
# 0.0.0.0 — that would put your decks on the network for anyone to open.
#
# Checks what it needs first and says what is missing. Only Python and the
# packages are required; without Ollama slides come from the built-in
# fallback writer, without LibreOffice there are no exact previews and SVG
# icons do not export.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Settings live in .env (copy .env.example). Anything already set in the
# shell wins over .env, so `PORT=8010 scripts/start.sh` still works.
if [ -f "$ROOT/.env" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^export[[:space:]]*//')"
    case "$line" in ''|'#'*) continue ;; *=*) ;; *) continue ;; esac
    k="${line%%=*}"; v="${line#*=}"
    [[ "$k" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
    if [ -z "${!k+x}" ]; then export "$k=$v"; fi
  done < "$ROOT/.env"
fi

HOST="127.0.0.1"
PORT="${PORT:-8000}"

# No network at runtime. The semantic model loads from models/ (put there once
# by scripts/fetch_models.py); these stop the Hugging Face libraries from ever
# trying the model hub. Forced, not defaulted.
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

export DECKENGINE_NARRATIVE_BACKEND="${DECKENGINE_NARRATIVE_BACKEND:-ollama}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma3:4b}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; exit 1; }

echo "pptgpt — checking this machine"

# 1. Python: the project's virtualenv, 3.11 or newer.
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || fail "No virtualenv at .venv. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt  (see SETUP.md)"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || fail "Python 3.11+ needed; .venv has $("$PY" -V 2>&1). Recreate .venv with a newer python3."
ok "Python $("$PY" -c 'import platform; print(platform.python_version())')"

# 2. Required packages.
"$PY" -c 'import fastapi, uvicorn, pptx, multipart' 2>/dev/null \
  || fail "Packages missing. Run: .venv/bin/pip install -r requirements.txt"
ok "Python packages"

# 3. The model that writes the slides — whichever backend .env chose.
#    One free request (a model list), so a wrong key or URL shows up here
#    instead of as generic fallback slides later.
echo "  model: $DECKENGINE_NARRATIVE_BACKEND"
if [ "${SKIP_MODEL_CHECK:-0}" != "1" ]; then
  "$PY" "$ROOT/scripts/check_model.py" \
    || fail "The model is not set up (above). Fix .env (see .env.example / SETUP.md), or start anyway with SKIP_MODEL_CHECK=1"
fi

# 4. The semantic model (optional: storyboard and thread map read meaning,
#    not just shared words). Fetched once; never downloaded from here.
if [ -f "$ROOT/models/all-MiniLM-L6-v2/modules.json" ]; then
  ok "Semantic model (models/all-MiniLM-L6-v2)"
else
  warn "No semantic model — the storyboard uses word overlap. Run once: .venv/bin/python scripts/fetch_models.py"
fi

# 5. LibreOffice (optional: exact previews, template backdrops, SVG icons).
if command -v soffice >/dev/null 2>&1 \
   || [ -x /Applications/LibreOffice.app/Contents/MacOS/soffice ] \
   || [ -x /usr/bin/soffice ] || [ -x /usr/lib/libreoffice/program/soffice ]; then
  ok "LibreOffice"
else
  warn "LibreOffice not found — no exact previews, and SVG icons will not export. See SETUP.md."
fi

# 6. Port free?
if "$PY" - "$HOST" "$PORT" <<'EOF' 2>/dev/null; then :; else fail "Port $PORT is in use. Try: PORT=8010 scripts/start.sh"; fi
import socket, sys
s = socket.socket()
try:
    s.bind((sys.argv[1], int(sys.argv[2])))
finally:
    s.close()
EOF

echo
echo "  Open  http://$HOST:$PORT/"
echo "  Kits  $ROOT/kits   (guide: kits/README.md)"
echo "  Stop  Ctrl+C"
echo

exec "$PY" -m uvicorn server:app --host "$HOST" --port "$PORT"
