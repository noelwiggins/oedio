/* PROTOGENESIS: a warm pond seen from the side. Building blocks are coloured pachinko balls; chains are strings of
   them in sequence order; a chain carrying the active site wears a gold ring. Vents smoke on the floor. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  const COL = { A: '#e5602a', B: '#f2b33d', C: '#3f97b5', D: '#a8c94a' };
  const COLI = ['#e5602a', '#f2b33d', '#3f97b5', '#a8c94a'];
  let W = 1200, H = 800, mon = [], monPrev = [], monAt = 0, vents = [];
  const chains = new Map();
  const LAG = 900;
  const sprites = {};

  function ball(color, r) {
    const key = color + r;
    if (sprites[key]) return sprites[key];
    const c = document.createElement('canvas'), R = Math.ceil(r + 2);
    c.width = c.height = R * 2;
    const g = c.getContext('2d');
    g.fillStyle = INK; g.beginPath(); g.arc(R, R, r + 1, 0, Math.PI * 2); g.fill();
    g.fillStyle = color; g.beginPath(); g.arc(R, R, r, 0, Math.PI * 2); g.fill();
    g.fillStyle = 'rgba(255,255,255,0.55)'; g.beginPath(); g.arc(R - r * 0.35, R - r * 0.35, r * 0.32, 0, Math.PI * 2); g.fill();
    sprites[key] = c;
    return c;
  }

  function ingest(d, now) {
    W = d.w; H = d.h; vents = d.vents || [];
    monPrev = mon; mon = d.monomers; monAt = now;
    const seen = new Set();
    for (const c of d.chains) {
      const [id, x, y, a, seq, fam, act, fold, gen] = c;
      seen.add(id);
      let o = chains.get(id);
      if (!o) { o = { id, x0: x, y0: y, a0: a, x1: x, y1: y, a1: a, t0: now, t1: now, born: now }; chains.set(id, o); }
      else { const p = cpos(o, now); Object.assign(o, { x0: p.x, y0: p.y, a0: p.a, x1: x, y1: y, a1: a, t0: now, t1: now + LAG, dead: 0 }); }
      Object.assign(o, { seq, fam, act, fold, gen });
    }
    for (const [id, o] of chains) if (!seen.has(id) && !o.dead) o.dead = now;
  }
  function cpos(o, now) {
    const f = o.t1 > o.t0 ? Math.min(1, Math.max(0, (now - o.t0) / (o.t1 - o.t0))) : 1;
    return { x: o.x0 + (o.x1 - o.x0) * f, y: o.y0 + (o.y1 - o.y0) * f, a: o.a0 + (o.a1 - o.a0) * f };
  }

  function background(ctx, V, t) {
    const bands = [[0, '#bfe6df'], [0.18, '#8fd3c8'], [0.42, '#3f97b5'], [0.7, '#2b5f86'], [0.9, '#1f4566']];
    for (let i = 0; i < bands.length; i++) {
      const y0 = V.oy + bands[i][0] * H * V.s, y1 = V.oy + (i + 1 < bands.length ? bands[i + 1][0] : 1) * H * V.s;
      ctx.fillStyle = bands[i][1];
      ctx.beginPath(); ctx.moveTo(V.ox, y1);
      for (let x = 0; x <= W; x += 20) ctx.lineTo(V.ox + x * V.s, y0 + Math.sin(x / 70 + t * 0.4 + i) * 4 * V.s * (i ? 1 : 0));
      ctx.lineTo(V.ox + W * V.s, y1); ctx.closePath(); ctx.fill();
      if (i) { ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 1.2 * V.s); ctx.stroke(); }
    }
    // vents on the floor, breathing
    for (const vx of vents) {
      const X = V.ox + vx * V.s, Y = V.oy + H * V.s, w = 46 * V.s, h = 70 * V.s;
      ctx.fillStyle = '#e5602a'; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 1.6 * V.s);
      ctx.beginPath(); ctx.moveTo(X - w, Y); ctx.lineTo(X - w * 0.3, Y - h); ctx.lineTo(X + w * 0.3, Y - h); ctx.lineTo(X + w, Y); ctx.closePath(); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#f2b33d'; ctx.beginPath(); ctx.ellipse(X, Y - h, w * 0.3, 6 * V.s, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      for (let k = 0; k < 5; k++) {
        const ph = (t * 0.35 + k / 5) % 1, ry = Y - h - ph * 260 * V.s, rr = (6 + ph * 26) * V.s;
        ctx.strokeStyle = `rgba(251,243,220,${0.55 * (1 - ph)})`; ctx.lineWidth = Math.max(1, 2 * V.s);
        ctx.beginPath(); ctx.arc(X + Math.sin(t + k) * 10 * V.s, ry, rr, 0, Math.PI * 2); ctx.stroke();
      }
    }
  }

  function draw(ctx, V, now, t, light) {
    background(ctx, V, t);
    // building blocks
    const f = Math.min(1, (now - monAt) / LAG), r = Math.max(2.2, 3.2 * V.s);
    const same = monPrev.length === mon.length;
    for (let i = 0; i < mon.length; i += 3) {
      let x = mon[i], y = mon[i + 1];
      if (same) { const px = monPrev[i], py = monPrev[i + 1]; if (Math.abs(px - x) < 25 && Math.abs(py - y) < 25) { x = px + (x - px) * f; y = py + (y - py) * f; } }
      const spr = ball(COLI[mon[i + 2]], r);
      ctx.drawImage(spr, V.ox + x * V.s - spr.width / 2, V.oy + y * V.s - spr.height / 2);
    }
    // chains: strings of balls; folded chains bend back on themselves as a hairpin
    const R = Math.max(2.8, 4.2 * V.s), gap = R * 1.85;
    for (const o of [...chains.values()]) {
      let alpha = Math.min(1, (now - o.born) / 700);
      if (o.dead) { alpha = Math.max(0, 1 - (now - o.dead) / 900); if (alpha <= 0) { chains.delete(o.id); continue; } }
      const p = cpos(o, now), X = V.ox + p.x * V.s, Y = V.oy + p.y * V.s, n = o.seq.length;
      const pts = [];
      const folded = o.fold > 0.45 && n >= 6, half = folded ? Math.ceil(n / 2) : n;
      for (let i = 0; i < n; i++) {
        let k = i, off = 0;
        if (folded && i >= half) { k = n - 1 - i; off = 1; }
        const wob = Math.sin(t * 1.3 + i * 0.7 + o.id) * 0.18;
        const a = p.a + wob;
        const along = (k - half / 2) * gap;
        pts.push([X + Math.cos(a) * along - Math.sin(a) * off * gap * 1.05, Y + Math.sin(a) * along + Math.cos(a) * off * gap * 1.05]);
      }
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, R * 0.5);
      ctx.beginPath(); pts.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.stroke();
      for (let i = 0; i < n; i++) { const spr = ball(COL[o.seq[i]], R); ctx.drawImage(spr, pts[i][0] - spr.width / 2, pts[i][1] - spr.height / 2); }
      if (o.act > 0.5) {
        let cx = 0, cy = 0; pts.forEach(([x, y]) => { cx += x; cy += y; }); cx /= n; cy /= n;
        const rr = gap * (folded ? half : n) * 0.55 + R * 2;
        ctx.strokeStyle = '#d8b447'; ctx.lineWidth = Math.max(1.5, 2.4 * V.s);
        ctx.beginPath(); ctx.arc(cx, cy, rr, 0, Math.PI * 2); ctx.stroke();
        ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.8, 0.8 * V.s);
        ctx.beginPath(); ctx.arc(cx, cy, rr + 1.6 * V.s, 0, Math.PI * 2); ctx.stroke();
        o._glow = [cx, cy, rr, o.act];
      } else o._glow = null;
      ctx.globalAlpha = 1;
    }
  }
  function drawGlow(ctx, V, now, t, light) {
    if (light > 0.85) return;
    const dark = Math.min(1, (0.85 - light) / 0.6);
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (const o of chains.values()) {
      if (!o._glow) continue;
      const [cx, cy, rr, act] = o._glow, Rg = rr * 2.2 * (0.85 + 0.15 * Math.sin(t * 2 + o.id));
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, Rg);
      g.addColorStop(0, `rgba(255,214,110,${0.5 * act * dark})`); g.addColorStop(1, 'rgba(255,214,110,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, Rg, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  return { size: d => [d.w || 1200, d.h || 800], ingest, draw, drawGlow };
})();
