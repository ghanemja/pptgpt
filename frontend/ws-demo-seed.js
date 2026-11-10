/* ============================================================
   ws-demo-seed.js — the canned deck for the static deploy.

   Netlify serves files, not Python, so on the public site there is
   no engine behind /api: no model generation, no .pptx export, no
   ingest. Rather than open on an empty workspace that quietly does
   nothing, the deployed build seeds a finished deck so every phase
   has something real in it.

   ws-app.jsx reads window.WS_SEED only when localStorage is empty,
   so a visitor's own work always wins after their first edit.

   scripts/build-netlify.mjs injects this file into the DIST pages
   only. Local dev (python server.py) has a real backend and opens
   empty, as it should.

   The deck mirrors frontend/samples/sample.pptx, which is
   generated from the same story by scripts/make_sample_deck.py.
   ============================================================ */
// This build ships without a backend. The probes in workspace-backend.js and
// ws-phases.jsx would otherwise fire at location.origin and 404 four times on
// every load; a static deploy should know it is static.
window.WS_NO_BACKEND = true;

window.WS_SEED = {
  feature: 'create',
  audience: 'exec',
  theme: 'bolt',
  phase: 'scope',
  orgSlug: 'default',
  deckId: 'demo',
  scope: {
    demo: {
      audience: 'Exec',
      decision: 'Approve two enterprise AEs and the security review for Q1',
      stakes: 'We lose the Q1 window and six gated deals age out',
      evidence: 'Net retention 118% — and 71% of new ARR came from 9% of accounts',
      objection: 'That the Q3 beat is seasonal renewal clustering, not structural',
      time: '15 min',
    },
  },
  chat: [
    { role: 'user', text: 'Q3 board review — we beat plan by 14%, want two enterprise AEs for Q1.' },
    { role: 'assistant', text: 'Drafted four slides on the Situation → Complication → Answer → Ask arc.' },
  ],
  decks: [{
    id: 'demo',
    title: 'Q3 board review',
    activeId: 's1',
    slides: [
      {
        id: 's1', kind: 'text', palette: 'warm', emphasis: 'number',
        eyebrow: 'Q3 results · exec review',
        title: 'Q3 beat plan on every line',
        metric: '+14%', metricSub: 'revenue vs plan · full-year pace',
        bullets: [
          'Net retention held at 118%',
          'Logo churn down to 1.8%',
          'Enterprise GTM drove the beat',
        ],
        takeaway: 'The quarter was strong — but the strength is concentrated.',
      },
      {
        id: 's2', kind: 'chart', palette: 'warm', emphasis: 'number',
        eyebrow: 'By the numbers',
        title: 'The beat came from one segment',
        chart: {
          title: 'new ARR by segment, $M',
          data: [
            { label: 'SMB', value: 1.2, hi: false },
            { label: 'Mid', value: 2.1, hi: false },
            { label: 'Ent', value: 8.4, hi: true },
          ],
        },
        takeaway: '71% of new ARR came from 9% of accounts.',
      },
      {
        id: 's3', kind: 'text', palette: 'warm', emphasis: 'story',
        eyebrow: 'The objection',
        title: 'Is this structural, or just seasonal?',
        bullets: [
          'Seasonal read: Q3 renewals cluster, so retention flatters',
          'Structural read: expansion came from new seats, not renewals',
          'The Q1 enterprise cohort is still net-expanding',
        ],
        takeaway: 'If Q4 expansion holds above 110%, it is structural.',
      },
      {
        id: 's4', kind: 'text', palette: 'warm', emphasis: 'number',
        eyebrow: 'The ask',
        title: 'Fund the motion that is already working',
        metric: '$1.4M', metricSub: 'Q1 investment · 4.2x modelled by FY27',
        bullets: [
          'Two enterprise AEs against the proven motion',
          'Security review that gates six open deals',
          'Mid-market spend flat until the cohort read lands',
        ],
        takeaway: 'Approve the enterprise hire plan today.',
      },
    ],
  }],
};
