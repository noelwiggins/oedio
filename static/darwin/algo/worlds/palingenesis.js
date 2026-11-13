/* PALINGENESIS: a forest seen from above as a flat printed map. Trees are round canopies in their kind's green, ringed
   darker the thicker their bark; fire is a flickering orange front; ash is grey, freckled where seed waits in it. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  let gw = 180, gh = 96, cells = null, pal = [];
  const CELL = 6.6667;
  let sprites = {}, spriteC = 0;
  function sprite(v, c) {
    if (spriteC !== c) { sprites = {}; spriteC = c; }
    if (sprites[v]) return sprites[v];
    const p = pal[v - 4] || [0.3, 0.2, 0.2], R = Math.ceil(c * 0.75) + 1, cv = document.createElement('canvas');
    cv.width = cv.height = R * 2;
    const g = cv.getContext('2d');
    g.fillStyle = INK; g.beginPath(); g.arc(R, R, c * 0.68, 0, Math.PI * 2); g.fill();
    g.fillStyle = `hsl(${p[0] * 360},${45 + 20 * (1 - p[1])}%,${30 + 14 * (1 - p[1])}%)`; g.beginPath(); g.arc(R, R, c * 0.58, 0, Math.PI * 2); g.fill();
    g.fillStyle = `hsl(${p[0] * 360},55%,${50 - 8 * p[1]}%)`; g.beginPath(); g.arc(R - c * 0.1, R - c * 0.12, c * (0.42 - 0.2 * p[1]), 0, Math.PI * 2); g.fill();
    if (p[2] > 0.4) { g.fillStyle = '#b9560c'; g.beginPath(); g.arc(R + c * 0.2, R + c * 0.18, c * 0.12, 0, Math.PI * 2); g.fill(); }
    sprites[v] = cv;
    return cv;
  }

  function ingest(f) {
    gw = f.gw; gh = f.gh; pal = f.palette; sprites = {};
    const bin = atob(f.cells), n = bin.length, a = new Uint8Array(n);
    for (let i = 0; i < n; i++) a[i] = bin.charCodeAt(i);
    cells = a;
  }

  function draw(ctx, V, now, t) {
    const W = gw * CELL, H = gh * CELL, c = CELL * V.s;
    ctx.fillStyle = '#e8d9a8'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    if (!cells) return;
    const n = gw * gh;
    // ground first: ash and seed
    for (let i = 0; i < n; i++) {
      const v = cells[i];
      if (v !== 1 && v !== 3) continue;
      const x = i % gw, y = (i / gw) | 0;
      ctx.fillStyle = '#b9bdb6'; ctx.fillRect(V.ox + x * c, V.oy + y * c, c + 0.5, c + 0.5);
      if (v === 3) { ctx.fillStyle = '#6b4a2b'; ctx.fillRect(V.ox + (x + 0.4) * c, V.oy + (y + 0.4) * c, c * 0.25, c * 0.25); }
    }
    // canopies, stamped from one drawing per kind of tree
    for (let i = 0; i < n; i++) {
      const v = cells[i];
      if (v < 4) continue;
      const spr = sprite(v, c), x = i % gw, y = (i / gw) | 0;
      ctx.drawImage(spr, V.ox + (x + 0.5) * c - spr.width / 2, V.oy + (y + 0.5) * c - spr.height / 2);
    }
    // fire
    for (let i = 0; i < n; i++) {
      if (cells[i] !== 2) continue;
      const x = i % gw, y = (i / gw) | 0, X = V.ox + (x + 0.5) * c, Y = V.oy + (y + 0.5) * c, f = 0.8 + 0.3 * Math.sin(t * 11 + i);
      ctx.fillStyle = '#e5602a'; ctx.beginPath(); ctx.arc(X, Y, c * 0.75 * f, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#f2b33d'; ctx.beginPath(); ctx.arc(X, Y - c * 0.1, c * 0.4 * f, 0, Math.PI * 2); ctx.fill();
    }
  }
  function drawGlow(ctx, V, now, t) {
    if (!cells) return;
    const c = CELL * V.s, n = gw * gh;
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    ctx.fillStyle = 'rgba(255,140,50,0.06)';
    for (let i = 0; i < n; i += 1) {
      if (cells[i] !== 2 || i % 3) continue;
      const x = i % gw, y = (i / gw) | 0;
      ctx.beginPath(); ctx.arc(V.ox + (x + 0.5) * c, V.oy + (y + 0.5) * c, c * 2.2, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  return { size: f => [(f.gw || 180) * CELL, (f.gh || 96) * CELL], ingest, draw, drawGlow };
})();
