/* ============================================================
   ws-thread.jsx — the thread connectivity graph.

   A deck breaks in two places: a message nothing else picks up,
   and a bumper that does not set up the next title. threadmap.py
   reads both (`flow`: a status per message, a status per handoff)
   plus orphan slides and the spine. The backend emits pure data —
   no pixels, no colors (R0.1) — so how they look lives here.

   Two reads, one after the other. The fast one (embeddings, or shared
   words without them) answers in well under a second and paints at
   once. The model's read — orphans with reasons, the spine as a
   sentence — takes tens of seconds on a local 4B model, so it is
   asked for in the background and replaces the fast one when it
   lands. Both ask only for the deck as it stands (`sides: 'before'`):
   nothing here shows the simulated "after", so it is never paid for.
   ============================================================ */

const { Ico } = window;
const { useState, useEffect } = React;

/* The workspace slide shape -> what threadmap.py reads. */
function toOutline(deck) {
  return deck.slides.map(s => ({
    id: s.id,
    title: s.title || '',
    messages: (s.bullets || []).slice(),
    bumper: s.takeaway || '',
  }));
}

/* Model reads already made this session, by deck content. Switching tabs
   back to Threads must not cost another model call for the same deck. */
const _deepReads = new Map();

function useThreadMap(deck, enabled) {
  const [data, setData] = useState(null);
  const [state, setState] = useState('idle');   // idle | loading | ok | off
  const [deep, setDeep] = useState('idle');     // idle | reading | done | none | empty
  const sig = deck.slides.map(s => `${s.id}:${s.title}:${(s.bullets || []).join('|')}:${s.takeaway || ''}`).join('//');

  useEffect(() => {
    if (!enabled || deck.slides.length < 2) { setData(null); setState('idle'); setDeep('idle'); return; }
    const origin = window.WS_NO_BACKEND ? '' : (window.BU_API_BASE || location.origin);
    if (!origin) { setState('off'); return; }
    let dead = false;
    const url = origin.replace(/\/$/, '') + '/api/thread_map';
    const outline = toOutline(deck);
    const ask = engine => fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ outline, engine, sides: 'before' }),
    }).then(r => (r.ok ? r.json() : Promise.reject(r.status)));

    const known = _deepReads.get(sig);
    if (known) { setData(known); setState('ok'); setDeep('done'); return; }

    setState('loading'); setDeep('idle');
    ask('fast')
      .then(d => {
        if (dead) return;
        setData(d); setState('ok');
        // The model read, in the background. If no model answers, the cascade
        // returns the same fast read — keep what is on screen and say so.
        setDeep('reading');
        return ask('auto').then(full => {
          if (dead) return;
          // Take the model's read only when it says something. A small
          // local model can answer with no spine, no links and no orphans,
          // and an empty graph is worse than the quick read already shown.
          if (full && full.before && full.before.engine === 'narrative' && saysSomething(full.before)) {
            _deepReads.set(sig, full);
            setData(full); setDeep('done');
          } else {
            setDeep(full && full.before && full.before.engine === 'narrative' ? 'empty' : 'none');
          }
        }).catch(() => { if (!dead) setDeep('none'); });
      })
      .catch(() => { if (!dead) setState('off'); });
    return () => { dead = true; };
  }, [sig, enabled]);

  return { data, state, deep };
}

function saysSomething(view) {
  const g = (view && view.graph) || {};
  return !!(view.narrative_spine || (g.edges || []).length || (g.orphans || []).length || (g.gaps || []).length);
}

const ENGINE_LABEL = {
  narrative: 'read by the local model',
  semantic: 'matched by meaning',
  lexical: 'matched by shared words',
};

/* ── the reading ──────────────────────────────────────────── */
/* Two columns. Left, the deck as it runs: every slide with its messages
   coloured by whether anything else in the deck picks them up, and between
   slides the handoff coloured by whether the bumper sets up the next title.
   Right, what breaks, worst first — each item jumps to its place on the
   left. Statuses come from threadmap.flow(); only their look is decided
   here. */

const HANDOFF_LABEL = { smooth: 'Smooth handoff', weak: 'Weak handoff', abrupt: 'Abrupt cut' };
const num = i => String(i + 1).padStart(2, '0');

