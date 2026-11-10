/* ============================================================
   ws-thread.jsx — the thread connectivity graph.

   A deck is connected when each slide shares meaning with its
   neighbours. deckengine/threadmap.py already computes that:
   nodes, weighted edges, orphans (a slide nothing links to),
   gaps (adjacent slides that do not connect) and the spine.
   Nothing rendered it until now.

   The backend emits pure data — no pixels, no colors (R0.1) —
   so the drawing lives here. Layout is deterministic: slides sit
   in deck order along a line, links arc above, and arc height
   tracks link weight. No physics, nothing to settle, the same
   deck always draws the same way.

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

/* ── the drawing ──────────────────────────────────────────── */
function ThreadGraph({ deck, onPick }) {
  const { data, state, deep } = useThreadMap(deck, true);
  const [hover, setHover] = useState(null);

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
  const g = view.graph;
  const n = g.nodes.length;
  const W = 820, H = 300, padX = 60, baseY = 214;
  const step = n > 1 ? (W - padX * 2) / (n - 1) : 0;
  // Labels must not run into each other on a long deck: fit the text to the
  // gap between beats, and alternate two rows once the gap gets tight.
  const stagger = step < 110;
  const maxChars = Math.max(6, Math.min(22, Math.floor((stagger ? step * 2 : step) / 6.4)));
  const clip = t => (t.length > maxChars ? t.slice(0, maxChars - 1) + '…' : t);
  const xOf = i => padX + i * step;
  const orphans = new Set(g.orphans || []);
  const gapPairs = new Set((g.gaps || []).map(x => `${x.from}->${x.to}`));
  const byId = {};
  g.nodes.forEach(nd => { byId[nd.id] = nd; });
  // Weights are on different scales per engine: a similarity in 0..1 for
  // embeddings, a COUNT (shared words, or shared recommendations) for the
  // other two. Draw them relative to the strongest link in this deck.
  const maxW = Math.max(1e-6, ...(g.edges || []).map(e => e.weight || 0));
  const rel = e => (e.weight || 0) / maxW;
  const linkNote = e => (view.engine === 'semantic'
    ? `${Math.round((e.weight || 0) * 100)}% similar`
    : view.engine === 'narrative'
      ? `linked by ${e.weight} note${e.weight === 1 ? '' : 's'}`
      : `${e.weight} shared word${e.weight === 1 ? '' : 's'}`);
  // orphan_reasons is {slide_id: reason}, present only on the model's read.
  const firstOrphan = (g.orphans || [])[0];
  const orphanReason = (g.orphan_reasons && firstOrphan && g.orphan_reasons[firstOrphan]) || null;

  return (
    <div className="tg">
      <div className="tg__head">
        <span className="tg__title">Thread connectivity</span>
        <span className="tg__engine">
          {ENGINE_LABEL[view.engine] || view.engine}
          {deep === 'reading' ? ' · the model is reading it…'
            : deep === 'none' ? ' · the model did not answer, so this is the quick read'
            : deep === 'empty' ? ' · the model found nothing to add' : ''}
        </span>
        <span className="tg__legend">
          <i className="tg__k tg__k--link" /> shared meaning
          <i className="tg__k tg__k--gap" /> hard cut
          <i className="tg__k tg__k--orphan" /> orphan
        </span>
      </div>

      <svg className="tg__svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        {/* the running order */}
        <line x1={padX} y1={baseY} x2={xOf(n - 1)} y2={baseY} className="tg__rail" />

        {/* a hard cut between adjacent beats */}
        {g.nodes.map((nd, i) => {
          if (i === 0) return null;
          const prev = g.nodes[i - 1];
          if (!gapPairs.has(`${prev.id}->${nd.id}`)) return null;
          const mx = (xOf(i - 1) + xOf(i)) / 2;
          return (
            <g key={`gap-${nd.id}`} className="tg__gap">
              <line x1={mx} y1={baseY - 16} x2={mx} y2={baseY + 16} />
              <text x={mx} y={baseY + 34} textAnchor="middle">cut</text>
            </g>
          );
        })}

        {/* links, arced above the running order */}
        {(g.edges || []).map((e, i) => {
          const a = byId[e.from], b = byId[e.to];
          if (!a || !b) return null;
          const x1 = xOf(a.index), x2 = xOf(b.index);
          const span = Math.abs(b.index - a.index);
          const lift = Math.min(150, 46 + span * 34);
          const on = hover && (hover === e.from || hover === e.to);
          return (
            <path key={i}
              className={`tg__edge ${on ? 'is-on' : ''}`}
              style={{ strokeWidth: 1 + rel(e) * 4 }}
              d={`M ${x1} ${baseY - 12} Q ${(x1 + x2) / 2} ${baseY - lift} ${x2} ${baseY - 12}`}>
              <title>{`${linkNote(e)}${e.shared && e.shared.length ? ' · ' + e.shared.join(' · ') : ''}`}</title>
            </path>
          );
        })}

        {/* the beats */}
        {g.nodes.map((nd, i) => {
          const isOrphan = orphans.has(nd.id);
          return (
            <g key={nd.id} className={`tg__node ${isOrphan ? 'is-orphan' : ''} ${hover === nd.id ? 'is-on' : ''}`}
               onMouseEnter={() => setHover(nd.id)} onMouseLeave={() => setHover(null)}
               onClick={() => onPick && onPick(nd.id)}>
              <circle cx={xOf(i)} cy={baseY - 12} r={isOrphan ? 11 : 9} />
              <text x={xOf(i)} y={baseY - 8} textAnchor="middle" className="tg__num">{i + 1}</text>
              <text x={xOf(i)} y={baseY + (stagger && i % 2 ? 72 : 56)} textAnchor="middle" className="tg__label">
                {clip(nd.title || '')}
                <title>{nd.title || ''}</title>
              </text>
            </g>
          );
        })}
      </svg>

      <div className="tg__read">
        {view.narrative_spine ? <p><b>Spine.</b> {view.narrative_spine}</p>
          : g.spine && g.spine.word ? <p><b>Spine.</b> “{g.spine.word}” runs through {g.spine.count} of {n} beats.</p>
          : <p><b>No spine.</b> No idea runs through most of the deck.</p>}
        {orphans.size
          ? <p><b>{orphans.size} orphan{orphans.size === 1 ? '' : 's'}.</b> {' '}
              {orphanReason
                ? <>“{(byId[firstOrphan] || {}).title}”: {orphanReason}</>
                : 'Nothing else in the deck picks this up — tie it to a neighbour or cut it.'}</p>
          : <p>No orphans — every beat connects to another.</p>}
        {(g.gaps || []).length
          ? <p><b>{g.gaps.length} hard cut{g.gaps.length === 1 ? '' : 's'}.</b> The bumper does not set up the next title, so the room has to jump.</p>
          : <p>No hard cuts — each beat hands off to the next.</p>}
      </div>
    </div>
  );
}

Object.assign(window, { ThreadGraph, toOutline });
