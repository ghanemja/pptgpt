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
const { useState, useEffect, useRef } = React;

const API = window.WS_NO_BACKEND ? ''
  : ((window.BU_API_BASE || '').replace(/\/$/, '')
    || ((location.protocol === 'http:' || location.protocol === 'https:') ? location.origin : ''));

const SEV_LABEL = { blocker: 'Blocker', push: 'Push back', nit: 'Nit' };
const STRICTNESS = [
  ['soft', 'Generous'],
  ['normal', 'Fair'],
  ['hard', 'Hostile'],
];
const STRICT_LABEL = Object.fromEntries(STRICTNESS);
const DEFAULT_WEIGHT = 2;   // a criterion ticked on that the persona did not weight

/* The ticks a reviewer starts with: what the persona weights, plus the
   company's own rules that are on by default — house rules apply to every
   reader. A saved reviewer is exact: it already says what was ticked. */
function startingWeights(coach, criteria) {
  const w = { ...((coach && coach.lenses) || {}) };
  if (!coach || !coach.saved) {
    criteria.forEach(c => {
      if (c.source === 'kit' && c.kind !== 'lens' && c.on && !w[c.id]) w[c.id] = DEFAULT_WEIGHT;
    });
  }
  return w;
}

function sameSetup(coach, criteria, strictness, weights) {
  if (!coach) return true;
  if ((coach.strictness || 'normal') !== strictness) return false;
  const start = startingWeights(coach, criteria);
  return criteria.every(c => (start[c.id] || 0) === (weights[c.id] || 0));
}

