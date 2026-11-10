# Installing pptgpt on a work machine

pptgpt runs entirely on your own computer: a small Python server, a local
model through Ollama, and LibreOffice for exact slide previews. No account, no
cloud service, and your company's files never leave the machine.

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

Notes:

- `sentence-transformers` pulls in PyTorch (~700 MB). It improves the
  storyboard's narrative analysis; if the install is too heavy or blocked,
  remove that line from `requirements.txt` — pptgpt falls back to a simpler
  word-overlap method and says so once at start-up.
- `anthropic` is only used if you choose the Anthropic API instead of Ollama.
  It is harmless to install either way.

## 3. Ollama and the model

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

Settings you can change when starting (all optional):

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8000` | Port to serve on, e.g. `PORT=8010 scripts/start.sh` |
| `OLLAMA_MODEL` | `gemma3:4b` | Any model you have pulled |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Where Ollama listens |
| `DECKENGINE_NARRATIVE_BACKEND` | `ollama` | `anthropic` to use the Anthropic API instead (needs `ANTHROPIC_API_KEY`) |

`start.sh` always binds to **127.0.0.1**, so only this computer can open
pptgpt, and that is why it runs without a login. Do not expose it on the
network.

On Windows, without bash, start it with:

```powershell
$env:BU_AUTH_DISABLED="1"; $env:DECKENGINE_NARRATIVE_BACKEND="ollama"; $env:OLLAMA_MODEL="gemma3:4b"; $env:OLLAMA_HOST="http://127.0.0.1:11434"
.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

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
| Slides all say the same canned things | Ollama isn't answering in time — check the terminal for `[narrative] ollama backend failed` |
| "Port 8000 is in use" | `PORT=8010 scripts/start.sh` |
| No "exact" badge on previews | LibreOffice not installed or not on PATH |
| Corporate proxy blocks `pip install` | `pip install --proxy http://proxy:port -r requirements.txt`, or ask IT for a package mirror |
| Corporate proxy blocks `ollama pull` | Set `HTTPS_PROXY` before starting Ollama, or ask IT to copy the model into `~/.ollama/models` |
