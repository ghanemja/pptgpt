/* ============================================================
   ws-data.js — "chart this" understood deterministically.

   When a prompt asks for a chart, two things decide what happens:
   whether it is asking, and whether the numbers to chart are already
   somewhere the engine can see. Both are read here, in the engine, by
   rule — no model is asked to decide either, so the same prompt always
   behaves the same way.

   Numbers already in context come from the prompt itself, then the
   slide being worked on, then the deck, then the scope brief. If none
   of those carry a series, the engine asks for one rather than
   inventing numbers — fabricating data onto a chart is the worst thing
   this program could do.
   ============================================================ */
(function () {
  'use strict';

  const CHART_WORDS = /\b(chart|graph|plot|visuali[sz]e|visuali[sz]ation|diagram|bar|bars|column|columns|pie|donut|doughnut|line|trend|trendline|breakdown|distribution|histogram)\b/i;
  // "a slide about bar staffing" is not a chart request; these say it is.
  const INTENT_WORDS = /\b(chart|graph|plot|visuali[sz]e|visuali[sz]ation|diagram|trend|breakdown|distribution|histogram)\b/i;

  const KIND_WORDS = [
    [/\b(pie|donut|doughnut|share of|split of|proportion)\b/i, 'pie'],
    [/\b(line|trend|trendline|over time|month over month|quarter over quarter|growth curve)\b/i, 'line'],
    [/\b(area|cumulative|stacked area)\b/i, 'area'],
    [/\b(horizontal bar|bar chart|ranked|ranking|leaderboard)\b/i, 'bar'],
    [/\b(column|vertical bar|bar)\b/i, 'column'],
  ];

  /* ── what KIND of visual, and how sure are we ──────────────────
     "Flow chart" contains the word chart and is not one: it asks for a
     process, and answering it with bars was both wrong and confident about
     it. Asks are resolved into a family first (a data chart, or a diagram
     of steps), then a specific kind, with a confidence. Named exactly, the
     engine builds it. Named vaguely — "add a chart" — it offers the kinds
     that fit the data rather than guessing silently. */

  const FLOW_WORDS = /\b(flow ?chart|flow|process|workflow|pipeline|journey|sequence|steps|stages|funnel|lifecycle)\b/i;
  const STEP_SPLIT = /\s*(?:→|->|=>|➔|then|next|followed by|;)\s*|\s*\n\s*/i;

  /* Steps read out of an ask: "A → B → C", "1. A 2. B", or bullet lines. */
  function extractSteps(text) {
    const t = String(text || '');
    const after = t.replace(/^[^:]*:\s*/, '');            // drop "flow chart of:"
    let parts = after.split(STEP_SPLIT).map(x => x.trim()).filter(Boolean);
    // "1. plan 2. build 3. ship" is one chunk to the splitter above, so the
    // numbering itself has to be the separator.
    if (parts.length < 2 && /\d+[.)]\s/.test(after)) {
      parts = after.split(/\s*\d+[.)]\s*/).map(x => x.trim()).filter(Boolean);
    }
    if (parts.length < 2) {
      parts = after.split(/\s*,\s*/).map(x => x.trim()).filter(Boolean);
    }
    parts = parts
      .map(x => x.replace(/^\d+[.)]\s*/, '').replace(/^[-•]\s*/, '').trim())
      .filter(x => x && x.length <= 48);
    return parts.length >= 2 ? parts.slice(0, 7) : [];
  }

  /* Candidate chart kinds for a given series, best first. Data shape is the
     evidence: four quarters is a trend, three segments summing to a whole is
     a split, ten rows is a ranking. */
  function chartOptionsFor(rows) {
    const n = rows.length;
    const looksTemporal = rows.every(r => /^(q[1-4]|fy\d|\d{4}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|mon|tue|wed|thu|fri|sat|sun|week|wk ?\d|m\d)/i.test(String(r.label).trim()));
    if (looksTemporal) return ['line', 'column', 'area'];
    if (n <= 5) return ['column', 'pie', 'bar'];
    return ['bar', 'column', 'line'];
  }

  /* Does this prompt ask for a visual? */
  function wantsChart(text) {
    const t = String(text || '');
    if (!CHART_WORDS.test(t)) return false;
    // A bare "bar" or "line" only counts alongside a verb that asks for one.
    if (INTENT_WORDS.test(t)) return true;
    return /\b(show|make|add|draw|give|include|build|create|put)\b/i.test(t);
  }

  function chartKind(text) {
    const t = String(text || '');
    for (const [re, kind] of KIND_WORDS) if (re.test(t)) return kind;
    return 'column';
  }

  const NUM = '(-?\\d[\\d,]*(?:\\.\\d+)?)\\s*(%|[kKmM]|[bB][nN]?)?';

  // Words that mean a run of text is a sentence, not a label. Without this,
  // "we beat plan by 14% and retention is 118%" charts two bars called
  // "we beat plan by" and "and retention is".
  const PROSE = new Set(('we i you they it he she this that these those and or but if then than '
    + 'is are was were be been being am do does did has have had will would can could should '
    + 'by of to in on for with at from into over under about as our your their his her its '
    + 'the a an up down out off so because while when which who whom whose there here').split(' '));

  function looksLikeLabel(name) {
    const words = name.split(/\s+/).filter(Boolean);
    if (!words.length || words.length > 3) return false;
    return !words.some(w => PROSE.has(w.toLowerCase().replace(/[^a-z]/g, '')));
  }

  const SCALE = { k: 1e3, m: 1e6, b: 1e9, bn: 1e9 };

  function toNumber(raw) {
    const n = parseFloat(String(raw).replace(/,/g, ''));
    return isFinite(n) ? n : null;
  }

  /* People write "1.2M", and an axis that reads 1200000 is worse than one
     that reads 1.2 with "in M" over it. The scale is kept as a UNIT rather
     than multiplied into the numbers — but only when every point shares it,
     because mixing 1.2M with 900k and calling them both "M" would lie. */
  function unitOf(rows) {
    const suffixes = rows.map(r => (r.suffix || '').toLowerCase());
    const first = suffixes[0];
    if (!first || !suffixes.every(x => x === first)) return '';
    if (first === '%') return '%';
    return SCALE[first] ? first.toUpperCase() : '';
  }

  /* Pull label/value pairs out of prose.

     Three shapes cover almost everything people paste: "Q1 32, Q2 38",
     "SMB: 1.2", and "revenue 14%". Anything that yields fewer than two
     points is not a series and is rejected — one number is a stat, and a
     chart of one bar is a worse way to say it. */
  function extractSeries(text) {
    const t = String(text || '');
    const out = [];
    const seen = new Set();

    const push = (label, raw, suffix) => {
      const value = toNumber(raw);
      const name = String(label || '').trim().replace(/[:\-–—]+$/, '').trim();
      if (value === null || !name || name.length > 28) return;
      if (!looksLikeLabel(name)) return;
      const key = name.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      out.push({ label: name, value, hi: false, suffix: suffix || '' });
    };

    // "Q1 32" / "Q1: 32" / "Q1 = 32" / "SMB — 1.2"
    //
    // The separator is required. Optional, a lazy label matches "Q" and the
    // value matches the "1" out of "Q1", turning four quarters into four
    // points named Q with values 1..4.
    const pairRe = new RegExp('([A-Za-z][A-Za-z0-9 .&/\'+-]{0,27}?)(?:\\s*[:=—–-]\\s*|\\s+)' + NUM + '(?=\\s*(?:,|;|\\.|\\n|$|\\s))', 'gi');
    let m;
    while ((m = pairRe.exec(t)) !== null) push(m[1], m[2], m[3]);

    // "32 in Q1" — value first
    if (out.length < 2) {
      const flipRe = new RegExp(NUM + '\\s+(?:in|for|during|at)\\s+([A-Za-z][A-Za-z0-9 .&/\'+-]{0,27})', 'gi');
      while ((m = flipRe.exec(t)) !== null) push(m[3], m[1], m[2]);
    }

    return out.length >= 2 ? out.slice(0, 12) : [];
  }

  /* Everywhere the engine may look for numbers, nearest first. The prompt
     wins, then the slide in hand, then the deck, then the brief. */
  function contextSources({ prompt, slide, deck, scope, chat }) {
    const src = [];
    if (prompt) src.push({ where: 'your message', text: String(prompt) });
    if (slide) {
      src.push({ where: 'this slide', text: [slide.title, slide.metric, slide.metricSub,
        ...(slide.bullets || []), slide.takeaway].filter(Boolean).join('\n') });
    }
    if (deck && deck.slides) {
      for (const s of deck.slides) {
        if (slide && s.id === slide.id) continue;
        if (s.chart && (s.chart.data || []).length >= 2) {
          src.push({ where: `slide "${s.title || 'untitled'}"`, rows: s.chart.data });
        }
        src.push({ where: `slide "${(s.title || 'untitled').slice(0, 28)}"`,
          text: [s.metric, s.metricSub, ...(s.bullets || [])].filter(Boolean).join('\n') });
      }
    }
    if (scope) {
      const vals = Object.entries(scope)
        .filter(([k]) => !k.startsWith('__'))
        .map(([, v]) => String(v || ''));
      if (vals.length) src.push({ where: 'the brief', text: vals.join('\n') });
    }
    if (chat && chat.length) {
      src.push({ where: 'the conversation',
        text: chat.slice(-6).map(c => c.text || '').join('\n') });
    }
    return src;
  }

  /* The first place that actually holds a series. Returns null when the
     engine would have to make the numbers up. */
  function findSeries(ctx) {
    for (const s of contextSources(ctx)) {
      if (s.rows && s.rows.length >= 2) {
        return { rows: s.rows.map(r => ({ ...r })), where: s.where };
      }
      const rows = extractSeries(s.text);
      if (rows.length) return { rows, where: s.where };
    }
    return null;
  }

  /* A chart slide built from numbers that already exist. */
  function buildChartSlide({ prompt, rows, kind, palette, audience, id, title }) {
    // The prompt usually carries the data after a colon or a dash; that is
    // the instruction, not the headline, so the title stops where it starts.
    const asked = String(prompt || '').split('\n')[0]
      .replace(/^(show|make|add|draw|give|include|build|create|put|chart|plot|graph)\b\s*/i, '')
      .replace(/^\s*(me|a|an|the)\b\s*/i, '')
      .split(/\s*[:—–]\s*|\s+-\s+/)[0]
      .replace(/\b(as|in)\s+a?\s*(chart|graph|plot|pie|bar|column|line|area)\b/ig, '')
      .replace(/[.?!,]+$/, '').trim();
    const headline = (title || '').trim() || asked || 'By the numbers';
    const unit = unitOf(rows);
    const clean = rows.map(r => ({ label: r.label, value: r.value, hi: false }));
    const top = clean.reduce((a, b) => ((b.value || 0) > (a.value || 0) ? b : a), clean[0]);
    rows = clean;
    return {
      id: id || (window.uid ? window.uid() : String(Date.now())),
      kind: 'chart',
      palette: palette || 'warm',
      emphasis: audience === 'conf' ? 'story' : 'number',
      eyebrow: audience === 'exec' ? 'Results' : 'By the numbers',
      title: headline.charAt(0).toUpperCase() + headline.slice(1),
      chart: {
        kind: kind || 'column',
        title: unit ? (unit === '%' ? 'percent' : `in ${unit}`) : '',
        data: rows,
        options: { sort: 'source', highlight: top ? top.label : null, valueLabels: true, gridlines: false },
      },
      takeaway: top ? `${top.label} leads at ${top.value}.` : '',
    };
  }

  /* The whole decision, in one place.

     Returns { family, kind, confidence, options }. `confidence` is 'high'
     when the ask named the kind, or when the data shape leaves one sensible
     answer; 'low' when it did not, which is what makes the UI offer a choice
     instead of picking for you. */
  function visualIntent(text, rows) {
    const t = String(text || '');
    const asked = wantsChart(t);
    const flow = FLOW_WORDS.test(t);

    if (flow) {
      const funnel = /\bfunnel\b/i.test(t);
      const steps = extractSteps(t);
      return {
        family: 'diagram',
        kind: funnel ? 'funnel' : 'flow',
        // Naming "funnel" or "flow chart" is explicit; "steps" alone is not.
        confidence: (funnel || /\bflow ?chart|process|workflow|pipeline\b/i.test(t)) ? 'high' : 'low',
        options: ['flow', 'funnel'],
        steps,
      };
    }

    const named = KIND_WORDS.some(([re]) => re.test(t));
    const hasRows = !!(rows && rows.length);

    // "pie of segment share: SMB 12, Mid 28" names a kind and carries a
    // series; it is an ask even without a verb in front of it.
    if (!asked && !(named && hasRows)) {
      return { family: 'none', kind: null, confidence: 'high', options: [] };
    }

    const opts = hasRows ? chartOptionsFor(rows) : ['column', 'bar', 'line'];

    // Named outright, there is nothing to ask about. Otherwise the DATA may
    // still settle it: a run of quarters is a trend and a long list is a
    // ranking — only a short unordered set is a real fork (column or pie),
    // and that is the one worth asking about.
    let confidence = 'low';
    if (named) confidence = 'high';
    else if (hasRows && opts[0] === 'line') confidence = 'high';
    else if (hasRows && rows.length > 5) confidence = 'high';

    return {
      family: 'chart',
      kind: named ? chartKind(t) : opts[0],
      confidence,
      options: confidence === 'high' ? [] : opts,
    };
  }

  function buildFlowSlide({ prompt, steps, kind, palette, audience, id, title }) {
    const asked = String(prompt || '').split('\n')[0]
      .replace(/^(show|make|add|draw|give|include|build|create|put)\b\s*/i, '')
      .replace(/^\s*(me|a|an|the)\b\s*/i, '')
      .split(/\s*[:—–]\s*/)[0]
      .replace(/[.?!,]+$/, '').trim();
    const headline = (title || '').trim() || asked || 'How it works';
    return {
      id: id || (window.uid ? window.uid() : String(Date.now())),
      kind: 'diagram',
      palette: palette || 'warm',
      emphasis: audience === 'conf' ? 'story' : 'number',
      eyebrow: 'Process',
      title: headline.charAt(0).toUpperCase() + headline.slice(1),
      diagram: { kind: kind || 'flow', steps: steps.slice(0, 7) },
      takeaway: '',
    };
  }

  Object.assign(window, {
    wantsChart, chartKind, extractSeries, findSeries, contextSources, buildChartSlide, unitOf,
    visualIntent, extractSteps, chartOptionsFor, buildFlowSlide,
  });
})();
