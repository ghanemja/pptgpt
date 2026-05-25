/* ============================================================
   pptgpt.jsx — landing / main entry
   Clean carousel-first design. One prompt, five takes.
   ============================================================ */

const { useState, useEffect, useRef, useCallback } = React;

/* ────────────────────────────────────────────────────────────
   Five slide variations — same content ("Q3 revenue beat plan
   by 14%"), five visual treatments.
   ──────────────────────────────────────────────────────────── */

function SBignum() {
  return (
    <div className="slide-card__inner s-bignum">
      <div className="s-bignum__left">
        <div>
          <div className="slide-eyebrow">Q3 results  ·  exec review</div>
          <h3 className="s-bignum__title" style={{ marginTop: 8 }}>
            Q3 revenue beat plan by 14%
          </h3>
        </div>
        <div>
          <div className="s-bignum__num">+14%</div>
          <div className="s-bignum__num-sub">vs plan  ·  $42M actuals</div>
        </div>
      </div>
      <div className="s-bignum__right">
        <div className="s-bignum__stats">
          <div>
            <div className="s-bignum__stat-label">Net retention</div>
            <div className="s-bignum__stat-val">118%</div>
          </div>
          <div>
            <div className="s-bignum__stat-label">Churn</div>
            <div className="s-bignum__stat-val">1.8%</div>
          </div>
          <div>
            <div className="s-bignum__stat-label">Gross margin</div>
            <div className="s-bignum__stat-val">76%</div>
          </div>
        </div>
        <div className="s-bignum__quote">
          "And the trend keeps compounding."
        </div>
      </div>
    </div>
  );
}

function SBars() {
  const data = [
    { q: 'Q1', v: 32, hi: false },
    { q: 'Q2', v: 38, hi: false },
    { q: 'Q3', v: 42, hi: true },
    { q: 'Q4', v: 37, hi: false, dim: true },
  ];
  const max = 48;
  const planFrac = 37 / max; // plan line at 37
  return (
    <div className="slide-card__inner s-bars">
      <div className="s-bars__head">
        <div>
          <div className="slide-eyebrow">Quarterly revenue  ·  $M</div>
          <div className="s-bars__title">A clean step-up in Q3</div>
        </div>
        <div className="slide-eyebrow" style={{ alignSelf: 'flex-end' }}>FY26</div>
      </div>
      <div className="s-bars__chart">
        <div className="s-bars__plan-line" style={{ bottom: `calc(32px + ${planFrac * 100}% * 0.7)` }}>
          <span className="s-bars__plan-tag">plan</span>
        </div>
        {data.map((d) => (
          <div className={`s-bars__bar-wrap ${d.hi ? 'is-hi' : ''}`} key={d.q}>
            <div
              className={`s-bars__bar ${d.hi ? 'is-hi' : ''}`}
              style={{
                height: `${(d.v / max) * 100}%`,
                opacity: d.dim ? 0.35 : 1,
                background: d.dim ? 'var(--mute)' : undefined,
              }}
            >
              <span className="s-bars__bar-val">{d.v}</span>
            </div>
            <span className="s-bars__bar-label">{d.q}</span>
          </div>
        ))}
      </div>
      <div className="s-bars__caption">
        Q3 ahead of plan by <strong style={{ color: 'var(--accent)' }}>$5.1M</strong>. Q4 trending in line.
      </div>
    </div>
  );
}

function SQuote() {
  return (
    <div className="slide-card__inner s-quote">
      <div className="slide-eyebrow">From the Q3 sales review</div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <div className="s-quote__open">"</div>
        <p className="s-quote__text">
          Enterprise close rate doubled. Multi-year contracts are now 60% of new ARR.
        </p>
      </div>
      <div className="s-quote__attr">— Sales review, Q3</div>
    </div>
  );
}

