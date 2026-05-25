/* ============================================================
   pptgpt v2.jsx — Apple-style scrollytelling
   Sticky demo + 5 mode panels that drive a synced visual
   ============================================================ */

const { useState, useEffect, useRef, useCallback } = React;

/* ────────────────────────────────────────────────────────────
   Modes — the actual capabilities of pptgpt
   ──────────────────────────────────────────────────────────── */

const MODES = [
  {
    key: 'draft',
    num: '01',
    title: 'Draft a slide.',
    titleEm: 'Draft',
    h: 'One sentence.\nOne polished slide.',
    p: 'Type a thought — a result, a takeaway, a hot mess of bullets. pptgpt drafts one slide that lands the point for whoever\u2019s in the room.',
    meta: [
      { label: 'in', val: 'a thought' },
      { label: 'out', val: '1 slide' },
    ],
  },
  {
    key: 'refine',
    num: '02',
    title: 'Refine a slide.',
    titleEm: 'Refine',
    h: 'Keep the bones.\nFix the buried point.',
    p: 'Drop in a slide that\u2019s nearly there. pptgpt rewrites only what\u2019s buried — title, hierarchy, the takeaway that should live in the lower right.',
    meta: [
      { label: 'in', val: 'a rough slide' },
      { label: 'out', val: 'the polished version' },
    ],
  },
  {
    key: 'condense',
    num: '03',
    title: 'Condense a deck.',
    titleEm: 'Condense',
    h: '40 slides.\nThree that argue.',
    p: 'Paste a whole deck or drop a .pptx. pptgpt picks the spine — three to five slides that carry the argument, with everything else cut.',
    meta: [
      { label: 'in', val: '.pptx / .pdf / paste' },
      { label: 'out', val: '3 — 5 slides' },
    ],
  },
  {
    key: 'visualize',
    num: '04',
    title: 'Visualize a formula.',
    titleEm: 'Visualize',
    h: 'A formula.\nA plot you can tune.',
    p: 'Drop in an equation — pptgpt builds the 3blue1brown-grade plot with the right axes, annotations, and parameters you can drag live.',
    meta: [
      { label: 'in', val: 'a formula' },
      { label: 'out', val: 'plot + sliders' },
    ],
  },
  {
    key: 'synthesize',
    num: '05',
    title: 'Synthesize from data.',
    titleEm: 'Synthesize',
    h: 'A table.\nA chart slide that holds up.',
    p: 'Paste a CSV, a table, comma-separated numbers — pptgpt picks the right chart type, picks the colors, and writes the takeaway under it.',
    meta: [
      { label: 'in', val: 'a table' },
      { label: 'out', val: 'chart + caption' },
    ],
  },
];

/* ────────────────────────────────────────────────────────────
   The 5 mode visuals — only one .is-active at a time
   ──────────────────────────────────────────────────────────── */

function ModeBadge({ num, label }) {
  return (
    <div className="mode-vis__badge">
      <span className="mode-vis__badge-num">{num}</span>
      {label}
    </div>
  );
}

