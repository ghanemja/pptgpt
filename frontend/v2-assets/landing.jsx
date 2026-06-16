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
    title: 'Visualize the math.',
    titleEm: 'Visualize',
    h: 'Data, plots, results.\nA chart you can tune.',
    p: 'Drop in raw data, plots, results, or a formula — pptgpt builds the 3blue1brown-grade visual with the right axes, annotations, and parameters you can drag live.',
    meta: [
      { label: 'in', val: 'data, plots, results' },
      { label: 'out', val: 'tunable visual' },
    ],
  },
  {
    key: 'synthesize',
    num: '05',
    title: 'Synthesize from data.',
    titleEm: 'Synthesize',
    h: 'Data, plots, results.\nA chart slide that holds up.',
    p: 'Drop in data, plots, or results — one file or fifty. pptgpt picks the right chart type, picks the colors, and writes the takeaway under it.',
    meta: [
      { label: 'in', val: 'data, plots, results' },
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
        <div className="mv-synth__label">drop data, plots, results</div>
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

/* ════════════════════════════════════════════════════════════
   MODES GLANCE — quick 5-card overview, scannable in 5 seconds
   ════════════════════════════════════════════════════════════ */

const MODE_GLANCE = [
  {
    num: '01',
    verb: 'Draft',
    sub: 'A thought becomes one polished slide.',
    inLabel: 'a thought',
    outLabel: '1 slide',
    visual: (
      <svg viewBox="0 0 200 110" preserveAspectRatio="xMidYMid meet">
        <rect x="8" y="14" width="184" height="22" rx="4" fill="#FFFCF4" stroke="#E1DBC7" />
        <rect x="16" y="22" width="120" height="3" rx="1" fill="#807C6E" />
        <rect x="16" y="28" width="86" height="2" rx="1" fill="#807C6E" opacity="0.55" />
        <path d="M100 44 L100 54 M96 50 L100 54 L104 50" stroke="#0E5B36" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <rect x="8" y="62" width="184" height="40" rx="4" fill="#FFFFFF" stroke="#E1DBC7" />
        <rect x="16" y="70" width="56" height="3" rx="1" fill="#11120E" />
        <text x="16" y="92" fontFamily="Manrope" fontSize="22" fontWeight="800" fill="#0E5B36">+14%</text>
        <rect x="92" y="78" width="92" height="2" rx="1" fill="#807C6E" opacity="0.5" />
        <rect x="92" y="84" width="72" height="2" rx="1" fill="#807C6E" opacity="0.5" />
        <rect x="92" y="90" width="80" height="2" rx="1" fill="#807C6E" opacity="0.5" />
      </svg>
    ),
  },
  {
    num: '02',
    verb: 'Refine',
    sub: 'A rough slide gets the buried point dug up.',
    inLabel: 'a rough slide',
    outLabel: 'polished',
    visual: (
      <svg viewBox="0 0 200 110" preserveAspectRatio="xMidYMid meet">
        <rect x="8" y="14" width="86" height="84" rx="4" fill="#FFFCF4" stroke="#E1DBC7" />
        <rect x="14" y="22" width="58" height="3" rx="1" fill="#807C6E" />
        <rect x="14" y="30" width="68" height="2" rx="1" fill="#807C6E" opacity="0.4" />
        <rect x="14" y="36" width="56" height="2" rx="1" fill="#807C6E" opacity="0.4" />
        <rect x="14" y="60" width="68" height="30" rx="2" fill="#F1ECDC" />
        <path d="M100 56 L114 56 M108 51 L114 56 L108 61" stroke="#0E5B36" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <rect x="118" y="14" width="74" height="84" rx="4" fill="#FFFFFF" stroke="#E1DBC7" />
        <rect x="124" y="22" width="40" height="3" rx="1" fill="#11120E" />
        <text x="124" y="60" fontFamily="Manrope" fontSize="22" fontWeight="800" fill="#0E5B36">+14%</text>
        <rect x="124" y="76" width="56" height="2" rx="1" fill="#807C6E" opacity="0.5" />
        <rect x="124" y="82" width="42" height="2" rx="1" fill="#807C6E" opacity="0.5" />
      </svg>
    ),
  },
  {
    num: '03',
    verb: 'Condense',
    sub: 'A long deck gets cut to its three load-bearing slides.',
    inLabel: '40 slides',
    outLabel: '3 slides',
    visual: (
      <svg viewBox="0 0 200 110" preserveAspectRatio="xMidYMid meet">
        {Array.from({ length: 12 }).map((_, i) => {
          const x = 8 + (i % 6) * 16;
          const y = 14 + Math.floor(i / 6) * 18;
          return <rect key={i} x={x} y={y} width="12" height="14" rx="1.5" fill="#FFFCF4" stroke="#E1DBC7" />;
        })}
        <path d="M108 30 L122 30 M116 25 L122 30 L116 35" stroke="#0E5B36" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <rect x="128" y="14" width="20" height="32" rx="3" fill="#FFFFFF" stroke="#0E5B36" strokeWidth="1.2" />
        <rect x="152" y="14" width="20" height="32" rx="3" fill="#FFFFFF" stroke="#0E5B36" strokeWidth="1.2" />
        <rect x="176" y="14" width="20" height="32" rx="3" fill="#FFFFFF" stroke="#0E5B36" strokeWidth="1.2" />
        <rect x="130" y="20" width="14" height="2" rx="1" fill="#11120E" />
        <rect x="154" y="20" width="14" height="2" rx="1" fill="#11120E" />
        <rect x="178" y="20" width="14" height="2" rx="1" fill="#11120E" />
        <rect x="130" y="26" width="10" height="1.5" rx="0.75" fill="#807C6E" opacity="0.5" />
        <rect x="154" y="26" width="10" height="1.5" rx="0.75" fill="#807C6E" opacity="0.5" />
        <rect x="178" y="26" width="10" height="1.5" rx="0.75" fill="#807C6E" opacity="0.5" />
        <text x="128" y="74" fontFamily="IBM Plex Mono" fontSize="8" fill="#807C6E" letterSpacing="0.1em">SPINE OF 3</text>
        <line x1="8" y1="86" x2="48" y2="86" stroke="#807C6E" strokeWidth="0.5" strokeDasharray="2 2" opacity="0.5" />
        <text x="8" y="100" fontFamily="IBM Plex Mono" fontSize="7" fill="#807C6E">40 IN</text>
        <text x="156" y="100" fontFamily="IBM Plex Mono" fontSize="7" fill="#0E5B36" fontWeight="600">3 OUT</text>
      </svg>
    ),
  },
  {
    num: '04',
    verb: 'Visualize',
    sub: 'Data or a formula becomes a tunable plot.',
    inLabel: 'data, plots, results',
    outLabel: 'tunable visual',
    visual: (
      <svg viewBox="0 0 200 110" preserveAspectRatio="xMidYMid meet">
        <rect x="8" y="10" width="184" height="20" rx="3" fill="#FFFCF4" stroke="#E1DBC7" />
        <text x="16" y="24" fontFamily="IBM Plex Mono" fontSize="9" fill="#11120E">x(t) = A·e</text>
        <text x="64" y="20" fontFamily="IBM Plex Mono" fontSize="7" fill="#0E5B36">−γt</text>
        <text x="76" y="24" fontFamily="IBM Plex Mono" fontSize="9" fill="#11120E">·cos(ωt+φ)</text>
        <rect x="8" y="38" width="184" height="62" rx="3" fill="#FFFFFF" stroke="#E1DBC7" />
        <line x1="14" y1="68" x2="186" y2="68" stroke="#E1DBC7" />
        {(() => {
          const pts = [];
          for (let i = 0; i <= 50; i++) {
            const t = i / 50;
            const x = 14 + t * 172;
            const env = Math.exp(-1.4 * t * 3) * 22;
            const y = 68 - Math.cos(t * Math.PI * 3.5) * env;
            pts.push((i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1));
          }
          return <path d={pts.join(' ')} stroke="#0E5B36" strokeWidth="1.6" fill="none" strokeLinecap="round" />;
        })()}
      </svg>
    ),
  },
  {
    num: '05',
    verb: 'Synthesize',
    sub: 'Numbers — one file or many — become a labeled chart slide.',
    inLabel: 'data, plots, results',
    outLabel: 'chart + caption',
    visual: (
      <svg viewBox="0 0 200 110" preserveAspectRatio="xMidYMid meet">
        <rect x="8" y="14" width="78" height="84" rx="3" fill="#FFFCF4" stroke="#E1DBC7" />
        <line x1="8" y1="30" x2="86" y2="30" stroke="#E1DBC7" />
        <line x1="46" y1="14" x2="46" y2="98" stroke="#E1DBC7" />
        {['Q1','Q2','Q3','Q4'].map((q, i) => (
          <g key={q}>
            <text x="14" y={44 + i * 14} fontFamily="IBM Plex Mono" fontSize="8" fill="#11120E">{q}</text>
            <text x="52" y={44 + i * 14} fontFamily="IBM Plex Mono" fontSize="8" fill="#11120E">{[32,38,42,45][i]}</text>
          </g>
        ))}
        <path d="M94 56 L108 56 M102 51 L108 56 L102 61" stroke="#0E5B36" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <rect x="114" y="14" width="78" height="84" rx="3" fill="#FFFFFF" stroke="#E1DBC7" />
        <line x1="114" y1="84" x2="192" y2="84" stroke="#E1DBC7" />
        {[32,38,42,45].map((v, i) => {
          const h = (v / 50) * 60;
          const x = 120 + i * 18;
          const hi = i === 2;
          return <rect key={i} x={x} y={84 - h} width="12" height={h} rx="1.5" fill={hi ? '#E26A2C' : '#0E5B36'} />;
        })}
      </svg>
    ),
  },
];

function ModesGlance() {
  return (
    <section className="modes-glance">
      <div className="modes-glance__head">
        <h2 className="modes-glance__h">
          What pptgpt <em>actually does.</em>
        </h2>
        <div className="modes-glance__sub">
          <div className="modes-glance__sub-eyebrow">five modes  ·  one tool</div>
          Each mode matches a different kind of raw material. You don't pick — pptgpt reads what you dropped in and reaches for the right one.
        </div>
      </div>
      <div className="modes-glance__grid">
        {MODE_GLANCE.map(m => (
          <article key={m.num} className="mg-card">
            <div className="mg-card__num">{m.num}</div>
            <h3 className="mg-card__verb">{m.verb}</h3>
            <p className="mg-card__verb-sub">{m.sub}</p>
            <div className="mg-card__visual">{m.visual}</div>
            <div className="mg-card__io">
              <strong>{m.inLabel}</strong>
              <span className="mg-card__io-arrow">→</span>
              <strong>{m.outLabel}</strong>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

/* ════════════════════════════════════════════════════════════
   AUDIENCE SWITCHER — pick a room, watch the same slide morph
   ════════════════════════════════════════════════════════════ */

function ASExec() {
  return (
    <div className="as-exec">
      <div className="as-exec__left">
        <div className="as-eyebrow">
          <span className="as-eyebrow-dot" />
          Q3 results  ·  exec review
        </div>
        <div>
          <h3 className="as-exec__title">Q3 revenue beat plan by 14%</h3>
          <div className="as-exec__big">+14%</div>
          <div className="as-exec__big-sub">vs plan  ·  $42M actuals</div>
        </div>
      </div>
      <div className="as-exec__right">
        <div>
          <div className="as-exec__stat">
            <div className="as-exec__stat-label">Net retention</div>
            <div className="as-exec__stat-val">118%</div>
          </div>
          <div className="as-exec__stat">
            <div className="as-exec__stat-label">Churn</div>
            <div className="as-exec__stat-val">1.8%</div>
          </div>
          <div className="as-exec__stat">
            <div className="as-exec__stat-label">Gross margin</div>
            <div className="as-exec__stat-val">76%</div>
          </div>
        </div>
        <div className="as-exec__decision">
          <span className="as-exec__decision-pill">DECIDE</span>
          Double down on enterprise. Pause SMB.
        </div>
      </div>
    </div>
  );
}

function ASCustomer() {
  return (
    <div className="as-customer">
      <div className="as-eyebrow">
        <span className="as-eyebrow-dot" />
        Q3 update for you
      </div>
      <h3 className="as-customer__title">
        Here's what shipped last quarter — and what we're focused on next.
      </h3>
      <div className="as-customer__story">
        {[
          { q: 'Q1', label: 'Foundations laid' },
          { q: 'Q2', label: 'Pilots running' },
          { q: 'Q3', label: 'GA launch', here: true },
          { q: 'Q4', label: 'Scaling rollout' },
        ].map(s => (
          <div key={s.q} className={`as-story-step ${s.here ? 'is-here' : ''}`}>
            <div className="as-story-q">{s.q}</div>
            <div className="as-story-dot" />
            <div className="as-story-label">{s.label}</div>
          </div>
        ))}
      </div>
      <p className="as-customer__foot">
        Q3 brought a <strong>14% lift</strong> over our internal plan. We're using that runway to expand support coverage and pull the Q4 roadmap forward.
      </p>
    </div>
  );
}

function ASConf() {
  return (
    <div className="as-conf">
      <div className="as-eyebrow">
        <span className="as-eyebrow-dot" />
        opening slide
      </div>
      <div className="as-conf__big">
        We beat plan by <span className="as-conf__big-em">14%.</span>
      </div>
      <div>
        <p className="as-conf__caption">
          And here's what we did that we'd do again — every quarter, for the next four.
        </p>
        <div className="as-conf__meta" style={{ marginTop: 18 }}>
          <span>SLIDE 03 OF 28</span>
          <span>·</span>
          <span>SPEAKER NOTES ATTACHED</span>
        </div>
      </div>
    </div>
  );
}

function ASStandup() {
  const rows = [
    { status: 'ok',    metric: 'Revenue',     value: '+14%', owner: 'M. Reyes',   date: 'Oct 15' },
    { status: 'ok',    metric: 'Retention',   value: '118%', owner: 'A. Chen',    date: 'Oct 15' },
    { status: 'warn',  metric: 'Onboarding',  value: '−8pt', owner: 'D. Park',    date: 'Oct 22' },
    { status: 'block', metric: 'SMB churn',   value: '4.2%', owner: 'unassigned', date: 'NEEDS OWNER' },
  ];
  return (
    <div className="as-standup">
      <div className="as-eyebrow">
        <span className="as-eyebrow-dot" />
        Q3 standup  ·  Oct 8  ·  10 min
      </div>
      <h3 className="as-standup__title">Where we stand — and what's open.</h3>
      <div className="as-standup__table">
        <div className="as-standup__row as-standup__row--head">
          <span></span>
          <span>METRIC</span>
          <span>VALUE</span>
          <span>OWNER</span>
          <span>BY</span>
        </div>
        {rows.map(r => (
          <div key={r.metric} className="as-standup__row">
            <span className={`as-standup__status is-${r.status === 'ok' ? '' : r.status}`} />
            <span className="as-standup__metric">{r.metric}</span>
            <span className="as-standup__value">{r.value}</span>
            <span className="as-standup__owner">{r.owner}</span>
            <span className="as-standup__date">{r.date}</span>
          </div>
        ))}
      </div>
      <div className="as-standup__legend">
        <span className="as-standup__legend-item"><span className="as-standup__legend-dot" style={{ background: 'var(--accent)' }} /> ok</span>
        <span className="as-standup__legend-item"><span className="as-standup__legend-dot" style={{ background: 'var(--gold)' }} /> at risk</span>
        <span className="as-standup__legend-item"><span className="as-standup__legend-dot" style={{ background: 'var(--spark)' }} /> blocked</span>
      </div>
    </div>
  );
}

function ASOneone() {
  return (
    <div className="as-oneone">
      <div className="as-oneone__pre">notes for our 1:1  ·  thursday</div>
      <h3 className="as-oneone__title">Here's what's on my mind this week.</h3>
      <div className="as-oneone__notes">
        <div className="as-oneone__notes-item">
          Q3 came in <em>+14% over plan</em> — feels good but the SMB cohort is dragging
        </div>
        <div className="as-oneone__notes-item">
          Want to shift 40% of marketing spend to ENT. Bold call, want your read
        </div>
        <div className="as-oneone__notes-item">
          Onboarding redesign cost us 8 points of activation. Need to roll back?
        </div>
        <div className="as-oneone__notes-item">
          Two design partners in public sector — both expansion-ready
        </div>
      </div>
      <div className="as-oneone__q">
        If you were me, what would you stop doing?
      </div>
    </div>
  );
}

function ASTech() {
  // Damped oscillator plot — small version
  const W = 200, H = 100, pad = 12;
  const samples = 80;
  const path = [];
  for (let i = 0; i <= samples; i++) {
    const t = i / samples;
    const x = pad + t * (W - 2 * pad);
    const y = H / 2 - Math.cos(t * Math.PI * 4) * Math.exp(-1.6 * t * 2) * (H / 2 - pad);
    path.push((i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1));
  }
  return (
    <div className="as-tech">
      <div className="as-tech__left">
        <div className="as-eyebrow">
          <span className="as-eyebrow-dot" />
          Tech deep-dive  ·  Q3 systems review
        </div>
        <h3 className="as-tech__title">Revenue residual ≈ damping × time</h3>
        <div className="as-tech__eq">
          R(t) = R<sub>0</sub> · e<sup>−<em>γ</em>t</sup> · cos(<em>ω</em>t + φ)
        </div>
        <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.5, margin: '6px 0 12px' }}>
          The 14% beat is consistent with a <em style={{ color: 'var(--accent)', fontStyle: 'normal', fontWeight: 600 }}>γ = 0.8</em> damping coefficient on the prior-cycle softening
          [<span style={{ color: 'var(--accent)' }}>1</span>], extrapolated forward over t = 90d.
        </p>
        <div className="as-tech__citations">
          <span className="as-tech__cite"><span className="as-tech__cite-num">[1]</span>Internal finance review, Q2 forecast variance memo, p. 7.</span>
          <span className="as-tech__cite"><span className="as-tech__cite-num">[2]</span>Reyes et al., GTM funnel decay model, FY26 Q3.</span>
        </div>
      </div>
      <div className="as-tech__plot">
        <div className="as-tech__plot-title">Forecast residual  ·  R(t)</div>
        <svg className="as-tech__plot-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
          <line x1={pad} y1={H/2} x2={W-pad} y2={H/2} stroke="var(--border)" />
          <line x1={pad} y1={pad} x2={pad} y2={H-pad} stroke="var(--border)" />
          <path d={path.join(' ')} stroke="var(--accent)" strokeWidth="1.8" fill="none" strokeLinecap="round" />
          <text x={W-pad-2} y={H/2-4} fontFamily="IBM Plex Mono" fontSize="8" fill="var(--mute)" textAnchor="end">t</text>
        </svg>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.1em', color: 'var(--mute)', textTransform: 'uppercase', marginTop: 8 }}>
          γ = 0.80  ·  ω = 4.50
        </div>
      </div>
    </div>
  );
}

const AUD_DATA = [
  {
    key: 'exec',     label: 'Exec review',       num: '01', sub: 'Numbers up front. Decision lower-right.',
    color: '#11120E', bars: { density: 30, polish: 95, visual: 30 },
    changes: ['Big number leads', 'Decision pill anchors the room', 'Sparse — no narrative'],
    Slide: ASExec,
  },
  {
    key: 'customer', label: 'Customer update',   num: '02', sub: 'Narrative first. One ask at the end.',
    color: '#C4633F', bars: { density: 45, polish: 80, visual: 70 },
    changes: ['Story arc framing', 'Friendlier tone, less density', 'Ask lands in the last beat'],
    Slide: ASCustomer,
  },
  {
    key: 'conf',     label: 'Conference talk',   num: '03', sub: 'One idea. Big type. Notes attached.',
    color: '#0E5B36', bars: { density: 15, polish: 95, visual: 95 },
    changes: ['One idea per slide', 'Typography does the heavy lifting', 'Speaker notes match your voice'],
    Slide: ASConf,
  },
  {
    key: 'standup',  label: 'Status / standup',  num: '04', sub: 'Owner + date per row.',
    color: '#C99A2E', bars: { density: 95, polish: 40, visual: 30 },
    changes: ['Status indicators per item', 'Owners and dates inline', 'Built for a 10-min room'],
    Slide: ASStandup,
  },
  {
    key: 'oneone',   label: '1:1 tag-up',        num: '05', sub: 'Low polish. Ends in a question.',
    color: '#807C6E', bars: { density: 50, polish: 25, visual: 30 },
    changes: ['Reads like talking points', 'Em-dashes, not bullets', 'Closes with a question'],
    Slide: ASOneone,
  },
  {
    key: 'tech',     label: 'Technical deep-dive', num: '06', sub: 'Equation + plot + citations.',
    color: '#5468C9', bars: { density: 85, polish: 90, visual: 75 },
    changes: ['Math rendered cleanly', 'Plot with tunable params', 'Citation per claim'],
    Slide: ASTech,
  },
];

function AudienceSwitcher() {
  const [activeKey, setActiveKey] = useState('exec');
  const active = AUD_DATA.find(a => a.key === activeKey) || AUD_DATA[0];

  return (
    <section className="aud-section" id="audiences">
      <div className="aud-section__head">
        <div className="aud-section__eyebrow">↓ pick a room, watch it morph</div>
        <h2 className="aud-section__h">
          Same content.<br/>
          <em>Six different rooms.</em>
        </h2>
        <p className="aud-section__sub">
          The Q3 result below stays identical. What changes is the room you're walking it into — density, polish, and where the takeaway lives.
        </p>
      </div>
      <div className="aud-switcher">
        <div className="aud-tabs">
          {AUD_DATA.map(a => (
            <button
              key={a.key}
              className={`aud-tab ${a.key === activeKey ? 'is-active' : ''}`}
              onClick={() => setActiveKey(a.key)}
            >
              <span className="aud-tab__num">{a.num}</span>
              <span className="aud-tab__dot" style={{ background: a.color }} />
              {a.label}
            </button>
          ))}
        </div>
        <div className="aud-stage">
          <div className="aud-slide-frame">
            {AUD_DATA.map(a => {
              const S = a.Slide;
              return (
                <div key={a.key} className={`aud-slide ${a.key === activeKey ? 'is-active' : ''}`}>
                  <S />
                </div>
              );
            })}
          </div>
          <div className="aud-meta">
            <div className="aud-meta__head">
              <span className="aud-meta__dot" style={{ background: active.color }} />
              <div>
                <h3 className="aud-meta__title">{active.label}</h3>
                <div className="aud-meta__sub">{active.sub}</div>
              </div>
            </div>
            <div className="aud-bars">
              {[
                { k: 'Density',    v: active.bars.density },
                { k: 'Polish',     v: active.bars.polish },
                { k: 'Visual weight', v: active.bars.visual },
              ].map(b => (
                <div key={b.k} className="aud-bar">
                  <div className="aud-bar__row">
                    <span>{b.k}</span>
                    <span>{b.v}%</span>
                  </div>
                  <div className="aud-bar__track">
                    <div className="aud-bar__fill" style={{ width: `${b.v}%`, background: active.color }} />
                  </div>
                </div>
              ))}
            </div>
            <div className="aud-changes">
              <div className="aud-changes__label">what changes</div>
              {active.changes.map(c => (
                <div key={c} className="aud-change">{c}</div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ════════════════════════════════════════════════════════════
   LIVE PLAYGROUND — Claude actually drafts a slide from input
   ════════════════════════════════════════════════════════════ */

const PLAY_SUGGESTIONS = [
  'We hit 118% net retention last quarter — three reasons why',
  'Onboarding drop-off is up 8 points since the redesign',
  'Why we\u2019re sunsetting the SMB self-serve tier',
  'How we shipped the migration in 6 weeks',
];

const PLAY_AUDIENCES = [
  { key: 'exec',     label: 'Exec',       tone: 'numbers-forward, sparse, decision-oriented' },
  { key: 'customer', label: 'Customer',   tone: 'narrative-first, more visual, conversational, ends with an ask' },
  { key: 'conf',     label: 'Conference', tone: 'one-idea, big-typography, takeaway-first' },
  { key: 'standup',  label: 'Standup',    tone: 'dense, action items with owners and dates' },
];

async function generateSlide(promptText, audienceTone) {
  const sysPrompt = `You are pptgpt, a tool that drafts one polished slide from a user's input.

Return ONLY a JSON object — no markdown, no code fences, no commentary. Schema:

{
  "eyebrow": "string — short context label, ALL CAPS, max 5 words",
  "title": "string — slide headline, takeaway-first, 4 to 9 words",
  "metric": "string or null — a hero number/phrase to render large (e.g. '+14%', '118%', '6 weeks'). null if not applicable.",
  "metric_sub": "string or null — short unit/context, max 6 words",
  "bullets": ["string — supporting point, max 9 words", "string — second point", "string — third point"],
  "takeaway": "string — closing one-liner, max 14 words, conversational"
}

The slide should feel: ${audienceTone}.

Rules:
- Be confident. No hedging language.
- No "delve", "leverage", "robust", "seamless", "harness", "comprehensive".
- Numbers earn their place; don't invent them. If user gave no numbers, leave metric as null.
- One claim per bullet.

User input:
"""
${promptText}
"""`;

  const text = await window.claude.complete(sysPrompt);

  // Strip code fences if Claude added them anyway
  let cleaned = String(text || '').trim();
  if (cleaned.startsWith('```')) {
    cleaned = cleaned.replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '');
  }
  // Find the first { and last } in case there's wrapper text
  const first = cleaned.indexOf('{');
  const last = cleaned.lastIndexOf('}');
  if (first >= 0 && last > first) {
    cleaned = cleaned.slice(first, last + 1);
  }
  return JSON.parse(cleaned);
}

function PlaceholderEmpty() {
  return (
    <div className="play__placeholder">
      <svg viewBox="0 0 64 64" fill="none">
        <rect x="6" y="14" width="52" height="36" rx="4" stroke="currentColor" strokeWidth="1.6" />
        <line x1="14" y1="24" x2="34" y2="24" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <line x1="14" y1="32" x2="46" y2="32" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.6" />
        <line x1="14" y1="40" x2="40" y2="40" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.4" />
      </svg>
      <div className="play__placeholder-text">
        Drop a thought on the left.<br/>The slide appears here.
      </div>
    </div>
  );
}

function LoadingShimmer() {
  return (
    <div className="play__loading">
      <div className="play__shimmer eyebrow" />
      <div className="play__shimmer title" />
      <div className="play__shimmer big" />
      <div className="play__shimmer bullet long" />
      <div className="play__shimmer bullet med" />
      <div className="play__shimmer bullet short" />
      <div className="play__loading-text">
        <span className="spinner" />
        drafting the slide
      </div>
    </div>
  );
}

function RenderedSlide({ slide }) {
  return (
    <div className="play__slide">
      <div className="play__slide-eyebrow">{slide.eyebrow}</div>
      <h3 className="play__slide-title">{slide.title}</h3>
      {slide.metric && (
        <>
          <div className="play__slide-metric">{slide.metric}</div>
          {slide.metric_sub && <div className="play__slide-metric-sub">{slide.metric_sub}</div>}
        </>
      )}
      {Array.isArray(slide.bullets) && slide.bullets.length > 0 && (
        <div className="play__slide-bullets">
          {slide.bullets.slice(0, 4).map((b, i) => (
            <div key={i} className="play__slide-bullet">{b}</div>
          ))}
        </div>
      )}
      {slide.takeaway && <div className="play__slide-takeaway">"{slide.takeaway}"</div>}
    </div>
  );
}

function Playground() {
  const [prompt, setPrompt] = useState('');
  const [audience, setAudience] = useState('exec');
  const [loading, setLoading] = useState(false);
  const [slide, setSlide] = useState(null);
  const [error, setError] = useState(null);
  const [files, setFiles] = useState([]);

  function fileExt(name) {
    const m = String(name).match(/\.([^.]+)$/);
    return m ? m[1].slice(0, 4).toUpperCase() : 'FILE';
  }
  function onFilesPicked(e) {
    const picked = Array.from(e.target.files || []);
    if (picked.length === 0) return;
    setFiles(prev => [...prev, ...picked]);
    e.target.value = ''; // allow re-pick of same file
  }
  function removeFile(i) {
    setFiles(prev => prev.filter((_, idx) => idx !== i));
  }

  const handleSend = useCallback(async () => {
    const text = prompt.trim();
    if ((!text && files.length === 0) || loading) return;
    setLoading(true);
    setError(null);
    setSlide(null);
    try {
      const tone = (PLAY_AUDIENCES.find(a => a.key === audience) || PLAY_AUDIENCES[0]).tone;
      const fileNote = files.length > 0
        ? `\n\n(The user also attached ${files.length} file${files.length > 1 ? 's' : ''}: ${files.map(f => f.name).join(', ')}. Use the file names as a hint for what kind of material this is — a deck, a CSV, a plot — but do NOT fabricate contents you can't see.)`
        : '';
      const fullInput = (text || 'Draft a slide from these files.') + fileNote;
      const result = await generateSlide(fullInput, tone);
      if (!result || (!result.title && !result.bullets)) {
        throw new Error('Response was missing required fields.');
      }
      setSlide(result);
    } catch (e) {
      console.warn('generateSlide failed', e);
      setError('Could not generate. Try again or rephrase.');
    } finally {
      setLoading(false);
    }
  }, [prompt, audience, loading, files]);

  function onKeyDown(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      handleSend();
    }
  }

  return (
    <section className="play" id="try">
      <div className="play__inner">
        <div className="play__head">
          <div className="play__eyebrow">
            <span className="live-dot" />
            live demo  ·  real AI, runs in your browser
          </div>
          <h2 className="play__h">
            Try it. <em>Right here.</em>
          </h2>
          <p className="play__sub">
            Type a thought, attach data, plots, decks, or results — one file or many. Pick a room. Watch pptgpt draft a slide on the right.
          </p>
        </div>
        <div className="play__grid">
          <div className="play__input-card">
            <div className="play__input-label">your thought</div>
            <textarea
              className="play__textarea"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="e.g. We hit 118% net retention last quarter — three reasons why, and what we do next."
            />
            <div className="play__attach">
              <label className="play__attach-btn">
                <svg viewBox="0 0 16 16" fill="none">
                  <path d="M11 7 L8 10 Q6 12 4.5 10.5 Q3 9 5 7 L9 3 Q11 1 12.5 2.5 Q14 4 12 6 L8 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Attach files
                <input
                  type="file"
                  multiple
                  accept=".pdf,.pptx,.docx,.csv,.xlsx,.png,.jpg,.jpeg,.svg,.txt,.md,.json"
                  onChange={onFilesPicked}
                />
              </label>
              <span className="play__attach-hint">decks  ·  data  ·  plots  ·  results  —  one or many</span>
              {files.length > 0 && (
                <div className="play__attach-chips">
                  {files.map((f, i) => (
                    <span key={i} className="play__file-chip">
                      <span className="play__file-chip-ico">{fileExt(f.name)}</span>
                      <span className="play__file-chip-name">{f.name}</span>
                      <span className="play__file-chip-size">{Math.max(1, Math.round(f.size / 1024))} KB</span>
                      <button
                        className="play__file-chip-close"
                        onClick={() => removeFile(i)}
                        aria-label={`remove ${f.name}`}
                      >×</button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="play__suggestions">
              <span className="play__suggestion-label">or try</span>
              {PLAY_SUGGESTIONS.map(s => (
                <button key={s} className="play__suggestion" onClick={() => setPrompt(s)}>
                  {s}
                </button>
              ))}
            </div>
            <div className="play__controls">
              <div className="play__audience-mini">
                {PLAY_AUDIENCES.map(a => (
                  <button
                    key={a.key}
                    className={`play__audience-mini-btn ${a.key === audience ? 'is-active' : ''}`}
                    onClick={() => setAudience(a.key)}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
              <button
                className="play__send"
                disabled={(!prompt.trim() && files.length === 0) || loading}
                onClick={handleSend}
              >
                {loading ? 'drafting…' : 'Draft my slide'}
                {!loading && (
                  <svg viewBox="0 0 16 16" fill="none">
                    <path d="M3 8 L13 8 M9 4 L13 8 L9 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </button>
            </div>
          </div>
          <div className="play__output-card">
            <div className="play__output-head">
              <div className="play__output-head-left">
                <span>output</span>
                <span style={{ opacity: 0.5 }}>·</span>
                <span style={{ color: 'var(--ink)' }}>{(PLAY_AUDIENCES.find(a => a.key === audience) || {}).label} room</span>
              </div>
              <div className="play__output-head-right">
                {loading ? 'rendering' : slide ? 'ready' : 'idle'}
              </div>
            </div>
            <div className="play__output">
              {!loading && !slide && !error && <PlaceholderEmpty />}
              {loading && <LoadingShimmer />}
              {error && !loading && (
                <div className="play__error">
                  <div className="play__error-icon">!</div>
                  <div className="play__error-text">{error}</div>
                </div>
              )}
              {slide && !loading && <RenderedSlide slide={slide} />}
            </div>
          </div>
        </div>
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
        <button className="nav__link" onClick={() => { window.location.href = '/storyboard'; }}>Storyboard</button>
        <button className="nav__link">Pricing</button>
      </div>
      <div className="nav__right">
        <button className="btn btn--ghost">Log in</button>
        <button
          className="btn btn--primary"
          onClick={() => { window.location.href = '/setup'; }}
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
        <span className="hero__eyebrow-pill">live</span>
        Five modes  ·  six rooms  ·  one tool
      </div>
      <h1 className="hero__title">
        Slides that <span className="hero__title-em">argue.</span>
      </h1>
      <p className="hero__sub">
        Drop in a thought, a slide, a deck, or your data, plots, and results — one file or many. pptgpt drafts, refines, condenses, visualizes, or synthesizes — whichever your material needs.
      </p>
      <div className="hero__cta">
        <button
          className="btn btn--accent btn--lg"
          onClick={() => { window.location.href = '/setup'; }}
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
          <span className="peek__label">drop in  ·  one or many</span>
          <div className="peek__chips">
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--mute)' }} />a thought</span>
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--mute)' }} />a draft slide</span>
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--mute)' }} />.pptx / .pdf decks</span>
            <span className="peek__chip"><span className="peek__chip-dot" style={{ background: 'var(--mute)' }} />data, plots & results</span>
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
        <div className="peek__multi-hint">
          <strong>↑</strong>  drop one file or fifty  ·  pptgpt reads them together
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
      <ModesGlance />
      <ScrollyDemo />
      <AudienceSwitcher />
      <Playground />
      <Footer />
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
