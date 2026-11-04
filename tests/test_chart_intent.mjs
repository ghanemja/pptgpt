/* Chart-intent tests (the browser-side rules, run under node).
 *
 * The contract:
 * - A prompt asking for a visual is recognised; prose that merely contains
 *   the word "bar" or "line" is not.
 * - A series is extracted only when there really is one. Two points minimum,
 *   because one number is a stat and a one-bar chart is a worse way to say it.
 * - Prose never becomes labels — this is what stops the engine charting
 *   nonsense scraped out of a sentence.
 * - Nothing is invented: no numbers anywhere means no series, which is what
 *   makes the UI ask instead of generate.
 */
global.window = { uid: () => 'id' };
const { createRequire } = await import('node:module');
const require = createRequire(import.meta.url);
require('../frontend/ws-data.js');
const { wantsChart, chartKind, extractSeries, findSeries, buildChartSlide } = window;

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { console.log(`PASS  ${name}`); pass++; }
  else { console.log(`FAIL  ${name}${detail ? ': ' + detail : ''}`); fail++; }
}

check('asks are recognised',
  ['chart revenue by quarter', 'show me a pie of segment share', 'visualize churn',
   'add a graph of ARR', 'plot the trend'].every(wantsChart));

check('prose is not an ask',
  !['the bar staffing plan needs work', 'we beat plan by 14%',
    'hold the line on pricing'].some(wantsChart));

check('kind is read from the ask',
  chartKind('pie of share') === 'pie' &&
  chartKind('trend over time') === 'line' &&
  chartKind('cumulative area') === 'area' &&
  chartKind('ranked bar chart') === 'bar' &&
  chartKind('chart it') === 'column');

const q = extractSeries('chart revenue: Q1 32, Q2 38, Q3 42, Q4 45');
check('labelled values are extracted whole',
  q.length === 4 && q[0].label === 'Q1' && q[0].value === 32,
  JSON.stringify(q));

check('a scale suffix is kept as a unit, not multiplied in', (() => {
  const rows = extractSeries('SMB 1.2M, Mid 2.1M, Ent 8.4M');
  const slide = buildChartSlide({ prompt: 'chart ARR: SMB 1.2M, Mid 2.1M, Ent 8.4M', rows, kind: 'column' });
  return slide.chart.data[0].value === 1.2 && slide.chart.title === 'in M';
})());

check('a mixed scale is not given a single unit', (() => {
  const rows = extractSeries('SMB 900k, Ent 8.4M');
  const slide = buildChartSlide({ prompt: 'chart it: SMB 900k, Ent 8.4M', rows, kind: 'column' });
  return slide.chart.title === '';
})());

check('prose never becomes labels',
  extractSeries('we beat plan by 14% and retention is 118%').length === 0);

check('one number is not a series',
  extractSeries('retention was 118%').length === 0);

check('two-word labels survive', (() => {
  const r = extractSeries('Net retention 118%, Gross retention 94%, Logo churn 1.8%');
  return r.length === 3 && r[0].label === 'Net retention';
})());

check('context is searched nearest first', (() => {
  const found = findSeries({
    prompt: 'chart retention',
    slide: null,
    deck: { slides: [{ id: 'a', title: 'x', bullets: ['Net retention 118%, Gross retention 94%'] }] },
    scope: { evidence: 'SMB 1, Mid 2, Ent 3' },
  });
  return found && found.rows.length === 2 && /slide/.test(found.where);
})());

check('no numbers anywhere means no series — so the UI asks',
  findSeries({ prompt: 'chart ARR by segment', deck: { slides: [] }, scope: {} }) === null);

check('the headline drops the data and the verb', (() => {
  const p = 'Chart new ARR by segment: SMB 1.2M, Mid 2.1M, Ent 8.4M';
  const slide = buildChartSlide({ prompt: p, rows: extractSeries(p), kind: 'column' });
  return slide.title === 'New ARR by segment';
})());

check('the biggest point is highlighted', (() => {
  const rows = extractSeries('SMB 1.2, Mid 2.1, Ent 8.4');
  const slide = buildChartSlide({ prompt: 'chart it', rows, kind: 'column' });
  return slide.chart.options.highlight === 'Ent';
})());

// ── visual intent: build when sure, offer when not ──────────────────
const { visualIntent, extractSteps, buildFlowSlide } = window;

check('a flow chart is a diagram, not bars', (() => {
  const t = 'make a flow chart of onboarding: sign up -> verify -> invite';
  const i = visualIntent(t, extractSeries(t));
  return i.family === 'diagram' && i.kind === 'flow' && i.confidence === 'high';
})());

check('a funnel is recognised as its own shape', (() => {
  const i = visualIntent('show the funnel: visits, signups, paid', []);
  return i.family === 'diagram' && i.kind === 'funnel' && i.confidence === 'high';
})());

check('steps are read from arrows, commas and numbering', (() => {
  const a = extractSteps('flow: sign up -> verify email -> first deck');
  const b = extractSteps('process: 1. plan 2. build 3. ship');
  const c = extractSteps('steps: plan, build, ship');
  return a.length === 3 && a[0] === 'sign up' && b.length === 3 && c.length === 3;
})());

check('a named chart kind is built without asking', (() => {
  const t = 'pie of segment share: SMB 12, Mid 28, Ent 60';
  const i = visualIntent(t, extractSeries(t));
  return i.kind === 'pie' && i.confidence === 'high' && i.options.length === 0;
})());

check('temporal data settles it — no question asked', (() => {
  const t = 'chart revenue: Q1 32, Q2 38, Q3 42, Q4 45';
  const i = visualIntent(t, extractSeries(t));
  return i.kind === 'line' && i.confidence === 'high';
})());

check('a long list settles it as a ranking', (() => {
  const t = 'chart spend: Sales 12, Marketing 9, Product 14, Support 5, Ops 7, Legal 3, Finance 4';
  const i = visualIntent(t, extractSeries(t));
  return i.kind === 'bar' && i.confidence === 'high';
})());

check('a short unordered set is a real fork — so it offers', (() => {
  const t = 'chart ARR: SMB 1.2, Mid 2.1, Ent 8.4';
  const i = visualIntent(t, extractSeries(t));
  return i.confidence === 'low' && i.options.includes('pie') && i.options.includes('column');
})());

check('a vague diagram ask offers flow or funnel', (() => {
  const i = visualIntent('draw the steps: plan, build, ship', []);
  return i.family === 'diagram' && i.confidence === 'low'
    && i.options.join() === 'flow,funnel';
})());

check('a flow slide carries steps and no geometry', (() => {
  const t = 'flow chart of onboarding: sign up -> verify -> invite';
  const slide = buildFlowSlide({ prompt: t, steps: extractSteps(t), kind: 'flow' });
  return slide.kind === 'diagram' && slide.diagram.steps.length === 3
    && slide.title === 'Flow chart of onboarding'
    && !('x' in slide) && !('w' in slide);
})());

console.log(`\n${pass}/${pass + fail} passed`);
process.exit(fail ? 1 : 0);
