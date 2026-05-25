# pptgpt — data contract

The UI is stateless. All design judgment lives behind a single async backend call.

## Single function the UI calls

```ts
function backend(req: BackendRequest): Promise<BackendResponse>;
```

Swap `mockBackend.js` for a real `fetch()` against your endpoint — same shapes, same semantics. Both `index.html` (input → questions → directions → focused) and `workbench.html` (3-panel outline + canvas + result) talk to the same function.

## Request

```ts
type BackendRequest = {
  rawContent: string;                          // user's pasted material (or outline serialized)
  mode: 'draft' | 'refine' | 'condense' | 'visualize';
  answers: Record<string, string>;             // questionId → chosen option
  outline?: OutlineSlide[];                    // OPTIONAL — structured input (workbench)
  wantsLiveDirections?: boolean;               // if true, backend returns provisional
                                               // directions even when questions remain
};

type OutlineSlide = {
  id: string;
  title: string;
  messages: string[];                          // exactly 3 by convention, N accepted
};
```

### Modes

- **`draft`** — rough notes → one styled slide.
- **`refine`** — paste what you have + what feels off → reworked single slide.
- **`condense`** — paste a full deck or upload a `.pptx` → short version. Each direction's `slides` array carries the condensed deck.
- **`visualize`** — describe a math concept → 3b1b-style explainer slide(s) containing a `plot` block. The block declares a curated function id, a curve color, and a `paramSchema` the host can render as sliders.

## File inputs (Story Map phase)

The Story Map's file uploader accepts these formats — all parsed in the browser, no server round-trip:

| Format | How it's parsed | Notes |
|---|---|---|
| `.pdf`     | pdf.js, text layer only | Scanned/image PDFs need OCR — not supported. |
| `.docx`    | JSZip → `word/document.xml` | Reads every `w:p` paragraph as a line. |
| `.pptx`    | JSZip → `ppt/slides/slide*.xml` | Each slide becomes a `---`-separated chunk; titles vs bullets detected via the `p:ph` placeholder type. |
| `.txt`, `.md`, `.rtf`, `.csv` | read as text | |

Libraries (`pdf.js`, `JSZip`) are lazy-loaded only when the user actually picks a file of that type. The page boots without them.

The parser feeds the extracted text into `extractStoryboard({ text, mode })` — the same entry point as paste-text — so the contract below is unchanged.

`answers` is `{}` on the first call. The UI re-calls with accumulated answers as the user picks.

If `wantsLiveDirections` is true (the workbench passes this), `directions` is populated as soon as possible — the backend fills unanswered questions with sensible defaults so the right panel always has something to render.

## Response

```ts
type BackendResponse = {
  slideIR:    SlideSpec;                       // "rough" preview shown while questions pend
  questions:  Question[];                      // empty when there are no more taste questions
  directions: Direction[];                     // empty until backend commits (unless wantsLiveDirections)
};

type Question = {
  id:      string;                             // stable id, used as answers key
  region:  'top' | 'bottom' | 'left' | 'right';// anchors card + drives exit drift direction
  text:    string;
  options: string[];
};

type Direction = {
  key:         string;
  label:       string;
  blurb?:      string;
  previewSpec: SlideSpec;                      // the lead/hero slide (always present)
  slides?:     SlideSpec[];                    // OPTIONAL — multi-slide deck (slides[0] === previewSpec)
};
```

## SlideSpec

The opaque slide description. The UI renders it verbatim — it does not invent layout, palette, sizes, or geometry.

