/* ============================================================
   ws-story.jsx — the Storyboard view (deck-shape mode)
   ------------------------------------------------------------
   The same live deck, opened up as WIRES: every slide is a
   column of draggable pieces — a TITLE, up to three MESSAGES,
   and a BUMPER (the line that hands off to the next slide).
   Drag messages within a slide or across slides, reorder whole
   slides by their title, swap bumpers. The AI reads the deck's
   narrative flow: each bumper -> next title handoff is scored
   strong / soft / broken, and structural advisories (merge /
   order / thin) surface at the top.
   ============================================================ */

const { Ico } = window;

/* ── vocabulary helpers ───────────────────────────────────── */
const STOP = new Set(('the a an and or of to in on for with at by is are be we our you your it its this that '
  + 'as from into over under up down out about across every their his her they them not no yes '
  + 'has have had will more most less than then now new deck slide today lets let'
  + ' one two three four every').split(/\s+/).filter(Boolean));

function words(s) {
  return String(s || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/)
    .filter(w => w.length > 3 && !STOP.has(w));
}
function wset(s) { return new Set(words(s)); }
function overlap(aStr, bStr) {
  const a = wset(aStr); let n = 0;
  for (const w of new Set(words(bStr))) if (a.has(w)) n++;
  return n;
}

/* ── per-slide pieces ─────────────────────────────────────── */
function slideRole(slide) {
  if (slide.kind === 'cover') return { key: 'open', label: 'Opening' };
  if (slide.kind === 'chart' || slide.kind === 'plot') return { key: 'data', label: 'Evidence' };
  if (slide.emphasis === 'story') return { key: 'turn', label: 'Story' };
  if (slide.metric) return { key: 'proof', label: 'Proof' };
  return { key: 'point', label: 'Point' };
}
function slideMessages(slide) {
  const m = (slide.bullets || []).slice();
  if (!m.length && slide.metric) m.push(`${slide.metric} — ${slide.metricSub || 'headline number'}`);
  if (!m.length && slide.subtitle) m.push(slide.subtitle);
  return m;
}

/* ── narrative flow analysis ──────────────────────────────── */
/* handoff strength between slide a's bumper and slide b's opening */
function handoff(a, b) {
  if (!a || !b) return { level: 'none', n: 0 };
  const from = a.takeaway || '';
  const to = [b.title, ...slideMessages(b)].join(' ');
  if (!from.trim()) return { level: a.kind === 'cover' ? 'none' : 'broken', n: 0 };
  const n = overlap(from, to);
  return { level: n >= 2 ? 'strong' : n === 1 ? 'soft' : 'broken', n };
}
function analyzeFlow(deck) {
  const s = deck.slides;
  const links = [];
  for (let i = 0; i < s.length - 1; i++) links.push({ i, ...handoff(s[i], s[i + 1]) });
  const scored = links.filter(l => l.level !== 'none');
  const strong = scored.filter(l => l.level === 'strong').length;
  const soft = scored.filter(l => l.level === 'soft').length;
  const broken = scored.filter(l => l.level === 'broken').length;
  // longest run of consecutive connected handoffs (the "thread")
  let run = 1, best = 1;
  links.forEach(l => { if (l.level === 'strong' || l.level === 'soft') { run++; best = Math.max(best, run); } else run = 1; });
  const thread = Math.min(best, s.length);
  let read;
  if (!links.length) read = 'A single slide — nothing to hand off yet.';
  else if (broken === 0 && soft <= 1) read = `The thread holds — ${strong} clean handoff${strong === 1 ? '' : 's'} carry the deck end to end.`;
  else if (broken > 0) read = `${broken} handoff${broken === 1 ? '' : 's'} ${broken === 1 ? 'breaks' : 'break'} the thread — a bumper doesn’t set up the slide after it.`;
  else read = `Mostly connected, but ${soft} handoff${soft === 1 ? '' : 's'} lean on a single shared idea.`;
  return { links, strong, soft, broken, thread, read, total: s.length };
}

/* orphan message: shares no vocabulary with its own title or any neighbour */
function isOrphan(deck, sIdx, msg) {
  const s = deck.slides[sIdx];
  const context = [s.title, deck.slides[sIdx - 1] && deck.slides[sIdx - 1].title,
    deck.slides[sIdx + 1] && deck.slides[sIdx + 1].title].filter(Boolean).join(' ');
  return words(msg).length > 0 && overlap(msg, context) === 0
    && overlap(msg, (s.bullets || []).filter(b => b !== msg).join(' ')) === 0;
}

