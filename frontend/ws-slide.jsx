/* ============================================================
   ws-slide.jsx — slide data model, renderer, generation
   ------------------------------------------------------------
   A "deck" is one live object shared across all three features.
   Slides are simple content objects; SlideCard renders them at
   a fixed 720×405 design size (parent scales via transform).
   Generation uses window.claude.complete with a robust canned
   fallback so the prototype always works.
   ============================================================ */

const SLIDE_W = 720, SLIDE_H = 405;

/* ── palettes = the three "directions", folded into chat ──── */
const PALETTES = {
  warm:  { key:'warm',  label:'Warm',  swatch:'#0E5B36',
    bg:'#FFFCF4', ink:'#11120E', sub:'#3D3F38', mute:'#807C6E', accent:'#0E5B36', spark:'#E26A2C', rule:'#E7E1CF' },
  bold:  { key:'bold',  label:'Bold',  swatch:'#11120E',
    bg:'#12130F', ink:'#FAF7EF', sub:'#CFC9B7', mute:'#8F8A79', accent:'#E9852F', spark:'#E9852F', rule:'rgba(255,255,255,0.14)' },
  clean: { key:'clean', label:'Clean', swatch:'#FFFFFF',
    bg:'#FFFFFF', ink:'#11120E', sub:'#3D3F38', mute:'#9A9788', accent:'#0E5B36', spark:'#0E5B36', rule:'#ECEAE2' },
};

const AUDIENCES = [
  { key:'exec',     label:'Exec',       color:'#11120E', tone:'numbers-forward, sparse, decision-oriented; the hero number leads and a decision anchors the lower right' },
  { key:'customer', label:'Customer',   color:'#C4633F', tone:'narrative-first, warmer, a little more visual, ends with a single ask' },
  { key:'conf',     label:'Conference', color:'#0E5B36', tone:'one idea, big typography, takeaway-first, minimal supporting text' },
  { key:'standup',  label:'Standup',    color:'#C99A2E', tone:'dense and practical, action items phrased with owners in mind' },
];

/* ── feature metadata ─────────────────────────────────────── */
const FEATURES = {
  create: {
    key:'create', name:'Create', sub:'a thought → a slide',
    initEyebrow:'Draft one clean slide',
    initH:['Type your ', 'idea', ''],
    initP:'Type a result, a takeaway, or a messy list. pptgpt drafts one slide that lands the point.',
    placeholder:'We beat Q3 plan by 14% — net retention 118%, churn down to 1.8%…',
    samples:[
      'We beat Q3 revenue plan by 14% — retention 118%, churn 1.8%',
      'Users abandon onboarding at step 4 — three fixes',
      'Why we should double down on enterprise',
    ],
  },
  data: {
    key:'data', name:'Data', sub:'upload → a chart',
    initEyebrow:'Visualize · Synthesize',
    initH:['Add your ', 'data', ''],
    initP:'Drop a spreadsheet, paste numbers, or type a formula. pptgpt turns it into a clean chart or plot on one slide.',
    placeholder:'Q1 32, Q2 38, Q3 42, Q4 45 — revenue in $M…',
    samples:[
      'Q1 32, Q2 38, Q3 42, Q4 45 — revenue in $M',
      'Damped oscillator: x(t)=A·e^(−γt)·cos(ωt)',
      'Churn by month: Jan 2.6, Feb 2.3, Mar 2.0, Apr 1.8',
    ],
  },
  refine: {
    key:'refine', name:'Refine', sub:'polish the current slide',
    initEyebrow:'Keep the bones · fix the buried point',
    initH:['Paste a ', 'slide', ''],
    initP:'Paste a slide that’s nearly there, or refine the one you’re on. pptgpt reworks only what’s buried — title, hierarchy, the takeaway.',
    placeholder:'What you have: a chart, three bullets, no takeaway.\nWhat’s off: the numbers feel buried…',
    samples:[
      'The takeaway is buried at the bottom — pull it up',
      'Title is generic, make it argue the point',
      'Too dense — cut to one idea',
    ],
  },
  condense: {
    key:'condense', name:'Condense', sub:'a deck → its spine',
    initEyebrow:'40 slides · three that argue',
    initH:['Paste your ', 'deck', ''],
    initP:'Paste a deck with --- between slides, or drop a .pptx. pptgpt keeps the three-to-five slides that carry the argument.',
    placeholder:'Slide 1 title\nbullets…\n---\nSlide 2 title\nbullets…\n---\nSlide 3 title\nbullets…',
    samples:[
      'Q3 board deck — cut to the spine',
      'Project pitch: problem / plan / cost / bet',
    ],
  },
};