function ArrowDown({ size = 22, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={{ color }}>
      <path d="M12 4 L12 19 M6 13 L12 19 L18 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MVDraft({ active }) {
  return (
    <div className={`mode-vis mv-draft ${active ? 'is-active' : ''}`}>
      <ModeBadge num="01" label="Draft" />
      <div className="mv-draft__input">
        <div className="mv-draft__input-label">your prompt</div>
        <div className="mv-draft__input-text">
          We beat Q3 revenue plan by 14% — net retention 118%, churn down to 1.8%.<span className="cursor" />
        </div>
      </div>
      <div className="mv-draft__arrow"><ArrowDown /></div>
      <div className="mv-draft__slide">
        <div className="mv-draft__slide-eyebrow">Q3 results  ·  exec review</div>
        <h3 className="mv-draft__slide-title">Q3 revenue beat plan by 14%</h3>
        <div className="mv-draft__big">+14%</div>
        <div className="mv-draft__big-sub">vs plan  ·  $42M actuals</div>
        <div className="mv-draft__bullets">
          <div className="mv-draft__bullet">Net retention 118%</div>
          <div className="mv-draft__bullet">Churn down to 1.8%</div>
          <div className="mv-draft__bullet">Enterprise GTM driving the beat</div>
        </div>
      </div>
    </div>
  );
}

function MVRefine({ active }) {
  return (
    <div className={`mode-vis mv-refine ${active ? 'is-active' : ''}`}>
      <ModeBadge num="02" label="Refine" />
      <div className="mv-refine__col mv-refine__col--before mv-refine__before">
        <div className="mv-refine__col-label">before</div>
        <div className="mv-refine__slide">
          <h4 className="mv-refine__h">Quarterly revenue growth</h4>
          <div className="mv-refine__body">
            Three lines, no labels, takeaway buried at the bottom of the deck.
          </div>
          <div className="mv-refine__before-chart" />
        </div>
      </div>
      <div className="mv-refine__col mv-refine__col--after mv-refine__after">
        <div className="mv-refine__col-label">after</div>
        <div className="mv-refine__slide">
          <div className="mv-refine__eyebrow">Q3 results</div>
          <h4 className="mv-refine__h">Revenue beat plan by 14%</h4>
          <div className="mv-refine__after-big">+14%</div>
          <div className="mv-refine__after-foot">"And the trend keeps compounding."</div>
        </div>
      </div>
    </div>
  );
}

function MVCondense({ active }) {
  return (
    <div className={`mode-vis mv-condense ${active ? 'is-active' : ''}`}>
      <ModeBadge num="03" label="Condense" />
      <div className="mv-condense__head">
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--mute)' }}>
          a 40-slide deck
        </div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--accent)' }}>
          → spine of 3
        </div>
      </div>
      <div className="mv-condense__many">
        {Array.from({ length: 16 }).map((_, i) => (
          <div key={i} className="mv-condense__many-slide" />
        ))}
      </div>
      <div className="mv-condense__arrow"><ArrowDown /></div>
      <div className="mv-condense__few">
        <div className="mv-condense__few-slide">
          <div className="mv-condense__few-num">01</div>
          <div className="mv-condense__few-title">Q3 beat plan by 14%</div>
          <div className="mv-condense__few-line med" />
          <div className="mv-condense__few-line short" />
          <div className="mv-condense__few-foot">summary</div>
        </div>
        <div className="mv-condense__few-slide">
          <div className="mv-condense__few-num">02</div>
          <div className="mv-condense__few-title">What drove it</div>
          <div className="mv-condense__few-line med" />
          <div className="mv-condense__few-line med" />
          <div className="mv-condense__few-line short" />
          <div className="mv-condense__few-foot">three reasons</div>
        </div>
        <div className="mv-condense__few-slide">
          <div className="mv-condense__few-num">03</div>
          <div className="mv-condense__few-title">What we do next</div>
          <div className="mv-condense__few-line med" />
          <div className="mv-condense__few-line short" />
          <div className="mv-condense__few-foot">decision</div>
        </div>
      </div>
    </div>
  );
}

