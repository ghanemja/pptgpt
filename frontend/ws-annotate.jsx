/* ============================================================
   ws-annotate.jsx — the review, one slide at a time, as a checklist.

   A review is worked through, not read once: you open a slide, fix what
   the critic raised, tick it off, move on. So the report is laid out the
   way the Deck phase is — the slide in place, arrows either side, the
   caption underneath — with the notes for that slide as a checklist on
   the right. Each note's target is outlined and numbered on the slide;
   the note you are on draws a leader line from the words that raised it
   to its line in the checklist.

   Where a note points comes from the ENGINE: every note carries a `target`
   naming a field of the slide's content ({field: "bullets", index: 2}).
   That is a reference, never a position. The overlay finds where the
   renderer actually put that field (SlideCard tags them `data-field`) and
   measures it, so an annotation can never disagree with the slide.

   Ticks are the viewer's own progress, kept in this browser only.
   ============================================================ */

const {
  useState: useAnnState, useRef: useAnnRef,
  useLayoutEffect: useAnnLayout, useEffect: useAnnEffect,
} = React;

const ANN_SEV = { blocker: 'Blocker', push: 'Push back', nit: 'Nit' };
const ANN_CHECK_W = 340;    // checklist panel
const ANN_SPLIT_MIN = 900;  // narrower than this: checklist goes below the slide
const ANN_FIELD = /^[a-zA-Z]+$/;
const ANN_DONE_KEY = 'pptgpt-review-done';

/* The element the renderer drew for a target, or null if it drew none. */
function annFind(root, t) {
  if (!root || !t || !ANN_FIELD.test(t.field || '') || t.field === 'slide') return null;
  if (t.field === 'bullets' && Number.isInteger(t.index)) {
    const el = root.querySelector(`[data-field="bullets"][data-index="${t.index}"]`);
    if (el) return el;
  }
  return root.querySelector(`[data-field="${t.field}"]:not([data-index])`);
}

/* Where a note's target sits, in root coordinates.

   kind 'el'    — the renderer drew it; outline exactly that.
   kind 'ghost' — the note is that it is MISSING (no title, no takeaway):
                  mark the band where the slide would carry it, dashed.
   kind 'slide' — the note is about the slide as a whole. */
function annTarget(note, slideEl, rootBox, s) {
  const t = note.target || { field: 'slide' };
  const el = t.missing ? null : annFind(slideEl, t);
  if (el) {
    const r = el.getBoundingClientRect();
    const pad = 4;
    return { kind: 'el', x: r.left - rootBox.left - pad, y: r.top - rootBox.top - pad,
             w: r.width + pad * 2, h: r.height + pad * 2 };
  }
  if (t.field === 'title') {
    return { kind: 'ghost', x: s.x + s.w * 0.06, y: s.y + s.h * 0.11, w: s.w * 0.62, h: s.h * 0.13 };
  }
  if (t.field === 'takeaway') {
    return { kind: 'ghost', x: s.x + s.w * 0.06, y: s.y + s.h * 0.8, w: s.w * 0.88, h: s.h * 0.1 };
  }
  return { kind: 'slide', x: s.x, y: s.y, w: s.w, h: s.h };
}

function annKey(slideId, n) { return `${slideId}|${n.lens}|${n.note}`; }

function useDone() {
  const [done, setDone] = useAnnState(() => {
    try { return JSON.parse(localStorage.getItem(ANN_DONE_KEY)) || {}; } catch (e) { return {}; }
  });
  function toggle(key) {
    setDone(prev => {
      const next = { ...prev };
      if (next[key]) delete next[key]; else next[key] = 1;
      try { localStorage.setItem(ANN_DONE_KEY, JSON.stringify(next)); } catch (e) {}
      return next;
    });
  }
  return [done, toggle];
}