/* ── icons ────────────────────────────────────────────────── */
function Ico({ name, size = 18 }) {
  const s = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' };
  const P = {
    create:  <><path d="M12 4v16M4 12h16" /></>,
    createx: <><path d="M5 16 15 6l3 3L8 19H5z" /><path d="M13 8l3 3" /><path d="M18 4l.6 1.4L20 6l-1.4.6L18 8l-.6-1.4L16 6l1.4-.6z" /></>,
    refine:  <><path d="M4 20 14 10" /><path d="M13 5l6 6" /><path d="M14.5 3.5 20.5 9.5" /><path d="M17 3l4 4" /></>,
    condense:<><path d="M8 4 4 8M8 20 4 16M16 4l4 4M16 20l4-4" /><path d="M4 8h4V4M20 8h-4V4M4 16h4v4M20 16h-4v4" /></>,
    chart:   <><path d="M4 20V4M4 20h16" /><rect x="7" y="12" width="3" height="5" /><rect x="12" y="8" width="3" height="9" /><rect x="17" y="5" width="3" height="12" /></>,
    type:    <><path d="M5 7V5h14v2M12 5v14M9 19h6" /></>,
    layout:  <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M4 9h16M10 9v11" /></>,
    palette: <><path d="M5 5h4v14H5zM11 5h3v14h-3zM16 5h3v14h-3" /></>,
    spark:   <><path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z" /></>,
    text:    <><path d="M5 7V5h14v2M12 5v14M9 19h6" /></>,
    new:     <><path d="M12 5v14M5 12h14" /></>,
    send:    <><path d="M4 12h13M11 6l6 6-6 6" /></>,
    attach:  <><path d="M17 8 9.5 15.5a3 3 0 1 1-4-4L13 4a2 2 0 0 1 3 3l-7.5 7.5" /></>,
    download:<><path d="M12 4v11M8 11l4 4 4-4" /><path d="M5 19h14" /></>,
    arrowr:  <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    chevron: <><path d="M6 9l6 6 6-6" /></>,
    collapse:<><path d="M15 6l-6 6 6 6" /></>,
    expand:  <><path d="M9 6l6 6-6 6" /></>,
    up:      <><path d="M6 15l6-6 6 6" /></>,
    close:   <><path d="M6 6l12 12M18 6 6 18" /></>,
    check:   <><path d="M5 12l5 5 9-11" /></>,
    tune:    <><path d="M4 8h10M18 8h2M4 16h4M12 16h8" /><circle cx="16" cy="8" r="2" /><circle cx="10" cy="16" r="2" /></>,
    doc:     <><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v4h4" /></>,
  };
  return <svg {...s}>{P[name] || null}</svg>;
}
const FEATURE_ICON = { create:'createx', data:'chart', refine:'refine', condense:'condense' };

