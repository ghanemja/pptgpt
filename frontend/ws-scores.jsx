/* ============================================================
   ws-scores.jsx — a panel of reviewers, scoring live.

   Pick who sits on the panel; each gets a score card — clear messaging,
   evidence, content density, plain language, ownership, and the company's
   house rules when its kit has any — judged for the room the deck is for
   (the audience) and against what it is for (the decision from scoping).

   It docks above the slide rather than over it, because the point is to
   watch it move: every edit re-scores the deck a moment later and each
   number shows which way it went.

   The scoring is the engine's (deckengine/scorecard.py): the coach's notes,
   counted. Deterministic, so a number that moves moved because the deck did.
   ============================================================ */

const {
  useState: useScState, useEffect: useScEffect, useRef: useScRef,
} = React;

const SC_API = window.WS_NO_BACKEND ? ''
  : ((window.BU_API_BASE || '').replace(/\/$/, '')
    || ((location.protocol === 'http:' || location.protocol === 'https:') ? location.origin : ''));
const SC_PANEL_KEY = 'pptgpt-panel';
const SC_DEFAULT_PANEL = ['board-chair', 'skeptical-analyst'];
const SC_DEBOUNCE_MS = 450;
const SC_SHORT = {
  messaging: 'Messaging', evidence: 'Evidence', density: 'Density',
  language: 'Language', ownership: 'Ownership', house: 'House',
};

function scBand(score) {
  if (score == null) return 'none';
  return score >= 80 ? 'good' : score >= 60 ? 'fair' : 'poor';
}

function ScoreDelta({ d }) {
  if (!d) return null;
  return <span className={`scdelta ${d > 0 ? 'up' : 'down'} tnum`}>{d > 0 ? '▲' : '▼'}{Math.abs(d)}</span>;
}

