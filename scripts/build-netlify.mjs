// Build the Netlify publish directory from frontend/ sources.
//
// netlify-dist/ used to be a hand-maintained copy of the frontend. That fork
// is how the unified workspace UI (frontend/ws-*.jsx) shipped to git but never
// reached the deployed site: nothing copied it across. netlify-dist/ is now
// generated and gitignored; edit frontend/ and let this script assemble it.
//
//   node scripts/build-netlify.mjs
//
// The transform from source to deployed page is small and mechanical:
//   1. relative asset refs become root-absolute, since the dist is flat while
//      the sources sit in nested directories;
//   2. every page gets /config.js (the BU_API_BASE injection), which must
//      land before any backend shim reads window.BU_API_BASE.

import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "frontend");
const out = join(root, "netlify-dist");

// Files copied through untouched, as `source (relative to frontend/) -> dist name`.
const ASSETS = [
  // landing, setup, storyboard, workbench
  ["landing.css", "landing.css"],
  ["landing.jsx", "landing.jsx"],
  ["setup.css", "setup.css"],
  ["setup.jsx", "setup.jsx"],
  ["storyboard-v2.css", "storyboard-v2.css"],
  ["storyboard-v2.jsx", "storyboard-v2.jsx"],
  ["workbench-v2.css", "workbench-v2.css"],
  ["workbench-v2.jsx", "workbench-v2.jsx"],
  ["mockBackend.js", "mockBackend.js"],
  ["previewRenderer.jsx", "previewRenderer.jsx"],
  ["samples", "samples"],
  ["vendor", "vendor"],

  // unified workspace
  ["workspace.css", "workspace.css"],
  ["ws-app.jsx", "ws-app.jsx"],
  ["ws-slide.jsx", "ws-slide.jsx"],
  ["ws-dash.jsx", "ws-dash.jsx"],
  ["ws-story.jsx", "ws-story.jsx"],
  ["ws-phases.jsx", "ws-phases.jsx"],
  ["ws-data.js", "ws-data.js"],
  ["ws-template.jsx", "ws-template.jsx"],
  ["ws-coach.jsx", "ws-coach.jsx"],
  ["ws-scores.jsx", "ws-scores.jsx"],
  ["ws-annotate.jsx", "ws-annotate.jsx"],
  ["ws-review.jsx", "ws-review.jsx"],
  ["ws-kit.jsx", "ws-kit.jsx"],
  ["ws-library.jsx", "ws-library.jsx"],
  ["ws-thread.jsx", "ws-thread.jsx"],
  ["ws-demo-seed.js", "ws-demo-seed.js"],
  ["ws-export.js", "ws-export.js"],
  ["workspace-backend.js", "workspace-backend.js"],
];

// Pages, as `source -> dist name`. Each is rewritten by transformHtml().
const PAGES = [
  // The workspace IS the product, so it owns "/". The marketing landing page
  // keeps its own URL at /landing for linking, but no longer gates the app
  // behind a splash screen.
  ["workspace.html", "index.html"],
  ["workspace.html", "workspace.html"],
  ["landing.html", "landing.html"],
  ["setup.html", "setup.html"],
  ["storyboard-v2.html", "storyboard.html"],
  ["workbench-v2.html", "workbench.html"],
];

/** Rewrite a source page for the flat dist. */
function transformHtml(html, { isWorkspace = false } = {}) {
  // Root-absolute asset refs. Anything already absolute, protocol-relative or
  // a full URL is left alone, as are in-page anchors and data: URIs.
  html = html.replace(
    /\b(src|href)="(?!https?:|\/\/|\/|#|data:|mailto:)([^"]+)"/g,
    (_m, attr, path) => `${attr}="/${path}"`,
  );

  // The static deploy has no backend, so the workspace opens on a canned
  // deck instead of an empty shell. Seeded before the app script runs, and
  // only here — local dev has a real engine and should open empty.
  const seed = isWorkspace ? '  <script src="/ws-demo-seed.js"></script>\n' : '';
  const injected = '  <script src="/config.js"></script>\n' + seed;

  // Inject right after </title> so the config is in place before any other
  // script runs.
  if (!/<\/title>/.test(html)) throw new Error("page has no <title> to anchor the injection");
  return html.replace(/<\/title>\s*\n/, (m) => m + injected);
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

for (const [from, to] of ASSETS) {
  const abs = join(src, from);
  if (!existsSync(abs)) throw new Error(`missing asset: frontend/${from}`);
  cpSync(abs, join(out, to), { recursive: true });
}

for (const [from, to] of PAGES) {
  const abs = join(src, from);
  if (!existsSync(abs)) throw new Error(`missing page: frontend/${from}`);
  const isWorkspace = from === "workspace.html";
  writeFileSync(join(out, to), transformHtml(readFileSync(abs, "utf8"), { isWorkspace }));
}

// Fail the build rather than publish a broken site — Netlify keeps the last
// good deploy when the build command exits non-zero.
for (const [, name] of [...ASSETS, ...PAGES]) {
  const abs = join(out, name);
  if (!existsSync(abs)) throw new Error(`build produced no ${name}`);
  const st = statSync(abs);
  if (!st.isDirectory() && st.size === 0) throw new Error(`build produced an empty ${name}`);
}

// Every local asset a built page references must exist in the dist. A page
// referencing a file that ASSETS forgot is the exact failure this build
// replaces — a silently missing script that only shows up as a blank page.
// config.js is written afterwards by gen-config.mjs, so it is exempt.
const missing = [];
for (const [, name] of PAGES) {
  const html = readFileSync(join(out, name), "utf8");
  for (const [, ref] of html.matchAll(/\b(?:src|href)="\/([^"?#]+)/g)) {
    if (ref !== "config.js" && !existsSync(join(out, ref))) missing.push(`${name} -> /${ref}`);
  }
}
if (missing.length) throw new Error(`dangling asset refs:\n  ${missing.join("\n  ")}`);

console.log(`[build-netlify] ${ASSETS.length} assets + ${PAGES.length} pages -> netlify-dist/`);
