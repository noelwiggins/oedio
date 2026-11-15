/* MORPHOGENESIS: a lit sea floor seen from the side. Each organism's cells are drawn as flat tiles in its own two
   colours (stem, leaf), with growing tips as cream beads; whole forms sway with the water. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  let gw = 180, gh = 96, types = null, slots = null, pal = new Map(), floor = [], sed = [];
  const CELL = 6;              // world units per cell (world is gw*6 by gh*6)

  function unrle(r, n) {
    const out = new Uint16Array(n);
    let k = 0;
    for (let i = 0; i < r.length; i += 2) { out.fill(r[i], k, k + r[i + 1]); k += r[i + 1]; }
    return out;
  }
  function ingest(d) {
    gw = d.gw; gh = d.gh; floor = d.floor; sed = d.sediment || [];
    types = unrle(d.types, gw * gh); slots = unrle(d.slots, gw * gh);
    pal = new Map(d.palette.map(([slot, h1, h2, lin]) => [slot, { h1, h2, lin }]));
  }

  function background(ctx, V, t, light) {
    const W = gw * CELL, H = gh * CELL;
    const bands = [[0, '#cfeee6'], [0.2, '#8fd3c8'], [0.48, '#3f97b5'], [0.78, '#2b5f86']];
    for (let i = 0; i < bands.length; i++) {
      const y0 = V.oy + bands[i][0] * H * V.s, y1 = V.oy + (i + 1 < bands.length ? bands[i + 1][0] : 1) * H * V.s;
      ctx.fillStyle = bands[i][1]; ctx.fillRect(V.ox, y0, W * V.s, y1 - y0 + 1);
      if (i) { ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 1.1 * V.s); ctx.beginPath(); ctx.moveTo(V.ox, y0); ctx.lineTo(V.ox + W * V.s, y0); ctx.stroke(); }
    }
    // shafts of light from the surface
    ctx.save(); ctx.globalAlpha = 0.18 * light;
    ctx.fillStyle = '#fbf3dc';
    for (let k = 0; k < 6; k++) {
      const x = V.ox + ((k * 211 + t * 9) % W) * V.s, w = (30 + 20 * Math.sin(k)) * V.s;
      ctx.beginPath(); ctx.moveTo(x, V.oy); ctx.lineTo(x + w, V.oy); ctx.lineTo(x + w * 2.4 + 80 * V.s, V.oy + H * V.s * 0.8); ctx.lineTo(x + 80 * V.s, V.oy + H * V.s * 0.8); ctx.closePath(); ctx.fill();
    }
    ctx.restore();
    // the floor
    if (floor.length) {
      ctx.fillStyle = '#d9c27a'; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 1.6 * V.s);
      ctx.beginPath(); ctx.moveTo(V.ox, V.oy + H * V.s);
      for (let x = 0; x < gw; x++) ctx.lineTo(V.ox + (x + 0.5) * CELL * V.s, V.oy + floor[x] * CELL * V.s);
      ctx.lineTo(V.ox + W * V.s, V.oy + H * V.s); ctx.closePath(); ctx.fill(); ctx.stroke();
      // pebbles
      ctx.fillStyle = '#b8954a';
      for (let x = 3; x < gw; x += 7) { const yy = floor[x] + 2 + (x * 7) % 4; ctx.beginPath(); ctx.arc(V.ox + x * CELL * V.s, V.oy + yy * CELL * V.s, 2.2 * V.s, 0, Math.PI * 2); ctx.fill(); }
    }
  }

  function draw(ctx, V, now, t, light) {
    background(ctx, V, t, light);
    if (!types) return;
    const c = CELL * V.s, n = gw * gh;
    const sway = (x, y, slot) => Math.sin(t * 0.8 + slot * 0.7 + x * 0.02) * (gh - y) / gh * 6 * V.s;
    // pass 1: ink silhouettes; pass 2: colours
    ctx.fillStyle = INK;
    for (let i = 0; i < n; i++) {
      if (!types[i] || types[i] === 5) continue;
      const x = i % gw, y = (i / gw) | 0, sl = slots[i];
      ctx.fillRect(V.ox + x * c + sway(x, y, sl) - c * 0.14, V.oy + y * c - c * 0.14, c * 1.28, c * 1.28);
    }
    for (let i = 0; i < n; i++) {
      const ty = types[i];
      if (!ty) continue;
      const x = i % gw, y = (i / gw) | 0, sl = slots[i], p = pal.get(sl) || { h1: 0.1, h2: 0.3 };
      const X = V.ox + x * c + sway(x, y, sl), Y = V.oy + y * c;
      if (ty === 1) { ctx.fillStyle = `hsl(${p.h1 * 360},40%,38%)`; ctx.fillRect(X, Y, c, c); }
      else if (ty === 2) {
        ctx.fillStyle = `hsl(${p.h2 * 360},68%,${54 + 8 * light}%)`;
        ctx.beginPath(); ctx.ellipse(X + c / 2, Y + c / 2, c * 0.62, c * 0.5, 0.4, 0, Math.PI * 2); ctx.fill();
      } else if (ty === 3) { ctx.fillStyle = '#fbf3dc'; ctx.beginPath(); ctx.arc(X + c / 2, Y + c / 2, c * 0.5, 0, Math.PI * 2); ctx.fill(); }
      else if (ty === 5) { ctx.fillStyle = 'rgba(251,243,220,0.55)'; ctx.fillRect(X + c * 0.3, Y + c * 0.3, c * 0.4, c * 0.4); }
      else { ctx.fillStyle = '#e5602a'; ctx.beginPath(); ctx.arc(X + c / 2, Y + c / 2, c * 0.55, 0, Math.PI * 2); ctx.fill(); }
    }
  }
  function drawGlow(ctx, V, now, t, light) {
    if (light > 0.85 || !types) return;
    const dark = Math.min(1, (0.85 - light) / 0.6), c = CELL * V.s;
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < gw * gh; i++) {
      if (types[i] !== 3) continue;
      const x = i % gw, y = (i / gw) | 0;
      ctx.fillStyle = `rgba(255,236,170,${0.22 * dark})`;
      ctx.beginPath(); ctx.arc(V.ox + (x + 0.5) * c, V.oy + (y + 0.5) * c, c * 1.4, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  // the dark side, Morpholysis: living forms as dim silhouettes, fallen cells sinking as marine snow in bone,
  // and the sediment they leave glowing amber along the floor
  function drawDark(ctx, V, now, t, light) {
    const W = gw * CELL, H = gh * CELL, c = CELL * V.s;
    ctx.fillStyle = '#0b0d16'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    if (!types) return;
    if (floor.length) {
      ctx.fillStyle = '#1a1510'; ctx.beginPath(); ctx.moveTo(V.ox, V.oy + H * V.s);
      for (let x = 0; x < gw; x++) ctx.lineTo(V.ox + (x + 0.5) * c, V.oy + floor[x] * c);
      ctx.lineTo(V.ox + W * V.s, V.oy + H * V.s); ctx.closePath(); ctx.fill();
      let mx = 1; for (const v of sed) mx = Math.max(mx, v);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      for (let x = 0; x < sed.length; x++) {
        const a = Math.min(1, Math.sqrt(sed[x] / mx));
        if (a < 0.03) continue;
        const X = V.ox + (x + 0.5) * c, Y = V.oy + floor[x] * c, h = (3 + 10 * a) * c;
        const g = ctx.createLinearGradient(0, Y - h * 0.3, 0, Y + h);
        g.addColorStop(0, 'rgba(231,162,59,0)'); g.addColorStop(0.3, `rgba(231,162,59,${0.55 * a})`); g.addColorStop(1, 'rgba(231,162,59,0)');
        ctx.fillStyle = g; ctx.fillRect(X - c * 0.6, Y - h * 0.3, c * 1.2, h * 1.3);
      }
      ctx.restore();
    }
    const sway = (x, y, slot) => Math.sin(t * 0.8 + slot * 0.7 + x * 0.02) * (gh - y) / gh * 6 * V.s;
    for (let i = 0; i < gw * gh; i++) {
      const ty = types[i];
      if (!ty || ty === 5) continue;
      const x = i % gw, y = (i / gw) | 0, sl = slots[i], p = pal.get(sl) || { h2: 0.3 };
      ctx.fillStyle = ty === 3 ? 'rgba(251,243,220,0.45)' : `hsla(${p.h2 * 360},30%,${ty === 2 ? 26 : 18}%,0.9)`;
      ctx.fillRect(V.ox + x * c + sway(x, y, sl), V.oy + y * c, c, c);
    }
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < gw * gh; i++) {
      if (types[i] !== 5) continue;
      const x = i % gw, y = (i / gw) | 0, X = V.ox + (x + 0.5) * c + Math.sin(t * 1.3 + i) * c * 0.3, Y = V.oy + (y + 0.5) * c;
      ctx.fillStyle = 'rgba(232,220,196,0.18)'; ctx.beginPath(); ctx.arc(X, Y, c * 0.9, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = 'rgba(232,220,196,0.8)'; ctx.fillRect(X - c * 0.2, Y - c * 0.2, c * 0.4, c * 0.4);
    }
    ctx.restore();
  }
  return { size: d => [(d.gw || 180) * CELL, (d.gh || 96) * CELL], ingest, draw, drawGlow, drawDark };
})();
