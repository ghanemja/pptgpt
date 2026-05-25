/* ============================================================
   previewRenderer.jsx
   ------------------------------------------------------------
   Renders a SlideSpec (slideIR or previewSpec) verbatim.

   The UI MUST NOT decide colors, sizes, or placement. Every
   visual property is read from the block.

   Block types: text | rect | bullets | rule | tag | plot
   ============================================================ */

// ── Curated math function registry (referenced by PlotBlock.curves[].fn) ──
// New entries only — the UI never invents formulas. Backends send a fn id
// from this map plus a params object.
const PLOT_FNS = {
  sine:        (x, p) => (p.A ?? 1) * Math.sin((p.omega ?? 1) * x + (p.phi ?? 0)),
  cosine:      (x, p) => (p.A ?? 1) * Math.cos((p.omega ?? 1) * x + (p.phi ?? 0)),
  damped:      (x, p) => (p.A ?? 1) * Math.exp(-(p.gamma ?? 0.2) * x) * Math.cos((p.omega ?? 2) * x),
  gaussian:    (x, p) => (p.A ?? 1) * Math.exp(-Math.pow((x - (p.mu ?? 0)) / (p.sigma ?? 1), 2) / 2),
  exponential: (x, p) => (p.A ?? 1) * Math.exp((p.k ?? 1) * x),
  polynomial:  (x, p) => (p.a ?? 0) * x * x * x + (p.b ?? 0) * x * x + (p.c ?? 1) * x + (p.d ?? 0),
  sigmoid:     (x, p) => (p.A ?? 1) / (1 + Math.exp(-(p.k ?? 1) * (x - (p.x0 ?? 0)))),
};
window.PLOT_FNS = PLOT_FNS;

function fontFamilyOf(font) {
  if (font === 'serif') return 'var(--font-serif)';
  if (font === 'mono')  return 'var(--font-mono)';
  return 'var(--font-sans)';
}

