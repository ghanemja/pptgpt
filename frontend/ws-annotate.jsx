/* ============================================================
   ws-annotate.jsx — review notes pinned to the slide they are about.

   A list of notes makes you hold the slide in your head and match "the
   third bullet hedges" to the third bullet. This draws the slide and puts
   each note beside it, with a leader line to the words that raised it —
   the way a reviewer marks up a printout.

   Where a note points comes from the ENGINE: every note carries a `target`
   naming a field of the slide's content ({field: "bullets", index: 2}).
   That is a reference, never a position. The overlay finds where the
   renderer actually put that field (SlideCard tags them `data-field`) and
   measures it, so the annotation can never disagree with the slide.

   Callouts sit in gutters either side of the slide and are stacked so they
   never overlap; when the panel is too narrow for gutters, they drop below
   the slide and the slide carries numbered markers instead of lines.
   ============================================================ */

const { useState: useAnnState, useRef: useAnnRef, useLayoutEffect: useAnnLayout } = React;

const ANN_SEV = { blocker: 'Blocker', push: 'Push back', nit: 'Nit' };
const ANN_GUTTER = 232;     // callout width
const ANN_GAP = 34;         // callout ↔ slide
const ANN_STACK = 10;       // between stacked callouts
const ANN_SPLIT_MIN = 900;  // narrower than this: callouts go below the slide
const ANN_FIELD = /^[a-zA-Z]+$/;

/* The element the renderer drew for a target, or null if it drew none. */
function annFind(root, t) {
  if (!root || !t || !ANN_FIELD.test(t.field || '') || t.field === 'slide') return null;
  if (t.field === 'bullets' && Number.isInteger(t.index)) {
    const el = root.querySelector(`[data-field="bullets"][data-index="${t.index}"]`);
    if (el) return el;
  }
  return root.querySelector(`[data-field="${t.field}"]:not([data-index])`);
}

/* Where a note's target sits, in wrapper coordinates.

   kind 'el'    — the renderer drew it; outline exactly that.
   kind 'ghost' — the note is that it is MISSING (no title, no takeaway):
                  mark the band where the slide would carry it, dashed.
   kind 'slide' — the note is about the slide as a whole. */