```ts
type SlideSpec = {
  canvasW: number;                             // design coordinate space (e.g. 1280)
  canvasH: number;                             // e.g. 720
  palette: { bg: string; ink: string; accent?: string; muted?: string };
  blocks:  Block[];
};

type Block =
  | TextBlock
  | RectBlock
  | BulletsBlock
  | RuleBlock
  | TagBlock
  | PlotBlock;

type BoxBase = {
  x: number; y: number; w: number; h: number;  // canvas coords
};

type TextBlock = BoxBase & {
  type: 'text';
  text: string;
  font?: 'sans' | 'serif' | 'mono';
  size: number;
  weight?: 400 | 500 | 600 | 700;
  italic?: boolean;
  lineHeight?: number;
  color: string;
  align?: 'left' | 'center' | 'right';
  letterSpacing?: number;                      // em
  transform?: 'uppercase' | 'none';
};

type RectBlock = BoxBase & {
  type: 'rect';
  fill: string;
  radius?: number;
};

type BulletsBlock = BoxBase & {
  type: 'bullets';
  items: string[];
  size: number;
  font?: 'sans' | 'serif' | 'mono';
  weight?: 400 | 500 | 600;
  lineHeight?: number;
  color: string;
  marker?: 'dot' | 'dash' | 'number' | 'none';
  markerColor?: string;
  gap?: number;
};

type RuleBlock = BoxBase & {
  type: 'rule';
  color: string;
  thickness?: number;
};

type TagBlock = BoxBase & {
  type: 'tag';
  text: string;
  fill: string;
  color: string;
  size?: number;
};

type PlotBlock = BoxBase & {
  type: 'plot';
  bg?: string;
  curves: Array<{
    fn:      CurveFn;                          // function id — see below
    params:  Record<string, number>;           // defaults for the curve
    color:   string;
    width?:  number;
    dash?:   string;
  }>;
  xRange: [number, number];                    // data coords
  yRange: [number, number];
  paramSchema?: Array<{                        // tunable params — UI renders sliders
    name:    string;                           // matches a key in curves[i].params
    label:   string;
    default: number;
    min:     number;
    max:     number;
    step:    number;
  }>;
  showGrid?:        boolean;
  showAxes?:        boolean;
  showTickLabels?:  boolean;
  axisColor?:       string;
  gridColor?:       string;
  tickColor?:       string;
  tickLabelColor?:  string;
  xTicks?:          number[];
  yTicks?:          number[];
  xLabel?:          string;
  yLabel?:          string;
  paddingLeft?:     number;
  paddingRight?:    number;
  paddingTop?:      number;
  paddingBottom?:   number;
};

// CurveFn ids — every entry maps to a real function in previewRenderer.jsx.
// The UI never invents formulas; backends pick from this list.
type CurveFn =
  | 'sine'        // p.A * sin(p.omega * x + p.phi)
  | 'cosine'      // p.A * cos(p.omega * x + p.phi)
  | 'damped'      // p.A * exp(-p.gamma * x) * cos(p.omega * x)
  | 'gaussian'    // p.A * exp(-((x - p.mu) / p.sigma)^2 / 2)
  | 'exponential' // p.A * exp(p.k * x)
  | 'polynomial'  // p.a*x^3 + p.b*x^2 + p.c*x + p.d
  | 'sigmoid';    // p.A / (1 + exp(-p.k * (x - p.x0)))
```

## Invariants

1. The UI never picks colors, fonts, or sizes for slide content. Every visual property is on the SlideSpec.
2. `region` drives BOTH the card's anchor and its exit drift direction.
3. The UI keeps `mode`, `answers`, and the latest response; everything else is the backend's problem.
4. If a Direction has `slides`, `slides[0]` MUST equal `previewSpec` so the UI can use `previewSpec` as the lead thumbnail without re-deriving.
5. Plot blocks declare which curve function to evaluate via `curves[i].fn` — UI hosts evaluate only the curated set in `CurveFn`. New formulas require a new entry in `previewRenderer.jsx::PLOT_FNS`.
6. `paramSchema` is optional. When present, hosts may render sliders and pass override values as `<SlidePreview plotParams={{...}}>`. The renderer merges them onto each curve's defaults at draw time.

## Host-only helpers

`previewRenderer.jsx` exposes:

```ts
extractPlotParamSchema(spec: SlideSpec): PlotParam[];
```

Returns the union of all `paramSchema` entries across every plot block in a spec, de-duplicated by `name`. The workbench uses it to render its slider stack next to the result preview.
