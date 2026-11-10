# Company kits — setup guide

A **kit** teaches pptgpt how one company presents: its PowerPoint template,
decks it is proud of, its icons and images, its house rules and the way it
writes. Pick the company in **Scope → Organization** and every deck you build
uses its kit.

Everything stays on your machine. A kit is an ordinary folder,
`kits/<company>/`, inside the pptgpt folder. Nothing is uploaded anywhere, and
kits are never committed to git (only this guide and `example-co/` are).

> **Quickest start:** open pptgpt, click the company name at the bottom of the
> left sidebar (or **Set up a kit** in Scope), press **New kit**, type the
> company name. Then work down the checklist on that screen. The rest of this
> guide explains each step and the folder behind it.

---

## 1. The three ways to add things

All three put files in the same folder, so mix them freely.

| Way | Where | Best for |
|---|---|---|
| **Upload** | Kit screen → a part's **Upload** button | A handful of files from your Downloads |
| **Point to a folder** | Kit screen → a part's **Point to a folder** | A shared drive or a big folder of decks |
| **Drop files in by hand** | Kit screen → **Open folder**, then drag files in Finder / Explorer, then **Rescan** | Anything — the folder is the source of truth |

### Upload

Press **Upload** on the part you are filling (Template, Example decks, Icons &
images, …), choose files. pptgpt checks each one and puts it in the right
sub-folder. Files it cannot use are listed with the reason, never silently
kept.

### Point to a folder

Press **Point to a folder**, paste the folder's full path — for example
`/Users/you/Library/CloudStorage/OneDrive-Acme/Decks` or
`C:\Users\you\Documents\Decks` — and choose:

- **Copy into the kit** — copies every file of the right type (sub-folders
  included). The kit then works on its own, even if the original moves.
- **Link in place** — copies nothing. The kit remembers the folder and reads
  it every time. Use this for a large library someone else keeps up to date.
  Only **Example decks** and **Icons & images** can be linked.

Tip: on a Mac, drag a folder into Terminal to see its full path; on Windows,
Shift + right-click the folder → **Copy as path**.

Pointing at a folder only works when pptgpt is running on the same machine as
the browser (it refuses requests from anywhere else).

### Drop files in by hand

Press **Open folder** — the kit's folder opens in Finder / Explorer. Copy files
into the right sub-folder (see the layout below), come back and press
**Rescan**. The checklist re-reads the folder every time it opens, so there is
no import step.

---

## 2. The folder layout

```
kits/
└── acme/                      ← one folder per company (lower-case, dashes)
    ├── kit.json               ← name, description, linked folders (written for you)
    ├── profile.json           ← scoping questions, narrative arc, house rules
    ├── voice.md               ← how the company writes, in plain sentences
    ├── Acme-Template.potx     ← the PowerPoint template (top level of the kit)
    ├── examples/              ← finished decks to learn from
    │   ├── 2025-board-q3.pptx
    │   └── customer-pitch.pptx
    ├── assets/
    │   ├── assets.csv         ← labels and tags for the files below
    │   ├── icons/             ← .svg or .png icons
    │   ├── images/            ← photos, screenshots
    │   └── clipart/           ← illustrations
    └── learned.json           ← written by "Learn from examples" — don't edit
```

`kits/example-co/` is a complete working kit. Open it to see every file
filled in, or copy it as a starting point.

### What each part is, and which files it takes