function ReviewPhase({ deck, onOpenSlide, onReviewed, orgSlug, orgName }) {
  const [coaches, setCoaches] = useState([]);
  const [criteria, setCriteria] = useState([]);
  const [kitError, setKitError] = useState('');
  const [who, setWho] = useState(() => {
    try { return localStorage.getItem('pptgpt-coach') || 'board-chair'; } catch (e) { return 'board-chair'; }
  });
  const [strictness, setStrictness] = useState('normal');
  const [weights, setWeights] = useState({});   // criterion id -> weight; 0/absent = unticked
  const [saveName, setSaveName] = useState('');
  const [saveMsg, setSaveMsg] = useState('');
  const [runError, setRunError] = useState('');
  const [report, setReport] = useState(null);
  const [runId, setRunId] = useState(0);       // a fresh run reopens the stage on its first note
  const reportRef = useRef(null);

  // The report lands below the form; bring it up rather than leave the
  // answer off-screen under the button that asked for it.
  useEffect(() => {
    if (runId && reportRef.current) reportRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [runId]);
  const [state, setState] = useState('idle');  // idle | running | ok | off
  const [view, setView] = useState(() => {
    try { return localStorage.getItem('pptgpt-review-view') || 'marked'; } catch (e) { return 'marked'; }
  });
  function pickView(v) {
    setView(v);
    try { localStorage.setItem('pptgpt-review-view', v); } catch (e) {}
  }

  const org = orgSlug && orgSlug !== 'default' ? orgSlug : '';
  useEffect(() => {
    if (!API) { setState('off'); return; }
    let dead = false;
    Promise.all([
      fetch(API + '/api/coaches').then(r => r.json()),
      fetch(API + '/api/coach_lenses' + (org ? `?org=${encodeURIComponent(org)}` : '')).then(r => r.json()),
    ])
      .then(([c, l]) => {
        if (dead) return;
        setCoaches(c.coaches || []);
        setCriteria(l.criteria || []);
        setKitError(l.error || '');
      })
      .catch(() => { if (!dead) setState('off'); });
    return () => { dead = true; };
  }, [org]);

  const chosen = coaches.find(c => c.slug === who) || coaches[0];

  // Choosing a reviewer loads how THEY read: their strictness and their
  // criteria, so the controls never show one thing and run another. Applied
  // once per (reviewer, criteria set) — a save must not reset what it saved.
  const applied = useRef('');
  const critKey = criteria.map(c => c.id).join(',');
  function pick(c) {
    applied.current = c.slug + '|' + critKey;
    setWho(c.slug);
    try { localStorage.setItem('pptgpt-coach', c.slug); } catch (e) {}
    setStrictness(c.strictness || 'normal');
    setWeights(startingWeights(c, criteria));
    setSaveName(c.saved ? c.name : '');
    setSaveMsg('');
  }
  useEffect(() => {
    if (chosen && criteria.length && applied.current !== chosen.slug + '|' + critKey) pick(chosen);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosen && chosen.slug, critKey]);

  function toggle(c) {
    setWeights(prev => {
      const on = (prev[c.id] || 0) > 0;
      const back = (chosen && chosen.lenses && chosen.lenses[c.id]) || DEFAULT_WEIGHT;
      return { ...prev, [c.id]: on ? 0 : back };
    });
  }

  const ticked = criteria.filter(c => (weights[c.id] || 0) > 0);
  const lensMap = () => Object.fromEntries(criteria.map(c => [c.id, weights[c.id] || 0]));
  const edited = !sameSetup(chosen, criteria, strictness, weights);

  function run() {
    if (!API) { setState('off'); return; }
    setState('running');
    setRunError('');
    fetch(API + '/api/critique_deck', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slides: deck.slides, coach: who, org: org || null,
                             overrides: { strictness, lenses: lensMap() } }),
    })
      .then(r => r.json().then(d => (r.ok ? d : Promise.reject(d))))
      .then(d => { setReport(d); setRunId(x => x + 1); setState('ok'); if (onReviewed) onReviewed(); })
      .catch(e => { setState('idle'); setRunError((e && e.error) || 'The review could not run.'); });
  }

  function save() {
    const name = saveName.trim();
    if (!name || !chosen) return;
    setSaveMsg('Saving…');
    fetch(API + '/api/coaches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, basedOn: chosen.slug, strictness, lenses: lensMap() }),
    })
      .then(r => r.json().then(d => (r.ok ? d : Promise.reject(d))))
      .then(d => {
        applied.current = d.coach.slug + '|' + critKey;
        setCoaches(d.coaches || []);
        setWho(d.coach.slug);
        try { localStorage.setItem('pptgpt-coach', d.coach.slug); } catch (e) {}
        setSaveMsg(`Saved as “${d.coach.name}”.`);
      })
      .catch(e => setSaveMsg((e && e.error) || 'Could not save.'));
  }

  function forget(c) {
    if (!window.confirm(`Delete the saved reviewer “${c.name}”? This cannot be undone.`)) return;
    fetch(API + '/api/coaches/' + encodeURIComponent(c.slug), { method: 'DELETE' })
      .then(r => r.json().then(d => (r.ok ? d : Promise.reject(d))))
      .then(d => {
        setCoaches(d.coaches || []);
        if (who === c.slug) {
          const back = (d.coaches || []).find(x => x.slug === c.basedOn) || (d.coaches || [])[0];
          if (back) pick(back);
        }
      })
      .catch(e => setSaveMsg((e && e.error) || 'Could not delete.'));
  }

  const summary = report && report.summary;
  const shipped = coaches.filter(c => !c.saved);
  const saved = coaches.filter(c => c.saved);
  const kitCrit = criteria.filter(c => c.source === 'kit');
  const engineCrit = criteria.filter(c => c.source !== 'kit');
  const nameOf = slug => (coaches.find(c => c.slug === slug) || {}).name || slug;

  const critRow = c => {
    const on = (weights[c.id] || 0) > 0;
    return (
      <label key={c.id} className={`critrow ${on ? 'is-on' : ''}`}>
        <span className="checkitem__box">
          <input type="checkbox" checked={on} onChange={() => toggle(c)} />
          <span aria-hidden="true" />
        </span>
        <span className="critrow__body">
          <span className="critrow__label">
            {c.label}
            {c.kind !== 'lens' ? <span className="critrow__tag">house rule</span> : null}
          </span>
          {c.means ? <span className="critrow__means">{c.means}</span> : null}
          {c.words && c.words.length ? (
            <span className="critrow__words" title={c.words.join(', ')}>
              {c.kind === 'lens' ? 'Watches for' : 'Flags'} {c.words.slice(0, 4).map(w => `“${w}”`).join(', ')}
              {c.words.length > 4 ? ` and ${c.words.length - 4} more` : ''}
            </span>
          ) : null}
        </span>
      </label>
    );
  };

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
            {shipped.map(c => (
              <button key={c.slug} className={`themecard ${who === c.slug ? 'on' : ''}`} onClick={() => pick(c)}>
                <span className="themecard__name">{c.name}</span>
                <span className="themecard__desc">{c.tagline}</span>
              </button>
            ))}
          </div>
          {saved.length ? (
            <>
              <h3 className="revsaved__h">Your saved reviewers</h3>
              <div className="themegrid">
                {saved.map(c => (
                  <div key={c.slug} className={`themecard revsaved ${who === c.slug ? 'on' : ''}`}>
                    <button className="revsaved__pick" onClick={() => pick(c)}>
                      <span className="themecard__name">{c.name}</span>
                      <span className="themecard__desc">
                        {c.basedOn ? `From ${nameOf(c.basedOn)} · ` : ''}{STRICT_LABEL[c.strictness] || c.strictness}
                        {' · '}{Object.values(c.lenses || {}).filter(w => w > 0).length} checks
                      </span>
                    </button>
                    <button className="revsaved__x" onClick={() => forget(c)}
                      title={`Delete ${c.name}`} aria-label={`Delete saved reviewer ${c.name}`}>×</button>
                  </div>
                ))}
              </div>
            </>
          ) : null}
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
          <h2 className="vsec__h">What they check
            <span className="vsec__sub">{ticked.length} of {criteria.length} ticked</span>
          </h2>
          {kitError ? <div className="vnote vnote--warn">{kitError}</div> : null}
          {kitCrit.length ? (
            <>
              <h3 className="critgroup__h">{orgName ? `${orgName}'s criteria` : 'Your company’s criteria'}
                <span>from the company kit</span></h3>
              <div className="critlist">{kitCrit.map(critRow)}</div>
              <h3 className="critgroup__h">Also available</h3>
            </>
          ) : null}
          <div className="critlist">{engineCrit.map(critRow)}</div>
        </section>

        <section className="vsec">
          <h2 className="vsec__h">Keep this reviewer
            <span className="vsec__sub">
              {edited ? 'tuned since you picked them — save to pick them again later'
                : chosen && chosen.saved ? 'saved' : 'save a tuned reviewer to pick again later'}
            </span>
          </h2>
          <form className="revsave" onSubmit={e => { e.preventDefault(); save(); }}>
            <input className="revsave__input" value={saveName} maxLength={80}
              onChange={e => { setSaveName(e.target.value); setSaveMsg(''); }}
              placeholder={chosen ? `e.g. ${chosen.name}, Thursday board` : 'Name this reviewer'}
              aria-label="Name for the saved reviewer" />
            <button className="dircard on" type="submit" disabled={!saveName.trim() || !ticked.length}>
              {chosen && chosen.saved && saveName.trim() === chosen.name ? 'Update' : 'Save reviewer'}
            </button>
          </form>
          {saveMsg ? <div className="revsave__msg">{saveMsg}</div> : null}
        </section>

        <footer className="phasefoot">
          <span className="phasefoot__count tnum">
            {deck.slides.length} slide{deck.slides.length === 1 ? '' : 's'}
          </span>
          <button className="phasefoot__go" onClick={run}
            disabled={state === 'running' || !deck.slides.length || !API || !ticked.length}>
            {state === 'running' ? 'Reading the deck…'
              : !ticked.length ? 'Tick at least one check'
              : `Review as ${chosen ? chosen.name : 'this critic'}${edited ? ' (tuned)' : ''}`}
            <Ico name="expand" size={15} />
          </button>
        </footer>
        {runError ? <div className="vnote vnote--warn">{runError}</div> : null}
      </div>

      {/* The report gets more room than the form above it: a marked-up
          slide needs gutters either side for its callouts. */}
      {report && state === 'ok' ? (
        <div className="revwide" ref={reportRef}>
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
              {[['marked', 'Slide by slide'], ['list', 'As a list']].map(([k, label]) => (
                <button key={k} className={`dircard ${view === k ? 'on' : ''}`}
                  onClick={() => pickView(k)}>{label}</button>
              ))}
            </div>

            {view === 'marked' && window.ReviewStage ? (
              <window.ReviewStage key={runId} deck={deck} results={report.results} onOpenSlide={onOpenSlide} />
            ) : (
              <div className="revlist">
                {report.results.map(r => (
                  <div key={r.slideId || r.index} className={`revslide revslide--${r.verdict}`}>
                    <button className="revslide__head" onClick={() => onOpenSlide(r.slideId)}>
                      <span className="revslide__num tnum">{String(r.index + 1).padStart(2, '0')}</span>
                      <span className="revslide__title">
                        {(deck.slides[r.index] && deck.slides[r.index].title) || 'Untitled slide'}
                      </span>
                      <span className="revslide__verdict">
                        {r.verdict === 'clear' ? 'clear' : `${r.notes.length} note${r.notes.length === 1 ? '' : 's'}`}
                      </span>
                    </button>
                    {r.notes.map((n, i) => (
                      <div key={i} className={`cnote cnote--${n.severity}`}>
                        <div className="cnote__head">
                          <span className="cnote__sev">{SEV_LABEL[n.severity]}</span>
                          <span className="cnote__lens">{n.label || n.lens}</span>
                        </div>
                        <div className="cnote__note">{n.note}</div>
                        {n.ask ? <div className="cnote__ask">“{n.ask}”</div> : null}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}

Object.assign(window, { ReviewPhase });
