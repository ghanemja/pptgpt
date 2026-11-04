/* ============================================================
   ws-app.jsx — pptgpt unified workspace
   One live deck object shared across Create / Refine / Condense.
   Working slide on top, Claude-style composer at the bottom;
   taste questions, palette directions and export all fold into
   the composer's coach line as chips.
   ============================================================ */

const { useState, useEffect, useRef, useCallback, useLayoutEffect } = React;
const { SLIDE_W, SLIDE_H, PALETTES, AUDIENCES, FEATURES, FEATURE_ICON, Ico, SlideCard, aiGenerate, uid, Storyboard } = window;
const { PHASES, PhaseRail, ScopePhase, VisualsPhase, PhaseEmpty, useOrg, briefFrom, scopeProgress, TOOL_PHASE } = window;

const LS_KEY = (typeof window !== 'undefined' && window.WS_LS_KEY) || 'pptgpt-ws-v2';
const FEATURE_ORDER = ['create', 'data', 'refine', 'condense'];

const THEMES = [
  { key:'bolt',   name:'Bolt',   desc:'Neo-brutalist pop · hard shadows · grotesk',    dots:['#FFD23F','#2F49FF','#FF3D7F','#131313'] },
  { key:'atlas',  name:'Atlas',  desc:'Editorial paper · oxblood · serif display',   dots:['#F4EEE1','#9C3B1C','#C67D2E','#1C1712'] },
  { key:'signal', name:'Signal', desc:'Blueprint · electric blue · mono labels',      dots:['#E9EDF1','#1458C8','#0A9BAE','#0F1720'] },
  { key:'ember',  name:'Ember',  desc:'Warm noir · amber on charcoal',                dots:['#16130E','#E2892E','#E7C24A','#F3ECDC'] },
  { key:'vivid',  name:'Vivid',  desc:'Bold pop · electric indigo · grotesk',         dots:['#F7F5FE','#5B2DE0','#EF2F7D','#16111F'] },
];

/* A slide the user has asked for but not yet described. Shared by the stage
   (which must say so) and by generation (which fills it in place). */
function isBlankSlide(s) {
  if (!s) return false;
  return !(s.title || '').trim()
    && !(s.takeaway || '').trim()
    && !(s.metric || '').trim()
    && !(s.bullets || []).filter(b => String(b).trim()).length
    && !s.chart && !s.plot;
}

/* ── scaled slide helpers ─────────────────────────────────── */
function useBox() {
  const ref = useRef(null);
  const last = useRef({ w: 0, h: 0 });
  const [box, setBox] = useState({ w: 860, h: 400 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0, ro = null;
    const reobserve = () => { if (ro && ref.current) ro.observe(ref.current); };
    const apply = () => {
      if (!ref.current) return;
      const w = ref.current.clientWidth, h = ref.current.clientHeight;
      if (Math.abs(w - last.current.w) >= 1 || Math.abs(h - last.current.h) >= 1) {
        last.current = { w, h };
        // stop observing across the state-driven relayout, then resume next
        // frame — prevents the "ResizeObserver loop" notification entirely
        if (ro) ro.disconnect();
        setBox({ w, h });
        requestAnimationFrame(reobserve);
      }
    };
    const schedule = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(apply); };
    apply();
    ro = new ResizeObserver(schedule);
    ro.observe(el);
    window.addEventListener('resize', schedule);
    return () => { cancelAnimationFrame(raf); if (ro) ro.disconnect(); window.removeEventListener('resize', schedule); };
  }, []);
  return [ref, box];
}

/* A thumbnail shows the same picture the stage does. With a template that
   means the exact render — the filmstrip showing the HTML approximation
   while the stage showed the real slide was the same inconsistency, just
   smaller. The render is shared, so a thumbnail costs nothing once the
   stage has asked for it. */
function Thumb({ slide, w, template }) {
  const scale = w / SLIDE_W;
  const h = SLIDE_H * scale;
  const html = (
    <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left', width: SLIDE_W, height: SLIDE_H }}>
      <SlideCard slide={slide} />
    </div>
  );
  if (template && window.ExactThumb) {
    return (
      <div style={{ width: w, height: h, overflow: 'hidden', position: 'relative' }}>
        <window.ExactThumb slide={slide} templateId={template.id} width={w} height={h}>
          {html}
        </window.ExactThumb>
      </div>
    );
  }
  return (
    <div style={{ width: w, height: h, overflow: 'hidden', position: 'relative' }}>
      {html}
    </div>
  );
}

