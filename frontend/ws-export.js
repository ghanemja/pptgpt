/* ============================================================
   ws-export.js — deterministic ws-slide → SlideSpec converter
   ------------------------------------------------------------
   Maps a ws-slide.jsx slide object (kind/eyebrow/title/metric/
   bullets/takeaway/chart/plot/palette/footer/page) to the
   existing SlideSpec block contract (frontend/types.md), using
   fixed per-kind geometry that mirrors SlideCard's own layout.
   Pure function — no LLM output ever reaches these coordinates;
   only the deterministic mapping below does (§0).
   ============================================================ */
(function () {
  'use strict';

  const CANVAS_W = 1280, CANVAS_H = 720;
  const SCALE = CANVAS_W / 720;          // SlideCard's own design box is 720x405
  const PT = px => Math.round(px * SCALE * 0.75);   // px (SlideCard) -> pt @96dpi
  const X = px => Math.round(px * SCALE);

  function pal(slide) {
    const p = (window.PALETTES && window.PALETTES[slide.palette]) || (window.PALETTES && window.PALETTES.warm) || {};
    return {
      bg: p.bg || '#FFFFFF', ink: p.ink || '#11120E', sub: p.sub || '#3D3F38',
      mute: p.mute || '#807C6E', accent: p.accent || '#0E5B36', spark: p.spark || '#E26A2C',
    };
  }

  function eyebrowBlock(slide, p, y) {
    return { type: 'text', x: X(48), y: X(y), w: X(500), h: X(24),
      text: slide.eyebrow || '', font: 'sans', size: PT(13), weight: 700,
      color: p.mute, align: 'left', transform: 'uppercase', letterSpacing: 0.12 };
  }

  function takeawayBlock(slide, p, y, h) {
    if (!slide.takeaway) return null;
    return { type: 'text', x: X(48), y: X(y), w: X(624), h: X(h),
      text: '“' + slide.takeaway + '”', font: 'serif', size: PT(16), italic: true,
      weight: 700, color: p.accent, lineHeight: 1.4 };
  }

  function footerBlock(slide, p) {
    if (!slide.footer) return null;
    return { type: 'text', x: X(48), y: X(383), w: X(500), h: X(16),
      text: slide.footer, font: 'sans', size: PT(10.5), weight: 700, color: p.mute };
  }

  function slideToSpec(slide) {
    const p = pal(slide);
    const blocks = [];

    if (slide.kind === 'cover') {
      blocks.push({ type: 'text', x: X(58), y: X(54), w: X(500), h: X(24),
        text: slide.eyebrow || '', font: 'sans', size: PT(13), weight: 700,
        color: p.spark, transform: 'uppercase', letterSpacing: 0.16 });
      blocks.push({ type: 'text', x: X(58), y: X(80), w: X(600), h: X(120),
        text: slide.title || '', font: 'sans', size: PT(46), weight: 900, color: p.ink, lineHeight: 1.04 });
      if (slide.subtitle) {
        blocks.push({ type: 'text', x: X(58), y: X(210), w: X(520), h: X(80),
          text: slide.subtitle, font: 'sans', size: PT(19), weight: 500, color: p.sub, lineHeight: 1.4 });
      }
      blocks.push({ type: 'text', x: X(58), y: X(370), w: X(300), h: X(16),
        text: slide.footer || '', font: 'sans', size: PT(12), weight: 700, color: p.mute });
      blocks.push({ type: 'text', x: X(500), y: X(370), w: X(180), h: X(16),
        text: slide.date || '', font: 'sans', size: PT(12), weight: 700, color: p.mute, align: 'right' });
      return { canvasW: CANVAS_W, canvasH: CANVAS_H, palette: { bg: p.bg, ink: p.ink, accent: p.accent, muted: p.mute }, blocks };
    }

    blocks.push(eyebrowBlock(slide, p, 44));

    if (slide.kind === 'chart' && slide.chart) {
      blocks.push({ type: 'text', x: X(48), y: X(70), w: X(624), h: X(48),
        text: slide.title || '', font: 'sans', size: PT(30), weight: 900, color: p.ink, lineHeight: 1.1 });
      blocks.push({ type: 'text', x: X(48), y: X(118), w: X(400), h: X(18),
        text: slide.chart.title || '', font: 'sans', size: PT(13), weight: 700, color: p.mute });
      blocks.push({ type: 'chart', x: X(48), y: X(140), w: X(624), h: X(176),
        kind: 'bar', data: slide.chart.data || [], bg: p.bg, primaryColor: p.accent,
        labelColor: p.mute, gridColor: p.bg, axisColor: p.mute, showValueLabels: true });
      const tk = takeawayBlock(slide, p, 335, 40); if (tk) blocks.push(tk);
      const ft = footerBlock(slide, p); if (ft) blocks.push(ft);
      return { canvasW: CANVAS_W, canvasH: CANVAS_H, palette: { bg: p.bg, ink: p.ink, accent: p.accent, muted: p.mute }, blocks };
    }

    if (slide.kind === 'plot' && slide.plot) {
      blocks.push({ type: 'text', x: X(48), y: X(70), w: X(624), h: X(48),
        text: slide.title || '', font: 'sans', size: PT(28), weight: 900, color: p.ink, lineHeight: 1.1 });
      if (slide.plot.eq) {
        blocks.push({ type: 'text', x: X(48), y: X(118), w: X(500), h: X(24),
          text: slide.plot.eq, font: 'serif', size: PT(18), weight: 700, color: p.accent });
      }
      const params = slide.plot.params || {};
      blocks.push({ type: 'plot', x: X(48), y: X(150), w: X(624), h: X(170),
        bg: p.bg, xRange: [0, 6], yRange: [-1.1, 1.1], showAxes: true, showGrid: false,
        axisColor: p.mute, curves: [{ fn: slide.plot.fn || 'damped', params, color: p.accent, width: 2.4 }] });
      const tk = takeawayBlock(slide, p, 335, 40); if (tk) blocks.push(tk);
      const ft = footerBlock(slide, p); if (ft) blocks.push(ft);
      return { canvasW: CANVAS_W, canvasH: CANVAS_H, palette: { bg: p.bg, ink: p.ink, accent: p.accent, muted: p.mute }, blocks };
    }

    // text slide
    const story = slide.emphasis === 'story';
    blocks.push({ type: 'text', x: X(48), y: X(70), w: X(624), h: X(60),
      text: slide.title || '', font: 'sans', size: PT(story ? 40 : 33), weight: 900, color: p.ink, lineHeight: 1.08 });

    let contentX = 48, contentW = 624;
    if (slide.metric && !story) {
      blocks.push({ type: 'text', x: X(48), y: X(150), w: X(200), h: X(70),
        text: String(slide.metric), font: 'sans', size: PT(68), weight: 900, color: p.accent, lineHeight: 0.95 });
      if (slide.metricSub) {
        blocks.push({ type: 'text', x: X(48), y: X(224), w: X(190), h: X(40),
          text: slide.metricSub, font: 'sans', size: PT(13), weight: 700, color: p.mute });
      }
      contentX = 250; contentW = 422;
    }
    if (Array.isArray(slide.bullets) && slide.bullets.length) {
      blocks.push({ type: 'bullets', x: X(contentX), y: X(150), w: X(contentW), h: X(150),
        items: slide.bullets.slice(0, story ? 3 : 4), font: 'sans', size: PT(16.5), weight: 400,
        color: p.sub, marker: 'dash', markerColor: p.spark, lineHeight: 1.4, gap: X(12) });
    }
    const tk = takeawayBlock(slide, p, 335, 40); if (tk) blocks.push(tk);
    const ft = footerBlock(slide, p); if (ft) blocks.push(ft);
    return { canvasW: CANVAS_W, canvasH: CANVAS_H, palette: { bg: p.bg, ink: p.ink, accent: p.accent, muted: p.mute }, blocks };
  }

  Object.assign(window, { slideToSpec });
})();
