/* Algogenesis — the Coast as a devotional print.

   The same living world, drawn in the visual language of the popular devotional prints made in India's studio presses
   between 1860 and 1930 (chromolithographs, hand-coloured lithographs and woodblock prints from Calcutta, Poona, Bombay,
   Nathdwara): jewel colours under varnish, gold and lotus ornament, the print running to the edge of the window. The surface is a
   block print's: stippled, sponged colour, every shape outlined in ink with a light rim inside, calligraphic curls on the
   water. Ornament and manner only: no figures of deities and no copies of particular prints.

   Loaded before panel.js, it sets window.ALGO_SKIN; panel.js calls these hooks in place of its own drawing. */
(function () {
  'use strict';
  const INK = '#231a1c', CREAM = '#f4ead2', VERM = '#c8402a', MAROON = '#6e221d', SAFF = '#e3a72f', GOLD = '#d4a537';
  const TEAL = '#2c5e6a', DEEP = '#1d3f52', ROSE = '#e59c88', LAPIS = '#4f70c2', OLIVE = '#7f9a4f', LEAF = '#2f4a3a';
  const rgb = h => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const mix = (a, b, k) => a.map((v, i) => Math.round(v + (b[i] - v) * k));
  const css = c => `rgb(${c[0]},${c[1]},${c[2]})`;
  // small deterministic noise, so the stipple is the same every time the land is painted
  const hash = (x, y) => { let h = (x * 374761393 + y * 668265263) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
  function vnoise(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi, sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
    const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
  }

  // ── the land: print colours, ink and a light rim at every edge, sponge stipple, curls on the water ──
  const ZC = [rgb('#1b3c50'), rgb('#2b5f6b'), rgb('#5f9a96'), rgb('#f2e6cc'), rgb('#7f9a4f'), rgb('#e0a63a'), rgb('#c4482c')];
  const SNOW = rgb('#f6f1e4'), INKC = rgb(INK), CREAMC = rgb(CREAM), LAPC = rgb(LAPIS);
  // a wave crest, cut like a block: a curl of cream on the dark water, in a staggered grid
  function curl(wx, wy) {
    const T = 30, row = Math.floor(wy / (T * 0.62)), u = ((wx + (row % 2) * T * 0.5) % T + T) % T - T / 2, v = ((wy % (T * 0.62)) + T * 0.62) % (T * 0.62) - T * 0.31;
    const r = Math.hypot(u, v), a = Math.atan2(v, u);
    return (Math.abs(r - 4.2) < 0.75 && a > -Math.PI * 0.95 && a < Math.PI * 0.35) || (Math.abs(r - 2) < 0.6 && a > 0 && a < Math.PI * 1.2);
  }
  // little ink squiggles on the cream shore, like the curls printed between the flowers
  function squiggle(wx, wy) {
    const T = 9, u = ((wx % T) + T) % T - T / 2, v = ((wy % T) + T) % T - T / 2, k = hash(Math.floor(wx / T), Math.floor(wy / T));
    if (k < 0.45) return false;
    const yy = Math.sin(u * 1.4 + k * 6) * 1.1;
    return Math.abs(v - yy) < 0.38 && Math.abs(u) < 3.2;
  }
  function terrainPixel(z, lev, snowy, wx, wy) {
    if (lev === 1) return INKC;
    let c = snowy ? SNOW : ZC[z];
    if (lev === 2) c = z === 3 ? LAPC : (z <= 1 ? mix(CREAMC, LAPC, 0.25) : CREAMC);   // the light rim inside each outline
    // sponge: broad mottling, then a fine speckle of dark and light flecks
    const n = vnoise(wx * 0.32, wy * 0.32), f = hash(Math.floor(wx * 3.1), Math.floor(wy * 3.1));
    let k = 0.86 + 0.2 * n;
    if (f < 0.10) k *= 0.78; else if (f > 0.95) c = mix(c, CREAMC, 0.45);
    c = c.map(v => Math.max(0, Math.min(255, v * k)));
    if (lev === 0 && !snowy) {
      if (z <= 1 && curl(wx, wy)) return mix(CREAMC, ZC[z], 0.15);
      if (z === 3 && squiggle(wx, wy)) return INKC;
      if (z === 5 && hash(Math.floor(wx / 6), Math.floor(wy / 6)) > 0.86 && Math.hypot((wx % 6 + 6) % 6 - 3, (wy % 6 + 6) % 6 - 3) < 0.9) return rgb(VERM);
    }
    return c;
  }

  // ── colours for living things: the jewel inks of the presses, chosen by hue ──
  const JEWELS = [[0, '#c8402a'], [28, '#d9822b'], [50, '#e3b23c'], [90, '#8aa046'], [140, '#3e7a52'], [185, '#2f7d86'],
                  [222, '#4a6fbf'], [270, '#6d4c9a'], [320, '#c9577f'], [360, '#c8402a']];
  function jewel(h) {
    h = ((h % 360) + 360) % 360;
    for (let i = 0; i < JEWELS.length - 1; i++) if (h <= JEWELS[i + 1][0]) {
      const [a, ca] = JEWELS[i], [b, cb] = JEWELS[i + 1];
      return mix(rgb(ca), rgb(cb), (h - a) / (b - a));
    }
    return rgb(VERM);
  }
  function animalColors(hue, sat, hue2) {
    const base = mix(jewel(hue * 360), CREAMC, 0.32 * (1 - sat));
    const alt = mix(jewel(hue2 * 360), CREAMC, 0.30);
    return [css(base), css(alt)];
  }
  // ornament on each body segment: dotted rosettes, printed stripes, or a paisley drop
  function pattern(ctx, px, py, r, i, pattern, base, alt, a) {
    if (r < 2.2) return;
    ctx.save(); ctx.translate(px, py); ctx.rotate(a);
    if (pattern > 0.66) {
      ctx.fillStyle = CREAM;
      for (let k = 0; k < 5; k++) { const aa = k / 5 * Math.PI * 2; ctx.beginPath(); ctx.arc(Math.cos(aa) * r * 0.5, Math.sin(aa) * r * 0.5, r * 0.13, 0, Math.PI * 2); ctx.fill(); }
      ctx.fillStyle = VERM; ctx.beginPath(); ctx.arc(0, 0, r * 0.17, 0, Math.PI * 2); ctx.fill();
    } else if (pattern > 0.33) {
      ctx.strokeStyle = i % 2 ? VERM : MAROON; ctx.lineWidth = Math.max(0.8, r * 0.14); ctx.lineCap = 'round';
      for (const o of [-0.45, 0, 0.45]) { ctx.beginPath(); ctx.moveTo(o * r, -r * 0.75); ctx.quadraticCurveTo(o * r + r * 0.25, 0, o * r, r * 0.75); ctx.stroke(); }
    } else {
      ctx.fillStyle = alt; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.6, r * 0.08);
      ctx.beginPath(); ctx.moveTo(-r * 0.55, 0); ctx.bezierCurveTo(-r * 0.4, -r * 0.6, r * 0.5, -r * 0.5, r * 0.45, r * 0.05);
      ctx.bezierCurveTo(r * 0.4, r * 0.35, 0, r * 0.3, -r * 0.1, r * 0.1); ctx.closePath(); ctx.fill(); ctx.stroke();
    }
    // the print's grain on the body
    ctx.fillStyle = 'rgba(35,26,28,0.22)';
    for (let k = 0; k < 4; k++) { const aa = hash(i, k) * 6.28, rr = hash(k, i + 9) * r * 0.85; ctx.fillRect(Math.cos(aa) * rr, Math.sin(aa) * rr, Math.max(0.6, r * 0.08), Math.max(0.6, r * 0.08)); }
    ctx.restore();
  }
  // a long almond eye, lined in kohl
  function eye(ctx, hx, hy, hr, h, diet) {
    const ex = hx + Math.cos(h) * hr * 0.45, ey = hy + Math.sin(h) * hr * 0.45, w = Math.max(1.2, hr * 0.34), e = Math.max(0.6, hr * 0.14);
    ctx.save(); ctx.translate(ex, ey); ctx.rotate(h);
    ctx.fillStyle = CREAM; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.7, hr * 0.09);
    ctx.beginPath(); ctx.moveTo(-w, 0); ctx.quadraticCurveTo(0, -e * 1.6, w, 0); ctx.quadraticCurveTo(0, e * 1.6, -w, 0); ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-w, 0); ctx.lineTo(-w * 1.6, -e * 0.5); ctx.stroke();      // the flick of kohl
    ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(w * 0.15, 0, e * 0.75, 0, Math.PI * 2); ctx.fill();
    if (diet > 0.6) { ctx.strokeStyle = VERM; ctx.lineWidth = Math.max(0.7, hr * 0.1); ctx.beginPath(); ctx.moveTo(-w * 0.8, -e * 1.5); ctx.lineTo(w * 0.9, -e * 1.9); ctx.stroke(); }
    ctx.restore();
  }
  // those that shine carry a gold nimbus behind the head
  function halo(ctx, pts, look, t, alpha) {
    const glow = look[4] || 0;
    if (glow < 0.35) return;
    const [hx, hy, hr] = pts[0], R = hr * (2.1 + 1.2 * glow);
    ctx.save(); ctx.globalAlpha = alpha * Math.min(1, (glow - 0.35) * 3);
    ctx.fillStyle = 'rgba(244,201,92,0.45)'; ctx.beginPath(); ctx.arc(hx, hy, R, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = GOLD; ctx.lineWidth = Math.max(0.8, hr * 0.14); ctx.stroke();
    ctx.strokeStyle = 'rgba(212,165,55,0.85)'; ctx.lineWidth = Math.max(0.6, hr * 0.07);
    for (let k = 0; k < 16; k++) {
      const a = k / 16 * Math.PI * 2 + t * 0.15;
      ctx.beginPath(); ctx.moveTo(hx + Math.cos(a) * R, hy + Math.sin(a) * R); ctx.lineTo(hx + Math.cos(a) * R * (k % 2 ? 1.18 : 1.32), hy + Math.sin(a) * R * (k % 2 ? 1.18 : 1.32)); ctx.stroke();
    }
    ctx.restore();
  }

  // ── the print's sponge: a speckle of light and dark laid over every fill, so colour looks dabbed, not flat ──
  let sponge = null;
  function spongePattern(ctx) {
    if (sponge) return sponge;
    const c = document.createElement('canvas'); c.width = c.height = 96; const g = c.getContext('2d');
    for (let k = 0; k < 900; k++) {
      const x = hash(k, 1) * 96, y = hash(k, 2) * 96, s = 0.7 + hash(k, 3) * 1.6;
      g.fillStyle = hash(k, 4) < 0.55 ? 'rgba(255,248,232,0.30)' : 'rgba(30,20,40,0.22)';
      g.beginPath(); g.arc(x, y, s / 2, 0, Math.PI * 2); g.fill();
    }
    sponge = ctx.createPattern(c, 'repeat');
    return sponge;
  }
  // fill the current path with a colour, then dab the sponge over it (anchored to the shape, so it moves with it)
  function dab(ctx, col, x, y, small) {
    ctx.fillStyle = col; ctx.fill();
    if (small) return;
    const pat = spongePattern(ctx);
    if (pat.setTransform) { M.a = 1; M.b = 0; M.c = 0; M.d = 1; M.e = x; M.f = y; pat.setTransform(M); }
    ctx.fillStyle = pat; ctx.fill();
  }
  const M = { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };                // one transform, reused for every pattern placement
  // red stripes on cream, as one pattern: turned and scaled to each frond, so a striped frond is a single fill
  let stripes = null;
  function stripePattern(ctx) {
    if (stripes) return stripes;
    const c = document.createElement('canvas'); c.width = 32; c.height = 8; const g = c.getContext('2d');
    g.fillStyle = CREAM; g.fillRect(0, 0, 32, 8);
    g.fillStyle = RED; g.fillRect(0, 0, 11, 8);
    stripes = ctx.createPattern(c, 'repeat');
    return stripes;
  }
  const RED = '#b23a2c', BLUE = '#5574c8', SAGE = '#9fb06a';

  // ── flowers: lotuses, two rings of pointed petals around a seed head ──
  function petal(g, len, wid) {
    g.beginPath(); g.moveTo(0, 0);
    g.bezierCurveTo(len * 0.3, -wid, len * 0.75, -wid * 0.9, len, 0);
    g.bezierCurveTo(len * 0.75, wid * 0.9, len * 0.3, wid, 0, 0); g.closePath();
  }
  function stipple(g, R, seed, col) {
    g.fillStyle = col;
    for (let k = 0; k < 26; k++) { const a = hash(seed, k) * 6.283, r = Math.sqrt(hash(k, seed)) * R; g.fillRect(Math.cos(a) * r, Math.sin(a) * r, Math.max(0.7, R * 0.045), Math.max(0.7, R * 0.045)); }
  }
  // a rounded petal with a scalloped tip, like the printed peony's
  function scallop(g, len, wid) {
    g.beginPath(); g.moveTo(0, 0);
    g.bezierCurveTo(len * 0.15, -wid * 1.05, len * 0.62, -wid * 1.25, len * 0.82, -wid * 0.55);
    g.quadraticCurveTo(len * 1.02, -wid * 0.35, len * 0.92, 0);
    g.quadraticCurveTo(len * 1.02, wid * 0.35, len * 0.82, wid * 0.55);
    g.bezierCurveTo(len * 0.62, wid * 1.25, len * 0.15, wid * 1.05, 0, 0); g.closePath();
  }
  // the flower: a stippled blue rim, scalloped outer petals in two tones, a pink inner ring, a saffron cup or a seed head
  function flower(g, R, p, open) {
    const n = Math.max(5, Math.min(10, p.petals)), outer = mix(jewel(p.hue * 360), CREAMC, 0.22 + 0.25 * (1 - p.sat));
    const tint = mix(outer, CREAMC, 0.5), inner = mix(jewel(p.hue2 * 360), rgb(ROSE), 0.55), cup = rgb(SAFF);
    const len = open ? R * 0.98 : R * 0.7, wid = (open ? R * 0.42 : R * 0.26) * Math.sqrt(6 / n);
    const each = (L, Wd, off, fn) => { for (let i = 0; i < n; i++) { g.save(); g.rotate(off + i / n * Math.PI * 2 - Math.PI / 2); if (!open) g.scale(1, 0.6); fn(L, Wd, i); g.restore(); } };
    // the stippled blue rim around the whole bloom
    each(len, wid, 0, (L, Wd) => { scallop(g, L, Wd); g.lineJoin = 'round'; g.strokeStyle = BLUE; g.lineWidth = Math.max(2, R * 0.2); g.stroke(); });
    each(len, wid, 0, (L, Wd) => { scallop(g, L, Wd); g.strokeStyle = 'rgba(244,234,210,0.55)'; g.setLineDash([R * 0.04, R * 0.07]); g.lineWidth = Math.max(1.2, R * 0.12); g.stroke(); g.setLineDash([]); });
    // outer petals: the colour, a lighter inner band, a red line
    each(len, wid, 0, (L, Wd) => {
      scallop(g, L, Wd); dab(g, css(outer), 0, 0);
      g.save(); g.translate(L * 0.1, 0); scallop(g, L * 0.72, Wd * 0.62); dab(g, css(tint), 0, 0); g.restore();
      scallop(g, L, Wd); g.strokeStyle = RED; g.lineWidth = Math.max(0.9, R * 0.06); g.stroke();
    });
    // inner ring: pink petals, offset half a step
    each(len * 0.62, wid * 0.85, Math.PI / n, (L, Wd) => {
      scallop(g, L, Wd); dab(g, css(inner), 0, 0); g.strokeStyle = RED; g.lineWidth = Math.max(0.8, R * 0.055); g.stroke();
    });
    if (p.petals % 2) {
      // a saffron cup with red tips, like the crowned buds of the prints
      g.beginPath();
      const cr = R * 0.3;
      for (let k = 0; k <= 10; k++) { const a = k / 10 * Math.PI * 2 - Math.PI / 2, rr = k % 2 ? cr * 0.6 : cr; g[k ? 'lineTo' : 'moveTo'](Math.cos(a) * rr, Math.sin(a) * rr); }
      g.closePath(); dab(g, css(cup), 0, 0); g.strokeStyle = RED; g.lineWidth = Math.max(0.8, R * 0.05); g.stroke();
      g.fillStyle = RED; g.beginPath(); g.arc(0, 0, cr * 0.32, 0, Math.PI * 2); g.fill();
    } else {
      // a seed head: rings of dark blue, each with a red heart
      const sr = R * 0.3;
      g.fillStyle = css(mix(cup, CREAMC, 0.2)); g.beginPath(); g.arc(0, 0, sr, 0, Math.PI * 2); g.fill();
      for (let k = 0; k < 7; k++) {
        const a = k / 7 * Math.PI * 2, x = k ? Math.cos(a) * sr * 0.55 : 0, y = k ? Math.sin(a) * sr * 0.55 : 0, rr = sr * 0.28;
        g.fillStyle = '#2b4a6e'; g.beginPath(); g.arc(x, y, rr, 0, Math.PI * 2); g.fill();
        g.fillStyle = css(rgb(ROSE)); g.beginPath(); g.arc(x, y, rr * 0.6, 0, Math.PI * 2); g.fill();
        g.fillStyle = RED; g.beginPath(); g.arc(x, y, rr * 0.25, 0, Math.PI * 2); g.fill();
      }
    }
  }

  // ── creatures, as the prints would cut them: bodies of paisley fronds, ink-curl legs, crowned crests ──
  // a frond: a paisley drop, round at the front and tapering back along the body
  function frond(ctx, x, y, r, a, k) {
    const L = r * (1.55 + 0.25 * (k || 0)), cx = Math.cos(a), sx = Math.sin(a), nx = -sx, ny = cx;
    ctx.beginPath();
    ctx.moveTo(x - cx * r * 0.95, y - sx * r * 0.95);
    ctx.bezierCurveTo(x - cx * r * 0.9 + nx * r * 1.05, y - sx * r * 0.9 + ny * r * 1.05, x + cx * L * 0.55 + nx * r * 0.85, y + sx * L * 0.55 + ny * r * 0.85, x + cx * L + nx * r * 0.18, y + sx * L + ny * r * 0.18);
    ctx.bezierCurveTo(x + cx * L * 0.6 - nx * r * 0.55, y + sx * L * 0.6 - ny * r * 0.55, x - cx * r * 0.9 - nx * r * 1.05, y - sx * r * 0.9 - ny * r * 1.05, x - cx * r * 0.95, y - sx * r * 0.95);
    ctx.closePath();
  }
  function frondPrint(ctx, x, y, r, a, i, pattern, base, alt, small) {
    // rim of stippled blue, then the fill, then the print's line inside it
    frond(ctx, x, y, r, a, i % 3);
    ctx.lineJoin = 'round'; ctx.strokeStyle = BLUE; ctx.lineWidth = Math.max(1.2, r * 0.42); ctx.stroke();
    if (pattern > 0.66 && !small) {                               // red stripes on cream, banded with the creature's colours
      const pat = stripePattern(ctx), k = r * 0.32 / 32, ca = Math.cos(a), sa = Math.sin(a);
      M.a = ca * k * 3.2; M.b = sa * k * 3.2; M.c = -sa * k * 3.2; M.d = ca * k * 3.2; M.e = x; M.f = y;
      if (pat.setTransform) pat.setTransform(M);
      ctx.fillStyle = pat; ctx.fill();
      const ga = ctx.globalAlpha; ctx.globalAlpha = ga * 0.85; ctx.fillStyle = i % 2 ? alt : base;
      ctx.beginPath(); ctx.ellipse(x + ca * r * 0.55, y + sa * r * 0.55, r * 0.9, r * 0.32, a, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = ga;
    } else if (pattern > 0.33 && !small) {                        // two tones: an inner drop of the second colour
      dab(ctx, base, x, y, small);
      ctx.save(); frond(ctx, x + Math.cos(a) * r * 0.25, y + Math.sin(a) * r * 0.25, r * 0.55, a, 0); dab(ctx, alt, x, y, small); ctx.restore();
    } else {                                                      // solid, with a dotted spine
      dab(ctx, small && pattern > 0.66 ? CREAM : base, x, y, small);
      if (small) { frond(ctx, x, y, r, a, i % 3); ctx.strokeStyle = RED; ctx.lineWidth = Math.max(0.7, r * 0.11); ctx.stroke(); return; }
      ctx.fillStyle = CREAM;
      for (let k = 0; k < 3; k++) { ctx.beginPath(); ctx.arc(x + Math.cos(a) * r * (0.1 + k * 0.45), y + Math.sin(a) * r * (0.1 + k * 0.45), Math.max(0.6, r * 0.12), 0, Math.PI * 2); ctx.fill(); }
    }
    frond(ctx, x, y, r, a, i % 3); ctx.strokeStyle = RED; ctx.lineWidth = Math.max(0.7, r * 0.11); ctx.stroke();
  }
  function animal(ctx, A) {
    const { pts, r0, ph, p, look, base, alt, t } = A;
    const [hue, sat, hue2, pattern, glow, segs, limbs, size, tail, crest, fin, diet] = look;
    const small = r0 < 5, insul = look[13] || 0;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    if (glow >= 0.35) halo(ctx, pts, look, t, A.alpha);
    // legs: calligraphic ink curls, swinging as it walks
    if (limbs > 0) {
      ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, r0 * 0.22);
      for (let k = 0; k < limbs; k++) {
        const i = Math.min(pts.length - 1, Math.round((k + 0.5) * pts.length / limbs - 0.5));
        const [px, py, r, a] = pts[i], step = Math.sin(ph * 1.6 + k * 1.7) * 0.45;
        for (const side of [-1, 1]) {
          const la = a + side * (Math.PI / 2 + step * side), len = r * 2.0, ex = px + Math.cos(la) * len, ey = py + Math.sin(la) * len;
          ctx.beginPath(); ctx.moveTo(px + Math.cos(la) * r * 0.6, py + Math.sin(la) * r * 0.6);
          ctx.quadraticCurveTo(px + Math.cos(la + 0.5 * side) * len * 0.8, py + Math.sin(la + 0.5 * side) * len * 0.8, ex, ey);
          ctx.arc(ex - Math.cos(la - side) * r * 0.32, ey - Math.sin(la - side) * r * 0.32, r * 0.32, la - side, la - side + side * 4.2, side < 0);
          ctx.stroke();
        }
      }
    }
    // tail: a fan of striped fronds
    const last = pts[pts.length - 1];
    if (tail > 0.15) {
      const [tx, ty, r, a] = last, nf = 2 + Math.round(tail * 3), sp = 0.3 + 0.45 * fin;
      for (let k = 0; k < nf; k++) {
        const aa = a + (nf > 1 ? (k / (nf - 1) - 0.5) * 2 * sp : 0) + Math.sin(ph + k) * 0.08;
        frondPrint(ctx, tx + Math.cos(aa) * r * 0.9, ty + Math.sin(aa) * r * 0.9, r0 * (0.55 + 0.6 * tail), aa, k, 0.8, base, alt, small);
      }
    }
    // a coat: a scalloped, stippled blue fringe
    if (insul > 0.3) {
      const fr = 0.2 + 0.3 * insul;
      ctx.fillStyle = BLUE;
      for (const [px, py, r, a] of pts) {
        if (r < 1.5) continue;
        ctx.beginPath();
        for (let k = 0; k < 8; k++) { const aa = a + k / 8 * Math.PI * 2; ctx.moveTo(px + Math.cos(aa) * r * (1 + fr), py + Math.sin(aa) * r * (1 + fr)); ctx.arc(px + Math.cos(aa) * r * (1 + fr * 0.5), py + Math.sin(aa) * r * (1 + fr * 0.5), r * fr * 0.9, 0, Math.PI * 2); }
        dab(ctx, BLUE, px, py, small);
      }
    }
    // the body: fronds from tail to head, each overlapping the one behind like scales of a printed leaf
    for (let i = pts.length - 1; i >= 1; i--) { const [px, py, r, a] = pts[i]; frondPrint(ctx, px, py, r * 1.05, a, i, pattern, base, alt, small); }
    // crest: a crown of saffron points along the back, outlined in red
    if (crest > 0.25) {
      for (let i = 0; i < Math.min(pts.length, 3); i++) {
        const [px, py, r, a] = pts[i], nrm = a + Math.PI / 2, h = r * (0.7 + 1.5 * crest), w = r * 0.9;
        const bx = px + Math.cos(nrm) * r * 0.8, by = py + Math.sin(nrm) * r * 0.8, ux = Math.cos(nrm), uy = Math.sin(nrm), vx = Math.cos(a), vy = Math.sin(a);
        ctx.beginPath(); ctx.moveTo(bx - vx * w, by - vy * w);
        for (let k = 0; k <= 4; k++) { const f = -1 + k / 2, up = k % 2 ? 0.45 : 1; ctx.lineTo(bx + vx * w * f * 0.9 + ux * h * up, by + vy * w * f * 0.9 + uy * h * up); }
        ctx.lineTo(bx + vx * w, by + vy * w); ctx.closePath();
        ctx.strokeStyle = BLUE; ctx.lineWidth = Math.max(1, r * 0.3); ctx.stroke();
        dab(ctx, SAFF, bx, by, small); ctx.strokeStyle = RED; ctx.lineWidth = Math.max(0.7, r * 0.1); ctx.stroke();
      }
    }
    // the head: round, rimmed and lined like everything else, with its almond eye
    const [hx, hy, hr, ha] = pts[0];
    ctx.beginPath(); ctx.arc(hx, hy, hr * 1.08, 0, Math.PI * 2);
    ctx.strokeStyle = BLUE; ctx.lineWidth = Math.max(1.2, hr * 0.42); ctx.stroke();
    dab(ctx, base, hx, hy, small);
    ctx.beginPath(); ctx.arc(hx, hy, hr * 0.62, 0, Math.PI * 2); dab(ctx, alt, hx, hy, small);
    ctx.beginPath(); ctx.arc(hx, hy, hr * 1.08, 0, Math.PI * 2); ctx.strokeStyle = RED; ctx.lineWidth = Math.max(0.8, hr * 0.12); ctx.stroke();
    eye(ctx, hx, hy, hr, p.h, diet);
  }

  // ── shared drawing helpers ──
  function rr(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
  function goldGrad(g, x0, y0, x1, y1) {
    const gr = g.createLinearGradient(x0, y0, x1, y1);
    gr.addColorStop(0, '#f6dc8c'); gr.addColorStop(0.3, '#c9962f'); gr.addColorStop(0.55, '#f3d27a'); gr.addColorStop(0.8, '#a9781f'); gr.addColorStop(1, '#e9c76d');
    return gr;
  }
  function stippleRect(g, x, y, w, h, col, dens, seed) {
    g.fillStyle = col; const n = Math.round(w * h * dens), s = Math.max(1, Math.min(w, h) * 0.004);
    for (let k = 0; k < n; k++) g.fillRect(x + hash(seed, k) * w, y + hash(k, seed + 7) * h, s, s);
  }
  function frame() { /* the print runs to the edge of the window: no arch, no curtains, no valance */ }

  // ── the cabinet: a maroon ground with a gold vine border and lotus corners ──
  let cabCache = null;
  function cabinet(ctx, L) {
    const key = [L.cw, L.ch].join('|');
    if (!cabCache || cabCache.key !== key) {
      const c = document.createElement('canvas'); c.width = L.cw; c.height = L.ch;
      const g = c.getContext('2d'), { cw, ch, u } = L;
      const gr = g.createLinearGradient(0, 0, 0, ch); gr.addColorStop(0, '#7a2620'); gr.addColorStop(1, '#5a1a17');
      g.fillStyle = gr; g.fillRect(0, 0, cw, ch);
      stippleRect(g, 0, 0, cw, ch, 'rgba(20,4,4,0.35)', 0.0018, 11);
      stippleRect(g, 0, 0, cw, ch, 'rgba(240,170,120,0.10)', 0.0010, 12);
      // a gold border with a running band of small petals
      const b = u * 0.018;
      g.strokeStyle = goldGrad(g, 0, 0, cw, ch); g.lineWidth = b * 0.55; rr(g, b * 0.6, b * 0.6, cw - b * 1.2, ch - b * 1.2, u * 0.025); g.stroke();
      g.strokeStyle = INK; g.lineWidth = Math.max(1, u * 0.0015); g.stroke();
      const step = u * 0.022;
      for (let x = b * 2; x < cw - b * 2; x += step) for (const y of [b * 1.35, ch - b * 1.35]) {
        g.save(); g.translate(x, y); g.rotate(y < ch / 2 ? Math.PI / 2 : -Math.PI / 2);
        petal(g, step * 0.42, step * 0.17); g.fillStyle = Math.round(x / step) % 2 ? ROSE : SAFF; g.fill(); g.strokeStyle = INK; g.lineWidth = Math.max(0.6, u * 0.001); g.stroke(); g.restore();
      }
      for (let y = b * 2; y < ch - b * 2; y += step) for (const x of [b * 1.35, cw - b * 1.35]) {
        g.save(); g.translate(x, y); g.rotate(x < cw / 2 ? 0 : Math.PI);
        petal(g, step * 0.42, step * 0.17); g.fillStyle = Math.round(y / step) % 2 ? ROSE : SAFF; g.fill(); g.strokeStyle = INK; g.lineWidth = Math.max(0.6, u * 0.001); g.stroke(); g.restore();
      }
      for (const [x, y] of [[b * 1.4, b * 1.4], [cw - b * 1.4, b * 1.4], [b * 1.4, ch - b * 1.4], [cw - b * 1.4, ch - b * 1.4]]) {
        g.save(); g.translate(x, y); flower(g, u * 0.028, { petals: 8, hue: 0.97, sat: 0.9, hue2: 0.13 }, true); g.restore();
      }
      cabCache = { key, c };
    }
    ctx.drawImage(cabCache.c, 0, 0);
  }
  // the molding around the window: gold, with a thin band of petals
  function bezel(ctx, L) {
    const { pf, u } = L, b = u * 0.016;
    ctx.save();
    ctx.lineWidth = b; ctx.strokeStyle = goldGrad(ctx, pf.x, pf.y, pf.x + pf.w, pf.y + pf.h);
    rr(ctx, pf.x - b / 2, pf.y - b / 2, pf.w + b, pf.h + b, u * 0.018); ctx.stroke();
    ctx.lineWidth = Math.max(1, u * 0.002); ctx.strokeStyle = INK;
    rr(ctx, pf.x - b, pf.y - b, pf.w + 2 * b, pf.h + 2 * b, u * 0.022); ctx.stroke();
    rr(ctx, pf.x, pf.y, pf.w, pf.h, u * 0.018); ctx.stroke();
    ctx.fillStyle = VERM;
    const per = 2 * (pf.w + pf.h), n = Math.round(per / (u * 0.03));
    for (let k = 0; k < n; k++) {                                   // little vermilion beads set in the gold
      let d = k / n * per, x, y;
      if (d < pf.w) { x = pf.x + d; y = pf.y - b / 2; } else if ((d -= pf.w) < pf.h) { x = pf.x + pf.w + b / 2; y = pf.y + d; }
      else if ((d -= pf.h) < pf.w) { x = pf.x + pf.w - d; y = pf.y + pf.h + b / 2; } else { d -= pf.w; x = pf.x - b / 2; y = pf.y + pf.h - d; }
      ctx.beginPath(); ctx.arc(x, y, b * 0.16, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  function metal(ctx, x0, y0, x1, y1) { return goldGrad(ctx, x0, y0, x1, y1); }
  // the brass pins of the cabinet become gold beads set with a ruby
  function pin(ctx, X, Y, r, night, t, seed) {
    ctx.fillStyle = 'rgba(35,26,28,0.35)'; ctx.beginPath(); ctx.arc(X + r * 0.4, Y + r * 0.5, r, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = GOLD; ctx.beginPath(); ctx.arc(X, Y, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.6, r * 0.18); ctx.stroke();
    ctx.fillStyle = night > 0.4 && (Math.floor(seed + t * 2) % 11 === 0) ? '#ff8a7a' : VERM;
    ctx.beginPath(); ctx.arc(X, Y, r * 0.45, 0, Math.PI * 2); ctx.fill();
  }
  // the tray: a maroon board with a gold edge and a row of seeds
  function tray(ctx, T, u) {
    ctx.save();
    rr(ctx, T.x, T.y, T.w, T.h, u * 0.02);
    const gr = ctx.createLinearGradient(0, T.y, 0, T.y + T.h); gr.addColorStop(0, '#842b23'); gr.addColorStop(1, '#5c1b17');
    ctx.fillStyle = gr; ctx.fill();
    ctx.lineWidth = u * 0.007; ctx.strokeStyle = goldGrad(ctx, T.x, T.y, T.x + T.w, T.y + T.h); ctx.stroke();
    ctx.lineWidth = Math.max(1, u * 0.0015); ctx.strokeStyle = INK; ctx.stroke();
    ctx.fillStyle = 'rgba(227,167,47,0.55)';
    for (let x = T.x + u * 0.03; x < T.x + T.w - u * 0.02; x += u * 0.016) for (const y of [T.y + u * 0.012, T.y + T.h - u * 0.012]) { ctx.beginPath(); ctx.arc(x, y, u * 0.0028, 0, Math.PI * 2); ctx.fill(); }
    ctx.restore();
  }
  // the nameplate: a cream cartouche with cusped ends, a double border, lettered in vermilion
  function nameplate(ctx, x, y, w, h, text, u) {
    ctx.save();
    const lobe = h * 0.5;
    ctx.beginPath();
    ctx.moveTo(x + lobe, y); ctx.lineTo(x + w - lobe, y);
    ctx.quadraticCurveTo(x + w - lobe * 0.2, y, x + w - lobe * 0.35, y + h * 0.25); ctx.quadraticCurveTo(x + w + lobe * 0.15, y + h * 0.5, x + w - lobe * 0.35, y + h * 0.75);
    ctx.quadraticCurveTo(x + w - lobe * 0.2, y + h, x + w - lobe, y + h); ctx.lineTo(x + lobe, y + h);
    ctx.quadraticCurveTo(x + lobe * 0.2, y + h, x + lobe * 0.35, y + h * 0.75); ctx.quadraticCurveTo(x - lobe * 0.15, y + h * 0.5, x + lobe * 0.35, y + h * 0.25);
    ctx.quadraticCurveTo(x + lobe * 0.2, y, x + lobe, y); ctx.closePath();
    ctx.fillStyle = CREAM; ctx.fill();
    ctx.lineWidth = u * 0.006; ctx.strokeStyle = goldGrad(ctx, x, y, x + w, y + h); ctx.stroke();
    ctx.lineWidth = Math.max(1, u * 0.0016); ctx.strokeStyle = MAROON; ctx.stroke();
    stippleRect(ctx, x + lobe * 0.5, y + h * 0.12, w - lobe, h * 0.76, 'rgba(110,34,29,0.12)', 0.004, 21);
    for (const s of [1, -1]) { ctx.save(); ctx.translate(s > 0 ? x + lobe * 0.85 : x + w - lobe * 0.85, y + h / 2); flower(ctx, h * 0.22, { petals: 6, hue: 0.97, sat: 0.9, hue2: 0.13 }, true); ctx.restore(); }
    ctx.fillStyle = MAROON; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    let fs = h * 0.5; ctx.font = `${fs}px "Yatra One", serif`;
    while (ctx.measureText(text).width > w - lobe * 3.2 && fs > 6) { fs -= 1; ctx.font = `${fs}px "Yatra One", serif`; }
    ctx.fillText(text, x + w / 2, y + h / 2 + fs * 0.06);
    ctx.restore();
  }
  // the print's own surface over the window: a fine grain, and the faint sheen of varnish
  let grain = null;
  function surface(ctx, pf, t) {
    if (!grain) {
      const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d');
      for (let k = 0; k < 2600; k++) { g.fillStyle = hash(k, 3) < 0.6 ? 'rgba(35,26,28,0.10)' : 'rgba(255,248,230,0.10)'; g.fillRect(hash(k, 1) * 256, hash(k, 2) * 256, 1 + hash(k, 4) * 1.5, 1 + hash(k, 5) * 1.5); }
      grain = ctx.createPattern(c, 'repeat');
    }
    ctx.fillStyle = grain; ctx.fillRect(pf.x, pf.y, pf.w, pf.h);
    const gr = ctx.createLinearGradient(pf.x, pf.y, pf.x + pf.w, pf.y + pf.h);
    gr.addColorStop(0, 'rgba(255,240,200,0.07)'); gr.addColorStop(0.5, 'rgba(255,240,200,0)'); gr.addColorStop(1, 'rgba(120,60,20,0.06)');
    ctx.fillStyle = gr; ctx.fillRect(pf.x, pf.y, pf.w, pf.h);
  }

  window.ALGO_SKIN = {
    id: 'devotional', slug: 'devotional',
    terrainPixel, animalColors, animal, flower, flowerPad: 0.25,
    frame, cabinet, bezel, metal, pin, tray, nameplate,          // (no surface layer: the land is already stippled)
  };
})();