function PreviewBlock({ block, scale, plotParams }) {
  const px = (v) => `${v * scale}px`;
  const baseBox = {
    position: 'absolute',
    left:   px(block.x),
    top:    px(block.y),
    width:  px(block.w),
    height: px(block.h),
  };

  if (block.type === 'text') {
    const ls = block.letterSpacing != null ? block.letterSpacing : block.tracking;
    return (
      <div style={{
        ...baseBox,
        fontFamily:    fontFamilyOf(block.font),
        fontSize:      px(block.size),
        fontWeight:    block.weight || 400,
        fontStyle:     block.italic ? 'italic' : 'normal',
        lineHeight:    block.lineHeight || 1.2,
        color:         block.color,
        textAlign:     block.align || 'left',
        letterSpacing: ls != null ? `${ls}em` : 'normal',
        textTransform: block.transform || 'none',
        whiteSpace:    'pre-wrap',
        overflow:      'hidden',
      }}>{block.text}</div>
    );
  }

  if (block.type === 'rect') {
    return (
      <div style={{
        ...baseBox,
        background:   block.fill,
        borderRadius: block.radius ? px(block.radius) : 0,
      }} />
    );
  }

  if (block.type === 'rule') {
    const thickness = block.thickness != null ? block.thickness : block.h;
    // Render as a filled rect of the proper thickness
    return (
      <div style={{
        position: 'absolute',
        left:   px(block.x),
        top:    px(block.y),
        width:  px(block.w),
        height: px(thickness),
        background: block.color,
      }} />
    );
  }

  if (block.type === 'tag') {
    const size = block.size || 14;
    return (
      <div style={{
        ...baseBox,
        background:    block.fill,
        color:         block.color,
        fontFamily:    'var(--font-mono)',
        fontSize:      px(size),
        fontWeight:    600,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        display:       'inline-flex',
        alignItems:    'center',
        justifyContent:'center',
        padding:       `0 ${px(size * 0.8)}`,
        borderRadius:  px(size * 1.6),
        width:         'fit-content',
      }}>{block.text}</div>
    );
  }

  if (block.type === 'bullets') {
    const items = block.items || [];
    const size = block.size;
    const gap = block.gap != null ? block.gap : 6;
    const marker = block.marker || 'dot';
    const markerColor = block.markerColor || block.color;
    return (
      <div style={{
        ...baseBox,
        fontFamily: fontFamilyOf(block.font),
        fontSize:   px(size),
        fontWeight: block.weight || 400,
        lineHeight: block.lineHeight || 1.45,
        color:      block.color,
      }}>
        {items.map((item, i) => {
          let m;
          if (marker === 'none')   m = null;
          else if (marker === 'dash')   m = '—';
          else if (marker === 'number') m = `${String(i + 1).padStart(2, '0')}`;
          else m = '•';
          return (
            <div className="sb-bullets-row" key={i} style={{
              marginBottom: px(gap),
              gap: px(size * 0.5),
            }}>
              {m !== null && (
                <span className="marker" style={{
                  color: markerColor,
                  minWidth: marker === 'number' ? px(size * 1.4) : px(size * 0.8),
                  fontFamily: marker === 'number' ? 'var(--font-mono)' : 'inherit',
                  fontWeight: marker === 'number' ? 500 : 400,
                  fontSize:   marker === 'number' ? px(size * 0.85) : px(size),
                  lineHeight: block.lineHeight || 1.45,
                  letterSpacing: marker === 'number' ? '0.05em' : 'normal',
                }}>{m}</span>
              )}
              <span className="body">{item}</span>
            </div>
          );
        })}
      </div>
    );
  }

  if (block.type === 'plot') {
    // The plot is rendered into an SVG sized to the block. We use canvas
    // coords for the SVG viewBox so the rest of the renderer's `scale`
    // logic just transforms the container — strokes / ticks stay crisp.
    const w = block.w;
    const h = block.h;
    const [x0, x1] = block.xRange || [-Math.PI * 2, Math.PI * 2];
    const [y0, y1] = block.yRange || [-2, 2];
    const padL = block.paddingLeft   ?? 28;
    const padR = block.paddingRight  ?? 12;
    const padT = block.paddingTop    ?? 16;
    const padB = block.paddingBottom ?? 28;
    const innerW = w - padL - padR;
    const innerH = h - padT - padB;
    const sx = (x) => padL + ((x - x0) / (x1 - x0)) * innerW;
    const sy = (y) => padT + (1 - (y - y0) / (y1 - y0)) * innerH;

    const tickColor   = block.tickColor     || 'rgba(255,255,255,0.28)';
    const gridColor   = block.gridColor     || 'rgba(255,255,255,0.06)';
    const axisColor   = block.axisColor     || 'rgba(255,255,255,0.6)';
    const labelColor  = block.tickLabelColor|| 'rgba(255,255,255,0.55)';
    const bg          = block.bg            || '#0f1226';
    const xTicks      = block.xTicks        || niceTicks(x0, x1, 6);
    const yTicks      = block.yTicks        || niceTicks(y0, y1, 4);

    const curves = (block.curves || []).map((c) => {
      const fn = PLOT_FNS[c.fn];
      if (!fn) return null;
      const mergedParams = { ...(c.params || {}), ...(plotParams || {}) };
      const n = c.samples || 240;
      const path = [];
      let prevValid = false;
      for (let i = 0; i <= n; i++) {
        const x = x0 + (x1 - x0) * (i / n);
        let y;
        try { y = fn(x, mergedParams); } catch (e) { y = NaN; }
        const valid = Number.isFinite(y) && y >= y0 - (y1 - y0) * 0.5 && y <= y1 + (y1 - y0) * 0.5;
        if (!valid) { prevValid = false; continue; }
        const cmd = prevValid ? 'L' : 'M';
        path.push(`${cmd}${sx(x).toFixed(2)},${sy(y).toFixed(2)}`);
        prevValid = true;
      }
      return { d: path.join(' '), color: c.color || '#4ec5ff', width: c.width || 2.5, dash: c.dash };
    }).filter(Boolean);

    return (
      <div style={{
        ...baseBox,
        background: bg,
        borderRadius: block.radius ? px(block.radius) : 0,
        overflow: 'hidden',
      }}>
        <svg
          width="100%" height="100%" viewBox={`0 0 ${w} ${h}`}
          preserveAspectRatio="none"
          style={{ display: 'block' }}
        >
          {/* grid lines */}
          {block.showGrid !== false && xTicks.map((t, i) => (
            <line key={`gx${i}`} x1={sx(t)} y1={padT} x2={sx(t)} y2={padT + innerH} stroke={gridColor} strokeWidth={1} />
          ))}
          {block.showGrid !== false && yTicks.map((t, i) => (
            <line key={`gy${i}`} x1={padL} y1={sy(t)} x2={padL + innerW} y2={sy(t)} stroke={gridColor} strokeWidth={1} />
          ))}

          {/* axes (x=0, y=0) */}
          {block.showAxes !== false && y0 < 0 && y1 > 0 && (
            <line x1={padL} y1={sy(0)} x2={padL + innerW} y2={sy(0)} stroke={axisColor} strokeWidth={1.2} />
          )}
          {block.showAxes !== false && x0 < 0 && x1 > 0 && (
            <line x1={sx(0)} y1={padT} x2={sx(0)} y2={padT + innerH} stroke={axisColor} strokeWidth={1.2} />
          )}

          {/* tick marks + labels */}
          {block.showTickLabels !== false && xTicks.map((t, i) => (
            <g key={`tx${i}`}>
              <line x1={sx(t)} y1={padT + innerH} x2={sx(t)} y2={padT + innerH + 4} stroke={tickColor} strokeWidth={1} />
              <text x={sx(t)} y={padT + innerH + 16} fill={labelColor} fontSize={10}
                    fontFamily="var(--font-mono)" textAnchor="middle">{formatTick(t)}</text>
            </g>
          ))}
          {block.showTickLabels !== false && yTicks.map((t, i) => (
            <g key={`ty${i}`}>
              <line x1={padL - 4} y1={sy(t)} x2={padL} y2={sy(t)} stroke={tickColor} strokeWidth={1} />
              <text x={padL - 6} y={sy(t) + 3} fill={labelColor} fontSize={10}
                    fontFamily="var(--font-mono)" textAnchor="end">{formatTick(t)}</text>
            </g>
          ))}

          {/* curves */}
          {curves.map((c, i) => (
            <path key={`c${i}`} d={c.d} stroke={c.color} strokeWidth={c.width}
                  fill="none"
                  strokeLinecap="round" strokeLinejoin="round"
                  strokeDasharray={c.dash || 'none'} />
          ))}

          {/* axis labels */}
          {block.xLabel && (
            <text x={padL + innerW} y={padT + innerH + 16} fill={labelColor} fontSize={11}
                  fontFamily="var(--font-serif)" fontStyle="italic" textAnchor="end">
              {block.xLabel}
            </text>
          )}
          {block.yLabel && (
            <text x={padL - 4} y={padT - 4} fill={labelColor} fontSize={11}
                  fontFamily="var(--font-serif)" fontStyle="italic" textAnchor="end">
              {block.yLabel}
            </text>
          )}
        </svg>
      </div>
    );
  }

  if (block.type === 'chart') {
    // Real-data bar / line charts. Same scale-everything-via-viewBox trick
    // as the plot block, so strokes stay crisp.
    const w = block.w, h = block.h;
    const data = block.data || [];
    const kind = block.kind || 'bar';
    const padL = block.paddingLeft   ?? 48;
    const padR = block.paddingRight  ?? 24;
    const padT = block.paddingTop    ?? 24;
    const padB = block.paddingBottom ?? 44;
    const innerW = w - padL - padR;
    const innerH = h - padT - padB;
    const bg          = block.bg            || '#FFFFFF';
    const primaryC    = block.primaryColor  || '#1E2761';
    const secondaryC  = block.secondaryColor;
    const axisColor   = block.axisColor     || '#E5E7EB';
    const gridColor   = block.gridColor     || '#F1F5F9';
    const labelColor  = block.labelColor    || '#6C7A89';
    const valueLabel  = block.showValueLabels !== false;

    // Y domain
    const vals = data.flatMap(d => [d.value, d.secondary].filter(v => v != null));
    const vMax = block.yMax != null ? block.yMax : (vals.length ? Math.max(...vals) : 1);
    const vMin = block.yMin != null ? block.yMin : (vals.length ? Math.min(0, ...vals) : 0);
    const range = (vMax - vMin) || 1;
    const sy = (v) => padT + (1 - (v - vMin) / range) * innerH;

    // Y ticks (4)
    const ticks = [vMin, vMin + range/3, vMin + 2*range/3, vMax].map(v => Number(v.toFixed(2)));

    return (
      <div style={{
        ...baseBox, background: bg,
        borderRadius: block.radius ? px(block.radius) : 0,
        overflow: 'hidden',
      }}>
        <svg width="100%" height="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: 'block' }}>
          {/* horizontal grid */}
          {ticks.map((t, i) => (
            <g key={'gy' + i}>
              <line x1={padL} y1={sy(t)} x2={padL + innerW} y2={sy(t)} stroke={gridColor} strokeWidth={1} />
              <text x={padL - 8} y={sy(t) + 4} fill={labelColor} fontSize={11}
                    fontFamily="var(--font-mono)" textAnchor="end">{formatTick(t)}</text>
            </g>
          ))}
          {/* x axis */}
          <line x1={padL} y1={padT + innerH} x2={padL + innerW} y2={padT + innerH} stroke={axisColor} strokeWidth={1} />
          {kind === 'bar' && (() => {
            const n = data.length;
            if (n === 0) return null;
            const grouped = secondaryC ? 2 : 1;
            const slot = innerW / n;
            const barW = Math.max(2, (slot * 0.62) / grouped);
            const gap = (slot - barW * grouped) / 2;
            return data.map((d, i) => {
              const xBase = padL + i * slot + gap;
              const y0 = sy(d.value);
              const y1 = sy(0);
              const cy = (yTop, yBot) => {
                const top = Math.min(yTop, yBot);
                const ht = Math.max(2, Math.abs(yBot - yTop));
                return { y: top, h: ht };
              };
              const main = cy(y0, y1);
              return (
                <g key={'bar' + i}>
                  <rect x={xBase} y={main.y} width={barW} height={main.h} fill={primaryC} rx={2} />
                  {secondaryC && d.secondary != null && (() => {
                    const sec = cy(sy(d.secondary), sy(0));
                    return <rect x={xBase + barW + 4} y={sec.y} width={barW} height={sec.h} fill={secondaryC} rx={2} />;
                  })()}
                  {valueLabel && (
                    <text x={xBase + barW / 2} y={main.y - 6} fill={primaryC}
                          fontSize={12} fontWeight={500} fontFamily="var(--font-mono)" textAnchor="middle">
                      {formatTick(d.value)}
                    </text>
                  )}
                  <text x={xBase + (secondaryC ? barW + 2 : barW / 2)} y={padT + innerH + 18}
                        fill={labelColor} fontSize={11} fontFamily="var(--font-mono)" textAnchor="middle">
                    {d.label}
                  </text>
                </g>
              );
            });
          })()}
          {kind === 'line' && data.length > 0 && (() => {
            const n = data.length;
            const slot = innerW / Math.max(n - 1, 1);
            const pts = data.map((d, i) => ({ x: padL + i * slot, y: sy(d.value) }));
            const path = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p.x.toFixed(2) + ',' + p.y.toFixed(2)).join(' ');
            return (
              <g>
                <path d={path} stroke={primaryC} strokeWidth={2.5} fill="none" strokeLinejoin="round" strokeLinecap="round" />
                {pts.map((p, i) => (
                  <circle key={'pt' + i} cx={p.x} cy={p.y} r={3.5} fill={bg} stroke={primaryC} strokeWidth={2} />
                ))}
                {data.map((d, i) => (
                  <text key={'lx' + i} x={pts[i].x} y={padT + innerH + 18} fill={labelColor}
                        fontSize={11} fontFamily="var(--font-mono)" textAnchor="middle">{d.label}</text>
                ))}
              </g>
            );
          })()}
        </svg>
      </div>
    );
  }

  return null;
}

