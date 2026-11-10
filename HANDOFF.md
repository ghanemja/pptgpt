# Handoff — company kits

Goal: make pptgpt ready to migrate to a work machine, where each company
brings its own **kit** — template, example decks, labelled icons/images,
style rules, writing voice — via **UI upload, "point to a folder", or by
moving files into the folder by hand**. People run it locally; Netlify is out
of scope.

Read `CLAUDE.md` first. Run the suite before and after (`python3 tests/test_*.py`,
`node tests/test_chart_intent.mjs`) — 194 tests green.

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

## Done in the follow-up (frontend, docs, scripts)

1. Every API call sends `org` (`window.WS_ORG`, set by `App` each render):
   generation, export, exact preview (and its cache signature), coach, review.
2. `frontend/ws-kit.jsx` — kit setup panel, opened from the sidebar footer
   (company name) and Scope → "Set up a kit / Edit kit". Create a kit; the
   six parts as a checklist; per part Upload / Point to a folder (copy or
   link) ; Open folder + Rescan; Learn from examples with suggested rules to
   tick into profile.json; voice editor. `scan()` now also returns `rules`
   and `voice_text` for it.
3. A kit's template applies itself when its company is picked (marked
   `template.fromKit`); switching company swaps or removes only a template a
   kit applied, never one the user chose in Visuals.
4. `frontend/ws-library.jsx` — topbar **Library** for kit orgs: search,
   "Suggested for this slide", pick / remove. `slide.image` shows in the HTML
   preview (right column) and the plain export (`image` block); with a
   template the engine casts it into the picture placeholder. A linked asset
   folder is labelled by its own `assets.csv`.
5. `kits/README.md` (setup guide), `SETUP.md` (work-machine install),
   `scripts/start.sh` (checks deps, 127.0.0.1 only, auth off). README.md and
   CLAUDE.md link them.
6. Dead `Coach` / `coachContent` / `coachStage` removed from `ws-app.jsx`.

Bugs found and fixed on the way:
- The workspace never called the engine: `ws-slide.jsx` re-assigned
  `window.aiGenerate` after `workspace-backend.js` had wrapped it. The
  wrapper now waits for the client generator, and `ws-app.jsx` reads
  `window.aiGenerate` at call time.
- "Build the storyboard" produced one flow diagram: the brief's narrative
  arc ("Situation → Complication → …") tripped the diagram detector.
  Condense no longer goes through visual-intent detection.
- Ollama's default host is now `127.0.0.1` — `localhost` resolved to `::1`
  first and the 1.5s reachability probe timed out.

## Open

- `gemma3:4b` answers the condense prompt with ONE slide object, not a
  list, and `workspace_gen` rejects that by design
  (`test_condense_non_list_response_returns_none`), so Scope → storyboard
  falls back to the canned writer with that model. Either accept a single
  object as a one-slide spine, or tighten the condense prompt.
- Under the project `.venv` (which has sentence-transformers) three
  `tests/test_threadmap.py` tests fail — they assume the word-overlap path.
  Pre-existing at 7db7e84; the suite is green under a Python without it.

## Thread graph (was `stash@{0}`, finished)

Story has two tabs: **Board** and **Threads**. `frontend/ws-thread.jsx`
draws `threadmap.py`'s graph — beats in order, links arced above, orphans
dashed, hard cuts marked. It reads twice: `engine: 'fast'` (embeddings or
shared words, paints at once), then the model in the background, which
replaces it only if it says something. Both ask `sides: 'before'`, so
nothing pays for the simulated "after" side. Fixed on the way: orphan
reasons are a dict (never shown before), and edge widths are normalised
per deck (counts drew 25px strokes).

## Decisions already made — don't relitigate
- The folder is the source of truth; the UI only writes into it.
- `import` and `reveal` answer to localhost only, whatever the auth settings.
- Learning is measured from the files, never inferred by a model.
- A kit wins over a built-in profile with the same slug.
- With a template, the template owns geometry (`native.py`); `layout.py`
  owns it otherwise (`CLAUDE.md`, "Templates: who owns geometry").

## Slide voice (humanplease)

`deckengine/humanplease_slides.md` (derived from humanplease @ 7f7f2d0,
vendored in `deckengine/vendor/humanplease/` by `scripts/sync_humanplease.py`)
rides on every workspace_gen prompt, refine included (refine was also missing
the house style; fixed). `scripts/eval_voice.py` A/Bs it. First run on
gemma3:4b, 8 briefs × 2: banned phrases 7→0, invented numbers 3→0, but
bullets per slide 3.4→1.6 (real points dropped) and invented owner names on
the postmortem brief unchanged (the `standup` tone asks for owners).
Open, needs the owner's call: loosening the `"bullets":["","",""]` template.

