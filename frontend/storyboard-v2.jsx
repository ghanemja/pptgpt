/* ============================================================
   pptgpt storyboard.jsx — graph-of-ideas storyboard page
   ------------------------------------------------------------
   slide spine (left → right) with thread arcs above showing
   which themes connect which slides. click any slide to open a
   detail editor. AI suggestions surface structural fixes.
   ============================================================ */

const { useState, useEffect, useRef, useCallback, useMemo } = React;

/* ──────────────────────────────────────────────────────────── */
/* DATA                                                          */
/* ──────────────────────────────────────────────────────────── */

const ROLES = [
  { key: 'summary',   label: 'Summary',   color: '#11120E' },
  { key: 'setup',     label: 'Setup',     color: '#C99A2E' },
  { key: 'deep-dive', label: 'Deep dive', color: '#0E5B36' },
  { key: 'decision',  label: 'Decision',  color: '#E26A2C' },
  { key: 'risk',      label: 'Risk',      color: '#C4502B' },
];

const ROLE_BY_KEY = Object.fromEntries(ROLES.map(r => [r.key, r]));

const INITIAL_DECK = {
  title: 'Q3 review  ·  and what we do next',
  audience: 'Exec review',
  mode: 'Condense  ·  28 → 6',
  slides: [
    {
      id: 's1',
      role: 'summary',
      title: 'Q3 beat plan by 14%',
      messages: [
        'Revenue +14% YoY ($42M)',
        'Net retention 118%, churn 1.8%',
        'Two design-partner wins in public sector',
      ],
      bumper: 'Let\u2019s look at what drove it.',
    },
    {
      id: 's2',
      role: 'deep-dive',
      title: 'Three things drove the beat',
      messages: [
        'Enterprise close rate doubled vs H1',
        'Multi-year deals = 60% of new ARR',
        'Public sector wins are compounding',
      ],
      bumper: 'Retention is the engine underneath.',
    },
    {
      id: 's3',
      role: 'deep-dive',
      title: 'Retention is the engine',
      messages: [
        'NRR 118% across all three segments',
        'Churn down to 1.8% from 3.2% in H1',
        'Expansion accounts for 40% of growth',
      ],
      bumper: 'Onboarding has become the bottleneck.',
    },
    {
      id: 's4',
      role: 'risk',
      title: 'Onboarding pressure is real',
      messages: [
        'Activation down 8 points since redesign',
        'Three at-risk cohorts identified',
        'Rollback under review — D. Park, Oct 22',
      ],
      bumper: 'Which lands us on Q4 decisions.',
    },
    {
      id: 's5',
      role: 'decision',
      title: 'Q4 decisions on the table',
      messages: [
        'Double down on enterprise GTM',
        'Pause SMB self-serve experiments',
        'Shift 40% of marketing to enterprise',
      ],
      bumper: 'And here\u2019s what we\u2019re watching.',
    },
    {
      id: 's6',
      role: 'risk',
      title: 'Risks worth naming',
      messages: [
        'Pricing power test in November',
        'Two unfilled GTM hires (eng + CS)',
        'Macro headwinds softening EU pipeline',
      ],
      bumper: '',
    },
  ],
};

const INITIAL_THREADS = [
  { id: 't1', label: 'Revenue + beat',   color: '#0E5B36', slideIds: ['s1','s2','s5'], strength: 0.92, type: 'core' },
  { id: 't2', label: 'Retention engine', color: '#E26A2C', slideIds: ['s1','s2','s3'], strength: 0.78, type: 'core' },
  { id: 't3', label: 'Enterprise GTM',   color: '#5468C9', slideIds: ['s2','s5'],      strength: 0.65, type: 'arc' },
  { id: 't4', label: 'Q4 decisions',     color: '#C99A2E', slideIds: ['s4','s5'],      strength: 0.85, type: 'arc' },
  { id: 't5', label: 'Risks to watch',   color: '#C4502B', slideIds: ['s4','s6'],      strength: 0.55, type: 'arc' },
];

const INITIAL_SUGGESTIONS = [
  {
    id: 'r1',
    kind: 'merge',
    text: 'Slides 2 and 3 share four keywords — consider merging into one stronger deep-dive.',
    slideIds: ['s2','s3'],
    actions: ['merge', 'dismiss'],
  },
  {
    id: 'r2',
    kind: 'order',
    text: 'Strongest call-to-action lives on slide 5. Try opening with the decision instead.',
    slideIds: ['s5'],
    actions: ['reorder', 'dismiss'],
  },
  {
    id: 'r3',
    kind: 'thin',
    text: 'Slide 6 touches one thread weakly. Develop the risk story or fold it into slide 5.',
    slideIds: ['s6'],
    actions: ['develop', 'dismiss'],
  },
];

/* ──────────────────────────────────────────────────────────── */
/* HELPERS                                                       */
/* ──────────────────────────────────────────────────────────── */

function clamp01(x) { return Math.max(0, Math.min(1, x)); }

function indexOfSlide(slides, id) {
  return slides.findIndex(s => s.id === id);
}

function threadsForSlide(slideId, threads) {
  return threads.filter(t => t.slideIds.includes(slideId));
}