function ThreadGraph({ deck, onPick }) {
  const { data, state, deep } = useThreadMap(deck, true);
  const [sel, setSel] = useState(null);        // the element an issue points at
  const [peek, setPeek] = useState(null);      // the slide a linked message points at

  if (deck.slides.length < 2) {
    return <div className="tg__note">A thread needs at least two beats. Add another slide.</div>;
  }
  if (state === 'loading') return <div className="tg__note">Reading the deck{'…'}</div>;
  if (state === 'off') {
    return (
      <div className="tg__note">
        Thread analysis runs in the engine, and this build has none behind it.
        Run the local server to see how the deck connects.
      </div>
    );
  }
  if (!data) return null;

  const view = data.before;
  const g = view.graph || {};
  const fl = view.flow || { slides: [], handoffs: [] };
  const orphanSlides = new Set(g.orphans || []);
  const reasons = g.orphan_reasons || {};
  const idx = {};
  fl.slides.forEach(sl => { idx[sl.id] = sl.index; });
  const handoffAfter = {};
  fl.handoffs.forEach(h => { handoffAfter[h.from] = h; });

  // What breaks, worst first.
  const cuts = fl.handoffs.filter(h => h.status === 'abrupt');
  const weak = fl.handoffs.filter(h => h.status === 'weak');
  const strays = [];
  fl.slides.forEach(sl => sl.messages.forEach((m, k) => {
    if (m.status === 'orphan' && !orphanSlides.has(sl.id)) strays.push({ sl, m, k });
  }));
  const lonely = fl.slides.filter(sl => orphanSlides.has(sl.id));
  const total = cuts.length + weak.length + strays.length + lonely.length;

  function go(key) {
    setSel(key);
    const el = document.getElementById('tf-' + key);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  const on = key => (sel === key ? 'is-sel' : '');

  const spine = view.narrative_spine
    || (g.spine && g.spine.word ? `“${g.spine.word}” runs through ${g.spine.count} of ${fl.slides.length} beats.` : null);

  return (
    <div className="tf">
      <div className="tf__head">
        <div className="tf__headl">
          <span className="tg__title">How the story connects</span>
          <span className="tg__engine">
            {ENGINE_LABEL[view.engine] || view.engine}
            {deep === 'reading' ? ' · the model is reading it…'
              : deep === 'none' ? ' · the model did not answer, so this is the quick read'
              : deep === 'empty' ? ' · the model found nothing to add' : ''}
          </span>
        </div>
        <div className="tf__tally">
          <span className={`tf__chip tf__chip--bad ${cuts.length ? '' : 'is-zero'}`}>{cuts.length} abrupt cut{cuts.length === 1 ? '' : 's'}</span>
          <span className={`tf__chip tf__chip--warn ${weak.length ? '' : 'is-zero'}`}>{weak.length} weak</span>
          <span className={`tf__chip tf__chip--bad ${strays.length ? '' : 'is-zero'}`}>{strays.length} stray message{strays.length === 1 ? '' : 's'}</span>
          <span className={`tf__chip tf__chip--bad ${lonely.length ? '' : 'is-zero'}`}>{lonely.length} orphan slide{lonely.length === 1 ? '' : 's'}</span>
        </div>
      </div>
      {spine ? <p className="tf__spine"><b>Spine.</b> {spine}</p> : <p className="tf__spine"><b>No spine.</b> No one idea runs through most of the deck.</p>}

      <div className="tf__cols">
        {/* ── left: the deck as it runs ── */}
        <div className="tf__run">
          {fl.slides.map(sl => {
            const h = handoffAfter[sl.id];
            const lone = orphanSlides.has(sl.id);
            return (
              <React.Fragment key={sl.id}>
                <div id={`tf-s-${sl.id}`}
                  className={`tfs ${lone ? 'is-orphan' : ''} ${peek === sl.id ? 'is-peek' : ''} ${on('s-' + sl.id)}`}>
                  <button className="tfs__head" onClick={() => onPick && onPick(sl.id)} title="Open this beat on the board">
                    <span className="tfs__num tnum">{num(sl.index)}</span>
                    <span className="tfs__title">{sl.title}</span>
                    {lone ? <span className="tf__tag tf__tag--bad">orphan slide</span> : null}
                  </button>
                  <div className="tfs__msgs">
                    {sl.messages.map((m, k) => (
                      <div key={k} id={`tf-m-${sl.id}-${k}`}
                        className={`tfm tfm--${m.status} ${on(`m-${sl.id}-${k}`)}`}
                        onMouseEnter={() => m.picks_up && setPeek(m.picks_up)}
                        onMouseLeave={() => setPeek(null)}>
                        <i className="tfm__dot" />
                        <span className="tfm__text">{m.text}</span>
                        {m.status === 'linked' && m.picks_up != null ? (
                          <span className="tf__tag tf__tag--ok" title={m.shared && m.shared.length ? `shares: ${m.shared.join(', ')}` : 'close in meaning'}>
                            ↗ {num(idx[m.picks_up])}
                          </span>
                        ) : m.status === 'orphan' ? <span className="tf__tag tf__tag--bad">stray</span> : null}
                      </div>
                    ))}
                    {!sl.messages.length ? <div className="tfm tfm--empty"><span className="tfm__text">no messages</span></div> : null}
                  </div>
                  <div className={`tfs__bumper ${sl.bumper ? '' : 'is-none'}`}>
                    {sl.bumper ? <>“{sl.bumper}”</> : (h ? 'no bumper' : 'last beat')}
                  </div>
                </div>
                {h ? (
                  <div id={`tf-h-${h.from}`} className={`tfh tfh--${h.status} ${on('h-' + h.from)}`}>
                    <span className="tfh__line" />
                    <span className="tfh__pill">{HANDOFF_LABEL[h.status] || h.status}</span>
                    {h.status !== 'smooth' && h.no_bumper ? <span className="tfh__why">no bumper to hand off with</span> : null}
                  </div>
                ) : null}
              </React.Fragment>
            );
          })}
        </div>

        {/* ── right: what breaks ── */}
        <aside className="tf__fix">
          <div className="tf__fixh">What breaks</div>
          {total === 0 ? (
            <p className="tf__clean">Nothing. Every message is picked up or backs its slide, and every handoff lands.</p>
          ) : null}

          {cuts.length ? <div className="tf__grp tf__grp--bad">Abrupt cuts</div> : null}
          {cuts.map(h => (
            <button key={'c' + h.from} className={`tfx tfx--bad ${on('h-' + h.from)}`} onClick={() => go('h-' + h.from)}>
              <span className="tfx__where tnum">{num(idx[h.from])} → {num(idx[h.to])}</span>
              <span className="tfx__what">
                {h.no_bumper
                  ? <>No bumper. “{h.source}” does not set up “{h.next_title}”.</>
                  : <>“{h.source}” does not set up “{h.next_title}”.</>}
              </span>
              <span className="tfx__fix">Write a bumper that names what the next slide is about — or move the slide.</span>
            </button>
          ))}

          {lonely.length ? <div className="tf__grp tf__grp--bad">Orphan slides</div> : null}
          {lonely.map(sl => (
            <button key={'o' + sl.id} className={`tfx tfx--bad ${on('s-' + sl.id)}`} onClick={() => go('s-' + sl.id)}>
              <span className="tfx__where tnum">{num(sl.index)}</span>
              <span className="tfx__what">“{sl.title}” — {reasons[sl.id] || 'nothing else in the deck picks it up.'}</span>
              <span className="tfx__fix">Tie it to a neighbour, move it to an appendix, or cut it.</span>
            </button>
          ))}

          {strays.length ? <div className="tf__grp tf__grp--bad">Stray messages</div> : null}
          {strays.map(({ sl, m, k }) => (
            <button key={`m${sl.id}-${k}`} className={`tfx tfx--bad ${on(`m-${sl.id}-${k}`)}`} onClick={() => go(`m-${sl.id}-${k}`)}>
              <span className="tfx__where tnum">{num(sl.index)}</span>
              <span className="tfx__what">“{m.text}” backs neither its title nor anything else in the deck.</span>
              <span className="tfx__fix">Cut it, or rewrite it to support “{sl.title}”.</span>
            </button>
          ))}

          {weak.length ? <div className="tf__grp tf__grp--warn">Weak handoffs</div> : null}
          {weak.map(h => (
            <button key={'w' + h.from} className={`tfx tfx--warn ${on('h-' + h.from)}`} onClick={() => go('h-' + h.from)}>
              <span className="tfx__where tnum">{num(idx[h.from])} → {num(idx[h.to])}</span>
              <span className="tfx__what">“{h.source}” only loosely leads into “{h.next_title}”.</span>
            </button>
          ))}

          <div className="tf__legend">
            <span><i className="tfm__dot tfm__dot--linked" /> picked up elsewhere</span>
            <span><i className="tfm__dot tfm__dot--local" /> backs its own slide</span>
            <span><i className="tfm__dot tfm__dot--orphan" /> stray</span>
          </div>
        </aside>
      </div>
    </div>
  );
}

Object.assign(window, { ThreadGraph, toOutline });
