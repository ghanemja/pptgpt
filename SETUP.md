# Installing pptgpt on a work machine

pptgpt runs entirely on your own computer: a small Python server, a local
model through Ollama, and LibreOffice for exact slide previews. No account, no
cloud service, and your company's files never leave the machine.

**Once installed, pptgpt makes no network calls while it runs, except to
Ollama on 127.0.0.1.** The browser libraries and fonts ship in
`frontend/vendor/`, the semantic model is downloaded once in step 2, and no
cloud model is ever used unless you name one in `.env` (see
[Use your own model](#use-your-own-model)). Downloads happen only during
setup: `pip install`, `scripts/fetch_models.py` and `ollama pull`.

Time: about 20 minutes, most of it downloads.

| You need | Why | Required? |
|---|---|---|
| Python 3.11 or newer | runs the server | **yes** |
| The Python packages in `requirements.txt` | the engine | **yes** |
| [Ollama](https://ollama.com) + the `gemma3:4b` model (~3.3 GB) | writes the slides | strongly recommended — without it slides come from a simple built-in writer |
| [LibreOffice](https://www.libreoffice.org) | exact previews, template backdrops, SVG icons in exports | recommended |
| git | to fetch the code | or download a zip |

If your company manages software installs, ask IT for Python, Ollama and
LibreOffice — all three are free and widely used.

---

## 1. Get the code

```bash
git clone <your pptgpt repository URL> pptgpt
cd pptgpt
```

(Or download the repository as a zip and unzip it; then `cd` into the folder.)

## 2. Python and the packages

Check the version first — it must say 3.11 or higher:

```bash
python3 --version
```

macOS: if it is older, install Python from python.org or with
`brew install python@3.12`. Windows: install from python.org and tick
**Add python.exe to PATH**.

Create a virtual environment inside the project and install the packages:

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

On Windows (PowerShell) the same two steps are:

```powershell
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Then download the semantic model, once (about 90 MB, into `models/`):

```bash
.venv/bin/python scripts/fetch_models.py
```

It ends with `OK: loads offline from models/all-MiniLM-L6-v2`. pptgpt loads
it from that folder and never downloads it while running. On a machine with
no internet, run this on one that has it and copy the `models/` folder over.

Notes:

- `sentence-transformers` pulls in PyTorch (~700 MB). It improves the
  storyboard's narrative analysis; if the install is too heavy or blocked,
  remove that line from `requirements.txt` and skip `fetch_models.py` —
  pptgpt falls back to a simpler word-overlap method and says so once in
  the terminal.
- `anthropic` is only used if you choose the Anthropic API instead of Ollama.
  It is harmless to install either way.

## 3. Ollama and the model

(Using Claude, OpenAI, your company's AI gateway or another server
instead? Skip this step and see **[Use your own model](#use-your-own-model)**.)

1. Install Ollama from <https://ollama.com/download> (macOS / Windows app), or
   on macOS `brew install ollama`.
2. Start it — open the Ollama app, or run `ollama serve` in a terminal.
3. Download the model once:

```bash
ollama pull gemma3:4b
```

4. Check it answers:

```bash
curl http://127.0.0.1:11434/api/tags
```

You should see `gemma3:4b` in the list. A machine with 16 GB of RAM runs it
comfortably; a slide takes a few seconds to a minute.

## 4. LibreOffice

- macOS: install from <https://www.libreoffice.org/download/> (it goes to
  `/Applications/LibreOffice.app`; pptgpt finds it there), or
  `brew install --cask libreoffice`.
- Windows: install from the same page, then make sure `soffice` is on PATH
  (usually `C:\Program Files\LibreOffice\program`).
- Linux: `sudo apt install libreoffice` (or your distribution's package).

Without LibreOffice everything still works, but previews are an HTML
approximation, the template's backdrop isn't drawn on screen, and SVG icons
are skipped in exported slides (use PNG icons instead).

## 5. Start it

```bash
scripts/start.sh
```

It checks each of the above, tells you what is missing, and starts the server.
Then open:

**<http://127.0.0.1:8000/workspace>**

Leave the terminal open while you work; **Ctrl+C** stops pptgpt.

Settings go in a file called `.env` in the pptgpt folder. `start.sh` reads
it every time it starts; a value set in the terminal wins over the file, so
`PORT=8010 scripts/start.sh` still works. With no `.env`, pptgpt uses Ollama
with `gemma3:4b` on port 8000. Which model writes the slides is covered in
the next section.

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8000` | Port to serve on |
| `DECKENGINE_NARRATIVE_BACKEND` | `ollama` | Which model writes the slides: `ollama`, `anthropic` or `openai` |
| `DECKENGINE_VOICE` | picked by model | Slide-voice rules sent with each prompt: `full`, `short` (the default for local models of 12B or less) or `off` |
| `SKIP_MODEL_CHECK` | unset | `1` starts even when the model check fails |

`start.sh` always binds to **127.0.0.1**, so only this computer can open
pptgpt, and that is why it runs without a login. Do not expose it on the
network.

On Windows, without bash, start it with:

```powershell
$env:DECKENGINE_NARRATIVE_BACKEND="ollama"; $env:OLLAMA_MODEL="gemma3:4b"; $env:OLLAMA_HOST="http://127.0.0.1:11434"
.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

(For Anthropic or an OpenAI-compatible endpoint, set that option's variables
the same way, `$env:NAME="value"`, instead of the Ollama ones. Windows does
not read `.env` on its own.)

## Use your own model

pptgpt can draft slides with any of three kinds of model. Pick one, then:

1. Copy the example settings file:

```bash
cp .env.example .env
```

2. Open `.env` in a text editor, comment out the Ollama block, uncomment
   the block you want and fill it in (the three options are described
   below).
3. Run `scripts/start.sh`. It makes one free request to the model, a list
   of models with no generation, and shows a ✓, or says exactly what is
   wrong (bad key, wrong URL, model name not offered) and stops.

`.env` is git-ignored, so your key stays on this machine. Keep it out of
email and chat like any password.

### Option A: Ollama, a local model (the default)

No key, nothing leaves the machine. Set up in step 3 above.

```dotenv
DECKENGINE_NARRATIVE_BACKEND=ollama
OLLAMA_MODEL=gemma3:4b
OLLAMA_HOST=http://127.0.0.1:11434
```

`OLLAMA_MODEL` can be any model you have pulled (`ollama list` shows them).

### Option B: Anthropic (Claude)

Install the Anthropic package once:

```bash
.venv/bin/pip install anthropic
```

Then in `.env`:

```dotenv
DECKENGINE_NARRATIVE_BACKEND=anthropic
ANTHROPIC_API_KEY=sk-ant-...
DECKENGINE_NARRATIVE_MODEL=claude-sonnet-4-6
```

Get a key at <https://console.anthropic.com> → API keys.
`DECKENGINE_NARRATIVE_MODEL` is any model id your key can use.

### Option C: any OpenAI-compatible endpoint

This covers OpenAI itself and anything that speaks the same API: a company
AI gateway, LM Studio, vLLM, llama.cpp's server. If its documentation mentions `/v1/chat/completions`, it works.

```dotenv
DECKENGINE_NARRATIVE_BACKEND=openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

| You use | `OPENAI_BASE_URL` | `OPENAI_API_KEY` | `OPENAI_MODEL` |
|---|---|---|---|
| OpenAI | `https://api.openai.com/v1` | your key | e.g. `gpt-4o-mini` |
| LM Studio | `http://127.0.0.1:1234/v1` | anything, e.g. `lm-studio` | the model's name in LM Studio |
| vLLM / llama.cpp | `http://127.0.0.1:8000/v1` (start pptgpt with `PORT=8010`) | whatever you set, or anything | the served model name |
| Company gateway | the URL IT gives you, ending in `/v1` | the key IT gives you | the name IT gives you |

The base URL ends in `/v1`. Do not add `/chat/completions`; pptgpt adds it.
If the endpoint lists its models, `start.sh` tells you which names it
accepts when yours is wrong.

Not supported yet: **Azure OpenAI**, whose URLs carry a deployment name and
an `api-version`. Use your company gateway if it fronts Azure with a plain
`/v1` URL.

The older names `DECKENGINE_NARRATIVE_BACKEND=gemma` with `LOCAL_LLM_BASE`,
`LOCAL_LLM_KEY` and `LOCAL_LLM_MODEL` still work and mean the same thing.

### When the model fails

If a call fails (key revoked, endpoint down, timeout), the server tries
Ollama on this machine, if it is running and was not already the one that
failed. It never falls back to a cloud model: Anthropic or an
OpenAI-compatible endpoint is only used when `DECKENGINE_NARRATIVE_BACKEND`
names it, so an `ANTHROPIC_API_KEY` sitting in your environment does nothing
on its own. If nothing answers, the browser falls back to a simple built-in
writer, and slides come out generic. The terminal shows
`[narrative] … backend failed` when that happens; re-run
`.venv/bin/python scripts/check_model.py` to see why.

## 6. Set up your company

Follow **[kits/README.md](kits/README.md)**. In short: in pptgpt, click the
company name at the bottom of the sidebar → **New kit** → add your template,
some example decks and icons → **Learn from examples**.

To bring kits from another machine, copy the `kits/<company>/` folders into
this machine's `kits/` folder (they are not in git). Any linked folders must
exist at the same path, or be pointed to again.

## 7. Check it works

1. `scripts/start.sh` shows ✓ for Python, packages, Ollama and LibreOffice.
2. Open <http://127.0.0.1:8000/workspace>. In **Scope → Organization** choose
   **Example Co** (the bundled example kit).
3. Its template applies by itself ("Applied the example-co-template
   template").
4. Press **Demo fill**, then **Build the storyboard**. Open **Deck**; the slide
   preview carries an **exact** badge once LibreOffice has rendered it.
5. **Export → PowerPoint** downloads a `.pptx` that opens in PowerPoint.

## 8. Run the tests (optional)

```bash
for f in tests/test_*.py; do .venv/bin/python "$f" | tail -1; done
```

```bash
node tests/test_chart_intent.mjs
```

Every line should end in `N/N passed`. The JavaScript test needs Node 18+.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `start.sh: Permission denied` | `chmod +x scripts/start.sh` |
| "Ollama not reachable" | Open the Ollama app or run `ollama serve`; check `curl http://127.0.0.1:11434/api/tags` |
| `[narrative] anthropic backend failed … No module named 'anthropic'` after an Ollama timeout | With `ANTHROPIC_API_KEY` set, a failed Ollama call falls back to Anthropic, which needs the SDK. `requirements.txt` lists it, but a venv built before that (or with the line removed) lacks it: `.venv/bin/pip install anthropic`, or unset `ANTHROPIC_API_KEY` to stay fully local. Frequent Ollama timeouts themselves usually mean the machine is busy or the model is too big for it |
| Slides all say the same canned things | The model isn't answering. Check the terminal for `[narrative] … backend failed`, and run `.venv/bin/python scripts/check_model.py` |
| `start.sh` stops at the model check | Read the ✗ line: it names the setting to fix in `.env`. See [Use your own model](#use-your-own-model) |
| "Port 8000 is in use" | `PORT=8010 scripts/start.sh` |
| No "exact" badge on previews | LibreOffice not installed or not on PATH |
| Corporate proxy blocks `pip install` | `pip install --proxy http://proxy:port -r requirements.txt`, or ask IT for a package mirror |
| `[semantics] model unavailable, falling back to lexical` | The semantic model is not in `models/`. Run `.venv/bin/python scripts/fetch_models.py` once (optional; everything works without it) |
| Corporate proxy blocks `ollama pull` | Set `HTTPS_PROXY` before starting Ollama, or ask IT to copy the model into `~/.ollama/models` |