// the "connection strength" of a slide = sum of thread strengths it touches
function slideStrength(slideId, threads) {
  const ts = threadsForSlide(slideId, threads);
  const sum = ts.reduce((s, t) => s + t.strength, 0);
  return clamp01(sum / 2.5); // normalize to roughly 0..1
}

/* ──────────────────────────────────────────────────────────── */
/* NAV                                                            */
/* ──────────────────────────────────────────────────────────── */

function Nav({ onBack }) {
  return (
    <nav className="nav">
      <div className="brand">
        <span className="brand__mark" />
        pptgpt
        <span className="brand__path">
          <span className="brand__path-sep">/</span>
          workbench
          <span className="brand__path-sep">/</span>
          <strong>storyboard</strong>
        </span>
      </div>
      <div className="nav__right">
        <button className="btn btn--ghost" onClick={onBack}>← back to landing</button>
        <button className="btn btn--outline">save draft</button>
        <button className="btn btn--primary">
          continue to workbench
          <svg viewBox="0 0 16 16" fill="none">
            <path d="M3 8 L13 8 M9 4 L13 8 L9 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </nav>
  );
}

/* ──────────────────────────────────────────────────────────── */
/* PAGE HEAD                                                     */
/* ──────────────────────────────────────────────────────────── */

function PageHead({ deck, onTitleChange }) {
  return (
    <header className="page-head">
      <div className="page-head__top">
        <span className="page-head__step">
          <span className="num">1</span> upload
        </span>
        <span className="page-head__sep">·</span>
        <span className="page-head__step">
          <span className="num">2</span> pick
        </span>
        <span className="page-head__sep">·</span>
        <span className="page-head__step is-active">
          <span className="num">3</span> storyboard
        </span>
        <span className="page-head__sep">·</span>
        <span className="page-head__step">
          <span className="num">4</span> workbench
        </span>
        <span className="page-head__sep">·</span>
        <span className="page-head__step">
          <span className="num">5</span> critique
        </span>
      </div>
      <div className="page-head__row">
        <h1 className="page-head__title">
          <input
            className="page-head__title-input"
            value={deck.title}
            onChange={(e) => onTitleChange(e.target.value)}
          />
        </h1>
        <div className="page-head__meta">
          <span className="meta-pill">
            <span className="meta-pill__label">room</span>
            <span className="meta-pill__dot" style={{ background: 'var(--ink)' }} />
            {deck.audience}
          </span>
          <span className="meta-pill">
            <span className="meta-pill__label">mode</span>
            <span className="meta-pill__dot" style={{ background: 'var(--accent)' }} />
            {deck.mode}
          </span>
          <span className="meta-pill">
            <span className="meta-pill__label">slides</span>
            <span className="meta-pill__dot" style={{ background: 'var(--spark)' }} />
            {deck.slides.length}
          </span>
        </div>
      </div>
    </header>
  );
}

/* ──────────────────────────────────────────────────────────── */
/* SUGGESTIONS BAR                                                */
/* ──────────────────────────────────────────────────────────── */