/* ── mini chart / plot renderers (self-contained) ─────────── */
function MiniBars({ data, pal, w, h }) {
  const pad = { l: 6, r: 6, t: 18, b: 22 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const max = Math.max(...data.map(d => d.value), 1) * 1.15;
  const n = data.length, slot = iw / n, bw = Math.min(48, slot * 0.5);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <line x1={pad.l} y1={pad.t + ih} x2={pad.l + iw} y2={pad.t + ih} stroke={pal.rule} strokeWidth="1" />
      {data.map((d, i) => {
        const bh = (d.value / max) * ih;
        const x = pad.l + i * slot + (slot - bw) / 2;
        const y = pad.t + ih - bh;
        return (
          <g key={i}>
            <rect x={x} y={y} width={bw} height={bh} rx="3" fill={d.hi ? pal.spark : pal.accent} />
            <text x={x + bw / 2} y={y - 6} textAnchor="middle" fontSize="12" fontWeight="900" fill={pal.ink} className="tnum">{d.value}</text>
            <text x={x + bw / 2} y={pad.t + ih + 15} textAnchor="middle" fontSize="11" fontWeight="700" fill={pal.mute}>{d.label}</text>
          </g>
        );
      })}
    </svg>
  );
}
function MiniPlot({ fn, params, pal, w, h }) {
  const pad = 14, iw = w - pad * 2, ih = h - pad * 2, n = 140;
  const f = window.PLOT_FNS && window.PLOT_FNS[fn] ? window.PLOT_FNS[fn]
    : (x, p) => (p.A ?? 1) * Math.exp(-(p.gamma ?? 0.7) * x) * Math.cos((p.omega ?? 4.5) * x);
  const x0 = 0, x1 = 6, y0 = -1.1, y1 = 1.1;
  const sx = x => pad + ((x - x0) / (x1 - x0)) * iw;
  const sy = y => pad + (1 - (y - y0) / (y1 - y0)) * ih;
  let d = '';
  for (let i = 0; i <= n; i++) {
    const x = x0 + (x1 - x0) * (i / n);
    let y; try { y = f(x, params || {}); } catch (e) { y = 0; }
    y = Math.max(y0, Math.min(y1, y));
    d += (i === 0 ? 'M' : 'L') + sx(x).toFixed(1) + ' ' + sy(y).toFixed(1) + ' ';
  }
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <line x1={pad} y1={sy(0)} x2={pad + iw} y2={sy(0)} stroke={pal.rule} strokeWidth="1" />
      <line x1={pad} y1={pad} x2={pad} y2={pad + ih} stroke={pal.rule} strokeWidth="1" />
      <path d={d} stroke={pal.accent} strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ── fonts the Typography dashboard can apply ─────────────── */
const FONTS = {
  'Lato':            "'Lato', system-ui, sans-serif",
  'Arial':           "Arial, Helvetica, sans-serif",
  'Times New Roman': "'Times New Roman', Georgia, serif",
  'Georgia':         "Georgia, 'Times New Roman', serif",
  'Space Grotesk':   "'Space Grotesk', sans-serif",
  'Courier New':     "'Courier New', ui-monospace, monospace",
};
const FONT_LIST = Object.keys(FONTS);
const FONT_SIZES = ['12 pt', '14 pt', '16 pt', '18 pt', '24 pt', '32 pt'];
function ptToScale(pt) { const n = parseInt(pt, 10) || 16; return Math.max(0.7, Math.min(1.7, n / 16)); }

/* ── the slide renderer (fixed 720×405) ───────────────────── */
function SlideCard({ slide }) {
  const pal = PALETTES[slide.palette] || PALETTES.warm;
  const story = slide.emphasis === 'story';
  const k = ptToScale(slide.fontPt || '16 pt');
  const z = n => Math.round(n * k * 10) / 10;
  // A template brings its own type. When one is applied its fonts win over
  // the workspace's, so the preview reads in the template's voice.
  const ffBody = pal.bodyFont ? `'${pal.bodyFont}', ${FONTS[slide.font] || FONTS['Lato']}`
    : (FONTS[slide.font] || FONTS['Lato']);
  const ffHead = pal.headerFont ? `'${pal.headerFont}', ${ffBody}` : ffBody;
  const ff = ffBody;
  // A template palette carries a picture of its own master; paint it behind
  // the content so the preview shows what will actually export — the logo,
  // the picture background, the footer rule — not just its colours.
  const base = {
    position: 'relative', width: SLIDE_W, height: SLIDE_H,
    background: pal.bg, color: pal.ink,
    padding: pal.pad
      ? `${pal.pad.top}px ${pal.pad.right}px ${pal.pad.bottom}px ${pal.pad.left}px`
      : '44px 48px',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
    fontFamily: ff,
    ...(pal.bgImage ? {
      backgroundImage: `url("${pal.bgImage}")`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
      backgroundRepeat: 'no-repeat',
    } : {}),
  };
  const eyebrow = (
    <div style={{ fontSize: z(13), fontWeight: 800, letterSpacing: '0.14em', textTransform: 'uppercase', color: pal.mute, display: 'flex', alignItems: 'center', gap: 9 }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: pal.spark }} />
      {slide.eyebrow}
    </div>
  );
  const takeaway = slide.takeaway && (
    <div style={{ marginTop: 'auto', paddingTop: 16, borderTop: `1px solid ${pal.rule}`, fontSize: z(story ? 22 : 16), fontStyle: 'italic', fontWeight: 700, color: pal.accent, lineHeight: 1.4 }}>
      {'“' + slide.takeaway + '”'}
    </div>
  );
  const footer = slide.footer && (
    <div style={{ marginTop: slide.takeaway ? 12 : 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', fontSize: z(10.5), color: pal.mute, fontWeight: 700, letterSpacing: '0.02em' }}>
      <span>{slide.footer}</span>{slide.page ? <span className="tnum">{slide.page}</span> : null}
    </div>
  );

  if (slide.kind === 'cover') {
    return (
      <div style={{ ...base, justifyContent: 'center', padding: '54px 58px' }}>
        <div style={{ fontSize: z(13), fontWeight: 800, letterSpacing: '0.18em', textTransform: 'uppercase', color: pal.spark, marginBottom: 18 }}>{slide.eyebrow}</div>
        <h2 style={{ fontFamily: ffHead, margin: 0, fontSize: z(46), fontWeight: 900, letterSpacing: '-0.03em', lineHeight: 1.04, maxWidth: '92%' }}>{slide.title}</h2>
        {slide.subtitle && <div style={{ marginTop: 18, fontSize: z(19), color: pal.sub, fontWeight: 500, maxWidth: '80%', lineHeight: 1.4 }}>{slide.subtitle}</div>}
        <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', fontSize: z(12), color: pal.mute, fontWeight: 700, letterSpacing: '0.02em' }}>
          <span>{slide.footer || ''}</span><span>{slide.date || ''}</span>
        </div>
      </div>
    );
  }

  if (slide.kind === 'chart' && slide.chart) {
    return (
      <div style={base}>
        {eyebrow}
        <h3 style={{ fontFamily: ffHead, margin: '14px 0 6px', fontSize: z(30), fontWeight: 900, letterSpacing: '-0.02em', lineHeight: 1.1 }}>{slide.title}</h3>
        <div style={{ fontSize: z(13), fontWeight: 700, color: pal.mute, marginBottom: 6 }}>{slide.chart.title}</div>
        <div style={{ flex: 1, minHeight: 0 }}><MiniBars data={slide.chart.data} pal={pal} w={SLIDE_W - 96} h={176} /></div>
        {takeaway}
        {footer}
      </div>
    );
  }
  if (slide.kind === 'plot' && slide.plot) {
    return (
      <div style={base}>
        {eyebrow}
        <h3 style={{ fontFamily: ffHead, margin: '14px 0 8px', fontSize: z(28), fontWeight: 900, letterSpacing: '-0.02em', lineHeight: 1.1 }}>{slide.title}</h3>
        {slide.plot.eq && <div style={{ fontSize: z(18), fontWeight: 700, color: pal.accent, marginBottom: 6 }}>{slide.plot.eq}</div>}
        <div style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'center' }}><MiniPlot fn={slide.plot.fn} params={slide.plot.params} pal={pal} w={SLIDE_W - 96} h={170} /></div>
        {takeaway}
        {footer}
      </div>
    );
  }

  // text slide
  const hasMetric = slide.metric && !story;
  return (
    <div style={base}>
      {eyebrow}
      <h3 style={{ fontFamily: ffHead, margin: '14px 0 0', fontSize: z(story ? 40 : 33), fontWeight: 900, letterSpacing: '-0.025em', lineHeight: 1.08, maxWidth: story ? '90%' : '100%' }}>{slide.title}</h3>
      <div style={{ display: 'flex', gap: 34, marginTop: 20, flex: 1, minHeight: 0 }}>
        {hasMetric && (
          <div style={{ flex: 'none' }}>
            <div className="tnum" style={{ fontSize: z(68), fontWeight: 900, letterSpacing: '-0.03em', color: pal.accent, lineHeight: 0.95 }}>{slide.metric}</div>
            {slide.metricSub && <div style={{ fontSize: z(13), fontWeight: 700, color: pal.mute, marginTop: 6, maxWidth: 190 }}>{slide.metricSub}</div>}
          </div>
        )}
        {Array.isArray(slide.bullets) && slide.bullets.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 4, flex: 1 }}>
            {slide.bullets.slice(0, story ? 3 : 4).map((b, i) => (
              <div key={i} style={{ display: 'flex', gap: 12, fontSize: z(16.5), color: pal.sub, lineHeight: 1.4 }}>
                <span style={{ color: pal.spark, fontWeight: 900 }}>—</span>
                <span>{b}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      {takeaway}
      {footer}
    </div>
  );
}

/* ── generation ───────────────────────────────────────────── */
function uid() { return 'sl_' + Math.random().toString(36).slice(2, 9); }
function firstLine(t) { return String(t || '').split('\n').map(s => s.trim()).filter(Boolean)[0] || ''; }
function pickMetric(t) { const m = String(t).match(/([+\-−]?\s?\d[\d,\.]*\s?(%|x|×|pts?|weeks?|days?|\$?[MBK])?)/i); return m ? m[0].replace(/\s+/g, '') : null; }

function looksTabular(t) {
  const lines = String(t).split('\n').map(s => s.trim()).filter(Boolean);
  const kv = lines.filter(l => /[A-Za-z].*?[:\-]?\s*[+\-]?\d/.test(l) && /\d/.test(l));
  return (kv.length >= 3) || /(^|\s)(q[1-4]\s+\d)/i.test(t);
}
function looksFormula(t) { return /[=]/.test(t) && /(sin|cos|e\^|exp|γ|ω|x\(t\)|·)/i.test(t); }

function cannedNumbers(t) {
  const nums = (String(t).match(/\d[\d,\.]*/g) || []).map(n => parseFloat(n.replace(/,/g, ''))).filter(n => !isNaN(n));
  const labels = (String(t).match(/q[1-4]/gi) || []);
  const data = [];
  const use = nums.slice(0, 4);
  use.forEach((v, i) => data.push({ label: labels[i] ? labels[i].toUpperCase() : ['A','B','C','D'][i], value: v, hi: false }));
  if (data.length === 0) [32,38,42,45].forEach((v,i)=>data.push({label:['Q1','Q2','Q3','Q4'][i],value:v,hi:false}));
  data[data.length-1].hi = true;
  return data;
}

function cannedSlide({ feature, prompt, audience, current, palette }) {
  const pal = palette || (current && current.palette) || 'warm';
  const aud = AUDIENCES.find(a => a.key === audience) || AUDIENCES[0];
  const text = String(prompt || '').trim();

  if (feature === 'refine' && current) {
    return { ...current, id: current.id,
      title: current.title.replace(/\.$/, '') + (/\d/.test(current.title) ? '' : ' — and why it matters'),
      takeaway: current.takeaway || 'Here’s the one thing to remember.',
      emphasis: current.emphasis === 'story' ? 'story' : 'number', palette: pal };
  }

  if (feature === 'data') {
    if (looksFormula(text)) {
      return { id: uid(), kind: 'plot', palette: pal,
        eyebrow: 'Visualized', title: firstLine(text).replace(/[:=].*$/, '').trim() || 'Damped oscillator',
        plot: { fn: 'damped', eq: 'x(t) = A·e^(−γt)·cos(ωt + φ)', params: { A: 1, gamma: 0.7, omega: 4.5 } },
        takeaway: 'The envelope decays; the oscillation carries the story.' };
    }
    return { id: uid(), kind: 'chart', palette: pal,
      eyebrow: aud.key === 'exec' ? 'Results' : 'By the numbers',
      title: firstLine(text).replace(/[—\-–].*$/, '').trim() || 'Quarterly revenue',
      chart: { title: 'in $M', data: cannedNumbers(text) },
      takeaway: 'The trend is up and to the right — and accelerating.' };
  }

  const metric = pickMetric(text);
  const lines = text.split('\n').map(s => s.replace(/^[-•\d.\s]+/, '').trim()).filter(Boolean);
  const title = (lines[0] || 'Your point, made once — clearly').replace(/\.$/, '');
  const bullets = lines.slice(1, 5).length ? lines.slice(1, 5)
    : ['Net retention held at 118%', 'Churn down to 1.8%', 'Enterprise GTM drove the beat'];
  return { id: uid(), kind: 'text', palette: pal,
    eyebrow: aud.key === 'exec' ? 'Q3 results · exec review' : aud.key === 'conf' ? 'opening slide' : 'update',
    title: metric ? title : title,
    metric, metricSub: metric ? 'vs plan · full-year pace' : null,
    bullets, takeaway: aud.key === 'conf' ? 'One number. One decision. One quarter.' : 'And the trend keeps compounding.',
    emphasis: aud.key === 'conf' ? 'story' : 'number' };
}

async function aiGenerate({ feature, prompt, audience, files, current, palette }) {
  const aud = AUDIENCES.find(a => a.key === audience) || AUDIENCES[0];
  const pal = palette || (current && current.palette) || 'warm';
  const fileNote = files && files.length
    ? `\nThe user attached ${files.length} file(s): ${files.map(f => f.name).join(', ')}. Use the names as a hint for the material type; do not fabricate contents.` : '';

  let sys;
  if (feature === 'condense') {
    sys = `You are pptgpt. Condense the pasted deck into its 3–5 load-bearing slides.
Return ONLY a JSON array (no prose, no code fences). Each item:
{"kind":"text","eyebrow":"ALL CAPS <=4 words","title":"takeaway-first, 4-8 words","metric":"hero number or null","metricSub":"<=5 words or null","bullets":["<=8 words","",""],"takeaway":"<=12 words"}
Slides should feel: ${aud.tone}. No fabricated numbers.${fileNote}\n\nDeck:\n"""${prompt}"""`;
  } else if (feature === 'refine' && current) {
    sys = `You are pptgpt. Rework the current slide keeping its bones — fix the buried point, sharpen the title, put the takeaway where it lands. Apply the user's note.
Return ONLY a JSON object (no prose/fences):
{"kind":"text|chart|plot","eyebrow":"ALL CAPS","title":"","metric":"or null","metricSub":"or null","bullets":["",""],"takeaway":""}
Audience feel: ${aud.tone}.
Current slide JSON: ${JSON.stringify({ title: current.title, metric: current.metric, bullets: current.bullets, takeaway: current.takeaway })}
User note: """${prompt || 'tighten it'}"""`;
  } else if (feature === 'data') {
    sys = `You are pptgpt. Turn the input data into ONE slide that is a chart or a plot.
Return ONLY a JSON object (no prose, no code fences):
{"kind":"chart|plot","eyebrow":"ALL CAPS <=4 words","title":"takeaway-first 4-8 words","takeaway":"<=14 words","chart":{"title":"axis/unit label","data":[{"label":"","value":0,"hi":false}]}|null,"plot":{"fn":"damped|sine|gaussian","eq":"","params":{}}|null}
Use "plot" for a formula/continuous function, else "chart". Highlight the most important bar with hi:true. Do not invent numbers not present.${fileNote}\n\nInput:\n"""${prompt}"""`;
  } else {
    sys = `You are pptgpt. Draft ONE polished TEXT slide from the input (no charts).
Return ONLY a JSON object (no prose, no code fences):
{"kind":"text","eyebrow":"ALL CAPS context <=5 words","title":"takeaway-first headline 4-9 words","metric":"hero number/phrase or null","metricSub":"<=6 words or null","bullets":["<=9 words","",""],"takeaway":"<=14 words conversational"}
Slide should feel: ${aud.tone}. No hedging; don't invent numbers.${fileNote}\n\nInput:\n"""${prompt}"""`;
  }

  try {
    if (!(window.claude && window.claude.complete)) throw new Error('no-claude');
    const raw = await window.claude.complete({ messages: [{ role: 'user', content: sys }], max_tokens: 1400 });
    let c = String(raw || '').trim();
    if (c.startsWith('```')) c = c.replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '');
    if (feature === 'condense') {
      const a = c.indexOf('['), b = c.lastIndexOf(']');
      const arr = JSON.parse(c.slice(a, b + 1));
      return arr.slice(0, 5).map(s => ({ id: uid(), kind: 'text', palette: pal, emphasis: aud.key === 'conf' ? 'story' : 'number', ...s }));
    }
    const a = c.indexOf('{'), b = c.lastIndexOf('}');
    const obj = JSON.parse(c.slice(a, b + 1));
    if (!obj.title && !obj.bullets) throw new Error('empty');
    const id = feature === 'refine' && current ? current.id : uid();
    return { id, palette: pal, emphasis: aud.key === 'conf' ? 'story' : (current && current.emphasis) || 'number', kind: obj.kind || 'text', ...obj };
  } catch (e) {
    if (feature === 'condense') {
      const chunks = String(prompt).split(/\n-{2,}\n|\n\s*---\s*\n/).map(s => s.trim()).filter(Boolean);
      const src = chunks.length > 1 ? chunks : String(prompt).split(/\n{2,}/).filter(Boolean);
      return (src.slice(0, 5).length ? src.slice(0, 5) : ['Q3 beat plan by 14%', 'What drove it', 'What we do next'])
        .map((ch, i) => {
          const cs = cannedSlide({ feature: 'create', prompt: ch, audience, palette: pal });
          return { ...cs, eyebrow: String(i + 1).padStart(2, '0') + ' · spine' };
        });
    }
    return cannedSlide({ feature, prompt, audience, current, palette: pal });
  }
}

Object.assign(window, {
  SLIDE_W, SLIDE_H, PALETTES, AUDIENCES, FEATURES, FEATURE_ICON,
  FONTS, FONT_LIST, FONT_SIZES,
  Ico, SlideCard, aiGenerate, uid,
});
