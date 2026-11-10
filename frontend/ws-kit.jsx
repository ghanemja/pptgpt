/* ============================================================
   ws-kit.jsx — set up a company kit.

   A kit is a folder, kits/<slug>/, and the folder is the source of truth
   (deckengine/kit.py). This panel only writes into it and reads it back:
   uploading a file here, pointing at a folder on this machine, and dragging
   files into the folder by hand all end in the same place, and Rescan shows
   whatever is on disk now.

   Every part of the kit is a row in a checklist — profile, template,
   example decks, icons & images, voice, learned — with the ways in that
   part supports. Learning is measured from the example decks by the engine
   (deckengine/kit_ingest.py); the rules it suggests are only suggestions
   until a person ticks them into the profile.

   Nothing here chooses geometry. A kit supplies content conventions and a
   template; the engine still places every box (CLAUDE.md, §0).
   ============================================================ */

const { Ico } = window;
const { useState, useEffect, useRef } = React;

const API = window.WS_NO_BACKEND ? ''
  : ((window.BU_API_BASE || '').replace(/\/$/, '')
    || ((location.protocol === 'http:' || location.protocol === 'https:') ? location.origin : ''));

/* What each part accepts and how it can be filled. `folder` is which
   "point to a folder" modes the server allows for that part: only example
   decks and assets can be linked in place (kit.import_path). */
const KIT_PARTS = {
  profile: {
    accept: '.json', multiple: false, folder: null,
    how: 'The scoping questions, narrative arc and house rules. Edit profile.json in a text editor, or upload a replacement.',
  },
  template: {
    accept: '.pptx,.potx', multiple: false, folder: ['copy'],
    how: 'Your PowerPoint template. Slides are cast into its own layouts, so the brand, type and backdrop come from the file.',
  },
  examples: {
    accept: '.pptx', multiple: true, folder: ['copy', 'link'],
    how: 'Finished decks that show how your company presents. Learning measures them. .pptx only — not .ppt, not PDF.',
  },
  assets: {
    accept: '.svg,.png,.jpg,.jpeg,.gif,.webp,.csv', multiple: true, folder: ['copy', 'link'],
    how: 'Icons and images for slides, plus assets.csv to label and tag them so search finds the right one.',
  },
  voice: {
    accept: '.md,.txt', multiple: false, folder: null,
    how: 'How your company writes, in plain words. It is added to every generation prompt. Edit it below.',
  },
  learned: {
    accept: null, multiple: false, folder: null,
    how: 'Written by "Learn from examples". Never edit it by hand — run learning again instead.',
  },
};

async function kitCall(method, path, body) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(API + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.detail || `request failed (${res.status})`);
  return data;
}

/* "Stored 3 · skipped 1 (why)" — what an upload or import actually did. */
function reportText(rep) {
  if (!rep) return '';
  if (rep.linked) {
    return `Linked ${rep.linked} in place — ${rep.files} file${rep.files === 1 ? '' : 's'} found. They stay where they are.`;
  }
  const stored = (rep.stored || []).length;
  const skipped = rep.skipped || [];
  let t = `Added ${stored} file${stored === 1 ? '' : 's'}.`;
  if (skipped.length) {
    const shown = skipped.slice(0, 3).map(s => `${String(s.file).split('/').pop()}: ${s.reason}`).join('; ');
    t += ` Skipped ${skipped.length} — ${shown}${skipped.length > 3 ? '…' : ''}`;
  }
  return t;
}

function pct(v) { return `${Math.round((v || 0) * 100)}%`; }

/* What learning measured, in sentences rather than a JSON dump. */
function LearnedSummary({ learned }) {
  if (!learned) return null;
  const d = learned.density || {};
  const t = learned.titles || {};
  const v = learned.visuals || {};
  const ty = learned.type || {};
  const rows = [
    ['Read', `${learned.decks} deck${learned.decks === 1 ? '' : 's'}, ${learned.slides} slides`
      + ((learned.failed || []).length ? ` (${learned.failed.length} could not be read)` : '')],
    d.points_per_slide && d.points_per_slide.n ? ['Points per slide', `median ${d.points_per_slide.median}, most ${d.points_per_slide.max}`] : null,
    d.words_per_point && d.words_per_point.n ? ['Words per point', `median ${d.words_per_point.median}`] : null,
    t.words && t.words.n ? ['Title length', `median ${t.words.median} words · ${pct(t.argue_share)} state a claim`] : null,
    ['Visuals', `${pct(v.chart_share)} charts · ${pct(v.picture_share)} pictures · ${pct(v.text_only_share)} text only`],
    (learned.layouts || []).length ? ['Layouts used', learned.layouts.slice(0, 4).map(l => `${l.name} ${pct(l.share)}`).join(' · ')] : null,
    (ty.fonts || []).length ? ['Fonts', ty.fonts.slice(0, 3).map(f => f.name).join(', ')] : null,
  ].filter(Boolean);
  return (
    <dl className="kitlearn__dl">
      {rows.map(([k, val]) => (
        <React.Fragment key={k}><dt>{k}</dt><dd>{val}</dd></React.Fragment>
      ))}
    </dl>
  );
}

