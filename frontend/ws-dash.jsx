/* ============================================================
   ws-dash.jsx — the decision dashboard
   ------------------------------------------------------------
   Replaces the chat-history view. As the user drives the deck
   (via the composer or preset chips), this surfaces the changes
   as CATEGORICAL, EDITABLE option groups. Baseline categories are
   predictable (Content, Typography, Layout, Direction); extra
   categories are generated on demand from what the user asks for.
   ============================================================ */

const { FONT_LIST, FONT_SIZES } = window;

const PALETTE_LABELS = { warm: 'Warm', bold: 'Bold', clean: 'Clean' };

/* ── parse a style request out of a prompt ────────────────── */
function parseStylePatch(prompt) {
  const t = ' ' + String(prompt || '').toLowerCase() + ' ';
  const patch = {}; const touched = [];

  // font family
  const aliases = { 'times new roman':'Times New Roman', 'times':'Times New Roman',
    'arial':'Arial', 'helvetica':'Arial', 'georgia':'Georgia',
    'space grotesk':'Space Grotesk', 'grotesk':'Space Grotesk',
    'courier new':'Courier New', 'courier':'Courier New', 'monospace':'Courier New',
    'lato':'Lato' };
  for (const key of Object.keys(aliases)) {
    if (t.includes(key)) { patch.font = aliases[key]; break; }
  }
  // font size
  const m = t.match(/(\d{1,3})\s*(pt|point|px)\b/) || (/(font\s*size|size)\b/.test(t) && t.match(/(\d{1,3})/));
  if (m) {
    const n = parseInt(m[1], 10);
    const nearest = [12, 14, 16, 18, 24, 32].reduce((a, b) => Math.abs(b - n) < Math.abs(a - n) ? b : a, 16);
    patch.fontPt = nearest + ' pt';
  }
  if (patch.font || patch.fontPt) touched.push('typography');

  // palette / direction
  if (/\b(bold|dark|high[- ]?contrast|dramatic)\b/.test(t)) { patch.palette = 'bold'; touched.push('direction'); }
  else if (/\b(clean|light|white|minimal|airy)\b/.test(t)) { patch.palette = 'clean'; touched.push('direction'); }
  else if (/\b(warm|cream|paper|earthy)\b/.test(t)) { patch.palette = 'warm'; touched.push('direction'); }

  // emphasis
  if (/\b(story|narrative|qualitative|opening)\b/.test(t)) { patch.emphasis = 'story'; touched.push('layout'); }
  else if (/\b(number|metric|stat|figure|quantitative|data-forward)\b/.test(t)) { patch.emphasis = 'number'; touched.push('layout'); }

  return { patch, touched };
}

/* ── generate extra categories on demand ──────────────────── */
function dynamicCats(prompt, slide) {
  const t = ' ' + String(prompt || '').toLowerCase() + ' ';
  const out = [];

  const chartM = t.match(/\b(column|bar|line|area|donut|pie)\b/);
  if (chartM && slide && (slide.kind === 'chart' || slide.kind === 'plot' || /\bchart|graph|plot\b/.test(t))) {
    const map = { column:'Column', bar:'Bar', line:'Line', area:'Area', donut:'Donut', pie:'Pie' };
    out.push({ id:'chart', label:'Chart style', icon:'chart', controls:[
      { id:'chartType', label:'Type', type:'select', options:['Column','Bar','Line','Area','Donut'], value: map[chartM[1]] || 'Column' },
      { id:'highlight', label:'Highlight', type:'select', options:['Last point','Highest','Lowest','None'], value:'Last point' },
    ] });
  }

  if (/\b(tight|dense|compact|spacious|roomy|whitespace|breathing|padding|space)\b/.test(t)) {
    out.push({ id:'density', label:'Density', icon:'layout', controls:[
      { id:'density', label:'Spacing', type:'segmented', options:['tight','roomy'], labels:{ tight:'Tight', roomy:'Roomy' },
        value: /\b(tight|dense|compact)\b/.test(t) ? 'tight' : 'roomy' },
    ] });
  }

  if (/\b(align|center|centre|left|right)\b/.test(t)) {
    out.push({ id:'align', label:'Alignment', icon:'layout', controls:[
      { id:'align', label:'Align', type:'segmented', options:['left','center'], labels:{ left:'Left', center:'Center' },
        value: /\b(center|centre)\b/.test(t) ? 'center' : 'left' },
    ] });
  }

  if (/\b(icon|emoji|logo|image|photo|picture)\b/.test(t)) {
    out.push({ id:'imagery', label:'Imagery', icon:'spark', controls:[
      { id:'imagery', label:'Show', type:'segmented', options:['off','on'], labels:{ off:'None', on:'Add slot' }, value:'on' },
    ] });
  }

  return out;
}

