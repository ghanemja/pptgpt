# Handoff — company kits (in progress)

Goal: make pptgpt ready to migrate to a work machine, where each company
brings its own **kit** — template, example decks, labelled icons/images,
style rules, writing voice — via **UI upload, "point to a folder", or by
moving files into the folder by hand**. People run it locally; Netlify is out
of scope.

Read `CLAUDE.md` first. Run the suite before and after (`python3 tests/test_*.py`,
`node tests/test_chart_intent.mjs`) — 192 tests green at this checkpoint.

## Done (committed)

**Backend — complete and tested** (`tests/test_kit.py`, 26 tests)

- `deckengine/kit.py` — the kit model. `kits/<slug>/` is the source of truth:
  `kit.json`, `profile.json`, `voice.md`, top-level `*.potx/*.pptx` (template),
  `examples/*.pptx`, `assets/{icons,images,clipart}/` + `assets/assets.csv`
  (`file,label,tags,use,license`), `learned.json`.
  - `create_kit`, `scan` (status per part, re-read from disk every call),
    `add_files` (sorts by type/name or explicit `part`; validates zips,
    profile JSON, CSV header), `import_path` (copy, or `link` → recorded in
    `kit.json` sources; never follows symlinks; skips `~$` lock files and dotfiles),
    `assets`/`search_assets` (tag hit ×2, label ×1, deterministic),
    `asset_png` (SVG → 768px PNG via LibreOffice, cached in `.cache/`),
    `asset_path` (refuses anything outside the kit/linked folders),
    `pin_templates` (content-addressed template ids), `house_brief`
    (rules + banned + learned norms + truncated voice → generation prompt),
    `resolver_for`, `preferred_layouts`.
  - New kits start with **empty** style rules (inheriting ours contradicted
    learned norms).
- `deckengine/kit_ingest.py` — `learn(slug)` measures example decks →
  `learned.json`: layouts used, points/slide, words/point, title words,
  argue-vs-label share, visual shares, fonts, type sizes; `norms`
  (p75, clamped) and `suggested_rules`. Stat values and the caption right
  after a stat are **not** counted as points.
- `org.py` — kits appear as orgs (`kit: true`) and win a slug clash with `orgs/`.
- `coach.py` — density lens uses learned norms ("denser than your own decks").
- `native.py` — learned layouts break ties (capped below one structural
  point); library images cast into the template's picture slot.
- `spec_render.py` — new `image` block type; `preview.py` threads `org`.
- `workspace_gen.py` — `house` brief appended to every feature's prompt.
- `server.py` endpoints (all done):
  `GET/POST /api/kits`, `GET /api/kits/{slug}` (scan),
  `POST /api/kits/{slug}/upload` (multipart `files`, optional form `part`),
  `POST /api/kits/{slug}/import` `{path, mode: copy|link, part}` **localhost only**,
  `POST /api/kits/{slug}/reveal` (opens folder in Finder) **localhost only**,
  `POST /api/kits/{slug}/learn`, `PUT /api/kits/{slug}/voice` `{text}`,
  `POST /api/kits/{slug}/rules` `{add: [...]}`,
  `GET /api/kits/{slug}/assets?q=`, `GET /api/kits/{slug}/asset?file=`.
  `org` accepted by `/api/workspace_generate`, `/api/preview_png`,
  `/api/render`, `/api/critique_slide`, `/api/critique_deck`.
- `kits/example-co/` — a complete working kit (built by
  `scripts/make_example_kit.py`). `.gitignore` ignores every other kit.

## Left to do

### 1. Frontend: send `org` everywhere (small, do first)
`orgSlug` lives in `ws-app.jsx` state. Pass it in:
- `frontend/workspace-backend.js` — `aiGenerate` body and `exportPptx` body
- `frontend/ws-template.jsx` — `exactUrl` payload **and** its cache signature
- `frontend/ws-coach.jsx` — `/api/critique_slide` body
- `frontend/ws-review.jsx` — `/api/critique_deck` body
Simplest: expose `window.WS_ORG = orgSlug` from `App` on each render.

