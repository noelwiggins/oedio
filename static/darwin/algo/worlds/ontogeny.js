/* ONTOGENY: one organism large in the middle of an aqua dish, each cell a flat round tile in its tissue's colour, and
   five siblings developing in small chrome pockets along the bottom. A grown larva sways as it swims. A row of seven
   lamps above the main embryo marks its stage, from zygote to adult. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  const TISSUE = ['#fbf3dc', '#f6e7bf', '#e5602a', '#f2b33d', '#7d5ba6', '#3f97b5'];
  let d = null, W = 1200, H = 640;

  function ingest(f) { d = f; W = f.w; H = f.h; }

  function embryo(ctx, e, cx, cy, scale, t, swim) {
    const P = e.cells, n = P.length / 2;
    if (!n) return;
    let mx = 0, my = 0;
    for (let i = 0; i < n; i++) { mx += P[2 * i]; my += P[2 * i + 1]; }
    mx /= n; my /= n;
    const ax = Math.cos(e.axis), ay = Math.sin(e.axis), r = 5 * scale;
    const pts = [];
    for (let i = 0; i < n; i++) {
      let x = P[2 * i] - mx, y = P[2 * i + 1] - my;
      if (swim) { const along = x * ax + y * ay, wob = Math.sin(t * 3 - along * 0.06) * Math.min(1, Math.abs(along) / 60) * 6; x += -ay * wob; y += ax * wob; }
      pts.push([cx + x * scale, cy + y * scale, e.types[i]]);
    }
    ctx.fillStyle = INK;
    for (const [x, y] of pts) { ctx.beginPath(); ctx.arc(x, y, r * 1.12 + 1, 0, Math.PI * 2); ctx.fill(); }
    for (const [x, y, k] of pts) {
      ctx.fillStyle = TISSUE[k]; ctx.beginPath(); ctx.arc(x, y, r * 0.98, 0, Math.PI * 2); ctx.fill();
      if (k === 4) { ctx.fillStyle = '#c9b6ff'; ctx.beginPath(); ctx.arc(x - r * 0.2, y - r * 0.2, r * 0.35, 0, Math.PI * 2); ctx.fill(); }
    }
    if (n === 1) { ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, scale); ctx.beginPath(); ctx.arc(cx, cy, r * 2.2, 0, Math.PI * 2); ctx.stroke(); }
  }

  function draw(ctx, V, now, t) {
    ctx.fillStyle = '#8fd3c8'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    // concentric rings, like a dish under a lens
    ctx.strokeStyle = 'rgba(42,29,20,0.12)'; ctx.lineWidth = Math.max(1, 1.2 * V.s);
    for (let r = 60; r < 700; r += 55) { ctx.beginPath(); ctx.arc(V.ox + 600 * V.s, V.oy + 260 * V.s, r * V.s, 0, Math.PI * 2); ctx.stroke(); }
    if (!d) return;
    const main = d.embryos[0];
    // stage lamps
    for (let k = 0; k < 7; k++) {
      const X = V.ox + (600 + (k - 3) * 34) * V.s, Y = V.oy + 40 * V.s, on = k <= main.stage;
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(X, Y, 9 * V.s, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = on ? (k === main.stage ? '#f2b33d' : '#e5602a') : '#5b6770'; ctx.beginPath(); ctx.arc(X, Y, 7 * V.s, 0, Math.PI * 2); ctx.fill();
    }
    const nMain = main.cells.length / 2, big = Math.min(2.4, 2.4 * Math.sqrt(220 / Math.max(nMain, 220)));
    embryo(ctx, main, V.ox + 600 * V.s, V.oy + 265 * V.s, V.s * big, t, main.stage >= 5);
    // the five siblings in pockets
    for (let i = 1; i < d.embryos.length; i++) {
      const X = V.ox + (600 + (i - 3) * 150) * V.s, Y = V.oy + 545 * V.s, R = 62 * V.s;
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(X, Y, R + 3 * V.s, 0, Math.PI * 2); ctx.fill();
      const g = ctx.createRadialGradient(X - R * 0.3, Y - R * 0.3, R * 0.1, X, Y, R * 1.05);
      g.addColorStop(0, '#ffffff'); g.addColorStop(0.5, '#c3cad0'); g.addColorStop(1, '#6c757d');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(X, Y, R, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#cfeee6'; ctx.beginPath(); ctx.arc(X, Y, R * 0.86, 0, Math.PI * 2); ctx.fill();
      const e = d.embryos[i], n = e.cells.length / 2;
      ctx.save(); ctx.beginPath(); ctx.arc(X, Y, R * 0.86, 0, Math.PI * 2); ctx.clip();
      embryo(ctx, e, X, Y, V.s * Math.min(0.42, 0.42 * Math.sqrt(160 / Math.max(n, 160))), t, e.stage >= 5);
      ctx.restore();
    }
  }
  return { size: f => [f.w || 1200, f.h || 640], ingest, draw };
})();