function annTarget(note, slideEl, wrapBox, s) {
  const t = note.target || { field: 'slide' };
  const el = t.missing ? null : annFind(slideEl, t);
  if (el) {
    const r = el.getBoundingClientRect();
    const pad = 4;
    return { kind: 'el', x: r.left - wrapBox.left - pad, y: r.top - wrapBox.top - pad,
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

/* Callouts go to the side their target is on, then the sides are evened
   out so one gutter does not become a tower while the other is empty. */
function annSides(boxes, s) {
  const mid = s.x + s.w / 2;
  const side = boxes.map(b => (b.kind === 'slide' ? null : (b.x + b.w / 2 < mid ? 'L' : 'R')));
  side.forEach((v, i) => {
    if (v) return;
    const l = side.filter(x => x === 'L').length, r = side.filter(x => x === 'R').length;
    side[i] = l <= r ? 'L' : 'R';
  });
  for (;;) {
    const l = side.filter(x => x === 'L').length, r = side.filter(x => x === 'R').length;
    if (Math.abs(l - r) < 2) break;
    const from = l > r ? 'L' : 'R';
    let best = -1, bestD = Infinity;
    side.forEach((v, i) => {
      if (v !== from) return;
      const d = Math.abs(boxes[i].x + boxes[i].w / 2 - mid);
      if (d < bestD) { bestD = d; best = i; }
    });
    side[best] = from === 'L' ? 'R' : 'L';
  }
  return side;
}

/* Each callout wants to sit level with its target; stack them so none
   overlap, pull the stack back up if it ran off the bottom of the slide. */
function annStack(items, floor) {
  const ord = items.slice().sort((a, b) => a.want - b.want);
  let prev = -Infinity;
  ord.forEach(it => { it.top = Math.max(0, it.want - it.h / 2, prev + ANN_STACK); prev = it.top + it.h; });
  let limit = floor;
  for (let j = ord.length - 1; j >= 0; j--) {
    ord[j].top = Math.min(ord[j].top, limit - ord[j].h);
    limit = ord[j].top - ANN_STACK;
  }
  prev = -Infinity;
  ord.forEach(it => { it.top = Math.max(0, it.top, prev + ANN_STACK); prev = it.top + it.h; });
  return prev === -Infinity ? 0 : prev;
}

function AnnotatedSlide({ slide, notes, onOpen }) {
  const { SlideCard, SLIDE_W, SLIDE_H } = window;
  const wrapRef = useAnnRef(null);
  const slideRef = useAnnRef(null);
  const calloutRefs = useAnnRef([]);
  const [width, setWidth] = useAnnState(0);
  const [lay, setLay] = useAnnState(null);
  const [hot, setHot] = useAnnState(-1);
  const [fontsTick, setFontsTick] = useAnnState(0);

  useAnnLayout(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    setWidth(el.getBoundingClientRect().width);
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(el);
    // Text reflows once webfonts land; the outlines have to follow it.
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => setFontsTick(t => t + 1));
    return () => ro.disconnect();
  }, []);

  const split = width >= ANN_SPLIT_MIN;
  const slideW = !width ? 0 : split ? Math.min(SLIDE_W, width - 2 * (ANN_GUTTER + ANN_GAP)) : width;
  const scale = slideW / SLIDE_W;
  const slideH = SLIDE_H * scale;
  const slideX = split ? (width - slideW) / 2 : 0;

  useAnnLayout(() => {
    const wrap = wrapRef.current, sEl = slideRef.current;
    if (!wrap || !sEl || !slideW) return;
    const wb = wrap.getBoundingClientRect();
    const s = { x: slideX, y: 0, w: slideW, h: slideH };
    const boxes = notes.map(n => annTarget(n, sEl, wb, s));

    if (!split) { setLay({ boxes, callouts: [], height: slideH }); return; }

    const side = annSides(boxes, s);
    const items = boxes.map((b, i) => ({
      i, side: side[i],
      want: b.kind === 'slide' ? s.h / 2 : b.y + b.h / 2,
      h: (calloutRefs.current[i] && calloutRefs.current[i].offsetHeight) || 80,
    }));
    const bottoms = ['L', 'R'].map(sd => annStack(items.filter(it => it.side === sd), slideH));
    const callouts = [];
    items.forEach(it => {
      const b = boxes[it.i];
      const left = it.side === 'L';
      const cx = left ? slideX - ANN_GAP - ANN_GUTTER : slideX + slideW + ANN_GAP;
      const sx = left ? cx + ANN_GUTTER : cx;                  // callout's inner edge
      const ay = b.kind === 'slide' ? Math.min(Math.max(it.top + it.h / 2, 12), slideH - 12) : b.y + b.h / 2;
      const sy = Math.min(Math.max(ay, it.top + 14), it.top + it.h - 14);
      const edge = left ? slideX - 10 : slideX + slideW + 10; // just outside the slide
      const ax = b.kind === 'slide' ? (left ? slideX : slideX + slideW) : (left ? b.x : b.x + b.w);
      callouts[it.i] = {
        side: it.side, left: cx, top: it.top,
        d: `M ${sx} ${sy} H ${edge} L ${ax} ${ay}`, ax, ay,
      };
    });
    setLay({ boxes, callouts, height: Math.max(slideH, ...bottoms) });
  }, [width, slide, notes, fontsTick]);

  const cls = sev => `ann--${ANN_SEV[sev] ? sev : 'nit'}`;
  const dim = i => (hot >= 0 && hot !== i ? ' ann--dim' : '');

  const callout = (n, i, style) => (
    <div key={i} ref={el => { calloutRefs.current[i] = el; }}
      className={`anncall ${cls(n.severity)}${dim(i)}${hot === i ? ' ann--hot' : ''}`}
      style={style}
      onMouseEnter={() => setHot(i)} onMouseLeave={() => setHot(-1)}
      onClick={onOpen} role="button" tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter' && onOpen) onOpen(); }}>
      <div className="anncall__head">
        <span className="anncall__num tnum">{i + 1}</span>
        <span className="anncall__sev">{ANN_SEV[n.severity] || n.severity}</span>
        <span className="anncall__lens">{n.lens}</span>
      </div>
      <div className="anncall__note">{n.note}</div>
      {n.ask ? <div className="anncall__ask">“{n.ask}”</div> : null}
    </div>
  );

  return (
    <div className="annwrap" ref={wrapRef}>
      <div className="annstage" style={{ height: lay ? lay.height : slideH }}>
        <div className="annslide" ref={slideRef}
          style={{ left: slideX, width: slideW, height: slideH }}>
          {slideW ? (
            <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left', width: SLIDE_W, height: SLIDE_H }}>
              <SlideCard slide={slide} />
            </div>
          ) : null}
        </div>

        {lay ? (
          <svg className="annsvg" width={width} height={lay.height} aria-hidden="true">
            {lay.boxes.map((b, i) => (b.kind === 'slide' ? null : (
              <rect key={'b' + i} className={`annbox ${cls(notes[i].severity)}${dim(i)}${b.kind === 'ghost' ? ' annbox--ghost' : ''}`}
                x={b.x} y={b.y} width={b.w} height={b.h} rx={5} />
            )))}
            {split ? lay.callouts.map((c, i) => (c ? (
              <g key={'l' + i} className={`annline ${cls(notes[i].severity)}${dim(i)}${hot === i ? ' ann--hot' : ''}`}>
                <path className="annline__halo" d={c.d} />
                <path className="annline__ink" d={c.d} />
                <circle className="annline__dot" cx={c.ax} cy={c.ay} r={3.5} />
              </g>
            ) : null)) : lay.boxes.map((b, i) => (
              <g key={'m' + i} className={`annmark ${cls(notes[i].severity)}`}>
                <circle cx={b.kind === 'slide' ? slideX + slideW - 16 - i * 22 : b.x + b.w}
                  cy={b.kind === 'slide' ? 16 : b.y} r={9} />
                <text x={b.kind === 'slide' ? slideX + slideW - 16 - i * 22 : b.x + b.w}
                  y={b.kind === 'slide' ? 16 : b.y} dy="0.35em">{i + 1}</text>
              </g>
            ))}
          </svg>
        ) : null}

        {split ? notes.map((n, i) => {
          const c = lay && lay.callouts[i];
          return callout(n, i, {
            position: 'absolute', width: ANN_GUTTER,
            left: c ? c.left : 0, top: c ? c.top : 0,
            visibility: c ? 'visible' : 'hidden',
          });
        }) : null}
      </div>

      {!split ? (
        <div className="annbelow">{notes.map((n, i) => callout(n, i, {}))}</div>
      ) : null}
    </div>
  );
}

Object.assign(window, { AnnotatedSlide });
