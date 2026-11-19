/* Algogenesis — the Coast as a dream.

   The same living world, drawn the way the dark side is: dim, soft and luminous. No creature is drawn as a body. Each
   species has one bright colour, and every member breathes a soft cloud of it into the air; where a species gathers, its clouds
   merge into one glowing drift, and as the animals move, graze, flee and breed the drifts shift, part and mingle. Where
   two species meet their colours mix. Flowers are a faint haze of pollen in their own species' colours, fruiting
   mushrooms a violet breath, and each animal a faint point of light inside its cloud. The land has no lines at all:
   after Rothko, it is a few great fields of colour (plum sea, crimson shore, orange and ochre heights) that bleed into
   one another over wide feathered bands, with the uneven density of thinned paint and a slow haze moving over them.

   Loaded before panel.js, it sets window.ALGO_SKIN; panel.js hands it the whole of life through the `life` hook. */
(function () {
  'use strict';
  const TAU = Math.PI * 2;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, k) => a.map((v, i) => Math.round(v + (b[i] - v) * k));
  const hash = (x, y) => { let h = (x * 374761393 + y * 668265263) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };

  // ── the land as colour fields, after Rothko: no lines, no shore, no contours. Height only chooses which field a
  //    place belongs to, and the fields bleed into one another over a wide, feathered band, with the slow uneven
  //    density of thinned paint laid on in layers ──
  const FIELDS = [            // [height, colour]: the ramp the land is painted on
    [-0.9, [52, 16, 74]], [-0.35, [92, 22, 88]], [-0.08, [150, 30, 70]], [0.08, [196, 52, 44]],
    [0.3, [226, 104, 38]], [0.6, [238, 160, 58]], [1.0, [246, 206, 120]]];
  const SNOWF = [250, 226, 190];
  function vnoise(x, y) {     // smooth value noise for the paint's uneven density
    const ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy, sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
    const a = hash(ix, iy), b = hash(ix + 1, iy), c = hash(ix, iy + 1), d = hash(ix + 1, iy + 1);
    return (a * (1 - sx) + b * sx) * (1 - sy) + (c * (1 - sx) + d * sx) * sy;
  }
  function terrainPixel(z, lev, snowy, wx, wy, name, h) {
    // feather the height itself, so the boundary between two fields is a soft band, not an edge
    const hh = h + (vnoise(wx * 0.006, wy * 0.006) - 0.5) * 0.22;
    let k = 0;
    while (k < FIELDS.length - 2 && hh > FIELDS[k + 1][0]) k++;
    const [h0, c0] = FIELDS[k], [h1, c1] = FIELDS[k + 1], f = clamp((hh - h0) / (h1 - h0), 0, 1);
    let c = lerp(c0, c1, f * f * (3 - 2 * f));
    if (snowy) c = lerp(c, SNOWF, 0.55);
    // layered paint: broad, slow variations in density, brighter here, deeper there
    const v = (vnoise(wx * 0.011, wy * 0.011) - 0.5) * 0.16 + (vnoise(wx * 0.035 + 7, wy * 0.035) - 0.5) * 0.06;
    return c.map(x => clamp(Math.round(x * (1 + v)), 0, 255));
  }

  // ── colour of a species: fixed by its first member's genes, so a whole species reads as one shade ──
  const spCol = new Map();
  function colourOf(sp, hue, kind) {
    const k = kind + sp;
    let c = spCol.get(k);
    if (!c) {
      // animal species are spread round the colour wheel by the golden angle, so neighbouring species read as distinct shades
      const H = kind === 'a' ? (Number(sp) * 137.508 + hue * 60) % 360 : hue * 360, S = kind === 'p' ? 80 : 92, L = kind === 'p' ? 66 : 58;
      c = { css: `hsl(${H},${S}%,${L}%)`, sprite: null, core: null };
      spCol.set(k, c);
      if (spCol.size > 4000) spCol.delete(spCol.keys().next().value);
    }
    return c;
  }
  // a soft round breath of a colour, with a gaussian-like falloff; drawn small and scaled up
  function puff(css) {
    const n = 64, c = document.createElement('canvas'); c.width = c.height = n;
    const g = c.getContext('2d'), gr = g.createRadialGradient(n / 2, n / 2, 0, n / 2, n / 2, n / 2);
    const m = css.match(/hsl\(([^,]+),([^,]+)%,([^)]+)%\)/), base = `hsla(${m[1]},${m[2]}%,${m[3]}%,`;
    [[0, 1], [0.25, 0.78], [0.5, 0.42], [0.75, 0.13], [1, 0]].forEach(([o, a]) => gr.addColorStop(o, base + a + ')'));
    g.fillStyle = gr; g.fillRect(0, 0, n, n);
    return c;
  }
  const spriteOf = c => c.sprite || (c.sprite = puff(c.css));

  // ── the mist: a tiling soft noise texture, panned slowly in two layers ──
  let mist = null;
  function mistTex() {
    if (mist) return mist;
    const n = 256, c = document.createElement('canvas'); c.width = c.height = n;
    const g = c.getContext('2d'), img = g.createImageData(n, n);
    const G = 8, val = (x, y) => hash(((x % G) + G) % G, ((y % G) + G) % G);
    const sm = t => t * t * (3 - 2 * t);
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      let v = 0, amp = 0.6, f = G / n;
      for (let o = 0; o < 3; o++) {
        const fx = x * f * (1 << o), fy = y * f * (1 << o), ix = Math.floor(fx), iy = Math.floor(fy), tx = sm(fx - ix), ty = sm(fy - iy);
        const a = val(ix, iy), b = val(ix + 1, iy), cc = val(ix, iy + 1), d = val(ix + 1, iy + 1);
        v += amp * ((a * (1 - tx) + b * tx) * (1 - ty) + (cc * (1 - tx) + d * tx) * ty); amp *= 0.5;
      }
      const i = (y * n + x) * 4, k = clamp((v - 0.45) * 2.2, 0, 1);
      img.data[i] = 255; img.data[i + 1] = 214; img.data[i + 2] = 190; img.data[i + 3] = Math.round(k * 255);
    }
    g.putImageData(img, 0, 0);
    return (mist = c);
  }

  // ── life, all of it at once ──
  let cloud = null, cctx = null;
  const DOWN = 5;                       // the cloud layer is drawn at a fifth of the resolution, then laid over softly
  function life(ctx, S) {
    const { animals, plants, fungi, now, t, light, night, pos, L } = S, pf = L.pf;
    const cw = Math.max(8, Math.ceil(pf.w / DOWN)), ch = Math.max(8, Math.ceil(pf.h / DOWN));
    if (!cloud || cloud.width !== cw || cloud.height !== ch) { cloud = document.createElement('canvas'); cloud.width = cw; cloud.height = ch; cctx = cloud.getContext('2d'); }
    // night deepens the land a little; the clouds glow brighter against it
    if (night > 0.01) { ctx.fillStyle = `rgba(20,4,30,${0.3 * night})`; ctx.fillRect(pf.x, pf.y, pf.w, pf.h); }
    cctx.setTransform(1, 0, 0, 1, 0, 0); cctx.globalCompositeOperation = 'source-over'; cctx.clearRect(0, 0, cw, ch);
    cctx.globalCompositeOperation = 'lighter';
    const zs = L.s / DOWN, ox = (L.ox - pf.x) / DOWN, oy = (L.oy - pf.y) / DOWN;
    const vis = (x, y, r) => { const X = ox + x * zs, Y = oy + y * zs, R = r * zs; return X + R > 0 && X - R < cw && Y + R > 0 && Y - R < ch; };
    // pollen haze: each flower a faint breath of its species' colour
    for (const p of plants.values()) {
      let a = Math.min(1, (now - p.born) / 1500);
      if (p.dead) { a = Math.max(0, 1 - (now - p.dead) / 1500); if (a <= 0) { plants.delete(p.id); continue; } }
      const R = (14 + 10 * p.size) * (0.6 + 0.4 * p.nectar);
      if (!vis(p.x, p.y, R)) continue;
      const c = colourOf(p.sp, p.hue, 'p'), r = R * zs;
      cctx.globalAlpha = 0.06 * a * (0.6 + 0.4 * light);
      cctx.drawImage(spriteOf(c), ox + p.x * zs - r, oy + p.y * zs - r, 2 * r, 2 * r);
    }
    // fruiting mushrooms: a violet breath
    for (const o of fungi.values()) {
      if (o.dead) continue;
      const f = o.fruitTo || 0;
      if (f < 0.1 || !vis(o.x, o.y, 20)) continue;
      const c = colourOf('fungus', 0.76, 'f'), r = (10 + 10 * f) * zs;
      cctx.globalAlpha = 0.12 * f;
      cctx.drawImage(spriteOf(c), ox + o.x * zs - r, oy + o.y * zs - r, 2 * r, 2 * r);
    }
    // the animals: every member a cloud of its species' colour; together, a drift
    const cores = [];
    for (const o of animals.values()) {
      let a = Math.max(0, Math.min(1, (now - o.born) / 900));
      if (o.dead) { a = Math.min(a, Math.max(0, 1 - (now - o.dead) / 1600)); if (now > o.dead && a <= 0) { animals.delete(o.id); continue; } }
      if (a <= 0) continue;
      const q = pos(o, now), size = o.look[7] || 1, grown = o.grown == null ? 1 : o.grown;
      const breathe = 1 + 0.18 * Math.sin(t * 0.55 + o.phase), R = (50 + 22 * size) * (0.6 + 0.4 * grown) * breathe;
      if (!vis(q.x, q.y, R)) continue;
      const c = colourOf(o.sp, o.look[0], 'a'), r = R * zs, X = ox + q.x * zs, Y = oy + q.y * zs;
      cctx.globalAlpha = 0.1 * a;
      cctx.drawImage(spriteOf(c), X - r, Y - r, 2 * r, 2 * r);
      cores.push([pf.x + X * DOWN, pf.y + Y * DOWN, c, a, o.look[4] || 0, o.phase]);
    }
    cctx.globalAlpha = 1;
    // lay the clouds over the land, softly
    ctx.save();
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.globalCompositeOperation = 'screen';
    ctx.drawImage(cloud, 0, 0, cw, ch, pf.x, pf.y, cw * DOWN, ch * DOWN);
    ctx.globalAlpha = 0.3; ctx.globalCompositeOperation = 'lighter';
    ctx.drawImage(cloud, 0, 0, cw, ch, pf.x, pf.y, cw * DOWN, ch * DOWN);
    // each creature a firefly point in its cloud; the glowing ones flicker brighter
    ctx.globalCompositeOperation = 'lighter';
    const cr = clamp(L.s * 1.6, 1.2, 7);
    for (const [x, y, c, a, glow, ph] of cores) {
      const flick = 0.55 + 0.45 * Math.sin(t * (1.5 + glow * 3) + ph * 3);
      ctx.globalAlpha = a * (0.12 + 0.3 * glow) * flick;
      const r = cr * (1 + glow);
      ctx.drawImage(spriteOf(c), x - r * 2, y - r * 2, r * 4, r * 4);
      ctx.fillStyle = 'rgba(255,250,240,0.9)'; ctx.globalAlpha = a * 0.18 * flick;
      ctx.beginPath(); ctx.arc(x, y, Math.max(0.6, cr * 0.35), 0, TAU); ctx.fill();
    }
    ctx.restore();
  }

  // the mist and a soft vignette over the window (light side only; the dark side keeps its own)
  function frame(ctx, L, t, night, isDark) {
    if (isDark) return;
    const pf = L.pf, m = mistTex(), sc = Math.max(pf.w, pf.h) / 256 * 1.2;
    ctx.save();
    ctx.globalCompositeOperation = 'screen';
    for (const [k, sp, a] of [[1.4, 3, 0.12], [2.3, -2, 0.08]]) {
      const s = sc * k, w = 256 * s, dx = ((t * sp) % w + w) % w, dy = ((t * sp * 0.4) % w + w) % w;
      ctx.globalAlpha = a * (1 - 0.4 * night);
      for (let x = pf.x - dx; x < pf.x + pf.w; x += w) for (let y = pf.y - dy; y < pf.y + pf.h; y += w) ctx.drawImage(m, x, y, w, w);
    }
    ctx.restore();
    const vg = ctx.createRadialGradient(pf.x + pf.w / 2, pf.y + pf.h / 2, Math.min(pf.w, pf.h) * 0.35, pf.x + pf.w / 2, pf.y + pf.h / 2, Math.hypot(pf.w, pf.h) * 0.6);
    vg.addColorStop(0, 'rgba(40,8,30,0)'); vg.addColorStop(1, 'rgba(40,8,30,0.5)');
    ctx.fillStyle = vg; ctx.fillRect(pf.x, pf.y, pf.w, pf.h);
  }

  // ── the cabinet: night, a few faint stars, hairlines of lavender light ──
  function rr(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
  let cab = null;
  function cabinet(ctx, L) {
    const key = L.cw + '|' + L.ch;
    if (!cab || cab.key !== key) {
      const c = document.createElement('canvas'); c.width = L.cw; c.height = L.ch;
      const g = c.getContext('2d'), { cw, ch, u } = L;
      const gr = g.createLinearGradient(0, 0, 0, ch); gr.addColorStop(0, '#0b0a1c'); gr.addColorStop(1, '#170f2c');
      g.fillStyle = gr; g.fillRect(0, 0, cw, ch);
      for (let k = 0; k < 140; k++) {
        const x = hash(k, 11) * cw, y = hash(k, 12) * ch, r = u * (0.0008 + hash(k, 13) * 0.0016);
        g.fillStyle = `rgba(210,205,255,${0.2 + 0.5 * hash(k, 14)})`; g.beginPath(); g.arc(x, y, r, 0, TAU); g.fill();
      }
      g.strokeStyle = 'rgba(170,160,255,0.22)'; g.lineWidth = u * 0.002; rr(g, u * 0.01, u * 0.01, cw - u * 0.02, ch - u * 0.02, u * 0.03); g.stroke();
      cab = { key, c };
    }
    ctx.drawImage(cab.c, 0, 0);
  }
  function bezel(ctx, L) {
    const { pf, u } = L;
    ctx.save();
    ctx.shadowColor = 'rgba(150,140,255,0.55)'; ctx.shadowBlur = u * 0.02;
    ctx.strokeStyle = 'rgba(200,192,255,0.5)'; ctx.lineWidth = u * 0.0025;
    rr(ctx, pf.x - u * 0.003, pf.y - u * 0.003, pf.w + u * 0.006, pf.h + u * 0.006, u * 0.02); ctx.stroke();
    ctx.restore();
  }
  function metal(ctx, x0, y0, x1, y1) {
    const g = ctx.createLinearGradient(x0, y0, x1, y1);
    g.addColorStop(0, '#3a3560'); g.addColorStop(0.5, '#8b84c4'); g.addColorStop(1, '#2a2648');
    return g;
  }
  function pin(ctx, X, Y, r, night, t, seed) {
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    ctx.fillStyle = `rgba(190,185,255,${0.25 + 0.15 * Math.sin(t + seed)})`; ctx.beginPath(); ctx.arc(X, Y, r * 0.6, 0, TAU); ctx.fill();
    ctx.restore();
  }
  function tray(ctx, T, u) {
    ctx.save();
    rr(ctx, T.x, T.y, T.w, T.h, u * 0.02); ctx.fillStyle = 'rgba(20,16,44,0.85)'; ctx.fill();
    ctx.strokeStyle = 'rgba(170,160,255,0.3)'; ctx.lineWidth = u * 0.0018; ctx.stroke();
    ctx.restore();
  }
  function nameplate(ctx, x, y, w, h, text, u) {
    ctx.save();
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    let fs = h * 0.66;
    const font = s => `italic 300 ${s}px "Cormorant Garamond", Georgia, serif`;
    ctx.font = font(fs);
    const label = text.split('').join(' ');
    while (ctx.measureText(label).width > w * 0.96 && fs > 6) { fs -= 1; ctx.font = font(fs); }
    ctx.shadowColor = 'rgba(160,150,255,0.8)'; ctx.shadowBlur = fs * 0.5;
    ctx.fillStyle = '#e4dfff'; ctx.fillText(label, x + w / 2, y + h / 2);
    ctx.restore();
  }

  window.ALGO_SKIN = {
    id: 'dream', slug: 'dream', wantsHeight: true, noNight: true,
    terrainPixel, life, frame, cabinet, bezel, metal, pin, tray, nameplate,
  };
})();