| Part | File(s) | Accepted formats | Notes |
|---|---|---|---|
| **Profile & style rules** | `profile.json` | `.json` | Created for you. Edit to change the Scope questions and house rules. |
| **PowerPoint template** | any `*.potx` / `*.pptx` at the **top level** | `.potx`, `.pptx` | Slides are cast into the template's own layouts, so fonts, colours, logo and backdrop come from it. If you have several, the first (alphabetically) is used. |
| **Example decks** | `examples/*.pptx` (sub-folders fine) | `.pptx` only | **Not** `.ppt` (open in PowerPoint and *Save As* `.pptx`) and **not** PDF — a PDF has no slide structure to measure. |
| **Icons & images** | `assets/icons/`, `assets/images/`, `assets/clipart/` | `.svg`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` | SVG icons are turned into PNGs for PowerPoint (needs LibreOffice). |
| **Asset labels** | `assets/assets.csv` | `.csv` | Optional but strongly recommended — see below. |
| **Writing voice** | `voice.md` | `.md`, `.txt` | Plain sentences. Also editable on the kit screen. |
| **Learned from examples** | `learned.json` | — | Written by pptgpt. Run learning again instead of editing it. |

How uploads are sorted when you drop a mixed batch on the kit:

- `.potx` → template. `.pptx` whose name contains *template*, *master*,
  *theme* or *brand* → template. Any other `.pptx` → example deck.
- Images → `assets/icons/` if `.svg`, otherwise `assets/images/`.
- `assets.csv` → `assets/assets.csv` (merged with the existing one, not replaced).
- `profile.json` → checked, then replaces the profile.
- `voice*.md` / `style*.md` / `writing*.md` → `voice.md`.
- Anything else is refused and listed. When pointing at a folder, Office lock
  files (`~$…`), hidden files and hidden folders are skipped.

Limits: 60 MB per file, 2,000 files per "point to a folder" run.

---

## 3. `assets.csv` — labelling icons and images

The library search, and the "Suggested for this slide" row, find pictures by
**label** and **tags**. A file with no row still shows up, labelled from its
file name and marked *unlabelled*.

Columns (the header row is required, in this order):

| Column | Meaning | Example |
|---|---|---|
| `file` | Path relative to `assets/` | `icons/growth.svg` |
| `label` | Short human name | `Growth` |
| `tags` | Words people would search for, separated by `;` | `growth;revenue;up;increase` |
| `use` | When to use it (shown on hover) | `Results that went up` |
| `license` | Where it came from / who may use it | `Brand team, internal use` |

```csv
file,label,tags,use,license
icons/growth.svg,Growth,growth;revenue;up;increase;trend,Results that went up,Brand team
icons/team.svg,Team,team;people;hiring;customers;staff,Anything about people,Brand team
images/hq-lobby.jpg,Headquarters,office;hq;building;company,About us slides,Photo by Comms
```

Tips:

- A **tag** match counts twice as much as a label match, so put the words
  people actually say ("revenue", "hiring") in tags.
- A linked asset folder can carry its **own** `assets.csv` at its top level,
  with paths relative to that folder. Rows in the kit's CSV also match by file
  name.
- Edit the CSV in Excel or Numbers, but save as **CSV UTF-8**.

To use a picture: pick the company in Scope, open a text slide, press
**Library** in the top bar, click a picture. **Remove image** takes it off.
With a template the picture goes into the template's own picture placeholder;
without one it sits to the right of the text.

---

## 4. `profile.json` — questions, story arc, house rules

```json
{
  "name": "Acme",
  "tagline": "One line shown next to the name in Scope.",
  "scope_questions": [
    { "id": "audience", "prompt": "Who is in the room?", "kind": "choice",
      "options": ["Exec", "Customer", "Conference", "Standup"], "required": true,
      "why": "Sets the tone." },
    { "id": "decision", "prompt": "What should they decide?", "kind": "text",
      "placeholder": "Approve the Q1 hire plan", "required": true }
  ],
  "narrative": {
    "guide": "Situation → Complication → Question → Answer",
    "beats": ["Situation", "Complication", "Question", "Answer", "Ask"],
    "bumper_rule": "Every slide ends in one sentence that sets up the next.",
    "messages_per_slide": 3
  },
  "style": {
    "theme": "bolt",
    "palette": "warm",
    "rules": ["Lead with the conclusion; the title is the claim."],
    "banned": ["3-D charts"]
  }
}
```

- `kind` is `text`, `longtext` or `choice` (a `choice` needs `options`).
- `style.rules` are sent to the model with every generation (the first 8),
  `style.banned` as "Never: …" lines (the first 6). Keep them short and
  specific.
- `theme` is one of `bolt`, `atlas`, `signal`, `ember`, `vivid`; `palette` one
  of `warm`, `bold`, `clean`. A template overrides both.
- Never put coordinates or sizes in a profile — pptgpt refuses one that does.
  Layout is the engine's job.

If `profile.json` is broken, the kit screen says why and the default
questions are used until it is fixed.

---

## 5. `voice.md` — how the company writes

A few plain sentences. Short and specific beats a pasted brand book — the
local model follows five concrete rules far better than five pages.

```markdown
- Say "customers", never "users".
- Every number carries a unit, a comparison and a date.
- Titles state the conclusion. No questions as titles.
- No exclamation marks.
```

The first ~1,500 characters are added to every generation prompt. Edit it on
the kit screen (**Save voice**) or in any text editor.

---

## 6. Learn from examples

Press **Learn from examples** once you have example decks (5–20 good ones is
plenty). pptgpt opens every deck and **counts** — nothing is guessed by a
model:

- points per slide and words per point (a big number and its caption are
  not counted as bullet points)
- title length, and how often a title states a claim rather than a topic
- how often slides use charts, pictures, tables, or text only
- which of the template's layouts the decks use most
- fonts and type sizes

It writes the results to `learned.json` and offers **suggested house rules**
such as "At most 4 points per slide." Tick the ones that are true for your
company and press **Add to house rules** — they are appended to
`profile.json`. Nothing becomes a rule until you tick it.

What the measurements change, even without adding rules:

- The **coach** judges density against your own decks ("denser than your own
  decks") instead of a generic limit.
- **Generation** is told your norms (bullets per slide, words per bullet,
  title length).
- With a template, the layouts your decks use most win ties when a slide
  could fit more than one layout.

When you add or change example decks the checklist shows **out of date** —
press **Learn again**.

---

## 7. Privacy

- Kits live only in `kits/` on this machine and are git-ignored.
- Generation runs on the local model (Ollama) when pptgpt is set up as in
  `SETUP.md`; nothing leaves the machine.
- "Point to a folder" and "Open folder" only answer to requests from this
  machine (`127.0.0.1`), whatever else is configured.
- Linked folders are read, never written. Symlinks are never followed.

---

## 8. Troubleshooting

| What you see | Why | Fix |
|---|---|---|
| SVG icons show in the library but not in exported slides | LibreOffice is not installed (it turns SVG into PNG) | Install LibreOffice (see `SETUP.md`), or use `.png` icons |
| No "exact" preview badge; template backdrop missing | LibreOffice not installed | Same — previews fall back to the HTML approximation |
| Template part shows a problem | The file is not a valid `.pptx`/`.potx`, or is password-protected | Re-save it from PowerPoint without a password |
| A deck is listed under "could not be read" after learning | Corrupt, password-protected or really a `.ppt` renamed | Open and *Save As* `.pptx` |
| "only available on this machine (localhost)" | You opened pptgpt from another computer | Use the browser on the machine running pptgpt, or copy files in by hand |
| "that folder is already inside kits/" | You pointed a kit at itself | Point at the original folder instead |
| A file you dropped in doesn't appear | Wrong sub-folder, or wrong format | Check the layout above, then **Rescan** |
| The company isn't in the Scope list | The folder name has capitals or spaces, or `profile.json` is missing or invalid (the kit screen says why) | Name the folder with lower-case letters, digits and dashes, e.g. `acme-corp`; fix or re-upload `profile.json` |

A kit with the same folder name as a built-in profile in `orgs/` replaces it.
