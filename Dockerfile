# DeckEngine backend — FastAPI + python-pptx renderer + matplotlib plots.
# Runs on HF Spaces (Docker SDK), Render, Railway, Fly, any container host.
#
# Local test:
#   docker build -t pptgpt .
#   docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY -p 7860:7860 pptgpt

FROM python:3.11-slim

# curl → healthcheck; ffmpeg → optional, plot/animation export safety.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend code + the static frontend the server mounts.
COPY server.py ./server.py
COPY deckengine/ ./deckengine/
COPY frontend/ ./frontend/

# Writable runtime dirs. HF Spaces runs the container as a non-root user, so
# the COPY'd (root-owned) /app/frontend/uploads must be world-writable for
# .pptx ingest. Harmless elsewhere (root anyway).
RUN mkdir -p /app/frontend/uploads && chmod -R 777 /app/frontend/uploads

# Port: HF Spaces routes to app_port (7860); Render/Railway inject $PORT.
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s \
  CMD curl -fsS http://localhost:${PORT:-7860}/health || exit 1

CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1
