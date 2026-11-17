/* Algogenesis — the Coast as a devotional print.

   The same living world, drawn in the visual language of the popular devotional prints made in India's studio presses
   between 1860 and 1930 (chromolithographs, hand-coloured lithographs and woodblock prints from Calcutta, Poona, Bombay,
   Nathdwara): jewel colours under varnish, gold, cusped arches, curtains drawn aside, lotus borders. The surface is a
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
  function flower(g, R, p, open) {
    const n = Math.max(5, Math.min(12, p.petals)), c1 = mix(jewel(p.hue * 360), CREAMC, 0.18 + 0.25 * (1 - p.sat)), c2 = mix(c1, CREAMC, 0.45);
    const len = open ? R : R * 0.8, wid = open ? R * 0.34 * (6 / n) ** 0.5 : R * 0.2;
    const ring = (L, Wd, off, fill) => {
      for (let i = 0; i < n; i++) {
        g.save(); g.rotate(off + i / n * Math.PI * 2 - Math.PI / 2);
        if (!open) g.scale(1, 0.55);
        petal(g, L, Wd);
        g.lineJoin = 'round';
        g.strokeStyle = CREAM; g.lineWidth = Math.max(1.6, R * 0.16); g.stroke();      // the light rim outside
        g.fillStyle = css(fill); g.fill();
        g.strokeStyle = MAROON; g.lineWidth = Math.max(0.8, R * 0.06); g.stroke();      // the ink line
        // a vein down the middle, as the printer cut it
        g.strokeStyle = 'rgba(110,34,29,0.45)'; g.lineWidth = Math.max(0.6, R * 0.035);
        g.beginPath(); g.moveTo(L * 0.18, 0); g.lineTo(L * 0.82, 0); g.stroke();
        g.restore();
      }
    };
    ring(len, wid, 0, c1);
    ring(len * 0.66, wid * 0.8, Math.PI / n, c2);
    stipple(g, R * 0.9, Math.round(p.hue * 97) + n, 'rgba(110,34,29,0.25)');
    // the seed head: a ring of seeds, each outlined
    const sc = mix(jewel(p.hue2 * 360), rgb(SAFF), 0.4), sr = R * 0.24;
    g.fillStyle = css(sc); g.strokeStyle = INK; g.lineWidth = Math.max(0.7, R * 0.05);
    g.beginPath(); g.arc(0, 0, sr, 0, Math.PI * 2); g.fill(); g.stroke();
    g.fillStyle = css(mix(sc, rgb(LEAF), 0.5));
    for (let k = 0; k < 6; k++) { const a = k / 6 * Math.PI * 2; g.beginPath(); g.arc(Math.cos(a) * sr * 0.55, Math.sin(a) * sr * 0.55, sr * 0.2, 0, Math.PI * 2); g.fill(); }
  }

  // ── the frame: a cusped arch, curtains drawn aside, a valance, a lotus dais ──
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
  // the opening of the arch: straight sides up to the springing, then a pointed arch of cusped lobes
  function archPath(g, pf) {
    const m = pf.w * 0.035, x0 = pf.x + m, x1 = pf.x + pf.w - m, cx = pf.x + pf.w / 2;
    const spring = pf.y + pf.h * 0.36, apex = pf.y + pf.h * 0.075, bottom = pf.y + pf.h + 4, N = 6;
    const P = s => [x0 + (cx - x0) * Math.pow(1 - Math.cos(s * Math.PI / 2), 0.8), spring - (spring - apex) * Math.pow(Math.sin(s * Math.PI / 2), 1.25)];
    g.moveTo(x0, bottom); g.lineTo(x0, spring);
    const lobes = (pts, out) => {
      for (let i = 0; i < pts.length - 1; i++) {
        const [ax, ay] = pts[i], [bx, by] = pts[i + 1], mx = (ax + bx) / 2, my = (ay + by) / 2, L = Math.hypot(bx - ax, by - ay);
        let nx = -(by - ay) / L, ny = (bx - ax) / L;
        if ((mx - cx) * nx + (my - spring) * ny < 0) { nx = -nx; ny = -ny; }            // bulge away from the centre
        g.quadraticCurveTo(mx + nx * L * 0.5, my + ny * L * 0.5, bx, by);
      }
    };
    const left = []; for (let i = 0; i <= N; i++) left.push(P(i / N));
    lobes(left);
    const right = left.slice().reverse().map(([x, y]) => [2 * cx - x, y]);
    g.lineTo(cx, apex - pf.h * 0.025); g.lineTo(right[0][0], right[0][1]);                // the little point at the apex
    lobes(right);
    g.lineTo(x1, bottom); g.lineTo(x0, bottom);
    return { spring, apex, x0, x1, cx, m };
  }
  function bigLotus(g, x, y, R, hue, rot) {
    g.save(); g.translate(x, y); g.rotate(rot || 0);
    flower(g, R, { petals: 8, hue, sat: 0.9, hue2: 0.13 }, true);
    g.restore();
  }
  function leaf(g, x, y, L, a, col) {
    g.save(); g.translate(x, y); g.rotate(a);
    petal(g, L, L * 0.28);
    g.strokeStyle = CREAM; g.lineWidth = L * 0.07; g.stroke(); g.fillStyle = col; g.fill();
    g.strokeStyle = INK; g.lineWidth = L * 0.025; g.stroke();
    g.strokeStyle = 'rgba(244,234,210,0.6)'; g.lineWidth = L * 0.02;
    for (let k = 1; k < 5; k++) { g.beginPath(); g.moveTo(L * k / 5.5, 0); g.lineTo(L * (k / 5.5 + 0.12), -L * 0.12); g.moveTo(L * k / 5.5, 0); g.lineTo(L * (k / 5.5 + 0.12), L * 0.12); g.stroke(); }
    g.restore();
  }
  function curtain(g, pf, side, spring) {
    const s = side, X0 = s > 0 ? pf.x : pf.x + pf.w, w = pf.w * 0.115, tieY = spring + pf.h * 0.05, tieX = X0 + s * pf.w * 0.03;
    g.save();
    g.beginPath(); g.moveTo(X0, pf.y); g.lineTo(X0 + s * w, pf.y);
    g.bezierCurveTo(X0 + s * w * 0.75, pf.y + pf.h * 0.18, tieX + s * pf.w * 0.03, tieY - pf.h * 0.1, tieX, tieY);
    g.bezierCurveTo(tieX - s * pf.w * 0.006, tieY + pf.h * 0.08, X0 + s * pf.w * 0.02, tieY + pf.h * 0.18, X0, tieY + pf.h * 0.26);
    g.closePath();
    const gr = g.createLinearGradient(X0, 0, X0 + s * w, 0);
    gr.addColorStop(0, '#7b1f1a'); gr.addColorStop(0.45, VERM); gr.addColorStop(1, '#8f2a20');
    g.fillStyle = gr; g.fill();
    g.save(); g.clip();
    for (let k = 1; k < 6; k++) {                                                            // folds falling to the tie
      g.strokeStyle = k % 2 ? 'rgba(60,12,10,0.35)' : 'rgba(255,200,170,0.18)'; g.lineWidth = pf.w * 0.006;
      g.beginPath(); g.moveTo(X0 + s * w * k / 6, pf.y); g.quadraticCurveTo(X0 + s * w * k / 9, tieY - pf.h * 0.1, tieX - s * pf.w * 0.004 * k, tieY); g.stroke();
    }
    stippleRect(g, Math.min(X0, X0 + s * w), pf.y, w, tieY + pf.h * 0.3 - pf.y, 'rgba(40,8,6,0.25)', 0.0016, 31 + s);
    g.restore();
    g.strokeStyle = goldGrad(g, X0, pf.y, X0 + s * w, tieY); g.lineWidth = pf.w * 0.006; g.stroke();
    g.strokeStyle = INK; g.lineWidth = Math.max(1, pf.w * 0.0015); g.stroke();
    // the tie: a gold cord and a tassel
    g.fillStyle = goldGrad(g, tieX - 10, tieY - 10, tieX + 10, tieY + 10);
    g.beginPath(); g.ellipse(tieX, tieY, pf.w * 0.011, pf.h * 0.018, 0, 0, Math.PI * 2); g.fill(); g.strokeStyle = INK; g.lineWidth = Math.max(1, pf.w * 0.0015); g.stroke();
    g.beginPath(); g.moveTo(tieX - pf.w * 0.006, tieY + pf.h * 0.015); g.lineTo(tieX + pf.w * 0.006, tieY + pf.h * 0.015); g.lineTo(tieX + pf.w * 0.009, tieY + pf.h * 0.075); g.lineTo(tieX - pf.w * 0.009, tieY + pf.h * 0.075); g.closePath();
    g.fillStyle = SAFF; g.fill(); g.stroke();
    g.restore();
  }
  function valance(g, pf) {
    const n = 14, w = pf.w / n, h = pf.h * 0.05;
    g.fillStyle = MAROON; g.fillRect(pf.x, pf.y, pf.w, h * 0.45);
    for (let k = 0; k < n; k++) {
      const x = pf.x + k * w;
      g.beginPath(); g.moveTo(x, pf.y + h * 0.4); g.quadraticCurveTo(x + w / 2, pf.y + h * 1.25, x + w, pf.y + h * 0.4); g.closePath();
      g.fillStyle = k % 2 ? VERM : '#8f2a20'; g.fill();
      g.strokeStyle = goldGrad(g, x, pf.y, x + w, pf.y + h); g.lineWidth = pf.w * 0.004; g.stroke();
      g.strokeStyle = INK; g.lineWidth = Math.max(1, pf.w * 0.0012); g.stroke();
      // a tassel from each point
      g.fillStyle = SAFF; g.beginPath(); g.moveTo(x - w * 0.06, pf.y + h * 0.42); g.lineTo(x + w * 0.06, pf.y + h * 0.42); g.lineTo(x, pf.y + h * 1.1); g.closePath(); g.fill(); g.stroke();
    }
    g.strokeStyle = goldGrad(g, pf.x, pf.y, pf.x + pf.w, pf.y); g.lineWidth = pf.h * 0.008; g.beginPath(); g.moveTo(pf.x, pf.y + h * 0.42); g.lineTo(pf.x + pf.w, pf.y + h * 0.42); g.stroke();
  }
  function dais(g, pf) {
    const h = pf.h * 0.04, n = 36, w = pf.w / n, y = pf.y + pf.h - h;
    g.fillStyle = MAROON; g.fillRect(pf.x, y + h * 0.55, pf.w, h * 0.45);
    for (let k = 0; k <= n; k++) {
      const x = pf.x + k * w;
      g.save(); g.translate(x, y + h); g.rotate(-Math.PI / 2);
      petal(g, h * 1.05, w * 0.5);
      g.strokeStyle = CREAM; g.lineWidth = w * 0.12; g.stroke();
      g.fillStyle = k % 2 ? ROSE : '#f0d9b5'; g.fill(); g.strokeStyle = MAROON; g.lineWidth = Math.max(1, w * 0.05); g.stroke();
      g.restore();
    }
    g.strokeStyle = goldGrad(g, pf.x, y, pf.x + pf.w, y); g.lineWidth = pf.h * 0.006; g.beginPath(); g.moveTo(pf.x, y + h); g.lineTo(pf.x + pf.w, y + h); g.stroke();
  }
  let frameCache = null;
  function buildFrame(L, dark) {
    const { pf } = L, c = document.createElement('canvas'); c.width = L.cw; c.height = L.ch;
    const g = c.getContext('2d');
    g.save();
    g.beginPath(); g.rect(pf.x, pf.y, pf.w, pf.h);
    const A = archPath(g, pf);
    g.clip('evenodd');
    // spandrels: a printed panel of deep teal, with lotuses, leaves and curls
    g.fillStyle = TEAL; g.fillRect(pf.x, pf.y, pf.w, pf.h);
    stippleRect(g, pf.x, pf.y, pf.w, pf.h, 'rgba(12,30,38,0.35)', 0.0022, 5);
    stippleRect(g, pf.x, pf.y, pf.w, pf.h, 'rgba(160,210,210,0.12)', 0.0012, 6);
    for (const s of [1, -1]) {
      const cx = s > 0 ? pf.x + pf.w * 0.15 : pf.x + pf.w * 0.85, cy = pf.y + pf.h * 0.12, R = pf.h * 0.07;
      for (let k = 0; k < 5; k++) leaf(g, cx, cy, R * 1.9, (s > 0 ? 0 : Math.PI) + (k - 2) * 0.55 + (s > 0 ? 0.6 : -0.6), k % 2 ? LEAF : OLIVE);
      bigLotus(g, cx, cy, R, s > 0 ? 0.97 : 0.62, s * 0.2);
    }
    g.restore();
    // the arch's edge: gold, ink, and a light rim, like the outline of everything else
    g.save(); g.beginPath(); archPath(g, pf);
    g.lineJoin = 'round';
    g.strokeStyle = CREAM; g.lineWidth = pf.w * 0.013; g.stroke();
    g.strokeStyle = goldGrad(g, pf.x, pf.y, pf.x + pf.w, pf.y + pf.h * 0.4); g.lineWidth = pf.w * 0.008; g.stroke();
    g.strokeStyle = INK; g.lineWidth = Math.max(1, pf.w * 0.0018); g.stroke();
    g.restore();
    g.save(); rr(g, pf.x, pf.y, pf.w, pf.h, L.u * 0.018); g.clip();
    curtain(g, pf, 1, A.spring); curtain(g, pf, -1, A.spring);
    valance(g, pf); dais(g, pf);
    g.restore();
    if (dark) { g.globalCompositeOperation = 'source-atop'; g.fillStyle = 'rgba(12,6,16,0.72)'; g.fillRect(0, 0, c.width, c.height); }
    return c;
  }
  function frame(ctx, L, t, night, dark) {
    const key = [L.cw, L.ch, L.pf.x, L.pf.y, L.pf.w, L.pf.h, dark ? 1 : 0].join('|');
    if (!frameCache || frameCache.key !== key) frameCache = { key, c: buildFrame(L, dark) };
    ctx.drawImage(frameCache.c, 0, 0);
  }

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
    terrainPixel, animalColors, pattern, eye, halo, flower, flowerPad: 0.2, rim: CREAM,
    frame, cabinet, bezel, metal, pin, tray, nameplate, surface,
  };
})();