function MVVisualize({ active }) {
  // Damped oscillator plot — animated when active
  const W = 480, H = 180;
  const pad = 20;
  const samples = 120;
  const omega = 4.5, gamma = 0.8;
  const path = [];
  for (let i = 0; i <= samples; i++) {
    const t = i / samples;
    const x = pad + t * (W - 2 * pad);
    const y = H / 2 - Math.cos(omega * t * Math.PI * 2) * Math.exp(-gamma * t * 4) * (H / 2 - pad);
    path.push((i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1));
  }
  const envUpper = [];
  const envLower = [];
  for (let i = 0; i <= samples; i++) {
    const t = i / samples;
    const x = pad + t * (W - 2 * pad);
    const env = Math.exp(-gamma * t * 4) * (H / 2 - pad);
    envUpper.push((i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + (H / 2 - env).toFixed(1));
    envLower.push((i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + (H / 2 + env).toFixed(1));
  }

  return (
    <div className={`mode-vis mv-vis ${active ? 'is-active' : ''}`}>
      <ModeBadge num="04" label="Visualize" />
      <div className="mv-vis__eq">
        x(t) = A · e<sup style={{ fontSize: 12 }}>−<em>γ</em>t</sup> · cos(<em>ω</em>t + φ)
      </div>
      <div className="mv-vis__plot">
        <div className="mv-vis__plot-title">Damped harmonic oscillator</div>
        <svg className="mv-vis__plot-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
          {/* axes */}
          <line x1={pad} y1={H / 2} x2={W - pad} y2={H / 2} stroke="var(--border)" strokeWidth="1" />
          <line x1={pad} y1={pad} x2={pad} y2={H - pad} stroke="var(--border)" strokeWidth="1" />
          {/* envelope */}
          <path d={envUpper.join(' ')} stroke="var(--spark)" strokeWidth="1" strokeDasharray="3 3" fill="none" opacity="0.7" />
          <path d={envLower.join(' ')} stroke="var(--spark)" strokeWidth="1" strokeDasharray="3 3" fill="none" opacity="0.7" />
          {/* wave */}
          <path d={path.join(' ')} stroke="var(--accent)" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          {/* labels */}
          <text x={W - pad - 4} y={H / 2 - 8} fontFamily="IBM Plex Mono" fontSize="10" fill="var(--mute)" textAnchor="end">t</text>
          <text x={pad + 6} y={pad + 4} fontFamily="IBM Plex Mono" fontSize="10" fill="var(--mute)">x(t)</text>
        </svg>
      </div>
      <div className="mv-vis__sliders">
        <div className="mv-vis__slider">
          <div className="mv-vis__slider-row"><span>γ damping</span><span>0.80</span></div>
          <div className="mv-vis__slider-track">
            <div className="mv-vis__slider-fill" style={{ width: '32%' }} />
            <div className="mv-vis__slider-thumb" style={{ left: '32%' }} />
          </div>
        </div>
        <div className="mv-vis__slider">
          <div className="mv-vis__slider-row"><span>ω frequency</span><span>4.50</span></div>
          <div className="mv-vis__slider-track">
            <div className="mv-vis__slider-fill" style={{ width: '60%' }} />
            <div className="mv-vis__slider-thumb" style={{ left: '60%' }} />
          </div>
        </div>
        <div className="mv-vis__slider">
          <div className="mv-vis__slider-row"><span>A amplitude</span><span>1.00</span></div>
          <div className="mv-vis__slider-track">
            <div className="mv-vis__slider-fill" style={{ width: '78%' }} />
            <div className="mv-vis__slider-thumb" style={{ left: '78%' }} />
          </div>
        </div>
      </div>
    </div>
  );
}

function MVSynthesize({ active }) {
  const rows = [
    { q: 'Q1', v: 32, hi: false },
    { q: 'Q2', v: 38, hi: false },
    { q: 'Q3', v: 42, hi: true },
    { q: 'Q4', v: 45, hi: false },
  ];
  const max = 50;
  return (
    <div className={`mode-vis mv-synth ${active ? 'is-active' : ''}`}>
      <ModeBadge num="05" label="Synthesize" />
      <div className="mv-synth__col">
        <div className="mv-synth__label">paste a table</div>
        <div className="mv-synth__table">
          <div className="mv-synth__row mv-synth__row--head"><span>quarter</span><span>$M</span></div>
          {rows.map(r => (
            <div className="mv-synth__row" key={r.q}><span>{r.q}</span><span>{r.v}</span></div>
          ))}
        </div>
      </div>
      <div className="mv-synth__col">
        <div className="mv-synth__label">get a chart slide</div>
        <div className="mv-synth__chart">
          <div className="mv-synth__chart-title">Quarterly revenue — $M</div>
          <div className="mv-synth__chart-area">
            {rows.map(r => (
              <div
                key={r.q}
                className={`mv-synth__bar ${r.hi ? 'is-hi' : ''}`}
                style={{ height: active ? `${(r.v / max) * 100}%` : '0%' }}
              >
                <span className="mv-synth__bar-val">{r.v}</span>
                <span className="mv-synth__bar-label">{r.q}</span>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: 'var(--mute)', marginTop: 14, fontStyle: 'italic' }}>
            Q3 ahead of plan. Q4 trending in line.
          </div>
        </div>
      </div>
    </div>
  );
}

const MODE_VISUALS = {
  draft:      MVDraft,
  refine:     MVRefine,
  condense:   MVCondense,
  visualize:  MVVisualize,
  synthesize: MVSynthesize,
};

/* ────────────────────────────────────────────────────────────
   ScrollyDemo — sticky stage + scrolling text panels
   ──────────────────────────────────────────────────────────── */

function ScrollyDemo() {
  const [activeIdx, setActiveIdx] = useState(0);
  const panelRefs = useRef([]);

  useEffect(() => {
    const els = panelRefs.current.filter(Boolean);
    if (els.length === 0) return;
    const obs = new IntersectionObserver(
      (entries) => {
        // pick the most visible panel
        let bestIdx = activeIdx;
        let bestRatio = 0;
        entries.forEach(e => {
          const i = els.indexOf(e.target);
          if (i < 0) return;
          if (e.intersectionRatio > bestRatio) {
            bestRatio = e.intersectionRatio;
            bestIdx = i;
          }
        });
        // Also check ALL current panels for the most visible
        els.forEach((el, i) => {
          const rect = el.getBoundingClientRect();
          const winH = window.innerHeight;
          const center = rect.top + rect.height / 2;
          const distance = Math.abs(center - winH / 2);
          if (distance < winH / 3 && rect.top < winH * 0.55 && rect.bottom > winH * 0.45) {
            bestIdx = i;
          }
        });
        if (bestIdx !== activeIdx) setActiveIdx(bestIdx);
      },
      { threshold: [0, 0.25, 0.5, 0.75, 1.0], rootMargin: '-30% 0px -30% 0px' }
    );
    els.forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, [activeIdx]);

  return (
    <section className="scrolly">
      <div className="scrolly__intro">
        <h2 className="scrolly__intro-h">
          One tool, <em>five modes</em>.<br/>
          Built for the material you actually have.
        </h2>
        <div className="scrolly__intro-sub">
          scroll to walk through  ↓
        </div>
      </div>
      <div className="scrolly__container">
        <div className="scrolly__stage">
          <div className="stage-frame">
            {MODES.map((m, i) => {
              const V = MODE_VISUALS[m.key];
              return <V key={m.key} active={i === activeIdx} />;
            })}
          </div>
        </div>
        <div className="scrolly__panels">
          {MODES.map((m, i) => (
            <article
              key={m.key}
              ref={el => panelRefs.current[i] = el}
              className={`panel ${i === activeIdx ? 'is-active' : 'is-dim'}`}
            >
              <div className="panel__step">
                <span className="panel__step-num">{m.num}</span>
                <span>{m.titleEm}</span>
              </div>
              <h3 className="panel__h">
                {m.h.split('\n').map((line, ix) => (
                  <span key={ix}>{line}{ix < m.h.split('\n').length - 1 && <br/>}</span>
                ))}
              </h3>
              <p className="panel__p">{m.p}</p>
              <div className="panel__meta">
                {m.meta.map((mt, ix) => (
                  <span key={ix} className="panel__meta-pip">
                    <span className="panel__meta-pip-dot" style={{ background: ix === 0 ? 'var(--mute)' : 'var(--accent)' }} />
                    {mt.label}  ·  <strong>{mt.val}</strong>
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────
   Audience rail — shows pptgpt's room-aware tuning
   ──────────────────────────────────────────────────────────── */

const AUDIENCES = [
  { key: 'exec',       tag: 'Exec review',       h: 'Numbers up front.', sub: 'Spare, decision-first. The takeaway lives in the lower right where the room is already looking.', ex: '"Q3 beat plan by 14%. Doubling down on enterprise."' },
  { key: 'customer',   tag: 'Customer update',   h: 'Narrative first.',  sub: 'More visual, less density. Frames a story arc with one ask landing at the end.', ex: '"Here\u2019s what shipped, what\u2019s next, and what we need from you."' },
  { key: 'conf',       tag: 'Conference talk',   h: 'Big visuals.',      sub: 'One idea per slide, takeaway-first. Speaker notes that match how you actually talk on stage.', ex: '"The plot you\u2019re about to see explains everything."' },
  { key: 'standup',    tag: 'Status / standup',  h: 'Dense, actionable.',sub: 'Action items, owners, and dates — formatted for a 10-minute room.', ex: '"3 open. 1 blocked. Need design review by Friday."' },
  { key: '1-1',        tag: '1:1 tag-up',        h: 'Conversational.',   sub: 'Low polish on purpose. Reads like talking points, not a presentation.', ex: '"Here\u2019s what\u2019s on my mind. What am I missing?"' },
  { key: 'technical',  tag: 'Technical deep-dive', h: 'Formulas + plots.', sub: 'Math rendered cleanly, plots with tunable parameters, citations under each claim.', ex: '"The damping coefficient explains the residual."' },
];

function Audiences() {
  return (
    <section className="audiences">
      <div className="audiences__head js-reveal">
        <h2 className="audiences__h">
          The same idea reads differently<br/>
          in <em>different rooms.</em>
        </h2>
        <p className="audiences__sub">
          pptgpt asks who's in the room before it drafts. Density, polish, and the position of the takeaway all shift to match.
        </p>
      </div>
      <div className="audiences__rail">
        {AUDIENCES.map(a => (
          <article key={a.key} className="aud-card">
            <div className="aud-card__tag">{a.tag}</div>
            <h3 className="aud-card__h">{a.h}</h3>
            <p className="aud-card__sub">{a.sub}</p>
            <div className="aud-card__hr" />
            <div className="aud-card__example">
              <div className="aud-card__example-label">sample takeaway</div>
              <div className="aud-card__example-text">{a.ex}</div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────
   Composer — the actual try-it surface
   ──────────────────────────────────────────────────────────── */

const COMPOSER_MODES = [
  { key: 'draft',      label: 'Draft',      color: 'var(--accent)' },
  { key: 'refine',     label: 'Refine',     color: 'var(--spark)' },
  { key: 'condense',   label: 'Condense',   color: 'var(--gold)' },
  { key: 'visualize',  label: 'Visualize',  color: '#5468C9' },
  { key: 'synthesize', label: 'Synthesize', color: '#7B68A8' },
];

function Composer() {
  const [prompt, setPrompt] = useState('');
  const [mode, setMode] = useState('draft');

  const placeholders = {
    draft:      'A sentence, a paragraph, a hot mess of bullets…',
    refine:     'Paste the slide that\u2019s nearly there…',
    condense:   'Drop a .pptx, or paste the deck text here…',
    visualize:  'x(t) = A · e^(−γt) · cos(ωt + φ)',
    synthesize: 'Q1, 32\nQ2, 38\nQ3, 42\nQ4, 45',
  };

  return (
    <section className="composer-section" id="try">
      <div className="composer-section__eyebrow">↓ try it</div>
      <h2 className="composer-section__h">
        Drop in <em>raw material.</em><br/>
        Get out a slide.
      </h2>
      <div className="composer">
        <textarea
          className="composer__textarea"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={placeholders[mode]}
          rows={3}
        />
        <div className="composer__modes">
          {COMPOSER_MODES.map(m => (
            <button
              key={m.key}
              className={`mode-chip ${mode === m.key ? 'is-active' : ''}`}
              onClick={() => setMode(m.key)}
            >
              <span className="mode-chip__dot" style={{ background: m.color }} />
              {m.label}
            </button>
          ))}
        </div>
        <div className="composer__row">
          <span className="composer__meta">5 takes  ·  ~10 seconds</span>
          <button className="composer__send" disabled={!prompt.trim()}>
            Make slides
            <svg viewBox="0 0 16 16" fill="none">
              <path d="M3 8 L13 8 M9 4 L13 8 L9 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
      <div className="composer-section__examples">
        {[
          'We beat Q3 revenue plan by 14%',
          'Onboarding drop-off up 8 points since the redesign',
          'Damped harmonic oscillator: γ controls decay',
          'Customer-renewal forecast for FY26',
        ].map(p => (
          <button key={p} className="example-chip" onClick={() => setPrompt(p)}>
            {p}
          </button>
        ))}
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────
   Nav — sticky with subtle border on scroll
   ──────────────────────────────────────────────────────────── */

function Nav() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return (
    <nav className={`nav ${scrolled ? 'is-scrolled' : ''}`}>
      <div className="brand">
        <span className="brand__mark" />
        pptgpt
      </div>
      <div className="nav__links">
        <button className="nav__link">Modes</button>
        <button className="nav__link">Audiences</button>
        <button className="nav__link">Examples</button>
        <button className="nav__link">Pricing</button>
      </div>
      <div className="nav__right">
        <button className="btn btn--ghost">Log in</button>
        <button
          className="btn btn--primary"
          onClick={() => document.getElementById('try').scrollIntoView({ behavior: 'smooth', block: 'start' })}
        >Try it free</button>
      </div>
    </nav>
  );
}

/* ────────────────────────────────────────────────────────────
   Hero
   ──────────────────────────────────────────────────────────── */

function Hero() {
  return (
    <section className="hero">
      <div className="hero__eyebrow">
        <span className="hero__eyebrow-pill">v2</span>
        Five modes  ·  one room-aware tool
      </div>
      <h1 className="hero__title">
        Slides that <span className="hero__title-em">argue.</span>
      </h1>
      <p className="hero__sub">
        Drop in a thought, a slide, a deck, a formula, or a table. pptgpt drafts, refines, condenses, visualizes, or synthesizes — whichever your material needs.
      </p>
      <div className="hero__cta">
        <button
          className="btn btn--accent btn--lg"
          onClick={() => document.getElementById('try').scrollIntoView({ behavior: 'smooth', block: 'start' })}
        >
          Try it free
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 8 L13 8 M9 4 L13 8 L9 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <button className="btn btn--ghost btn--lg">
          See examples
        </button>
      </div>
      <div className="peek">
        <div className="peek__col">
          <span className="peek__label">drop in</span>
          <div className="peek__chips">
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--mute)' }} />a thought</span>
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--mute)' }} />a rough slide</span>
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--mute)' }} />.pptx / .pdf</span>
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--mute)' }} />a formula</span>
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--mute)' }} />a table</span>
          </div>
        </div>
        <div className="peek__arrow">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 12 L20 12 M14 6 L20 12 L14 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div className="peek__col peek__col--right">
          <span className="peek__label">get out</span>
          <div className="peek__chips">
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--accent)' }} />a slide</span>
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--accent)' }} />a deck spine</span>
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--accent)' }} />a tuned plot</span>
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--accent)' }} />a chart with caption</span>
          </div>
        </div>
      </div>
      <div className="hero__scroll" style={{ marginTop: 80 }}>
        <span>scroll for how it works</span>
        <span className="hero__scroll-arrow">
          <svg viewBox="0 0 18 18" fill="none">
            <path d="M9 3 L9 14 M4 9 L9 14 L14 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────
   Footer
   ──────────────────────────────────────────────────────────── */

function Footer() {
  return (
    <footer className="footer">
      <div className="footer__brand">
        <span className="brand__mark" />
        pptgpt © 2026
      </div>
      <div>built for the room</div>
      <div className="footer__links">
        <a href="#" className="footer__link">Privacy</a>
        <a href="#" className="footer__link">Terms</a>
        <a href="#" className="footer__link">Contact</a>
      </div>
    </footer>
  );
}

/* ────────────────────────────────────────────────────────────
   Reveal fallback for browsers without animation-timeline
   ──────────────────────────────────────────────────────────── */

function useJSReveal() {
  useEffect(() => {
    if (CSS.supports && CSS.supports('animation-timeline: view()')) return;
    const els = document.querySelectorAll('.js-reveal');
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach(e => {
          if (e.isIntersecting) {
            e.target.classList.add('is-in');
            obs.unobserve(e.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: '0px 0px -10% 0px' }
    );
    els.forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, []);
}

/* ────────────────────────────────────────────────────────────
   App
   ──────────────────────────────────────────────────────────── */

function App() {
  useJSReveal();
  return (
    <>
      <Nav />
      <Hero />
      <ScrollyDemo />
      <Audiences />
      <Composer />
      <Footer />
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