### 2. Kit setup panel — new `frontend/ws-kit.jsx`
Open it from the sidebar footer (replace the fake "Jane G. / Pro workspace"
footer in `Sidebar` with the current company + "Set up kit") and from the
Organization row in Scope (`ws-phases.jsx` `ScopePhase`). Overlay like
`History` (`.history` styles). Contents:
- kit picker + "New kit" (`POST /api/kits`)
- the six parts from `scan().parts` as a checklist (✓ / missing, detail,
  problems, relative path)
- per part: **Upload** (multipart, set `part`), **Point to a folder**
  (text input + copy/link toggle → `import`), and the absolute folder path
  with **Open folder** (`reveal`) + **Rescan** (re-GET)
- **Learn from examples** → show `learned` summary + `suggested_rules` with
  checkboxes → **Add to house rules** (`POST rules`)
- voice editor (textarea → `PUT voice`)
Register the file in `scripts/build-netlify.mjs` ASSETS and
`frontend/workspace.html` (before `ws-app.jsx`).

### 3. Auto-apply the kit's template
When the selected org is a kit and `scan().templates[0].id` exists and no
template is applied, call the existing `applyTemplate` with
`GET /api/templates/{id}`.

### 4. Asset library — new `frontend/ws-library.jsx`
Topbar **Library** button, shown when the org is a kit. Search
`/api/kits/{slug}/assets?q=`, thumbnails from `/api/kits/{slug}/asset?file=`,
a "Suggested for this slide" row (query = title + bullets). Click sets the
active slide's `image = {kit, file, label}`; a "Remove image" action clears it.
Then:
- `ws-slide.jsx` `SlideCard`: when `slide.image`, text column left + image right
- `ws-export.js` `slideToSpec`: emit `{type:'image', x, y, w, h, image}`
  (server already renders it; narrow the text column to make room)

### 5. Docs + scripts
- `kits/README.md` — **the setup guide** the user asked to be very clear:
  three ways in (UI upload / point to a folder / drop files in), the folder
  layout, what each file is, formats (`.pptx` not `.ppt`; PDFs not used as
  examples), `assets.csv` columns with an example, `profile.json` fields,
  what learning measures and how suggested rules work, privacy (all local),
  troubleshooting (LibreOffice missing → no SVG icons / exact previews).
- `SETUP.md` — install on a work machine: Python 3.11+, `.venv`,
  `pip install -r requirements.txt`, Ollama + `ollama pull gemma3:4b`,
  LibreOffice, start command, env vars, how to verify, how to run tests.
- `scripts/start.sh` — checks deps, starts uvicorn on **127.0.0.1** with
  `BU_AUTH_DISABLED=1` (safe only because it is bound to localhost) and the
  Ollama backend env from `.claude/launch.json`.
- Link both from `README.md`; add `kit.py`, `kit_ingest.py`,
  `test_kit.py`, `kits/` to the Layout section of `CLAUDE.md`.

### 6. Cleanup
- `ws-app.jsx`: `Coach` and `coachContent` are dead code (never rendered).
  Delete them; `coachStage` state can go too if nothing visible reads it.
- `git stash list` → `stash@{0}` "thread graph + fast thread_map options
  (WIP)". Ask the user whether to finish or drop it.

### 7. Verify end to end, then commit + push
Start the server (`preview_start pptgpt`), and in the browser: create a kit,
upload a deck, point at a folder (copy and link), drop a file in by hand and
rescan, learn, add suggested rules, confirm the template auto-applies, put a
library icon on a slide, check the exact preview shows it in the template's
picture slot, export and open the `.pptx`. Full suite green, then commit.

## Decisions already made — don't relitigate
- The folder is the source of truth; the UI only writes into it.
- `import` and `reveal` answer to localhost only, whatever the auth settings.
- Learning is measured from the files, never inferred by a model.
- A kit wins over a built-in profile with the same slug.
- With a template, the template owns geometry (`native.py`); `layout.py`
  owns it otherwise (`CLAUDE.md`, "Templates: who owns geometry").
