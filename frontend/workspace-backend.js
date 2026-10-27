/* ============================================================
   workspace-backend.js — real Gemma/Ollama/Anthropic backend for
   the pptgpt workspace UI.

   Same probe-then-override pattern as frontend/realBackend.js:
   probes /health; if the server is up, wraps window.aiGenerate
   to call /api/workspace_generate. On any failure (unavailable,
   network error, malformed response) it falls through to the
   original client-side aiGenerate (canned-content fallback) —
   never a dead end.

   Also installs window.exportPptx, used by ws-app.jsx's Export
   menu to render the live deck to a real .pptx via /api/render.
   ============================================================ */
(function () {
  'use strict';

  // BU_API_BASE (set at deploy time by scripts/gen-config.mjs) points the
  // static Netlify frontend at the HF Space backend; locally it is unset and
  // the server is same-origin.
  const ORIGIN = (window.BU_API_BASE || '').replace(/\/$/, '')
    || ((location.protocol === 'http:' || location.protocol === 'https:')
      ? location.origin
      : null);

  // file://, or a static deploy that declares it has no engine behind it —
  // either way, keep the client-only canned generator and probe nothing.
  if (!ORIGIN || window.WS_NO_BACKEND) return;

  async function probe() {
    try {
      const res = await fetch(ORIGIN + '/health', { method: 'GET' });
      return res.ok;
    } catch (_) { return false; }
  }

  probe().then((ok) => {
    if (!ok) {
      console.info('[workspace-backend] /health unreachable — using client-side generator.');
      return;
    }

    const clientGenerate = window.aiGenerate;

    window.aiGenerate = async function (req) {
      const { feature, prompt, audience, files, current, palette } = req;
      try {
        const res = await fetch(ORIGIN + '/api/workspace_generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            feature, prompt, audience, current, palette,
            fileNames: (files || []).map(f => f.name),
          }),
        });
        if (!res.ok) throw new Error('workspace_generate -> ' + res.status);
        const data = await res.json();
        if (!data.available) throw new Error(data.reason || 'model unavailable');

        if (feature === 'condense') {
          const arr = Array.isArray(data.slide) ? data.slide : [data.slide];
          return arr.slice(0, 5).map(s => ({
            id: window.uid(), palette: palette || 'warm',
            emphasis: (audience === 'conf') ? 'story' : 'number',
            kind: s.kind || 'text', ...s,
          }));
        }
        const id = (feature === 'refine' && current) ? current.id : window.uid();
        return {
          id, palette: palette || (current && current.palette) || 'warm',
          emphasis: (audience === 'conf') ? 'story' : (current && current.emphasis) || 'number',
          kind: data.slide.kind || 'text', ...data.slide,
        };
      } catch (e) {
        console.warn('[workspace-backend] generation failed, using client-side fallback:', e.message);
        return clientGenerate(req);
      }
    };

    window.exportPptx = async function (slides) {
      const specs = slides.map(s => window.slideToSpec(s));
      const res = await fetch(ORIGIN + '/api/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slides: specs }),
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

    console.info('[workspace-backend] connected to /api — real generation + export installed.');
  });
})();