function Suggestions({ items, onAct, onDismiss, onHover }) {
  if (items.length === 0) return null;
  return (
    <div className="suggestions">
      <div className="suggestions__inner">
        <div className="suggestions__pill">
          <span className="suggestions__pill-num">{items.length}</span>
          AI noticed
        </div>
        <div className="suggestions__list">
          {items.map(s => (
            <div
              key={s.id}
              className="sugg-card"
              onMouseEnter={() => onHover(s.slideIds)}
              onMouseLeave={() => onHover(null)}
            >
              <div className={`sugg-card__kind is-${s.kind}`}>{s.kind}</div>
              <div className="sugg-card__text">{s.text}</div>
              <div className="sugg-card__actions">
                <button className="sugg-btn sugg-btn--accept" onClick={() => onAct(s)}>accept</button>
                <button className="sugg-btn" onClick={() => onDismiss(s.id)}>dismiss</button>
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--mute)' }}>
          hover a card<br/>to highlight
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────── */
/* THREAD LEGEND + TRACKS                                         */
/* ──────────────────────────────────────────────────────────── */

function ThreadLegend({ threads, activeId, onToggle, onHover }) {
  return (
    <div className="thread-legend">
      <span className="thread-legend__label">threads</span>
      {threads.map(t => (
        <button
          key={t.id}
          className={`thread-chip ${activeId === t.id ? 'is-active' : ''}`}
          style={{ color: activeId === t.id ? '#fff' : t.color }}
          onClick={() => onToggle(t.id)}
          onMouseEnter={() => onHover(t.id)}
          onMouseLeave={() => onHover(null)}
        >
          <span className="thread-chip__dot" />
          {t.label}
          <span className="thread-chip__count">{t.slideIds.length}</span>
        </button>
      ))}
      <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--mute)', marginLeft: 'auto' }}>
        click a thread to focus
      </span>
    </div>
  );
}

function Tracks({ threads, slides, activeId, hoverId }) {
  const slideCount = slides.length;
  const isFocused = activeId != null || hoverId != null;
  const focusId = hoverId || activeId;

  return (
    <div className="tracks">
      {threads.map(thread => {
        const isFocus = focusId === thread.id;
        const isDim = isFocused && !isFocus;
        const slideIdxs = thread.slideIds.map(sid => indexOfSlide(slides, sid)).filter(i => i >= 0).sort((a, b) => a - b);
        const minI = slideIdxs[0];
        const maxI = slideIdxs[slideIdxs.length - 1];

        return (
          <div
            key={thread.id}
            className={`track ${isDim ? 'is-dim' : ''} ${isFocus ? 'is-highlight' : ''}`}
            style={{ color: thread.color }}
          >
            <div className="track__label">
              <span className="track__label-dot" style={{ background: thread.color }} />
              {thread.label}
            </div>
            <div
              className="track__row"
              style={{ gridTemplateColumns: `repeat(${slideCount}, 1fr)` }}
            >
              {slides.map((slide, i) => {
                const isOn = thread.slideIds.includes(slide.id);
                const isBetween = i > minI && i < maxI;
                const showLine = isBetween || (isOn && i < maxI);
                const isStart = i === minI && isOn;
                return (
                  <div className="track__cell" key={slide.id}>
                    {/* line segment to the right cell, if this is on a stretch */}
                    {showLine && (
                      <div
                        className="track__line"
                        style={{
                          left: isStart ? '50%' : 0,
                          right: i === maxI ? '50%' : 0,
                          animationDelay: `${0.2 + i * 0.05}s`,
                        }}
                      />
                    )}
                    {isOn && (
                      <div
                        className="track__node"
                        style={{
                          animationDelay: `${0.3 + i * 0.06}s`,
                        }}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────── */
/* SLIDE CARD                                                    */
/* ──────────────────────────────────────────────────────────── */

function SlideCard({ slide, idx, threads, isSelected, isDimmed, hasWarning, onSelect }) {
  const slideThreads = threadsForSlide(slide.id, threads);
  const strength = slideStrength(slide.id, threads);
  const role = ROLE_BY_KEY[slide.role] || ROLE_BY_KEY['summary'];

  // refs for the tiles so we can draw graph wires between them
  const cardRef = useRef(null);
  const titleRef = useRef(null);
  const msgRefs = useRef([]);
  const bumperRef = useRef(null);
  const [wires, setWires] = useState({ primary: [], secondary: [], w: 0, h: 0 });

  React.useLayoutEffect(() => {
    function compute() {
      const card = cardRef.current;
      const title = titleRef.current;
      const msgs = msgRefs.current.filter(Boolean);
      const bumper = bumperRef.current;
      if (!card || !title || msgs.length === 0) return;

      const cr = card.getBoundingClientRect();
      const pad = 8; // shave a bit so wires terminate at the tile edge
      const portsTop = (el) => {
        const r = el.getBoundingClientRect();
        const left = r.left - cr.left + r.width * 0.18;
        const mid  = r.left - cr.left + r.width * 0.50;
        const right= r.left - cr.left + r.width * 0.82;
        return { left, mid, right, y: r.top - cr.top + 2 };
      };
      const portsBot = (el) => {
        const r = el.getBoundingClientRect();
        const left = r.left - cr.left + r.width * 0.18;
        const mid  = r.left - cr.left + r.width * 0.50;
        const right= r.left - cr.left + r.width * 0.82;
        return { left, mid, right, y: r.bottom - cr.top - 2 };
      };

      const tB = portsBot(title);
      const mTops = msgs.map(portsTop);
      const mBots = msgs.map(portsBot);
      const bT = bumper ? portsTop(bumper) : null;

      // cubic-bezier path with a smooth vertical handle
      function curve(x1, y1, x2, y2) {
        const dy = Math.abs(y2 - y1);
        const h = Math.max(10, dy * 0.55);
        return `M ${x1} ${y1} C ${x1} ${y1 + h}, ${x2} ${y2 - h}, ${x2} ${y2}`;
      }

      const primary = [];
      const secondary = [];

      // Build a sequential chain of tiles: title → msg1 → msg2 → msg3 → bumper
      // Each step gets criss-cross wires (primary going down, secondary doing the X)
      const chain = [
        { bot: tB, top: null },                    // title (only bottom port matters)
        ...msgs.map((_, i) => ({ bot: mBots[i], top: mTops[i] })),
      ];
      if (bT) chain.push({ bot: null, top: bT });

      for (let i = 0; i < chain.length - 1; i++) {
        const from = chain[i];
        const to = chain[i + 1];
        if (!from.bot || !to.top) continue;
        const fromPorts = [from.bot.left, from.bot.mid, from.bot.right];
        const toPorts   = [to.top.left,   to.top.mid,   to.top.right];
        // primary (parallel): left→left, mid→mid, right→right
        primary.push(curve(fromPorts[1], from.bot.y, toPorts[1], to.top.y));
        // secondary (crossing): left→right, right→left  (the criss-cross)
        secondary.push(curve(fromPorts[0], from.bot.y, toPorts[2], to.top.y));
        secondary.push(curve(fromPorts[2], from.bot.y, toPorts[0], to.top.y));
      }

      // Long cross-links — title to msg-3 left, title to bumper-right (graph feel)
      if (mTops.length >= 3) {
        secondary.push(curve(tB.left, tB.y, mTops[2].left, mTops[2].y));
      }
      if (bT && mBots.length >= 1) {
        secondary.push(curve(mBots[0].right, mBots[0].y, bT.right, bT.y));
      }

      setWires({ primary, secondary, w: cr.width, h: cr.height });
    }

    compute();
    const ro = new ResizeObserver(compute);
    if (cardRef.current) ro.observe(cardRef.current);
    if (titleRef.current) ro.observe(titleRef.current);
    msgRefs.current.forEach(el => el && ro.observe(el));
    if (bumperRef.current) ro.observe(bumperRef.current);
    return () => ro.disconnect();
  }, [slide.title, slide.messages, slide.bumper]);

  return (
    <div
      ref={cardRef}
      data-role={slide.role}
      className={`slide-card ${isSelected ? 'is-selected' : ''} ${isDimmed ? 'is-dimmed' : ''}`}
      style={{ animationDelay: `${idx * 80}ms` }}
      onClick={() => onSelect(slide.id)}
    >
      <svg className="slide-card__wires" preserveAspectRatio="none" viewBox={`0 0 ${wires.w || 1} ${wires.h || 1}`} width={wires.w} height={wires.h}>
        {wires.secondary.map((d, i) => (
          <path key={`s${i}`} className="slide-card__wire is-secondary" d={d} style={{ animationDelay: `${(idx * 80) + 240 + i * 40}ms` }} />
        ))}
        {wires.primary.map((d, i) => (
          <path key={`p${i}`} className="slide-card__wire" d={d} style={{ animationDelay: `${(idx * 80) + 220 + i * 30}ms` }} />
        ))}
      </svg>
      {hasWarning && <div className="slide-card__warning">!</div>}
      <div className="slide-card__head">
        <span className="slide-card__num">slide {String(idx + 1).padStart(2, '0')}</span>
        <span className={`slide-card__role is-${slide.role}`}>{role.label}</span>
      </div>
      <h3 ref={titleRef} className="slide-card__title">{slide.title || 'Untitled'}</h3>
      <ul className="slide-card__msgs">
        {[0, 1, 2].map(i => {
          const m = (slide.messages || [])[i];
          if (!m) {
            return (
              <li
                key={i}
                ref={el => msgRefs.current[i] = el}
                className="slide-card__msg is-empty"
                data-num={String(i + 1).padStart(2, '0')}
              >
                empty message
              </li>
            );
          }
          return (
            <li
              key={i}
              ref={el => msgRefs.current[i] = el}
              className="slide-card__msg"
              data-num={String(i + 1).padStart(2, '0')}
            >
              {m}
            </li>
          );
        })}
      </ul>
      {slide.bumper ? (
        <div ref={bumperRef} className="slide-card__bumper">{slide.bumper}</div>
      ) : (
        <div ref={bumperRef} className="slide-card__bumper is-empty">no bumper to next slide</div>
      )}
      <div className="slide-card__threads">
        {slideThreads.map(t => (
          <span
            key={t.id}
            className={`slide-card__thread-dot ${t.strength > 0.7 ? 'is-strong' : ''}`}
            style={{ color: t.color }}
            title={t.label}
          />
        ))}
      </div>
      <div className="slide-card__strength">
        <span>flow</span>
        <div className="slide-card__strength-bar">
          <div className="slide-card__strength-fill" style={{ width: `${Math.max(8, strength * 100)}%` }} />
        </div>
        <span>{Math.round(strength * 100)}</span>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────── */
/* SLIDE ROW                                                     */
/* ──────────────────────────────────────────────────────────── */

function InterSlideWires({ slides }) {
  const ref = useRef(null);
  const [state, setState] = useState({ wires: [], w: 0, h: 0 });

  React.useLayoutEffect(() => {
    function compute() {
      const host = ref.current;
      if (!host) return;
      const parent = host.parentElement;
      if (!parent) return;
      const pr = parent.getBoundingClientRect();
      const cards = parent.querySelectorAll('.slide-card');
      const wires = [];
      for (let i = 0; i < cards.length - 1; i++) {
        const a = cards[i];
        const b = cards[i + 1];
        const bumperA = a.querySelector('.slide-card__bumper');
        const titleB = b.querySelector('.slide-card__title');
        if (!bumperA || !titleB) continue;
        const ra = bumperA.getBoundingClientRect();
        const rb = titleB.getBoundingClientRect();
        const x1 = ra.right - pr.left - 1;
        const y1 = ra.top + ra.height * 0.5 - pr.top;
        const x2 = rb.left - pr.left + 1;
        const y2 = rb.top + rb.height * 0.5 - pr.top;
        const midX = (x1 + x2) / 2;
        // S-curve: hand off horizontally first, then arc up to next title
        const d = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
        wires.push({ d, x2, y2, key: `iw-${i}` });
      }
      setState({ wires, w: pr.width, h: pr.height });
    }
    compute();
    const ro = new ResizeObserver(compute);
    const parent = ref.current && ref.current.parentElement;
    if (parent) ro.observe(parent);
    parent && parent.querySelectorAll('.slide-card').forEach(c => ro.observe(c));
    return () => ro.disconnect();
  }, [slides]);

  return (
    <svg
      ref={ref}
      className="inter-wires"
      viewBox={`0 0 ${state.w || 1} ${state.h || 1}`}
      preserveAspectRatio="none"
      width={state.w}
      height={state.h}
    >
      <defs>
        <marker id="inter-arrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M 0 0 L 7 4 L 0 8 z" className="inter-wire__head" />
        </marker>
      </defs>
      {state.wires.map((w, i) => (
        <g key={w.key}>
          <path className="inter-wire" d={w.d} markerEnd="url(#inter-arrow)" style={{ animationDelay: `${0.4 + i * 0.08}s` }} />
        </g>
      ))}
    </svg>
  );
}

function WireLegend() {
  return (
    <div className="wire-legend">
      <span className="wire-legend__label">wires</span>
      <span className="wire-legend__item">
        <span className="wire-legend__swatch">
          <svg viewBox="0 0 28 8"><path d="M2 4 L26 4" stroke="#0E5B36" strokeWidth="1.4" strokeDasharray="2.5 3.5" fill="none" strokeLinecap="round" /></svg>
        </span>
        title ↔ messages ↔ bumper  ·  <em style={{ color: 'var(--ink)', fontStyle: 'normal', fontWeight: 600 }}>colored by slide role</em>
      </span>
      <span className="wire-legend__sep" />
      <span className="wire-legend__item">
        <span className="wire-legend__swatch">
          <svg viewBox="0 0 28 8"><path d="M2 4 L24 4" stroke="#11120E" strokeWidth="1.6" strokeDasharray="5 4" fill="none" strokeLinecap="round" /><path d="M22 1 L27 4 L22 7 Z" fill="#11120E" opacity="0.7" /></svg>
        </span>
        bumper → next title  ·  <em style={{ color: 'var(--ink)', fontStyle: 'normal', fontWeight: 600 }}>narrative handoff</em>
      </span>
      <span className="wire-legend__sep" />
      <span className="wire-legend__item" style={{ marginLeft: 'auto' }}>
        <span style={{ display: 'inline-flex', gap: 4 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#11120E' }} title="Summary" />
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#C99A2E' }} title="Setup" />
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#0E5B36' }} title="Deep dive" />
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#E26A2C' }} title="Decision" />
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#C4502B' }} title="Risk" />
        </span>
        5 slide roles
      </span>
    </div>
  );
}

function SlideRow({ slides, threads, selectedId, highlightSet, warningSet, onSelectSlide, onAddSlide }) {
  const slideCount = slides.length;
  const gridCols = `repeat(${slideCount}, 1fr) 200px`;
  return (
    <div className="slide-row-wrap">
      <div
        className="slide-row"
        style={{ gridTemplateColumns: gridCols }}
      >
        {slides.map((slide, i) => {
          const isHL = highlightSet ? highlightSet.has(slide.id) : false;
          const isDimmed = highlightSet && !isHL;
          return (
            <React.Fragment key={slide.id}>
              <SlideCard
                slide={slide}
                idx={i}
                threads={threads}
                isSelected={selectedId === slide.id}
                isDimmed={isDimmed}
                hasWarning={warningSet && warningSet.has(slide.id)}
                onSelect={onSelectSlide}
              />
            </React.Fragment>
          );
        })}
        <button className="slide-add" onClick={onAddSlide}>
          <span className="slide-add__plus">+</span>
          <span className="slide-add__label">add slide</span>
        </button>
      </div>
      <InterSlideWires slides={slides} />
    </div>
  );
}

/* ──────────────────────────────────────────────────────────── */
/* DETAIL PANEL                                                  */
/* ──────────────────────────────────────────────────────────── */

function DetailPanel({ slide, idx, threads, isOpen, onClose, onEdit, onDelete, onDuplicate }) {
  if (!slide) return (
    <div className={`detail-overlay ${isOpen ? 'is-open' : ''}`}>
      <div className="detail-panel" />
    </div>
  );
  const slideThreads = threadsForSlide(slide.id, threads);
  return (
    <div
      className={`detail-overlay ${isOpen ? 'is-open' : ''}`}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="detail-panel">
        <div className="detail__head">
          <div className="detail__head-left">
            <span className="detail__head-num">SLIDE {String(idx + 1).padStart(2, '0')}</span>
            <span className={`slide-card__role is-${slide.role}`}>{(ROLE_BY_KEY[slide.role] || ROLES[0]).label}</span>
          </div>
          <button className="detail__close" onClick={onClose}>×</button>
        </div>
        <div className="detail__grid">
          <div>
            <div className="detail__col-label">title</div>
            <input
              className="detail__title-input"
              value={slide.title}
              onChange={(e) => onEdit({ title: e.target.value })}
              placeholder="What is this slide saying?"
            />
            <div className="detail__col-label" style={{ marginTop: 22 }}>three messages</div>
            {[0, 1, 2].map(i => (
              <div className="detail__msg" key={i}>
                <span className="detail__msg-num">{String(i + 1).padStart(2, '0')}</span>
                <textarea
                  className="detail__msg-input"
                  rows={1}
                  value={(slide.messages || [])[i] || ''}
                  onChange={(e) => {
                    const next = [...(slide.messages || ['', '', ''])];
                    while (next.length < 3) next.push('');
                    next[i] = e.target.value;
                    onEdit({ messages: next });
                  }}
                  placeholder={`Message ${i + 1}…`}
                  onInput={(e) => {
                    e.target.style.height = 'auto';
                    e.target.style.height = e.target.scrollHeight + 'px';
                  }}
                />
              </div>
            ))}
            <div className="detail__bumper">
              <div className="detail__bumper-label">bumper to next slide</div>
              <textarea
                className="detail__bumper-input"
                rows={2}
                value={slide.bumper || ''}
                onChange={(e) => onEdit({ bumper: e.target.value })}
                placeholder="One line that hands off to the next slide…"
                onInput={(e) => {
                  e.target.style.height = 'auto';
                  e.target.style.height = e.target.scrollHeight + 'px';
                }}
              />
            </div>
          </div>
          <div>
            <div className="detail__col-label">role  ·  what is this slide doing?</div>
            <div className="detail__roles" style={{ marginBottom: 24 }}>
              {ROLES.map(r => (
                <button
                  key={r.key}
                  className={`detail__role-chip ${slide.role === r.key ? 'is-active' : ''}`}
                  onClick={() => onEdit({ role: r.key })}
                >
                  <span className="detail__role-chip-dot" style={{ background: r.color }} />
                  {r.label}
                </button>
              ))}
            </div>
            <div className="detail__col-label">connects to  ·  {slideThreads.length} thread{slideThreads.length === 1 ? '' : 's'}</div>
            <div className="detail__threads">
              {slideThreads.length === 0 && (
                <div style={{ fontSize: 13, color: 'var(--mute)', padding: '12px 0' }}>
                  This slide doesn't connect to any thread in the deck. Consider strengthening or removing it.
                </div>
              )}
              {slideThreads.map(t => (
                <div className="detail__thread" key={t.id}>
                  <div className="detail__thread-left">
                    <span className="detail__thread-dot" style={{ background: t.color }} />
                    <span style={{ fontSize: 13.5, fontWeight: 500 }}>{t.label}</span>
                  </div>
                  <span className="detail__thread-strength">
                    {Math.round(t.strength * 100)}% strength
                  </span>
                </div>
              ))}
            </div>
            <div className="detail__col-label">actions</div>
            <div className="detail__actions">
              <button className="btn btn--outline" onClick={onDuplicate}>
                <svg viewBox="0 0 16 16" fill="none">
                  <rect x="3" y="3" width="9" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
                  <rect x="6" y="6" width="9" height="9" rx="1.5" fill="var(--card)" stroke="currentColor" strokeWidth="1.5" />
                </svg>
                duplicate
              </button>
              <button className="btn btn--ghost" onClick={onDelete}>
                <svg viewBox="0 0 16 16" fill="none">
                  <path d="M3 5 L13 5 M6 5 L6 3 L10 3 L10 5 M5 5 L5 13 L11 13 L11 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                delete slide
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────── */
/* LIVE-DATA SURFACES (engine badge, spine bar, tensions strip)  */
/* ──────────────────────────────────────────────────────────── */

function EngineBadge({ engine, backendInfo }) {
  if (!engine || engine === 'empty') return null;
  const label =
    engine === 'narrative' ? `◆ narrative · ${backendInfo.model || (backendInfo.backend === 'ollama' ? 'gemma' : 'claude')}` :
    engine === 'semantic'  ? '◉ semantic'  :
                             '○ lexical (fallback)';
  const tip =
    engine === 'narrative' ? 'An LLM read the deck and reasoned about story structure.' :
    engine === 'semantic'  ? 'Sentence-transformer embeddings. Catches synonyms; no narrative reasoning. Set ANTHROPIC_API_KEY or DECKENGINE_NARRATIVE_BACKEND=ollama to upgrade.' :
                             'Bag-of-words token overlap only. Install sentence-transformers (or configure an LLM) for real analysis.';
  return (
    <div className={`engine-badge engine-badge--${engine}`} title={tip}>
      {label}
    </div>
  );
}

function SpineBar({ spine }) {
  if (!spine || !spine.text) return null;
  return (
    <div className={`spine-bar spine-bar--${spine.kind || 'concept'}`}>
      <span className="spine-bar__eyebrow">through-line</span>
      <span className="spine-bar__text">{spine.text}</span>
      {spine.arc && <span className="spine-bar__arc">{spine.arc}</span>}
    </div>
  );
}

function TensionsStrip({ tensions }) {
  if (!tensions || tensions.length === 0) return null;
  return (
    <div className="tensions-strip">
      <span className="tensions-strip__label">tensions</span>
      <ul>
        {tensions.map((t, i) => (
          <li key={i} className={`tensions-strip__row tensions-strip__row--${t.kind}`}>
            <span className="tensions-strip__kind">{t.kind}</span>
            <span className="tensions-strip__text">{t.issue}</span>
            <span className="tensions-strip__slides">slides {(t.slide_idx || []).join(' · ')}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────── */
/* MAIN STORYBOARD                                                */
/* ──────────────────────────────────────────────────────────── */

function readSetupFromSession() {
  try {
    const raw = sessionStorage.getItem('pptgpt.setup');
    if (!raw) return null;
    const s = JSON.parse(raw);
    const overlay = {};
    if (s.title) overlay.title = s.title;
    if (s.audience) overlay.audience = s.audience;
    if (s.mode) overlay.mode = s.mode;
    if (s.stakes) overlay.stakes = s.stakes;
    return overlay;
  } catch (_) {
    return null;
  }
}

function Storyboard() {
  const [deck, setDeck] = useState(() => {
    const overlay = readSetupFromSession();
    return overlay ? { ...INITIAL_DECK, ...overlay } : INITIAL_DECK;
  });
  const [threads, setThreads] = useState(INITIAL_THREADS);
  const [suggestions, setSuggestions] = useState(INITIAL_SUGGESTIONS);
  const [selectedSlideId, setSelectedSlideId] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [hoverThreadId, setHoverThreadId] = useState(null);
  const [hoverWarnIds, setHoverWarnIds] = useState(null);

  // Live-data state — populated by /api/storyboard_view. While the request
  // is in flight we keep the previous threads/suggestions so the UI doesn't
  // flash empty on every edit.
  const [spine, setSpine] = useState(null);          // {text, arc, kind} | null
  const [tensions, setTensions] = useState([]);      // [{slides, slide_idx, issue, kind}]
  const [engine, setEngine] = useState(null);        // 'narrative' | 'semantic' | 'lexical' | 'empty'
  const [backendInfo, setBackendInfo] = useState({}); // {backend, model}
  const [dismissedSugg, setDismissedSugg] = useState(() => new Set());

  // Fetch live narrative + threadmap whenever the deck content changes
  // (debounced so typing in the detail panel doesn't hammer the backend).
  useEffect(() => {
    const onlyHttp = (location.protocol === 'http:' || location.protocol === 'https:');
    if (!onlyHttp) return;
    const handle = setTimeout(() => {
      let cancelled = false;
      (async () => {
        try {
          const res = await fetch(location.origin + '/api/storyboard_view', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
              outline:  deck.slides,
              audience: deck.audience || null,
              mode:     deck.mode || 'condense',
            }),
          });
          if (!res.ok) throw new Error('storyboard_view ' + res.status);
          const v = await res.json();
          if (cancelled) return;
          // graft roles from the LLM into the deck if it provided any
          if (v.outline) {
            setDeck(d => ({
              ...d,
              slides: d.slides.map(s => {
                const live = v.outline.find(x => x.id === s.id);
                return live && live.role && live.role !== s.role ? { ...s, role: live.role } : s;
              }),
            }));
          }
          if (Array.isArray(v.threads))     setThreads(v.threads);
          if (Array.isArray(v.suggestions)) {
            setSuggestions(v.suggestions.filter(s => !dismissedSugg.has(s.id)));
          }
          setSpine(v.spine || null);
          setTensions(v.tensions || []);
          setEngine(v.engine || null);
          setBackendInfo({ backend: v.backend || null, model: v.model || null });
        } catch (err) {
          // Server down or fetch failed — keep whatever we have and log it.
          console.warn('[storyboard] live-data fetch failed:', err.message);
        }
      })();
      return () => { cancelled = true; };
    }, 600);
    return () => clearTimeout(handle);
  // We deliberately re-fetch on slides content/order change, not on dismissedSugg
  // (dismissals are local state, not a backend concern).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(deck.slides), deck.audience, deck.mode]);

  // computed highlight set (which slides are highlighted)
  const focusThreadId = hoverThreadId || activeThreadId;
  const focusThread = focusThreadId ? threads.find(t => t.id === focusThreadId) : null;
  const focusedSlideSet = focusThread ? new Set(focusThread.slideIds) : null;
  const warningSlideSet = hoverWarnIds ? new Set(hoverWarnIds) : null;

  // pick selected slide info
  const selectedIdx = selectedSlideId ? indexOfSlide(deck.slides, selectedSlideId) : -1;
  const selectedSlide = selectedIdx >= 0 ? deck.slides[selectedIdx] : null;

  const handleTitleChange = useCallback((title) => {
    setDeck(d => ({ ...d, title }));
  }, []);

  const handleSelectSlide = useCallback((id) => {
    setSelectedSlideId(id);
    setDetailOpen(true);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setDetailOpen(false);
    // keep selectedSlideId so animations finish cleanly
    setTimeout(() => setSelectedSlideId(null), 320);
  }, []);

  const handleEditSlide = useCallback((patch) => {
    setDeck(d => ({
      ...d,
      slides: d.slides.map(s => s.id === selectedSlideId ? { ...s, ...patch } : s),
    }));
  }, [selectedSlideId]);

  const handleDeleteSlide = useCallback(() => {
    setDeck(d => ({ ...d, slides: d.slides.filter(s => s.id !== selectedSlideId) }));
    setThreads(ts => ts.map(t => ({ ...t, slideIds: t.slideIds.filter(id => id !== selectedSlideId) })).filter(t => t.slideIds.length > 0));
    handleCloseDetail();
  }, [selectedSlideId, handleCloseDetail]);

  const handleDuplicateSlide = useCallback(() => {
    setDeck(d => {
      const idx = d.slides.findIndex(s => s.id === selectedSlideId);
      if (idx < 0) return d;
      const src = d.slides[idx];
      const next = {
        ...src,
        id: 's' + Date.now().toString(36),
        title: src.title + ' (copy)',
      };
      const slides = [...d.slides];
      slides.splice(idx + 1, 0, next);
      return { ...d, slides };
    });
  }, [selectedSlideId]);

  const handleAddSlide = useCallback(() => {
    setDeck(d => ({
      ...d,
      slides: [
        ...d.slides,
        {
          id: 's' + Date.now().toString(36),
          role: 'summary',
          title: 'New slide',
          messages: ['', '', ''],
          bumper: '',
        },
      ],
    }));
  }, []);

  const handleToggleThread = useCallback((id) => {
    setActiveThreadId(prev => prev === id ? null : id);
  }, []);

  const handleAcceptSuggestion = useCallback((s) => {
    if (s.kind === 'merge' && s.slideIds.length >= 2) {
      const [aId, bId] = s.slideIds;
      setDeck(d => {
        const aIdx = d.slides.findIndex(x => x.id === aId);
        const bIdx = d.slides.findIndex(x => x.id === bId);
        if (aIdx < 0 || bIdx < 0) return d;
        const a = d.slides[aIdx];
        const b = d.slides[bIdx];
        const merged = {
          ...a,
          title: a.title,
          messages: [...(a.messages || []), ...(b.messages || [])].filter(Boolean).slice(0, 3),
          bumper: a.bumper || b.bumper,
        };
        while (merged.messages.length < 3) merged.messages.push('');
        const slides = [...d.slides];
        slides[aIdx] = merged;
        slides.splice(bIdx, 1);
        return { ...d, slides };
      });
      setThreads(ts => ts.map(t => ({
        ...t,
        slideIds: Array.from(new Set(t.slideIds.map(id => id === bId ? aId : id))),
      })));
    } else if (s.kind === 'order' && s.slideIds.length >= 1) {
      const id = s.slideIds[0];
      setDeck(d => {
        const idx = d.slides.findIndex(x => x.id === id);
        if (idx <= 0) return d;
        const slides = [...d.slides];
        const [moved] = slides.splice(idx, 1);
        slides.unshift(moved);
        return { ...d, slides };
      });
    } else if (s.kind === 'thin' && s.slideIds.length >= 1) {
      // 'thin' = drop a slide that doesn't tie to the spine, or shrink to 1 msg
      const id = s.slideIds[0];
      setDeck(d => {
        const idx = d.slides.findIndex(x => x.id === id);
        if (idx < 0) return d;
        // if the slide has multiple messages, thin it to the strongest one;
        // otherwise remove it.
        const target = d.slides[idx];
        const nonEmpty = (target.messages || []).filter(Boolean);
        if (nonEmpty.length >= 2) {
          const slides = [...d.slides];
          slides[idx] = { ...target, messages: [nonEmpty[0], '', ''] };
          return { ...d, slides };
        }
        const slides = d.slides.filter(x => x.id !== id);
        return { ...d, slides };
      });
      setThreads(ts => ts
        .map(t => ({ ...t, slideIds: t.slideIds.filter(x => x !== id) }))
        .filter(t => t.slideIds.length >= 2)
      );
    } else if (s.kind === 'develop' && s.slideIds.length >= 1) {
      // 'develop' is a hint, not a destructive edit — open the detail panel
      // on the targeted slide so the user can write the missing content.
      setSelectedSlideId(s.slideIds[0]);
      setDetailOpen(true);
    }
    // Mark as accepted (so the threadmap "accepted" mode can pick it up)
    // and remove from the visible list.
    setSuggestions(prev => prev.filter(x => x.id !== s.id));
    setDismissedSugg(prev => {
      const next = new Set(prev);
      next.add(s.id);
      return next;
    });
  }, []);

  const handleDismissSuggestion = useCallback((id) => {
    setSuggestions(prev => prev.filter(x => x.id !== id));
    setDismissedSugg(prev => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }, []);

  return (
    <>
      <Nav onBack={() => { window.location.href = '/'; }} />
      <PageHead deck={deck} onTitleChange={handleTitleChange} />
      <EngineBadge engine={engine} backendInfo={backendInfo} />
      <SpineBar spine={spine} />
      <Suggestions
        items={suggestions}
        onAct={handleAcceptSuggestion}
        onDismiss={handleDismissSuggestion}
        onHover={setHoverWarnIds}
      />
      <TensionsStrip tensions={tensions} />
      <div className="canvas">
        <div className="canvas__inner">
          <ThreadLegend
            threads={threads}
            activeId={activeThreadId}
            onToggle={handleToggleThread}
            onHover={setHoverThreadId}
          />
          <div className="canvas__scroll">
            <Tracks
              threads={threads}
              slides={deck.slides}
              activeId={activeThreadId}
              hoverId={hoverThreadId}
            />
            <WireLegend />
            <SlideRow
              slides={deck.slides}
              threads={threads}
              selectedId={selectedSlideId}
              highlightSet={focusedSlideSet}
              warningSet={warningSlideSet}
              onSelectSlide={handleSelectSlide}
              onAddSlide={handleAddSlide}
            />
          </div>
        </div>
      </div>
      <DetailPanel
        slide={selectedSlide}
        idx={selectedIdx}
        threads={threads}
        isOpen={detailOpen}
        onClose={handleCloseDetail}
        onEdit={handleEditSlide}
        onDelete={handleDeleteSlide}
        onDuplicate={handleDuplicateSlide}
      />
      <footer className="page-footer">
        <div>← step 02  ·  pick the goal</div>
        <div className="page-footer__step-nav">
          continue when ready  ·  next  →  workbench
        </div>
      </footer>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<Storyboard />);
