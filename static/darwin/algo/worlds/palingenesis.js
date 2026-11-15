/* PALINGENESIS: a forest seen from above as a flat printed map. Trees are round canopies in their kind's green, ringed
   darker the thicker their bark; fire is a flickering orange front; ash is grey, freckled where seed waits in it. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  let gw = 180, gh = 96, cells = null, pal = [], under = null;
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
    if (f.under) { const u = atob(f.under), b = new Uint8Array(u.length); for (let i = 0; i < u.length; i++) b[i] = u.charCodeAt(i); under = b; }
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
  // the dark side, Palinphthora: the forest floor seen in the dark. Humus glows amber where rot has made it; fallen
  // wood lies in bone; beetles move through a stand of one kind in red; the living are faint rings, fire is embers.
  function drawDark(ctx, V, now, t) {
    const W = gw * CELL, H = gh * CELL, c = CELL * V.s, n = gw * gh;
    ctx.fillStyle = '#120b10'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    if (!cells) return;
    if (under) {
      const hw = gw / 2, hh = gh / 2, c2 = c * 2;
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      for (let j = 0; j < hw * hh; j++) {
        const hum = under[j * 3 + 1];
        if (hum < 6) continue;
        ctx.fillStyle = `rgba(231,162,59,${Math.min(0.5, hum / 400)})`;
        ctx.fillRect(V.ox + (j % hw) * c2, V.oy + ((j / hw) | 0) * c2, c2 + 0.5, c2 + 0.5);
      }
      ctx.restore();
      ctx.lineCap = 'round';
      for (let j = 0; j < hw * hh; j++) {
        const dw = under[j * 3], bt = under[j * 3 + 2], X = V.ox + ((j % hw) + 0.5) * c2, Y = V.oy + (((j / hw) | 0) + 0.5) * c2;
        if (dw > 20) {                                    // a fallen log, lying its own way
          const a = (j * 2.399) % Math.PI, L = c * (0.8 + Math.min(1.4, dw / 120));
          ctx.strokeStyle = `rgba(232,220,196,${Math.min(0.85, 0.25 + dw / 300)})`; ctx.lineWidth = Math.max(1, c * 0.35);
          ctx.beginPath(); ctx.moveTo(X - Math.cos(a) * L, Y - Math.sin(a) * L); ctx.lineTo(X + Math.cos(a) * L, Y + Math.sin(a) * L); ctx.stroke();
        }
        if (bt > 30) {                                    // beetles at work
          ctx.fillStyle = `rgba(229,64,42,${0.4 + 0.4 * Math.sin(t * 5 + j) ** 2})`;
          for (let k = 0; k < 3; k++) { ctx.beginPath(); ctx.arc(X + Math.cos(j + k * 2.1 + t) * c * 0.6, Y + Math.sin(j * 1.3 + k * 2.1 + t) * c * 0.6, Math.max(0.8, c * 0.16), 0, Math.PI * 2); ctx.fill(); }
        }
      }
    }
    for (let i = 0; i < n; i++) {
      const v = cells[i], x = i % gw, y = (i / gw) | 0, X = V.ox + (x + 0.5) * c, Y = V.oy + (y + 0.5) * c;
      if (v >= 4 && (i % 2 === 0)) { ctx.strokeStyle = 'rgba(140,190,120,0.22)'; ctx.lineWidth = 0.8; ctx.beginPath(); ctx.arc(X, Y, c * 0.55, 0, Math.PI * 2); ctx.stroke(); }
      else if (v === 2) { ctx.fillStyle = `rgba(229,96,42,${0.6 + 0.4 * Math.sin(t * 9 + i)})`; ctx.fillRect(X - c * 0.3, Y - c * 0.3, c * 0.6, c * 0.6); }
      else if (v === 3) { ctx.fillStyle = 'rgba(180,140,255,0.55)'; ctx.fillRect(X - c * 0.12, Y - c * 0.12, c * 0.24, c * 0.24); }   // seed waiting
    }
  }
  return { size: f => [(f.gw || 180) * CELL, (f.gh || 96) * CELL], ingest, draw, drawGlow, drawDark };
})();
