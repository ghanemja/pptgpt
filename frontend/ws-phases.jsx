/* ============================================================
   ws-phases.jsx — the pipeline, embedded in the workspace.

   There is one app. The old /workbench stepper (upload → pick →
   storyboard → workbench → critique) becomes four phases of the
   same deck object:

     scope    — the org’s questions. What are we even sharing?
     story    — title / three messages / bumper   (ws-story.jsx)
     visuals  — house style, direction, charts
     deck     — the fused slides + export          (ws-app.jsx)

   The questions are NOT hardcoded here. Each organization ships a
   profile under orgs/<slug>.json (see deckengine/org.py) with its
   own scoping interview, narrative arc and style rules. This file
   fetches that profile and renders it; it invents no content and,
   per R0.1, no geometry.
   ============================================================ */

const { Ico } = window;
const { useState, useEffect } = React;

/* The four phases, each owning the tools that belong to it. Create / Data /
   Refine / Condense used to sit in a parallel "Features" nav, which asked the
   user to hold two mental models at once — a workflow and a toolbox. A tool
   now lives inside the step of the workflow where you would reach for it. */
const PHASES = [
  { key: 'scope',   name: 'Scope',   icon: 'refine',  sub: 'what are we sharing', tools: [] },
  { key: 'story',   name: 'Story',   icon: 'layout',  sub: 'title · 3 messages · bumper', tools: ['condense'] },
  { key: 'visuals', name: 'Visuals', icon: 'palette', sub: 'house style · graphics', tools: ['data'] },
  { key: 'deck',    name: 'Deck',    icon: 'createx', sub: 'fuse it · export', tools: ['create', 'refine'] },
  { key: 'review',  name: 'Review',  icon: 'spark',   sub: 'who will object', tools: [] },
];

/* Which phase a tool belongs to — the inverse of PHASES[].tools. */
const TOOL_PHASE = {};
PHASES.forEach(p => (p.tools || []).forEach(t => { TOOL_PHASE[t] = p.key; }));

/* How you arrive at a deck. The scope interview is the same either way; what
   changes is what the engine is given to work from. */
const ENTRY_MODES = [
  { key: 'prompt',    name: 'From a prompt',     sub: 'describe it and answer the questions',
    blurb: 'Start from an idea. The brief you build here is what the engine writes to.' },
  { key: 'brief',     name: 'I have a brief',    sub: 'paste what you already wrote',
    blurb: 'Paste an existing brief, abstract or outline. The questions stay available to fill gaps.' },
  { key: 'materials', name: 'From material',     sub: 'point at decks, docs or a folder',
    blurb: 'Build from what already exists — past decks, a report, a folder. Needs the local engine; the hosted demo cannot read files.' },
];

/* The API origin, resolved the same way workspace-backend.js does it, so a
   static deploy with no backend still works (we fall back to the profile
   baked in below). */
const API_ORIGIN = window.WS_NO_BACKEND ? ''
  : ((window.BU_API_BASE || '').replace(/\/$/, '')
    || ((location.protocol === 'http:' || location.protocol === 'https:') ? location.origin : ''));

/* Offline fallback — mirrors orgs/default.json. The server copy is the
   source of truth; this only keeps the UI honest when there is no server. */