/* ── baseline (always-present) categories from the slide ──── */
function baselineCats(slide, feature) {
  if (!slide) return [];
  const cats = [];
  cats.push({ id:'content', label:'Content', icon:'text', controls:[
    { id:'title', label:'Headline', type:'text', value: slide.title || '' },
    { id:'takeaway', label:'Takeaway', type:'text', value: slide.takeaway || '' },
  ] });
  cats.push({ id:'typography', label:'Typography', icon:'type', controls:[
    { id:'font', label:'Font', type:'select', options: FONT_LIST, value: slide.font || 'Lato' },
    { id:'fontPt', label:'Size', type:'select', options: FONT_SIZES, value: slide.fontPt || '16 pt' },
  ] });
  cats.push({ id:'layout', label:'Layout', icon:'layout', controls:[
    { id:'emphasis', label:'Emphasis', type:'segmented', options:['number','story'], labels:{ number:'Number leads', story:'Story leads' }, value: slide.emphasis || 'number' },
  ] });
  cats.push({ id:'direction', label:'Direction', icon:'palette', controls:[
    { id:'palette', label:'Palette', type:'select', options:['warm','bold','clean'], labels: PALETTE_LABELS, value: slide.palette || 'warm' },
  ] });

  // A chart slide gets controls that actually change the chart. The old ones
  // were produced by text-matching a prompt and applied nowhere, so picking a
  // type did nothing; these read from and write to the slide's chart model.
  if (slide.kind === 'chart' && slide.chart) {
    const o = slide.chart.options || {};
    cats.push({ id:'chart', label:'Chart', icon:'chart', controls:[
      { id:'chartKind', label:'Type', type:'select',
        options:['bar','column','line','area','pie'],
        labels:{ bar:'Bar', column:'Column', line:'Line', area:'Area', pie:'Pie' },
        value: slide.chart.kind || 'column' },
      { id:'chartLabels', label:'Values', type:'segmented', options:['on','off'],
        labels:{ on:'Show', off:'Hide' }, value: o.valueLabels === false ? 'off' : 'on' },
      { id:'chartGrid', label:'Gridlines', type:'segmented', options:['on','off'],
        labels:{ on:'Show', off:'Hide' }, value: o.gridlines ? 'on' : 'off' },
      { id:'chartSort', label:'Order', type:'select',
        options:['source','desc','asc'],
        labels:{ source:'As given', desc:'Largest first', asc:'Smallest first' },
        value: o.sort || 'source' },
      { id:'chartHighlight', label:'Highlight', type:'select',
        options:['none', ...(slide.chart.data || []).map(d => String(d.label))],
        labels:{ none:'None' }, value: o.highlight || 'none' },
    ] });
  }
  return cats;
}

/* ── controls ─────────────────────────────────────────────── */
/* ── timeline controls ───────────────────────────────────── */
function TlControl({ catId, ctrl, onControl }) {
  const { Ico } = window;
  if (ctrl.type === 'text') {
    return (
      <label className="tl-ctrl tl-ctrl--wide">
        <span className="tl-ctrl__l">{ctrl.label}</span>
        <input className="tl-input" value={ctrl.value} spellCheck={false}
          onChange={e => onControl(catId, ctrl.id, e.target.value)} />
      </label>
    );
  }
  if (ctrl.type === 'select') {
    return (
      <label className="tl-ctrl">
        <span className="tl-ctrl__l">{ctrl.label}</span>
        <span className="tl-sel-wrap">
          <select className="tl-sel" value={ctrl.value} onChange={e => onControl(catId, ctrl.id, e.target.value)}>
            {ctrl.options.map(o => <option key={o} value={o}>{(ctrl.labels && ctrl.labels[o]) || o}</option>)}
          </select>
          <Ico name="chevron" size={12} />
        </span>
      </label>
    );
  }
  if (ctrl.type === 'segmented') {
    return (
      <span className="tl-ctrl">
        <span className="tl-ctrl__l">{ctrl.label}</span>
        <span className="tl-seg">
          {ctrl.options.map(o => (
            <button key={o} className={`tl-seg__b ${ctrl.value === o ? 'on' : ''}`}
              onClick={() => onControl(catId, ctrl.id, o)}>{(ctrl.labels && ctrl.labels[o]) || o}</button>
          ))}
        </span>
      </span>
    );
  }
  return null;
}