/* ── structural advisories (merge / order / thin) ─────────── */
function slideText(s) { return [s.title, s.eyebrow, ...(s.bullets || []), s.takeaway].join(' '); }
function buildAdvisories(deck) {
  const out = [];
  const slides = deck.slides;
  if (slides.length < 2) return out;

  let best = null;
  for (let i = 0; i < slides.length; i++)
    for (let j = i + 1; j < slides.length; j++) {
      if (slides[i].kind === 'cover' || slides[j].kind === 'cover') continue;
      const shared = [...new Set(words(slideText(slides[j])).filter(w => wset(slideText(slides[i])).has(w)))];
      if (shared.length >= 2 && (!best || shared.length > best.words.length)) best = { i, j, words: shared };
    }
  if (best) out.push({
    id: 'merge-' + slides[best.i].id + '-' + slides[best.j].id, kind: 'MERGE',
    text: `Slides ${best.i + 1} and ${best.j + 1} both circle "${best.words.slice(0, 2).join('", "')}". Fold them into one stronger beat?`,
    accept: 'Merge them', apply: d => mergeSlides(d, slides[best.i].id, slides[best.j].id),
  });

  const decidR = /\b(double down|the ask|should|decide|decision|bet|next|recommend|propose|approve)\b/i;
  const askIdx = slides.findIndex((s, k) => k > 0 && k < slides.length - 1 && decidR.test(slideText(s)));
  if (askIdx > -1 && askIdx < slides.length - 2) out.push({
    id: 'order-' + slides[askIdx].id, kind: 'ORDER',
    text: `The strongest call-to-action lives on slide ${askIdx + 1}. Land it near the close instead?`,
    accept: 'Move to the end', apply: d => moveSlide(d, slides[askIdx].id, d.slides.length - 1),
  });

  const weight = s => (s.bullets || []).join(' ').length + String(s.takeaway || '').length + (s.metric ? 30 : 0);
  let thin = null;
  slides.forEach((s, k) => { if (s.kind !== 'cover' && k !== 0 && (!thin || weight(s) < weight(thin.s))) thin = { s, k }; });
  if (thin && weight(thin.s) < 90) out.push({
    id: 'thin-' + thin.s.id, kind: 'THIN',
    text: `Slide ${thin.k + 1} touches one thread weakly. Fold it into slide ${thin.k}?`,
    accept: 'Fold it in', apply: d => mergeSlides(d, slides[thin.k - 1].id, thin.s.id),
  });

  return out.slice(0, 3);
}
function mergeSlides(deck, keepId, dropId) {
  const keep = deck.slides.find(s => s.id === keepId), drop = deck.slides.find(s => s.id === dropId);
  if (!keep || !drop) return deck;
  const merged = { ...keep, bullets: [...(keep.bullets || []), ...(drop.bullets || [])].slice(0, 4), takeaway: keep.takeaway || drop.takeaway };
  return { ...deck, slides: deck.slides.filter(s => s.id !== dropId).map(s => s.id === keepId ? merged : s), activeId: keepId };
}
function moveSlide(deck, id, toIdx) {
  const from = deck.slides.findIndex(s => s.id === id);
  if (from < 0) return deck;
  const slides = deck.slides.slice();
  const [it] = slides.splice(from, 1);
  slides.splice(Math.max(0, Math.min(slides.length, toIdx)), 0, it);
  return { ...deck, slides };
}

/* ── a single draggable wire chip ─────────────────────────── */
function Wire({ kind, sid, index, text, empty, placeholder, orphan, drag, onDragStart, onDragEnd }) {
  const dragging = drag && drag.kind === kind && drag.sid === sid && drag.index === index;
  return (
    <div
      className={`sbw sbw--${kind} ${dragging ? 'is-dragging' : ''} ${empty ? 'is-empty' : ''} ${orphan ? 'is-orphan' : ''}`}
      draggable={!empty}
      onDragStart={e => { if (empty) { e.preventDefault(); return; } e.dataTransfer.effectAllowed = 'move'; try { e.dataTransfer.setData('text/plain', text || ''); } catch (x) {} onDragStart({ kind, sid, index, text }); }}
      onDragEnd={onDragEnd}
      title={orphan ? 'Off-thread — this message shares no words with its neighbours' : (empty ? '' : 'Drag to move')}
    >
      {!empty && <span className="sbw__grip"><i /><i /><i /><i /><i /><i /></span>}
      <span className="sbw__text">{empty ? placeholder : text}</span>
      {orphan && <span className="sbw__orphan" title="Off-thread">!</span>}
    </div>
  );
}