function niceTicks(min, max, count) {
  const range = max - min;
  const rough = range / Math.max(count, 2);
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / mag;
  let step;
  if      (norm < 1.5) step = 1 * mag;
  else if (norm < 3)   step = 2 * mag;
  else if (norm < 7)   step = 5 * mag;
  else                 step = 10 * mag;
  const out = [];
  const start = Math.ceil(min / step) * step;
  for (let v = start; v <= max + 1e-9; v += step) {
    out.push(Math.abs(v) < 1e-9 ? 0 : Number(v.toFixed(6)));
  }
  return out;
}
function formatTick(v) {
  if (v === 0) return '0';
  const abs = Math.abs(v);
  if (abs >= 100) return v.toFixed(0);
  if (abs >= 10)  return v.toFixed(0);
  if (abs >= 1)   return v.toFixed(1).replace(/\.0$/, '');
  return v.toFixed(2).replace(/0$/, '');
}

function SlidePreview({ spec, width, height, plotParams }) {
  if (!spec) return null;
  const sx = width  / spec.canvasW;
  const sy = height / spec.canvasH;
  // Keep aspect: use the smaller scale to avoid distortion if caller
  // passes a wrong ratio. But normally caller passes the right ratio.
  const scale = Math.min(sx, sy);
  const renderedW = spec.canvasW * scale;
  const renderedH = spec.canvasH * scale;

  return (
    <div style={{
      position: 'relative',
      width:  renderedW,
      height: renderedH,
      background: spec.palette.bg,
      overflow: 'hidden',
    }}>
      {spec.blocks.map((b, i) => <PreviewBlock key={i} block={b} scale={scale} plotParams={plotParams} />)}
    </div>
  );
}

// Extract param schema from any plot blocks in a spec — used by hosts that
// want to render slider chrome for a slide that contains a plot.
function extractPlotParamSchema(spec) {
  if (!spec || !spec.blocks) return [];
  const out = [];
  const seen = new Set();
  for (const b of spec.blocks) {
    if (b.type === 'plot' && Array.isArray(b.paramSchema)) {
      for (const p of b.paramSchema) {
        if (seen.has(p.name)) continue;
        seen.add(p.name);
        out.push(p);
      }
    }
  }
  return out;
}

// expose to window so app.jsx can use them across script scopes
window.SlidePreview = SlidePreview;
window.PreviewBlock = PreviewBlock;
window.extractPlotParamSchema = extractPlotParamSchema;
