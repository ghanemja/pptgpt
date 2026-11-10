/* ============================================================
   ws-review.jsx — phase 05, the adversarial read.

   The Coach reads the slide in front of you. A review reads the whole deck
   as one argument, in the voice of someone you expect to be in the room,
   and tells you where it is weakest — which is a property of the set, not
   of any single slide.

   The persona is configured here before it runs: who is reading, how hard
   they push, and which lenses they care about today. Those are sent as an
   override, so tuning a critic for one meeting does not mean editing the
   persona everyone else uses.

   The engine does the reading (deckengine/coach.py) and the counting. This
   panel configures, shows, and jumps to the slide a note is about.
   ============================================================ */

const { Ico } = window;
const { useState, useEffect } = React;

const API = window.WS_NO_BACKEND ? ''
  : ((window.BU_API_BASE || '').replace(/\/$/, '')
    || ((location.protocol === 'http:' || location.protocol === 'https:') ? location.origin : ''));

const SEV_LABEL = { blocker: 'Blocker', push: 'Push back', nit: 'Nit' };
const STRICTNESS = [
  ['soft', 'Generous'],
  ['normal', 'Fair'],
  ['hard', 'Hostile'],
];
const LENS_WHY = {
  ask: 'is there something to decide',
  evidence: 'claims backed by numbers',
  source: 'where the numbers came from',
  comparison: 'compared to what',
  density: 'one idea per slide',
  title: 'headlines that argue',
  hedge: 'no weasel words',
  jargon: 'plain language',
  ownership: 'who actually does it',
  handoff: 'does it flow',
};

