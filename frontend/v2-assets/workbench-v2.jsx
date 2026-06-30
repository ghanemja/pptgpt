/* ============================================================
   workbench.jsx — three-panel workbench for pptgpt
   ------------------------------------------------------------
   LEFT   · outline editor (slides + 3 messages each)
   CENTER · question canvas (taste questions drift)
   RIGHT  · live result preview + plot sliders for visualize mode
   ============================================================ */

const { useState, useEffect, useRef, useLayoutEffect, useMemo, useCallback } = React;
const { SlidePreview, extractPlotParamSchema } = window;

const WB_DESIGN_W = 1360;
const WB_DESIGN_H = 780;
const WB_SLIDE_W  = 720;
const WB_SLIDE_H  = 405;

const MODE_LABELS = {
  draft:      'Draft',
  refine:     'Refine',
  condense:   'Condense',
  visualize:  'Visualize',
  synthesize: 'Synthesize',
};

const MODE_DESCRIPTIONS = {
  draft:      { verb: 'Draft it',     sub: 'one polished slide for whoever\u2019s in the room' },
  refine:     { verb: 'Refine it',    sub: 'rework what\u2019s here without losing the bones' },
  condense:   { verb: 'Condense it',  sub: 'compress a long deck into 3\u20135 slides' },
  visualize:  { verb: 'Visualize it', sub: '3blue1brown plot with tunable parameters' },
  synthesize: { verb: 'Synthesize',   sub: 'paste data tables \u2192 deck with real bar / line charts' },
};

const AUDIENCES = [
  { key: 'exec',      label: 'Exec review',        sub: 'spare, numbers-forward' },
  { key: 'customer',  label: 'Customer update',    sub: 'narrative-first, more visual' },
  { key: 'conference',label: 'Conference talk',    sub: 'big visuals, takeaway-first' },
  { key: 'status',    label: 'Status / standup',   sub: 'dense, action items' },
  { key: 'oneonone',  label: '1:1 tag-up',         sub: 'conversational, low polish' },
  { key: 'technical', label: 'Technical deep-dive',sub: 'formulas, plots, citations' },
];

// ── SVG icons for the storymap pickers ─────────────────────────
// Each icon is a tiny visual cue so the user can intuit the path
// without reading. Kept monochrome (currentColor) so they pick up
// the card's text color and adapt to active state.
const GOAL_ICONS = {
  draft: (
    <svg viewBox="0 0 48 32" fill="none" aria-hidden="true">
      <rect x="6" y="4" width="36" height="24" rx="2" stroke="currentColor" strokeWidth="1.4"/>
      <line x1="11" y1="10" x2="29" y2="10" stroke="currentColor" strokeWidth="1.4"/>
      <line x1="11" y1="15" x2="34" y2="15" stroke="currentColor" strokeWidth="1.4" opacity="0.55"/>
      <line x1="11" y1="20" x2="24" y2="20" stroke="currentColor" strokeWidth="1.4" opacity="0.55"/>
    </svg>
  ),
  refine: (
    <svg viewBox="0 0 48 32" fill="none" aria-hidden="true">
      <rect x="6" y="4" width="36" height="24" rx="2" stroke="currentColor" strokeWidth="1.4" strokeDasharray="3 2"/>
      <line x1="11" y1="10" x2="22" y2="10" stroke="currentColor" strokeWidth="1.4"/>
      <line x1="11" y1="15" x2="26" y2="15" stroke="currentColor" strokeWidth="1.4" opacity="0.45"/>
      <path d="M28 22 L36 14 L38.5 16.5 L30.5 24.5 L27 25 Z" fill="currentColor"/>
    </svg>
  ),
  condense: (
    <svg viewBox="0 0 48 32" fill="none" aria-hidden="true">
      <rect x="2"  y="6" width="9" height="20" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="13" y="6" width="9" height="20" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="24" y="6" width="9" height="20" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M35 16 L42 16 M38 13 L42 16 L38 19" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
      <rect x="40" y="11" width="6" height="10" rx="1" fill="currentColor" opacity="0.85"/>
    </svg>
  ),
  visualize: (
    <svg viewBox="0 0 48 32" fill="none" aria-hidden="true">
      <rect x="6" y="4" width="36" height="24" rx="2" stroke="currentColor" strokeWidth="1.4"/>
      <line x1="6" y1="22" x2="42" y2="22" stroke="currentColor" strokeWidth="1.2" opacity="0.4"/>
      <line x1="12" y1="4" x2="12" y2="28" stroke="currentColor" strokeWidth="1.2" opacity="0.4"/>
      <path d="M12 22 Q17 8, 22 18 T34 14 T42 18" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round"/>
    </svg>
  ),
  synthesize: (
    <svg viewBox="0 0 48 32" fill="none" aria-hidden="true">
      <rect x="6" y="4" width="36" height="24" rx="2" stroke="currentColor" strokeWidth="1.4"/>
      <line x1="10" y1="23" x2="38" y2="23" stroke="currentColor" strokeWidth="1.2" opacity="0.4"/>
      <rect x="12" y="17" width="4" height="6" fill="currentColor"/>
      <rect x="19" y="12" width="4" height="11" fill="currentColor"/>
      <rect x="26" y="8"  width="4" height="15" fill="currentColor"/>
      <rect x="33" y="14" width="4" height="9" fill="currentColor"/>
    </svg>
  ),
};

const AUDIENCE_ICONS = {
  exec: (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="7" r="3" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M5 21 L5 17 Q5 13 12 13 Q19 13 19 17 L19 21" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round"/>
      <path d="M11 13 L12 17 L13 13" stroke="currentColor" strokeWidth="1.2"/>
    </svg>
  ),
  customer: (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 6 H20 V16 H13 L9 20 V16 H4 Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" fill="none"/>
      <circle cx="9"  cy="11" r="0.9" fill="currentColor"/>
      <circle cx="12" cy="11" r="0.9" fill="currentColor"/>
      <circle cx="15" cy="11" r="0.9" fill="currentColor"/>
    </svg>
  ),
  conference: (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="3" width="6" height="9" rx="0.5" stroke="currentColor" strokeWidth="1.4"/>
      <line x1="12" y1="12" x2="12" y2="17" stroke="currentColor" strokeWidth="1.4"/>
      <line x1="6" y1="17" x2="18" y2="17" stroke="currentColor" strokeWidth="1.4"/>
      <circle cx="4"  cy="20" r="1.2" fill="currentColor" opacity="0.7"/>
      <circle cx="9"  cy="20" r="1.2" fill="currentColor" opacity="0.7"/>
      <circle cx="15" cy="20" r="1.2" fill="currentColor" opacity="0.7"/>
      <circle cx="20" cy="20" r="1.2" fill="currentColor" opacity="0.7"/>
    </svg>
  ),
  status: (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="5" y="3" width="14" height="18" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M8 8 L9.5 9.5 L12 7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
      <line x1="13" y1="8.5" x2="16" y2="8.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M8 13 L9.5 14.5 L12 12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
      <line x1="13" y1="13.5" x2="16" y2="13.5" stroke="currentColor" strokeWidth="1.4"/>
      <line x1="8" y1="18" x2="16" y2="18" stroke="currentColor" strokeWidth="1.4" opacity="0.45"/>
    </svg>
  ),
  oneonone: (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="8"  cy="8" r="3" stroke="currentColor" strokeWidth="1.4"/>
      <circle cx="16" cy="8" r="3" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M2 20 Q2 14 8 14 Q14 14 14 20" stroke="currentColor" strokeWidth="1.4" fill="none"/>
      <path d="M10 20 Q10 14 16 14 Q22 14 22 20" stroke="currentColor" strokeWidth="1.4" fill="none"/>
    </svg>
  ),
  technical: (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 4 H17 L13 12 L17 20 H6 L11 12 Z" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinejoin="round"/>
    </svg>
  ),
};

// Template options for Step 02c
const TEMPLATES = [
  { key: 'inherit', label: 'Keep input theme',  sub: 'reuse colors + fonts from the uploaded deck' },
  { key: 'clean',   label: 'Clean default',     sub: 'pptgpt house style \u2014 calm whiteboard' },
  { key: 'upload',  label: 'Upload template',   sub: '.pptx / .thmx \u2014 drop your brand assets' },
];

const TEMPLATE_PREVIEWS = {
  // Each preview is a tiny SVG slide thumbnail showing palette + layout cues.
  inherit: (
    <svg viewBox="0 0 64 36" aria-hidden="true">
      <rect width="64" height="36" rx="2" fill="#FAFAF7"/>
      <rect x="2" y="2" width="60" height="6" rx="1" fill="#1E2761" opacity="0.85"/>
      <rect x="4"  y="12" width="22" height="2" rx="1" fill="#1E2761"/>
      <rect x="4"  y="16" width="32" height="1.5" rx="0.75" fill="#94A3B8"/>
      <rect x="4"  y="19" width="28" height="1.5" rx="0.75" fill="#94A3B8"/>
      <rect x="40" y="12" width="20" height="20" rx="1" fill="#C9531C" opacity="0.85"/>
      <text x="63" y="6" fontSize="2.6" textAnchor="end" fill="#FFFFFF" opacity="0.85" fontFamily="monospace">FROM YOUR DECK</text>
    </svg>
  ),
  clean: (
    <svg viewBox="0 0 64 36" aria-hidden="true">
      <rect width="64" height="36" rx="2" fill="#F4F1EA"/>
      <line x1="4" y1="6" x2="10" y2="6" stroke="#1A1A1A" strokeWidth="0.8"/>
      <rect x="4"  y="9"  width="36" height="3" rx="0.5" fill="#1A1A1A"/>
      <rect x="4"  y="14" width="28" height="1.5" rx="0.5" fill="#6C7A89"/>
      <rect x="4"  y="17" width="32" height="1.5" rx="0.5" fill="#6C7A89"/>
      <rect x="4"  y="20" width="22" height="1.5" rx="0.5" fill="#6C7A89"/>
      <circle cx="58" cy="31" r="1.4" fill="#C9531C"/>
    </svg>
  ),
  upload: (
    <svg viewBox="0 0 64 36" aria-hidden="true">
      <rect x="0.75" y="0.75" width="62.5" height="34.5" rx="2"
            fill="none" stroke="#B9B0A0" strokeWidth="1" strokeDasharray="3 2"/>
      <path d="M28 22 L32 16 L36 22 M32 16 L32 26" stroke="#6C7A89" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
      <text x="32" y="9" fontSize="3" textAnchor="middle" fill="#6C7A89" fontFamily="monospace">DROP HERE</text>
    </svg>
  ),
};

const DEFAULT_OUTLINE = {
  draft: [{
    id: 's1',
    title: 'Q3 revenue beat plan by 14%',
    messages: [
      'Net retention 118%, churn down to 1.8%',
      'New enterprise cohort outpacing SMB by 2x',
      'Decision: double down on enterprise GTM',
    ],
    bumper: 'And the trend keeps compounding.',
  }],
  refine: [{
    id: 's1',
    title: 'Quarterly revenue growth — 14% YoY',
    messages: [
      'Chart has three lines, no labels — feels buried',
      'Numbers should land first, narrative second',
      'Want one clear takeaway in the lower-right',
    ],
    bumper: 'The takeaway needs to live below the chart.',
  }],
  condense: [
    { id: 's1', title: 'Q3 results — exec summary', messages: [
      'Net revenue beat plan by 14%',
      'Retention strong, churn down two points',
      'Enterprise GTM working; SMB softening',
    ], bumper: 'Let\u2019s look at the numbers behind the beat.' },
    { id: 's2', title: 'The numbers', messages: [
      'Revenue +14% YoY ($42M)',
      'Net retention 118%',
      'Gross margin held at 76%',
    ], bumper: 'Which raises the question: what\u2019s working?' },
    { id: 's3', title: "What's working", messages: [
      'Enterprise close rate up 2x',
      'Multi-year contracts now 60% of new ARR',
      'Two design-partner wins in the public sector',
    ], bumper: 'So the plan is to double down here.' },
  ],
  visualize: [{
    id: 's1',
    title: 'Damped harmonic oscillator',
    messages: [
      'Amplitude decays exponentially as γ rises',
      'Critical damping happens when γ approaches ω',
      'Real-world: pendulum in air, RLC circuit, mass on a spring',
    ],
    bumper: 'And the math lines up with the intuition.',
  }],
  synthesize: [{
    id: 's1',
    title: 'Quarterly revenue',
    messages: [
      'Q1: 32, Q2: 38, Q3: 42, Q4: 45  (in M$)',
      'Accelerating from Q2 onward',
      'Enterprise GTM is the main driver',
    ],
    bumper: 'The acceleration is real, not a one-off.',
  }],
};

function outlineToRaw(outline) {
  return outline.map(s =>
    [s.title, ...((s.messages || []).filter(Boolean))].join('\n')
  ).join('\n---\n');
}

function uid(prefix) {
  return prefix + '-' + Math.random().toString(36).slice(2, 8);
}

// ───────────────────────────────────────────────────────────────
// PDF / DOCX / PPTX extraction (all lazy, libs loaded on demand)
// ───────────────────────────────────────────────────────────────
let _pdfJsPromise = null;
function loadPdfJs() {
  if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
  if (_pdfJsPromise) return _pdfJsPromise;
  _pdfJsPromise = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://unpkg.com/pdfjs-dist@3.11.174/legacy/build/pdf.min.js';
    s.onload = () => {
      const lib = window.pdfjsLib;
      if (!lib) return reject(new Error('pdf.js loaded but pdfjsLib is missing'));
      if (lib.GlobalWorkerOptions && !lib.GlobalWorkerOptions.workerSrc) {
        lib.GlobalWorkerOptions.workerSrc = 'https://unpkg.com/pdfjs-dist@3.11.174/legacy/build/pdf.worker.min.js';
      }
      resolve(lib);
    };
    s.onerror = () => reject(new Error('Could not load pdf.js from CDN.'));
    document.head.appendChild(s);
  });
  return _pdfJsPromise;
}

