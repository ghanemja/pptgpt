/* ============================================================
   app.jsx — pptgpt UI
   ------------------------------------------------------------
   Thin, stateless view over the data contract in types.md.
   All design decisions (palette, layout, sizes) come from
   the backend's SlideSpec. The UI only renders.
   ============================================================ */

const { useState, useEffect, useLayoutEffect, useRef, useMemo } = React;
const { SlidePreview } = window;

// Design canvas — the workspace is laid out at these dims, then
// CSS-scaled to fit the viewport. Slide is centered at 720x405.
const DESIGN_W = 1360;
const DESIGN_H = 780;
const SLIDE_W  = 720;
const SLIDE_H  = 405;

const SAMPLE_PROMPTS = {
  draft: [
    { label: 'Q3 board update', body:
`Q3 revenue beat plan by 14%
Net retention 118%, churn down to 1.8%
New enterprise cohort outpacing SMB by 2x
Decision: double down on enterprise GTM` },
    { label: 'Launch announcement', body:
`Announcing Helix 2.0
Faster offline-first sync
Native iPad pencil support
Available to all teams today` },
    { label: 'Research finding', body:
`Users abandon onboarding at step 4
Drop-off correlates with form length
Hypothesis: split into 3 micro-steps
Pilot with 5% of new signups` },
  ],
  refine: [
    { label: 'A half-done chart slide', body:
`Quarterly revenue growth
Chart shows: 14% YoY, accelerating from Q2's 9%
Three lines, no labels
Feels: numbers buried, no takeaway in sight` },
    { label: 'A flat title slide', body:
`Welcome to Helix 2.0
Subtitle: A better way to think
It's just centered text on white. Feels generic.
Should communicate: warm, considered, technical` },
  ],
  condense: [
    { label: 'Q3 board deck (5 → 3)', body:
`Q3 results — exec summary
Net revenue beat plan by 14%
Retention strong; churn down two points
Enterprise GTM working; SMB softening
---
The numbers
Revenue +14% YoY ($42M)
Net retention 118%
Churn 1.8%, down from 3.6% in Q2
Gross margin held at 76%
---
What's working
Enterprise close rate up 2x
Multi-year contracts now 60% of new ARR
Two design-partner wins in the public sector
---
What's not
SMB CAC up 30%
Free-trial conversion flat
PLG funnel needs surgery, not optimization
---
Next quarter
Double down on enterprise GTM
Pause SMB paid acquisition
Ship the new onboarding flow by Nov 1` },
    { label: 'Project pitch (4 → 3)', body:
`The Helix project: native-first sync
What's broken: web sync drops 6% of edits monthly
---
The plan: rewrite sync in Rust, offline-first
Three engineers, 12 weeks
---
The cost: $480K (engineering + infra)
Risk: native engineers are hard to hire
---
The bet: 3x reliability, opens iPad market` },
  ],
};

const MODE_META = {
  draft:    { label: 'Draft',    title: 'a rough slide',       blurb: 'paste your raw notes',                     placeholder: 'One title.\nA few lines of body.\nNumbers if you have them.\nA decision or takeaway.\n\nWe\'ll ask a couple of taste questions before drafting.' },
  refine:   { label: 'Refine',   title: 'a half-done draft',   blurb: 'paste what you have + what feels off',     placeholder: 'What you have:\n  A chart, 3 bullets, no takeaway line.\n\nWhat\'s off:\n  Numbers feel buried, the eye doesn\'t land anywhere.\n\nWe\'ll ask you a few taste questions and rework it.' },
  condense: { label: 'Condense', title: 'a full deck',         blurb: 'paste your slides, --- between them',      placeholder: 'Slide 1 title\nBullets…\n---\nSlide 2 title\nBullets…\n---\nSlide 3 title\nBullets…\n\nWe\'ll ask you what to compress around, then return a short version.' },
};

// ── Hook: keep workspace scaled to fit viewport ─────────────────
function useFitScale(designW, designH, vPad, hPad) {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const onResize = () => {
      const availW = window.innerWidth  - hPad * 2;
      const availH = window.innerHeight - vPad;
      const s = Math.min(availW / designW, availH / designH, 1);
      setScale(Math.max(s, 0.4));
    };
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [designW, designH, vPad, hPad]);
  return scale;
}