function SCols() {
  return (
    <div className="slide-card__inner s-cols">
      <div className="slide-eyebrow">What drove the beat</div>
      <h3 className="s-cols__title">Three things compounded</h3>
      <div className="s-cols__grid">
        <div className="s-cols__col">
          <div>
            <div className="s-cols__col-num">01</div>
            <div className="s-cols__col-h">Enterprise GTM</div>
          </div>
          <div>
            <div className="s-cols__col-val">+2×</div>
            <div className="s-cols__col-sub">close rate vs H1, on larger deals</div>
          </div>
        </div>
        <div className="s-cols__col">
          <div>
            <div className="s-cols__col-num">02</div>
            <div className="s-cols__col-h">Multi-year deals</div>
          </div>
          <div>
            <div className="s-cols__col-val">60%</div>
            <div className="s-cols__col-sub">share of new ARR booked Q3</div>
          </div>
        </div>
        <div className="s-cols__col">
          <div>
            <div className="s-cols__col-num">03</div>
            <div className="s-cols__col-h">Public sector</div>
          </div>
          <div>
            <div className="s-cols__col-val">2</div>
            <div className="s-cols__col-sub">design-partner wins, both expansion-ready</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SDecision() {
  return (
    <div className="slide-card__inner s-dec">
      <div className="s-dec__head">
        <div className="slide-eyebrow">Q4 plan</div>
        <div className="s-dec__tag">decision</div>
      </div>
      <p className="s-dec__statement">
        Double down on <em>enterprise.</em><br/>
        Pause SMB experiments.
      </p>
      <div className="s-dec__next">
        <div className="s-dec__next-item">
          <div className="s-dec__next-label">Owner</div>
          <div className="s-dec__next-val">M. Reyes — GTM</div>
        </div>
        <div className="s-dec__next-item">
          <div className="s-dec__next-label">By when</div>
          <div className="s-dec__next-val">Oct 15</div>
        </div>
        <div className="s-dec__next-item">
          <div className="s-dec__next-label">Spend shift</div>
          <div className="s-dec__next-val">40% of marketing → ENT</div>
        </div>
      </div>
    </div>
  );
}

const SLIDES = [
  { key: 'bignum',   label: 'Big number',     Comp: SBignum },
  { key: 'bars',     label: 'Bar chart',      Comp: SBars },
  { key: 'quote',    label: 'Pull quote',     Comp: SQuote },
  { key: 'cols',     label: 'Three columns',  Comp: SCols },
  { key: 'decision', label: 'Decision card',  Comp: SDecision },
];

/* ────────────────────────────────────────────────────────────
   Carousel layout — fanned stack with active slide forward
   ──────────────────────────────────────────────────────────── */

function offsetFor(diff, total) {
  // Diff = position relative to active, clamped to nearest path on the ring
  let d = diff;
  if (d > total / 2) d -= total;
  if (d < -total / 2) d += total;
  return d;
}

function transformFor(d, isActive) {
  const abs = Math.abs(d);
  if (abs > 2) {
    return { x: d < 0 ? -800 : 800, scale: 0.5, rot: d < 0 ? -18 : 18, opacity: 0, z: 0 };
  }
  if (abs === 0) return { x: 0,   scale: 1.0,  rot: 0,  opacity: 1,   z: 4 };
  if (abs === 1) return { x: d * 320, scale: 0.86, rot: d * -6,  opacity: 0.92, z: 3 };
  if (abs === 2) return { x: d * 520, scale: 0.72, rot: d * -10, opacity: 0.55, z: 2 };
  return { x: 0, scale: 1, rot: 0, opacity: 1, z: 4 };
}

function Carousel({ idx, onJump, total }) {
  return (
    <div className="stage__track">
      {SLIDES.map((s, i) => {
        const d = offsetFor(i - idx, total);
        const t = transformFor(d, i === idx);
        const isActive = i === idx;
        return (
          <div
            key={s.key}
            className={`slide-card ${isActive ? 'is-active' : ''}`}
            onClick={() => !isActive && onJump(i)}
            style={{
              transform: `translateX(${t.x}px) scale(${t.scale}) rotate(${t.rot}deg)`,
              opacity: t.opacity,
              zIndex: t.z,
              pointerEvents: Math.abs(d) > 2 ? 'none' : 'auto',
              filter: !isActive ? 'saturate(0.92)' : undefined,
            }}
            aria-hidden={!isActive}
          >
            <s.Comp />
          </div>
        );
      })}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   Demo prompt — appears in the floating prompt card. Cycles
   gently to suggest the user can type whatever.
   ──────────────────────────────────────────────────────────── */

const DEMO_PROMPTS = [
  'We beat Q3 revenue plan by 14% — here\u2019s why',
  'Onboarding drop-off is up 8 points since the redesign',
  'Damped harmonic oscillator: γ controls how fast it decays',
  'Customer-renewal forecast for FY26',
];

function useRotatingText(strings, intervalMs, paused) {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setIdx(i => (i + 1) % strings.length), intervalMs);
    return () => clearInterval(t);
  }, [strings.length, intervalMs, paused]);
  return strings[idx];
}

/* ────────────────────────────────────────────────────────────
   Composer — actual input
   ──────────────────────────────────────────────────────────── */

const AUDIENCES = [
  { key: 'exec',       label: 'Exec review' },
  { key: 'customer',   label: 'Customer update' },
  { key: 'standup',    label: 'Standup' },
  { key: 'conference', label: 'Conference talk' },
];

function Composer({ value, onChange, audience, onAudience, onGenerate }) {
  return (
    <div className="composer-wrap">
      <div className="composer-eyebrow"><span className="arrow">↓</span> now make your own</div>
      <h2 className="composer-h">
        Tell us what your slide is <em>about.</em>
      </h2>
      <div className="composer">
        <div className="composer__inner">
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="e.g. We hit 118% net retention last quarter — three reasons why, and what we do next."
            rows={2}
          />
          <div className="composer__row">
            <div className="composer__chips">
              {AUDIENCES.map(a => (
                <button
                  key={a.key}
                  className={`chip ${audience === a.key ? 'is-active' : ''}`}
                  onClick={() => onAudience(a.key)}
                >
                  <span className="chip__dot" />
                  {a.label}
                </button>
              ))}
            </div>
            <button
              className="composer__send"
              disabled={!value.trim()}
              onClick={onGenerate}
            >
              Make 5 slides
              <svg viewBox="0 0 16 16" fill="none">
                <path d="M3 8 L13 8 M9 4 L13 8 L9 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      </div>
      <div className="examples">
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, letterSpacing: '0.14em', color: 'var(--mute)', textTransform: 'uppercase', alignSelf: 'center', marginRight: 4 }}>or try</span>
        {[
          'Onboarding drop-off is up 8 points',
          'How we shipped the migration in 6 weeks',
          'Why our churn fell to 1.8%',
        ].map(p => (
          <button key={p} className="example" onClick={() => onChange(p)}>
            <span className="quote">"</span>{p}<span className="quote">"</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   How it works — three small visualized steps
   ──────────────────────────────────────────────────────────── */

function HowItWorks() {
  return (
    <section className="how">
      <div className="how__head">
        <h2 className="how__h">How it works</h2>
        <span className="how__meta">three steps  ·  ~10 seconds</span>
      </div>
      <div className="how__grid">
        <div className="how__step">
          <div className="how__num">01  ·  TYPE</div>
          <h4 className="how__step-h">Drop a thought.</h4>
          <p className="how__step-p">A sentence, a paragraph, a bullet list. Or a PDF.</p>
          <div className="how__step-vis">
            <svg viewBox="0 0 240 100" style={{ width: '100%', height: '100%' }} aria-hidden="true">
              <rect x="6" y="6" width="228" height="88" rx="6" fill="#FFFFFF" stroke="#DCD5C3" />
              <rect x="16" y="18" width="160" height="6" rx="2" fill="#14141B" />
              <rect x="16" y="32" width="200" height="4" rx="2" fill="#8A8678" opacity="0.6" />
              <rect x="16" y="42" width="180" height="4" rx="2" fill="#8A8678" opacity="0.6" />
              <rect x="16" y="52" width="140" height="4" rx="2" fill="#8A8678" opacity="0.4" />
              <rect x="16" y="74" width="2" height="12" fill="#1F2BD6">
                <animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite" />
              </rect>
            </svg>
          </div>
        </div>
        <div className="how__step">
          <div className="how__num">02  ·  PICK</div>
          <h4 className="how__step-h">Get five takes.</h4>
          <p className="how__step-p">Same idea, different visual treatments. Pick the one that fits the room.</p>
          <div className="how__step-vis">
            <svg viewBox="0 0 240 100" style={{ width: '100%', height: '100%' }} aria-hidden="true">
              {[0,1,2,3,4].map(i => (
                <g key={i} transform={`translate(${50 + i * 28}, ${24 - i * 2}) rotate(${(i-2)*3} 60 30)`}>
                  <rect width="120" height="68" rx="4" fill="#FFFFFF" stroke="#DCD5C3" />
                  <rect x="10" y="10" width={60 - i*4} height="4" rx="1" fill="#14141B" />
                  <rect x="10" y="22" width="80" height="3" rx="1" fill="#8A8678" opacity="0.5" />
                  <rect x="10" y="30" width="60" height="3" rx="1" fill="#8A8678" opacity="0.5" />
                  {i === 2 && <rect x="10" y="46" width="32" height="14" rx="2" fill="#1F2BD6" />}
                </g>
              ))}
            </svg>
          </div>
        </div>
        <div className="how__step">
          <div className="how__num">03  ·  KEEP</div>
          <h4 className="how__step-h">Export, edit, or iterate.</h4>
          <p className="how__step-p">Download as .pptx, tweak in your deck app, or ask for another take.</p>
          <div className="how__step-vis">
            <svg viewBox="0 0 240 100" style={{ width: '100%', height: '100%' }} aria-hidden="true">
              <rect x="60" y="14" width="120" height="68" rx="6" fill="#FFFFFF" stroke="#DCD5C3" />
              <rect x="72" y="26" width="50" height="6" rx="2" fill="#14141B" />
              <rect x="72" y="40" width="80" height="3" rx="1" fill="#8A8678" opacity="0.5" />
              <rect x="72" y="48" width="60" height="3" rx="1" fill="#8A8678" opacity="0.5" />
              <rect x="72" y="62" width="36" height="12" rx="2" fill="#FF5A2C" />
              <text x="90" y="71" fontSize="8" fill="#FFFFFF" fontFamily="IBM Plex Mono, monospace" textAnchor="middle" fontWeight="600">.PPTX</text>
              <path d="M120 90 L120 96 M116 92 L120 96 L124 92" stroke="#1F2BD6" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────
   App
   ──────────────────────────────────────────────────────────── */

function App() {
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [prompt, setPrompt] = useState('');
  const [audience, setAudience] = useState('exec');
  const composerRef = useRef(null);

  const total = SLIDES.length;

  // Autoplay carousel
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setIdx(i => (i + 1) % total), 4200);
    return () => clearInterval(t);
  }, [playing, total]);

  // Keyboard nav
  useEffect(() => {
    function onKey(e) {
      if (e.target && (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT')) return;
      if (e.key === 'ArrowLeft') { setIdx(i => (i - 1 + total) % total); setPlaying(false); }
      if (e.key === 'ArrowRight') { setIdx(i => (i + 1) % total); setPlaying(false); }
      if (e.key === ' ') { setPlaying(p => !p); e.preventDefault(); }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [total]);

  const demoPrompt = useRotatingText(DEMO_PROMPTS, 5500, !playing);
  const activeLabel = SLIDES[idx].label;

  const advance = useCallback((delta) => {
    setIdx(i => (i + delta + total) % total);
    setPlaying(false);
  }, [total]);

  const scrollToComposer = useCallback(() => {
    if (composerRef.current) {
      const top = composerRef.current.getBoundingClientRect().top + window.scrollY - 24;
      window.scrollTo({ top, behavior: 'smooth' });
    }
  }, []);

  return (
    <>
      <nav className="nav">
        <div className="nav__brand">
          <span className="nav__brand-mark" />
          pptgpt
        </div>
        <div className="nav__links">
          <button className="nav__link">Examples</button>
          <button className="nav__link">Templates</button>
          <button className="nav__link">Pricing</button>
          <button className="nav__link">Docs</button>
        </div>
        <div className="nav__right">
          <button className="btn btn--ghost">Log in</button>
          <button className="btn btn--primary" onClick={scrollToComposer}>Try it free</button>
        </div>
      </nav>

      <section className="hero">
        <div className="hero__eyebrow"><span className="dot" />five drafts per prompt  ·  no template lock-in</div>
        <h1 className="hero__title">
          Type a thought.<br/>Pick a <em>slide.</em>
        </h1>
        <p className="hero__sub">
          pptgpt drafts five takes on every slide you describe. Same idea, five visual treatments. You pick the one that fits the room.
        </p>

        <div className="stage">
          <Carousel idx={idx} onJump={(i) => { setIdx(i); setPlaying(false); }} total={total} />

          <div className="prompt-card">
            <div className="prompt-card__lead">
              <div className="prompt-card__label">your prompt</div>
              <div className="prompt-card__text" key={demoPrompt}>
                {demoPrompt}<span className="cursor" />
              </div>
            </div>
            <button className="btn btn--accent" onClick={scrollToComposer}>
              Try yours
              <svg viewBox="0 0 14 14" width="14" height="14" fill="none">
                <path d="M3 7 L11 7 M8 4 L11 7 L8 10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>

        <div className="controls">
          <button className="ctrl" onClick={() => advance(-1)} aria-label="previous">
            <svg viewBox="0 0 16 16" fill="none">
              <path d="M10 3 L5 8 L10 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <button className="ctrl ctrl--play" onClick={() => setPlaying(p => !p)} aria-label={playing ? 'pause' : 'play'}>
            {playing ? (
              <svg viewBox="0 0 16 16" fill="none">
                <rect x="5" y="3.5" width="2" height="9" rx="0.5" fill="currentColor" />
                <rect x="9" y="3.5" width="2" height="9" rx="0.5" fill="currentColor" />
              </svg>
            ) : (
              <svg viewBox="0 0 16 16" fill="none">
                <path d="M5 3 L13 8 L5 13 Z" fill="currentColor" />
              </svg>
            )}
          </button>
          <button className="ctrl" onClick={() => advance(1)} aria-label="next">
            <svg viewBox="0 0 16 16" fill="none">
              <path d="M6 3 L11 8 L6 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <div className="dots">
            {SLIDES.map((s, i) => (
              <button
                key={s.key}
                className={`dot ${i === idx ? 'is-active' : ''}`}
                onClick={() => { setIdx(i); setPlaying(false); }}
                aria-label={`go to ${s.label}`}
              />
            ))}
          </div>
          <span className="counter">
            {String(idx + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}  ·  {activeLabel}
          </span>
        </div>
      </section>

      <div ref={composerRef}>
        <Composer
          value={prompt}
          onChange={setPrompt}
          audience={audience}
          onAudience={setAudience}
          onGenerate={() => {
            // Demo only — flash a hint and scroll up to the carousel
            window.scrollTo({ top: 0, behavior: 'smooth' });
            setPlaying(true);
            setIdx(0);
          }}
        />
      </div>

      <HowItWorks />

      <footer className="footer">
        <div>© 2026 pptgpt  ·  built for the room</div>
        <div className="footer__links">
          <a href="#" className="footer__link">Privacy</a>
          <a href="#" className="footer__link">Terms</a>
          <a href="#" className="footer__link">Contact</a>
        </div>
      </footer>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
