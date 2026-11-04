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

console.log(`\n${pass}/${pass + fail} passed`);
process.exit(fail ? 1 : 0);
