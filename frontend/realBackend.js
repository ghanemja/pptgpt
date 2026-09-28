/* ============================================================
   realBackend.js — HTTP wrapper that overrides the mock.

   Loads AFTER mockBackend.js. Probes /health; if the server is up,
   it replaces window.mockBackend / window.extractStoryboard /
   window.generateCritique with fetch() versions that hit the
   matching /api/* routes. Same shapes, same semantics.

   If the probe fails (e.g. opened via file:// with no server),
   the mock implementations stay in place — the UI keeps working.
   ============================================================ */
(function () {
  'use strict';

  // Resolve base. BU_API_BASE (set at deploy time by scripts/gen-config.mjs)
  // points the static Netlify frontend at the HF Space backend; locally it is
  // unset and the server is same-origin.
  // When opened via file://, location.origin is "file://" — force null in that
  // case so we never even try a relative fetch.
  const ORIGIN = (window.BU_API_BASE || '').replace(/\/$/, '')
    || ((location.protocol === 'http:' || location.protocol === 'https:')
      ? location.origin
      : null);

  if (!ORIGIN) return;  // file:// — keep the local mock

  async function post(path, body) {
    const res = await fetch(ORIGIN + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) throw new Error('backend ' + path + ' -> ' + res.status);
    return res.json();
  }

  async function probe() {
    try {
      const res = await fetch(ORIGIN + '/health', { method: 'GET' });
      return res.ok;
    } catch (_) { return false; }
  }

  // Keep references to the mocks; we'll fall back to them on network error.
  const mockBackend       = window.mockBackend;
  const mockStoryboard    = window.extractStoryboard;
  const mockCritique      = window.generateCritique;

  function withFallback(name, mock, path) {
    return async function (req) {
      try { return await post(path, req); }
      catch (e) {
        console.warn('[realBackend] ' + name + ' failed, using mock:', e.message);
        if (mock) return mock(req);
        throw e;
      }
    };
  }

  probe().then((ok) => {
    if (!ok) {
      console.info('[realBackend] /health unreachable — using local mock.');
      return;
    }
    window.mockBackend       = withFallback('mockBackend',       mockBackend,    '/api/backend');
    window.extractStoryboard = withFallback('extractStoryboard', mockStoryboard, '/api/storyboard');
    window.generateCritique  = withFallback('generateCritique',  mockCritique,   '/api/critique');

    // Also expose a server-side .pptx export the workbench can call.
    // The mock has no equivalent — UI checks for window.exportPptx before showing the button.
    window.exportPptx = async function (slides) {
      const res = await fetch(ORIGIN + '/api/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slides }),
      });
      if (!res.ok) throw new Error('export ' + res.status);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'deck.pptx';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    };

    console.info('[realBackend] connected to /api — overrides installed.');
  });
})();