function KitPart({ part, scan, busy, onUpload, onImport, sources }) {
  const cfg = KIT_PARTS[part.key] || {};
  const fileRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState('');
  const [mode, setMode] = useState('copy');
  const problems = part.problems || [];

  return (
    <div className={`kitpart ${part.ok ? 'is-ok' : ''}`}>
      <div className="kitpart__head">
        <span className={`kitpart__tick ${part.ok ? 'on' : ''}`}>
          {part.ok ? <Ico name="check" size={13} /> : null}
        </span>
        <div className="kitpart__txt">
          <div className="kitpart__label">{part.label}</div>
          <div className="kitpart__detail">{part.detail}</div>
        </div>
        <code className="kitpart__path" title={`${scan.path}/${part.path}`}>{part.path}</code>
      </div>
      <p className="kitpart__how">{cfg.how}</p>
      {problems.length ? (
        <ul className="kitpart__probs">{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
      ) : null}
      {(sources || []).length ? (
        <div className="kitpart__links">
          Linked in place: {sources.map(s => <code key={s}>{s}</code>)}
        </div>
      ) : null}

      {cfg.accept || cfg.folder ? (
        <div className="kitpart__acts">
          {cfg.accept ? (
            <>
              <button className="msg__act" disabled={busy} onClick={() => fileRef.current && fileRef.current.click()}>
                Upload{cfg.multiple ? ' files' : ''}
              </button>
              <input ref={fileRef} type="file" hidden accept={cfg.accept} multiple={cfg.multiple}
                onChange={e => {
                  const files = Array.from(e.target.files || []);
                  e.target.value = '';
                  if (files.length) onUpload(part.key, files);
                }} />
            </>
          ) : null}
          {cfg.folder ? (
            <button className={`msg__act ${open ? 'is-on' : ''}`} disabled={busy} onClick={() => setOpen(o => !o)}>
              Point to a folder
            </button>
          ) : null}
        </div>
      ) : null}

      {open && cfg.folder ? (
        <div className="kitimport">
          <input className="qrow__in" value={path} spellCheck={false}
            placeholder="/Users/you/Shared/Decks"
            onChange={e => setPath(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && path.trim()) onImport(part.key, path.trim(), mode); }} />
          {cfg.folder.length > 1 ? (
            <div className="kitimport__modes">
              <label><input type="radio" checked={mode === 'copy'} onChange={() => setMode('copy')} /> Copy into the kit</label>
              <label><input type="radio" checked={mode === 'link'} onChange={() => setMode('link')} /> Link in place</label>
            </div>
          ) : null}
          <div className="kitimport__why">
            {mode === 'link'
              ? 'The files stay where they are; the kit remembers the folder. Good for a large shared drive that someone else keeps up to date.'
              : 'Copies every file of the right type into the kit, so the kit works on its own. Sub-folders are included.'}
          </div>
          <button className="tplup" disabled={busy || !path.trim()}
            onClick={() => onImport(part.key, path.trim(), cfg.folder.length > 1 ? mode : 'copy')}>
            <Ico name="folder" size={15} />{mode === 'link' && cfg.folder.length > 1 ? 'Link folder' : 'Copy from folder'}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function KitPanel({ orgSlug, onClose, onKitsChanged, onUseKit, onScanned }) {
  const [kits, setKits] = useState([]);
  const [root, setRoot] = useState('');
  const [cur, setCur] = useState(null);
  const [scan, setScan] = useState(null);
  const [state, setState] = useState(API ? 'loading' : 'off');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [err, setErr] = useState('');
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [voice, setVoice] = useState('');
  const [voiceDirty, setVoiceDirty] = useState(false);
  const [picked, setPicked] = useState([]);

  function loadKits(prefer) {
    return kitCall('GET', '/api/kits').then(d => {
      const list = d.kits || [];
      setKits(list); setRoot(d.root || ''); setState('ok');
      const want = prefer || (list.some(k => k.slug === orgSlug) ? orgSlug : (list[0] && list[0].slug));
      setCur(want || null);
      if (!list.length) setCreating(true);
      return list;
    }).catch(() => setState('off'));
  }

  useEffect(() => { if (API) loadKits(); }, []);

  function take(s) {
    setScan(s);
    if (onScanned) onScanned(s);
  }

  function rescan(slug) {
    const s = slug || cur;
    if (!s) return Promise.resolve();
    setErr('');
    return kitCall('GET', `/api/kits/${encodeURIComponent(s)}`)
      .then(d => { take(d); return d; })
      .catch(e => setErr(e.message));
  }

  // A different kit: read it fresh, and start the voice editor from disk.
  useEffect(() => {
    if (!cur) { setScan(null); return; }
    setErr(''); setPicked([]);
    rescan(cur).then(d => { if (d) { setVoice(d.voice_text || ''); setVoiceDirty(false); } });
  }, [cur]);

  // Suggestions not already in the profile, ticked by default.
  const learned = scan && scan.learned;
  const fresh = ((learned && learned.suggested_rules) || []).filter(r => !((scan && scan.rules) || []).includes(r));
  const freshKey = fresh.join('|');
  useEffect(() => { setPicked(fresh); }, [freshKey]);

  async function run(label, fn) {
    setBusy(true); setErr(''); setNote('');
    try {
      const msg = await fn();
      if (msg) setNote(msg);
    } catch (e) {
      setErr(`${label}: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  function create() {
    const name = newName.trim();
    if (!name) return;
    run('Could not create the kit', async () => {
      const d = await kitCall('POST', '/api/kits', { name, description: newDesc.trim() });
      setCreating(false); setNewName(''); setNewDesc('');
      await loadKits(d.slug);
      if (onKitsChanged) onKitsChanged(d.slug);
      return `Created ${d.name} at ${d.path}. Add its parts below.`;
    });
  }

  function upload(part, files) {
    run('Upload failed', async () => {
      const fd = new FormData();
      files.forEach(f => fd.append('files', f));
      fd.append('part', part);
      const d = await kitCall('POST', `/api/kits/${encodeURIComponent(cur)}/upload`, fd);
      take(d.kit);
      return reportText(d);
    });
  }

  function importFolder(part, path, mode) {
    run('Could not read that folder', async () => {
      const d = await kitCall('POST', `/api/kits/${encodeURIComponent(cur)}/import`, { path, mode, part });
      take(d.kit);
      return reportText(d);
    });
  }

  function reveal() {
    run('Could not open the folder', async () => {
      const d = await kitCall('POST', `/api/kits/${encodeURIComponent(cur)}/reveal`);
      return `Opened ${d.opened}. Drop files in, then press Rescan.`;
    });
  }

  function learn() {
    run('Learning failed', async () => {
      const d = await kitCall('POST', `/api/kits/${encodeURIComponent(cur)}/learn`);
      take(d.kit);
      return `Read ${d.learned.decks} deck${d.learned.decks === 1 ? '' : 's'}. Review the suggested rules below.`;
    });
  }

  function addRules() {
    if (!picked.length) return;
    run('Could not add the rules', async () => {
      const d = await kitCall('POST', `/api/kits/${encodeURIComponent(cur)}/rules`, { add: picked });
      take(d);
      return `Added ${picked.length} rule${picked.length === 1 ? '' : 's'} to profile.json.`;
    });
  }

  function saveVoice() {
    run('Could not save the voice', async () => {
      const d = await kitCall('PUT', `/api/kits/${encodeURIComponent(cur)}/voice`, { text: voice });
      take(d); setVoiceDirty(false);
      return 'Saved voice.md.';
    });
  }

  const inUse = cur && cur === orgSlug;

  return (
    <div className="history kitpanel">
      <div className="history__head">
        <span className="history__title">Company kit</span>
        <div className="kitpick">
          {kits.length ? (
            <select className="orgpick__sel" value={cur || ''} onChange={e => { setNote(''); setCur(e.target.value); }}>
              {kits.map(k => <option key={k.slug} value={k.slug}>{k.name}</option>)}
            </select>
          ) : null}
          <button className={`storytab ${creating ? 'on' : ''}`} onClick={() => setCreating(c => !c)} disabled={state !== 'ok'}>
            <Ico name="new" size={13} /> New kit
          </button>
        </div>
        <button className="rail__collapse" onClick={onClose} title="Close"><Ico name="close" size={16} /></button>
      </div>

      <div className="history__scroll">
        <div className="history__inner">
          {state === 'off' ? (
            <div className="tray__empty">
              Kits live in a folder on the machine running pptgpt, and this build has no engine behind it.
              Start the local server (see SETUP.md) to set one up.
            </div>
          ) : state === 'loading' ? (
            <div className="tray__empty">Reading kits…</div>
          ) : (
            <>
              {creating ? (
                <div className="kitnew">
                  <div className="kitnew__h">New company kit</div>
                  <p className="kitpart__how">
                    Makes a folder under <code>{root || 'kits/'}</code> with starter files. You can fill it
                    from this screen, or by copying files into the folder yourself.
                  </p>
                  <input className="qrow__in" value={newName} placeholder="Company name, e.g. Acme Corp"
                    onChange={e => setNewName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') create(); }} autoFocus />
                  <input className="qrow__in" value={newDesc} placeholder="One line on how this company presents (optional)"
                    onChange={e => setNewDesc(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') create(); }} />
                  <div className="kitpart__acts">
                    <button className="tplup" disabled={busy || !newName.trim()} onClick={create}>
                      <Ico name="new" size={15} />Create kit
                    </button>
                    {kits.length ? <button className="tplclear" onClick={() => setCreating(false)}>Cancel</button> : null}
                  </div>
                </div>
              ) : null}

              {err ? <div className="tplerr">{err}</div> : null}
              {note ? <div className="kitnote">{note}</div> : null}

              {scan ? (
                <>
                  <div className="kithead">
                    <div className="kithead__txt">
                      <div className="kithead__name">{scan.name}
                        <span className="kithead__score tnum">{scan.ready}/{scan.total} ready</span>
                      </div>
                      {scan.description ? <div className="kithead__desc">{scan.description}</div> : null}
                      <code className="kithead__path">{scan.path}</code>
                    </div>
                    <div className="kithead__acts">
                      {inUse ? (
                        <span className="kithead__inuse"><Ico name="check" size={13} /> Used for this deck</span>
                      ) : (
                        <button className="tplup" onClick={() => onUseKit && onUseKit(cur)}>Use for this deck</button>
                      )}
                      <button className="msg__act" disabled={busy} onClick={reveal} title="Open this folder in Finder / Explorer">
                        Open folder
                      </button>
                      <button className="msg__act" disabled={busy} onClick={() => run('Rescan failed', async () => { await rescan(); return 'Rescanned the folder.'; })}
                        title="Read the folder again — after you copy files in by hand">
                        Rescan
                      </button>
                    </div>
                  </div>

                  <div className="kitparts">
                    {scan.parts.map(p => (
                      <KitPart key={p.key} part={p} scan={scan} busy={busy}
                        sources={(scan.sources || {})[p.key]}
                        onUpload={upload} onImport={importFolder} />
                    ))}
                  </div>

                  <section className="kitsec">
                    <div className="kitsec__h">Learn from examples</div>
                    <p className="kitpart__how">
                      Measures the example decks — points per slide, words per point, title length,
                      how often a title argues, which layouts and visuals you use. Counted from the
                      files, never guessed. The coach then judges a slide against your own decks.
                    </p>
                    <div className="kitpart__acts">
                      <button className="tplup" disabled={busy || !scan.parts.find(p => p.key === 'examples').ok} onClick={learn}>
                        <Ico name="spark" size={15} />{learned ? 'Learn again' : 'Learn from examples'}
                      </button>
                      {scan.stale ? <span className="kitstale">Examples changed since the last run.</span> : null}
                    </div>
                    <LearnedSummary learned={learned} />
                    {learned ? (
                      fresh.length ? (
                        <div className="kitrules">
                          <div className="kitrules__h">Suggested house rules — tick the ones that are true</div>
                          {fresh.map(r => (
                            <label key={r} className="kitrules__row">
                              <input type="checkbox" checked={picked.includes(r)}
                                onChange={() => setPicked(p => (p.includes(r) ? p.filter(x => x !== r) : [...p, r]))} />
                              <span>{r}</span>
                            </label>
                          ))}
                          <button className="tplup" disabled={busy || !picked.length} onClick={addRules}>
                            Add {picked.length || ''} to house rules
                          </button>
                        </div>
                      ) : (
                        <p className="kitpart__how">Every suggested rule is already in the profile.</p>
                      )
                    ) : null}
                    {(scan.rules || []).length ? (
                      <div className="kitrules kitrules--have">
                        <div className="kitrules__h">House rules in profile.json</div>
                        <ul>{scan.rules.map(r => <li key={r}>{r}</li>)}</ul>
                      </div>
                    ) : null}
                  </section>

                  <section className="kitsec">
                    <div className="kitsec__h">Writing voice</div>
                    <p className="kitpart__how">
                      Plain sentences about how you write: words you use and avoid, how formal, how
                      long. Keep it short — a small local model follows five specific rules far better
                      than a pasted style guide. Saved to <code>voice.md</code>.
                    </p>
                    <textarea className="qrow__ta kitvoice" rows={7} value={voice}
                      placeholder={'Say "customers", never "users".\nLead with the number, then what it means.\nNo exclamation marks.'}
                      onChange={e => { setVoice(e.target.value); setVoiceDirty(true); }} />
                    <div className="kitpart__acts">
                      <button className="tplup" disabled={busy || !voiceDirty} onClick={saveVoice}>Save voice</button>
                      {voiceDirty ? <span className="kitstale">Unsaved changes.</span> : null}
                    </div>
                  </section>
                </>
              ) : !creating && !kits.length ? (
                <div className="tray__empty">No kits yet.</div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { KitPanel, kitCall });
