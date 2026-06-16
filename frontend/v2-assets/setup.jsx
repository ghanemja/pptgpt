/* ============================================================
   pptgpt — setup page (step 02 · pick the goal)
   ------------------------------------------------------------
   Collects deck title, audience, mode, optional stakes.
   Persists to sessionStorage('pptgpt.setup') and routes to
   /storyboard. Storyboard reads it on mount and merges over
   INITIAL_DECK.
   ============================================================ */

const { useState, useMemo } = React;

// Keys MUST match workbench-v2.jsx AUDIENCES so hydration picks the
// right card on /workbench mount. Labels here can be richer.
const AUDIENCES = [
  { key: 'exec',       label: 'Exec review',         tone: 'numbers-forward, sparse, decision-oriented' },
  { key: 'customer',   label: 'Customer update',     tone: 'narrative-first, visual, ends with an ask' },
  { key: 'conference', label: 'Conference talk',     tone: 'one-idea, big type, takeaway-first' },
  { key: 'status',     label: 'Status / standup',    tone: 'dense, action items with owners + dates' },
  { key: 'oneonone',   label: '1:1 tag-up',          tone: 'conversational, low polish' },
  { key: 'technical',  label: 'Technical deep-dive', tone: 'formulas, plots, citations' },
];

const MODES = [
  { key: 'draft',      label: 'Draft',      tone: 'rough notes → one styled slide, three directions' },
  { key: 'refine',     label: 'Refine',     tone: 'reworked single slide from feedback' },
  { key: 'condense',   label: 'Condense',   tone: 'full deck (--- separators) → short deck' },
  { key: 'visualize',  label: 'Visualize',  tone: '3b1b explainer with a tunable plot' },
  { key: 'synthesize', label: 'Synthesize', tone: 'a table or k:v pairs → chart slide' },
];

function Card({ active, label, tone, onClick }) {
  return (
    <button
      type="button"
      className={`setup-card ${active ? 'is-active' : ''}`}
      onClick={onClick}
    >
      <div className="setup-card__label">{label}</div>
      <div className="setup-card__tone">{tone}</div>
    </button>
  );
}

function Setup() {
  const [title, setTitle] = useState('Q3 review  ·  and what we do next');
  const [audienceKey, setAudienceKey] = useState('exec');
  const [modeKey, setModeKey] = useState('condense');
  const [stakes, setStakes] = useState('');

  const canContinue = useMemo(
    () => title.trim().length > 0 && audienceKey && modeKey,
    [title, audienceKey, modeKey]
  );

  function handleContinue() {
    const audience = AUDIENCES.find(a => a.key === audienceKey);
    const mode = MODES.find(m => m.key === modeKey);
    const payload = {
      title: title.trim(),
      audience: audience.label,
      audienceKey,
      audienceTone: audience.tone,
      mode: mode.label,
      modeKey,
      stakes: stakes.trim(),
    };
    try {
      sessionStorage.setItem('pptgpt.setup', JSON.stringify(payload));
    } catch (_) { /* private mode etc. — fall through */ }
    // Hand off to the canonical 5-phase app. Workbench reads
    // pptgpt.setup on mount and pre-selects the matching mode/audience
    // cards so the user lands on step 01 with their picks intact.
    location.href = '/workbench';
  }

  return (
    <div className="setup-page">
      <div className="setup-wrap">
        <header className="setup-head">
          <div className="setup-head__steps">
            <span className="setup-head__step">
              <span className="num">1</span> upload
            </span>
            <span className="setup-head__sep">·</span>
            <span className="setup-head__step is-active">
              <span className="num">2</span> pick
            </span>
            <span className="setup-head__sep">·</span>
            <span className="setup-head__step">
              <span className="num">3</span> storyboard
            </span>
            <span className="setup-head__sep">·</span>
            <span className="setup-head__step">
              <span className="num">4</span> workbench
            </span>
            <span className="setup-head__sep">·</span>
            <span className="setup-head__step">
              <span className="num">5</span> critique
            </span>
          </div>
          <h1 className="setup-head__title">Pick the goal.</h1>
          <p className="setup-head__sub">
            Three knobs the engine respects: who is in the room, what shape the
            material needs, what is at stake. Everything downstream — spine
            selection, recommendations, critique — is tuned by these.
          </p>
        </header>

        <div className="setup-field">
          <div className="setup-field__label">Deck title</div>
          <input
            className="setup-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Q3 review · and what we do next"
          />
        </div>

        <div className="setup-field">
          <div className="setup-field__label">Audience</div>
          <div className="setup-grid">
            {AUDIENCES.map(a => (
              <Card
                key={a.key}
                active={audienceKey === a.key}
                label={a.label}
                tone={a.tone}
                onClick={() => setAudienceKey(a.key)}
              />
            ))}
          </div>
          <div className="setup-field__hint">
            Shapes tone, density, takeaway style. Same content morphs by room.
          </div>
        </div>

        <div className="setup-field">
          <div className="setup-field__label">Mode</div>
          <div className="setup-grid">
            {MODES.map(m => (
              <Card
                key={m.key}
                active={modeKey === m.key}
                label={m.label}
                tone={m.tone}
                onClick={() => setModeKey(m.key)}
              />
            ))}
          </div>
          <div className="setup-field__hint">
            Picks the right pipeline. Pure layout invariants stay the same.
          </div>
        </div>

        <div className="setup-field">
          <div className="setup-field__label">What is at stake (optional)</div>
          <textarea
            className="setup-textarea"
            value={stakes}
            onChange={(e) => setStakes(e.target.value)}
            placeholder="e.g. board needs to greenlight headcount; we are over budget."
          />
          <div className="setup-field__hint">
            Free-text. Helps the critique panel raise the right objections.
          </div>
        </div>

        <footer className="setup-footer">
          <a className="setup-footer__back" href="/">← landing</a>
          <button
            type="button"
            className="setup-cta"
            disabled={!canContinue}
            onClick={handleContinue}
          >
            continue to workbench
            <span className="setup-cta__arrow">→</span>
          </button>
        </footer>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<Setup />);