function TlNode({ cat, flash, onControl }) {
  const { Ico } = window;
  return (
    <div className={`tl-node ${flash ? 'is-flash' : ''}`}>
      <span className="tl-rail"><span className="tl-dot" /></span>
      <div className="tl-main">
        <div className="tl-label">
          <Ico name={cat.icon} size={13} />{cat.label}
          {flash && <span className="tl-tag">updated</span>}
        </div>
        <div className="tl-controls">
          {cat.controls.map(c => <TlControl key={c.id} catId={cat.id} ctrl={c} onControl={onControl} />)}
        </div>
      </div>
    </div>
  );
}

/* ── the dashboard (collapsible timeline) ─────────────────── */
function Dashboard({ cats, flash, onControl, onAction, feature, samples, onPreset, open, onToggle, notify, stageView, onStageView, advCount }) {
  const { Ico, FEATURES, FEATURE_ICON } = window;
  const FEATURE_ORDER = ['create', 'data', 'refine', 'condense'];
  const others = FEATURE_ORDER.filter(f => f !== feature);
  if (!cats.length) return null;
  const nUpd = flash ? flash.length : 0;
  return (
    <div className="dash">
      <div className="dash__head">
        <button className="dash__headbtn" onClick={onToggle} aria-expanded={open}>
          <span className="dash__title">
            <span className="dash__chev"><Ico name={open ? 'chevron' : 'expand'} size={13} /></span>
            <Ico name="tune" size={14} />Adjustments
            {nUpd ? <span className="dash__badge">{nUpd} updated</span> : null}
            {!open && notify ? <span className="dash__notify" title="New changes to review" /> : null}
          </span>
        </button>
        <span className="dash__spacer" />
        {stageView ? (
          <span className="stageview" role="tablist" aria-label="Stage view">
            <button className={`stageview__b ${stageView === 'slide' ? 'on' : ''}`} onClick={() => onStageView('slide')}>
              <Ico name="layout" size={13} />Slide
            </button>
            <button className={`stageview__b ${stageView === 'storyboard' ? 'on' : ''}`} onClick={() => onStageView('storyboard')}>
              <Ico name="condense" size={13} />Storyboard
              {advCount ? <span className="stageview__badge tnum">{advCount}</span> : null}
            </button>
          </span>
        ) : (
          <span className="dash__hint">{open ? 'Timeline of changes — every value is editable' : (notify ? 'New changes — expand to review' : 'Expand to review & edit changes')}</span>
        )}
      </div>

      {open && (
        <div className="tl">
          {cats.map(cat => <TlNode key={cat.id} cat={cat} flash={flash && flash.includes(cat.id)} onControl={onControl} />)}
          <div className="tl-node tl-node--last">
            <span className="tl-rail"><span className="tl-dot tl-dot--go" /></span>
            <div className="tl-main">
              <div className="tl-label"><Ico name="download" size={13} />Deliver</div>
              <div className="tl-controls tl-controls--acts">
                <button className="tl-act primary" onClick={() => onAction({ type:'export', v:'pptx' })}><Ico name="download" size={12} />.pptx</button>
                <button className="tl-act" onClick={() => onAction({ type:'export', v:'pdf' })}>.pdf</button>
                {others.map(o => (
                  <button key={o} className="tl-act ghost" onClick={() => onAction({ type:'goto', v:o })}>
                    <Ico name={FEATURE_ICON[o]} size={12} />{FEATURES[o].name}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="tl-suggest">
            <div className="tl-suggest__l"><Ico name="spark" size={13} />Suggested next steps</div>
            <div className="tl-suggest__chips">
              {(samples || []).map(s => <button key={s} className="tl-chip" onClick={() => onPreset(s)}>{s}</button>)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

Object.assign(window, { parseStylePatch, dynamicCats, baselineCats, Dashboard });