let _jsZipPromise = null;
function loadJSZip() {
  if (window.JSZip) return Promise.resolve(window.JSZip);
  if (_jsZipPromise) return _jsZipPromise;
  _jsZipPromise = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://unpkg.com/jszip@3.10.1/dist/jszip.min.js';
    s.onload = () => window.JSZip ? resolve(window.JSZip) : reject(new Error('JSZip missing'));
    s.onerror = () => reject(new Error('Could not load JSZip from CDN.'));
    document.head.appendChild(s);
  });
  return _jsZipPromise;
}

// XML namespaces used inside .docx / .pptx
const OOXML_NS = {
  a: 'http://schemas.openxmlformats.org/drawingml/2006/main',
  p: 'http://schemas.openxmlformats.org/presentationml/2006/main',
  w: 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
};

function getElsNS(root, ns, tag) {
  return Array.from(root.getElementsByTagNameNS(ns, tag));
}

async function extractDocxText(buf) {
  const JSZip = await loadJSZip();
  const zip = await JSZip.loadAsync(buf);
  const file = zip.file('word/document.xml');
  if (!file) throw new Error('Not a Word document (missing word/document.xml).');
  const xml = await file.async('text');
  const dom = new DOMParser().parseFromString(xml, 'application/xml');
  const parser = dom.querySelector('parsererror');
  if (parser) throw new Error('Word file is malformed.');

  // Walk every paragraph, join run texts inside it.
  const paragraphs = getElsNS(dom, OOXML_NS.w, 'p');
  const out = [];
  for (const p of paragraphs) {
    const runs = getElsNS(p, OOXML_NS.w, 't');
    const text = runs.map(t => t.textContent).join('').trim();
    if (text) out.push(text);
  }
  return out.join('\n');
}

// Pull text from one pptx slide XML, returning { title, bullets } so the
// caller can decide how to flatten the deck.
function parsePptxSlideXml(xml) {
  const dom = new DOMParser().parseFromString(xml, 'application/xml');
  const parser = dom.querySelector('parsererror');
  if (parser) return { title: '', bullets: [] };
  const shapes = getElsNS(dom, OOXML_NS.p, 'sp');
  const titleParts = [];
  const bulletParts = [];

  for (const sp of shapes) {
    const phs = getElsNS(sp, OOXML_NS.p, 'ph');
    const phType = phs[0]?.getAttribute('type') || '';
    const isTitle = phType === 'title' || phType === 'ctrTitle';

    const txBodies = getElsNS(sp, OOXML_NS.p, 'txBody');
    for (const tx of txBodies) {
      // each a:p is a paragraph (= a line / bullet)
      const ps = getElsNS(tx, OOXML_NS.a, 'p');
      for (const ap of ps) {
        const runs = getElsNS(ap, OOXML_NS.a, 't');
        const text = runs.map(t => t.textContent).join('').trim();
        if (!text) continue;
        if (isTitle) titleParts.push(text);
        else bulletParts.push(text);
      }
    }
  }
  return { title: titleParts.join(' ').trim(), bullets: bulletParts };
}

async function extractPptxText(buf) {
  const JSZip = await loadJSZip();
  const zip = await JSZip.loadAsync(buf);
  const slideNames = Object.keys(zip.files)
    .filter(n => /^ppt\/slides\/slide\d+\.xml$/.test(n))
    .sort((a, b) => {
      const ai = parseInt(a.match(/slide(\d+)/)[1], 10);
      const bi = parseInt(b.match(/slide(\d+)/)[1], 10);
      return ai - bi;
    });
  if (slideNames.length === 0) throw new Error('Not a PowerPoint file (no slides found).');

  const slidesOut = [];
  for (const name of slideNames) {
    const xml = await zip.file(name).async('text');
    const { title, bullets } = parsePptxSlideXml(xml);
    if (!title && bullets.length === 0) continue;
    const lines = [];
    if (title) lines.push(title);
    for (const b of bullets) lines.push(b);
    slidesOut.push(lines.join('\n'));
  }
  // Join slides with `---` so the existing condense parser recognises them
  // as separate cards. Modes that want one slide will fold them together.
  return slidesOut.join('\n---\n');
}

async function extractFileText(file) {
  if (!file) return '';
  const name = (file.name || '').toLowerCase();
  const type = file.type || '';

  // text-ish files
  if (/\.(txt|md|markdown|rtf|csv)$/.test(name) || type.startsWith('text/')) {
    return await file.text();
  }

  // PDF
  if (name.endsWith('.pdf') || type === 'application/pdf') {
    const lib = await loadPdfJs();
    const buf = await file.arrayBuffer();
    const pdf = await lib.getDocument({ data: buf }).promise;
    let out = '';
    const maxPages = Math.min(pdf.numPages, 30);
    for (let i = 1; i <= maxPages; i++) {
      const page = await pdf.getPage(i);
      const content = await page.getTextContent();
      let lastY = null;
      let line = '';
      const lines = [];
      for (const item of content.items) {
        const y = item.transform ? item.transform[5] : 0;
        if (lastY != null && Math.abs(y - lastY) > 4) {
          if (line.trim()) lines.push(line.trim());
          line = '';
        }
        line += (line && !line.endsWith(' ') ? ' ' : '') + (item.str || '');
        lastY = y;
      }
      if (line.trim()) lines.push(line.trim());
      out += lines.join('\n') + '\n\n';
    }
    return out;
  }

  // Word (.docx)
  if (name.endsWith('.docx') || type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
    const buf = await file.arrayBuffer();
    return await extractDocxText(buf);
  }

  // PowerPoint (.pptx)
  if (name.endsWith('.pptx') || type === 'application/vnd.openxmlformats-officedocument.presentationml.presentation') {
    const buf = await file.arrayBuffer();
    return await extractPptxText(buf);
  }

  // .doc / .ppt (legacy binary) — not supported by client-side parsers
  if (name.endsWith('.doc') || name.endsWith('.ppt')) {
    throw new Error('Legacy binary .doc / .ppt aren\'t supported. Save as .docx / .pptx and try again.');
  }

  // anything else: try as text and hope for the best
  try { return await file.text(); }
  catch (e) { throw new Error('Unsupported file type. Try .pdf, .docx, .pptx, .txt, or .md.'); }
}

// ───────────────────────────────────────────────────────────────
// Hooks
// ───────────────────────────────────────────────────────────────

function useFitScale(ref, designW, designH, minScale) {
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      const padX = 40, padY = 40;
      const s = Math.min((rect.width - padX) / designW, (rect.height - padY) / designH, 1);
      setScale(Math.max(s, minScale || 0.3));
    };
    measure();
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    });
    ro.observe(el);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [designW, designH]);
  return scale;
}

function useDebounced(value, ms) {
  const [d, setD] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setD(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return d;
}

// ───────────────────────────────────────────────────────────────
// Header
// ───────────────────────────────────────────────────────────────

function WBHeader({ mode, onModeChange, loading, onReset, phase, onBackToStoryMap }) {
  const stepActive =
    phase === 'storymap'   ? 1 :
    phase === 'storyboard' ? 3 :
    phase === 'workbench'  ? 4 :
    phase === 'critique'   ? 5 : 1;
  return (
    <header className="wb-header">
      <div className="wb-wordmark">
        <span className="dot" />
        pptgpt
        <span className="meta">
          {phase === 'storymap'   ? 'workbench  ·  story map' :
           phase === 'storyboard' ? 'workbench  ·  storyboard' :
           phase === 'critique'   ? 'workbench  ·  critique' :
                                    'workbench  ·  outline · stage · result'}
        </span>
      </div>
      {phase === 'workbench' ? (
        <div className="wb-modes" role="tablist">
          {Object.entries(MODE_LABELS).map(([k, label]) => (
            <button
              key={k}
              role="tab"
              aria-selected={mode === k}
              className={`wb-mode ${mode === k ? 'is-active' : ''}`}
              onClick={() => onModeChange(k)}
            >{label}</button>
          ))}
        </div>
      ) : (
        <div className="wb-stepdots">
          <span className={`wb-stepdot ${stepActive >= 1 ? 'is-active' : ''}`} />
          <span className={`wb-step-label ${stepActive === 1 ? '' : 'is-faint'}`}>01  upload</span>
          <span className="wb-stepdot-sep" />
          <span className={`wb-stepdot ${stepActive >= 2 ? 'is-active' : ''}`} />
          <span className={`wb-step-label ${stepActive === 2 ? '' : 'is-faint'}`}>02  pick</span>
          <span className="wb-stepdot-sep" />
          <span className={`wb-stepdot ${stepActive >= 3 ? 'is-active' : ''}`} />
          <span className={`wb-step-label ${stepActive === 3 ? '' : 'is-faint'}`}>03  storyboard</span>
          <span className="wb-stepdot-sep" />
          <span className={`wb-stepdot ${stepActive >= 4 ? 'is-active' : ''}`} />
          <span className={`wb-step-label ${stepActive === 4 ? '' : 'is-faint'}`}>04  workbench</span>
          <span className="wb-stepdot-sep" />
          <span className={`wb-stepdot ${stepActive >= 5 ? 'is-active' : ''}`} />
          <span className={`wb-step-label ${stepActive === 5 ? '' : 'is-faint'}`}>05  critique</span>
        </div>
      )}
      <div className="wb-actions">
        {loading && (
          <span className="thinking"><span className="dot" />thinking</span>
        )}
        {phase === 'workbench' && (
          <button onClick={onBackToStoryMap}>← story map</button>
        )}
        <button onClick={onReset}>↺ reset</button>
      </div>
    </header>
  );
}

// ───────────────────────────────────────────────────────────────
// Outline panel
// ───────────────────────────────────────────────────────────────

function OutlinePanel({ outline, selectedId, onSelect, onEdit, onAdd, onRemove, allowMultiSlide }) {
  return (
    <section className="wb-panel">
      <div className="wb-panel__head">
        <span className="wb-panel__title">Outline</span>
        <span className="wb-panel__hint">title + 3 messages</span>
      </div>
      <div className="wb-panel__body">
        {outline.map((slide, i) => (
          <div
            key={slide.id}
            className={`outline-slide ${slide.id === selectedId ? 'is-selected' : ''}`}
            onClick={() => onSelect(slide.id)}
          >
            <div className="outline-slide__head">
              <span className="num">slide {String(i + 1).padStart(2, '0')}</span>
              {allowMultiSlide && outline.length > 1 && (
                <button
                  className="outline-slide__remove"
                  onClick={(e) => { e.stopPropagation(); onRemove(slide.id); }}
                  title="remove slide"
                >×</button>
              )}
            </div>
            <input
              className="outline-title"
              value={slide.title}
              onChange={(e) => onEdit(slide.id, { title: e.target.value })}
              placeholder="Slide title…"
              onClick={(e) => e.stopPropagation()}
            />
            <ul className="outline-msgs">
              {[0, 1, 2].map(idx => (
                <li className="outline-msg" key={idx}>
                  <span className="outline-msg__bullet">0{idx + 1}</span>
                  <AutoTextarea
                    value={slide.messages[idx] || ''}
                    onChange={(v) => {
                      const next = [...slide.messages];
                      next[idx] = v;
                      onEdit(slide.id, { messages: next });
                    }}
                    placeholder={`Message ${idx + 1}…`}
                    onClick={(e) => e.stopPropagation()}
                  />
                </li>
              ))}
            </ul>
          </div>
        ))}
        {allowMultiSlide && (
          <button className="outline-add" onClick={onAdd}>+ add slide</button>
        )}
      </div>
    </section>
  );
}

function AutoTextarea({ value, onChange, placeholder, onClick, dataAnchor }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    if (!ref.current) return;
    ref.current.style.height = 'auto';
    ref.current.style.height = ref.current.scrollHeight + 'px';
  }, [value]);
  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      onClick={onClick}
      rows={1}
      data-anchor={dataAnchor}
    />
  );
}

// ───────────────────────────────────────────────────────────────
// Center: question canvas
// ───────────────────────────────────────────────────────────────

