/* ============================================================
   mockBackend.js — ISOLATED MOCK
   ------------------------------------------------------------
   The only file that fakes the backend. Swap the body of
   `mockBackend` for a real `fetch()` and the UI keeps working.

   Contract (see types.md):
     mockBackend({ mode, rawContent, answers }) -> Promise<{
       slideIR, questions, directions
     }>
   ============================================================ */
(function () {
  'use strict';

  // ── Question decks (one set per mode) ──────────────────────
  const QUESTION_DECKS = {
    draft: [
      { id: 'q_lead',  region: 'top',    text: 'Lead with the headline, or open with the question it answers?', options: ['Headline first', 'Question first'] },
      { id: 'q_focus', region: 'right',  text: 'Foreground the numbers, or the narrative?',                     options: ['Numbers up front', 'Narrative up front'] },
      { id: 'q_tone',  region: 'left',   text: 'Bold and dark, or clean and light?',                            options: ['Bold + dark', 'Clean + light'] },
      { id: 'q_close', region: 'bottom', text: 'End on a takeaway, or on a call to action?',                    options: ['Takeaway', 'Call to action'] },
    ],
    refine: [
      { id: 'q_keep',  region: 'top',    text: 'Keep the current structure, or rework it?',          options: ['Keep structure', 'Rework structure'] },
      { id: 'q_tone',  region: 'left',   text: 'Quieter and more confident, or louder and bolder?',   options: ['Quieter', 'Louder'] },
      { id: 'q_focus', region: 'right',  text: 'Pull the eye to the data, or to the conclusion?',     options: ['To the data', 'To the conclusion'] },
    ],
    condense: [
      { id: 'q_arc',   region: 'top',    text: 'Compress to one big idea, or preserve the arc?',      options: ['One big idea', 'Preserve the arc'] },
      { id: 'q_cut',   region: 'left',   text: 'What gets cut first — context, or supporting detail?',options: ['Cut context', 'Cut detail'] },
      { id: 'q_close', region: 'bottom', text: 'Land on a number, or on the recommendation?',          options: ['A number', 'A recommendation'] },
      { id: 'q_focus', region: 'right',  text: 'Stat-led slides, or story-led slides?',                options: ['Stat-led', 'Story-led'] },
    ],
    visualize: [
      { id: 'q_emphasis', region: 'top',    text: 'Lead with the formula, or the intuition?',          options: ['Formula first', 'Intuition first'] },
      { id: 'q_layout',   region: 'right',  text: 'Plot front-and-center, or split with the explanation?', options: ['Plot center', 'Split layout'] },
      { id: 'q_annot',    region: 'left',   text: 'Annotate the curve, or let it breathe?',             options: ['Annotated', 'Clean'] },
      { id: 'q_palette',  region: 'bottom', text: 'Cool palette (teals), or warm accent (yellow)?',     options: ['Cool', 'Warm'] },
    ],
    synthesize: [
      { id: 'q_chart',  region: 'top',    text: 'Bars, or line over time?',                       options: ['Bars', 'Line'] },
      { id: 'q_label',  region: 'right',  text: 'Label every value, or just the axis ticks?',     options: ['Every value', 'Just ticks'] },
      { id: 'q_focus',  region: 'left',   text: 'Hero the biggest number, or the trend?',         options: ['Hero the number', 'Hero the trend'] },
      { id: 'q_close',  region: 'bottom', text: 'Close on what the data means, or what to do?',   options: ['What it means', 'What to do'] },
    ],
  };

  // ── Tiny parsers ───────────────────────────────────────────
  function parseSingle(text) {
    const lines = (text || '').split('\n').map(s => s.trim()).filter(Boolean);
    const stat  = pickStat(text);
    return {
      title:   lines[0] || 'Untitled slide',
      bullets: lines.slice(1).filter(Boolean),
      stat,
    };
  }
  function parseDeck(rawContent) {
    const parts = (rawContent || '').split(/^\s*---+\s*$/m).map(s => s.trim()).filter(Boolean);
    if (parts.length === 0) return [parseSingle(rawContent)];
    return parts.map(parseSingle);
  }
  function pickStat(text) {
    if (!text) return '+14%';
    // Prefer signed or %-suffixed numbers (skip "Q3" etc.)
    const m = text.match(/[+\-]\d+(?:\.\d+)?%?/) || text.match(/\d+(?:\.\d+)?%/);
    return m ? m[0] : '+14%';
  }

  // ── Color palettes (per direction archetype) ───────────────
  const PALETTES = {
    editorial: { bg: '#F6F2EA', ink: '#1A1A1A', accent: '#1E2761', muted: '#7B7468', sub: '#3D362B', rule: '#1A1A1A' },
    boldDark:  { bg: '#0F1226', ink: '#FFFFFF', accent: '#F4B58A', muted: '#A6ABC4', sub: '#D6DAEC', rule: '#F4B58A' },
    boldLight: { bg: '#FAFAF7', ink: '#0F1226', accent: '#F4B58A', muted: '#6C7A89', sub: '#334155', rule: '#F4B58A' },
    data:      { bg: '#FFFFFF', ink: '#0F172A', accent: '#1E2761', muted: '#6C7A89', sub: '#334155', rule: '#E5E7EB' },
  };

  // ── Per-direction slide builders ───────────────────────────
  // Each takes (role, content, answers) and returns SlideSpec.
  // role: 'singleton' | 'cover' | 'stat' | 'takeaways' | 'recap'

  function editorialSlide(role, c, answers) {
    const p = PALETTES.editorial;
    const leadWithQuestion = answers.q_lead === 'Question first';
    const eyebrow = {
      singleton: leadWithQuestion ? 'A QUESTION' : 'THE FINDING',
      cover:     'IN BRIEF',
      stat:      'THE NUMBER',
      takeaways: 'TO REMEMBER',
      recap:     'TO REMEMBER',
    }[role] || 'A NOTE';

    const blocks = [
      { type: 'text', text: eyebrow, x: 96, y: 96, w: 400, h: 24,
        font: 'mono', size: 13, weight: 500, color: p.muted,
        letterSpacing: 0.24, transform: 'uppercase' },
      { type: 'rule', x: 96, y: 132, w: 28, h: 1, color: p.ink },
      { type: 'text', text: 'pptgpt  ·  ' + (c.pageLabel || '01 / 01'),
        x: 96, y: 656, w: 400, h: 20,
        font: 'mono', size: 12, weight: 400, color: '#9A9286',
        letterSpacing: 0.12, transform: 'uppercase' },
    ];

    if (role === 'stat') {
      blocks.push(
        { type: 'text', text: c.stat,
          x: 96, y: 192, w: 1088, h: 280,
          font: 'serif', size: 240, weight: 400, italic: false,
          color: p.ink, lineHeight: 0.95, letterSpacing: -0.04 },
        { type: 'text', text: c.statLabel,
          x: 96, y: 488, w: 800, h: 80,
          font: 'serif', size: 28, italic: true, color: p.sub, lineHeight: 1.35 },
      );
    } else if (role === 'takeaways' || role === 'recap') {
      blocks.push(
        { type: 'text', text: c.title,
          x: 96, y: 176, w: 1000, h: 100,
          font: 'serif', size: 44, weight: 500, color: p.ink, lineHeight: 1.15 },
        { type: 'bullets', items: (c.bullets || []).slice(0, 3),
          x: 96, y: 300, w: 1000, h: 280,
          font: 'serif', size: 26, weight: 400, color: p.sub,
          lineHeight: 1.5, marker: 'number', markerColor: p.muted, gap: 14 },
      );
    } else {
      // cover / singleton
      const big = role === 'singleton' && leadWithQuestion ? c.question : c.title;
      blocks.push(
        { type: 'text', text: big,
          x: 96, y: 188, w: 1000, h: 320,
          font: 'serif', size: 84, weight: 400, italic: leadWithQuestion,
          color: p.ink, lineHeight: 1.05, letterSpacing: -0.02 },
        { type: 'text', text: c.support,
          x: 96, y: 552, w: 760, h: 80,
          font: 'serif', size: 22, weight: 400, color: p.sub, lineHeight: 1.45 },
      );
    }
    return { canvasW: 1280, canvasH: 720, palette: { bg: p.bg, ink: p.ink, accent: p.accent, muted: p.muted }, blocks };
  }

  function boldSlide(role, c, answers) {
    const dark = answers.q_tone !== 'Clean + light' && answers.q_tone !== 'Quieter';
    const p = dark ? PALETTES.boldDark : PALETTES.boldLight;
    const eyebrow = {
      singleton: 'KEY POINT',
      cover:     'KEY POINT',
      stat:      'THE METRIC',
      takeaways: 'THE TAKEAWAY',
      recap:     'THE TAKEAWAY',
    }[role] || 'NOTE';

    const blocks = [
      { type: 'rect', x: 0, y: 0, w: 8, h: 720, fill: p.accent },
      { type: 'tag', text: eyebrow, x: 96, y: 96, w: 110, h: 26,
        fill: p.accent, color: '#0F1226', size: 11 },
    ];

    if (role === 'stat') {
      blocks.push(
        { type: 'text', text: c.stat,
          x: 96, y: 152, w: 1088, h: 380,
          font: 'sans', size: 280, weight: 700,
          color: p.ink, lineHeight: 0.92, letterSpacing: -0.05 },
        { type: 'rule', x: 96, y: 560, w: 64, h: 3, color: p.accent },
        { type: 'text', text: c.statLabel,
          x: 96, y: 588, w: 900, h: 60,
          font: 'sans', size: 22, weight: 500, color: p.sub,
          letterSpacing: 0.06, transform: 'uppercase' },
      );
    } else if (role === 'takeaways' || role === 'recap') {
      blocks.push(
        { type: 'text', text: c.title,
          x: 96, y: 168, w: 1088, h: 140,
          font: 'sans', size: 60, weight: 700, color: p.ink, lineHeight: 1.05, letterSpacing: -0.02 },
        { type: 'rule', x: 96, y: 332, w: 64, h: 3, color: p.accent },
        { type: 'bullets', items: (c.bullets || []).slice(0, 3),
          x: 96, y: 368, w: 1000, h: 280,
          font: 'sans', size: 28, weight: 500, color: p.sub,
          lineHeight: 1.45, marker: 'number', markerColor: p.accent, gap: 12 },
      );
    } else {
      blocks.push(
        { type: 'text', text: c.title,
          x: 96, y: 168, w: 1088, h: 360,
          font: 'sans', size: 120, weight: 700,
          color: p.ink, lineHeight: 0.98, letterSpacing: -0.035 },
        { type: 'rule', x: 96, y: 568, w: 64, h: 3, color: p.accent },
        { type: 'text', text: c.support,
          x: 96, y: 600, w: 900, h: 80,
          font: 'sans', size: 22, weight: 400,
          color: p.sub, lineHeight: 1.4 },
      );
    }
    return { canvasW: 1280, canvasH: 720, palette: { bg: p.bg, ink: p.ink, accent: p.accent, muted: p.muted }, blocks };
  }

  function dataSlide(role, c, answers) {
    const p = PALETTES.data;
    const cta = answers.q_close === 'Call to action' || answers.q_close === 'A recommendation';

    const blocks = [
      { type: 'text', text: 'Q3 / SIGNAL', x: 96, y: 88, w: 400, h: 24,
        font: 'mono', size: 13, weight: 500, color: p.muted,
        letterSpacing: 0.22, transform: 'uppercase' },
    ];

    if (role === 'stat') {
      blocks.push(
        { type: 'text', text: c.stat,
          x: 96, y: 144, w: 1088, h: 380,
          font: 'sans', size: 280, weight: 600,
          color: p.accent, lineHeight: 0.9, letterSpacing: -0.04 },
        { type: 'text', text: c.statLabel,
          x: 96, y: 560, w: 900, h: 40,
          font: 'sans', size: 22, weight: 500,
          color: p.muted, letterSpacing: 0.05, transform: 'uppercase' },
        { type: 'rule', x: 96, y: 624, w: 200, h: 1, color: '#E5E7EB' },
      );
    } else if (role === 'takeaways' || role === 'recap') {
      blocks.push(
        { type: 'text', text: c.title,
          x: 96, y: 152, w: 1088, h: 120,
          font: 'serif', size: 40, weight: 500, color: p.ink, lineHeight: 1.15 },
        { type: 'rule', x: 96, y: 300, w: 64, h: 1, color: p.accent },
        { type: 'bullets', items: (c.bullets || []).slice(0, 3),
          x: 96, y: 332, w: 1088, h: 280,
          font: 'sans', size: 22, weight: 400, color: p.sub,
          lineHeight: 1.55, marker: 'dot', markerColor: p.accent, gap: 14 },
        cta
          ? { type: 'tag', text: 'BOOK A REVIEW →', x: 96, y: 624, w: 188, h: 32,
              fill: p.accent, color: '#FFFFFF', size: 12 }
          : { type: 'text', text: 'Compounds monthly · holds in down-quarters',
              x: 96, y: 632, w: 760, h: 20, font: 'mono', size: 12, weight: 400,
              color: p.muted, letterSpacing: 0.08 },
      );
    } else {
      // singleton or cover — stat hero + supporting column
      const numbersFirst = answers.q_focus !== 'Narrative up front' && answers.q_focus !== 'To the conclusion';
      blocks.push(
        { type: 'text', text: c.stat,
          x: 96, y: numbersFirst ? 144 : 380, w: 760, h: 260,
          font: 'sans', size: 220, weight: 600,
          color: p.accent, lineHeight: 0.92, letterSpacing: -0.04 },
        { type: 'text', text: c.statLabel,
          x: 96, y: numbersFirst ? 410 : 644, w: 760, h: 40,
          font: 'sans', size: 20, weight: 500,
          color: p.muted, letterSpacing: 0.04, transform: 'uppercase' },
        { type: 'rule', x: 904, y: 144, w: 1, h: 432, color: '#E5E7EB' },
        { type: 'text', text: c.title,
          x: 944, y: numbersFirst ? 144 : 88, w: 256, h: 200,
          font: 'serif', size: 28, weight: 500, color: p.ink, lineHeight: 1.2 },
        { type: 'bullets', items: (c.bullets || []).slice(0, 3),
          x: 944, y: numbersFirst ? 320 : 200, w: 256, h: 280,
          font: 'sans', size: 14, weight: 400, color: p.sub,
          lineHeight: 1.55, marker: 'dot', markerColor: p.accent, gap: 8 },
        cta
          ? { type: 'tag', text: 'BOOK A REVIEW →', x: 96, y: 624, w: 188, h: 32,
              fill: p.accent, color: '#FFFFFF', size: 12 }
          : { type: 'text', text: 'Compounds monthly · holds in down-quarters',
              x: 96, y: 632, w: 760, h: 20, font: 'mono', size: 12, weight: 400,
              color: p.muted, letterSpacing: 0.08 },
      );
    }
    return { canvasW: 1280, canvasH: 720, palette: { bg: p.bg, ink: p.ink, accent: p.accent, muted: p.muted }, blocks };
  }

  // ── content-extraction for a SINGLE styled slide ───────────
  function singletonContent(rawContent) {
    const s = parseSingle(rawContent);
    return {
      title:     s.title,
      question:  'What changed in Q3 — and is it durable?',
      support:   s.bullets.join(' · ') || 'Retention strong · churn down two points · revenue compounding',
      stat:      s.stat,
      statLabel: 'YoY revenue, Q3',
      bullets:   s.bullets.length ? s.bullets : [
        'Retention up 4 pts',
        'Churn down to 1.8%',
        'New cohort LTV +22%',
      ],
      pageLabel: '01 / 01',
    };
  }

  // ── content-extraction for a CONDENSED deck (3 slides) ─────
  function condensedDeck(rawContent, answers) {
    const slides = parseDeck(rawContent);
    const cover = slides[0] || { title: 'Untitled deck', bullets: [] };
    // pick the largest stat anywhere in the deck
    const allText = slides.flatMap(s => [s.title, ...s.bullets]).join('\n');
    const stat = pickStat(allText);

    // gather all bullets, pick 3 strongest (mock: just dedupe + first 3)
    const bullets = Array.from(new Set(slides.flatMap(s => s.bullets))).slice(0, 3);
    const oneBigIdea = answers.q_arc === 'One big idea';
    const closeOnNumber = answers.q_close === 'A number';

    // If "one big idea": cover → stat → takeaway (just 3, same shape)
    // If "preserve arc": cover → stat → takeaways (we don't change slide count for the mock)
    return {
      cover: {
        title:     cover.title,
        support:   bullets.join(' · '),
        bullets:   bullets,
        stat,
        statLabel: 'HEADLINE NUMBER',
        question:  oneBigIdea ? 'One question. One answer.' : cover.title,
        pageLabel: '01 / 03',
      },
      stat: {
        title:     cover.title,
        bullets:   bullets,
        stat,
        statLabel: 'THE NUMBER THAT MATTERS',
        question:  'In one number:',
        support:   bullets.slice(0, 1).join(''),
        pageLabel: '02 / 03',
      },
      takeaways: {
        title:     closeOnNumber ? `Bottom line: ${stat}` : 'What to do next',
        bullets:   bullets,
        stat,
        statLabel: 'OUTCOME',
        question:  'What to do next',
        support:   bullets.slice(0, 1).join(''),
        pageLabel: '03 / 03',
      },
    };
  }

  // ── Baseline IR (shown while questions are pending) ────────
  function baselineIR(req) {
    const slides = parseDeck(req.rawContent);
    const isDeck = slides.length > 1;
    const c = parseSingle(req.rawContent);
    const eyebrow =
      req.mode === 'condense' ? `DECK · ${slides.length} SLIDES · DRAFT` :
      req.mode === 'refine'   ? 'REWORK · DRAFT'                          :
                                'DRAFT';

    const blocks = [
      { type: 'text', text: eyebrow,
        x: 80, y: 72, w: 600, h: 28,
        font: 'mono', size: 14, weight: 500,
        color: '#6C7A89', letterSpacing: 0.18, transform: 'uppercase' },
      { type: 'rule', x: 80, y: 116, w: 36, h: 2, color: '#0F172A' },
      { type: 'text', text: c.title,
        x: 80, y: 160, w: 1120, h: 240,
        font: 'serif', size: 64, weight: 500,
        color: '#0F172A', lineHeight: 1.12, letterSpacing: -0.015 },
    ];
    if (c.bullets.length) {
      blocks.push({
        type: 'bullets', items: c.bullets.slice(0, 5),
        x: 80, y: 440, w: 1120, h: 240,
        font: 'sans', size: 22, weight: 400,
        color: '#334155', lineHeight: 1.5,
        marker: 'dash', markerColor: '#6C7A89', gap: 6,
      });
    }
    return {
      canvasW: 1280, canvasH: 720,
      palette: { bg: '#FAFAF7', ink: '#0F172A', accent: '#1E2761', muted: '#6C7A89' },
      blocks,
    };
  }

  // ── Visualize-mode helpers ─────────────────────────────────
  function visualizeContent(req) {
    // Prefer outline if the workbench sent one
    if (req.outline && req.outline.length > 0) {
      const s = req.outline[0];
      return {
        title:    (s.title || 'Untitled visualization').trim(),
        messages: (s.messages || []).slice(0, 3).map(x => (x || '').trim()).filter(Boolean),
      };
    }
    const lines = (req.rawContent || '').split('\n').map(s => s.trim()).filter(Boolean);
    return {
      title:    lines[0] || 'Untitled visualization',
      messages: lines.slice(1, 4),
    };
  }

  function detectPlot(rawContent, title) {
    const text = ((title || '') + ' ' + (rawContent || '')).toLowerCase();
    const has = (w) => text.includes(w);

    if (has('damped') || has('oscillat') || has('decay') || has('rlc')) {
      return {
        fnId: 'damped',
        params: { A: 1, gamma: 0.3, omega: 4 },
        paramSchema: [
          { name: 'A',     label: 'A · amplitude', default: 1,   min: 0,   max: 2,   step: 0.05 },
          { name: 'gamma', label: 'γ · damping',    default: 0.3, min: 0,   max: 1.5, step: 0.05 },
          { name: 'omega', label: 'ω · frequency',  default: 4,   min: 0.5, max: 10,  step: 0.1 },
        ],
        xRange: [0, 8], yRange: [-1.2, 1.2],
        formula: 'y = A · e^(−γx) · cos(ωx)',
      };
    }
    if (has('gaussian') || has('normal distribution') || has('bell') || has('normal')) {
      return {
        fnId: 'gaussian',
        params: { A: 1, mu: 0, sigma: 1 },
        paramSchema: [
          { name: 'mu',    label: 'μ · mean',      default: 0, min: -3,   max: 3, step: 0.1 },
          { name: 'sigma', label: 'σ · std-dev',   default: 1, min: 0.2,  max: 3, step: 0.05 },
          { name: 'A',     label: 'A · amplitude', default: 1, min: 0,    max: 2, step: 0.05 },
        ],
        xRange: [-4, 4], yRange: [0, 1.2],
        formula: 'y = A · exp(−½((x−μ)/σ)²)',
      };
    }
    if (has('sigmoid') || has('logistic')) {
      return {
        fnId: 'sigmoid',
        params: { A: 1, k: 1, x0: 0 },
        paramSchema: [
          { name: 'k',  label: 'k · steepness', default: 1, min: 0.2, max: 5, step: 0.1 },
          { name: 'x0', label: 'x₀ · midpoint', default: 0, min: -3,  max: 3, step: 0.1 },
        ],
        xRange: [-5, 5], yRange: [-0.1, 1.2],
        formula: 'y = 1 / (1 + e^(−k(x−x₀)))',
      };
    }
    if (has('exponential') || has('growth') || has('compound')) {
      return {
        fnId: 'exponential',
        params: { A: 1, k: 0.5 },
        paramSchema: [
          { name: 'k', label: 'k · rate',       default: 0.5, min: -1, max: 1.5, step: 0.05 },
          { name: 'A', label: 'A · amplitude',  default: 1,   min: 0,  max: 2,   step: 0.05 },
        ],
        xRange: [0, 5], yRange: [0, 5],
        formula: 'y = A · e^(kx)',
      };
    }
    // default: sine wave
    return {
      fnId: 'sine',
      params: { A: 1, omega: 1, phi: 0 },
      paramSchema: [
        { name: 'A',     label: 'A · amplitude', default: 1, min: 0,         max: 2,         step: 0.05 },
        { name: 'omega', label: 'ω · frequency', default: 1, min: 0.1,       max: 4,         step: 0.05 },
        { name: 'phi',   label: 'φ · phase',     default: 0, min: -3.14159,  max: 3.14159,   step: 0.1  },
      ],
      xRange: [-2 * Math.PI, 2 * Math.PI], yRange: [-1.5, 1.5],
      formula: 'y = A · sin(ωx + φ)',
    };
  }

  // 3b1b-language slide builders. Dark navy bg; serif italic text;
  // a single highlight color picked from {teal #4ec5ff, warm #ffd166}.
  function plotBlock(plot, x, y, w, h, color, opts) {
    opts = opts || {};
    return {
      type: 'plot', x, y, w, h,
      bg: opts.bg || '#0a0a14',
      curves: [{ fn: plot.fnId, params: plot.params, color, width: opts.width || 3 }],
      xRange: plot.xRange, yRange: plot.yRange,
      paramSchema: plot.paramSchema,
      showGrid: opts.showGrid !== false,
      showAxes: opts.showAxes !== false,
      showTickLabels: opts.showTickLabels !== false,
      gridColor: opts.gridColor || 'rgba(255,255,255,0.05)',
      axisColor: opts.axisColor || 'rgba(255,255,255,0.55)',
      tickColor: 'rgba(255,255,255,0.3)',
      tickLabelColor: 'rgba(255,255,255,0.55)',
      xLabel: opts.xLabel, yLabel: opts.yLabel,
      paddingLeft:   opts.paddingLeft,
      paddingRight:  opts.paddingRight,
      paddingTop:    opts.paddingTop,
      paddingBottom: opts.paddingBottom,
    };
  }

  function manimClassicSlide(content, plot, answers, main, accent2) {
    const annotated = answers.q_annot === 'Annotated';
    const formulaFirst = answers.q_emphasis === 'Formula first';
    return {
      canvasW: 1280, canvasH: 720,
      palette: { bg: '#0F0F1E', ink: '#fff', accent: main, muted: 'rgba(255,255,255,0.6)' },
      blocks: [
        { type: 'text', text: 'manim · 3b1b', x: 64, y: 56, w: 400, h: 24,
          font: 'mono', size: 12, weight: 500, color: 'rgba(255,255,255,0.45)',
          letterSpacing: 0.22, transform: 'uppercase' },
        { type: 'text', text: content.title,
          x: 64, y: 90, w: 1152, h: 80,
          font: 'serif', size: 44, weight: 500, italic: true,
          color: '#fff', letterSpacing: -0.005, lineHeight: 1.1 },
        formulaFirst
          ? { type: 'text', text: plot.formula, x: 64, y: 168, w: 1152, h: 40,
              font: 'serif', italic: true, size: 24, color: accent2 }
          : null,
        plotBlock(plot, 140, formulaFirst ? 230 : 200, 1000, formulaFirst ? 380 : 410, main, {
          showGrid: annotated, showAxes: true, showTickLabels: annotated,
          xLabel: annotated ? 'x' : null, yLabel: annotated ? 'y' : null,
        }),
        !formulaFirst
          ? { type: 'text', text: plot.formula, x: 64, y: 640, w: 1152, h: 40,
              font: 'serif', italic: true, size: 22, color: accent2, align: 'center' }
          : null,
      ].filter(Boolean),
    };
  }

  function splitLectureSlide(content, plot, answers, main, accent2) {
    const formulaFirst = answers.q_emphasis === 'Formula first';
    const annotated = answers.q_annot === 'Annotated';
    const msgs = content.messages.length ? content.messages : ['Pick a parameter to tune', 'Watch the curve respond', 'Read off the relationship'];
    return {
      canvasW: 1280, canvasH: 720,
      palette: { bg: '#0F0F1E', ink: '#fff', accent: main, muted: 'rgba(255,255,255,0.6)' },
      blocks: [
        { type: 'text', text: 'lecture · split', x: 64, y: 56, w: 400, h: 24,
          font: 'mono', size: 12, color: 'rgba(255,255,255,0.45)',
          letterSpacing: 0.22, transform: 'uppercase' },
        { type: 'text', text: content.title,
          x: 64, y: 96, w: 540, h: 120,
          font: 'serif', italic: true, size: 36, weight: 500, color: '#fff',
          lineHeight: 1.15, letterSpacing: -0.005 },
        formulaFirst
          ? { type: 'text', text: plot.formula, x: 64, y: 234, w: 540, h: 40,
              font: 'serif', italic: true, size: 22, color: accent2 }
          : null,
        { type: 'bullets', items: msgs.slice(0, 3),
          x: 64, y: formulaFirst ? 296 : 248, w: 540, h: 360,
          font: 'sans', size: 19, weight: 400,
          color: 'rgba(255,255,255,0.85)', lineHeight: 1.55,
          marker: 'number', markerColor: main, gap: 16 },
        !formulaFirst
          ? { type: 'text', text: plot.formula, x: 64, y: 632, w: 540, h: 32,
              font: 'serif', italic: true, size: 18, color: accent2 }
          : null,
        plotBlock(plot, 660, 96, 556, 528, main, {
          showGrid: true, showAxes: true, showTickLabels: annotated,
          xLabel: 'x', yLabel: 'y',
        }),
      ].filter(Boolean),
    };
  }

  function annotatedSlide(content, plot, answers, main, accent2) {
    return {
      canvasW: 1280, canvasH: 720,
      palette: { bg: '#0F0F1E', ink: '#fff', accent: main, muted: 'rgba(255,255,255,0.6)' },
      blocks: [
        plotBlock(plot, 0, 0, 1280, 720, main, {
          bg: '#0F0F1E',
          width: 4,
          showGrid: true, showAxes: true, showTickLabels: true,
          gridColor: 'rgba(255,255,255,0.04)',
          axisColor: 'rgba(255,255,255,0.4)',
          xLabel: 'x', yLabel: 'y',
          paddingLeft: 96, paddingRight: 96, paddingTop: 160, paddingBottom: 110,
        }),
        { type: 'text', text: '01 · visualize', x: 64, y: 56, w: 240, h: 20,
          font: 'mono', size: 11, weight: 500, color: accent2,
          letterSpacing: 0.22, transform: 'uppercase' },
        { type: 'text', text: content.title,
          x: 64, y: 80, w: 800, h: 80,
          font: 'serif', italic: true, size: 32, weight: 500,
          color: '#fff', lineHeight: 1.15 },
        { type: 'text', text: plot.formula,
          x: 800, y: 90, w: 416, h: 60,
          font: 'serif', italic: true, size: 22, color: accent2, align: 'right' },
        // closing message at bottom
        content.messages[0]
          ? { type: 'text', text: '— ' + content.messages[0],
              x: 64, y: 656, w: 1152, h: 30,
              font: 'serif', italic: true, size: 18,
              color: 'rgba(255,255,255,0.7)' }
          : null,
      ].filter(Boolean),
    };
  }

  // ── Synthesize helpers (data → chart slides) ──────────────
  function parseDataTable(text) {
    // Try CSV / TSV / pipe-separated. First non-blank row that contains
    // 2+ cells AND has a numeric in the SECOND row treated as headers.
    const lines = (text || '').split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length < 2) return null;
    const sep = /\s*[,\t|]\s*|\s{2,}/;
    const headers = lines[0].split(sep).filter(Boolean);
    if (headers.length < 2) return null;
    const rows = [];
    for (const line of lines.slice(1)) {
      const cells = line.split(sep).filter((c, i) => i < headers.length);
      if (cells.length < 2) continue;
      const label = cells[0];
      const value = parseFloat(cells[1].replace(/[$,%]/g, ''));
      if (!Number.isFinite(value)) continue;
      const row = { label, value };
      if (cells.length > 2) {
        const secondary = parseFloat(cells[2].replace(/[$,%]/g, ''));
        if (Number.isFinite(secondary)) row.secondary = secondary;
      }
      rows.push(row);
    }
    if (rows.length === 0) return null;
    return { headers, rows };
  }

  function synthesizeContent(req) {
    // Prefer outline messages — they may contain inline data like
    // "Q1: 32, Q2: 38, Q3: 42, Q4: 45"
    let table = parseDataTable(req.rawContent);
    if (!table) {
      // try to extract pairs like "Q1: 32" from the messages
      const text = req.rawContent || '';
      const pairs = [];
      const inlineRe = /([A-Za-z0-9 _-]+?)\s*[:=]\s*([+\-]?\d+(?:\.\d+)?)/g;
      let m;
      while ((m = inlineRe.exec(text)) && pairs.length < 8) {
        const label = m[1].trim();
        const value = parseFloat(m[2]);
        if (Number.isFinite(value)) pairs.push({ label, value });
      }
      if (pairs.length >= 2) table = { headers: ['label', 'value'], rows: pairs };
    }
    if (!table) {
      table = { headers: ['q', 'rev'], rows: [
        { label: 'Q1', value: 32 }, { label: 'Q2', value: 38 },
        { label: 'Q3', value: 42 }, { label: 'Q4', value: 45 },
      ]};
    }

    const titleLine = (req.outline && req.outline[0]?.title) || (req.rawContent || '').split('\n')[0] || 'Untitled data';
    const messages = (req.outline && req.outline[0]?.messages) || [];
    return {
      title: titleLine,
      messages: messages.filter(Boolean).slice(0, 3),
      data: table.rows,
      yLabel: table.headers[1],
      xLabel: table.headers[0],
    };
  }

  function synthesizeChartSlide(role, c, answers) {
    const heroNumber = answers.q_focus === 'Hero the number';
    const closeAction = answers.q_close === 'What to do';
    const everyLabel = answers.q_label !== 'Just ticks';
    const chartKind = answers.q_chart === 'Line' ? 'line' : 'bar';

    // role: 'editorial' | 'bold' | 'data'
    if (role === 'editorial') {
      return {
        canvasW: 1280, canvasH: 720,
        palette: { bg: '#F6F2EA', ink: '#1A1A1A', accent: '#1E2761', muted: '#7B7468' },
        blocks: [
          { type: 'text', text: 'THE DATA', x: 96, y: 96, w: 400, h: 24,
            font: 'mono', size: 13, weight: 500, color: '#7B7468',
            letterSpacing: 0.24, transform: 'uppercase' },
          { type: 'rule', x: 96, y: 132, w: 28, h: 1, color: '#1A1A1A' },
          { type: 'text', text: c.title,
            x: 96, y: 168, w: 1088, h: 80,
            font: 'serif', size: 38, weight: 500, italic: true,
            color: '#1A1A1A', lineHeight: 1.15 },
          { type: 'chart',
            x: 96, y: 264, w: 720, h: 360,
            kind: chartKind, data: c.data,
            bg: '#FFFFFF', primaryColor: '#1E2761',
            axisColor: '#D8D2C4', gridColor: '#EDE9DF', labelColor: '#7B7468',
            showValueLabels: everyLabel,
          },
          { type: 'bullets', items: c.messages.length ? c.messages : [c.yLabel],
            x: 864, y: 264, w: 320, h: 360,
            font: 'serif', size: 17, weight: 400, italic: false,
            color: '#3D362B', lineHeight: 1.55,
            marker: 'dash', markerColor: '#7B7468', gap: 10 },
          { type: 'text', text: closeAction ? '— Next step: invest in Q4 expansion' : '— ' + (c.messages[0] || 'A consistent trend'),
            x: 96, y: 656, w: 1088, h: 30,
            font: 'serif', italic: true, size: 18, color: '#7B7468' },
        ],
      };
    }
    if (role === 'bold') {
      const dark = answers.q_tone !== 'Quieter' && answers.q_tone !== 'Clean + light';
      const bg = dark ? '#0F1226' : '#FAFAF7';
      const ink = dark ? '#FFFFFF' : '#0F1226';
      const sub = dark ? '#D6DAEC' : '#334155';
      const accent = '#F4B58A';
      return {
        canvasW: 1280, canvasH: 720,
        palette: { bg, ink, accent, muted: dark ? '#A6ABC4' : '#6C7A89' },
        blocks: [
          { type: 'rect', x: 0, y: 0, w: 8, h: 720, fill: accent },
          { type: 'tag', text: 'THE NUMBERS', x: 96, y: 96, w: 130, h: 26,
            fill: accent, color: '#0F1226', size: 11 },
          { type: 'text', text: c.title,
            x: 96, y: 144, w: 1088, h: 80,
            font: 'sans', size: 48, weight: 700,
            color: ink, lineHeight: 1.05, letterSpacing: -0.02 },
          { type: 'chart',
            x: 96, y: 240, w: 1088, h: 380,
            kind: chartKind, data: c.data,
            bg: dark ? '#1A1E3D' : '#FFFFFF', primaryColor: accent,
            axisColor: dark ? 'rgba(255,255,255,0.25)' : '#E5E7EB',
            gridColor: dark ? 'rgba(255,255,255,0.08)' : '#F1F5F9',
            labelColor: dark ? '#D6DAEC' : '#6C7A89',
            showValueLabels: everyLabel,
          },
          { type: 'text', text: closeAction
              ? 'Action: invest in Q4 expansion'
              : (c.messages[0] || 'A consistent trend — and it accelerates'),
            x: 96, y: 644, w: 1088, h: 40,
            font: 'sans', size: 18, weight: 500, color: sub,
            letterSpacing: 0.02 },
        ],
      };
    }
    // 'data' archetype — hero number on the left, chart smaller right
    const top = c.data.reduce((a, b) => b.value > a.value ? b : a, c.data[0] || { value: 0, label: '' });
    return {
      canvasW: 1280, canvasH: 720,
      palette: { bg: '#FFFFFF', ink: '#0F172A', accent: '#1E2761', muted: '#6C7A89' },
      blocks: [
        { type: 'text', text: 'SIGNAL', x: 96, y: 88, w: 400, h: 24,
          font: 'mono', size: 13, weight: 500, color: '#6C7A89',
          letterSpacing: 0.22, transform: 'uppercase' },
        heroNumber
          ? { type: 'text', text: String(top.value),
              x: 96, y: 128, w: 560, h: 240,
              font: 'sans', size: 200, weight: 600,
              color: '#1E2761', lineHeight: 0.92, letterSpacing: -0.04 }
          : null,
        heroNumber
          ? { type: 'text', text: c.yLabel + ' · ' + top.label,
              x: 96, y: 392, w: 560, h: 28,
              font: 'sans', size: 16, weight: 500, color: '#6C7A89',
              letterSpacing: 0.06, transform: 'uppercase' }
          : null,
        { type: 'text', text: c.title,
          x: heroNumber ? 96 : 96, y: heroNumber ? 448 : 128, w: heroNumber ? 560 : 1088, h: 60,
          font: 'serif', size: heroNumber ? 24 : 36, weight: 500, color: '#0F172A',
          lineHeight: 1.2 },
        { type: 'chart',
          x: heroNumber ? 696 : 96, y: heroNumber ? 128 : 200, w: heroNumber ? 488 : 1088, h: heroNumber ? 420 : 380,
          kind: chartKind, data: c.data,
          bg: '#FFFFFF', primaryColor: '#1E2761',
          axisColor: '#E5E7EB', gridColor: '#F1F5F9', labelColor: '#6C7A89',
          showValueLabels: everyLabel,
        },
        c.messages[0]
          ? { type: 'text', text: '— ' + c.messages[0],
              x: 96, y: 664, w: 1088, h: 30,
              font: 'serif', italic: true, size: 16, color: '#6C7A89' }
          : null,
      ].filter(Boolean),
    };
  }

  // ── Build directions for the current mode ──────────────────
  function buildDirections(req) {
    const answers = req.answers || {};
    if (req.mode === 'synthesize') {
      const c = synthesizeContent(req);
      const ed = synthesizeChartSlide('editorial', c, answers);
      const bo = synthesizeChartSlide('bold',      c, answers);
      const da = synthesizeChartSlide('data',      c, answers);
      return [
        { key: 'editorial', label: 'Editorial Chart', blurb: 'Chart left, story column right, single takeaway closes.', previewSpec: ed, slides: [ed] },
        { key: 'bold',      label: 'Bold Chart',      blurb: 'Full-width chart with display-sans title and accent rule.',  previewSpec: bo, slides: [bo] },
        { key: 'data',      label: 'Hero Number',     blurb: 'Headline value front-and-center; chart supports.',          previewSpec: da, slides: [da] },
      ];
    }
    if (req.mode === 'visualize') {
      const content = visualizeContent(req);
      const plot = detectPlot(req.rawContent, content.title);
      const cool = answers.q_palette !== 'Warm';
      const main = cool ? '#4ec5ff' : '#ffd166';
      const accent2 = cool ? '#ffd166' : '#4ec5ff';
      const ma = manimClassicSlide(content, plot, answers, main, accent2);
      const sl = splitLectureSlide(content, plot, answers, main, accent2);
      const an = annotatedSlide(content, plot, answers, main, accent2);
      return [
        { key: 'manim',     label: 'Manim Classic', blurb: 'Title up top, plot center, formula as the closing line.', previewSpec: ma, slides: [ma] },
        { key: 'split',     label: 'Split Lecture', blurb: 'Half lecture notes, half plot — sized for explanation.',  previewSpec: sl, slides: [sl] },
        { key: 'annotated', label: 'Full Bleed',    blurb: 'Plot is the slide. Title and formula overlay the canvas.',previewSpec: an, slides: [an] },
      ];
    }

    if (req.mode === 'condense') {
      const c = condensedDeck(req.rawContent, answers);
      const make = (fn) => {
        const slides = [
          fn('cover',     { ...c.cover,     pageLabel: '01 / 03' }, answers),
          fn('stat',      { ...c.stat,      pageLabel: '02 / 03' }, answers),
          fn('takeaways', { ...c.takeaways, pageLabel: '03 / 03' }, answers),
        ];
        return { previewSpec: slides[0], slides };
      };
      const ed = make(editorialSlide);
      const bo = make(boldSlide);
      const da = make(dataSlide);
      return [
        { key: 'editorial', label: 'Editorial Compression', blurb: 'Three slides. Eyebrow + serif headline + numbered close.', ...ed },
        { key: 'bold',      label: 'Bold Throughline',      blurb: 'Single visual voice across all three. Display sans, accent rule.', ...bo },
        { key: 'data',      label: 'Number First',          blurb: 'Cover defers to the stat. Story slides earn the page.', ...da },
      ];
    }

    // draft / refine — single slide
    const content = singletonContent(req.rawContent);
    const ed = editorialSlide('singleton', content, answers);
    const bo = boldSlide('singleton',      content, answers);
    const da = dataSlide('singleton',      content, answers);
    return [
      { key: 'editorial', label: 'Editorial Calm',   blurb: 'Serif headline, generous air, single eyebrow.',        previewSpec: ed, slides: [ed] },
      { key: 'bold',      label: 'Bold Statement',   blurb: 'Display sans, weighted color block, accent rule.',     previewSpec: bo, slides: [bo] },
      { key: 'data',      label: 'Data Foreground',  blurb: 'Stat hero, supporting column, light footer.',          previewSpec: da, slides: [da] },
    ];
  }

  // ── The mock function the UI imports ───────────────────────
  async function mockBackend(req) {
    await new Promise(r => setTimeout(r, 480));   // simulate network

    const mode    = req.mode || 'draft';
    const answers = req.answers || {};
    const deck    = QUESTION_DECKS[mode] || QUESTION_DECKS.draft;
    const answeredIds = new Set(Object.keys(answers).filter(k => answers[k]));
    const remaining = deck.filter(q => !answeredIds.has(q.id));

    const slideIR = baselineIR(req);

    // Workbench mode wants live directions even while questions are open;
    // index.html ignores them until questions clear.
    const wantsLive = req.wantsLiveDirections === true;
    const directionsReady = remaining.length === 0;
    const directions = (directionsReady || wantsLive)
      ? buildDirections({ ...req, mode })
      : [];

    return { slideIR, questions: remaining, directions };
  }

  window.mockBackend = mockBackend;

  // ── Storyboard extraction (separate entry, not the main backend) ──
  // The story-map phase calls this with pasted text or PDF-extracted text;
  // it returns an OutlineSlide[] the user can review and edit before being
  // dropped into the workbench. Same swap-for-fetch pattern.
  async function extractStoryboard(req) {
    await new Promise(r => setTimeout(r, 520));

    const text = (req.text || '').trim();
    const mode = req.mode || 'draft';
    if (!text) return { outline: [emptySlide(1)], recommendations: [] };

    // 1) split by --- separators (deck-style)
    let chunks = text.split(/^\s*---+\s*$/m).map(s => s.trim()).filter(Boolean);

    // 2) if there's just one big blob, try to split on heading-ish lines
    if (chunks.length === 1) {
      chunks = splitOnHeadings(text);
    }

    // For visualize / synthesize / refine — single-slide output.
    // For draft — usually one slide, but the user can ask for N via targetCount.
    // For condense, keep ALL chunks (capped to targetCount below).
    if (mode === 'visualize' || mode === 'synthesize' || mode === 'refine') {
      const all = chunks.join('\n');
      const single = [textToSlide(all, 1)];
      return { outline: single, recommendations: buildRecommendations(single, mode, req.audience) };
    }

    if (mode === 'draft') {
      const draftTarget = Math.max(1, Math.min(6, req.targetCount || 1));
      if (draftTarget === 1) {
        const all = chunks.join('\n');
        const single = [textToSlide(all, 1)];
        return { outline: single, recommendations: buildRecommendations(single, mode, req.audience) };
      }
      // Multi-slide draft: take up to N chunks (or split a single blob)
      const src = chunks.length >= draftTarget ? chunks.slice(0, draftTarget) : chunks;
      let slides = src.map((c, i) => textToSlide(c, i + 1));
      while (slides.length < draftTarget) slides.push(emptySlide(slides.length + 1));
      return { outline: slides, recommendations: buildRecommendations(slides, mode, req.audience) };
    }

    // condense — turn each chunk into a slide; user picks target count (default 5)
    const target = Math.max(2, Math.min(10, req.targetCount || 5));
    let slides = chunks.map((c, i) => textToSlide(c, i + 1));
    if (slides.length > target) {
      // keep the strongest N (mock heuristic: longest content wins)
      slides.sort((a, b) => (b.messages.join(' ').length) - (a.messages.join(' ').length));
      slides = slides.slice(0, target).sort((a, b) => slidesOrderOf(a, b, chunks));
    }
    // No auto-padding: an empty slide is a phantom, not a real one. The user
    // adds slides via the "+ ADD SLIDE" affordance in the storyboard editor.
    if (slides.length === 0) slides.push(emptySlide(1));
    return { outline: slides, recommendations: buildRecommendations(slides, mode, req.audience) };
  }

  // Preserve original order when picking strongest N
  function slidesOrderOf(a, b, chunks) {
    const ai = chunks.findIndex(c => c.includes((a.title || '').slice(0, 12)));
    const bi = chunks.findIndex(c => c.includes((b.title || '').slice(0, 12)));
    return ai - bi;
  }

  // ── semantic-rec library — word-level swaps tuned by audience ──
  // These are SURFACE moves: same idea, sharper words. Distinct from
  // structural / content recs (merge, bridge, orphan) which change WHAT
  // the deck argues, not HOW it argues it. The UI shows both as tracks.
  const SEMANTIC_SWAPS = {
    'utilize':      { to: 'use',      why: 'shorter, no register cost' },
    'leverage':     { to: 'use',      why: 'corporate filler, rarely earned' },
    'facilitate':   { to: 'enable',   why: 'one syllable shorter, same meaning' },
    'demonstrate':  { to: 'show',     why: 'demonstrate is a stage word, show is plain' },
    'commence':     { to: 'start',    why: 'commence reads bureaucratic' },
    'terminate':    { to: 'end',      why: 'simpler, less corporate' },
    'subsequently': { to: 'then',     why: 'replaces a 5-syllable filler' },
    'in order to':  { to: 'to',       why: '"in order to" is always cuttable' },
    'going forward':{ to: 'next',     why: 'verbal padding; "next" lands' },
    'at this point in time': { to: 'now', why: '5 words for one' },
    'with regard to':{ to: 'about',   why: 'corporate distance; plain word' },
  };
  const HEDGE_WORDS = ['might', 'perhaps', 'possibly', 'somewhat', 'arguably', 'kind of', 'sort of', 'fairly', 'rather'];
  const AUDIENCE_TONE_HINTS = {
    exec:       'Exec room: numbers up front, hedging out, decision verbs.',
    customer:   'Customer room: second-person ("you/your"), one ask at the end.',
    conference: 'Conference room: one idea per slide, takeaway-first headlines.',
    status:     'Status room: imperative verbs, owners + dates after every action.',
    oneonone:   '1:1 room: conversational; numbers OK but not the lead.',
    technical:  'Technical room: precise nouns; replace metaphor with the actual mechanism.',
  };

  function buildSemanticRecs(outline, audience) {
    const out = [];
    const fields = (s) => [
      ['title', s.title || ''],
      ...((s.messages || []).map((m, mi) => ['msg' + (mi + 1), m || ''])),
      ['bumper', s.bumper || ''],
    ];
    outline.forEach((s, si) => {
      for (const [field, text] of fields(s)) {
        if (!text) continue;
        const lower = text.toLowerCase();
        for (const [bad, info] of Object.entries(SEMANTIC_SWAPS)) {
          if (lower.includes(bad)) {
            out.push({
              id: `swap-${si}-${field}-${bad.replace(/\s+/g, '_')}`,
              kind: 'word-swap',
              track: 'semantic',
              // Structured fields so sbAcceptRec can apply the mutation
              // deterministically — no string-parsing the rec text.
              slideIdx: si,
              field,
              badWord: bad,
              goodWord: info.to,
              text: `Slide ${String(si + 1).padStart(2, '0')} (${field}) — swap "${bad}" → "${info.to}". ${info.why}.`,
            });
            if (out.length >= 8) return;
          }
        }
        if (audience === 'exec' || audience === 'conference') {
          for (const h of HEDGE_WORDS) {
            const re = new RegExp(`\\b${h}\\b`, 'i');
            if (re.test(text)) {
              out.push({
                id: `hedge-${si}-${field}-${h}`,
                kind: 'hedge',
                track: 'semantic',
                slideIdx: si,
                field,
                hedgeWord: h,
                text: `Slide ${String(si + 1).padStart(2, '0')} (${field}) — drop "${h}". ${audience === 'exec' ? 'Exec room reads hedges as no-confidence.' : 'Conference room loses the room when hedging.'}`,
              });
              if (out.length >= 8) return;
            }
          }
        }
        if (audience === 'customer' && field !== 'title' && !/\byou\b|\byour\b/i.test(text)) {
          out.push({
            id: `you-${si}-${field}`,
            kind: 'second-person',
            track: 'semantic',
            slideIdx: si,
            field,
            text: `Slide ${String(si + 1).padStart(2, '0')} (${field}) — no "you" / "your". Customer rooms drift when copy is third-person.`,
          });
          if (out.length >= 8) return;
        }
      }
    });
    // Always lead semantic track with the room-tone hint so users can see
    // what the engine is tuning for, even if no specific swaps fire.
    if (audience && AUDIENCE_TONE_HINTS[audience]) {
      out.unshift({
        id: 'tone-' + audience,
        kind: 'tone',
        track: 'semantic',
        advisory: true,
        text: AUDIENCE_TONE_HINTS[audience],
      });
    }
    return out.slice(0, 8);
  }

  function buildRecommendations(outline, mode, audience) {
    const recs = [];
    if (mode === 'condense' && outline.length >= 2) {
      // 1. Detect duplicate titles
      const titles = outline.map(s => (s.title || '').toLowerCase().trim());
      titles.forEach((t, i) => {
        if (!t) return;
        const j = titles.findIndex((u, k) => k > i && u === t);
        if (j > -1) {
          recs.push({
            id: 'dup-' + i + '-' + j,
            kind: 'merge',
            text: `Slides ${String(i + 1).padStart(2, '0')} and ${String(j + 1).padStart(2, '0')} repeat "${outline[i].title}". Merge them?`,
            slideIds: [outline[i].id, outline[j].id],
          });
        }
      });
      // 2. Missing setup slide (first slide is a stat, not a setup)
      const first = outline[0];
      if (first && /\b\d/.test(first.title) && !/intro|overview|context|setup|summary/i.test(first.title)) {
        recs.push({
          id: 'add-setup',
          kind: 'add-setup',
          text: 'No setup slide — the deck opens cold on a number. Add a context slide at the start?',
        });
      }
      // 3. Audience-shaped recommendations
      if (audience === 'exec' && outline.length > 5) {
        recs.push({
          id: 'exec-shorter',
          kind: 'trim',
          text: 'Execs typically need 3–4 slides. Drop the weakest ' + (outline.length - 4) + '?',
          slideIds: outline.slice(4).map(s => s.id),
        });
      }
      if (audience === 'conference' && outline.some(s => (s.messages || []).filter(Boolean).length > 2)) {
        recs.push({
          id: 'conf-thin',
          kind: 'thin',
          text: 'Conference talks land best with 1–2 messages per slide. Thin out the dense ones?',
        });
      }
      if (audience === 'status' && outline.length > 0 && !outline.some(s => /action|next|todo|owner|by:/i.test(s.title + ' ' + (s.messages || []).join(' ')))) {
        recs.push({
          id: 'status-actions',
          kind: 'add-actions',
          text: 'No action items detected. Add a closing slide with next steps and owners?',
        });
      }
    }

    // ── Thread / narrative analysis (runs on any multi-slide deck) ──
    if (outline.length >= 2) {
      const STOPS = new Set(['the','a','an','and','or','of','to','for','in','on','at','is','it','this','that','with','from','as','by','be','are','was','were','but','so','if','we','our','you','your','their','they','will','can','have','has','had','about','into','than','then','what','which','who','one','more','less','most','any','some','no']);
      const tok = (s) => new Set(((s||'').toLowerCase().match(/\b[a-z][a-z0-9]+\b/g) || []).filter(w => !STOPS.has(w)));
      const slideTokens = outline.map(s => tok([s.title || '', ...((s.messages || [])), s.bumper || ''].join(' ')));

      // (a) Spine candidate: word in 3+ slides — strongest spine candidate
      const wordCounts = new Map();
      slideTokens.forEach(t => t.forEach(w => wordCounts.set(w, (wordCounts.get(w) || 0) + 1)));
      const candidates = [...wordCounts.entries()].filter(([_, c]) => c >= 3).sort((a, b) => b[1] - a[1]);
      if (candidates.length > 0 && outline.length >= 3) {
        const [word, count] = candidates[0];
        recs.push({
          id: 'spine-' + word,
          kind: 'spine',
          advisory: true,
          text: `"${word}" appears in ${count} of ${outline.length} slides — your strongest spine candidate. Promote it into every slide title to make the through-line obvious.`,
        });
      }

      // (b) Orphan slides — no shared content with any other slide
      slideTokens.forEach((t, i) => {
        if (t.size === 0) return;
        const sharesWithAny = slideTokens.some((other, j) => j !== i && [...t].some(w => other.has(w)));
        if (!sharesWithAny) {
          recs.push({
            id: 'orphan-' + outline[i].id,
            kind: 'orphan',
            advisory: true,
            text: `Slide ${String(i + 1).padStart(2, '0')} ("${(outline[i].title || 'untitled').slice(0, 40)}") shares no keywords with any other slide. It reads as an orphan — add a thread that ties it in.`,
          });
        }
      });

      // (c) Hard gaps — adjacent slides with zero shared concepts
      for (let i = 0; i + 1 < outline.length; i++) {
        const a = slideTokens[i], b = slideTokens[i + 1];
        if (a.size === 0 || b.size === 0) continue;
        const shared = [...a].some(w => b.has(w));
        if (!shared) {
          recs.push({
            id: 'gap-' + i,
            kind: 'gap',
            advisory: true,
            text: `Hard cut between slide ${String(i + 1).padStart(2, '0')} and ${String(i + 2).padStart(2, '0')} — no shared concepts. Add a bridging bumper or rework the next title.`,
          });
        }
      }

      // (d) Bridge concepts — words in slide N and N+2 but absent from N+1
      for (let i = 0; i + 2 < outline.length; i++) {
        const a = slideTokens[i], b = slideTokens[i + 1], c = slideTokens[i + 2];
        const skipped = [...a].filter(w => c.has(w) && !b.has(w));
        if (skipped.length > 0 && recs.filter(r => r.kind === 'bridge').length < 3) {
          recs.push({
            id: 'bridge-' + i,
            kind: 'bridge',
            advisory: true,
            text: `Slides ${String(i + 1).padStart(2, '0')} and ${String(i + 3).padStart(2, '0')} share "${skipped[0]}" but slide ${String(i + 2).padStart(2, '0')} drops it. Weave "${skipped[0]}" through the middle slide to bridge the idea.`,
          });
        }
      }
    }
    // Tag everything above as the 'content' track (structural moves —
    // merge slides, bridge concepts, fix orphans, promote spine, add
    // setup/action slides). Then concat the 'semantic' track (word-level
    // swaps + room-tone hints).
    for (const r of recs) if (!r.track) r.track = 'content';
    const semantic = buildSemanticRecs(outline, audience);
    return recs.concat(semantic);
  }

  // Heuristic splitter — splits a blob into slide-sized chunks at lines that
  // look like headings (Title Case ≤ 80 chars, no terminal punctuation) or
  // numbered headers ("1. Intro", "Section 2 — …").
  function splitOnHeadings(text) {
    const lines = text.split('\n');
    const out = [];
    let buf = [];
    const flush = () => { if (buf.length) { out.push(buf.join('\n').trim()); buf = []; } };
    const isHeading = (line) => {
      const t = line.trim();
      if (!t) return false;
      if (t.length > 80) return false;
      if (/[.!?,;:]$/.test(t)) return false;
      // numbered like "1." or "Section X" or "Slide N"
      if (/^(?:\d+[\.\)]|section|slide|chapter|part)\s/i.test(t)) return true;
      // mostly Title Case
      const words = t.split(/\s+/).filter(Boolean);
      if (words.length === 0) return false;
      const cap = words.filter(w => /^[A-Z]/.test(w)).length;
      return cap / words.length >= 0.6 && words.length >= 2 && words.length <= 10;
    };
    for (const line of lines) {
      if (isHeading(line) && buf.length > 0) flush();
      if (line.trim()) buf.push(line);
    }
    flush();
    // If we ended up with too many small chunks, recombine
    if (out.length > 8) {
      const recombined = [];
      let group = [];
      out.forEach((c, i) => {
        group.push(c);
        if (group.length >= Math.ceil(out.length / 5)) {
          recombined.push(group.join('\n\n'));
          group = [];
        }
      });
      if (group.length) recombined.push(group.join('\n\n'));
      return recombined;
    }
    if (out.length === 0) return [text];
    return out;
  }

  function textToSlide(chunk, n) {
    const lines = chunk.split('\n').map(l => l.trim()).filter(Boolean);
    const splitSentences = (s) =>
      s.split(/(?<=[.!?])\s+/).map(t => t.trim()).filter(t => t.length >= 4);

    // Decide title vs body:
    //   - Multi-line: line 1 is title, rest is body.
    //   - One line with multiple sentences: first sentence is title,
    //     remaining sentences are body. Avoids the "title eats the whole
    //     paragraph" bug when input has no internal newlines.
    //   - Short single line: it's the title; no body.
    let title;
    let bodyUnits;
    if (lines.length === 0) {
      title = 'Untitled slide';
      bodyUnits = [];
    } else if (lines.length === 1) {
      const sents = splitSentences(lines[0]);
      if (sents.length >= 2) {
        title = sents[0];
        bodyUnits = sents.slice(1);
      } else {
        title = lines[0];
        bodyUnits = [];
      }
    } else {
      title = lines[0];
      bodyUnits = lines.slice(1).flatMap(splitSentences);
    }

    const allMsgs = bodyUnits;
    const messages = allMsgs.slice(0, 3);
    while (messages.length < 3) messages.push('');

    // Bumper: the LAST body line — the "and then…" line that ought to set up
    // the next slide. Skip if it would duplicate the last message.
    let bumper = '';
    if (allMsgs.length > 3) {
      bumper = allMsgs[allMsgs.length - 1];
    } else if (allMsgs.length === 3 && allMsgs[2].length < 60) {
      // short third line — treat it as the bumper instead of message 3
      bumper = allMsgs[2];
    }

    return {
      id: 's' + n + '-' + Math.random().toString(36).slice(2, 6),
      title: title.length > 100 ? title.slice(0, 100) + '…' : title,
      messages: messages.map(m => m.length > 180 ? m.slice(0, 180) + '…' : m),
      bumper: bumper.length > 140 ? bumper.slice(0, 140) + '…' : bumper,
    };
  }

  function emptySlide(n) {
    return {
      id: 's' + n + '-' + Math.random().toString(36).slice(2, 6),
      title: '',
      messages: ['', '', ''],
      bumper: '',
    };
  }

  window.extractStoryboard = extractStoryboard;

  // ── Adversarial commentary (audience + mode + content shaped) ──
  // Returns { voice, criticisms[], questions[] } the workbench's critique
  // page renders as cards. Swap-for-fetch like everything else.
  const CRITIQUES_BY_AUDIENCE = {
    exec: {
      voice: 'an Exec',
      criticisms: [
        { id: 'a-exec-1', sev: 'high', text: 'There\u2019s no bottom-line on the title slide. Execs scan the title + slide 1 — both should already say "do X".' },
        { id: 'a-exec-2', sev: 'med',  text: 'Three messages per slide is dense for exec attention. Two would land harder.' },
        { id: 'a-exec-3', sev: 'med',  text: 'Numbers without comparison framing ("vs plan", "vs last quarter") read as bragging instead of evidence.' },
      ],
      questions: [
        { id: 'q-exec-1', text: 'What does this change in next quarter\u2019s plan?' },
        { id: 'q-exec-2', text: 'Who owns the next step, and by when?' },
        { id: 'q-exec-3', text: 'What\u2019s the cost of not acting on this?' },
        { id: 'q-exec-4', text: 'Where do you need me to clear a blocker?' },
      ],
    },
    customer: {
      voice: 'a Customer',
      criticisms: [
        { id: 'a-cust-1', sev: 'high', text: 'Speaks in your team\u2019s language, not the customer\u2019s. Translate "GTM" \u2192 "what we\u2019re shipping".' },
        { id: 'a-cust-2', sev: 'med',  text: 'No before/after the customer can see. They want "what changes for me".' },
        { id: 'a-cust-3', sev: 'low',  text: 'Heavy on metrics, light on stories. One customer name lands harder than three percentages.' },
      ],
      questions: [
        { id: 'q-cust-1', text: 'When will this be available to us?' },
        { id: 'q-cust-2', text: 'What does my team need to do to use it?' },
        { id: 'q-cust-3', text: 'Is there a price or contract change?' },
        { id: 'q-cust-4', text: 'What support comes with this?' },
      ],
    },
    conference: {
      voice: 'a Conference room',
      criticisms: [
        { id: 'a-conf-1', sev: 'high', text: 'No clear contribution statement. A senior researcher will ask "what\u2019s new here" within 90 seconds.' },
        { id: 'a-conf-2', sev: 'med',  text: 'Missing prior-art comparison. The first question will be "how does this differ from X".' },
        { id: 'a-conf-3', sev: 'med',  text: 'Middle slides read like internal status. Cut them or reframe as method/result.' },
      ],
      questions: [
        { id: 'q-conf-1', text: 'How does this compare to the baseline published at last year\u2019s venue?' },
        { id: 'q-conf-2', text: 'What\u2019s your ablation? Which component matters most?' },
        { id: 'q-conf-3', text: 'Is the dataset and code available?' },
        { id: 'q-conf-4', text: 'What\u2019s the failure mode?' },
      ],
    },
    status: {
      voice: 'a Status meeting',
      criticisms: [
        { id: 'a-stat-1', sev: 'high', text: 'No actions, owners, or dates. A status without those is a story without a plot.' },
        { id: 'a-stat-2', sev: 'med',  text: 'Risk slide is missing — every status reader scans for "what could blow up".' },
        { id: 'a-stat-3', sev: 'low',  text: 'Too many wins, not enough surface area on the blockers.' },
      ],
      questions: [
        { id: 'q-stat-1', text: 'What\u2019s blocked right now, and who can unblock it?' },
        { id: 'q-stat-2', text: 'What slipped since last week?' },
        { id: 'q-stat-3', text: 'Are we still on the original date?' },
        { id: 'q-stat-4', text: 'What needs a decision from this group?' },
      ],
    },
    oneonone: {
      voice: 'your 1:1 partner',
      criticisms: [
        { id: 'a-1on1-1', sev: 'med', text: 'This reads like a deck, not a conversation. A 1:1 hangs on one chart and two questions.' },
        { id: 'a-1on1-2', sev: 'med', text: 'No "I need" or "I\u2019d like your input on…". The other person leaves unsure what to do.' },
        { id: 'a-1on1-3', sev: 'low', text: 'Too polished — your manager will ask "what\u2019s the rough draft?" if it looks final.' },
      ],
      questions: [
        { id: 'q-1on1-1', text: 'What do you actually want from me here?' },
        { id: 'q-1on1-2', text: 'What\u2019s your gut say, before you show me the data?' },
        { id: 'q-1on1-3', text: 'Which of these are you not sure about?' },
      ],
    },
    technical: {
      voice: 'a Technical reviewer',
      criticisms: [
        { id: 'a-tech-1', sev: 'high', text: 'Result first, derivation second. Engineers won\u2019t trust a result until they see the math behind it.' },
        { id: 'a-tech-2', sev: 'med',  text: 'Numbers without uncertainty (error bars / CI) — the room will discount them.' },
        { id: 'a-tech-3', sev: 'med',  text: 'No "I considered approach X and rejected it because Y". Without that, "why this approach" is the first question.' },
      ],
      questions: [
        { id: 'q-tech-1', text: 'What\u2019s the failure mode at the extremes?' },
        { id: 'q-tech-2', text: 'Did you try the obvious alternative? Why not?' },
        { id: 'q-tech-3', text: 'How robust is this to noise or adversarial input?' },
        { id: 'q-tech-4', text: 'Can you reproduce this with the same parameters?' },
      ],
    },
  };

  const CRITIQUES_BY_MODE = {
    draft: [
      { id: 'm-draft-1', sev: 'low', kind: 'criticism', text: 'One slide is brave. Make sure it earns that — every other concept gets cut.' },
    ],
    refine: [
      { id: 'm-refine-1', sev: 'med', kind: 'criticism', text: 'Did the rework actually fix the gap you flagged, or just polish?' },
    ],
    condense: [
      { id: 'm-cond-1', sev: 'med', kind: 'criticism', text: 'What got cut, and does the full deck still exist for follow-up?' },
    ],
    visualize: [
      { id: 'm-vis-1',  sev: 'med', kind: 'criticism', text: 'Parameter ranges define the story. Pick ranges that show the edge cases, not just the comfortable zone.' },
      { id: 'm-vis-2',  sev: 'low', kind: 'question',  text: 'What happens outside this plot range?' },
    ],
    synthesize: [
      { id: 'm-syn-1',  sev: 'high', kind: 'criticism', text: 'Where is this data from, and what window was selected? Pick that window honestly or someone will ask.' },
      { id: 'm-syn-2',  sev: 'med',  kind: 'question',  text: 'What\u2019s the sample size and confidence interval?' },
    ],
  };

  async function generateCritique(req) {
    await new Promise(r => setTimeout(r, 380));
    const audience = req.audience || 'exec';
    const mode     = req.mode || 'draft';
    const outline  = req.outline || [];
    const aud = CRITIQUES_BY_AUDIENCE[audience] || CRITIQUES_BY_AUDIENCE.exec;

    const criticisms = aud.criticisms.map(c => ({ ...c, source: 'audience', kind: 'criticism' }));
    const questions  = aud.questions.map(q  => ({ ...q,  source: 'audience', kind: 'question' }));

    const modeAdds = CRITIQUES_BY_MODE[mode] || [];
    for (const m of modeAdds) {
      if (m.kind === 'question') questions.push({ ...m, source: 'mode' });
      else                       criticisms.push({ ...m, source: 'mode' });
    }

    // Content-aware probes (mock heuristics)
    if (audience === 'status' && outline.length > 0 &&
        !outline.some(s => /action|next step|owner|by:|by \w/i.test(s.title + ' ' + (s.messages || []).join(' ') + ' ' + (s.bumper || '')))) {
      criticisms.push({
        id: 'c-content-1', sev: 'high', source: 'content', kind: 'criticism',
        text: 'No action items detected anywhere in the deck. A status meeting will ask "who, by when" within 30 seconds.',
      });
    }
    if (audience === 'exec' && outline.length > 4) {
      criticisms.push({
        id: 'c-content-2', sev: 'med', source: 'content', kind: 'criticism',
        text: `${outline.length} slides for an exec is a lot. They want 3 — slide 01 telling them what to do, 02 why, 03 the anchor number.`,
      });
    }
    const cells = outline.flatMap(s => [s.title, ...(s.messages || [])]).filter(Boolean);
    const numericCells = cells.filter(t => /\b\d/.test(t)).length;
    if (cells.length > 0 && numericCells / cells.length > 0.55) {
      criticisms.push({
        id: 'c-content-3', sev: 'med', source: 'content', kind: 'criticism',
        text: 'The deck is dense with numbers — most cells contain a digit. Each needs a sentence telling the room what it means.',
      });
    }
    if (outline.length > 0 && outline.every(s => (s.messages || []).filter(Boolean).length >= 3)) {
      criticisms.push({
        id: 'c-content-4', sev: 'low', source: 'content', kind: 'criticism',
        text: 'Every slide carries the maximum 3 messages. Some should breathe — a single message slide is a power move.',
      });
    }
    return { voice: aud.voice, criticisms, questions };
  }

  window.generateCritique = generateCritique;

  // ─────────────────────────────────────────────────────────────
  // Client-side fallback for /api/thread_map (Netlify static build)
  // Lexical-only token overlap — same shape as backend's _view_lexical.
  // Honest limitation: misses paraphrase/synonyms. ThreadMapView calls
  // this when the real /api/thread_map fetch fails.
  // ─────────────────────────────────────────────────────────────
  const _STOPS = new Set([
    'the','a','an','and','or','of','to','for','in','on','at','is','it','this',
    'that','with','from','as','by','be','are','was','were','but','so','if',
    'we','our','you','your','their','they','will','can','have','has','had',
    'about','into','than','then','what','which','who','one','more','less',
    'most','any','some','no',
  ]);
  function _tok(s) {
    const out = new Set();
    const matches = String(s || '').toLowerCase().match(/\b[a-z][a-z0-9]+\b/g) || [];
    for (const w of matches) if (!_STOPS.has(w) && w.length >= 3) out.add(w);
    return out;
  }
  function _slideText(slide) {
    const parts = [slide.title || ''];
    for (const m of (slide.messages || [])) parts.push(m || '');
    parts.push(slide.bumper || '');
    return parts.filter(Boolean).join(' ');
  }
  function _viewLexical(outline) {
    const slideTokens = outline.map(s => _tok(_slideText(s)));
    const nodes = outline.map((s, i) => ({
      id: s.id || `s${i}`,
      index: i,
      title: (s.title || '').trim() || `Slide ${i + 1}`,
      concept_count: slideTokens[i].size,
    }));
    const edges = [];
    for (let i = 0; i < slideTokens.length; i++) {
      for (let j = i + 1; j < slideTokens.length; j++) {
        const shared = [];
        for (const w of slideTokens[i]) if (slideTokens[j].has(w)) shared.push(w);
        if (shared.length === 0) continue;
        edges.push({
          from: nodes[i].id,
          to:   nodes[j].id,
          weight: shared.length,
          shared: shared.sort().slice(0, 6),
          adjacent: (j - i === 1),
        });
      }
    }
    const orphanIds = [];
    for (let i = 0; i < slideTokens.length; i++) {
      const ts = slideTokens[i];
      if (ts.size === 0) { orphanIds.push(nodes[i].id); continue; }
      let shares = false;
      for (let j = 0; j < slideTokens.length; j++) {
        if (j === i) continue;
        for (const w of ts) { if (slideTokens[j].has(w)) { shares = true; break; } }
        if (shares) break;
      }
      if (!shares) orphanIds.push(nodes[i].id);
    }
    const counts = {};
    for (const ts of slideTokens) for (const w of ts) counts[w] = (counts[w] || 0) + 1;
    const spinePairs = Object.entries(counts)
      .filter(([, c]) => c >= 2)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    let spine = null;
    const spineFloor = Math.max(3, Math.floor((outline.length + 1) / 2));
    if (spinePairs.length > 0 && spinePairs[0][1] >= spineFloor) {
      const [word, count] = spinePairs[0];
      spine = {
        word, count,
        slides: outline
          .map((_, i) => slideTokens[i].has(word) ? nodes[i].id : null)
          .filter(Boolean),
      };
    }
    const gaps = [];
    for (let i = 0; i < slideTokens.length - 1; i++) {
      const a = slideTokens[i], b = slideTokens[i + 1];
      if (a.size > 0 && b.size > 0) {
        let shares = false;
        for (const w of a) if (b.has(w)) { shares = true; break; }
        if (!shares) gaps.push({ from: nodes[i].id, to: nodes[i + 1].id });
      }
    }
    const ribbons = [];
    const sortedCounts = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    for (const [word, count] of sortedCounts) {
      if (count < 2) continue;
      const slidesIn = outline.map((_, i) => slideTokens[i].has(word) ? i : -1).filter(i => i >= 0);
      const hasGap = (Math.max(...slidesIn) - Math.min(...slidesIn) + 1) !== slidesIn.length;
      ribbons.push({
        token: word,
        slides: slidesIn,
        weight: count,
        broken: hasGap,
        is_spine: (spine !== null && word === spine.word),
      });
      if (ribbons.length >= 8) break;
    }
    const n = outline.length;
    const orphanRate = n > 0 ? orphanIds.length / n : 0;
    const gapRate = n > 1 ? gaps.length / (n - 1) : 0;
    const spinePenalty = spine ? 0 : 0.35;
    const messiness = Math.min(1.0, 0.45 * orphanRate + 0.35 * gapRate + spinePenalty);
    return {
      graph: { nodes, edges, orphans: orphanIds, spine, gaps },
      ribbons,
      stats: {
        slides: n,
        orphans: orphanIds.length,
        gaps: gaps.length,
        edges: edges.length,
        ribbons: ribbons.length,
        spine_word: spine ? spine.word : null,
        messiness: Math.round(messiness * 1000) / 1000,
      },
      engine: 'lexical',
    };
  }
  async function computeThreadMapLocal(req) {
    const outline = req.outline || [];
    const recs = req.recommendations || [];
    const accepted = new Set(req.acceptedIds || []);
    const mode = req.mode || 'potential';
    const applicable = (mode === 'accepted')
      ? recs.filter(r => accepted.has(r.id))
      : recs.slice();
    const before = _viewLexical(outline);
    // Simulated AFTER: pretend each applied advisory removes one orphan or
    // one hard cut. Doesn't mutate the outline — purely a visible delta so
    // the BEFORE/AFTER comparison reads as meaningful in the mock path.
    const after = _viewLexical(outline);
    let drops = applicable.length;
    while (drops > 0 && (after.graph.gaps.length > 0 || after.graph.orphans.length > 0)) {
      if (after.graph.gaps.length > 0) after.graph.gaps.pop();
      else if (after.graph.orphans.length > 0) after.graph.orphans.pop();
      drops--;
    }
    after.stats.gaps    = after.graph.gaps.length;
    after.stats.orphans = after.graph.orphans.length;
    const orphanRateA = outline.length > 0 ? after.graph.orphans.length / outline.length : 0;
    const gapRateA    = outline.length > 1 ? after.graph.gaps.length / (outline.length - 1) : 0;
    const spinePenaltyA = after.graph.spine ? 0 : 0.35;
    after.stats.messiness = Math.round(
      Math.min(1.0, 0.45 * orphanRateA + 0.35 * gapRateA + spinePenaltyA) * 1000
    ) / 1000;
    return {
      before, after,
      diff: {},
      applied: applicable.map(r => r.id),
      mode,
    };
  }
  window.computeThreadMapLocal = computeThreadMapLocal;
})();