/* ── sidebar ──────────────────────────────────────────────── */
function Sidebar({ collapsed, onCollapse, feature, onFeature, decks, deckId, onPickSlide, onSwitch, onNew, audience, phase, onPhase, phaseStatus, template }) {
  return (
    <aside className="rail">
      <div className="rail__top">
        <button className="brand" onClick={onCollapse} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          <span className="brand__mark" /><span className="brand__name">pptgpt</span>
        </button>
        <button className="rail__collapse" onClick={onCollapse} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          <Ico name={collapsed ? 'expand' : 'collapse'} size={16} />
        </button>
      </div>

      <button className="rail__new" onClick={onNew}>
        <Ico name="new" size={16} /><span>New deck</span>
      </button>

      {/* One nav. The pipeline is the app, and each phase carries the tools
         you would reach for inside it — Condense in Story, Data in Visuals,
         Create and Refine in Deck. */}
      <div className="rail__label"><span>Pipeline</span></div>
      <PhaseRail
        phase={phase} onPhase={onPhase} status={phaseStatus}
        feature={feature} onTool={onFeature}
        features={FEATURES} featureIcon={FEATURE_ICON}
      />

      <div className="rail__tray">
        <div className="tray__head">
          <span className="tray__title">Decks</span>
          <span className="tray__count">{decks.length}</span>
        </div>
        <div className="deckcard-list">
          {decks.map(d => (
            <button key={d.id} className={`deckcard ${d.id === deckId ? 'is-active' : ''}`} onClick={() => onSwitch(d.id)}>
              <span className="deckcard__thumb">{d.slides[0]
                ? <Thumb slide={d.slides[0]} w={54} template={template} />
                : <span className="deckcard__thumb-empty"><Ico name="new" size={14} /></span>}</span>
              <span className="deckcard__meta">
                <span className="deckcard__name">{d.title || 'Untitled deck'}</span>
                <span className="deckcard__count">{d.slides.length} {d.slides.length === 1 ? 'slide' : 'slides'}</span>
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="rail__foot">
        <span className="avatar">JG</span>
        <span className="rail__foot-txt">
          <span className="rail__foot-name">Jane G.</span>
          <span className="rail__foot-sub">Pro workspace</span>
        </span>
      </div>
    </aside>
  );
}

/* ── audience dropdown ────────────────────────────────────── */
function AudienceDD({ audience, onPick, open, setOpen, down }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open, setOpen]);
  const cur = AUDIENCES.find(a => a.key === audience) || AUDIENCES[0];
  return (
    <div className="dd" ref={ref}>
      {down ? (
        <button className="aud-pill" onClick={() => setOpen(o => !o)}>
          <span className="aud-pill__cap">Room</span>
          <span className="aud-pill__dot" style={{ background: cur.color }} />
          {cur.label}<Ico name="chevron" size={13} />
        </button>
      ) : (
        <button className="box__aud" onClick={() => setOpen(o => !o)}>
          <span className="dot" style={{ background: cur.color }} />{cur.label}<Ico name="chevron" size={13} />
        </button>
      )}
      {open && (
        <div className={`dd__menu ${down ? 'dd__menu--down' : ''}`}>
          {AUDIENCES.map(a => (
            <button key={a.key} className={`dd__item ${a.key === audience ? 'is-active' : ''}`} onClick={() => { onPick(a.key); setOpen(false); }}>
              <span className="dd__item-dot" style={{ background: a.color }} />
              <span>
                <span className="dd__item-name">{a.label}</span>
                <span className="dd__item-sub">{a.tone.split(';')[0].split(',').slice(0, 2).join(', ')}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── theme switcher ───────────────────────────────────────── */
function ThemeSwitcher({ theme, onPick }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);
  const cur = THEMES.find(t => t.key === theme) || THEMES[0];
  return (
    <div className="theme-dd" ref={ref}>
      <button className="theme-btn" onClick={() => setOpen(o => !o)} title="Switch theme">
        <span className="theme-btn__sw">{cur.dots.slice(0, 3).map((c, i) => <i key={i} style={{ background: c }} />)}</span>
        {cur.name}<Ico name="chevron" size={13} />
      </button>
      {open && (
        <div className="theme-menu">
          {THEMES.map(t => (
            <button key={t.key} className={`theme-item ${t.key === theme ? 'is-active' : ''}`} onClick={() => { onPick(t.key); setOpen(false); }}>
              <span className="theme-swatch">{t.dots.map((c, i) => <b key={i} style={{ background: c }} />)}</span>
              <span className="theme-item__txt">
                <span className="theme-item__name">{t.name}{t.key === theme && <Ico name="check" size={14} />}</span>
                <span className="theme-item__desc">{t.desc}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── export menu ──────────────────────────────────────────── */
function ExportMenu({ deck, feature, onExport, onGoto }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);
  const others = FEATURE_ORDER.filter(f => f !== feature);
  const empty = deck.slides.length === 0;
  return (
    <div className="export-wrap" ref={ref}>
      <button className="btn-export" disabled={empty} onClick={() => setOpen(o => !o)}>
        <Ico name="download" size={16} />Export<Ico name="chevron" size={13} />
      </button>
      {open && (
        <div className="menu">
          <div className="menu__group-label">Download</div>
          <button className="menu__item" onClick={() => { onExport('pptx'); setOpen(false); }}>
            <Ico name="doc" size={16} />PowerPoint<small>.pptx</small>
          </button>
          <button className="menu__item" onClick={() => { onExport('pdf'); setOpen(false); }}>
            <Ico name="doc" size={16} />PDF<small>.pdf</small>
          </button>
          <div className="menu__sep" />
          <div className="menu__group-label">Send to feature</div>
          {others.map(o => (
            <button key={o} className="menu__item" onClick={() => { onGoto(o); setOpen(false); }}>
              <Ico name={FEATURE_ICON[o]} size={16} />{FEATURES[o].name}<small>carry the deck</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── init / empty state (shared by every feature) ────────── */
function InitState({ feature, onSample }) {
  const f = FEATURES[feature];
  return (
    <div className="init">
      <div className="init__ico"><Ico name={FEATURE_ICON[feature]} size={26} /></div>
      <div className="init__eyebrow">{f.initEyebrow}</div>
      <h1 className="init__h">{f.initH[0]}<em>{f.initH[1]}</em>{f.initH[2]}</h1>
      <p className="init__p">{f.initP}</p>
      <div className="init__samples">
        {f.samples.map(s => <button key={s} className="chip" onClick={() => onSample(s)}>{s}</button>)}
      </div>
    </div>
  );
}

function ThinkingSlide() {
  return (
    <div className="slide-frame">
      <div className="thinking-slide">
        <div className="shim eyebrow" />
        <div className="shim title" />
        <div className="shim big" />
        <div className="shim line a" /><div className="shim line b" /><div className="shim line c" />
      </div>
    </div>
  );
}

/* ── working area ─────────────────────────────────────────── */
function Work({ deck, loading, feature, onSample, onPickSlide, onPrev, onNext, onAdd, pulseId, template }) {
  const [boxRef, box] = useBox();
  const active = deck.slides.find(s => s.id === deck.activeId);
  const idx = deck.slides.findIndex(s => s.id === deck.activeId);
  const atFirst = idx <= 0;
  const atLast = idx === deck.slides.length - 1;

  // Arrows (2x36) + their gaps (2x10) + the view's own padding (2x12), and
  // vertically the caption strip. Tight on purpose: this is the slide, and it
  // should read at the size a .pptx editor shows one.
  const availW = Math.max(220, box.w - 2 * 36 - 2 * 10 - 24);
  const availH = Math.max(150, box.h - 24 - 30);
  const scale = Math.max(0.3, Math.min(availW / SLIDE_W, availH / SLIDE_H, 2.2));

  const showInit = !loading && deck.slides.length === 0;

  if (showInit) {
    return <div className="stage__scroll stage__scroll--init"><InitState feature={feature} onSample={onSample} /></div>;
  }

  return (
    <div className="stage__scroll stage__scroll--card">
      <div className="stagecard">
        <div className="stagecard__view" ref={boxRef}>
          <div className="stagecard__stage">
            <button className="navarrow" onClick={onPrev} disabled={atFirst || loading} title="Previous slide">
              <Ico name="collapse" size={20} />
            </button>

            <div className="stagecard__slide">
              {/* A blank slide renders as the template's empty master, which
                  reads as finished rather than as waiting for you. Say what
                  it wants instead. */}
              {!loading && active && isBlankSlide(active) ? (
                <div className="blankslide" style={{ width: SLIDE_W * scale, height: SLIDE_H * scale }}>
                  <div className="blankslide__num tnum">{String(idx + 1).padStart(2, '0')}</div>
                  <div className="blankslide__h">Describe this slide</div>
                  <p className="blankslide__p">
                    Type what it should say below — a result, a takeaway, a messy list.
                    It fills this slide in place.
                  </p>
                  <div className="blankslide__chips">
                    {FEATURES[feature].samples.slice(0, 2).map(sample => (
                      <button key={sample} className="chip" onClick={() => onSample(sample)}>{sample}</button>
                    ))}
                  </div>
                </div>
              ) : loading && !active ? <ThinkingSlide /> : active && (
                <div className={`slide-frame ${pulseId === active.id ? 'is-updating' : ''}`} key={active.id + pulseId}
                     style={{ width: SLIDE_W * scale, height: SLIDE_H * scale }}>
                  {/* On a template, show the slide as it actually exports —
                      the HTML card can only approximate it. */}
                  {template && window.ExactSlide ? (
                    <window.ExactSlide slide={active} templateId={template.id}
                      width={SLIDE_W * scale} height={SLIDE_H * scale}>
                      <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left', width: SLIDE_W, height: SLIDE_H }}>
                        <SlideCard slide={active} />
                      </div>
                    </window.ExactSlide>
                  ) : (
                    <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left', width: SLIDE_W, height: SLIDE_H }}>
                      <SlideCard slide={active} />
                    </div>
                  )}
                </div>
              )}
            </div>

            <button className={`navarrow ${atLast ? 'navarrow--add' : ''}`}
              onClick={atLast ? onAdd : onNext} disabled={loading}
              title={atLast ? 'Add a slide' : 'Next slide'}>
              <Ico name={atLast ? 'new' : 'expand'} size={20} />
            </button>
          </div>

          {active && (
            <div className="slide-cap">
              <span>{FEATURES[feature].name}</span><span className="dot" />
              <span className="tnum">{idx + 1} / {deck.slides.length}</span><span className="dot" />
              <span>{active.kind} slide</span><span className="dot" />
              <span>{(PALETTES[active.palette] || PALETTES.warm).label} · 16:9</span>
              {loading && <><span className="dot" /><span>updating…</span></>}
            </div>
          )}
        </div>
        <div className="stagecard__rail">
          {deck.slides.map((s, i) => (
            <button key={s.id} className={`railthumb ${s.id === deck.activeId ? 'on' : ''}`} onClick={() => onPickSlide(s.id)}>
              <span className="railthumb__num">{String(i + 1).padStart(2, '0')}</span>
              <span className="railthumb__thumb"><Thumb slide={s} w={104} template={template} /></span>
            </button>
          ))}
          <button className="railthumb railthumb--add" onClick={onAdd} title="Add a slide">
            <Ico name="new" size={18} /><span>Add slide</span>
          </button>
        </div>

      </div>
    </div>
  );
}

/* ── coach (guidance + chips above composer) ──────────────── */
function coachContent(stage, feature, active, deck) {
  const others = FEATURE_ORDER.filter(f => f !== feature);
  if (stage === 'taste') {
    return {
      text: <>Nice draft. Should the <b>number</b> lead the eye, or the <b>story</b>?</>,
      chips: [
        { label: 'Number leads', accent: active && active.emphasis !== 'story', act: { type: 'emphasis', v: 'number' } },
        { label: 'Story leads', accent: active && active.emphasis === 'story', act: { type: 'emphasis', v: 'story' } },
        { label: 'Looks good', act: { type: 'skip' } },
      ],
    };
  }
  if (stage === 'count') {
    return {
      text: <>Kept the spine — <b>{deck.slides.length} slides</b>. Tighter, or give it room?</>,
      chips: [
        { label: 'Tight · 3 slides', act: { type: 'count', v: 3 } },
        { label: 'Room · 5 slides', act: { type: 'count', v: 5 } },
      ],
    };
  }
  if (stage === 'direction') {
    return {
      text: <>Now the <b>direction</b> — same content, three palettes. It applies to the whole deck.</>,
      chips: Object.values(PALETTES).map(p => ({
        label: p.label, sw: p.swatch, accent: deck.slides.every(s => s.palette === p.key),
        act: { type: 'palette', v: p.key },
      })),
    };
  }
  if (stage === 'refine') {
    return {
      text: <>You{'’'}re on slide {deck.slides.findIndex(s => s.id === deck.activeId) + 1}. What feels off? Type a note, or:</>,
      chips: [
        { label: 'Pull the takeaway up', act: { type: 'send', text: 'The takeaway is buried — pull it up front.' } },
        { label: 'Sharpen the title', act: { type: 'send', text: 'The title is generic — make it argue the point.' } },
        { label: 'Cut to one idea', act: { type: 'send', text: 'Too dense — cut it to one idea.' } },
      ],
    };
  }
  if (stage === 'next') {
    return {
      text: <>Looks sharp. <b>Export</b> it — or hand the deck to another feature.</>,
      chips: [
        { label: 'Download .pptx', act: { type: 'export', v: 'pptx' } },
        { label: 'Download .pdf', act: { type: 'export', v: 'pdf' } },
        ...others.map(o => ({ label: `Send to ${FEATURES[o].name}`, act: { type: 'goto', v: o } })),
      ],
    };
  }
  return null;
}

function Coach({ stage, feature, active, deck, onChip, onHistory, hasHistory }) {
  const c = coachContent(stage, feature, active, deck);
  if (!c) return null;
  return (
    <div className="coach">
      <div className="coach__row">
        <span className="coach__ava">p</span>
        <div className="coach__body">
          <div className="coach__text">{c.text}</div>
          <div className="coach__chips">
            {c.chips.map((chip, i) => (
              <button key={i} className={`qchip ${chip.accent ? 'is-accent' : ''}`} onClick={() => onChip(chip.act)}>
                {chip.sw && <span className="qchip__sw" style={{ background: chip.sw }} />}
                {chip.label}
              </button>
            ))}
            {hasHistory && <button className="coach__more" onClick={onHistory}><Ico name="up" size={13} /> conversation</button>}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── composer ─────────────────────────────────────────────── */
function Composer({ feature, draft, setDraft, files, setFiles, audience, setAudience, onSend, loading, showPresets, onPreset, coach, compact }) {
  const [audOpen, setAudOpen] = useState(false);
  const taRef = useRef(null);
  useEffect(() => {
    const ta = taRef.current; if (!ta) return;
    ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 168) + 'px';
  }, [draft]);

  const f = FEATURES[feature];
  function key(e) { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); onSend(); } }
  function pick(e) {
    const picked = Array.from(e.target.files || []); if (!picked.length) return;
    setFiles(prev => [...prev, ...picked]); e.target.value = '';
  }
  function ext(n) { const m = String(n).match(/\.([^.]+)$/); return m ? m[1].slice(0, 4).toUpperCase() : 'FILE'; }
  const canSend = (draft.trim() || files.length) && !loading;

  // storyboard mode: collapse to just the Adjustments bar (which carries the view toggle)
  if (compact) {
    return (
      <div className="composer composer--compact">
        <div className="composer__inner">
          <div className="box box--baronly">{coach}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="composer">
      <div className="composer__inner">
        <div className="box">
          {coach}
          <textarea ref={taRef} value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={key}
            placeholder={f.placeholder} rows={1} />
          {files.length > 0 && (
            <div className="file-chips">
              {files.map((fl, i) => (
                <span key={i} className="file-chip">
                  <span className="file-chip__ico">{ext(fl.name)}</span>{fl.name}
                  <button className="file-chip__x" onClick={() => setFiles(prev => prev.filter((_, x) => x !== i))}>×</button>
                </span>
              ))}
            </div>
          )}
          <div className="box__row">
            <label className="box__btn"><Ico name="attach" size={16} />Attach
              <input type="file" multiple hidden accept=".pdf,.pptx,.docx,.csv,.xlsx,.png,.jpg,.svg,.txt,.md,.json" onChange={pick} />
            </label>
            <AudienceDD audience={audience} onPick={setAudience} open={audOpen} setOpen={setAudOpen} />
            <span className="box__spacer" />
            <span className="box__hint"><kbd>⌘</kbd> <kbd>↵</kbd></span>
            <button className="send" disabled={!canSend} onClick={onSend} title="Send">
              {loading ? <span style={{ fontSize: 15 }}>…</span> : <Ico name="send" size={17} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── history sheet ────────────────────────────────────────── */
function History({ chat, onClose }) {
  const scRef = useRef(null);
  useEffect(() => { if (scRef.current) scRef.current.scrollTop = scRef.current.scrollHeight; }, []);
  return (
    <div className="history">
      <div className="history__head">
        <span className="history__title">Conversation</span>
        <button className="rail__collapse" onClick={onClose}><Ico name="close" size={16} /></button>
      </div>
      <div className="history__scroll" ref={scRef}>
        <div className="history__inner">
          {chat.length === 0 && <div className="tray__empty">No messages yet.</div>}
          {chat.map((m, i) => (
            <div key={i} className={`msg msg--${m.role}`}>
              <span className="msg__ava">{m.role === 'user' ? 'JG' : 'p'}</span>
              <div className="msg__text">{m.text}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── toasts ───────────────────────────────────────────────── */
function Toasts({ items }) {
  return (
    <div className="toasts">
      {items.map(t => <div key={t.id} className="toast"><Ico name="check" size={16} />{t.text}</div>)}
    </div>
  );
}

/* ── app ──────────────────────────────────────────────────── */
function loadState() {
  try {
    const s = JSON.parse(localStorage.getItem(LS_KEY));
    if (s && (Array.isArray(s.decks) || (s.deck && Array.isArray(s.deck.slides)))) return s;
  } catch (e) {}
  return null;
}

function App() {
  const saved = loadState() || (typeof window !== 'undefined' && window.WS_SEED) || null;
  const [collapsed, setCollapsed] = useState(false);
  const [feature, setFeature] = useState(saved ? saved.feature : 'create');
  const [audience, setAudience] = useState(saved ? saved.audience : 'exec');
  const [theme, setTheme] = useState(saved && saved.theme ? saved.theme : 'bolt');
  const initDecks = (saved && Array.isArray(saved.decks) && saved.decks.length)
    ? saved.decks
    : (saved && saved.deck ? [{ id: saved.deck.id || 'd1', ...saved.deck }] : [{ id: 'd1', title: 'Untitled deck', slides: [], activeId: null }]);
  const initDeckId = (saved && saved.deckId) || initDecks[0].id;
  const initDeck = initDecks.find(d => d.id === initDeckId) || initDecks[0];
  const [decks, setDecks] = useState(initDecks);
  const [deckId, setDeckId] = useState(initDeckId);
  const [chat, setChat] = useState(saved ? saved.chat || [] : []);
  const [coachStage, setCoachStage] = useState(initDeck.slides.length ? 'next' : null);
  const [topAudOpen, setTopAudOpen] = useState(false);

  const [draft, setDraft] = useState('');
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [pulseId, setPulseId] = useState(null);
  const [dynCats, setDynCats] = useState([]);
  const [flash, setFlash] = useState([]);
  const [dashOpen, setDashOpen] = useState(false);
  const [dashNotify, setDashNotify] = useState(false);
  // One pipeline, four views of the same deck: scope -> story -> visuals -> deck.
  const [phase, setPhase] = useState(saved && saved.phase ? saved.phase : 'scope');
  const [orgSlug, setOrgSlug] = useState(saved && saved.orgSlug ? saved.orgSlug : 'default');
  const [scope, setScope] = useState(saved && saved.scope ? saved.scope : {});
  const { org, orgs, offline: orgOffline } = useOrg(orgSlug);
  const [advDismissed, setAdvDismissed] = useState([]);
  // The applied template: brand + constraints for this deck. Persisted with
  // the deck state so a reload keeps drawing onto the same master.
  const [template, setTemplate] = useState(saved && saved.template ? saved.template : null);

  const deck = decks.find(d => d.id === deckId) || decks[0];
  function setDeck(updater) {
    setDecks(prev => prev.map(d => d.id === deckId ? (typeof updater === 'function' ? updater(d) : updater) : d));
  }
  const active = deck.slides.find(s => s.id === deck.activeId) || null;

  // persist
  useEffect(() => {
    try { localStorage.setItem(LS_KEY, JSON.stringify({ feature, audience, theme, decks, deckId, chat, phase, orgSlug, scope, template })); } catch (e) {}
  }, [feature, audience, theme, decks, deckId, chat, phase, orgSlug, scope, template]);

  // apply theme to the document so fixed elements (toasts) inherit it too
  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); }, [theme]);

  function toast(text) {
    const id = uid();
    setToasts(t => [...t, { id, text }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 2600);
  }
  function pushChat(role, text) { setChat(c => [...c, { role, text }]); }
  function pulse(id) { setPulseId(id); setTimeout(() => setPulseId(null), 650); }

  // ── storyboard: drag pieces / trim / advisories ─────────
  function moveMessage(fromSid, fromIdx, toSid, toIdx) {
    setDeck(prev => {
      const slides = prev.slides.map(s => ({ ...s, bullets: (s.bullets || []).slice() }));
      const from = slides.find(s => s.id === fromSid), to = slides.find(s => s.id === toSid);
      if (!from || !to || fromIdx >= from.bullets.length) return prev;
      const [msg] = from.bullets.splice(fromIdx, 1);
      if (msg == null) return prev;
      let insert = toIdx;
      if (fromSid === toSid && toIdx > fromIdx) insert -= 1;
      insert = Math.max(0, Math.min(to.bullets.length, insert));
      to.bullets.splice(insert, 0, msg);
      to.bullets = to.bullets.slice(0, 4);
      return { ...prev, slides };
    });
  }
  function reorderByTitle(fromSid, toSid) {
    setDeck(prev => {
      const slides = prev.slides.slice();
      const fi = slides.findIndex(s => s.id === fromSid);
      if (fi < 0) return prev;
      const [it] = slides.splice(fi, 1);
      const dest = slides.findIndex(s => s.id === toSid);
      if (dest < 0) return prev;
      slides.splice(dest, 0, it);
      return { ...prev, slides };
    });
  }
  function swapBumper(fromSid, toSid) {
    setDeck(prev => {
      const a = prev.slides.find(s => s.id === fromSid), b = prev.slides.find(s => s.id === toSid);
      if (!a || !b) return prev;
      const slides = prev.slides.map(s => s.id === fromSid ? { ...s, takeaway: b.takeaway }
        : s.id === toSid ? { ...s, takeaway: a.takeaway } : s);
      return { ...prev, slides };
    });
    toast('Swapped the bumpers.');
  }
  function trimSlide(id) {
    setDeck(prev => {
      if (prev.slides.length <= 1) return prev;
      const i = prev.slides.findIndex(s => s.id === id);
      const slides = prev.slides.filter(s => s.id !== id);
      const activeId = prev.activeId === id ? slides[Math.max(0, i - 1)].id : prev.activeId;
      return { ...prev, slides, activeId };
    });
    toast('Trimmed a beat from the deck.');
  }
  function acceptAdvisory(adv) {
    setDeck(prev => adv.apply(prev));
    setAdvDismissed(d => [...d, adv.id]);
    setDashNotify(true);
    toast(`${adv.kind} applied · ${adv.accept.toLowerCase()}`);
    pushChat('assistant', `${adv.kind}: ${adv.accept.toLowerCase()}. Reshaped the deck — review it on the board.`);
  }
  function dismissAdvisory(adv) { setAdvDismissed(d => [...d, adv.id]); }

  function stepSlide(dir) {
    setDeck(prev => {
      if (!prev.slides.length) return prev;
      const i = prev.slides.findIndex(s => s.id === prev.activeId);
      const ni = Math.max(0, Math.min(prev.slides.length - 1, i + dir));
      return { ...prev, activeId: prev.slides[ni].id };
    });
  }

  const doSend = useCallback(async (override, toolOverride) => {
    // `feature` here is the closure's value. A caller that calls setFeature
    // and sends in the same tick would read the stale one, so it passes the
    // tool explicitly instead.
    const tool = toolOverride || feature;
    const text = (override != null ? override : draft).trim();
    if ((!text && files.length === 0) || loading) return;
    const label = text || `Draft from ${files.map(f => f.name).join(', ')}`;
    pushChat('user', label);
    setDraft(''); const usedFiles = files; setFiles([]);
    setLoading(true); setCoachStage(null); setHistoryOpen(false);

    const { patch, touched } = window.parseStylePatch(text);
    const dcActive = active ? window.dynamicCats(text, active) : [];
    const isAdjust = !!active && (touched.length > 0 || dcActive.length > 0)
      && /\b(change|make|set|use|bigger|smaller|larger|font|size|colou?r|palette|bold|clean|minimal|tighter|denser|spacious|roomy|align|centre|center|story|number|metric|swap|switch|increase|decrease|pt|point)\b/i.test(text)
      && text.length < 140;

    // ── pure adjustment: edit the current slide, don't generate a new one
    if (isAdjust) {
      setDeck(prev => {
        let slides = prev.slides.map(s => s.id === prev.activeId ? { ...s,
          ...(patch.font ? { font: patch.font } : {}),
          ...(patch.fontPt ? { fontPt: patch.fontPt } : {}),
          ...(patch.emphasis ? { emphasis: patch.emphasis } : {}) } : s);
        if (patch.palette) slides = slides.map(s => ({ ...s, palette: patch.palette }));
        return { ...prev, slides };
      });
      if (dcActive.length) setDynCats(prev => { const byId = {}; [...prev, ...dcActive].forEach(c => { byId[c.id] = c; }); return Object.values(byId); });
      const fIds = [...touched, ...dcActive.map(c => c.id)];
      if (fIds.length) { setFlash(fIds); setTimeout(() => setFlash([]), 1800); }
      setDashNotify(true);
      setLoading(false); setCoachStage('next');
      pushChat('assistant', 'Applied it — see the highlighted adjustment below.');
      if (active) pulse(active.id);
      return;
    }

    const deckPalette = deck.slides.length ? deck.slides[0].palette : 'warm';
    const result = await aiGenerate({ feature: tool, prompt: text, audience, files: usedFiles, current: active, palette: deckPalette });

    let newActiveId;
    setDeck(prev => {
      let slides, activeId;
      if (tool === 'condense') {
        slides = Array.isArray(result) ? result : [result]; activeId = slides[0].id;
      } else if (tool === 'refine' && active) {
        slides = prev.slides.map(s => s.id === result.id ? result : s); activeId = result.id;
      } else if (isBlankSlide(active)) {
        // The user asked for a slide, then said what it is. One slide.
        slides = prev.slides.map(s => (s.id === active.id ? { ...result, id: active.id } : s));
        activeId = active.id;
      } else {
        slides = [...prev.slides, result]; activeId = result.id;
      }
      const applyPatch = s => ({ ...s,
        ...(patch.font ? { font: patch.font } : {}),
        ...(patch.fontPt ? { fontPt: patch.fontPt } : {}),
        ...(patch.emphasis ? { emphasis: patch.emphasis } : {}) });
      slides = slides.map(s => s.id === activeId ? applyPatch(s) : s);
      if (patch.palette) slides = slides.map(s => ({ ...s, palette: patch.palette }));
      newActiveId = activeId;
      return { ...prev, slides, activeId };
    });

    const nslide = Array.isArray(result) ? result[0] : result;
    const dc = window.dynamicCats(text, { ...nslide, ...patch });
    if (dc.length) setDynCats(prev => { const byId = {}; [...prev, ...dc].forEach(c => { byId[c.id] = c; }); return Object.values(byId); });
    const flashIds = [...touched, ...dc.map(c => c.id)];
    if (tool === 'refine') flashIds.push('content');
    if (flashIds.length) { setFlash(flashIds); setTimeout(() => setFlash([]), 1800); }
    setDashNotify(true);

    setLoading(false); setCoachStage('next');
    // A tool run from Visuals produces a slide, and a slide is shown in Deck.
    // Condense stays put: its output IS the board you are already looking at.
    if (phase === 'visuals') setPhase('deck');
    pushChat('assistant', tool === 'condense' ? 'Condensed to the spine — review the adjustments below.'
      : tool === 'data' ? 'Charted it. Tune the chart or styles below.'
      : tool === 'refine' ? 'Reworked it — your changes are itemized below.'
      : 'Drafted a slide. Adjust anything below.');
    pulse(newActiveId);
  }, [draft, files, loading, feature, audience, active, deck, phase]);

  function applyControl(catId, ctrlId, value) {
    if (ctrlId === 'palette') {
      setDeck(prev => ({ ...prev, slides: prev.slides.map(s => ({ ...s, palette: value })) }));
      if (active) pulse(active.id);
    } else if (ctrlId === 'length') {
      setDeck(prev => { const slides = prev.slides.slice(0, parseInt(value, 10)); return { ...prev, slides, activeId: slides.some(s => s.id === prev.activeId) ? prev.activeId : slides[0].id }; });
    } else if (['title', 'takeaway', 'font', 'fontPt', 'emphasis'].includes(ctrlId)) {
      setDeck(prev => ({ ...prev, slides: prev.slides.map(s => s.id === prev.activeId ? { ...s, [ctrlId]: value } : s) }));
      if (active && ctrlId !== 'title' && ctrlId !== 'takeaway') pulse(active.id);
    } else {
      // an AI-generated (dynamic) control — remember its value
      setDynCats(prev => prev.map(c => c.id === catId ? { ...c, controls: c.controls.map(ct => ct.id === ctrlId ? { ...ct, value } : ct) } : c));
    }
  }

  function applyChip(act) {
    if (act.type === 'emphasis') {
      setDeck(prev => ({ ...prev, slides: prev.slides.map(s => s.id === prev.activeId ? { ...s, emphasis: act.v } : s) }));
      pushChat('assistant', act.v === 'story' ? 'Story leads now — the headline and takeaway carry it.' : 'Number leads — the hero stat anchors the slide.');
      if (active) pulse(active.id);
      setCoachStage('direction');
    } else if (act.type === 'skip') {
      setCoachStage('direction');
    } else if (act.type === 'count') {
      setDeck(prev => {
        let slides = prev.slides.slice(0, act.v);
        return { ...prev, slides, activeId: slides.some(s => s.id === prev.activeId) ? prev.activeId : slides[0].id };
      });
      pushChat('assistant', `Trimmed to ${act.v} slides.`);
      setCoachStage('direction');
    } else if (act.type === 'palette') {
      setDeck(prev => ({ ...prev, slides: prev.slides.map(s => ({ ...s, palette: act.v })) }));
      pushChat('assistant', `Applied the ${PALETTES[act.v].label} direction across the deck.`);
      if (active) pulse(active.id);
      setCoachStage('next');
    } else if (act.type === 'export') {
      doExport(act.v);
    } else if (act.type === 'goto') {
      gotoFeature(act.v, true);
    } else if (act.type === 'send') {
      doSend(act.text);
    }
  }

  function doExport(fmt) {
    if (fmt === 'pptx' && window.exportPptx) {
      window.exportPptx(deck.slides, template ? template.id : null)
        .then(() => {
          toast(`Exported ${deck.title || 'deck'} · ${deck.slides.length} slides · .pptx`);
          pushChat('assistant', `Exported the deck as .pptx (${deck.slides.length} slides).`);
        })
        .catch(() => {
          toast('Export failed — check the server logs.');
        });
      setCoachStage('next');
      return;
    }
    toast(`Exported ${deck.title || 'deck'} · ${deck.slides.length} slides · .${fmt}`);
    pushChat('assistant', `Exported the deck as .${fmt} (${deck.slides.length} slides).`);
    setCoachStage('next');
  }

  function gotoFeature(next, fromChip, keepPhase) {
    setFeature(next);
    setHistoryOpen(false);
    // A tool belongs to a phase; selecting one moves you there.
    if (!keepPhase && TOOL_PHASE[next]) setPhase(TOOL_PHASE[next]);
    if (deck.slides.length === 0) { setCoachStage(null); return; }
    if (next === 'refine') { setCoachStage('refine'); if (fromChip) pushChat('assistant', 'Moved the deck into Refine. Tell me what feels off.'); }
    else if (next === 'condense') { setCoachStage(deck.slides.length > 1 ? 'count' : null); if (fromChip) pushChat('assistant', 'Moved into Condense — paste more, or tune the spine.'); }
    else { setCoachStage('next'); if (fromChip) pushChat('assistant', 'Back in Create. Add another slide, or export.'); }
  }

  // "Add slide" adds a real blank slide and selects it; the next generation
  // fills that slide in place rather than appending a second one (doSend).
  function addBlankSlide() {
    const id = uid();
    const palette = template ? 'template' : deckPalette;
    setDeck(prev => ({
      ...prev,
      slides: [...prev.slides, {
        id, kind: 'text', palette,
        emphasis: audience === 'conf' ? 'story' : 'number',
        eyebrow: '', title: '', bullets: [], takeaway: '',
      }],
      activeId: id,
    }));
    setPhase('deck');
    gotoFeature('create', false, true);
    setCoachStage(null);
    // Put the cursor where the answer goes.
    setTimeout(() => {
      const ta = document.querySelector('.composer textarea');
      if (ta) ta.focus();
    }, 60);
    return id;
  }

  function newDeck() {
    const d = { id: uid(), title: 'Untitled deck', slides: [], activeId: null };
    setDecks(prev => [...prev, d]); setDeckId(d.id);
    setChat([]); setCoachStage(null); setFeature('create'); setDraft(''); setFiles([]);
    setDynCats([]); setFlash([]); setPhase('scope'); setAdvDismissed([]);
  }

  function switchDeck(id) {
    if (id === deckId) return;
    setDeckId(id); setCoachStage('next'); setDynCats([]); setFlash([]); setHistoryOpen(false); setDraft(''); setAdvDismissed([]);
  }

  const dashCats = active ? [
    ...window.baselineCats(active, feature),
    ...(feature === 'condense' && deck.slides.length > 1
      ? [{ id:'length', label:'Deck length', icon:'condense', controls:[{ id:'length', label:'Slides', type:'select', options:['3','4','5'], value: String(deck.slides.length) }] }]
      : []),
    ...dynCats,
  ] : [];

  const hasSlides = deck.slides.length > 0;

  // ── scope answers live on the deck: a brief belongs to its deck ──
  const scopeAnswers = scope[deckId] || {};
  // `__mode` and `__carry` are scope state, not answers: how the user arrived
  // (prompt / existing brief / existing material) and what they brought with
  // them. Underscored so they never collide with an org's question ids.
  const scopeMode = scopeAnswers.__mode || 'prompt';
  const scopeCarry = scopeAnswers.__carry || '';
  function setScopeMeta(key, value) {
    setScope(prev => ({ ...prev, [deckId]: { ...(prev[deckId] || {}), [key]: value } }));
  }
  function setScopeAnswer(qid, value) {
    setScope(prev => ({ ...prev, [deckId]: { ...(prev[deckId] || {}), [qid]: value } }));
    // the audience question drives the engine's tone, so keep them in sync
    if (qid === 'audience' && value) {
      const hit = AUDIENCES.find(a => a.label.toLowerCase() === String(value).toLowerCase());
      if (hit) setAudience(hit.key);
    }
  }
  // Scope hands off to Story, not to Deck. The brief becomes a SPINE — a few
  // beats with titles, messages and bumpers — which is what phase 02 is for.
  // Condense is the tool that turns prose into a spine, so that is what runs.
  function startFromBrief() {
    const answered = briefFrom(org, scopeAnswers);
    const carried = (scopeCarry || '').trim();
    const lead = !carried ? ''
      : scopeMode === 'materials' ? `Build from the material at: ${carried}\n`
      : `${carried}\n`;
    const brief = lead + answered;
    if (scopeMode === 'materials' && !window.exportPptx) {
      toast('Reading files needs the local engine — drafting from the brief instead.');
    }
    setFeature('condense');
    setPhase('story');
    setCoachStage(null);
    setDraft('');
    doSend(brief, 'condense');
  }

  const deckPalette = deck.slides.length ? deck.slides[0].palette : (org.style && org.style.palette) || 'warm';

  // A template's colours become a palette the preview can render, so the
  // screen matches what exports. Registered on PALETTES because SlideCard
  // looks palettes up by key; it is a translation of the template's theme,
  // not a design decision of the UI's (R0.3).
  //
  // Done during render, NOT in an effect: slides restored from localStorage
  // already carry palette 'template', and an effect runs after the first
  // paint — which rendered those slides against a palette that did not exist
  // yet.
  if (template && window.paletteFromTemplate) {
    PALETTES.template = window.paletteFromTemplate(template);
  } else if (PALETTES.template) {
    delete PALETTES.template;
  }

  // A template profile is persisted with the deck, so a stored one can be
  // older than the engine that reads it — missing the sampled background, or
  // naming a template since deleted. Re-fetch it once on load and take the
  // server's answer; drop it if the template is gone.
  useEffect(() => {
    if (!template || !template.id || window.WS_NO_BACKEND) return;
    const origin = (window.BU_API_BASE || '').replace(/\/$/, '') || location.origin;
    let dead = false;
    fetch(`${origin}/api/templates/${template.id}`)
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(fresh => { if (!dead && fresh && fresh.id) setTemplate(fresh); })
      .catch(status => {
        if (dead) return;
        if (status === 404) { removeTemplate(); toast('That template is no longer on the server.'); }
      });
    return () => { dead = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [template && template.id]);

  function applyTemplate(tpl) {
    if (!tpl || !tpl.id) return;
    PALETTES.template = window.paletteFromTemplate(tpl);
    setTemplate(tpl);
    setDeck(prev => ({ ...prev, slides: prev.slides.map(sl => ({ ...sl, palette: 'template' })) }));
    toast(`Applied ${tpl.name} — exports draw onto its master.`);
    pushChat('assistant', `Applied the ${tpl.name} template. Same slides, your brand and backdrop.`);
  }

  function removeTemplate() {
    const back = (org.style && org.style.palette) || 'warm';
    setTemplate(null);
    setDeck(prev => ({ ...prev, slides: prev.slides.map(sl => (sl.palette === 'template' ? { ...sl, palette: back } : sl)) }));
    toast('Removed the template.');
  }

  const sp = scopeProgress(org, scopeAnswers);  // meta keys are ignored: it walks org.scope_questions
  // The pipeline runs in order. A phase is locked until the thing it works on
  // exists — there is no storyboard to arrange before a spine is written, and
  // nothing to dress or export before that. `why` is what the lock says when
  // you click it, so a locked step teaches instead of just refusing.
  const phaseStatus = {
    scope: {
      done: sp.ready,
      note: sp.done ? `${sp.done}/${sp.total} answered` : null,
    },
    story: {
      done: deck.slides.length > 1,
      note: hasSlides ? `${deck.slides.length} beat${deck.slides.length === 1 ? '' : 's'}` : null,
      locked: !hasSlides && !sp.ready,
      why: 'Answer the required questions first — the storyboard is written from that brief.',
    },
    visuals: {
      done: hasSlides && deck.slides.every(sl => sl.palette === deckPalette),
      note: null,
      locked: !hasSlides,
      why: 'Nothing to dress yet. Build the storyboard first.',
    },
    deck: {
      done: hasSlides,
      note: hasSlides ? `${deck.slides.length} slide${deck.slides.length === 1 ? '' : 's'}` : null,
      locked: !hasSlides,
      why: 'No slides yet. Build the storyboard first, then fuse it here.',
    },
  };

  // Clicking a locked step does not silently refuse: if its input can be
  // produced, produce it. From Scope with a ready brief, "go to Deck" means
  // "run the chain" — write the spine, then land where you asked.
  function goPhase(next) {
    const st = phaseStatus[next] || {};
    if (!st.locked) { setPhase(next); return; }
    if (sp.ready && !hasSlides) {
      toast(`Building the storyboard first — ${PHASES.find(p => p.key === next).name} needs it.`);
      startFromBrief();
      return;
    }
    setPhase('scope');
    toast(st.why || 'Earlier steps first.');
  }

  const advisories = (deck.slides.length > 1 && window.buildAdvisories ? window.buildAdvisories(deck) : [])
    .filter(a => !advDismissed.includes(a.id));
  const hasDeck = hasSlides;

  return (
    <div className={`ws ${collapsed ? 'is-collapsed' : ''}`}>
      <Sidebar
        collapsed={collapsed} onCollapse={() => setCollapsed(c => !c)}
        feature={feature} onFeature={f => gotoFeature(f, false)}
        onPhase={goPhase}
        decks={decks} deckId={deckId} onPickSlide={id => setDeck(p => ({ ...p, activeId: id }))}
        onSwitch={switchDeck} onNew={newDeck} audience={audience}
        phase={phase} phaseStatus={phaseStatus} template={template}
      />
      <div className="main">
        <div className="topbar">
          <div className="topbar__feat">
            <span className="topbar__feat-ico"><Ico name={FEATURE_ICON[feature]} size={16} /></span>
            <span className="topbar__feat-name">{FEATURES[feature].name}</span>
          </div>
          <div className="topbar__deck">
            <input className="topbar__deck-title" value={deck.title}
              onChange={e => setDeck(p => ({ ...p, title: e.target.value }))} spellCheck={false} />
          </div>
          <span className="topbar__spacer" />
          <ThemeSwitcher theme={theme} onPick={setTheme} />
          <ExportMenu deck={deck} feature={feature} onExport={doExport} onGoto={o => gotoFeature(o, true)} />
        </div>

        <div className="stage">
          {phase === 'scope' ? (
            <ScopePhase
              org={org} orgs={orgs} orgSlug={orgSlug} onOrg={setOrgSlug} offline={orgOffline}
              answers={scopeAnswers} onAnswer={setScopeAnswer} onStart={startFromBrief}
              mode={scopeMode} onMode={v => setScopeMeta('__mode', v)}
              carry={scopeCarry} onCarry={v => setScopeMeta('__carry', v)}
            />
          ) : phase === 'visuals' ? (
            <VisualsPhase
              org={org} themes={THEMES} theme={theme} onTheme={setTheme}
              palettes={PALETTES} palette={deckPalette} deck={deck}
              template={template} onTemplate={applyTemplate} onTemplateRemove={removeTemplate}
              onPalette={v => {
                setDeck(prev => ({ ...prev, slides: prev.slides.map(sl => ({ ...sl, palette: v })) }));
                if (deck.slides.length) toast(`Applied the ${PALETTES[v].label} direction.`);
              }}
            />
          ) : phase === 'story' && !hasDeck && !loading ? (
            <PhaseEmpty
              title={<>No beats to <em>board</em> yet</>}
              body="The storyboard opens up a deck you already have — titles, three messages each, and the bumper that hands off to the next slide."
              cta="Start from the brief" onCta={() => setPhase('scope')}
            />
          ) : hasDeck && phase === 'story' && !loading ? (
            <Storyboard
              deck={deck} feature={feature}
              onPick={id => setDeck(p => ({ ...p, activeId: id }))}
              onOpen={id => { setDeck(p => ({ ...p, activeId: id })); setPhase('deck'); }}
              onMoveMessage={moveMessage}
              onReorderByTitle={reorderByTitle}
              onSwapBumper={swapBumper}
              onTrim={trimSlide}
              onAdd={addBlankSlide}
              advisories={advisories}
              onAccept={acceptAdvisory} onDismiss={dismissAdvisory}
            />
          ) : (
            <Work
              deck={deck} loading={loading} feature={feature}
              onSample={s => { setDraft(s); }}
              onPickSlide={id => setDeck(p => ({ ...p, activeId: id }))}
              onPrev={() => stepSlide(-1)}
              onNext={() => stepSlide(1)}
              onAdd={addBlankSlide}
              pulseId={pulseId} template={template}
            />
          )}
        </div>

        {/* Scope is a form, not a conversation. Every other phase owns at
            least one tool that takes text, so the composer stays. */}
        {phase === 'scope' ? null : <Composer
          feature={feature} draft={draft} setDraft={setDraft} files={files} setFiles={setFiles}
          audience={audience} setAudience={setAudience} onSend={() => doSend()} loading={loading}
          showPresets={false} onPreset={s => setDraft(s)}
          compact={hasDeck && phase === 'story'}
          coach={active ? <Dashboard
            cats={dashCats} flash={flash} onControl={applyControl} onAction={applyChip}
            feature={feature} samples={FEATURES[feature].samples} onPreset={s => setDraft(s)}
            open={dashOpen} notify={dashNotify}
            onToggle={() => setDashOpen(o => { if (!o) setDashNotify(false); return !o; })}
            stageView={hasDeck ? (phase === 'story' ? 'storyboard' : 'slide') : null}
            onStageView={v => setPhase(v === 'storyboard' ? 'story' : 'deck')} advCount={advisories.length}
          /> : null}
        />}
      </div>
      <Toasts items={toasts} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