// ── Chrome (top bar) ────────────────────────────────────────────
function Chrome({ phase, mode, onReset, loading }) {
  const modeLabel = MODE_META[mode] ? MODE_META[mode].label.toLowerCase() : '';
  return (
    <header className="chrome">
      <div className="wordmark">
        <span className="mark-dot" />
        pptgpt
        <span className="mark-meta">{phase === 'input' ? 'a slide that asks first' : `mode · ${modeLabel}`}</span>
      </div>
      <div className="chrome-actions">
        {loading && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span className="thinking-dot" /> thinking
          </span>
        )}
        {phase !== 'input' && (
          <button onClick={onReset}>↺ start over</button>
        )}
      </div>
    </header>
  );
}

// ── Footer (step indicator) ─────────────────────────────────────
function Footer({ phase, answeredCount, totalQuestions, hideChrome }) {
  if (hideChrome) return null;
  const steps = [
    { key: 'input',      label: '01  paste' },
    { key: 'questions',  label: '02  decide' },
    { key: 'directions', label: '03  pick a direction' },
  ];
  const currentIndex = phase === 'focused' ? 2 : steps.findIndex(s => s.key === phase);

  return (
    <footer className="footer">
      <div className="step-dots">
        {steps.map((s, i) => (
          <React.Fragment key={s.key}>
            <span className={`step-dot ${i === currentIndex ? 'is-active' : i < currentIndex ? 'is-done' : ''}`} />
            <span style={{ opacity: i === currentIndex ? 1 : 0.5 }}>{s.label}</span>
            {i < steps.length - 1 && <span style={{ width: 24, height: 1, background: 'var(--gray-3)', display: 'inline-block', margin: '0 4px' }} />}
          </React.Fragment>
        ))}
      </div>
      <div className="keyhint">
        {phase === 'input' && (<>press <kbd>⌘</kbd> <kbd>↵</kbd> to send</>)}
        {phase === 'questions' && totalQuestions > 0 && (
          <span>{answeredCount} / {totalQuestions} answered  ·  cards drift to confirm</span>
        )}
        {phase === 'directions' && (<>tap any direction to inspect full-size</>)}
        {phase === 'focused' && (<>press <kbd>esc</kbd> to return</>)}
      </div>
    </footer>
  );
}