const FALLBACK_ORG = {
  slug: 'default', name: 'Default',
  tagline: 'Sensible questions for a deck with no house style yet.',
  scope_questions: [
    { id:'audience', prompt:'Who is in the room?', kind:'choice',
      options:['Exec','Customer','Conference','Standup'], required:true,
      why:'Sets the tone the engine writes in — numbers-forward vs narrative-first.' },
    { id:'decision', prompt:'What should they decide, do, or believe when you finish?', kind:'text',
      placeholder:'Approve the enterprise hire plan', required:true,
      why:'A deck with no ask is a status update. This becomes the closing bumper.' },
    { id:'stakes', prompt:'What happens if they say no?', kind:'text',
      placeholder:'We lose the Q1 window and the pipeline ages out',
      why:'Stakes are what make the middle of the deck matter.' },
    { id:'evidence', prompt:'What is your strongest piece of evidence?', kind:'text',
      placeholder:'Net retention 118% in the segment we want to expand',
      why:'The engine leads with this; everything else supports it.' },
    { id:'objection', prompt:'What will they push back on hardest?', kind:'text',
      placeholder:'That the churn drop is seasonal, not structural',
      why:'An unanswered objection sinks the deck in the room, not in the draft.' },
    { id:'time', prompt:'How long do you have?', kind:'choice',
      options:['5 min','15 min','30 min','Read-ahead, no meeting'],
      why:'Caps the deck length before the engine writes a slide you will cut.' },
  ],
  narrative: {
    guide:'Situation → Complication → Question → Answer',
    beats:['Situation','Complication','Question','Answer','Ask'],
    bumper_rule:'Every slide ends in one sentence that sets up the next.',
    messages_per_slide: 3,
  },
  style: {
    theme:'bolt', palette:'warm',
    rules:['One idea per slide.','At most three messages per slide.',
      'Every slide carries a title that argues, not a label.',
      'Numbers get units and a comparison.'],
    banned:['clip art','gradient fills','full-sentence bullets'],
  },
  examples: [],
};

/* ── org loading ──────────────────────────────────────────── */
function useOrg(slug, version) {
  const [orgs, setOrgs] = useState([{ slug:'default', name:'Default', tagline: FALLBACK_ORG.tagline }]);
  const [org, setOrg] = useState(FALLBACK_ORG);
  const [offline, setOffline] = useState(true);

  useEffect(() => {
    if (!API_ORIGIN) return;
    let dead = false;
    fetch(API_ORIGIN + '/api/orgs')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(d => { if (!dead && Array.isArray(d.orgs) && d.orgs.length) { setOrgs(d.orgs); setOffline(false); } })
      .catch(() => {});
    return () => { dead = true; };
  }, [version]);

  useEffect(() => {
    if (!API_ORIGIN) { setOrg(FALLBACK_ORG); return; }
    let dead = false;
    fetch(API_ORIGIN + '/api/orgs/' + encodeURIComponent(slug || 'default'))
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(d => { if (!dead && d && d.scope_questions) { setOrg(d); setOffline(false); } })
      .catch(() => { if (!dead) setOrg(FALLBACK_ORG); });
    return () => { dead = true; };
  }, [slug, version]);

  return { org, orgs, offline };
}

/* A scope answer set, rendered as the brief the engine is given. Pure
   content — it never reaches layout. */
function briefFrom(org, answers) {
  const lines = [];
  (org.scope_questions || []).forEach(q => {
    const v = (answers || {})[q.id];
    if (v && String(v).trim()) lines.push(`${q.prompt} ${String(v).trim()}`);
  });
  if (org.narrative && org.narrative.guide) lines.push(`Narrative arc: ${org.narrative.guide}.`);
  (((org.style || {}).rules) || []).forEach(r => lines.push(`House rule: ${r}`));
  return lines.join('\n');
}

function scopeProgress(org, answers) {
  const qs = org.scope_questions || [];
  const req = qs.filter(q => q.required);
  const done = qs.filter(q => ((answers || {})[q.id] || '').toString().trim()).length;
  const reqDone = req.filter(q => ((answers || {})[q.id] || '').toString().trim()).length;
  return { done, total: qs.length, reqDone, reqTotal: req.length, ready: reqDone === req.length };
}

/* ── phase rail (sidebar) ─────────────────────────────────── */
/* One nav, not two. The active phase unfolds to show its tools; picking a
   tool selects both the tool and its phase, so the two can never disagree. */
