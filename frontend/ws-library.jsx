/* ============================================================
   ws-library.jsx — the company's icons and images, on a slide.

   The library is the kit's assets/ folder, labelled and tagged by
   assets/assets.csv (deckengine/kit.py). Search is the engine's —
   deterministic, a tag hit counts twice a label hit — so the same
   words always surface the same pictures.

   Picking one sets `slide.image = {kit, file, label}`. That is a
   reference, not a placement: with a template the engine casts it into
   the template's own picture slot (native.py); without one the export
   lays it out beside the text (ws-export.js). The UI chooses which
   picture, never where it goes.
   ============================================================ */

const { Ico } = window;
const { useState, useEffect } = React;

const API = window.WS_NO_BACKEND ? ''
  : ((window.BU_API_BASE || '').replace(/\/$/, '')
    || ((location.protocol === 'http:' || location.protocol === 'https:') ? location.origin : ''));

function assetUrl(kit, file) {
  return `${API}/api/kits/${encodeURIComponent(kit)}/asset?file=${encodeURIComponent(file)}`;
}

/* The words a slide is about — its title, eyebrow and points. */
function slideQuery(slide) {
  if (!slide) return '';
  return [slide.eyebrow, slide.title, ...(slide.bullets || []), slide.takeaway]
    .filter(Boolean).join(' ').slice(0, 400);
}

function useAssets(kit, q) {
  const [items, setItems] = useState([]);
  const [state, setState] = useState('loading');
  useEffect(() => {
    if (!API || !kit) { setState('off'); return; }
    let dead = false;
    setState('loading');
    // Typing should not fire a search per keystroke.
    const t = setTimeout(() => {
      fetch(`${API}/api/kits/${encodeURIComponent(kit)}/assets?q=${encodeURIComponent(q || '')}&limit=60`)
        .then(r => (r.ok ? r.json() : Promise.reject()))
        .then(d => { if (!dead) { setItems(d.assets || []); setState('ok'); } })
        .catch(() => { if (!dead) setState('off'); });
    }, 180);
    return () => { dead = true; clearTimeout(t); };
  }, [kit, q]);
  return { items, state };
}

function AssetTile({ kit, a, on, onPick, disabled }) {
  return (
    <button className={`libtile ${on ? 'on' : ''}`} disabled={disabled} onClick={() => onPick(a)}
      title={[a.label, a.use, (a.tags || []).join(', '), a.license].filter(Boolean).join(' · ')}>
      <span className="libtile__img"><img src={assetUrl(kit, a.file)} alt={a.label} loading="lazy" /></span>
      <span className="libtile__label">{a.label}</span>
      {!a.labeled ? <span className="libtile__warn" title="No row in assets.csv — found by file name only">unlabelled</span> : null}
    </button>
  );
}

function LibraryPanel({ kit, kitName, slide, onPick, onRemove, onClose }) {
  const [q, setQ] = useState('');
  const all = useAssets(kit, q);
  const query = slideQuery(slide);
  const suggested = useAssets(kit, query);

  // A chart, diagram or plot already fills the slide's picture slot.
  const hasVisual = !!(slide && ((slide.kind === 'chart' && slide.chart)
    || (slide.kind === 'diagram' && slide.diagram) || (slide.kind === 'plot' && slide.plot)
    || slide.kind === 'cover'));
  const cur = slide && slide.image;
  const isOn = a => !!(cur && cur.kit === kit && cur.file === a.file);
  const pick = a => onPick({ kit, file: a.file, label: a.label });

  // Only show suggestions that actually matched something on the slide.
  const sugg = query ? suggested.items.filter(a => (a.score || 0) > 0).slice(0, 8) : [];

  return (
    <div className="history libpanel">
      <div className="history__head">
        <span className="history__title">Library · {kitName || kit}</span>
        <input className="qrow__in libsearch" value={q} placeholder="Search icons and images — growth, team, security…"
          onChange={e => setQ(e.target.value)} autoFocus />
        <button className="rail__collapse" onClick={onClose} title="Close"><Ico name="close" size={16} /></button>
      </div>
      <div className="history__scroll">
        <div className="history__inner libinner">
          {all.state === 'off' ? (
            <div className="tray__empty">
              The library is read from the kit folder by the local engine, and none is reachable.
            </div>
          ) : (
            <>
              {hasVisual ? (
                <div className="vnote">
                  This slide is a {slide.kind}; its visual already takes the picture slot. Pick a text slide to add an image.
                </div>
              ) : !slide ? (
                <div className="vnote">Add a slide first, then pick a picture for it.</div>
              ) : cur ? (
                <div className="libcur">
                  <span className="libcur__img"><img src={assetUrl(cur.kit, cur.file)} alt="" /></span>
                  <span className="libcur__txt">On this slide: <b>{cur.label || cur.file}</b></span>
                  <button className="tplclear" onClick={onRemove}>Remove image</button>
                </div>
              ) : null}

              {!q && sugg.length ? (
                <section>
                  <div className="kitsec__h">Suggested for this slide</div>
                  <div className="libgrid">
                    {sugg.map(a => <AssetTile key={a.file} kit={kit} a={a} on={isOn(a)} onPick={pick} disabled={hasVisual || !slide} />)}
                  </div>
                </section>
              ) : null}

              <section>
                <div className="kitsec__h">{q ? `Matches for “${q}”` : 'Everything'}
                  <span className="tray__count">{all.items.length}</span></div>
                {all.state === 'loading' && !all.items.length ? (
                  <div className="tray__empty">Searching…</div>
                ) : all.items.length ? (
                  <div className="libgrid">
                    {all.items.map(a => <AssetTile key={a.file} kit={kit} a={a} on={isOn(a)} onPick={pick} disabled={hasVisual || !slide} />)}
                  </div>
                ) : (
                  <div className="tray__empty">
                    {q ? 'Nothing matches. Tags in assets.csv decide what a search finds.'
                      : 'No assets in this kit yet. Add icons and images in the kit setup.'}
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { LibraryPanel, assetUrl });