function ReviewPhase({ deck, onOpenSlide, onReviewed }) {
  const [coaches, setCoaches] = useState([]);
  const [lenses, setLenses] = useState([]);
  const [who, setWho] = useState(() => {
    try { return localStorage.getItem('pptgpt-coach') || 'board-chair'; } catch (e) { return 'board-chair'; }
  });
  const [strictness, setStrictness] = useState('normal');
  const [off, setOff] = useState([]);          // lenses switched off for this run
  const [report, setReport] = useState(null);
  const [state, setState] = useState('idle');  // idle | running | ok | off
  const [view, setView] = useState(() => {
    try { return localStorage.getItem('pptgpt-review-view') || 'marked'; } catch (e) { return 'marked'; }
  });
  function pickView(v) {
    setView(v);
    try { localStorage.setItem('pptgpt-review-view', v); } catch (e) {}
  }

  useEffect(() => {
    if (!API) { setState('off'); return; }
    let dead = false;
    Promise.all([
      fetch(API + '/api/coaches').then(r => r.json()),
      fetch(API + '/api/coach_lenses').then(r => r.json()),
    ])
      .then(([c, l]) => { if (!dead) { setCoaches(c.coaches || []); setLenses(l.lenses || []); } })
      .catch(() => { if (!dead) setState('off'); });
    return () => { dead = true; };
  }, []);

  function run() {
    if (!API) { setState('off'); return; }
    setState('running');
    const overrides = { strictness };
    if (off.length) {
      overrides.lenses = {};
      off.forEach(l => { overrides.lenses[l] = 0; });
    }
    fetch(API + '/api/critique_deck', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slides: deck.slides, coach: who, overrides }),
    })
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then(d => { setReport(d); setState('ok'); if (onReviewed) onReviewed(); })
      .catch(() => setState('off'));
  }

  function toggleLens(l) {
    setOff(prev => (prev.includes(l) ? prev.filter(x => x !== l) : [...prev, l]));
  }

  const chosen = coaches.find(c => c.slug === who);
  const summary = report && report.summary;

  return (
    <div className="stage__scroll stage__scroll--phase">
      <div className="phasewrap">
        <header className="phasehead">
          <div className="phasehead__eyebrow">Phase 05 · Review</div>
          <h1 className="phasehead__h">Who is going to <em>object</em>?</h1>
          <p className="phasehead__p">
            Pick the person you are afraid of, set how hard they push, and read the
            whole deck through them before the room does.
          </p>
        </header>

        {state === 'off' && !coaches.length ? (
          <div className="vnote">
            The review runs in the engine, and this build has none behind it.
            Run the local server to hear it.
          </div>
        ) : null}

        <section className="vsec">
          <h2 className="vsec__h">Who is reading</h2>
          <div className="themegrid">
            {coaches.map(c => (
              <button key={c.slug} className={`themecard ${who === c.slug ? 'on' : ''}`}
                onClick={() => {
                  setWho(c.slug);
                  try { localStorage.setItem('pptgpt-coach', c.slug); } catch (e) {}
                }}>
                <span className="themecard__name">{c.name}</span>
                <span className="themecard__desc">{c.tagline}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="vsec">
          <h2 className="vsec__h">How hard they push</h2>
          <div className="dirgrid">
            {STRICTNESS.map(([key, label]) => (
              <button key={key} className={`dircard ${strictness === key ? 'on' : ''}`}
                onClick={() => setStrictness(key)}>{label}</button>
            ))}
          </div>
        </section>

        <section className="vsec">
          <h2 className="vsec__h">What they are looking for
            <span className="vsec__sub">switch off what does not matter today</span>
          </h2>
          <div className="dirgrid">
            {lenses.map(l => (
              <button key={l} className={`dircard ${off.includes(l) ? '' : 'on'}`}
                onClick={() => toggleLens(l)} title={LENS_WHY[l] || ''}>
                {l}
              </button>
            ))}
          </div>
        </section>

        <footer className="phasefoot">
          <span className="phasefoot__count tnum">
            {deck.slides.length} slide{deck.slides.length === 1 ? '' : 's'}
          </span>
          <button className="phasefoot__go" onClick={run}
            disabled={state === 'running' || !deck.slides.length || !API}>
            {state === 'running' ? 'Reading the deck…'
              : `Review as ${chosen ? chosen.name : 'this critic'}`}
            <Ico name="expand" size={15} />
          </button>
        </footer>
      </div>

      {/* The report gets more room than the form above it: a marked-up
          slide needs gutters either side for its callouts. */}
      {report && state === 'ok' ? (
        <div className="revwide">
          <section className="vsec">
            <div className="revsay">
              <span className="msg__ava">{(report.coach.name || '?').slice(0, 2).toUpperCase()}</span>
              <div>
                <div className="coachsay__open">{report.coach.opening}</div>
                <div className="coachsay__sig">{report.coach.signature}</div>
              </div>
            </div>

            <div className="revtally">
              <span className={`revtally__v revtally__v--${summary.verdict}`}>
                {summary.verdict === 'clear' ? 'Holds up' : SEV_LABEL[summary.verdict]}
              </span>
              <span className="revtally__n tnum">{summary.severities.blocker} blockers</span>
              <span className="revtally__n tnum">{summary.severities.push} pushes</span>
              <span className="revtally__n tnum">{summary.severities.nit} nits</span>
              <span className="revtally__n tnum">{summary.clear}/{summary.slides} clear</span>
            </div>

            {summary.weakest.length ? (
              <div className="vnote">
                Weakest: {summary.weakest.map(i => `slide ${i + 1}`).join(', ')}.
                {Object.keys(summary.lenses).length
                  ? ` Recurring: ${Object.keys(summary.lenses).slice(0, 3).join(', ')}.`
                  : ''}
              </div>
            ) : null}

            <div className="revview">
              <span className="revview__label">Show notes</span>
              {[['marked', 'On the slides'], ['list', 'As a list']].map(([k, label]) => (
                <button key={k} className={`dircard ${view === k ? 'on' : ''}`}
                  onClick={() => pickView(k)}>{label}</button>
              ))}
            </div>

            <div className="revlist">
              {report.results.map(r => (
                <div key={r.slideId || r.index}
                  className={`revslide revslide--${r.verdict}${view === 'marked' && r.notes.length ? ' revslide--marked' : ''}`}>
                  <button className="revslide__head" onClick={() => onOpenSlide(r.slideId)}>
                    <span className="revslide__num tnum">{String(r.index + 1).padStart(2, '0')}</span>
                    <span className="revslide__title">
                      {(deck.slides[r.index] && deck.slides[r.index].title) || 'Untitled slide'}
                    </span>
                    <span className="revslide__verdict">
                      {r.verdict === 'clear' ? 'clear' : `${r.notes.length} note${r.notes.length === 1 ? '' : 's'}`}
                    </span>
                  </button>
                  {view === 'marked' && r.notes.length && deck.slides[r.index] && window.AnnotatedSlide ? (
                    <window.AnnotatedSlide slide={deck.slides[r.index]} notes={r.notes}
                      onOpen={() => onOpenSlide(r.slideId)} />
                  ) : r.notes.map((n, i) => (
                    <div key={i} className={`cnote cnote--${n.severity}`}>
                      <div className="cnote__head">
                        <span className="cnote__sev">{SEV_LABEL[n.severity]}</span>
                        <span className="cnote__lens">{n.lens}</span>
                      </div>
                      <div className="cnote__note">{n.note}</div>
                      {n.ask ? <div className="cnote__ask">“{n.ask}”</div> : null}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}

Object.assign(window, { ReviewPhase });
