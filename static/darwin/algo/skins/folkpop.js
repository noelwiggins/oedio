/* Algogenesis — the Coast as folk pop.

   The same living world, drawn in a mix of two manners: Ukrainian naive folk painting in the spirit of Maria Prymachenko
   (fantastical beasts whose bodies are gardens of dots, stripes and flowers; huge lashed eyes; striped legs with claws;
   tails that end in a bloom; plants that are all fans and berries; every contour traced with a row of white dots) and the
   flat, saturated, op-art colour of late-1960s psychedelic animation in the spirit of Yellow Submarine (rainbow contour
   bands, wavy stripes on the sea, starbursts, bubbly lettering). Manner only: no copies of particular paintings, no
   characters from the film.

   Loaded before panel.js, it sets window.ALGO_SKIN; panel.js calls these hooks in place of its own drawing. */
(function () {
  'use strict';
  const INK = '#151215', WHITE = '#fffaf0', RED = '#e8322b', ORANGE = '#f58a1f', YELLOW = '#ffd21f', LIME = '#8cc63f';
  const GREEN = '#1e9a55', TURQ = '#18b5b0', SKY = '#5ec8f2', BLUE = '#2f5bd3', VIOLET = '#7b3fb5', MAGENTA = '#e8338b', PINK = '#ff9ccf';
  const RAINBOW = [RED, ORANGE, YELLOW, LIME, TURQ, BLUE, VIOLET, MAGENTA];
  const rgb = h => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const mix = (a, b, k) => a.map((v, i) => Math.round(v + (b[i] - v) * k));
  const css = c => `rgb(${c[0]},${c[1]},${c[2]})`;
  const hash = (x, y) => { let h = (x * 374761393 + y * 668265263) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
  const TAU = Math.PI * 2;

  // ── the land: rainbow contour bands on the hills, wavy op-art stripes on the sea, dotted shores ──
  // each zone has two or three flat colours that alternate in bands following the height of the land
  const BANDS = [[BLUE, VIOLET], [TURQ, BLUE, SKY], [SKY, TURQ], [YELLOW, WHITE], [LIME, GREEN, YELLOW], [ORANGE, YELLOW, PINK], [MAGENTA, RED, ORANGE]].map(z => z.map(rgb));
  const INKC = rgb(INK), WHITEC = rgb(WHITE), REDC = rgb(RED), SNOWB = [rgb(WHITE), rgb(SKY)];
  const DOTS = [RED, MAGENTA, BLUE, ORANGE, GREEN].map(rgb);
  function terrainPixel(z, lev, snowy, wx, wy, name, h) {
    if (lev === 1) return INKC;
    if (lev === 2) {                                                  // the white rim inside each outline, with coloured dots in it
      const T = 5, cx = Math.floor(wx / T), cy = Math.floor(wy / T), u = ((wx % T) + T) % T - T / 2, v = ((wy % T) + T) % T - T / 2;
      return u * u + v * v < 1.1 ? DOTS[(cx * 7 + cy * 3) % DOTS.length & 0x7fffffff] || REDC : WHITEC;
    }
    if (snowy) { const b = Math.floor((h * 60 + Math.sin(wx * 0.05) * 1.5)) & 1; return SNOWB[b]; }
    const P = BANDS[z];
    if (z <= 2) {                                                     // the sea: wavy horizontal stripes, the swell bending them
      const w = wy * 0.16 + Math.sin(wx * 0.06 + wy * 0.01) * 1.4 + Math.sin(wx * 0.017) * 2.2 - h * 9;
      const k = ((Math.floor(w) % P.length) + P.length) % P.length;
      return Math.abs(w - Math.round(w)) < 0.07 ? mix(P[k], INKC, 0.35) : P[k];
    }
    if (z === 3) {                                                    // the shore: lemon with rows of polka dots
      const T = 7, row = Math.floor(wy / T), u = ((wx + (row % 2) * T / 2) % T + T) % T - T / 2, v = ((wy % T) + T) % T - T / 2;
      if (u * u + v * v < 1.6) return DOTS[((row * 5 + Math.floor((wx + (row % 2) * T / 2) / T)) % DOTS.length + DOTS.length) % DOTS.length];
      return P[0];
    }
    // the hills: contour bands, a thin ink line between them, so the land reads as a stack of coloured terraces
    const c = h * 38 + Math.sin(wx * 0.045) * 0.35 + Math.sin(wy * 0.05) * 0.35;
    const k = ((Math.floor(c) % P.length) + P.length) % P.length;
    if (Math.abs(c - Math.round(c)) < 0.06) return mix(P[k], INKC, 0.55);
    // a scatter of tiny folk flowers in the meadow
    if (z === 4 && hash(Math.floor(wx / 9), Math.floor(wy / 9)) > 0.88) {
      const u = ((wx % 9) + 9) % 9 - 4.5, v = ((wy % 9) + 9) % 9 - 4.5;
      if (u * u + v * v < 1.4) return REDC; if (u * u + v * v < 2.6) return WHITEC;
    }
    return P[k];
  }

  // ── colours for living things: a pop palette, chosen by hue ──
  const POP = [[0, RED], [30, ORANGE], [55, YELLOW], [95, LIME], [145, GREEN], [180, TURQ], [205, SKY], [235, BLUE], [275, VIOLET], [320, MAGENTA], [345, PINK], [360, RED]];
  function pop(h) {
    h = ((h % 360) + 360) % 360;
    for (let i = 0; i < POP.length - 1; i++) if (h <= POP[i + 1][0]) {
      const [a, ca] = POP[i], [b, cb] = POP[i + 1], f = (h - a) / (b - a);
      return rgb(f < 0.5 ? ca : cb);                                  // flat colours: snap to the nearer one, no muddy blends
    }
    return rgb(RED);
  }
  function animalColors(hue, sat, hue2) {
    const base = pop(hue * 360), alt0 = pop(hue2 * 360);
    const alt = alt0.join() === base.join() ? pop(hue2 * 360 + 150) : alt0;
    return [css(sat < 0.3 ? mix(base, WHITEC, 0.35) : base), css(alt)];
  }

  // a row of white dots along a path already set: the folk painter's traced contour
  function dotted(ctx, w, gap) {
    ctx.save(); ctx.setLineDash([0.01, gap]); ctx.lineCap = 'round'; ctx.strokeStyle = WHITE; ctx.lineWidth = w; ctx.stroke(); ctx.restore();
  }
  // a little five-petal flower, used inside bodies and at the tips of tails
  function rosette(ctx, x, y, r, c1, c2) {
    ctx.fillStyle = c1;
    for (let k = 0; k < 5; k++) { const a = k / 5 * TAU; ctx.beginPath(); ctx.arc(x + Math.cos(a) * r * 0.55, y + Math.sin(a) * r * 0.55, r * 0.45, 0, TAU); ctx.fill(); }
    ctx.fillStyle = c2; ctx.beginPath(); ctx.arc(x, y, r * 0.38, 0, TAU); ctx.fill();
  }

  // ── flowers: a folk fan-bloom seen from above: teardrop petals in two colours, each with a stripe and a row of dots,
  //    green blades between them, and a rainbow-ringed heart ──
  function teardrop(g, len, wid) {
    g.beginPath(); g.moveTo(0, 0);
    g.bezierCurveTo(len * 0.15, -wid, len * 0.85, -wid * 1.1, len, 0);
    g.bezierCurveTo(len * 0.85, wid * 1.1, len * 0.15, wid, 0, 0); g.closePath();
  }
  function flower(g, R, p, open) {
    const n = Math.max(5, Math.min(10, p.petals)), c1 = css(pop(p.hue * 360)), c2 = css(pop(p.hue2 * 360 + 40));
    const len = open ? R * 0.98 : R * 0.62, wid = (open ? R * 0.36 : R * 0.22) * Math.sqrt(6 / n), lw = Math.max(1, R * 0.08);
    g.lineJoin = 'round'; g.lineCap = 'round';
    // green blades between the petals
    for (let i = 0; i < n; i++) {
      g.save(); g.rotate((i + 0.5) / n * TAU - Math.PI / 2); if (!open) g.scale(1, 0.6);
      teardrop(g, len * 0.85, wid * 0.45); g.fillStyle = GREEN; g.fill(); g.strokeStyle = INK; g.lineWidth = lw * 0.8; g.stroke();
      g.beginPath(); g.moveTo(len * 0.12, 0); g.lineTo(len * 0.7, 0); g.strokeStyle = LIME; g.lineWidth = lw * 0.6; g.stroke();
      g.restore();
    }
    for (let i = 0; i < n; i++) {
      g.save(); g.rotate(i / n * TAU - Math.PI / 2); if (!open) g.scale(1, 0.6);
      teardrop(g, len, wid); g.fillStyle = i % 2 ? c2 : c1; g.fill(); g.strokeStyle = INK; g.lineWidth = lw; g.stroke();
      // a stripe of the other colour down the middle, and a row of white dots along it
      teardrop(g, len * 0.8, wid * 0.38); g.fillStyle = i % 2 ? c1 : c2; g.fill();
      if (R > 7) { g.fillStyle = WHITE; for (let k = 1; k <= 3; k++) { g.beginPath(); g.arc(len * (0.25 + k * 0.17), 0, Math.max(0.6, R * 0.045), 0, TAU); g.fill(); } }
      // the painter's flick at the tip
      g.beginPath(); g.moveTo(len * 0.98, 0); g.lineTo(len * 1.12, 0); g.strokeStyle = INK; g.lineWidth = lw * 0.7; g.stroke();
      g.restore();
    }
    // the heart: rainbow rings, then berries for an odd number of petals or a dotted seed disc for an even one
    const hr = R * 0.32;
    [MAGENTA, ORANGE, YELLOW].forEach((c, k) => { g.beginPath(); g.arc(0, 0, hr * (1 - k * 0.28), 0, TAU); g.fillStyle = c; g.fill(); });
    g.beginPath(); g.arc(0, 0, hr, 0, TAU); g.strokeStyle = INK; g.lineWidth = lw; g.stroke();
    if (p.petals % 2) {
      for (let k = 0; k < 3; k++) { const a = k / 3 * TAU + 0.5; g.fillStyle = RED; g.beginPath(); g.arc(Math.cos(a) * hr * 0.4, Math.sin(a) * hr * 0.4, hr * 0.26, 0, TAU); g.fill(); g.strokeStyle = INK; g.lineWidth = lw * 0.6; g.stroke(); }
    } else {
      g.fillStyle = INK; for (let k = 0; k < 6; k++) { const a = k / 6 * TAU; g.beginPath(); g.arc(Math.cos(a) * hr * 0.55, Math.sin(a) * hr * 0.55, Math.max(0.5, hr * 0.1), 0, TAU); g.fill(); }
    }
  }

  // ── creatures: folk beasts. Round segments filled with dots, rainbow stripes or little flowers, traced with white dots;
  //    striped legs with claws; a big lashed eye; tails that curl and end in a bloom; plumes of fan feathers ──
  function segment(ctx, x, y, r, a, i, pattern, base, alt, small) {
    ctx.beginPath(); ctx.ellipse(x, y, r * 1.12, r, a, 0, TAU);
    ctx.fillStyle = base; ctx.fill();
    if (!small) {
      ctx.save(); ctx.clip();
      if (pattern > 0.66) {                                           // polka dots in the second colour, ringed in white
        const nd = 5;
        for (let k = 0; k < nd; k++) {
          const aa = a + k / nd * TAU + i, d = k ? r * 0.55 : 0, px = x + Math.cos(aa) * d, py = y + Math.sin(aa) * d;
          ctx.fillStyle = WHITE; ctx.beginPath(); ctx.arc(px, py, r * 0.26, 0, TAU); ctx.fill();
          ctx.fillStyle = alt; ctx.beginPath(); ctx.arc(px, py, r * 0.17, 0, TAU); ctx.fill();
        }
      } else if (pattern > 0.33) {                                    // rainbow bands across the body
        ctx.translate(x, y); ctx.rotate(a);
        const bw = r * 0.42;
        for (let k = -3; k <= 3; k++) { ctx.fillStyle = RAINBOW[((k + i * 2) % RAINBOW.length + RAINBOW.length) % RAINBOW.length]; ctx.fillRect(k * bw - bw / 2, -r * 1.2, bw * 0.62, r * 2.4); }
      } else {                                                        // a little flower in the middle
        rosette(ctx, x, y, r * 0.6, alt, YELLOW);
      }
      ctx.restore();
    }
    ctx.beginPath(); ctx.ellipse(x, y, r * 1.12, r, a, 0, TAU);
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.9, r * 0.2); ctx.stroke();
    if (!small) { ctx.beginPath(); ctx.ellipse(x, y, r * 0.86, r * 0.74, a, 0, TAU); dotted(ctx, Math.max(0.8, r * 0.13), Math.max(1.8, r * 0.3)); }
  }
  function eye(ctx, hx, hy, hr, h, diet, small) {
    const ex = hx + Math.cos(h) * hr * 0.25, ey = hy + Math.sin(h) * hr * 0.25, er = Math.max(1.1, hr * 0.5);
    ctx.fillStyle = WHITE; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.7, hr * 0.1);
    ctx.beginPath(); ctx.arc(ex, ey, er, 0, TAU); ctx.fill(); ctx.stroke();
    ctx.fillStyle = diet > 0.6 ? RED : BLUE; ctx.beginPath(); ctx.arc(ex + Math.cos(h) * er * 0.25, ey + Math.sin(h) * er * 0.25, er * 0.58, 0, TAU); ctx.fill();
    ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(ex + Math.cos(h) * er * 0.32, ey + Math.sin(h) * er * 0.32, er * 0.3, 0, TAU); ctx.fill();
    ctx.fillStyle = WHITE; ctx.beginPath(); ctx.arc(ex + Math.cos(h - 1) * er * 0.35, ey + Math.sin(h - 1) * er * 0.35, er * 0.13, 0, TAU); ctx.fill();
    if (small) return;
    // the lashes: a fan of strokes on the back of the eye
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.6, hr * 0.08);
    for (let k = -3; k <= 3; k++) {
      const a = h + Math.PI + k * 0.32, x0 = ex + Math.cos(a) * er, y0 = ey + Math.sin(a) * er;
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + Math.cos(a) * er * 0.55, y0 + Math.sin(a) * er * 0.55); ctx.stroke();
    }
  }
  // the shining ones carry a starburst of rainbow rays
  function burst(ctx, pts, look, t, alpha) {
    const glow = look[4] || 0;
    if (glow < 0.35) return;
    const [hx, hy, hr] = pts[0], R = hr * (2.2 + 1.4 * glow), n = 14;
    ctx.save(); ctx.globalAlpha = alpha * Math.min(1, (glow - 0.35) * 3) * 0.85;
    for (let k = 0; k < n; k++) {
      const a0 = k / n * TAU + t * 0.2, a1 = a0 + TAU / n * 0.5;
      ctx.beginPath(); ctx.moveTo(hx, hy); ctx.arc(hx, hy, R * (k % 2 ? 0.85 : 1), a0, a1); ctx.closePath();
      ctx.fillStyle = RAINBOW[k % RAINBOW.length]; ctx.fill();
    }
    ctx.restore();
  }
  function animal(ctx, A) {
    const { pts, r0, ph, p, look, base, alt, t } = A;
    const [, , , pattern, glow, , limbs, , tail, crest, fin, diet] = look;
    const small = r0 < 5, insul = look[13] || 0;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    if (glow >= 0.35) burst(ctx, pts, look, t, A.alpha);
    // legs: striped in the two colours, bending at a knee, three ink claws
    if (limbs > 0) {
      for (let k = 0; k < limbs; k++) {
        const i = Math.min(pts.length - 1, Math.round((k + 0.5) * pts.length / limbs - 0.5));
        const [px, py, r, a] = pts[i], step = Math.sin(ph * 1.6 + k * 1.7) * 0.45;
        for (const side of [-1, 1]) {
          const la = a + side * (Math.PI / 2 + step * side), len = r * 1.9;
          const kx = px + Math.cos(la) * len * 0.55, ky = py + Math.sin(la) * len * 0.55;
          const fa = la - side * 0.6, fx = kx + Math.cos(fa) * len * 0.55, fy = ky + Math.sin(fa) * len * 0.55;
          const w = Math.max(1.2, r * 0.42);
          ctx.strokeStyle = INK; ctx.lineWidth = w + Math.max(1, r * 0.16);
          ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(kx, ky); ctx.lineTo(fx, fy); ctx.stroke();
          ctx.lineWidth = w; ctx.strokeStyle = alt; ctx.stroke();
          if (!small) {                                               // stripes: dashes of the body colour along the leg
            ctx.setLineDash([w * 0.55, w * 0.55]); ctx.strokeStyle = base; ctx.stroke(); ctx.setLineDash([]);
            ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.6, r * 0.1);
            for (const c of [-0.5, 0, 0.5]) { const ca = fa + c; ctx.beginPath(); ctx.moveTo(fx, fy); ctx.lineTo(fx + Math.cos(ca) * r * 0.45, fy + Math.sin(ca) * r * 0.45); ctx.stroke(); }
          }
        }
      }
    }
    // tail: a long curl ending in a bloom (fins make it a fan of striped feathers instead)
    const [tx, ty, tr, ta] = pts[pts.length - 1];
    if (tail > 0.15) {
      const L = r0 * (2 + 3 * tail), sw = Math.sin(ph) * 0.5;
      const c1x = tx - Math.cos(ta) * L * 0.5 + Math.cos(ta + Math.PI / 2) * L * 0.35 * sw, c1y = ty - Math.sin(ta) * L * 0.5 + Math.sin(ta + Math.PI / 2) * L * 0.35 * sw;
      const ex = tx - Math.cos(ta + sw * 0.8) * L, ey = ty - Math.sin(ta + sw * 0.8) * L;
      if (fin > 0.5) {
        const nf = 5;
        for (let k = 0; k < nf; k++) {
          const aa = ta + Math.PI + (k / (nf - 1) - 0.5) * 1.2 + sw * 0.3;
          ctx.save(); ctx.translate(tx, ty); ctx.rotate(aa);
          teardrop(ctx, L * 0.8, r0 * 0.3); ctx.fillStyle = RAINBOW[k % RAINBOW.length]; ctx.fill(); ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.7, r0 * 0.1); ctx.stroke();
          ctx.restore();
        }
      } else {
        ctx.beginPath(); ctx.moveTo(tx, ty); ctx.quadraticCurveTo(c1x, c1y, ex, ey);
        ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1.4, r0 * 0.42); ctx.stroke();
        ctx.strokeStyle = base; ctx.lineWidth = Math.max(0.8, r0 * 0.24); ctx.stroke();
        if (!small) { ctx.setLineDash([r0 * 0.15, r0 * 0.3]); ctx.strokeStyle = WHITE; ctx.lineWidth = Math.max(0.6, r0 * 0.1); ctx.stroke(); ctx.setLineDash([]); }
        rosette(ctx, ex, ey, r0 * (0.45 + 0.35 * tail), alt, YELLOW);
        ctx.beginPath(); ctx.arc(ex, ey, r0 * (0.45 + 0.35 * tail) * 0.38, 0, TAU); ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.6, r0 * 0.08); ctx.stroke();
      }
    }
    // a coat: a fringe of short coloured fur strokes
    if (insul > 0.3 && !small) {
      ctx.lineWidth = Math.max(0.8, r0 * 0.14);
      for (const [px, py, r, a] of pts) {
        const nf = 14, fl = r * (0.25 + 0.4 * insul);
        for (let k = 0; k < nf; k++) {
          const aa = a + k / nf * TAU, x0 = px + Math.cos(aa) * r * 1.05, y0 = py + Math.sin(aa) * r * 0.95;
          ctx.strokeStyle = k % 2 ? ORANGE : INK; ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + Math.cos(aa) * fl, y0 + Math.sin(aa) * fl); ctx.stroke();
        }
      }
    }
    // the body, tail end first
    for (let i = pts.length - 1; i >= 1; i--) { const [px, py, r, a] = pts[i]; segment(ctx, px, py, r * 1.04, a, i, pattern, base, alt, small); }
    // crest: a plume of fan feathers, each a teardrop in the rainbow with a white-dotted spine
    if (crest > 0.25) {
      const [px, py, r, a] = pts[0], nf = 3 + Math.round(crest * 3), L = r * (1.1 + 1.8 * crest);
      for (let k = 0; k < nf; k++) {
        const aa = a + Math.PI + (k / (nf - 1) - 0.5) * 1.6;
        ctx.save(); ctx.translate(px - Math.cos(a) * r * 0.2, py - Math.sin(a) * r * 0.2); ctx.rotate(aa);
        teardrop(ctx, L, r * 0.32); ctx.fillStyle = RAINBOW[(k + 2) % RAINBOW.length]; ctx.fill();
        ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.7, r * 0.12); ctx.stroke();
        if (!small) { ctx.fillStyle = WHITE; for (let q = 1; q <= 3; q++) { ctx.beginPath(); ctx.arc(L * (0.2 + q * 0.2), 0, Math.max(0.5, r * 0.07), 0, TAU); ctx.fill(); } }
        ctx.restore();
      }
    }
    // the head: a round face in the body colour, a cheek dot, the big eye, and for hunters a toothy grin
    const [hx, hy, hr] = pts[0], h = p.h;
    ctx.beginPath(); ctx.arc(hx, hy, hr * 1.1, 0, TAU); ctx.fillStyle = base; ctx.fill();
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.9, hr * 0.2); ctx.stroke();
    if (!small) {
      ctx.fillStyle = PINK; ctx.beginPath(); ctx.arc(hx + Math.cos(h + 1.3) * hr * 0.55, hy + Math.sin(h + 1.3) * hr * 0.55, hr * 0.2, 0, TAU); ctx.fill();
      if (diet > 0.6) {
        const mx = hx + Math.cos(h) * hr * 0.85, my = hy + Math.sin(h) * hr * 0.85;
        ctx.fillStyle = RED; ctx.beginPath(); ctx.arc(mx, my, hr * 0.38, h - 1.2, h + 1.2); ctx.closePath(); ctx.fill();
        ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.6, hr * 0.08); ctx.stroke();
        ctx.fillStyle = WHITE;
        for (const s of [-0.6, 0, 0.6]) {
          const ba = h + s, bx = mx + Math.cos(ba) * hr * 0.3, by = my + Math.sin(ba) * hr * 0.3;
          ctx.beginPath(); ctx.moveTo(bx + Math.cos(ba + 1.57) * hr * 0.08, by + Math.sin(ba + 1.57) * hr * 0.08);
          ctx.lineTo(bx - Math.cos(ba + 1.57) * hr * 0.08, by - Math.sin(ba + 1.57) * hr * 0.08); ctx.lineTo(bx - Math.cos(ba) * hr * 0.18, by - Math.sin(ba) * hr * 0.18); ctx.fill();
        }
      }
    }
    eye(ctx, hx, hy, hr, h, diet, small);
  }

  // ── the cabinet: a violet sky of rainbow sunbursts and stars, a border of folk dots ──
  function rr(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
  function star(g, x, y, r, c) {
    g.beginPath();
    for (let k = 0; k < 10; k++) { const a = k / 10 * TAU - Math.PI / 2, rr2 = k % 2 ? r * 0.42 : r; g[k ? 'lineTo' : 'moveTo'](x + Math.cos(a) * rr2, y + Math.sin(a) * rr2); }
    g.closePath(); g.fillStyle = c; g.fill(); g.strokeStyle = INK; g.lineWidth = Math.max(1, r * 0.12); g.stroke();
  }
  let cabCache = null;
  function cabinet(ctx, L) {
    const key = [L.cw, L.ch].join('|');
    if (!cabCache || cabCache.key !== key) {
      const c = document.createElement('canvas'); c.width = L.cw; c.height = L.ch;
      const g = c.getContext('2d'), { cw, ch, u } = L;
      g.fillStyle = VIOLET; g.fillRect(0, 0, cw, ch);
      // two rainbow sunbursts rising from the bottom corners, in concentric bands
      for (const [ox, oy] of [[0, ch], [cw, ch], [cw * 0.5, -ch * 0.1]]) {
        const R = Math.hypot(cw, ch) * 0.75, bw = u * 0.03;
        for (let k = Math.floor(R / bw); k >= 0; k--) { g.beginPath(); g.arc(ox, oy, k * bw, 0, TAU); g.fillStyle = k % 2 ? VIOLET : [MAGENTA, ORANGE, YELLOW, LIME, TURQ, BLUE][k / 2 % 6]; g.globalAlpha = 0.5; g.fill(); }
        g.globalAlpha = 1;
      }
      for (let k = 0; k < 26; k++) star(g, hash(k, 3) * cw, hash(k, 4) * ch, u * (0.006 + hash(k, 5) * 0.01), [YELLOW, WHITE, PINK][k % 3]);
      // a border of dots, folk-fashion
      const b = u * 0.016, step = u * 0.02;
      g.lineWidth = b; g.strokeStyle = INK; rr(g, b * 0.5, b * 0.5, cw - b, ch - b, u * 0.03); g.stroke();
      let k = 0;
      for (let x = b * 2; x < cw - b; x += step) for (const y of [b * 0.5, ch - b * 0.5]) { g.fillStyle = RAINBOW[k++ % RAINBOW.length]; g.beginPath(); g.arc(x, y, b * 0.3, 0, TAU); g.fill(); }
      for (let y = b * 2; y < ch - b; y += step) for (const x of [b * 0.5, cw - b * 0.5]) { g.fillStyle = RAINBOW[k++ % RAINBOW.length]; g.beginPath(); g.arc(x, y, b * 0.3, 0, TAU); g.fill(); }
      for (const [x, y] of [[b * 2.6, b * 2.6], [cw - b * 2.6, b * 2.6], [b * 2.6, ch - b * 2.6], [cw - b * 2.6, ch - b * 2.6]]) {
        g.save(); g.translate(x, y); flower(g, u * 0.026, { petals: 7, hue: 0.0, sat: 1, hue2: 0.15 }, true); g.restore();
      }
      cabCache = { key, c };
    }
    ctx.drawImage(cabCache.c, 0, 0);
  }
  // the window's frame: black, with thin rainbow bands round it
  function bezel(ctx, L) {
    const { pf, u } = L, b = u * 0.004;
    ctx.save();
    const cols = [INK, RED, ORANGE, YELLOW, GREEN, BLUE, VIOLET, INK];
    cols.forEach((c, k) => { ctx.lineWidth = b * 1.05; ctx.strokeStyle = c; rr(ctx, pf.x - b * (k + 0.5), pf.y - b * (k + 0.5), pf.w + b * (2 * k + 1), pf.h + b * (2 * k + 1), u * 0.016 + b * k); ctx.stroke(); });
    ctx.restore();
  }
  function metal(ctx, x0, y0, x1, y1) {
    const g = ctx.createLinearGradient(x0, y0, x1, y1);
    RAINBOW.forEach((c, k) => g.addColorStop(k / (RAINBOW.length - 1), c));
    return g;
  }
  // the pins: a dotted folk flower-head
  function pin(ctx, X, Y, r, night, t, seed) {
    ctx.fillStyle = 'rgba(21,18,21,0.3)'; ctx.beginPath(); ctx.arc(X + r * 0.35, Y + r * 0.45, r, 0, TAU); ctx.fill();
    ctx.fillStyle = RAINBOW[Math.floor(seed) % RAINBOW.length] || RED; ctx.beginPath(); ctx.arc(X, Y, r, 0, TAU); ctx.fill();
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.6, r * 0.18); ctx.stroke();
    ctx.fillStyle = night > 0.4 && (Math.floor(seed + t * 2) % 9 === 0) ? WHITE : YELLOW;
    ctx.beginPath(); ctx.arc(X, Y, r * 0.42, 0, TAU); ctx.fill();
  }
  // the tray: a pink board with a yellow-dotted edge
  function tray(ctx, T, u) {
    ctx.save();
    rr(ctx, T.x, T.y, T.w, T.h, u * 0.02); ctx.fillStyle = PINK; ctx.fill();
    ctx.lineWidth = u * 0.004; ctx.strokeStyle = INK; ctx.stroke();
    let k = 0;
    for (let x = T.x + u * 0.02; x < T.x + T.w - u * 0.015; x += u * 0.014) for (const y of [T.y + u * 0.011, T.y + T.h - u * 0.011]) { ctx.fillStyle = k++ % 2 ? YELLOW : WHITE; ctx.beginPath(); ctx.arc(x, y, u * 0.003, 0, TAU); ctx.fill(); }
    ctx.restore();
  }
  // the nameplate: a bubbly cloud of lemon, lettered fat and round in magenta with a black drop shadow
  function nameplate(ctx, x, y, w, h, text, u) {
    ctx.save();
    const n = Math.max(6, Math.round(w / h * 2.2)), br = h * 0.32;
    ctx.beginPath();
    for (let k = 0; k <= n; k++) { const bx = x + br + (w - 2 * br) * k / n; ctx.moveTo(bx + br, y + br); ctx.arc(bx, y + br, br, 0, TAU); ctx.moveTo(bx + br, y + h - br); ctx.arc(bx, y + h - br, br, 0, TAU); }
    ctx.rect(x + br * 0.6, y + br, w - br * 1.2, h - 2 * br);
    ctx.fillStyle = INK; ctx.save(); ctx.translate(u * 0.004, u * 0.005); ctx.fill(); ctx.restore();
    ctx.fillStyle = YELLOW; ctx.fill();
    ctx.fillStyle = MAGENTA; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    let fs = h * 0.56; ctx.font = `${fs}px "Shrikhand", "Righteous", sans-serif`;
    while (ctx.measureText(text).width > w - br * 2.4 && fs > 6) { fs -= 1; ctx.font = `${fs}px "Shrikhand", "Righteous", sans-serif`; }
    ctx.fillStyle = INK; ctx.fillText(text, x + w / 2 + fs * 0.06, y + h / 2 + fs * 0.1);
    ctx.fillStyle = MAGENTA; ctx.fillText(text, x + w / 2, y + h / 2 + fs * 0.04);
    ctx.restore();
  }
  function frame() { /* full bleed: nothing between the window and the world */ }

  window.ALGO_SKIN = {
    id: 'folkpop', slug: 'folkpop', wantsHeight: true,
    mushroom: { ink: INK, cap: (h, S, L) => css(pop(h * 360)), gill: WHITE, ring: MAGENTA, umbo: YELLOW, spot: WHITE, shine: 'rgba(255,250,240,0.7)', lines: VIOLET },
    organs: { ink: INK, eye: WHITE, plate: YELLOW, wing: PINK, jaw: WHITE, wingA: 0.85 },
    terrainPixel, animalColors, animal, flower, flowerPad: 0.25,
    frame, cabinet, bezel, metal, pin, tray, nameplate,
  };
})();