function QuestionCard({ q, index, total, picked, isDrifting, onPick }) {
  return (
    <div className={`wb-card-anchor wb-card-anchor--${q.region}`}>
      <span className="wb-qcard__leader" />
      <span className="wb-qcard__pin" />
      <div className={`wb-qcard ${isDrifting ? 'is-drifting' : ''}`}>
        <div className="wb-qcard__head">
          <span>{String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}</span>
          <span className="wb-qcard__region">{q.region}</span>
        </div>
        <p className="wb-qcard__text">{q.text}</p>
        <div className="wb-qcard__opts">
          {q.options.map(opt => (
            <button
              key={opt}
              className={`wb-qopt ${picked === opt ? 'is-picked' : ''}`}
              disabled={!!picked}
              onClick={() => onPick(opt)}
            >{opt}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

function CenterCanvas({ response, answers, removedIds, onAnswer }) {
  const stageRef = useRef(null);
  const scale = useFitScale(stageRef, WB_DESIGN_W, WB_DESIGN_H, 0.3);

  const slideIR = response && response.slideIR;
  const allQs = response ? response.questions : [];
  const visibleQs = allQs.filter(q => !removedIds.has(q.id));

  return (
    <section className="wb-panel wb-center">
      <div className="wb-panel__head">
        <span className="wb-panel__title">Question canvas</span>
        <span className="wb-panel__hint">
          {visibleQs.length === 0
            ? 'all decisions made'
            : `${visibleQs.length} taste question${visibleQs.length === 1 ? '' : 's'} pending`}
        </span>
      </div>
      <div className="wb-stage" ref={stageRef}>
        <div className="wb-canvas-wrap" style={{ width: WB_DESIGN_W * scale, height: WB_DESIGN_H * scale }}>
          <div
            className="wb-canvas-wrap__scale"
            style={{ width: WB_DESIGN_W, height: WB_DESIGN_H, transform: `scale(${scale})` }}
          >
            <div style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }}>
              <div className="wb-slide-wrap" style={{ width: WB_SLIDE_W, height: WB_SLIDE_H }}>
                <div className="wb-slide-frame" style={{ width: WB_SLIDE_W, height: WB_SLIDE_H }}>
                  <div className="wb-slide-inner">
                    {slideIR && <SlidePreview spec={slideIR} width={WB_SLIDE_W} height={WB_SLIDE_H} />}
                  </div>
                </div>
                <span className="wb-slide-label">
                  draft preview
                  {slideIR && <span className="dim">{slideIR.canvasW}×{slideIR.canvasH}  ·  16:9</span>}
                </span>
                {visibleQs.length === 0 && allQs.length > 0 && (
                  <div style={{ position: 'absolute', left: '50%', top: '100%', transform: 'translate(-50%, 40px)' }}>
                    <span className="wb-all-done">all decisions in  ·  see the result →</span>
                  </div>
                )}
                {visibleQs.map((q) => (
                  <QuestionCard
                    key={q.id}
                    q={q}
                    index={allQs.findIndex(qq => qq.id === q.id)}
                    total={allQs.length}
                    picked={answers[q.id]}
                    isDrifting={!!answers[q.id]}
                    onPick={(opt) => onAnswer(q, opt)}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ───────────────────────────────────────────────────────────────
// Right panel: result + plot sliders
// ───────────────────────────────────────────────────────────────

function PlotSliders({ schema, values, onChange, onReset, formula }) {
  if (!schema || schema.length === 0) return null;
  return (
    <div className="plot-sliders">
      <div className="plot-sliders__head">
        <span className="plot-sliders__title">Tune the parameters</span>
        <button className="plot-sliders__reset" onClick={onReset}>reset</button>
      </div>
      {schema.map((p) => {
        const v = values[p.name] != null ? values[p.name] : p.default;
        return (
          <div className="plot-slider" key={p.name}>
            <div className="plot-slider__row">
              <span className="plot-slider__label">{p.label || p.name}</span>
              <span className="plot-slider__value">{formatNum(v)}</span>
            </div>
            <input
              type="range"
              min={p.min} max={p.max} step={p.step}
              value={v}
              onChange={(e) => onChange(p.name, parseFloat(e.target.value))}
            />
          </div>
        );
      })}
      {formula && <div className="plot-formula">{formula}</div>}
    </div>
  );
}

function formatNum(v) {
  if (!Number.isFinite(v)) return '—';
  const abs = Math.abs(v);
  if (abs === 0) return '0';
  if (abs >= 100) return v.toFixed(0);
  if (abs >= 10)  return v.toFixed(1);
  if (abs >= 1)   return v.toFixed(2);
  return v.toFixed(2);
}

function ResultPanel({ response, selectedKey, onSelectKey, plotParams, onPlotParamChange, onPlotParamReset, onGoToCritique }) {
  const wrapRef = useRef(null);
  const [thumbW, setThumbW] = useState(0);

  const dirs = (response && response.directions) || [];
  const dir = dirs.find(d => d.key === selectedKey) || dirs[0];
  const spec = dir && dir.previewSpec;

  // Callback ref attached to .result-frame itself so we measure exactly when
  // the frame mounts (not on the parent section's resize, which never fires
  // for a child appearing).
  const frameRef = useCallback((node) => {
    if (!node) { setThumbW(0); return; }
    const measure = () => setThumbW(node.clientWidth);
    measure();
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    });
    ro.observe(node);
    // stash the observer on the node so we can clean it up when react detaches
    node.__ro = ro;
    node.__raf = () => cancelAnimationFrame(raf);
  }, []);

  const thumbH = spec ? thumbW * (spec.canvasH / spec.canvasW) : 0;

  // Plot parameter schema extracted from the spec
  const schema = useMemo(() => spec ? extractPlotParamSchema(spec) : [], [spec]);
  // Pull plot formula if there's a plot block (mock keeps it as a text block;
  // in the workbench we just show whatever lives in plot-sliders chrome)

  return (
    <section className="wb-panel" ref={wrapRef}>
      <div className="wb-panel__head">
        <span className="wb-panel__title">Result preview</span>
        <span className="wb-panel__hint">
          {dirs.length > 0 ? 'live · tap a direction' : 'no directions yet'}
          {dirs.length > 0 && (
            <button
              className="wb-print"
              onClick={() => window.print()}
              title="Open the print dialog — save as PDF from there"
            >save as pdf</button>
          )}
          {dirs.length > 0 && onGoToCritique && (
            <button
              className="wb-print wb-critique-btn"
              onClick={onGoToCritique}
              title="See what the room will ask"
            >rehearse the room →</button>
          )}
        </span>
      </div>
      {dirs.length > 0 && (
        <div className="result-tabs">
          {dirs.map(d => (
            <button
              key={d.key}
              className={`result-tab ${d === dir ? 'is-active' : ''}`}
              onClick={() => onSelectKey(d.key)}
            >{d.label}</button>
          ))}
        </div>
      )}
      <div className="wb-panel__body">
        {!spec && (
          <div style={{ color: 'var(--gray)', fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', padding: '40px 0', textAlign: 'center' }}>
            edit the outline or answer a question to see a result
          </div>
        )}
        {spec && (
          <>
            <div className="result-frame" ref={frameRef}>
              {thumbW > 0 && (
                <SlidePreview spec={spec} width={thumbW} height={thumbH} plotParams={plotParams} />
              )}
            </div>
            <div className="result-meta">{dir.key} · {dir.label}</div>
            <div className="result-blurb">{dir.blurb || ''}</div>
            <PlotSliders
              schema={schema}
              values={plotParams}
              onChange={onPlotParamChange}
              onReset={onPlotParamReset}
            />
          </>
        )}
      </div>
    </section>
  );
}

// ───────────────────────────────────────────────────────────────
// Story-map phase
// ───────────────────────────────────────────────────────────────

function StoryMap({ mode, onModeChange, audience, onAudienceChange, template, onTemplateChange, loading, onExtracted, file: extFile, onFileChange }) {
  const [pasteText, setPasteText] = useState('');
  const [file, setFile] = useState(null);
  const [templateFile, setTemplateFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [targetCount, setTargetCount] = useState(5);

  async function extract() {
    setError('');
    let text = pasteText.trim();
    let sourceImages = [];   // [{ slideIdx, path, alt, kind, chart_data? }]
    if (file) {
      setExtracting(true);
      // For .pptx specifically, prefer the backend ingest path when
      // a FastAPI server is reachable: it gives us per-slide image
      // blobs (saved to /uploads/...) and chart data. Falls back to
      // the pure client-side text extractor on Netlify / static.
      const isPptx = /\.pptx$/i.test(file.name || '')
        || (file.type || '').includes('presentationml');
      let backendDeck = null;
      if (isPptx && (location.protocol === 'http:' || location.protocol === 'https:')) {
        try {
          const fd = new FormData();
          fd.append('file', file);
          const r = await fetch(location.origin + '/api/ingest', { method: 'POST', body: fd });
          if (r.ok) backendDeck = await r.json();
        } catch (_e) { backendDeck = null; }
      }
      if (backendDeck && Array.isArray(backendDeck.slides)) {
        // Flatten the backend deck into the same blob-of-text+separators
        // shape window.extractStoryboard expects, AND collect the images
        // per source slide so we can re-attach after extraction.
        const chunks = [];
        backendDeck.slides.forEach((s, i) => {
          const lines = [];
          for (const b of (s.blocks || [])) {
            if (b.kind === 'title' && b.text) lines.push(b.text);
            else if (b.kind === 'paragraph' && b.text) lines.push(b.text);
            else if (b.kind === 'bullets' && Array.isArray(b.items)) lines.push(...b.items);
            else if (b.kind === 'stat' && b.value) lines.push(`${b.value} — ${b.label || ''}`.trim());
          }
          if (lines.length) chunks.push(lines.join('\n'));
          for (const im of (s.images || [])) {
            sourceImages.push({ slideIdx: i, path: im.path, alt: im.alt, kind: im.kind, chart_data: im.chart_data });
          }
        });
        const joined = chunks.join('\n---\n');
        text = (text ? text + '\n\n' : '') + joined;
      } else {
        try {
          text = (text ? text + '\n\n' : '') + (await extractFileText(file));
        } catch (e) {
          setError(e.message || 'Could not read file.');
          setExtracting(false);
          return;
        }
      }
    }
    if (!text) {
      setError('Paste some text or drop a file first.');
      setExtracting(false);
      return;
    }
    try {
      const res = await window.extractStoryboard({ text, mode, audience, targetCount });
      // Re-attach source images. mockBackend tags each output slide with
      // sourceIdx (the chunk index it came from), so we can route the
      // backend-extracted images even after condense reorders/slices.
      const enrichedOutline = res.outline.map((s, i) => {
        const src = (typeof s.sourceIdx === 'number') ? s.sourceIdx : i;
        const imgs = sourceImages.filter(im => im.slideIdx === src);
        return imgs.length ? { ...s, images: imgs } : s;
      });
      onExtracted({
        outline: enrichedOutline,
        recommendations: res.recommendations || [],
        sourceFile: file,
        sourceText: text,
        targetCount,
      });
    } catch (e) {
      setError(e.message || 'Extraction failed.');
    }
    setExtracting(false);
  }

  const [peek, setPeek] = useState(null);
  const [peeking, setPeeking] = useState(false);

  function onFile(f) {
    if (!f) return;
    setFile(f);
    setError('');
    setPeek(null);
    // Only .pptx is peek-able server-side. Skip for other formats.
    const ext = (f.name || '').toLowerCase().split('.').pop();
    if (ext !== 'pptx') return;
    setPeeking(true);
    const fd = new FormData();
    fd.append('file', f, f.name);
    fetch('/api/peek', { method: 'POST', body: fd })
      .then(r => r.ok ? r.json() : null)
      .then(j => setPeek(j))
      .catch(() => setPeek(null))
      .finally(() => setPeeking(false));
  }

  async function loadSample() {
    setError('');
    try {
      const res = await fetch('/samples/cadme_claude_usecases.pptx');
      if (!res.ok) throw new Error('sample fetch failed: ' + res.status);
      const blob = await res.blob();
      const f = new File([blob], 'cadme_claude_usecases.pptx', {
        type: blob.type || 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      });
      onFile(f);
    } catch (e) {
      setError('Could not load the sample deck. ' + (e.message || ''));
    }
  }

  function onDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) onFile(f);
  }

  function editSlide(id, patch) {
    setOutline(prev => prev.map(s => s.id === id ? { ...s, ...patch } : s));
  }
  function addCard() {
    setOutline(prev => [...prev, { id: uid('s'), title: '', messages: ['', '', ''] }]);
  }
  function removeCard(id) {
    setOutline(prev => {
      const next = prev.filter(s => s.id !== id);
      return next.length === 0 ? [{ id: uid('s'), title: '', messages: ['', '', ''] }] : next;
    });
  }
  function moveCard(id, dir) {
    setOutline(prev => {
      const i = prev.findIndex(s => s.id === id);
      if (i < 0) return prev;
      const j = i + dir;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }

  function dismissRec(id) {
    setDismissedRecs(prev => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }
  function acceptRec(rec) {
    setOutline(prev => {
      let next = [...prev];
      if (rec.kind === 'merge' && rec.slideIds && rec.slideIds.length >= 2) {
        const [a, b] = rec.slideIds;
        const ai = next.findIndex(s => s.id === a);
        const bi = next.findIndex(s => s.id === b);
        if (ai > -1 && bi > -1 && ai !== bi) {
          const aSlide = next[ai];
          const bSlide = next[bi];
          const merged = {
            id: aSlide.id,
            title: aSlide.title,
            messages: dedupe([...aSlide.messages, ...bSlide.messages]).filter(Boolean).slice(0, 3),
          };
          while (merged.messages.length < 3) merged.messages.push('');
          next[ai] = merged;
          next.splice(bi, 1);
        }
      } else if (rec.kind === 'add-setup') {
        next.unshift({ id: uid('s'), title: 'Setup', messages: ['Context for what follows', '', ''] });
      } else if (rec.kind === 'trim' && rec.slideIds) {
        next = next.filter(s => !rec.slideIds.includes(s.id));
      } else if (rec.kind === 'thin') {
        next = next.map(s => {
          const kept = s.messages.filter(Boolean).slice(0, 2);
          while (kept.length < 3) kept.push('');
          return { ...s, messages: kept };
        });
      } else if (rec.kind === 'add-actions') {
        next.push({ id: uid('s'), title: 'Next steps', messages: ['Action  ·  owner  ·  by when', '', ''] });
      }
      return next.length === 0 ? [emptyOutlineSlide()] : next;
    });
    dismissRec(rec.id);
  }

  function dedupe(arr) {
    const seen = new Set();
    return arr.filter(x => {
      const k = (x || '').trim().toLowerCase();
      if (!k || seen.has(k)) return false;
      seen.add(k);
      return true;
    });
  }
  function emptyOutlineSlide() {
    return { id: uid('s'), title: '', messages: ['', '', ''] };
  }

  const allowMulti = mode === 'condense';

  return (
    <div className="sm">
      <div className="sm-inner">
        <div>
          <div className="sm-eyebrow">step one  ·  the story map</div>
          <h1 className="sm-title">
            Start with the <em>raw material</em>.
          </h1>
          <p className="sm-sub">
            Paste a draft, drop a PDF, or both. We'll pull out a storyboard you can edit before
            heading into the workbench.
          </p>
        </div>

        {/* Step 1 — input */}
        <div className="sm-step">
          <div className="sm-step__head">
            <span className="sm-step__num">01</span>
            <span className="sm-step__title">Drop a file, paste some text, or both.</span>
          </div>
          <div className="sm-inputs">
          <div className="sm-card sm-paste">
            <div className="sm-card__head">
              <span className="sm-card__title">Paste text</span>
              <span className="sm-card__hint">title / bullets / --- between slides</span>
            </div>
            <textarea
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              placeholder={
                mode === 'condense'
                  ? 'Slide 1 title\nbullets…\n---\nSlide 2 title\nbullets…'
                  : mode === 'visualize'
                  ? 'Damped harmonic oscillator\n\nAmplitude decays with γ\nCritical damping at γ = ω\nApplications: pendulum, RLC, springs'
                  : mode === 'synthesize'
                  ? 'Quarterly revenue\n\nQ1, 32\nQ2, 38\nQ3, 42\nQ4, 45\n\n(commas, tabs, or pipes between cells)'
                  : 'One title.\nA few lines of body.\nNumbers if you have them.\nA decision or takeaway.'
              }
            />
          </div>

          <div
            className={`sm-card sm-upload ${dragOver ? 'is-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
          >
            <div className="sm-card__head">
              <span className="sm-card__title">Or drop a file</span>
              <span className="sm-card__hint">pdf  ·  docx  ·  pptx  ·  txt  ·  md</span>
            </div>
            <label className={`sm-drop ${dragOver ? 'is-over' : ''}`}>
              <span className="sm-drop__icon">↑</span>
              <span className="sm-drop__label">
                {file ? 'replace file' : 'click to pick a file'}
              </span>
              <span className="sm-drop__hint">or drag one in</span>
              <input type="file"
                     accept=".pdf,.docx,.pptx,.txt,.md,.markdown,text/*,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation"
                     onChange={(e) => onFile(e.target.files[0])} />
            </label>
            {file && (
              <div className="sm-upload__file">
                <span>📄 {file.name}  ·  {Math.round(file.size / 1024)} KB</span>
                <button className="sm-upload__clear" onClick={() => { setFile(null); setPeek(null); }}>×</button>
              </div>
            )}
            {!file && (
              <div className="sm-upload__sample">
                <span>No deck handy?</span>
                <button
                  type="button"
                  className="sm-upload__sample-link"
                  onClick={loadSample}
                >try a sample .pptx →</button>
              </div>
            )}
          </div>
        </div>

        {(peeking || peek) && (
          <div className="sm-peek">
            {peeking && <div className="sm-peek__loading">reading deck…</div>}
            {peek && (
              <>
                <div className="sm-peek__stats">
                  <span className="sm-peek__stat"><strong>{peek.slide_count}</strong> slide{peek.slide_count === 1 ? '' : 's'}</span>
                  {peek.image_count > 0 && (
                    <span className="sm-peek__stat"><strong>{peek.image_count}</strong> image{peek.image_count === 1 ? '' : 's'}</span>
                  )}
                  {peek.chart_count > 0 && (
                    <span className="sm-peek__stat"><strong>{peek.chart_count}</strong> chart{peek.chart_count === 1 ? '' : 's'}</span>
                  )}
                  <span className="sm-peek__stat sm-peek__stat--mute">{Math.round((peek.size_bytes || 0) / 1024)} KB</span>
                </div>
                <ol className="sm-peek__slides">
                  {(peek.slides || []).map(s => (
                    <li key={s.index}>
                      <span className="sm-peek__idx">{String(s.index + 1).padStart(2, '0')}</span>
                      <span className="sm-peek__title">{s.title}</span>
                    </li>
                  ))}
                </ol>
              </>
            )}
          </div>
        )}
        </div>{/* /sm-step 01 */}

        {error && <div className="sm-error">{error}</div>}

        {/* Step 2 — pick the goal */}
        <div className="sm-step">
          <div className="sm-step__head">
            <span className="sm-step__num">02</span>
            <span className="sm-step__title">What do you want to do with this?</span>
          </div>
          <div className="sm-goals">
            {Object.entries(MODE_DESCRIPTIONS).map(([k, m]) => (
              <button
                key={k}
                className={`sm-goal ${mode === k ? 'is-active' : ''}`}
                onClick={() => onModeChange(k)}
              >
                <span className="sm-goal__icon">{GOAL_ICONS[k]}</span>
                <span className="sm-goal__verb">{m.verb}</span>
                <span className="sm-goal__sub">{m.sub}</span>
              </button>
            ))}
          </div>
          {(mode === 'condense' || mode === 'draft') && (
            <div className="sm-substep">
              <span className="sm-substep__label">{mode === 'draft' ? 'how many slides?' : 'target slides'}</span>
              <div className="sm-stepper">
                <button onClick={() => setTargetCount(c => Math.max(1, c - 1))} disabled={targetCount <= 1}>−</button>
                <span className="sm-stepper__value">{targetCount}</span>
                <button onClick={() => setTargetCount(c => Math.min(mode === 'draft' ? 6 : 10, c + 1))} disabled={targetCount >= (mode === 'draft' ? 6 : 10)}>+</button>
              </div>
              <span className="sm-substep__hint">{mode === 'draft' ? '1 — 6' : '2 — 10'}</span>
            </div>
          )}
        </div>

        {/* Step 2b — pick the audience */}
        <div className="sm-step">
          <div className="sm-step__head">
            <span className="sm-step__num">02b</span>
            <span className="sm-step__title">Who is in the room?</span>
          </div>
          <div className="sm-audience">
            {AUDIENCES.map(a => (
              <button
                key={a.key}
                className={`sm-aud ${audience === a.key ? 'is-active' : ''}`}
                onClick={() => onAudienceChange(a.key)}
              >
                <span className="sm-aud__icon">{AUDIENCE_ICONS[a.key]}</span>
                <span className="sm-aud__text">
                  <span className="sm-aud__label">{a.label}</span>
                  <span className="sm-aud__sub">{a.sub}</span>
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Step 2c — template */}
        <div className="sm-step">
          <div className="sm-step__head">
            <span className="sm-step__num">02c</span>
            <span className="sm-step__title">Visual template</span>
          </div>
          <div className="sm-templates">
            {TEMPLATES.map(t => {
              const isInherit = t.key === 'inherit';
              const inheritAvailable = file && /\.pptx$/i.test(file.name || '');
              const disabled = isInherit && !inheritAvailable;
              return (
                <button
                  key={t.key}
                  className={`sm-tpl ${template === t.key ? 'is-active' : ''} ${disabled ? 'is-disabled' : ''}`}
                  onClick={() => !disabled && onTemplateChange(t.key)}
                  disabled={disabled}
                  title={disabled ? 'Upload a .pptx in step 01 to enable this' : undefined}
                >
                  <span className="sm-tpl__thumb">{TEMPLATE_PREVIEWS[t.key]}</span>
                  <span className="sm-tpl__label">{t.label}</span>
                  <span className="sm-tpl__sub">{t.sub}</span>
                  {disabled && <span className="sm-tpl__disabled">needs a .pptx in step 01</span>}
                </button>
              );
            })}
          </div>
          {template === 'upload' && (
            <label className="sm-tpl__uploader">
              <span className="sm-tpl__uploader-icon">↑</span>
              <span className="sm-tpl__uploader-label">
                {templateFile ? templateFile.name : 'pick a .pptx or .thmx template'}
              </span>
              <input
                type="file"
                accept=".pptx,.thmx,application/vnd.openxmlformats-officedocument.presentationml.presentation"
                onChange={(e) => setTemplateFile(e.target.files[0])}
              />
            </label>
          )}
        </div>

        <div className="sm-cta-row">
          <button
            className="sm-extract"
            onClick={extract}
            disabled={extracting || (!pasteText.trim() && !file)}
          >
            {extracting ? 'reading…' : 'extract storyboard'} <span className="arrow">→</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// Storyboard page (its own phase)
// ───────────────────────────────────────────────────────────────

const STORYBOARD_STOPWORDS = new Set([
  'the','a','an','and','or','of','to','for','in','on','at','is','it','this','that',
  'with','from','as','by','be','are','was','were','but','so','if','we','our','you',
  'your','their','they','will','can','have','has','had','about','into',
  'than','then','what','which','who','one','more','less','most','any','some','no',
]);
function tokenize(s) {
  return (s || '').toLowerCase().match(/\b[a-z][a-z0-9]+\b/g) || [];
}
function tokenSet(s) {
  return new Set(tokenize(s).filter(w => !STORYBOARD_STOPWORDS.has(w)));
}
function fieldText(slide, field, msgIdx) {
  if (field === 'title')  return slide.title || '';
  if (field === 'bumper') return slide.bumper || '';
  if (field === 'msg')    return (slide.messages || [])[msgIdx] || '';
  return '';
}
function fieldAnchor(slide, field, msgIdx) {
  // stable key used as data-anchor on the DOM element
  if (field === 'msg') return `${slide.id}::msg::${msgIdx}`;
  return `${slide.id}::${field}`;
}

// Build the thread graph: for every non-empty title/message/bumper, find
// the strongest match in the next 1-2 slides. Multiple threads can run in
// parallel; thread "health" derives from the count and the longest chain.
function computeThreads(slides) {
  const threads = [];
  if (!slides || slides.length < 2) return threads;
  for (let i = 0; i < slides.length; i++) {
    const slide = slides[i];
    const sources = [
      { field: 'title',  msgIdx: null },
      { field: 'msg',    msgIdx: 0 },
      { field: 'msg',    msgIdx: 1 },
      { field: 'msg',    msgIdx: 2 },
      { field: 'bumper', msgIdx: null },
    ];
    for (const src of sources) {
      const srcText = fieldText(slide, src.field, src.msgIdx);
      const srcTokens = tokenSet(srcText);
      if (srcTokens.size === 0) continue;

      let best = null;
      for (let j = i + 1; j < Math.min(slides.length, i + 3); j++) {
        const next = slides[j];
        const tgts = [
          { field: 'title', msgIdx: null },
          { field: 'msg',   msgIdx: 0 },
          { field: 'msg',   msgIdx: 1 },
          { field: 'msg',   msgIdx: 2 },
        ];
        for (const tgt of tgts) {
          const txt = fieldText(next, tgt.field, tgt.msgIdx);
          if (!txt.trim()) continue;
          const tt = tokenSet(txt);
          const overlap = [...srcTokens].filter(w => tt.has(w));
          if (overlap.length === 0) continue;
          const score = overlap.length - (j - i - 1) * 0.4;
          if (!best || score > best.score) {
            best = {
              from: { slideIdx: i, anchor: fieldAnchor(slide, src.field, src.msgIdx), field: src.field, msgIdx: src.msgIdx },
              to:   { slideIdx: j, anchor: fieldAnchor(next, tgt.field, tgt.msgIdx), field: tgt.field, msgIdx: tgt.msgIdx },
              keywords: overlap,
              score,
            };
          }
        }
        // If we found a strong adjacent-slide match, take it
        if (best && best.to.slideIdx === i + 1 && best.score >= 1) break;
      }
      if (best) threads.push(best);
    }
  }
  return threads;
}

// Derive a "thread health" report from the threads + slides.
function threadHealth(slides, threads) {
  if (!slides || slides.length < 2) return { state: 'na', summary: 'Add a second slide to see threads.' };
  const cellCount = slides.length * 4; // title + 3 messages per slide as "cells"
  const touched = new Set();
  for (const t of threads) {
    touched.add(t.from.anchor);
    touched.add(t.to.anchor);
  }
  // Compute longest chain via simple DFS
  const byFrom = new Map();
  for (const t of threads) {
    if (!byFrom.has(t.from.anchor)) byFrom.set(t.from.anchor, []);
    byFrom.get(t.from.anchor).push(t);
  }
  const memo = new Map();
  function chainLen(anchor) {
    if (memo.has(anchor)) return memo.get(anchor);
    const outs = byFrom.get(anchor) || [];
    let best = 1;
    for (const t of outs) best = Math.max(best, 1 + chainLen(t.to.anchor));
    memo.set(anchor, best);
    return best;
  }
  let longest = 0;
  for (const t of threads) longest = Math.max(longest, chainLen(t.from.anchor));
  const isolated = Math.max(0, slides.length * 3 - touched.size);  // messages without any thread

  let state, summary;
  if (threads.length === 0) {
    state = 'broken';
    summary = `No threads detected across ${slides.length} slides. Every slide reads as a stand-alone — add overlapping language to tie them together.`;
  } else if (longest >= slides.length - 1) {
    state = 'strong';
    summary = `One strong thread runs the length of the deck (${longest} steps). ${threads.length} total thread${threads.length === 1 ? '' : 's'}.`;
  } else if (threads.length >= slides.length) {
    state = 'mixed';
    summary = `${threads.length} threads but the longest chain is only ${longest}. The deck has overlapping ideas without a single spine.`;
  } else {
    state = 'loose';
    summary = `${threads.length} short thread${threads.length === 1 ? '' : 's'} (longest: ${longest} steps). The deck reads like a list — consider weaving a recurring concept through.`;
  }
  return { state, summary, total: threads.length, longest, isolated };
}

// Renders the storyboard as a Figma-style canvas of draggable tiles. Each
// title / message / bumper is its own free-positioned tile; threads draw
// between their DOM positions so the lines follow the user's layout.
function StoryboardCanvas({ outline, allowMulti, onEdit, onAdd, onRemove, onMove }) {
  const canvasRef = React.useRef(null);
  const [positions, setPositions] = React.useState({});
  const [dragging, setDragging] = React.useState(null);
  const [paths, setPaths] = React.useState([]);
  const threads = React.useMemo(() => computeThreads(outline), [outline]);
  const health = React.useMemo(() => threadHealth(outline, threads), [outline, threads]);

  // Default-position any tile we haven't seen yet (preserves user drags).
  const slideIdsKey = outline.map(s => s.id).join('|');
  React.useEffect(() => {
    setPositions(prev => {
      const next = { ...prev };
      const W = 320;
      outline.forEach((s, i) => {
        const x = 16 + i * W;
        const ensure = (k, dy) => { if (!next[k]) next[k] = { x, y: dy }; };
        ensure(fieldAnchor(s, 'title'),       16);
        ensure(fieldAnchor(s, 'msg', 0),      96);
        ensure(fieldAnchor(s, 'msg', 1),     180);
        ensure(fieldAnchor(s, 'msg', 2),     264);
        ensure(fieldAnchor(s, 'bumper'),     348);
      });
      return next;
    });
  }, [slideIdsKey]);

  function resetLayout() {
    setPositions({});
    // immediately reseed
    setTimeout(() => {
      const next = {};
      const W = 320;
      outline.forEach((s, i) => {
        const x = 16 + i * W;
        next[fieldAnchor(s, 'title')]   = { x, y: 16 };
        next[fieldAnchor(s, 'msg', 0)]  = { x, y: 96 };
        next[fieldAnchor(s, 'msg', 1)]  = { x, y: 180 };
        next[fieldAnchor(s, 'msg', 2)]  = { x, y: 264 };
        next[fieldAnchor(s, 'bumper')]  = { x, y: 348 };
      });
      setPositions(next);
    }, 0);
  }

  // Pointer-event drag handling — global listeners so the drag continues
  // when the cursor leaves the canvas during a fast drag. X is free during
  // the drag; on release, the tile snaps to the nearest slide column.
  React.useEffect(() => {
    if (!dragging) return;
    function onMove(e) {
      setPositions(prev => ({
        ...prev,
        [dragging.anchor]: {
          x: dragging.originX + (e.clientX - dragging.startX),
          y: Math.max(8, dragging.originY + (e.clientY - dragging.startY)),
        },
      }));
    }
    function onUp() {
      // Snap X to the nearest column position so tiles stay column-aligned.
      const W = 280;
      const cols = outline.map((_, i) => 16 + i * W);
      setPositions(prev => {
        const cur = prev[dragging.anchor];
        if (!cur || cols.length === 0) return prev;
        let nearest = cols[0], best = Infinity;
        for (const c of cols) {
          const d = Math.abs(c - cur.x);
          if (d < best) { best = d; nearest = c; }
        }
        return { ...prev, [dragging.anchor]: { x: nearest, y: cur.y } };
      });
      setDragging(null);
    }
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
    };
  }, [dragging, outline]);

  function onGripDown(e, anchor) {
    e.preventDefault();
    const pos = positions[anchor] || { x: 0, y: 0 };
    setDragging({
      anchor,
      startX: e.clientX, startY: e.clientY,
      originX: pos.x,    originY: pos.y,
    });
  }

  // Compute SVG paths from current DOM positions of anchors.
  React.useLayoutEffect(() => {
    if (!canvasRef.current) return;
    let rafId = 0;
    const measure = () => {
      const root = canvasRef.current;
      if (!root) return;
      const rootRect = root.getBoundingClientRect();
      const scrollX = root.scrollLeft;
      const scrollY = root.scrollTop;
      const next = threads.map((t) => {
        const a = root.querySelector(`[data-anchor="${t.from.anchor}"]`);
        const b = root.querySelector(`[data-anchor="${t.to.anchor}"]`);
        if (!a || !b) return null;
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        const ax = ar.right  - rootRect.left + scrollX;
        const ay = ar.top + ar.height / 2 - rootRect.top + scrollY;
        const bx = br.left   - rootRect.left + scrollX;
        const by = br.top + br.height / 2 - rootRect.top + scrollY;
        const dx = Math.max(40, Math.abs(bx - ax) * 0.45);
        const d = `M ${ax.toFixed(1)} ${ay.toFixed(1)} C ${(ax + dx).toFixed(1)} ${ay.toFixed(1)}, ${(bx - dx).toFixed(1)} ${by.toFixed(1)}, ${bx.toFixed(1)} ${by.toFixed(1)}`;
        return { d, strength: t.keywords.length, label: t.keywords.slice(0, 2).join(', '), labelX: (ax + bx) / 2, labelY: (ay + by) / 2 };
      }).filter(Boolean);
      setPaths(next);
    };
    measure();
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(measure);
    });
    ro.observe(canvasRef.current);
    canvasRef.current.querySelectorAll('[data-anchor]').forEach(el => ro.observe(el));
    return () => {
      cancelAnimationFrame(rafId);
      ro.disconnect();
    };
  }, [outline, threads, positions]);

  // Canvas content area must size to fit the tiles' bounding box.
  const bounds = React.useMemo(() => {
    let maxX = 0, maxY = 0;
    Object.values(positions).forEach(p => {
      maxX = Math.max(maxX, p.x + 320);
      maxY = Math.max(maxY, p.y + 120);
    });
    return { w: Math.max(maxX + 40, 960), h: Math.max(maxY + 60, 560) };
  }, [positions]);

  return (
    <>
      <div className="sb-banner-row">
        <div className={`sb-health is-${health.state}`}>
          <span className="sb-health__dot" />
          <span className="sb-health__text">{health.summary}</span>
        </div>
        <button className="sb-reset-layout" onClick={resetLayout} title="Reset all tiles to their default grid">↺ relayout</button>
      </div>
      <div className="sb-canvas" ref={canvasRef}>
        <div className="sb-content" style={{ width: bounds.w, height: bounds.h }}>
          <svg className="sb-overlay" width={bounds.w} height={bounds.h}>
            <defs>
              <marker id="sb-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
              </marker>
            </defs>
            {paths.map((p, i) => (
              <g key={i} className={`sb-thread sb-thread--s${Math.min(p.strength, 3)}`}>
                <path d={p.d} fill="none" markerEnd="url(#sb-arrow)" />
                {p.label && (
                  <foreignObject x={p.labelX - 70} y={p.labelY - 12} width="140" height="24"
                                 style={{ pointerEvents: 'none' }}>
                    <div className="sb-thread__label" xmlns="http://www.w3.org/1999/xhtml">{p.label}</div>
                  </foreignObject>
                )}
              </g>
            ))}
          </svg>
          {outline.map((slide, idx) => {
            const slideNum = String(idx + 1).padStart(2, '0');
            const tile = (anchor, kind, body) => {
              const pos = positions[anchor] || { x: 0, y: 0 };
              return (
                <div
                  key={anchor}
                  className={`sb-tile sb-tile--${kind} ${dragging && dragging.anchor === anchor ? 'is-dragging' : ''}`}
                  data-anchor={anchor}
                  style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }}
                >
                  <div className="sb-tile__head" onPointerDown={(e) => onGripDown(e, anchor)}>
                    <span className="sb-tile__grip" aria-hidden="true">⠿</span>
                    <span className="sb-tile__slide">slide {slideNum}</span>
                    <span className="sb-tile__kind">{kind === 'title' ? 'title' : kind === 'bumper' ? 'bumper' : 'msg ' + kind.replace('msg', '')}</span>
                    {kind === 'title' && allowMulti && outline.length > 1 && (
                      <span className="sb-tile__actions">
                        <button onClick={() => onMove(slide.id, -1)} disabled={idx === 0} title="move slide left">←</button>
                        <button onClick={() => onMove(slide.id, +1)} disabled={idx === outline.length - 1} title="move slide right">→</button>
                        <button onClick={() => onRemove(slide.id)} title="remove slide">×</button>
                      </span>
                    )}
                  </div>
                  <div className="sb-tile__body">{body}</div>
                </div>
              );
            };
            return (
              <React.Fragment key={slide.id}>
                {tile(fieldAnchor(slide, 'title'), 'title', (
                  <>
                    <input
                      className="sb-tile__title-input"
                      value={slide.title}
                      onChange={(e) => onEdit(slide.id, { title: e.target.value })}
                      placeholder="Slide title…"
                    />
                    {Array.isArray(slide.images) && slide.images.length > 0 && (
                      <div className="sb-tile__thumbs" title="From the source deck">
                        {slide.images.map((im, ii) => {
                          if (im.kind === 'chart') {
                            const t = (im.chart_data && im.chart_data.type) || 'chart';
                            return (
                              <div key={ii} className="sb-tile__chart-chip" title={im.alt || t}>
                                <span aria-hidden="true">▦</span> {t}
                              </div>
                            );
                          }
                          if (im.path) {
                            return (
                              <img
                                key={ii}
                                className="sb-tile__thumb"
                                src={im.path}
                                alt={im.alt || ''}
                                title={im.alt || ''}
                                loading="lazy"
                              />
                            );
                          }
                          return (
                            <div key={ii} className="sb-tile__thumb-placeholder" title={im.alt || im.kind}>
                              {im.kind}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </>
                ))}
                {[0,1,2].map(m => (
                  <React.Fragment key={m}>
                    {tile(fieldAnchor(slide, 'msg', m), 'msg' + (m+1), (
                      <AutoTextarea
                        value={slide.messages[m] || ''}
                        onChange={(v) => {
                          const next = [...slide.messages];
                          next[m] = v;
                          onEdit(slide.id, { messages: next });
                        }}
                        placeholder={`Key message ${m+1}…`}
                      />
                    ))}
                  </React.Fragment>
                ))}
                {tile(fieldAnchor(slide, 'bumper'), 'bumper', (
                  <AutoTextarea
                    value={slide.bumper || ''}
                    onChange={(v) => onEdit(slide.id, { bumper: v })}
                    placeholder="Transition into the next slide…"
                  />
                ))}
              </React.Fragment>
            );
          })}
          {allowMulti && (
            <button
              className="sb-add-card"
              style={{ position: 'absolute', left: bounds.w - 240, top: 24 }}
              onClick={onAdd}
            >+ add slide</button>
          )}
        </div>
      </div>
    </>
  );
}

// ───────────────────────────────────────────────────────────────
// Thread Map — visualizes the deck's narrative messiness.
// Ported from v1 frontend/workbench.jsx. Calls /api/thread_map when
// a backend is reachable; renders an inline placeholder when not
// (Netlify static build has no backend, so the tab degrades to a
// "wire up the backend" hint instead of crashing).
// ───────────────────────────────────────────────────────────────

function ThreadMapView({ outline, recs, dismissedRecs, acceptedIds }) {
  const [vizMode, setVizMode] = useState('graph');
  const [recMode, setRecMode] = useState('potential');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [unreachable, setUnreachable] = useState(false);

  const liveRecs = useMemo(
    () => (recs || []).filter(r => !dismissedRecs.has(r.id)),
    [recs, dismissedRecs]
  );

  useEffect(() => {
    let cancelled = false;
    async function go() {
      if (!outline || outline.length === 0) { setData(null); return; }
      setLoading(true);
      setUnreachable(false);
      const reqBody = {
        outline,
        recommendations: liveRecs,
        acceptedIds: Array.from(acceptedIds || []),
        mode: recMode,
      };
      try {
        const url = (location.protocol === 'http:' || location.protocol === 'https:')
          ? location.origin + '/api/thread_map'
          : '/api/thread_map';
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(reqBody),
        });
        if (!res.ok) throw new Error('thread_map ' + res.status);
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (err) {
        // Backend unreachable (Netlify static, etc.) — fall back to the
        // client-side lexical compute exposed by mockBackend.js. Flag the
        // tier so the UI can show the lexical badge instead of silently
        // pretending it ran the real cascade.
        if (!cancelled && typeof window.computeThreadMapLocal === 'function') {
          try {
            const local = await window.computeThreadMapLocal(reqBody);
            if (!cancelled) { setData(local); setUnreachable(false); }
          } catch (_e) {
            if (!cancelled) { setData(null); setUnreachable(true); }
          }
        } else if (!cancelled) {
          setData(null); setUnreachable(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    go();
    return () => { cancelled = true; };
  }, [outline, liveRecs, acceptedIds, recMode]);

  if (!data) {
    return (
      <div className="tm-empty">
        {loading
          ? 'computing thread map…'
          : unreachable
            ? 'Thread map needs a backend or the mock fallback. Reload the page.'
            : 'no outline yet — add some slides to see the thread map.'}
      </div>
    );
  }

  const before = data.before;
  const after = data.after;
  const beforeStats = before.stats || {};
  const afterStats  = after.stats  || {};

  function delta(b, a) {
    const d = a - b;
    if (d === 0) return <span className="tm-delta tm-delta--zero">no change</span>;
    if (d < 0)   return <span className="tm-delta tm-delta--good">−{Math.abs(d)}</span>;
    return <span className="tm-delta tm-delta--bad">+{d}</span>;
  }

  return (
    <div className="tm">
      <div className="tm-bar">
        <div className="tm-bar__seg">
          <button
            className={`tm-pill ${vizMode === 'graph' ? 'is-active' : ''}`}
            onClick={() => setVizMode('graph')}
          >concept graph</button>
          <button
            className={`tm-pill ${vizMode === 'ribbons' ? 'is-active' : ''}`}
            onClick={() => setVizMode('ribbons')}
          >concept ribbons</button>
          {data?.before?.engine && (
            <span className={`tm-engine-badge tm-engine-badge--${data.before.engine}`}
                  title={
                    data.before.engine === 'narrative'
                      ? 'LLM reads the deck and reasons about story structure.'
                      : data.before.engine === 'semantic'
                      ? 'Sentence-transformer embeddings — synonyms link, no reasoning.'
                      : 'Bag-of-words token overlap fallback.'
                  }>
              {data.before.engine === 'narrative'
                ? '◆ narrative (LLM)'
                : data.before.engine === 'semantic'
                ? '◉ semantic'
                : '○ lexical fallback'}
            </span>
          )}
        </div>
        <div className="tm-bar__seg tm-bar__seg--right">
          <span className="tm-bar__label">compare:</span>
          <button
            className={`tm-pill ${recMode === 'potential' ? 'is-active' : ''}`}
            onClick={() => setRecMode('potential')}
            title="Show what the deck could be if every advisory were applied"
          >potential</button>
          <button
            className={`tm-pill ${recMode === 'accepted' ? 'is-active' : ''}`}
            onClick={() => setRecMode('accepted')}
            title="Show only the recommendations you've actually accepted"
          >accepted only</button>
        </div>
      </div>

      {data?.before?.narrative_spine && (
        <div className="tm-spine-card">
          <div className="tm-spine-card__label">through-line</div>
          <div className="tm-spine-card__text">{data.before.narrative_spine}</div>
          {data.before.narrative_arc && (
            <div className="tm-spine-card__arc">
              <span className="tm-spine-card__arc-k">arc</span>
              <code>{data.before.narrative_arc}</code>
            </div>
          )}
        </div>
      )}

      <div className="tm-stats">
        <span className="tm-stat">
          <span className="tm-stat__k">messiness</span>
          <span className="tm-stat__v">{beforeStats.messiness} → <strong>{afterStats.messiness}</strong></span>
        </span>
        <span className="tm-stat"><span className="tm-stat__k">orphans</span><span className="tm-stat__v">{beforeStats.orphans} → {afterStats.orphans} {delta(beforeStats.orphans, afterStats.orphans)}</span></span>
        <span className="tm-stat"><span className="tm-stat__k">hard cuts</span><span className="tm-stat__v">{beforeStats.gaps} → {afterStats.gaps} {delta(beforeStats.gaps, afterStats.gaps)}</span></span>
        <span className="tm-stat"><span className="tm-stat__k">connections</span><span className="tm-stat__v">{beforeStats.edges} → {afterStats.edges} {delta(beforeStats.edges, afterStats.edges)}</span></span>
        {data?.before?.engine !== 'narrative' && (
          <span className="tm-stat"><span className="tm-stat__k">spine</span><span className="tm-stat__v">
            {beforeStats.spine_word ? <em>{beforeStats.spine_word}</em> : <span className="tm-none">none</span>}
            {' → '}
            {afterStats.spine_word ? <em>{afterStats.spine_word}</em> : <span className="tm-none">none</span>}
          </span></span>
        )}
      </div>

      {data?.before?.graph?.tensions?.length > 0 && (
        <div className="tm-tensions">
          <div className="tm-tensions__label">tensions detected</div>
          <ul>
            {data.before.graph.tensions.map((t, i) => (
              <li key={i} className={`tm-tension tm-tension--${t.kind}`}>
                <span className="tm-tension__kind">{t.kind}</span>
                <span className="tm-tension__text">{t.issue}</span>
                <span className="tm-tension__slides">slides {t.slides.map(s => {
                  const idx = (data.before.graph.nodes.find(n => n.id === s) || {}).index;
                  return idx != null ? String(idx + 1).padStart(2, '0') : s;
                }).join(' · ')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="tm-split">
        <div className="tm-pane">
          <div className="tm-pane__title">before <span className="tm-pane__hint">as it stands</span></div>
          {vizMode === 'graph'
            ? <ConceptGraph view={before} faded={false} />
            : <ConceptRibbons view={before} faded={false} />}
        </div>
        <div className="tm-pane">
          <div className="tm-pane__title">
            after {' '}
            <span className="tm-pane__hint">{recMode === 'potential' ? `all ${data.applied.length} advisories applied` : `${data.applied.length} accepted recs applied`}</span>
          </div>
          {vizMode === 'graph'
            ? <ConceptGraph view={after} faded={data.applied.length === 0} />
            : <ConceptRibbons view={after} faded={data.applied.length === 0} />}
        </div>
      </div>
    </div>
  );
}

// ── force-directed concept graph (SVG) ──────────────────────────
function ConceptGraph({ view, faded }) {
  const W = 480, H = 360;
  const nodes = view?.graph?.nodes || [];
  const edges = view?.graph?.edges || [];
  const orphans = new Set(view?.graph?.orphans || []);
  const spine = view?.graph?.spine;
  const spineSlides = new Set(spine?.slides || []);
  const gapPairs = new Set((view?.graph?.gaps || []).map(g => g.from + '|' + g.to));

  const layout = useMemo(() => {
    if (nodes.length === 0) return [];
    const idIdx = new Map(nodes.map((n, i) => [n.id, i]));
    const N = nodes.length;
    const pts = nodes.map((_, i) => {
      const angle = (i / N) * Math.PI * 2 - Math.PI / 2;
      return { x: W/2 + Math.cos(angle) * 120, y: H/2 + Math.sin(angle) * 120 };
    });
    const k = Math.sqrt((W * H) / N);
    for (let step = 0; step < 220; step++) {
      const t = 6 * (1 - step / 220);
      const disp = pts.map(() => ({ x: 0, y: 0 }));
      for (let i = 0; i < N; i++) {
        for (let j = i + 1; j < N; j++) {
          let dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
          let d = Math.max(1, Math.sqrt(dx * dx + dy * dy));
          const force = (k * k) / d;
          dx /= d; dy /= d;
          disp[i].x += dx * force; disp[i].y += dy * force;
          disp[j].x -= dx * force; disp[j].y -= dy * force;
        }
      }
      for (const e of edges) {
        const a = idIdx.get(e.from), b = idIdx.get(e.to);
        if (a == null || b == null) continue;
        let dx = pts[a].x - pts[b].x, dy = pts[a].y - pts[b].y;
        let d = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        const force = (d * d) / k * (0.4 + 0.15 * e.weight);
        dx /= d; dy /= d;
        disp[a].x -= dx * force; disp[a].y -= dy * force;
        disp[b].x += dx * force; disp[b].y += dy * force;
      }
      for (let i = 0; i < N; i++) {
        const dx = disp[i].x, dy = disp[i].y;
        const d = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        pts[i].x += (dx / d) * Math.min(d, t);
        pts[i].y += (dy / d) * Math.min(d, t);
        pts[i].x += (W/2 - pts[i].x) * 0.005;
        pts[i].y += (H/2 - pts[i].y) * 0.005;
        const pad = 28;
        pts[i].x = Math.max(pad, Math.min(W - pad, pts[i].x));
        pts[i].y = Math.max(pad, Math.min(H - pad, pts[i].y));
      }
    }
    return pts;
  }, [nodes.length, JSON.stringify(edges.map(e => [e.from, e.to, e.weight]))]);

  if (nodes.length === 0) {
    return <div className="tm-empty">no slides yet</div>;
  }

  const maxW = Math.max(1, ...edges.map(e => e.weight));

  return (
    <svg className={`tm-svg ${faded ? 'is-faded' : ''}`} viewBox={`0 0 ${W} ${H}`}>
      {edges.map((e, idx) => {
        const a = nodes.findIndex(n => n.id === e.from);
        const b = nodes.findIndex(n => n.id === e.to);
        if (a < 0 || b < 0) return null;
        const isGap = gapPairs.has(e.from + '|' + e.to) || gapPairs.has(e.to + '|' + e.from);
        if (isGap) return null;
        const strokeW = 0.6 + (e.weight / maxW) * 2.2;
        return (
          <line
            key={'e' + idx}
            className={`tm-edge ${e.adjacent ? 'tm-edge--adjacent' : ''}`}
            x1={layout[a].x} y1={layout[a].y}
            x2={layout[b].x} y2={layout[b].y}
            strokeWidth={strokeW}
          >
            <title>{e.shared.join(', ')}</title>
          </line>
        );
      })}
      {(view?.graph?.gaps || []).map((g, idx) => {
        const a = nodes.findIndex(n => n.id === g.from);
        const b = nodes.findIndex(n => n.id === g.to);
        if (a < 0 || b < 0) return null;
        return (
          <line
            key={'gap' + idx}
            className="tm-gap"
            x1={layout[a].x} y1={layout[a].y}
            x2={layout[b].x} y2={layout[b].y}
          >
            <title>hard cut between adjacent slides — no shared concept</title>
          </line>
        );
      })}
      {nodes.map((n, i) => {
        const isOrphan = orphans.has(n.id);
        const isSpine = spineSlides.has(n.id);
        return (
          <g
            key={n.id}
            className={`tm-node ${isOrphan ? 'is-orphan' : ''} ${isSpine ? 'is-spine' : ''}`}
            transform={`translate(${layout[i].x},${layout[i].y})`}
          >
            <circle r={isOrphan ? 10 : 12} />
            <text textAnchor="middle" dy={4} fontSize="11">{String(n.index + 1).padStart(2, '0')}</text>
            <text className="tm-node__title" textAnchor="middle" y={26} fontSize="10">
              {n.title.length > 22 ? n.title.slice(0, 21) + '…' : n.title}
            </text>
            <title>{n.title}{isOrphan ? '  (orphan — shares nothing)' : ''}{isSpine ? '  (carries spine word)' : ''}</title>
          </g>
        );
      })}
      {spine && (
        <g className="tm-spine-tag" transform={`translate(${W - 8}, 16)`}>
          <text textAnchor="end" fontSize="11">spine · <tspan className="tm-spine-tag__word">{spine.word}</tspan></text>
        </g>
      )}
    </svg>
  );
}

// ── concept ribbons (Sankey-style flow) ─────────────────────────
function ConceptRibbons({ view, faded }) {
  const W = 480, H = 360;
  const nodes = view?.graph?.nodes || [];
  const ribbons = view?.ribbons || [];
  if (nodes.length === 0) return <div className="tm-empty">no slides yet</div>;

  const padX = 36, padY = 30;
  const colW = (W - padX * 2) / Math.max(1, nodes.length - 1 || 1);
  const slideY = padY;
  const slideH = 36;
  const flowTop = slideY + slideH + 18;
  const flowBottom = H - padY - 18;
  const flowH = flowBottom - flowTop;

  const ribbonsToDraw = ribbons.slice(0, 8);
  const lanes = ribbonsToDraw.length;
  const laneH = flowH / Math.max(1, lanes);

  const palette = ['#4ec5ff', '#ffd166', '#a3e635', '#f97070', '#c084fc', '#22d3ee', '#fb923c', '#34d399'];

  function nodeX(i) {
    if (nodes.length === 1) return W / 2;
    return padX + i * colW;
  }

  return (
    <svg className={`tm-svg tm-svg--ribbons ${faded ? 'is-faded' : ''}`} viewBox={`0 0 ${W} ${H}`}>
      {nodes.map((n, i) => (
        <g key={n.id} transform={`translate(${nodeX(i) - 30},${slideY})`}>
          <rect className="tm-slide-tile" width={60} height={slideH} rx={4} />
          <text x={30} y={16} textAnchor="middle" fontSize="11">{String(n.index + 1).padStart(2, '0')}</text>
          <text className="tm-slide-tile__title" x={30} y={30} textAnchor="middle" fontSize="9">
            {n.title.length > 14 ? n.title.slice(0, 13) + '…' : n.title}
          </text>
        </g>
      ))}
      {ribbonsToDraw.map((r, ri) => {
        const color = r.is_spine ? '#ffd166' : palette[ri % palette.length];
        const y = flowTop + laneH * ri + laneH / 2;
        const slides = r.slides;
        const segs = [];
        for (let i = 0; i < slides.length - 1; i++) {
          const a = slides[i], b = slides[i + 1];
          segs.push({ a, b, broken: (b - a) > 1 });
        }
        return (
          <g key={r.token}>
            {segs.map((seg, si) => {
              const x1 = nodeX(seg.a), x2 = nodeX(seg.b);
              const mid = (x1 + x2) / 2;
              const d = `M${x1},${y} C${mid},${y} ${mid},${y} ${x2},${y}`;
              return (
                <path
                  key={si}
                  d={d}
                  className={`tm-ribbon ${seg.broken ? 'is-broken' : ''} ${r.is_spine ? 'is-spine' : ''}`}
                  stroke={color}
                  strokeWidth={r.is_spine ? 4 : 2 + r.weight * 0.35}
                  fill="none"
                  strokeLinecap="round"
                />
              );
            })}
            {slides.map(si => (
              <circle key={si} cx={nodeX(si)} cy={y} r={r.is_spine ? 4 : 3} fill={color} />
            ))}
            <text x={padX - 10} y={y + 3} textAnchor="end" fontSize="10"
                  className={`tm-ribbon-label ${r.is_spine ? 'is-spine' : ''}`}>
              {r.token}{r.broken ? ' ·' : ''}
            </text>
          </g>
        );
      })}
      {ribbonsToDraw.length === 0 && (
        <text x={W/2} y={H/2} textAnchor="middle" fontSize="12" className="tm-empty-text">
          no recurring concepts — every slide is its own island
        </text>
      )}
    </svg>
  );
}

function StoryboardPage({ outline, recs, dismissedRecs, allowMulti, mode, audience, settingsStale, reextracting, onReextract, onEdit, onAdd, onRemove, onMove, onAcceptRec, onDismissRec, onContinue, onBack, acceptedIds }) {
  const liveRecs = recs.filter(r => !dismissedRecs.has(r.id));
  // Split-screen layout (no tabs): storyboard fills the left column; the
  // right column stacks thread map on top of recommendations so users
  // can see the structural picture and the suggested moves together.
  return (
    <div className="sm">
      <div className="sm-inner">
        <div>
          <div className="sm-eyebrow">step three  ·  the storyboard</div>
          <h1 className="sm-title">
            Here’s the <em>shape of the deck</em>.
          </h1>
          <p className="sm-sub">
            Edit titles, swap messages, reorder. The thread map on the right
            visualizes the deck's narrative; the recommendations propose moves.
            When it reads right, take it to the workbench.
          </p>
        </div>

        {settingsStale && (
          <div className="sb-stale">
            <div className="sb-stale__msg">
              Mode / audience changed since extraction
              <span className="sb-stale__detail"> · current: <strong>{mode}</strong> · <strong>{audience}</strong></span>
            </div>
            <button
              className="sb-stale__btn"
              onClick={onReextract}
              disabled={reextracting}
            >
              {reextracting ? 'rebuilding…' : 're-extract'}
            </button>
          </div>
        )}

        <div className="sb-grid">
          <div className="sb-board">
            <div className="sm-board__head">
              <h2 className="sm-board__title">
                Storyboard  <em>·  {outline.length} slide{outline.length === 1 ? '' : 's'}</em>
              </h2>
              <span className="sm-board__hint">edit  ·  reorder  ·  add or trim before continuing</span>
            </div>
            <StoryboardCanvas
              outline={outline}
              allowMulti={allowMulti}
              onEdit={onEdit}
              onAdd={onAdd}
              onRemove={onRemove}
              onMove={onMove}
            />
          </div>

          <aside className="sb-side">
            <div className="sb-side__head">
              <span className="sb-side__title">Recommendations</span>
              <span className="sb-side__hint">{liveRecs.length === 0 ? 'all clear' : `${liveRecs.length} suggestion${liveRecs.length === 1 ? '' : 's'}`}</span>
            </div>
            {liveRecs.length === 0 ? (
              <div className="sb-side__empty">
                No suggestions \u2014 the storyboard reads cleanly. You can still tune it manually, or move on.
              </div>
            ) : (() => {
              const contentRecs  = liveRecs.filter(r => (r.track || 'content') === 'content');
              const semanticRecs = liveRecs.filter(r => r.track === 'semantic');
              function renderRec(rec) {
                const icon = rec.kind === 'spine' ? '◆'
                  : rec.kind === 'bridge' ? '⌒'
                  : rec.kind === 'gap' ? '⎯'
                  : rec.kind === 'orphan' ? '◌'
                  : rec.kind === 'word-swap' ? '⇄'
                  : rec.kind === 'hedge' ? '✂'
                  : rec.kind === 'tone' ? '♪'
                  : rec.kind === 'second-person' ? '☞'
                  : '→';
                // Tone hints are FYI — they describe how the engine is
                // tuning the room. Nothing to apply, just show + dismiss.
                const isInfoOnly = rec.kind === 'tone';
                return (
                  <div className={`sm-rec sb-rec ${isInfoOnly ? 'is-info' : ''} ${rec.kind ? 'sb-rec--' + rec.kind : ''}`} key={rec.id}>
                    <span className="sm-rec__icon">{icon}</span>
                    <span className="sm-rec__text">{rec.text}</span>
                    <span className="sm-rec__actions">
                      {isInfoOnly ? (
                        <button className="sm-rec__reject" onClick={() => onDismissRec(rec.id)}>dismiss</button>
                      ) : (
                        <>
                          <button className="sm-rec__accept" onClick={() => onAcceptRec(rec)}>apply</button>
                          <button className="sm-rec__reject" onClick={() => onDismissRec(rec.id)}>reject</button>
                        </>
                      )}
                    </span>
                  </div>
                );
              }
              return (
                <>
                  {contentRecs.length > 0 && (
                    <div className="sb-rec-group">
                      <div className="sb-rec-group__head">
                        <span className="sb-rec-group__label">Content</span>
                        <span className="sb-rec-group__hint">structural moves</span>
                      </div>
                      <div className="sm-recs__list">{contentRecs.map(renderRec)}</div>
                    </div>
                  )}
                  {semanticRecs.length > 0 && (
                    <div className="sb-rec-group">
                      <div className="sb-rec-group__head">
                        <span className="sb-rec-group__label">Semantic</span>
                        <span className="sb-rec-group__hint">word + tone per room</span>
                      </div>
                      <div className="sm-recs__list">{semanticRecs.map(renderRec)}</div>
                    </div>
                  )}
                </>
              );
            })()}
          </aside>

          <section className="sb-thread-panel">
            <div className="sb-thread-panel__head">
              <span className="sb-thread-panel__title">Thread map</span>
              <span className="sb-thread-panel__hint">see the messiness</span>
            </div>
            <ThreadMapView
              outline={outline}
              recs={recs}
              dismissedRecs={dismissedRecs}
              acceptedIds={acceptedIds || new Set()}
            />
          </section>
        </div>

        <div className="sm-foot">
          <button className="sb-back" onClick={onBack}>← back to story map</button>
          <span className="sm-foot__meta">storyboard ready  ·  next: tune palette, layout, taste</span>
          <button className="sm-continue" onClick={onContinue}>
            take it to the workbench <span className="arrow">→</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// Critique page (adversarial commentary)
// ───────────────────────────────────────────────────────────────

function CritiqueCard({ item }) {
  const sev = item.sev || 'med';
  return (
    <div className={`cq-card cq-card--${item.kind} cq-card--sev-${sev}`}>
      <div className="cq-card__head">
        <span className={`cq-card__sev cq-card__sev--${sev}`}>{sev}</span>
        <span className="cq-card__src">{item.source}</span>
      </div>
      <p className="cq-card__text">{item.text}</p>
    </div>
  );
}

function CritiquePage({ critique, audience, onBack, onExport, loading }) {
  if (!critique) {
    return (
      <div className="sm">
        <div className="sm-inner">
          <div className="cq-loading">
            <span className="thinking-dot" /> rehearsing the room\u2026
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="sm">
      <div className="sm-inner">
        <div>
          <div className="sm-eyebrow">step five  \u00b7  adversarial commentary</div>
          <h1 className="sm-title">
            Through the eyes of <em>{critique.voice}</em>.
          </h1>
          <p className="sm-sub">
            Before you walk in, here\u2019s what your audience will likely push on and the questions
            you should already have answers to.
          </p>
        </div>

        <div className="cq-grid">
          <section className="cq-col">
            <h2 className="cq-col__head">What they\u2019ll challenge</h2>
            <div className="cq-list">
              {critique.criticisms.map(c => <CritiqueCard key={c.id} item={c} />)}
            </div>
          </section>
          <section className="cq-col">
            <h2 className="cq-col__head">What they\u2019ll ask</h2>
            <div className="cq-list">
              {critique.questions.map(q => <CritiqueCard key={q.id} item={q} />)}
            </div>
          </section>
        </div>

        <div className="sm-foot">
          <button className="sb-back" onClick={onBack}>\u2190 back to workbench</button>
          <span className="sm-foot__meta">pre-mortem complete  \u00b7  ready to ship</span>
          <div className="cq-export">
            <button className="cq-export__btn" onClick={() => onExport('json')}>save .json</button>
            <button className="cq-export__btn cq-export__btn--primary" onClick={() => onExport('pdf')}>save .pdf \u2192</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// App
// ───────────────────────────────────────────────────────────────

// Read mode/audience from sessionStorage so /setup can hand off picks
// without forcing the user to re-select on /workbench. Falls back to
// defaults silently if absent or malformed.
function readSetupHydration() {
  try {
    const raw = sessionStorage.getItem('pptgpt.setup');
    if (!raw) return null;
    const s = JSON.parse(raw);
    return {
      modeKey: typeof s.modeKey === 'string' ? s.modeKey : null,
      audienceKey: typeof s.audienceKey === 'string' ? s.audienceKey : null,
    };
  } catch (_) {
    return null;
  }
}

function App() {
  const setupHydration = readSetupHydration();
  const [phase, setPhase] = useState('storymap');
  const [mode, setMode] = useState(() => setupHydration?.modeKey || 'draft');
  const [audience, setAudience] = useState(() => setupHydration?.audienceKey || 'exec');
  const [template, setTemplate] = useState('clean');
  const [outlines, setOutlines] = useState(() => structuredClone(DEFAULT_OUTLINE));
  const [storyMapKey, setStoryMapKey] = useState(0);

  // Storyboard-phase state — lifted out of StoryMap so the storyboard page
  // can edit independently.
  const [extractedOutline, setExtractedOutline] = useState(null);
  const [extractedRecs, setExtractedRecs] = useState([]);
  const [dismissedRecs, setDismissedRecs] = useState(new Set());
  // Accepted recs power the Thread map "accepted only" comparison.
  // Grows as the user clicks "accept" in the suggestions side panel.
  const [acceptedRecIds, setAcceptedRecIds] = useState(new Set());
  // Settings signature captured at the last extraction. When the current
  // mode/audience differs we render a "settings changed → re-extract" banner
  // on the storyboard so the user knows the outline is stale.
  const [extractedSignature, setExtractedSignature] = useState(null);
  // Cached input the last extraction ran on, so the re-extract button has
  // something to feed back to extractStoryboard without making the user
  // re-paste / re-upload.
  const [lastExtractInput, setLastExtractInput] = useState(null);
  const [reextracting, setReextracting] = useState(false);

  const outline = outlines[mode];

  const [selectedSlideId, setSelectedSlideId] = useState(outline[0].id);

  // Answers and removedIds are per-mode (questions are about the overall
  // design; the same answers apply to every slide in a deck)
  const [answersByMode, setAnswersByMode] = useState({});
  const answers = answersByMode[mode] || {};
  const [removedByMode, setRemovedByMode] = useState({});
  const removedIds = removedByMode[mode] || new Set();

  const [responseByMode, setResponseByMode] = useState({});
  const response = responseByMode[mode] || null;

  const [loading, setLoading] = useState(false);
  const [selectedDirKey, setSelectedDirKey] = useState({});
  const dirKey = selectedDirKey[mode];

  const [plotParams, setPlotParams] = useState({});

  // Debounce outline edits before refetch
  const debouncedOutline = useDebounced(outline, 320);
  const debouncedAnswers = useDebounced(answers, 200);

  useEffect(() => {
    if (phase !== 'workbench') return;
    let cancelled = false;
    setLoading(true);
    window.mockBackend({
      mode,
      audience,
      outline: debouncedOutline,
      rawContent: outlineToRaw(debouncedOutline),
      answers: debouncedAnswers,
      wantsLiveDirections: true,
    }).then(res => {
      if (cancelled) return;
      setResponseByMode(prev => ({ ...prev, [mode]: res }));
      setLoading(false);
      const has = res.directions.find(d => d.key === dirKey);
      if (!has && res.directions.length > 0) {
        setSelectedDirKey(prev => ({ ...prev, [mode]: res.directions[0].key }));
      }
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, mode, audience, JSON.stringify(debouncedOutline), JSON.stringify(debouncedAnswers)]);

  function editSlide(slideId, patch) {
    setOutlines(prev => ({
      ...prev,
      [mode]: prev[mode].map(s => s.id === slideId ? { ...s, ...patch } : s),
    }));
  }
  function addSlide() {
    setOutlines(prev => ({
      ...prev,
      [mode]: [...prev[mode], { id: uid('s'), title: '', messages: ['', '', ''] }],
    }));
  }
  function removeSlide(id) {
    setOutlines(prev => {
      const next = prev[mode].filter(s => s.id !== id);
      if (next.length === 0) next.push({ id: uid('s'), title: '', messages: ['', '', ''] });
      return { ...prev, [mode]: next };
    });
    if (selectedSlideId === id) {
      setSelectedSlideId(outline[0].id);
    }
  }

  function answerQuestion(q, option) {
    setAnswersByMode(prev => {
      const cur = prev[mode] || {};
      if (cur[q.id]) return prev;
      return { ...prev, [mode]: { ...cur, [q.id]: option } };
    });
    setTimeout(() => {
      setRemovedByMode(prev => {
        const cur = prev[mode] || new Set();
        if (cur.has(q.id)) return prev;
        const nx = new Set(cur);
        nx.add(q.id);
        return { ...prev, [mode]: nx };
      });
    }, 760);
  }

  function reset() {
    // Drop the /setup handoff so a fresh session doesn't silently re-apply
    // stale picks the next time the user revisits.
    try { sessionStorage.removeItem('pptgpt.setup'); } catch (_) {}
    setPhase('storymap');
    setMode('draft');
    setAudience('exec');
    setTemplate('clean');
    setOutlines(structuredClone(DEFAULT_OUTLINE));
    setExtractedOutline(null);
    setExtractedRecs([]);
    setDismissedRecs(new Set());
    setAcceptedRecIds(new Set());
    setExtractedSignature(null);
    setLastExtractInput(null);
    setAnswersByMode({});
    setRemovedByMode({});
    setResponseByMode({});
    setSelectedDirKey({});
    setPlotParams({});
    setStoryMapKey(k => k + 1);
  }

  function onExtracted({ outline, recommendations, sourceFile, sourceText, targetCount }) {
    setExtractedOutline(outline);
    setExtractedRecs(recommendations || []);
    setDismissedRecs(new Set());
    setAcceptedRecIds(new Set());
    setExtractedSignature(JSON.stringify({ mode, audience, targetCount: targetCount || null }));
    setLastExtractInput({ text: sourceText || '', targetCount: targetCount || null });
    setPhase('storyboard');
  }

  // Re-run extraction with the CURRENT mode/audience settings using the
  // last input. Triggered by the "settings changed" banner on the
  // storyboard. Mutates the same state path as the initial extraction.
  async function reextractWithCurrentSettings() {
    if (!lastExtractInput) return;
    setReextracting(true);
    try {
      const res = await window.extractStoryboard({
        text: lastExtractInput.text,
        mode,
        audience,
        targetCount: lastExtractInput.targetCount || (mode === 'draft' ? 1 : 5),
      });
      setExtractedOutline(res.outline);
      setExtractedRecs(res.recommendations || []);
      setDismissedRecs(new Set());
      setAcceptedRecIds(new Set());
      setExtractedSignature(JSON.stringify({ mode, audience, targetCount: lastExtractInput.targetCount }));
    } catch (_) {
      // swallow — banner stays visible so the user can retry
    } finally {
      setReextracting(false);
    }
  }

  const currentSignature = JSON.stringify({
    mode, audience,
    targetCount: lastExtractInput?.targetCount || null,
  });
  const settingsStale = !!extractedSignature && extractedSignature !== currentSignature;

  // ── Storyboard-phase editing handlers ────────────────────────
  function sbEdit(id, patch) {
    setExtractedOutline(prev => (prev || []).map(s => s.id === id ? { ...s, ...patch } : s));
  }
  function sbAdd() {
    setExtractedOutline(prev => [...(prev || []), { id: uid('s'), title: '', messages: ['', '', ''], bumper: '' }]);
  }
  function sbRemove(id) {
    setExtractedOutline(prev => {
      const next = (prev || []).filter(s => s.id !== id);
      return next.length === 0 ? [{ id: uid('s'), title: '', messages: ['', '', ''], bumper: '' }] : next;
    });
  }
  function sbMove(id, dir) {
    setExtractedOutline(prev => {
      const arr = prev || [];
      const i = arr.findIndex(s => s.id === id);
      if (i < 0) return arr;
      const j = i + dir;
      if (j < 0 || j >= arr.length) return arr;
      const next = [...arr];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }
  function sbDismissRec(id) {
    setDismissedRecs(prev => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }
  function _fieldGet(slide, field) {
    if (field === 'title') return slide.title || '';
    if (field === 'bumper') return slide.bumper || '';
    if (field && field.startsWith('msg')) {
      const idx = parseInt(field.slice(3), 10) - 1;
      return (slide.messages || [])[idx] || '';
    }
    return '';
  }
  function _fieldSet(slide, field, value) {
    if (field === 'title')  return { ...slide, title: value };
    if (field === 'bumper') return { ...slide, bumper: value };
    if (field && field.startsWith('msg')) {
      const idx = parseInt(field.slice(3), 10) - 1;
      const msgs = [...(slide.messages || ['', '', ''])];
      msgs[idx] = value;
      return { ...slide, messages: msgs };
    }
    return slide;
  }
  function _hasKeyword(text, word) {
    if (!word) return false;
    return new RegExp(`\\b${word}\\b`, 'i').test(text || '');
  }
  // Deterministic per-rec-kind mutations. A rec leaves the panel ONLY if
  // it produced a real edit to the outline (or the user explicitly
  // rejected it via sbDismissRec). Gemma can replace these stubs later
  // by routing kind + slide context through /api/apply_suggestion.
  function sbAcceptRec(rec) {
    let mutated = false;
    setExtractedOutline(prev => {
      let next = [...(prev || [])];
      // ── content track ─────────────────────────────────────
      if (rec.kind === 'merge' && rec.slideIds && rec.slideIds.length >= 2) {
        const [a, b] = rec.slideIds;
        const ai = next.findIndex(s => s.id === a);
        const bi = next.findIndex(s => s.id === b);
        if (ai > -1 && bi > -1 && ai !== bi) {
          const aSlide = next[ai], bSlide = next[bi];
          const seen = new Set();
          const merged = [...aSlide.messages, ...bSlide.messages]
            .map(x => (x || '').trim())
            .filter(x => { if (!x || seen.has(x.toLowerCase())) return false; seen.add(x.toLowerCase()); return true; })
            .slice(0, 3);
          while (merged.length < 3) merged.push('');
          next[ai] = { id: aSlide.id, title: aSlide.title, messages: merged };
          next.splice(bi, 1);
          mutated = true;
        }
      } else if (rec.kind === 'add-setup') {
        next.unshift({ id: uid('s'), title: 'Setup', messages: ['Context for what follows', '', ''], bumper: 'And here\u2019s what changed.' });
        mutated = true;
      } else if (rec.kind === 'trim' && rec.slideIds) {
        next = next.filter(s => !rec.slideIds.includes(s.id));
        mutated = true;
      } else if (rec.kind === 'thin') {
        next = next.map(s => {
          const kept = s.messages.filter(Boolean).slice(0, 2);
          while (kept.length < 3) kept.push('');
          return { ...s, messages: kept };
        });
        mutated = true;
      } else if (rec.kind === 'add-actions') {
        next.push({ id: uid('s'), title: 'Next steps', messages: ['Action  ·  owner  ·  by when', '', ''], bumper: '' });
        mutated = true;
      } else if (rec.kind === 'spine') {
        // Promote the spine word into every title that doesn't already
        // reference it. Word is parsed from id "spine-<word>".
        const word = (rec.id || '').replace(/^spine-/, '');
        if (word) {
          next = next.map(s => {
            if (_hasKeyword(s.title, word)) return s;
            const titled = (s.title || '').trim();
            const prefixed = titled
              ? `${word.charAt(0).toUpperCase() + word.slice(1)} · ${titled}`
              : word;
            mutated = true;
            return { ...s, title: prefixed };
          });
        }
      } else if (rec.kind === 'gap') {
        // Add a bridging bumper to slide i naming a concept the next
        // slide carries. id is "gap-<i>".
        const i = parseInt((rec.id || '').replace(/^gap-/, ''), 10);
        if (Number.isInteger(i) && next[i] && next[i + 1]) {
          const nextSlide = next[i + 1];
          const seed = (nextSlide.title || (nextSlide.messages || [])[0] || '')
            .split(/\s+/).slice(0, 4).join(' ');
          if (seed) {
            next[i] = { ...next[i], bumper: `Next: ${seed}.` };
            mutated = true;
          }
        }
      } else if (rec.kind === 'bridge') {
        // Weave the bridging token into the middle slide's first message.
        // id is "bridge-<i>"; the token is quoted in rec.text.
        const i = parseInt((rec.id || '').replace(/^bridge-/, ''), 10);
        const tokenMatch = (rec.text || '').match(/share "([^"]+)"/);
        const token = tokenMatch ? tokenMatch[1] : null;
        if (token && Number.isInteger(i) && next[i + 1]) {
          const mid = next[i + 1];
          const msgs = [...(mid.messages || ['', '', ''])];
          if (!_hasKeyword((msgs[0] || '') + ' ' + (mid.title || ''), token)) {
            msgs[0] = msgs[0]
              ? `${msgs[0].replace(/\.$/, '')} — ${token}.`
              : `Carries ${token} forward.`;
            next[i + 1] = { ...mid, messages: msgs };
            mutated = true;
          }
        }
      } else if (rec.kind === 'orphan') {
        // Bring the orphan back by adding a phrase from a neighbor to
        // its first empty message slot. id is "orphan-<slideId>".
        const orphanId = (rec.id || '').replace(/^orphan-/, '');
        const oi = next.findIndex(s => s.id === orphanId);
        if (oi >= 0) {
          const neighbor = next[oi + 1] || next[oi - 1];
          const hook = neighbor && (neighbor.title || (neighbor.messages || [])[0] || '')
            .split(/\s+/).slice(0, 3).join(' ');
          if (hook) {
            const msgs = [...((next[oi].messages) || ['', '', ''])];
            const slot = msgs.findIndex(m => !m);
            if (slot >= 0) {
              msgs[slot] = `Ties to: ${hook}.`;
              next[oi] = { ...next[oi], messages: msgs };
              mutated = true;
            }
          }
        }
      // ── semantic track ────────────────────────────────────
      } else if (rec.kind === 'word-swap') {
        const slide = next[rec.slideIdx];
        if (slide && rec.field && rec.badWord && rec.goodWord) {
          const cur = _fieldGet(slide, rec.field);
          const swapped = cur.replace(new RegExp(rec.badWord, 'gi'), (m) =>
            m[0] === m[0].toUpperCase()
              ? rec.goodWord.charAt(0).toUpperCase() + rec.goodWord.slice(1)
              : rec.goodWord
          );
          if (swapped !== cur) {
            next[rec.slideIdx] = _fieldSet(slide, rec.field, swapped);
            mutated = true;
          }
        }
      } else if (rec.kind === 'hedge') {
        const slide = next[rec.slideIdx];
        if (slide && rec.field && rec.hedgeWord) {
          const cur = _fieldGet(slide, rec.field);
          const stripped = cur
            .replace(new RegExp(`\\s*\\b${rec.hedgeWord}\\b\\s*`, 'gi'), ' ')
            .replace(/\s{2,}/g, ' ')
            .trim();
          if (stripped !== cur) {
            next[rec.slideIdx] = _fieldSet(slide, rec.field, stripped);
            mutated = true;
          }
        }
      } else if (rec.kind === 'second-person') {
        const slide = next[rec.slideIdx];
        if (slide && rec.field) {
          const cur = _fieldGet(slide, rec.field);
          if (cur && !/\byou\b|\byour\b/i.test(cur)) {
            const youified = /^[A-Z]/.test(cur)
              ? `You ${cur.charAt(0).toLowerCase() + cur.slice(1)}`
              : `You ${cur}`;
            next[rec.slideIdx] = _fieldSet(slide, rec.field, youified);
            mutated = true;
          }
        }
      }
      return next.length === 0 ? [{ id: uid('s'), title: '', messages: ['', '', ''], bumper: '' }] : next;
    });
    if (!mutated) {
      // No-op rec (kind=tone, or already-applied content): do NOT
      // record acceptance or dismiss it — the user must explicitly
      // reject to clear it. This enforces the gate: a rec leaves the
      // panel only when the storyboard actually changes.
      return;
    }
    setAcceptedRecIds(prev => {
      const next = new Set(prev);
      next.add(rec.id);
      return next;
    });
    sbDismissRec(rec.id);
  }

  function continueToWorkbench() {
    if (extractedOutline && extractedOutline.length > 0) {
      setOutlines(prev => ({ ...prev, [mode]: extractedOutline }));
      setSelectedSlideId(extractedOutline[0].id);
    }
    setPhase('workbench');
  }

  function backToStoryMap() {
    setPhase('storymap');
  }

  // ── Critique phase ───────────────────────────────────────────
  const [critique, setCritique] = useState(null);
  const [critiqueLoading, setCritiqueLoading] = useState(false);

  async function goToCritique() {
    setPhase('critique');
    setCritiqueLoading(true);
    try {
      const res = await window.generateCritique({
        mode, audience,
        outline: outlines[mode],
      });
      setCritique(res);
    } catch (e) { /* ignore */ }
    setCritiqueLoading(false);
  }
  function backToWorkbench() {
    setPhase('workbench');
  }

  // ── Export ──────────────────────────────────────────────────
  function onExport(kind) {
    if (kind === 'json') {
      const data = {
        version: 1,
        exportedAt: new Date().toISOString(),
        mode, audience, template,
        outline: outlines[mode],
        answers: answersByMode[mode] || {},
        plotParams,
        directions: responseByMode[mode] ? responseByMode[mode].directions : [],
        critique,
      };
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pptgpt-${mode}-${Date.now()}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } else if (kind === 'pdf') {
      window.print();
    }
  }

  function setPlotParam(name, value) {
    setPlotParams(prev => ({ ...prev, [name]: value }));
  }
  function resetPlotParams() {
    setPlotParams({});
  }

  // When mode or direction changes, reset plotParams so we get fresh defaults
  useEffect(() => { setPlotParams({}); }, [mode, dirKey]);

  // When mode changes, point selectedSlideId at first slide
  useEffect(() => {
    const o = outlines[mode];
    if (o && o.length && !o.find(s => s.id === selectedSlideId)) {
      setSelectedSlideId(o[0].id);
    }
  }, [mode, outlines, selectedSlideId]);

  const allowMultiSlide = mode === 'condense';

  return (
    <div className={`wb ${mode === 'visualize' ? 'is-visualize' : ''}`}>
      <WBHeader
        mode={mode}
        onModeChange={setMode}
        loading={loading}
        onReset={reset}
        phase={phase}
        onBackToStoryMap={backToStoryMap}
      />
      {phase === 'storymap' && (
        <StoryMap
          key={storyMapKey}
          mode={mode}
          onModeChange={setMode}
          audience={audience}
          onAudienceChange={setAudience}
          template={template}
          onTemplateChange={setTemplate}
          loading={loading}
          onExtracted={onExtracted}
        />
      )}
      {phase === 'storyboard' && extractedOutline && (
        <StoryboardPage
          outline={extractedOutline}
          recs={extractedRecs}
          dismissedRecs={dismissedRecs}
          acceptedIds={acceptedRecIds}
          allowMulti={mode === 'condense'}
          mode={mode}
          audience={audience}
          settingsStale={settingsStale}
          reextracting={reextracting}
          onReextract={reextractWithCurrentSettings}
          onEdit={sbEdit}
          onAdd={sbAdd}
          onRemove={sbRemove}
          onMove={sbMove}
          onAcceptRec={sbAcceptRec}
          onDismissRec={sbDismissRec}
          onContinue={continueToWorkbench}
          onBack={backToStoryMap}
        />
      )}
      {phase === 'workbench' && (
        <div className="wb-grid">
          <OutlinePanel
            outline={outline}
            selectedId={selectedSlideId}
            onSelect={setSelectedSlideId}
            onEdit={editSlide}
            onAdd={addSlide}
            onRemove={removeSlide}
            allowMultiSlide={allowMultiSlide}
          />
          <CenterCanvas
            response={response}
            answers={answers}
            removedIds={removedIds}
            onAnswer={answerQuestion}
          />
          <ResultPanel
            response={response}
            selectedKey={dirKey}
            onSelectKey={(k) => setSelectedDirKey(prev => ({ ...prev, [mode]: k }))}
            plotParams={plotParams}
            onPlotParamChange={setPlotParam}
            onPlotParamReset={resetPlotParams}
            onGoToCritique={goToCritique}
          />
        </div>
      )}
      {phase === 'critique' && (
        <CritiquePage
          critique={critique}
          audience={audience}
          loading={critiqueLoading}
          onBack={backToWorkbench}
          onExport={onExport}
        />
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
