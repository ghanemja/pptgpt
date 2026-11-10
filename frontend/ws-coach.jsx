/* ============================================================
   ws-coach.jsx — the room, before the room.

   Pick who is reading the deck and they read the slide you are on: a board
   chair who wants the ask up front, an analyst who wants the number
   sourced, an editor who wants one idea. Each note names the lens it came
   from and asks the question that persona would actually ask, so a critique
   is something to act on rather than a mood.

   The reading is done by the engine (deckengine/coach.py), deterministically
   — the same slide and persona always produce the same notes. This panel
   only shows them, and where a note points at a field, offers to take you
   there.
   ============================================================ */

const { Ico } = window;
const { useState, useEffect } = React;

const API = window.WS_NO_BACKEND ? ''
  : ((window.BU_API_BASE || '').replace(/\/$/, '')
    || ((location.protocol === 'http:' || location.protocol === 'https:') ? location.origin : ''));

const SEV_LABEL = { blocker: 'Blocker', push: 'Push back', nit: 'Nit' };

function useCoaches() {
  const [coaches, setCoaches] = useState([]);
  useEffect(() => {
    if (!API) return;
    let dead = false;
    fetch(API + '/api/coaches')
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then(d => { if (!dead) setCoaches(d.coaches || []); })
      .catch(() => {});
    return () => { dead = true; };
  }, []);
  return coaches;
}

function CoachPanel({ slide, nextSlide, onClose, onFocusField }) {
  const coaches = useCoaches();
  const [who, setWho] = useState(() => {
    try { return localStorage.getItem('pptgpt-coach') || 'board-chair'; } catch (e) { return 'board-chair'; }
  });
  const [result, setResult] = useState(null);
  const [state, setState] = useState('idle');

  // Judged against the company's own decks when it has a kit (learned norms).
  const org = window.WS_ORG || null;
  const sig = JSON.stringify([slide, who, org]);
  useEffect(() => {
    if (!API || !slide) { setState('off'); return; }
    let dead = false;
    setState('reading');
    fetch(API + '/api/critique_slide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slide, coach: who, next: nextSlide || null, org }),
    })
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then(d => { if (!dead) { setResult(d); setState('ok'); } })
      .catch(() => { if (!dead) setState('off'); });
    return () => { dead = true; };
  }, [sig]);

  function pick(slug) {
    setWho(slug);
    try { localStorage.setItem('pptgpt-coach', slug); } catch (e) {}
  }

  const notes = (result && result.notes) || [];

  return (
    <div className="history coachpanel">
      <div className="history__head">
        <span className="history__title">Coach</span>
        <div className="coachpick">
          {coaches.map(c => (
            <button key={c.slug} className={`storytab ${who === c.slug ? 'on' : ''}`}
              onClick={() => pick(c.slug)} title={c.tagline}>{c.name}</button>
          ))}
        </div>
        <button className="rail__collapse" onClick={onClose}><Ico name="close" size={16} /></button>
      </div>

      <div className="history__scroll">
        <div className="history__inner">
          {state === 'off' ? (
            <div className="tray__empty">
              The coach reads slides in the engine, and this build has none behind it.
              Run the local server to hear it.
            </div>
          ) : state === 'reading' ? (
            <div className="tray__empty">Reading the slide…</div>
          ) : result ? (
            <>
              <div className="coachsay">
                <span className="msg__ava">{(result.coach.name || '?').slice(0, 2).toUpperCase()}</span>
                <div>
                  <div className="coachsay__open">{result.coach.opening}</div>
                  <div className="coachsay__sig">{result.coach.signature}</div>
                </div>
              </div>

              {notes.length === 0 ? (
                <div className="coachclear">
                  Nothing to push on. This one holds up to {result.coach.name}.
                </div>
              ) : notes.map((n, i) => (
                <div key={i} className={`cnote cnote--${n.severity}`}>
                  <div className="cnote__head">
                    <span className="cnote__sev">{SEV_LABEL[n.severity] || n.severity}</span>
                    <span className="cnote__lens">{n.lens}</span>
                  </div>
                  <div className="cnote__note">{n.note}</div>
                  {n.ask ? <div className="cnote__ask">“{n.ask}”</div> : null}
                  {n.fix && n.fix.field ? (
                    <button className="msg__act" onClick={() => onFocusField(n.fix.field)}>
                      Fix the {n.fix.field}
                    </button>
                  ) : null}
                </div>
              ))}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { CoachPanel });