function ReviewStage({ deck, results, onOpenSlide }) {
  const { SlideCard, SLIDE_W, SLIDE_H, Ico } = window;
  const rootRef = useAnnRef(null);
  const slideRef = useAnnRef(null);
  const itemRefs = useAnnRef([]);
  const [width, setWidth] = useAnnState(0);
  const [layRaw, setLay] = useAnnState(null);
  const [hot, setHot] = useAnnState(-1);       // hovered note
  const [sel, setSel] = useAnnState(0);        // note the line is drawn for
  const [fontsTick, setFontsTick] = useAnnState(0);
  const [done, toggleDone] = useDone();

  // Open on the first slide that has something to fix.
  const [idx, setIdx] = useAnnState(() => {
    const i = results.findIndex(r => r.notes.length);
    return i < 0 ? 0 : i;
  });
  const n = results.length;
  const r = results[Math.min(idx, n - 1)];
  const slide = r && deck.slides[r.index];
  const notes = (r && r.notes) || [];
  const slideId = (slide && slide.id) || (r && r.slideId);
  const go = d => { setIdx(i => Math.max(0, Math.min(n - 1, i + d))); setSel(0); setHot(-1); };

  useAnnEffect(() => {
    function key(e) {
      const t = e.target;
      // Arrows still page while a checkbox has focus (you just ticked one),
      // but never steal them from somewhere text is being typed.
      if (t && t.closest && t.closest('textarea, select, [contenteditable="true"], input:not([type="checkbox"])')) return;
      if (e.key === 'ArrowLeft') go(-1);
      else if (e.key === 'ArrowRight') go(1);
    }
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [n]);

  useAnnLayout(() => {
    const el = rootRef.current;
    if (!el) return undefined;
    setWidth(el.getBoundingClientRect().width);
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(el);
    // Text reflows once webfonts land; the outlines have to follow it.
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => setFontsTick(t => t + 1));
    return () => ro.disconnect();
  }, []);

  const split = width >= ANN_SPLIT_MIN;
  const viewW = split ? width - ANN_CHECK_W - 24 : width;
  const availW = Math.max(220, viewW - 2 * 44 - 2 * 10 - 8);
  const scale = Math.min(availW / SLIDE_W, 1.3);
  const slideW = SLIDE_W * scale, slideH = SLIDE_H * scale;

  useAnnLayout(() => {
    const root = rootRef.current, sEl = slideRef.current;
    if (!root || !sEl || !width) return;
    const rb = root.getBoundingClientRect();
    const sb = sEl.getBoundingClientRect();
    const s = { x: sb.left - rb.left, y: sb.top - rb.top, w: sb.width, h: sb.height };
    const boxes = notes.map(nt => annTarget(nt, sEl, rb, s));
    const items = itemRefs.current.slice(0, notes.length).map(it => {
      if (!it) return null;
      const b = it.getBoundingClientRect();
      return { x: b.left - rb.left, y: b.top - rb.top + 20 };
    });
    setLay({ idx, s, boxes, items });
  }, [width, idx, slide, notes, fontsTick, done]);

  // A layout measured for the previous slide is never drawn over this one:
  // paging renders once before the overlay is re-measured.
  const lay = layRaw && layRaw.idx === idx && layRaw.boxes.length === notes.length ? layRaw : null;

  // The marker sits on the target's top-right corner; a whole-slide note
  // queues its markers along the slide's top edge instead.
  // Two notes about the same words share one outline, so their markers
  // step left along its top edge rather than sitting on top of each other.
  const marker = (b, i) => {
    if (b.kind === 'slide') return { x: lay.s.x + lay.s.w - 16 - i * 22, y: lay.s.y + 16 };
    const same = lay.boxes.slice(0, i).filter(o => o.kind !== 'slide'
      && Math.abs(o.x - b.x) < 1 && Math.abs(o.y - b.y) < 1).length;
    return { x: b.x + b.w - same * 22, y: b.y };
  };

  const line = i => {
    if (!lay || !split || i < 0 || !lay.boxes[i] || !lay.items[i]) return null;
    const b = lay.boxes[i], it = lay.items[i];
    const ay = b.kind === 'slide' ? lay.s.y + lay.s.h / 2 : b.y + b.h / 2;
    const ax = b.kind === 'slide' ? lay.s.x + lay.s.w : b.x + b.w;
    const edge = lay.s.x + lay.s.w + 6;                 // just outside the slide
    const ix = it.x - 6;
    const mid = edge + Math.max(12, (ix - edge) / 2);
    return `M ${ax} ${ay} H ${edge} C ${mid} ${ay}, ${mid} ${it.y}, ${ix} ${it.y}`;
  };
  const active = hot >= 0 ? hot : (sel < notes.length ? sel : -1);
  const cls = sev => `ann--${ANN_SEV[sev] ? sev : 'nit'}`;

  const doneHere = notes.filter(nt => done[annKey(slideId, nt)]).length;
  const totalAll = results.reduce((a, x) => a + x.notes.length, 0);
  const doneAll = results.reduce((a, x) => {
    const sid = (deck.slides[x.index] && deck.slides[x.index].id) || x.slideId;
    return a + x.notes.filter(nt => done[annKey(sid, nt)]).length;
  }, 0);

  if (!r || !slide) return null;

  return (
    <div className={`revstage ${split ? '' : 'revstage--stacked'}`} ref={rootRef}>
      <div className="revstage__view">
        <div className="stagecard__stage">
          <button className="navarrow" onClick={() => go(-1)} disabled={idx === 0} title="Previous slide (←)">
            <Ico name="collapse" size={20} />
          </button>
          <div className="slide-frame" ref={slideRef} style={{ width: slideW, height: slideH }}>
            <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left', width: SLIDE_W, height: SLIDE_H }}>
              <SlideCard slide={slide} />
            </div>
          </div>
          <button className="navarrow" onClick={() => go(1)} disabled={idx >= n - 1} title="Next slide (→)">
            <Ico name="expand" size={20} />
          </button>
        </div>

        <div className="slide-cap">
          <span>Review</span><span className="dot" />
          <span className="tnum">{idx + 1} / {n}</span><span className="dot" />
          <span>{slide.kind || 'text'} slide</span><span className="dot" />
          <span>{notes.length ? `${notes.length} note${notes.length === 1 ? '' : 's'}` : 'holds up'}</span>
        </div>

        <div className="revdots" role="tablist" aria-label="Slides">
          {results.map((x, i) => {
            const sid = (deck.slides[x.index] && deck.slides[x.index].id) || x.slideId;
            const left = x.notes.filter(nt => !done[annKey(sid, nt)]).length;
            return (
              <button key={sid || i} role="tab" aria-selected={i === idx}
                className={`revdot revdot--${x.notes.length && !left ? 'done' : x.verdict} ${i === idx ? 'on' : ''}`}
                onClick={() => { setIdx(i); setSel(0); setHot(-1); }}
                title={`Slide ${i + 1}: ${x.notes.length ? `${left} of ${x.notes.length} left` : 'clear'}`}>
                <span className="tnum">{i + 1}</span>
              </button>
            );
          })}
        </div>
      </div>

      <aside className="revcheck">
        <div className="revcheck__head">
          <div className="revcheck__eyebrow tnum">Slide {String(idx + 1).padStart(2, '0')}</div>
          <div className="revcheck__title">{slide.title || 'Untitled slide'}</div>
          <div className="revcheck__meta">
            <span className="tnum">{notes.length ? `${doneHere} of ${notes.length} done` : 'Nothing to fix'}</span>
            <button className="revcheck__open" onClick={() => onOpenSlide(r.slideId)}>
              Edit slide <Ico name="expand" size={12} />
            </button>
          </div>
          {notes.length ? (
            <div className="revcheck__bar"><span style={{ width: `${(doneHere / notes.length) * 100}%` }} /></div>
          ) : null}
        </div>

        {notes.length ? (
          <ol className="revcheck__list">
            {notes.map((nt, i) => {
              const k = annKey(slideId, nt);
              const isDone = !!done[k];
              return (
                <li key={k} ref={el => { itemRefs.current[i] = el; }}
                  className={`checkitem ${cls(nt.severity)} ${isDone ? 'is-done' : ''} ${active === i ? 'is-active' : ''}`}
                  onMouseEnter={() => setHot(i)} onMouseLeave={() => setHot(-1)}
                  onClick={() => setSel(i)}>
                  <label className="checkitem__box" onClick={e => e.stopPropagation()}>
                    <input type="checkbox" checked={isDone} onChange={() => toggleDone(k)}
                      aria-label={`Mark note ${i + 1} done`} />
                    <span aria-hidden="true" />
                  </label>
                  <div className="checkitem__body">
                    <div className="checkitem__head">
                      <span className="checkitem__num tnum">{i + 1}</span>
                      <span className="checkitem__sev">{ANN_SEV[nt.severity] || nt.severity}</span>
                      <span className="checkitem__lens">{nt.lens}</span>
                    </div>
                    <div className="checkitem__note">{nt.note}</div>
                    {nt.ask ? <div className="checkitem__ask">“{nt.ask}”</div> : null}
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <div className="revcheck__clear">This slide holds up for this critic.</div>
        )}

        <div className="revcheck__foot tnum">
          {totalAll ? `${doneAll} of ${totalAll} done across the deck` : 'The deck holds up.'}
          {idx < n - 1 ? (
            <button className="revcheck__next" onClick={() => go(1)}>
              Next slide <Ico name="expand" size={12} />
            </button>
          ) : null}
        </div>
      </aside>

      {lay ? (
        <svg className="annsvg" width={width} height="100%" aria-hidden="true">
          {lay.boxes.map((b, i) => {
            const isDone = !!done[annKey(slideId, notes[i])];
            const st = `${cls(notes[i].severity)}${isDone ? ' ann--done' : ''}${active === i ? ' ann--hot' : active >= 0 && hot >= 0 ? ' ann--dim' : ''}`;
            const m = marker(b, i);
            return (
              <g key={i}>
                {b.kind === 'slide' ? null : (
                  <rect className={`annbox ${st}${b.kind === 'ghost' ? ' annbox--ghost' : ''}`}
                    x={b.x} y={b.y} width={b.w} height={b.h} rx={5} />
                )}
                <g className={`annmark ${st}`}>
                  <circle cx={m.x} cy={m.y} r={9} />
                  <text x={m.x} y={m.y} dy="0.35em">{isDone ? '✓' : i + 1}</text>
                </g>
              </g>
            );
          })}
          {line(active) ? (
            <g className={`annline ${cls(notes[active].severity)}`}>
              <path className="annline__halo" d={line(active)} />
              <path className="annline__ink" d={line(active)} />
            </g>
          ) : null}
        </svg>
      ) : null}
    </div>
  );
}

Object.assign(window, { ReviewStage });
