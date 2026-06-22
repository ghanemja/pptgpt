# Deploy

DeckEngine ships as **two pieces**: a FastAPI backend on Hugging Face Spaces
(Docker SDK) and a static frontend on Netlify. They are wired by one env var
on each side.

## Topology

```
  Netlify (frontend)                 HF Space (backend)
  https://pptgpt.netlify.app  ─────► https://jang0294-pptgpt.hf.space
       │                                       │
       │ BU_API_BASE env var                   │ BU_AUTH_*, CORS_ORIGINS,
       │ → injected into config.js             │ LLM creds (see below)
       │                                       │
       └── netlify-dist/  (static)             └── Dockerfile + server.py
```

## 1. Push to GitHub (first time)

```bash
gh repo create ghanemja/pptgpt --private --source=. --push
```

## 2. Create the HF Space

1. Go to <https://huggingface.co/new-space>.
2. Owner: `jang0294`. Space name: `pptgpt`. SDK: **Docker**. Hardware: CPU basic (free).
3. Push this repo to the Space:
   ```bash
   git remote add hf https://huggingface.co/spaces/jang0294/pptgpt
   git push hf main
   ```
4. Set the Space's secrets in Settings → Variables and secrets.
   See [PORTFOLIO_ENV.md in brain-university](https://github.com/ghanemja/brain-university/blob/main/PORTFOLIO_ENV.md)
   for the shared 9 env vars to set on this Space. After creating the Space,
   paste them in Settings → Variables and secrets.

   Also set this **per-project** variable:

   | Key            | Value                                  |
   |----------------|----------------------------------------|
   | `CORS_ORIGINS` | `https://pptgpt.netlify.app`           |

## 3. Wire Netlify

1. Import the repo at <https://app.netlify.com/start>.
2. Build settings are auto-detected from `netlify.toml` (publish: `netlify-dist`,
   command: `node scripts/gen-config.mjs`).
3. Set ONE env var:

   | Key           | Value                                |
   |---------------|--------------------------------------|
   | `BU_API_BASE` | `https://jang0294-pptgpt.hf.space`   |

4. Trigger a deploy → copy the Netlify URL → if different from the URL above,
   update `CORS_ORIGINS` on the HF Space.

## 4. Verify

- `curl https://jang0294-pptgpt.hf.space/health` → `{"ok": true}`
- Open `https://pptgpt.netlify.app/workbench` → log in with the
  `BU_AUTH_USER` / `BU_AUTH_PASSWORD` from your password manager.
- Paste rough text → `Generate` → a slide renders.

## Local dev

```bash
pip install -r requirements.txt
BU_AUTH_DISABLED=1 python -m uvicorn server:app --reload --port 7860
# open http://localhost:7860/workbench
```