/* ── a slide column ───────────────────────────────────────── */
function Column({ deck, slide, idx, active, drag, over,
  onDragStart, onDragEnd, setOver, onPick, onOpen, onTrim,
  onDropMsg, onDropTitle, onDropBumper }) {
  const role = slideRole(slide);
  const msgs = slideMessages(slide);
  const slots = Math.max(3, msgs.length);

  const canTitle = drag && drag.kind === 'title' && drag.sid !== slide.id;
  const canBump = drag && drag.kind === 'bumper' && drag.sid !== slide.id;
  const canMsg = drag && drag.kind === 'msg';
  const overHere = over && over.sid === slide.id;

  return (
    <div className={`sbcol sbcol--${role.key} ${active ? 'is-active' : ''} ${drag && drag.sid === slide.id ? 'is-source' : ''}`}>
      {/* header */}
      <div className={`sbcol__head ${canTitle && overHere && over.kind === 'title' ? 'is-drop' : ''}`}
        onDragOver={e => { if (canTitle) { e.preventDefault(); setOver({ sid: slide.id, kind: 'title', index: 0 }); } }}
        onDrop={e => { if (canTitle) { e.preventDefault(); onDropTitle(drag.sid, slide.id); } }}>
        <span className="sbcol__num tnum">{String(idx + 1).padStart(2, '0')}</span>
        <span className={`sbrole sbrole--${role.key}`}>{role.label}</span>
        <span className="sbcol__tools">
          <button className="sbcol__tool" title="Open on stage" onClick={() => onOpen(slide.id)}><Ico name="expand" size={12} /></button>
          {deck.slides.length > 1 && <button className="sbcol__tool sbcol__tool--x" title="Trim slide" onClick={() => onTrim(slide.id)}><Ico name="close" size={12} /></button>}
        </span>
      </div>

      {/* title wire */}
      <div className="sbsec">
        <div className="sbsec__label">Title</div>
        <div className={`sbslot ${canTitle && overHere && over.kind === 'title' ? 'is-over' : ''}`}
          onClick={() => onPick(slide.id)} onDoubleClick={() => onOpen(slide.id)}
          onDragOver={e => { if (canTitle) { e.preventDefault(); setOver({ sid: slide.id, kind: 'title', index: 0 }); } }}
          onDrop={e => { if (canTitle) { e.preventDefault(); onDropTitle(drag.sid, slide.id); } }}>
          <Wire kind="title" sid={slide.id} index={0} text={slide.title || 'Untitled'} drag={drag} onDragStart={onDragStart} onDragEnd={onDragEnd} />
        </div>
      </div>

      {/* messages */}
      <div className="sbsec sbsec--msgs">
        <div className="sbsec__label">Messages <span className="sbsec__count">{msgs.length}</span></div>
        <div className="sbmsgs">
          {Array.from({ length: slots }).map((_, i) => {
            const has = i < msgs.length;
            const isOver = canMsg && overHere && over.kind === 'msg' && over.index === i;
            return (
              <div key={i} className={`sbslot sbslot--msg ${isOver ? 'is-over' : ''}`}
                onDragOver={e => { if (canMsg) { e.preventDefault(); setOver({ sid: slide.id, kind: 'msg', index: i }); } }}
                onDrop={e => { if (canMsg) { e.preventDefault(); onDropMsg(drag, slide.id, i); } }}>
                <Wire kind="msg" sid={slide.id} index={i} text={has ? msgs[i] : ''} empty={!has}
                  placeholder="drop a message" orphan={has && isOrphan(deck, idx, msgs[i])}
                  drag={drag} onDragStart={onDragStart} onDragEnd={onDragEnd} />
              </div>
            );
          })}
        </div>
      </div>

      {/* bumper */}
      <div className="sbsec">
        <div className="sbsec__label">Bumper <span className="sbsec__hint">{idx === deck.slides.length - 1 ? 'closes' : 'hands off →'}</span></div>
        <div className={`sbslot sbslot--bump ${canBump && overHere && over.kind === 'bumper' ? 'is-over' : ''}`}
          onDragOver={e => { if (canBump) { e.preventDefault(); setOver({ sid: slide.id, kind: 'bumper', index: 0 }); } }}
          onDrop={e => { if (canBump) { e.preventDefault(); onDropBumper(drag.sid, slide.id); } }}>
          <Wire kind="bumper" sid={slide.id} index={0} text={slide.takeaway || ''} empty={!slide.takeaway}
            placeholder="no bumper yet" drag={drag} onDragStart={onDragStart} onDragEnd={onDragEnd} />
        </div>
      </div>
    </div>
  );
}