function PhaseRail({ phase, onPhase, status, feature, onTool, features, featureIcon }) {
  return (
    <nav className="rail__nav phaserail">
      {PHASES.map((p, i) => {
        const st = status[p.key] || {};
        const open = phase === p.key;
        return (
          <div key={p.key} className={`phasegroup ${open ? 'is-open' : ''}`}>
            <button className={`feat phase ${open ? 'is-active' : ''} ${st.done ? 'is-done' : ''} ${st.locked ? 'is-locked' : ''}`}
              onClick={() => onPhase(p.key)} title={st.locked ? st.why : p.sub}>
              <span className="phase__num tnum">{String(i + 1).padStart(2, '0')}</span>
              <span className="feat__txt">
                <span className="feat__title">{p.name}</span>
                <span className="phase__sub">{st.note || p.sub}</span>
              </span>
              {st.done ? <span className="phase__tick"><Ico name="check" size={13} /></span> : null}
            </button>
            {open && p.tools.length ? (
              <div className="phasetools">
                {p.tools.map(t => (
                  <button key={t} className={`ptool ${feature === t ? 'is-on' : ''}`}
                    onClick={() => onTool(t)} title={features[t].sub}>
                    <span className="ptool__ico"><Ico name={featureIcon[t]} size={14} /></span>
                    <span className="ptool__txt">{features[t].name}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}

/* ── phase 1 · scope ──────────────────────────────────────── */
/* A plausible answer for a question, taken from the profile itself: a choice
   question answers with its first option, anything else with its own
   placeholder. Nothing is invented here, so the fill works for any org's
   question set — including ones added after this was written. */
function demoAnswer(q) {
  if (q.kind === 'choice') return (q.options && q.options[0]) || '';
  return q.placeholder || '';
}

function ScopePhase({ org, orgs, orgSlug, onOrg, answers, onAnswer, onStart, offline,
                      mode, onMode, carry, onCarry, orgIsKit, onKit }) {
  const p = scopeProgress(org, answers);
  const m = mode || 'prompt';
  // Testing the pipeline means getting past this form a lot. The toggle fills
  // every question from the profile's own examples, and clears them again.
  const filled = (org.scope_questions || []).length > 0
    && (org.scope_questions || []).every(q => (answers[q.id] || '') === demoAnswer(q));
  function toggleDemo() {
    (org.scope_questions || []).forEach(q => onAnswer(q.id, filled ? '' : demoAnswer(q)));
    if (!filled && !(carry || '').trim() && m === 'prompt') {
      onCarry('We beat Q3 plan by 14% and I want two enterprise AEs for Q1.');
    }
  }
  return (
    <div className="stage__scroll stage__scroll--phase">
      <div className="phasewrap">
        <header className="phasehead">
          <div className="phasehead__eyebrow">Phase 01 · Scope</div>
          <h1 className="phasehead__h">What are we <em>sharing</em>?</h1>
          <p className="phasehead__p">
            These questions come from your organization{'’'}s profile, not from pptgpt.
            Answer what you can — the engine writes to this brief.
          </p>
          <div className="orgpick">
            <label className="orgpick__lab">Organization</label>
            <select className="orgpick__sel" value={orgSlug} onChange={e => onOrg(e.target.value)} disabled={offline}>
              {orgs.map(o => <option key={o.slug} value={o.slug}>{o.name}</option>)}
            </select>
            <span className="orgpick__tag">{org.tagline}</span>
            {offline ? <span className="orgpick__off" title="No backend reachable — showing the default profile">default profile</span> : null}
            {!offline && onKit ? (
              <button className="orgpick__kit" onClick={onKit}
                title="A company kit: your template, example decks, icons and writing voice">
                <Ico name="folder" size={13} />{orgIsKit ? 'Edit kit' : 'Set up a kit'}
              </button>
            ) : null}
            <button className={`demofill ${filled ? 'on' : ''}`} onClick={toggleDemo}
              title="Fill every question from this profile's own examples">
              {filled ? 'Clear demo' : 'Demo fill'}
            </button>
          </div>
        </header>

        <div className="modepick">
          {ENTRY_MODES.map(em => (
            <button key={em.key} className={`modecard ${m === em.key ? 'on' : ''}`} onClick={() => onMode(em.key)}>
              <span className="modecard__name">{em.name}</span>
              <span className="modecard__sub">{em.sub}</span>
            </button>
          ))}
        </div>
        <p className="modeblurb">{(ENTRY_MODES.find(e => e.key === m) || ENTRY_MODES[0]).blurb}</p>

        {m === 'prompt' ? (
          <div className="carry">
            <label className="carry__lab">What is this deck about?</label>
            <textarea className="qrow__ta" rows={3} value={carry || ''}
              placeholder="We beat Q3 plan by 14% and I want two enterprise AEs for Q1…"
              onChange={e => onCarry(e.target.value)} />
          </div>
        ) : m === 'brief' ? (
          <div className="carry">
            <label className="carry__lab">Paste the brief you already have</label>
            <textarea className="qrow__ta" rows={7} value={carry || ''}
              placeholder={'Audience: the board\nAsk: approve two enterprise AEs\nEvidence: 118% NRR, 71% of new ARR from 9% of accounts…'}
              onChange={e => onCarry(e.target.value)} />
            <div className="carry__why">Answer the questions below for anything the brief leaves implicit — they are appended, not replaced.</div>
          </div>
        ) : (
          <div className="carry">
            <label className="carry__lab">Where is the material?</label>
            <input className="qrow__in" value={carry || ''}
              placeholder="~/decks/q3-board/   or   /path/to/report.pptx"
              onChange={e => onCarry(e.target.value)} />
            <div className="carry__why">
              A folder or a file. The engine reads it for CONTENT — the facts and the story.
              Which decks it copies the FORMAT from is a house rule, set in {org.name}{'’'}s profile
              under <code>examples</code>.
            </div>
            {offline ? (
              <div className="carry__warn">
                This build has no engine behind it, so it cannot read files. Run the local server to use this mode.
              </div>
            ) : null}
          </div>
        )}

        <div className="qlist">
          {(org.scope_questions || []).map(q => {
            const v = (answers || {})[q.id] || '';
            return (
              <div key={q.id} className={`qrow ${v ? 'is-filled' : ''}`}>
                <div className="qrow__head">
                  <span className="qrow__prompt">{q.prompt}</span>
                  {q.required ? <span className="qrow__req">required</span> : null}
                </div>
                {q.kind === 'choice' ? (
                  <div className="qrow__opts">
                    {q.options.map(o => (
                      <button key={o} className={`chip ${v === o ? 'is-on' : ''}`}
                        onClick={() => onAnswer(q.id, v === o ? '' : o)}>{o}</button>
                    ))}
                  </div>
                ) : q.kind === 'longtext' ? (
                  <textarea className="qrow__ta" rows={3} value={v} placeholder={q.placeholder}
                    onChange={e => onAnswer(q.id, e.target.value)} />
                ) : (
                  <input className="qrow__in" value={v} placeholder={q.placeholder}
                    onChange={e => onAnswer(q.id, e.target.value)} />
                )}
                {q.why ? <div className="qrow__why">{q.why}</div> : null}
              </div>
            );
          })}
        </div>

        <footer className="phasefoot">
          <span className="phasefoot__count tnum">{p.done}/{p.total} answered</span>
          <button className="phasefoot__go" disabled={!p.ready} onClick={onStart}>
            {p.ready ? 'Build the storyboard' : `Answer the ${p.reqTotal - p.reqDone} required`}
            <Ico name="expand" size={15} />
          </button>
        </footer>
      </div>
    </div>
  );
}

/* ── phase 3 · visuals ────────────────────────────────────── */
function VisualsPhase({ org, themes, theme, onTheme, palettes, palette, onPalette, deck,
                       template, onTemplate, onTemplateRemove }) {
  const style = org.style || {};
  const offStyle = style.theme && theme !== style.theme;
  const TemplatePanel = window.TemplatePanel;
  return (
    <div className="stage__scroll stage__scroll--phase">
      <div className="phasewrap">
        <header className="phasehead">
          <div className="phasehead__eyebrow">Phase 03 · Visuals</div>
          <h1 className="phasehead__h">Dress it in the <em>house style</em></h1>
          <p className="phasehead__p">
            Direction changes the palette and type, never the geometry — the engine
            resolves boxes the same way in every theme.
          </p>
        </header>

        <section className="vsec">
          <h2 className="vsec__h">Template
            <span className="vsec__sub">your own .pptx — its master, background and logo carry through</span>
          </h2>
          {TemplatePanel ? (
            <TemplatePanel appliedId={template ? template.id : null}
              onApply={onTemplate} onRemove={onTemplateRemove} />
          ) : null}
          {template ? (
            <div className="vnote">
              Drawing onto <b>{template.name}</b>. The engine still resolves every box inside
              its margins — the template supplies the brand and the backdrop, never a position.
            </div>
          ) : null}
        </section>

        <section className="vsec">
          <h2 className="vsec__h">Theme</h2>
          <div className="themegrid">
            {themes.map(t => (
              <button key={t.key} className={`themecard ${theme === t.key ? 'on' : ''}`} onClick={() => onTheme(t.key)}>
                <span className="themecard__dots">{t.dots.map((d, i) => <i key={i} style={{ background: d }} />)}</span>
                <span className="themecard__name">{t.name}
                  {style.theme === t.key ? <span className="themecard__house">house</span> : null}</span>
                <span className="themecard__desc">{t.desc}</span>
              </button>
            ))}
          </div>
          {offStyle ? (
            <div className="vnote">
              {org.name} ships <b>{style.theme}</b> as its house theme. You{'’'}re off-style — fine for a draft, flagged for a review.
            </div>
          ) : null}
        </section>

        <section className="vsec">
          <h2 className="vsec__h">Direction <span className="vsec__sub">applies to all {deck.slides.length} slides</span></h2>
          <div className="dirgrid">
            {Object.values(palettes).map(p => (
              <button key={p.key} className={`dircard ${palette === p.key ? 'on' : ''}`} onClick={() => onPalette(p.key)}>
                <span className="dircard__sw" style={{ background: p.swatch }} />
                <span className="dircard__name">{p.label}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="vsec vsec--split">
          <div>
            <h2 className="vsec__h">House rules</h2>
            <ul className="rulelist">
              {(style.rules || []).map((r, i) => <li key={i}>{r}</li>)}
              {!(style.rules || []).length ? <li className="rulelist__none">No rules in this profile.</li> : null}
            </ul>
          </div>
          <div>
            <h2 className="vsec__h">Never</h2>
            <ul className="rulelist rulelist--no">
              {(style.banned || []).map((b, i) => <li key={i}>{b}</li>)}
              {!(style.banned || []).length ? <li className="rulelist__none">Nothing banned.</li> : null}
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
}

/* ── empty states for phases that need a deck ─────────────── */
function PhaseEmpty({ title, body, cta, onCta }) {
  return (
    <div className="stage__scroll stage__scroll--init">
      <div className="init">
        <div className="init__ico"><Ico name="layout" size={26} /></div>
        <div className="init__eyebrow">Nothing to show yet</div>
        <h1 className="init__h">{title}</h1>
        <p className="init__p">{body}</p>
        <div className="init__samples"><button className="chip" onClick={onCta}>{cta}</button></div>
      </div>
    </div>
  );
}

Object.assign(window, {
  PHASES, TOOL_PHASE, ENTRY_MODES, PhaseRail, ScopePhase, VisualsPhase, PhaseEmpty,
  useOrg, briefFrom, scopeProgress, FALLBACK_ORG,
});
