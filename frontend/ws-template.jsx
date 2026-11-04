/* ============================================================
   ws-template.jsx — upload a .pptx template, apply or remove it.

   A template is brand plus constraints, never layout. The server
   (deckengine/template.py) reads the file into a theme — colours,
   type, slide size, any band the master already occupies — and the
   engine keeps resolving every box itself inside those margins.

   Applying one here does two things:
     1. the preview switches to a palette built from the template's
        own colours, so the screen matches what exports;
     2. the export carries `templateId`, so the .pptx is drawn onto
        the real master and the logo and background come through.

   Removing it puts both back. Nothing about the slides' content or
   their geometry changes either way.
   ============================================================ */

const { Ico } = window;
const { useState, useEffect, useRef } = React;

const API = window.WS_NO_BACKEND ? ''
  : ((window.BU_API_BASE || '').replace(/\/$/, '')
    || ((location.protocol === 'http:' || location.protocol === 'https:') ? location.origin : ''));

/* A template's theme -> the palette shape the preview renders with, plus a
   picture of its own master as the backdrop.

   Colours alone were a preview that lied: the export carried the template's
   logo, picture background and footer while the screen showed three flat
   swatches. `bgImage` is a PNG of one empty slide on that master, rendered
   server-side through LibreOffice — the real thing, not an approximation.
   It is a picture, not geometry: no coordinate from it reaches layout. */
function paletteFromTemplate(tpl) {
  const t = tpl.theme || {};
  const hx = v => (v && /^[0-9A-Fa-f]{6}$/.test(v) ? `#${v}` : null);
  // The rendered master is the truth about the background. A template can
  // carry a navy brand colour on white paper, and trusting the theme there
  // put white type on a white slide.
  const sampled = tpl.backdrop || null;
  const dark = sampled ? !!sampled.dark : !!t.dark;
  const bg = (sampled && hx(sampled.bg)) || hx(t.primary) || (dark ? '#12130F' : '#FFFFFF');
  const accent = hx(t.accent) || '#0E5B36';

  // Text colour follows the background we actually render on. The theme's
  // sub_on_dark is a brand tint (often a pale blue) that reads as washed-out
  // body copy on someone else's master, so body text is the ink colour held
  // back a little rather than a different hue.
  const ink = dark ? '#FFFFFF' : '#11120E';
  const sub = dark ? 'rgba(255,255,255,0.82)' : 'rgba(17,18,14,0.74)';
  return {
    key: 'template', label: tpl.name || 'Template', swatch: accent,
    bg, ink, sub, mute: sub, accent, spark: accent,
    rule: dark ? 'rgba(255,255,255,0.22)' : 'rgba(17,18,14,0.14)',
    bgImage: tpl.id ? `${API}/api/templates/${tpl.id}/backdrop.png` : null,
    // The template's own type, used for the preview and carried into export.
    headerFont: t.header_font || null,
    bodyFont: t.body_font || null,
    // The engine's working margins for this template, in preview pixels, so
    // the preview keeps content clear of a logo band or an ornamental frame
    // instead of running underneath it. 720px of preview = 13.333in.
    pad: tpl.margins ? {
      top: Math.round(tpl.margins.top * (720 / 13.333)),
      right: Math.round(tpl.margins.right * (720 / 13.333)),
      bottom: Math.round(tpl.margins.bottom * (720 / 13.333)),
      left: Math.round(tpl.margins.left * (720 / 13.333)),
    } : null,
  };
}

function useTemplates() {
  const [items, setItems] = useState([]);
  const [state, setState] = useState(API ? 'loading' : 'off');

  function refresh() {
    if (!API) { setState('off'); return Promise.resolve([]); }
    return fetch(API + '/api/templates')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(d => { setItems(d.templates || []); setState('ok'); return d.templates || []; })
      .catch(() => { setState('off'); return []; });
  }

  useEffect(() => { refresh(); }, []);
  return { items, state, refresh };
}

function TemplatePanel({ appliedId, onApply, onRemove }) {
  const { items, state, refresh } = useTemplates();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const fileRef = useRef(null);

  async function upload(file) {
    if (!file) return;
    setErr(''); setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(API + '/api/templates', { method: 'POST', body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `upload failed (${res.status})`);
      await refresh();
      onApply(data);                       // applying what you just uploaded
    } catch (e) {
      setErr(e.message || 'Upload failed.');
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function remove(tid, e) {
    e.stopPropagation();
    setErr('');
    try {
      const res = await fetch(`${API}/api/templates/${tid}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('could not delete it');
      if (appliedId === tid) onRemove();
      await refresh();
    } catch (e2) {
      setErr(e2.message);
    }
  }

  if (state === 'off') {
    return (
      <div className="vnote">
        Templates are read by the engine, and this build has none behind it.
        Run the local server to upload a .pptx and draw your decks onto it.
      </div>
    );
  }

  return (
    <div className="tplpanel">
      <div className="tplrow">
        <button className="tplup" disabled={busy} onClick={() => fileRef.current && fileRef.current.click()}>
          <Ico name="attach" size={15} />
          {busy ? 'Reading the template…' : 'Upload a .pptx template'}
        </button>
        <input ref={fileRef} type="file" accept=".pptx,.potx" hidden
          onChange={e => upload(e.target.files && e.target.files[0])} />
        {appliedId ? (
          <button className="tplclear" onClick={onRemove}>Remove from deck</button>
        ) : null}
      </div>
      {err ? <div className="tplerr">{err}</div> : null}

      {items.length ? (
        <div className="tpllist">
          {items.map(t => {
            const on = appliedId === t.id;
            const pal = paletteFromTemplate(t);
            return (
              <button key={t.id} className={`tplcard ${on ? 'on' : ''}`}
                onClick={() => (on ? onRemove() : onApply(t))}>
                <span className="tplcard__swatches">
                  <i style={{ background: pal.bg }} />
                  <i style={{ background: pal.accent }} />
                  <i style={{ background: pal.ink }} />
                </span>
                <span className="tplcard__body">
                  <span className="tplcard__name">{t.name}</span>
                  <span className="tplcard__meta">
                    {(t.theme && t.theme.header_font) || 'default type'} · {t.slide_w}×{t.slide_h}in
                    {t.reserved && t.reserved.length
                      ? ` · ${t.reserved.length} reserved band${t.reserved.length === 1 ? '' : 's'}`
                      : ''}
                  </span>
                </span>
                <span className="tplcard__state">{on ? 'Applied' : 'Apply'}</span>
                <span className="tplcard__del" title="Delete this template" onClick={e => remove(t.id, e)}>
                  <Ico name="close" size={13} />
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <p className="tplempty">No templates yet. Upload one and every generated slide is drawn onto its master.</p>
      )}
    </div>
  );
}

Object.assign(window, { TemplatePanel, paletteFromTemplate });