/* ── connector between two columns (colored by handoff) ───── */
function Connector({ level }) {
  const col = level === 'strong' ? 'var(--accent)' : level === 'soft' ? 'var(--gold)' : level === 'none' ? 'var(--border)' : 'var(--mute)';
  const tag = level === 'strong' ? 'strong' : level === 'soft' ? 'soft' : level === 'none' ? 'open' : 'broken';
  return (
    <div className={`sbconn sbconn--${level}`} title={`${tag} handoff`}>
      <svg width="40" height="16" viewBox="0 0 40 16" fill="none">
        <path d="M1 8 H30" stroke={col} strokeWidth="1.6" strokeDasharray={(level === 'broken' || level === 'none') ? '2 4' : '0'} strokeLinecap="round" />
        <path d="M28 4 L36 8 L28 12" stroke={col} strokeWidth="1.7" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="sbconn__tag">{tag}</span>
    </div>
  );
}

/* ── the storyboard view ──────────────────────────────────── */
function Storyboard({ deck, feature, onPick, onOpen, onTrim, onAdd,
  onMoveMessage, onReorderByTitle, onSwapBumper,
  advisories, onAccept, onDismiss }) {
  const [drag, setDrag] = React.useState(null);
  const [over, setOver] = React.useState(null);
  const flow = analyzeFlow(deck);
  const adv = advisories && advisories[0];

  function onDragStart(d) { setDrag(d); setOver(null); }
  function onDragEnd() { setDrag(null); setOver(null); }
  function onDropMsg(from, toSid, toIdx) { onMoveMessage(from.sid, from.index, toSid, toIdx); setDrag(null); setOver(null); }
  function onDropTitle(fromSid, toSid) { if (fromSid !== toSid) onReorderByTitle(fromSid, toSid); setDrag(null); setOver(null); }
  function onDropBumper(fromSid, toSid) { if (fromSid !== toSid) onSwapBumper(fromSid, toSid); setDrag(null); setOver(null); }

  return (
    <div className="stage__scroll stage__scroll--board" onDragEnd={onDragEnd}>
      {/* flow report */}
      <div className="sbreport">
        <div className="sbreport__l">
          <div className="sbreport__title">Narrative flow</div>
          <div className="sbreport__read">{flow.read}</div>
          {flow.links.length > 0 && (
            <div className="sbreport__pips">
              <span className="sbreport__pips-cap">Handoffs</span>
              {flow.links.map((l, i) => <span key={i} className={`sbpip sbpip--${l.level}`} title={`Slide ${l.i + 1} → ${l.i + 2}: ${l.level}`} />)}
              <span className="sbreport__legend">
                <i className="sbpip sbpip--strong" /> strong
                <i className="sbpip sbpip--soft" /> soft
                <i className="sbpip sbpip--broken" /> broken
              </span>
            </div>
          )}
        </div>
        <div className="sbreport__r">
          {adv ? (
            <div className="sbadv" key={adv.id}>
              <div className="sbadv__row">
                <span className={`sbadv__kind sbadv__kind--${adv.kind.toLowerCase()}`}>{adv.kind}</span>
                <span className="sbadv__text">{adv.text}</span>
              </div>
              <div className="sbadv__acts">
                <button className="qchip is-accent" onClick={() => onAccept(adv)}><Ico name="check" size={12} />{adv.accept}</button>
                <button className="qchip" onClick={() => onDismiss(adv)}>Dismiss</button>
                {advisories.length > 1 && <span className="sbadv__more">+{advisories.length - 1} more</span>}
              </div>
            </div>
          ) : (
            <div className="sbadv sbadv--clear">
              <span className="sbadv__clearico"><Ico name="check" size={14} /></span>
              <span>Structure looks clean — no moves to suggest.</span>
            </div>
          )}
        </div>
      </div>

      {/* wires board */}
      <div className={`sbboard ${drag ? 'is-dragging' : ''}`}>
        {deck.slides.map((s, i) => (
          <React.Fragment key={s.id}>
            <Column
              deck={deck} slide={s} idx={i} active={s.id === deck.activeId}
              drag={drag} over={over}
              onDragStart={onDragStart} onDragEnd={onDragEnd} setOver={setOver}
              onPick={onPick} onOpen={onOpen} onTrim={onTrim}
              onDropMsg={onDropMsg} onDropTitle={onDropTitle} onDropBumper={onDropBumper}
            />
            {i < deck.slides.length - 1 && <Connector level={flow.links[i] ? flow.links[i].level : 'broken'} />}
          </React.Fragment>
        ))}
        <button className="sbadd" onClick={onAdd} title="Add a slide"><Ico name="new" size={18} /><span>Add slide</span></button>
      </div>
    </div>
  );
}

Object.assign(window, { Storyboard, buildAdvisories, analyzeFlow, slideRole });