function ScorePanel({ slides, audience, purpose, orgSlug, onClose, onPickSlide }) {
  const { Ico } = window;
  const [coaches, setCoaches] = useScState([]);
  const [panel, setPanel] = useScState(() => {
    try { return JSON.parse(localStorage.getItem(SC_PANEL_KEY)) || SC_DEFAULT_PANEL; }
    catch (e) { return SC_DEFAULT_PANEL; }
  });
  const [result, setResult] = useScState(null);
  const [deltas, setDeltas] = useScState({});    // "slug" | "slug|dim" -> change since the last edit
  const [state, setState] = useScState('idle');  // idle | scoring | off
  const [open, setOpen] = useScState('');        // the card shown in detail
  const [picking, setPicking] = useScState(false);
  const last = useScRef(null);

  useScEffect(() => {
    if (!SC_API) { setState('off'); return; }
    fetch(SC_API + '/api/coaches').then(r => r.json())
      .then(d => setCoaches(d.coaches || []))
      .catch(() => setState('off'));
  }, []);

  function setPanelSaved(next) {
    setPanel(next);
    try { localStorage.setItem(SC_PANEL_KEY, JSON.stringify(next)); } catch (e) {}
  }
  function toggleMember(slug) {
    setPanelSaved(panel.includes(slug) ? panel.filter(s => s !== slug) : [...panel, slug].slice(0, 6));
  }

  // Score a moment after the deck stops changing, and say how each number
  // moved relative to the last time it was scored.
  const org = orgSlug && orgSlug !== 'default' ? orgSlug : null;
  const sig = JSON.stringify([slides, panel, audience, purpose, org]);
  useScEffect(() => {
    if (!SC_API || !panel.length) return undefined;
    const ctl = new AbortController();
    const t = setTimeout(() => {
      setState('scoring');
      fetch(SC_API + '/api/scorecard', {
        method: 'POST', signal: ctl.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slides, coaches: panel, audience, purpose: purpose || '', org }),
      })
        .then(r => (r.ok ? r.json() : Promise.reject()))
        .then(d => {
          const prev = last.current;
          if (prev) {
            const was = {};
            prev.cards.forEach(c => {
              was[c.coach.slug] = c.overall;
              Object.entries(c.dims).forEach(([k, v]) => { was[c.coach.slug + '|' + k] = v.score; });
            });
            const next = {};
            d.cards.forEach(c => {
              const s = c.coach.slug;
              if (was[s] != null && c.overall != null && c.overall !== was[s]) next[s] = c.overall - was[s];
              Object.entries(c.dims).forEach(([k, v]) => {
                const w = was[s + '|' + k];
                if (w != null && v.score !== w) next[s + '|' + k] = v.score - w;
              });
            });
            // Arrows say what THIS edit did; one that changed nothing clears them.
            setDeltas(next);
          }
          last.current = d;
          setResult(d);
          setState('idle');
        })
        .catch(e => { if (e && e.name === 'AbortError') return; setState('off'); });
    }, SC_DEBOUNCE_MS);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [sig]);

  const dims = (result && result.dimensions) || [];
  const cards = (result && result.cards) || [];
  const detail = cards.find(c => c.coach.slug === open);
  const aud = result && result.audience;

  return (
    <div className="scorestrip">
      <div className="scorestrip__head">
        <span className="scorestrip__title">Scores</span>
        {aud ? (
          <span className="scorestrip__ctx" title={aud.why}>
            for {/^[aeiou]/i.test(aud.label) ? 'an' : 'a'} <b>{aud.label}</b> room
          </span>
        ) : null}
        {result && result.purpose ? (
          <span className={`scorestrip__purpose ${result.purposeMet ? 'met' : 'unmet'}`}
            title={result.purposeMet ? 'A headline or closing line asks for this.' : 'Nothing in the deck asks for this yet.'}>
            {result.purposeMet ? '✓' : '✗'} asks for “{result.purpose}”
          </span>
        ) : (
          <span className="scorestrip__ctx scorestrip__ctx--mute">no decision set in Scope</span>
        )}
        <span className="scorestrip__spacer" />
        {state === 'scoring' ? <span className="scorestrip__live">scoring…</span>
          : state === 'off' ? <span className="scorestrip__live">engine offline</span>
          : <span className="scorestrip__live scorestrip__live--on">live</span>}
        <div className="scorestrip__pickwrap">
          <button className={`storytab ${picking ? 'on' : ''}`} onClick={() => setPicking(p => !p)}>
            Panel · {panel.length}
          </button>
          {picking ? (
            <div className="scpick" role="dialog" aria-label="Who sits on the panel">
              {coaches.map(c => (
                <label key={c.slug} className="scpick__row">
                  <input type="checkbox" checked={panel.includes(c.slug)} onChange={() => toggleMember(c.slug)} />
                  <span>{c.name}</span>
                  {c.saved ? <span className="scpick__tag">saved</span> : null}
                </label>
              ))}
            </div>
          ) : null}
        </div>
        <button className="rail__collapse" onClick={onClose} title="Hide scores"><Ico name="close" size={15} /></button>
      </div>

      {!panel.length ? (
        <div className="scorestrip__empty">Put someone on the panel to see scores.</div>
      ) : (
        <div className="scorestrip__cards">
          {cards.map(c => {
            const s = c.coach.slug;
            return (
              <button key={s} className={`sccard ${open === s ? 'on' : ''}`}
                onClick={() => setOpen(o => (o === s ? '' : s))}
                title="Show what is costing points">
                <div className="sccard__top">
                  <span className="msg__ava">{c.coach.name.slice(0, 2).toUpperCase()}</span>
                  <span className="sccard__name">{c.coach.name}</span>
                  <span className={`sccard__overall sc--${scBand(c.overall)} tnum`}>{c.overall ?? '—'}</span>
                  <ScoreDelta d={deltas[s]} />
                </div>
                <div className="sccard__dims">
                  {dims.map(d => {
                    const v = c.dims[d.id];
                    return (
                      <div key={d.id} className={`scdim ${v ? '' : 'scdim--off'}`} title={v ? d.means : `${c.coach.name} does not read for this`}>
                        <span className="scdim__l">{SC_SHORT[d.id] || d.label}</span>
                        <span className="scdim__bar"><span className={`sc--${scBand(v && v.score)}`} style={{ width: `${v ? v.score : 0}%` }} /></span>
                        <span className="scdim__n tnum">{v ? v.score : '—'}</span>
                        <ScoreDelta d={deltas[s + '|' + d.id]} />
                      </div>
                    );
                  })}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {detail ? (
        <div className="scdetail">
          {dims.filter(d => detail.dims[d.id]).map(d => {
            const v = detail.dims[d.id];
            return (
              <div key={d.id} className="scdetail__dim">
                <div className="scdetail__h">
                  <span>{d.label}</span>
                  <span className={`sc--${scBand(v.score)} tnum`}>{v.score}</span>
                </div>
                {v.issues.length ? v.issues.slice(0, 4).map((it, i) => (
                  <div key={i} className={`scissue scissue--${it.severity}`}>
                    <span className="scissue__l">{it.label}</span>
                    {it.slides.length ? (
                      <span className="scissue__slides">
                        {it.slides.slice(0, 6).map(ix => (
                          <button key={ix} className="scissue__slide tnum"
                            onClick={() => slides[ix] && onPickSlide(slides[ix].id)}>{ix + 1}</button>
                        ))}
                      </span>
                    ) : null}
                  </div>
                )) : <div className="scissue scissue--clear">Nothing costing points.</div>}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

Object.assign(window, { ScorePanel });