// ── Input phase ─────────────────────────────────────────────────
function InputPhase({ mode, onModeChange, value, onChange, onSubmit }) {
  const ref = useRef(null);
  useEffect(() => { ref.current && ref.current.focus(); }, []);

  function onKey(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      onSubmit();
    }
  }

  const meta = MODE_META[mode];

  return (
    <div className="input-phase">
      <div className="input-eyebrow">a calm canvas for one slide — or one short deck — at a time</div>
      <h1 className="input-prompt">
        Start with <em>{meta.title}</em>.
        <br />Don't worry about how it looks.
      </h1>

      <div className="mode-picker" role="tablist" aria-label="entry mode">
        {Object.entries(MODE_META).map(([key, m]) => (
          <button
            key={key}
            role="tab"
            aria-selected={mode === key}
            className={`mode-pill ${mode === key ? 'is-active' : ''}`}
            onClick={() => onModeChange(key)}
          >
            <span className="mode-pill__label">{m.label}</span>
            <span className="mode-pill__blurb">{m.blurb}</span>
          </button>
        ))}
      </div>

      <div className="input-paper">
        <textarea
          ref={ref}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={onKey}
          placeholder={meta.placeholder}
        />
        <div className="input-row">
          <div className="samples">
            <span style={{ alignSelf: 'center', marginRight: 4 }}>or try</span>
            {(SAMPLE_PROMPTS[mode] || []).map(s => (
              <button key={s.label} className="sample-chip" onClick={() => onChange(s.body)}>{s.label}</button>
            ))}
          </div>
          <button className="go-btn" disabled={!value.trim()} onClick={onSubmit}>
            ask the taste questions <span className="arrow">→</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Question card ───────────────────────────────────────────────
function QuestionCard({ q, index, total, picked, isDrifting, onPick }) {
  return (
    <div className={`card-anchor card-anchor--${q.region}`}>
      <span className="qcard__leader" />
      <span className="qcard__pin" />
      <div className={`qcard ${isDrifting ? 'is-drifting' : ''}`}>
        <div className="qcard__head">
          <span className="qcard__index">{String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}</span>
          <span className="qcard__region">{q.region}</span>
        </div>
        <p className="qcard__text">{q.text}</p>
        <div className="qcard__opts">
          {q.options.map(opt => (
            <button
              key={opt}
              className={`qopt ${picked === opt ? 'is-picked' : ''}`}
              disabled={!!picked}
              onClick={() => onPick(opt)}
            >{opt}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Questions phase ─────────────────────────────────────────────
function QuestionsPhase({ response, answers, removedIds, loading, onAnswer }) {
  const scale = useFitScale(DESIGN_W, DESIGN_H, 220, 64);

  if (!response) {
    // First-load loading state
    return (
      <div className="canvas-wrap" style={{ width: DESIGN_W * scale, height: DESIGN_H * scale }}>
        <div style={{
          width: DESIGN_W, height: DESIGN_H,
          transform: `scale(${scale})`, transformOrigin: 'top left',
        }}>
          <div className="workspace">
            <div className="slide-wrap" style={{ width: SLIDE_W, height: SLIDE_H }}>
              <div className="slide-frame" style={{ width: SLIDE_W, height: SLIDE_H, opacity: 0.4 }} />
              <span className="slide-frame__label">draft preview <span className="dim">awaiting backend…</span></span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const { slideIR, questions } = response;
  const visibleQuestions = questions.filter(q => !removedIds.has(q.id));

  return (
    <div className="canvas-wrap" style={{ width: DESIGN_W * scale, height: DESIGN_H * scale }}>
      <div style={{
        width: DESIGN_W, height: DESIGN_H,
        transform: `scale(${scale})`, transformOrigin: 'top left',
        position: 'relative',
      }}>
        <div className="workspace">
          <div className="slide-wrap" style={{ width: SLIDE_W, height: SLIDE_H }}>
            <div className="slide-frame" style={{ width: SLIDE_W, height: SLIDE_H }}>
              <div className="slide-inner">
                <SlidePreview spec={slideIR} width={SLIDE_W} height={SLIDE_H} />
              </div>
            </div>
            <span className="slide-frame__label">
              draft preview
              <span className="dim">{slideIR.canvasW}×{slideIR.canvasH}  ·  16:9</span>
            </span>
            {visibleQuestions.map((q, i) => (
              <QuestionCard
                key={q.id}
                q={q}
                index={questions.findIndex(qq => qq.id === q.id)}
                total={questions.length}
                picked={answers[q.id]}
                isDrifting={!!answers[q.id]}
                onPick={(opt) => onAnswer(q, opt)}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Directions phase ────────────────────────────────────────────
function DirectionsPhase({ response, mode, onPick, loading }) {
  // Render each previewSpec scaled to a thumbnail width.
  const wrapRef = useRef(null);
  const [thumbW, setThumbW] = useState(0);
  useLayoutEffect(() => {
    const measure = () => {
      if (!wrapRef.current) return;
      const card = wrapRef.current.querySelector('.dir-frame');
      if (card) setThumbW(card.clientWidth);
    };
    measure();
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    });
    if (wrapRef.current) ro.observe(wrapRef.current);
    window.addEventListener('resize', measure);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [response]);

  if (!response) return null;
  const { directions } = response;
  const isMulti = directions.some(d => d.slides && d.slides.length > 1);

  return (
    <div className="directions" ref={wrapRef}>
      <div className="directions-head">
        <h2>
          {mode === 'condense'
            ? <>Three condensations — same arc, three <em>takes</em>.</>
            : mode === 'refine'
            ? <>Three reworks — same content, three <em>directions</em>.</>
            : <>Three directions — same content, three <em>takes</em>.</>}
        </h2>
        <div className="sub">
          tap a thumbnail to inspect full-size  ·  pick the one that fits the room
        </div>
      </div>
      <div className="directions-grid">
        {directions.map((d, i) => {
          const spec = d.previewSpec;
          const slides = d.slides || [spec];
          const thumbH = thumbW * (spec.canvasH / spec.canvasW);
          return (
            <button
              key={d.key}
              className="dir-card"
              onClick={() => onPick(d.key)}
            >
              <div className="dir-frame-wrap">
                {slides.length > 1 && (
                  <div className="dir-frame__stack" aria-hidden="true">
                    <span className="dir-frame__stack-sheet" />
                    <span className="dir-frame__stack-sheet dir-frame__stack-sheet--2" />
                  </div>
                )}
                <div className="dir-frame">
                  {thumbW > 0 && (
                    <SlidePreview spec={spec} width={thumbW} height={thumbH} />
                  )}
                </div>
              </div>
              <div className="dir-meta">
                <span className="dir-label">{d.label}</span>
                <span className="dir-key">
                  {slides.length > 1
                    ? `${slides.length} slides`
                    : `${String(i + 1).padStart(2, '0')} / ${String(directions.length).padStart(2, '0')}`}
                </span>
              </div>
              {d.blurb && <div className="dir-blurb">{d.blurb}</div>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Focused phase ───────────────────────────────────────────────
function FocusedPhase({ response, focusedKey, onBack }) {
  const wrapRef = useRef(null);
  const [w, setW] = useState(0);
  const [slideIdx, setSlideIdx] = useState(0);

  // reset slide index when switching focused direction
  useEffect(() => { setSlideIdx(0); }, [focusedKey]);

  useLayoutEffect(() => {
    const measure = () => {
      if (!wrapRef.current) return;
      const frame = wrapRef.current.querySelector('.focus-frame');
      if (frame) setW(frame.clientWidth);
    };
    measure();
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    });
    if (wrapRef.current) ro.observe(wrapRef.current);
    window.addEventListener('resize', measure);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [focusedKey]);

  const dir = response && response.directions.find(d => d.key === focusedKey);
  const slides = dir ? (dir.slides || [dir.previewSpec]) : [];
  const total  = slides.length;

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape')    onBack();
      if (e.key === 'ArrowRight' && total > 1) setSlideIdx(i => Math.min(i + 1, total - 1));
      if (e.key === 'ArrowLeft'  && total > 1) setSlideIdx(i => Math.max(i - 1, 0));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onBack, total]);

  if (!dir) return null;
  const spec = slides[slideIdx] || dir.previewSpec;
  const h = w * (spec.canvasH / spec.canvasW);

  return (
    <div className="focus-phase" ref={wrapRef}>
      <div className="focus-head">
        <button className="back" onClick={onBack}>← back to directions</button>
        <div className="focus-title">
          <span className="k">direction · {dir.key}</span>
          <h2>{dir.label}</h2>
        </div>
        <div style={{ minWidth: 160 }}>
          {total > 1 && (
            <div className="slide-nav">
              <button className="nav-btn" onClick={() => setSlideIdx(i => Math.max(i - 1, 0))} disabled={slideIdx === 0}>←</button>
              <span className="nav-count">{String(slideIdx + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}</span>
              <button className="nav-btn" onClick={() => setSlideIdx(i => Math.min(i + 1, total - 1))} disabled={slideIdx === total - 1}>→</button>
            </div>
          )}
        </div>
      </div>
      <div className="focus-frame">
        {w > 0 && <SlidePreview spec={spec} width={w} height={h} />}
      </div>
      {total > 1 && (
        <div className="filmstrip">
          {slides.map((s, i) => {
            const tw = 140;
            const th = tw * (s.canvasH / s.canvasW);
            return (
              <button
                key={i}
                className={`filmstrip__cell ${i === slideIdx ? 'is-active' : ''}`}
                onClick={() => setSlideIdx(i)}
              >
                <div className="filmstrip__thumb" style={{ width: tw, height: th }}>
                  <SlidePreview spec={s} width={tw} height={th} />
                </div>
                <span className="filmstrip__num">{String(i + 1).padStart(2, '0')}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Top-level App ───────────────────────────────────────────────
function App() {
  // Allow deep-linking via URL params:
  //   ?mode=draft|refine|condense   — set starting mode
  //   ?sample=0                     — prefill the Nth sample for that mode
  //   ?go=1                         — auto-advance to the questions phase
  //   ?chrome=0                     — hide top/bottom chrome (for embedding)
  const params = new URLSearchParams(window.location.search);
  const initialMode = (() => {
    const m = params.get('mode');
    return (m === 'draft' || m === 'refine' || m === 'condense') ? m : 'draft';
  })();
  const sampleIdx   = parseInt(params.get('sample') || '-1', 10);
  const initialRaw  = sampleIdx >= 0 && SAMPLE_PROMPTS[initialMode] && SAMPLE_PROMPTS[initialMode][sampleIdx]
                        ? SAMPLE_PROMPTS[initialMode][sampleIdx].body : '';
  const autoGo      = params.get('go') === '1';
  const hideChrome  = params.get('chrome') === '0';

  const [phase, setPhase] = useState('input');
  const [mode, setMode] = useState(initialMode);
  const [rawContent, setRawContent] = useState(initialRaw);
  const [response, setResponse] = useState(null);
  const [answers, setAnswers] = useState({});
  const [removedIds, setRemovedIds] = useState(() => new Set());
  const [loading, setLoading] = useState(false);
  const [focusedKey, setFocusedKey] = useState(null);

  async function submit() {
    if (!rawContent.trim()) return;
    setLoading(true);
    setPhase('questions');
    const res = await window.mockBackend({ mode, rawContent, answers: {} });
    setResponse(res);
    setLoading(false);
  }

  // Auto-advance to questions phase if URL says so (and we have content)
  useEffect(() => {
    if (autoGo && rawContent.trim() && phase === 'input') {
      submit();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function reset() {
    setPhase('input');
    setResponse(null);
    setAnswers({});
    setRemovedIds(new Set());
    setFocusedKey(null);
    setLoading(false);
  }

  function changeMode(next) {
    setMode(next);
    setRawContent('');
  }

  function answerQuestion(q, option) {
    setAnswers(prev => prev[q.id] ? prev : { ...prev, [q.id]: option });
    setTimeout(() => {
      setRemovedIds(prev => {
        if (prev.has(q.id)) return prev;
        const next = new Set(prev);
        next.add(q.id);
        return next;
      });
    }, 760);
  }

  // ─── derived effect: when every question is answered, fetch directions
  useEffect(() => {
    if (phase !== 'questions') return;
    if (!response || response.questions.length === 0) return;
    const allDone = response.questions.every(q => answers[q.id]);
    if (!allDone) return;
    const t = setTimeout(async () => {
      setLoading(true);
      const res = await window.mockBackend({ mode, rawContent, answers });
      setResponse(res);
      setLoading(false);
      setPhase('directions');
    }, 820);
    return () => clearTimeout(t);
  }, [answers, response, phase, rawContent, mode]);

  function pickDirection(key) {
    setFocusedKey(key);
    setPhase('focused');
  }

  const totalQuestions = response && phase === 'questions' ? response.questions.length : 0;
  const answeredCount = Object.keys(answers).length;

  return (
    <div className={`app ${hideChrome ? 'app--bare' : ''}`}>
      {!hideChrome && <Chrome phase={phase} mode={mode} onReset={reset} loading={loading} />}
      <div className="stage">
        {phase === 'input' && (
          <InputPhase
            mode={mode}
            onModeChange={changeMode}
            value={rawContent}
            onChange={setRawContent}
            onSubmit={submit}
          />
        )}
        {phase === 'questions' && (
          <QuestionsPhase
            response={response}
            answers={answers}
            removedIds={removedIds}
            loading={loading}
            onAnswer={answerQuestion}
          />
        )}
        {phase === 'directions' && (
          <DirectionsPhase
            response={response}
            mode={mode}
            onPick={pickDirection}
            loading={loading}
          />
        )}
        {phase === 'focused' && (
          <FocusedPhase
            response={response}
            focusedKey={focusedKey}
            onBack={() => setPhase('directions')}
          />
        )}
      </div>
      <Footer
        phase={phase}
        answeredCount={answeredCount}
        totalQuestions={totalQuestions}
        hideChrome={hideChrome}
      />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
