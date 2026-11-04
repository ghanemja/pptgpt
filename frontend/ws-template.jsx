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

/* ============================================================
   ExactSlide — the slide as it actually exports.

   The HTML preview is an approximation and always will be: a browser can
   only draw with fonts the viewer has installed, so a deck on a template
   built in Bookman Old Style previews in whatever the machine substitutes.
   This asks the engine to render the real .pptx — same spec_render path as
   export, same template master — and shows the image it gets back.

   The HTML card stays underneath as the instant view: it appears at once,
   and the exact render swaps in when it is ready (a few seconds, then
   cached). If the engine cannot render — no LibreOffice — the HTML preview
   simply stays, which is why `children` is always mounted.
   ============================================================ */
function ExactSlide({ slide, templateId, width, height, children }) {
  const [src, setSrc] = useState(null);
  const [state, setState] = useState('idle');    // idle | rendering | ok | off
  const sig = JSON.stringify([slide, templateId]);

  useEffect(() => {
    if (!API || window.WS_NO_BACKEND || !window.slideToSpec) { setState('off'); return; }
    let dead = false;
    let url = null;
    setState('rendering');
    // The previous slide's render is not this slide: clear it so the loader
    // shows rather than the wrong slide sitting there looking current.
    setSrc(null);
    // A keystroke should not queue a render; wait for the edit to settle.
    const timer = setTimeout(() => {
      // With a template, send the SLIDE: the engine casts it into that
      // template's own layouts, so position, type and bullet styling are the
      // template's rather than ours. Without one, send the engine's placement.
      let payload;
      if (templateId) {
        payload = { slide, templateId };
      } else {
        try { payload = { spec: window.slideToSpec(slide) }; }
        catch (e) { setState('off'); return; }
      }
      fetch(API + '/api/preview_png', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
        .then(r => (r.ok ? r.blob() : Promise.reject(r.status)))
        .then(blob => {
          if (dead) return;
          url = URL.createObjectURL(blob);
          setSrc(url);
          setState('ok');
        })
        .catch(() => { if (!dead) setState('off'); });
    }, 450);

    return () => {
      dead = true;
      clearTimeout(timer);
      if (url) URL.revokeObjectURL(url);
    };
  }, [sig]);

  // While the exact render is on its way, show a loader — not the HTML
  // approximation. Flashing the template's bare master and then replacing it
  // a second later reads as a bug, and the approximation is the thing we
  // stopped trusting. The HTML preview is kept for the one case it is still
  // the answer: no engine behind this build, so no exact render is coming.
  const showHtml = state === 'off';

  return (
    <div className="exact" style={{ width, height }}>
      {showHtml ? <div className="exact__html">{children}</div> : null}
      {src ? <img className={`exact__img ${state === 'ok' ? 'is-on' : ''}`} src={src} alt="" /> : null}
      {state === 'rendering' || state === 'idle' ? (
        <div className="exact__wait">
          <span className="exact__spin" />
          <span className="exact__waittxt">rendering slide</span>
        </div>
      ) : null}
      {state === 'ok' ? <span className="exact__badge is-ok">exact</span> : null}
    </div>
  );
}

Object.assign(window, { ExactSlide });
