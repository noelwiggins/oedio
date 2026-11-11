/* AUTOPOIESIS: a flat cream dish. Substrate is a fine speckle; links are orange beads on chrome bonds; a closed ring
   around a catalyst is a cell, filled with its catalyst's colour; catalysts are jewel lamps that glow when sheltered. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  let W = 1200, H = 800, d = null;
  const kpos = new Map();
  const LAG = 900;

  function ingest(f, now) {
    W = f.w; H = f.h; d = f;
    for (const [id, x, y, hue, inside] of f.catalysts) {
      let o = kpos.get(id);
      if (!o) { o = { x0: x, y0: y, x1: x, y1: y, t0: now, t1: now }; kpos.set(id, o); }
      else { const p = kp(o, now); Object.assign(o, { x0: p.x, y0: p.y, x1: x, y1: y, t0: now, t1: now + LAG }); }
      o.hue = hue; o.inside = inside; o.seen = now;
    }
    for (const [id, o] of kpos) if (now - o.seen > 5000) kpos.delete(id);
  }
  function kp(o, now) {
    const f = o.t1 > o.t0 ? Math.min(1, Math.max(0, (now - o.t0) / (o.t1 - o.t0))) : 1;
    return { x: o.x0 + (o.x1 - o.x0) * f, y: o.y0 + (o.y1 - o.y0) * f };
  }

  function draw(ctx, V, now, t) {
    // the dish: flat cream with a faint printed grid
    ctx.fillStyle = '#f6e7bf'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    ctx.strokeStyle = 'rgba(185,86,12,0.12)'; ctx.lineWidth = 1;
    for (let x = 0; x <= W; x += 40) { ctx.beginPath(); ctx.moveTo(V.ox + x * V.s, V.oy); ctx.lineTo(V.ox + x * V.s, V.oy + H * V.s); ctx.stroke(); }
    for (let y = 0; y <= H; y += 40) { ctx.beginPath(); ctx.moveTo(V.ox, V.oy + y * V.s); ctx.lineTo(V.ox + W * V.s, V.oy + y * V.s); ctx.stroke(); }
    if (!d) return;
    // substrate
    ctx.fillStyle = 'rgba(138,90,43,0.55)';
    const sr = Math.max(1, 1.3 * V.s), S = d.substrate;
    for (let i = 0; i < S.length; i += 2) ctx.fillRect(V.ox + S[i] * V.s - sr / 2, V.oy + S[i + 1] * V.s - sr / 2, sr, sr);
    const Lk = d.links, X = i => V.ox + Lk[2 * i] * V.s, Y = i => V.oy + Lk[2 * i + 1] * V.s;
    // cells: filled rings
    for (const [ring, hue] of d.rings) {
      if (ring.length < 3) continue;
      ctx.beginPath(); ring.forEach((li, k) => k ? ctx.lineTo(X(li), Y(li)) : ctx.moveTo(X(li), Y(li))); ctx.closePath();
      ctx.fillStyle = hue >= 0 ? `hsla(${hue * 360},70%,62%,0.55)` : 'rgba(143,211,200,0.35)'; ctx.fill();
    }
    // bonds
    const B = d.bonds;
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(2, 3.2 * V.s);
    ctx.beginPath(); for (let i = 0; i < B.length; i += 2) { ctx.moveTo(X(B[i]), Y(B[i])); ctx.lineTo(X(B[i + 1]), Y(B[i + 1])); } ctx.stroke();
    ctx.strokeStyle = '#c9d0d5'; ctx.lineWidth = Math.max(1, 1.6 * V.s);
    ctx.beginPath(); for (let i = 0; i < B.length; i += 2) { ctx.moveTo(X(B[i]), Y(B[i])); ctx.lineTo(X(B[i + 1]), Y(B[i + 1])); } ctx.stroke();
    // links
    const r = Math.max(2, 3.2 * V.s);
    for (let i = 0; i < Lk.length / 2; i++) {
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(X(i), Y(i), r + 1, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#ee7d22'; ctx.beginPath(); ctx.arc(X(i), Y(i), r, 0, Math.PI * 2); ctx.fill();
    }
    // catalysts: jewel lamps in chrome
    for (const o of kpos.values()) {
      const p = kp(o, now), cx = V.ox + p.x * V.s, cy = V.oy + p.y * V.s, R = Math.max(5, 7.5 * V.s);
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(cx, cy, R + 2.4 * V.s, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#d8dde2'; ctx.beginPath(); ctx.arc(cx, cy, R + 1.2 * V.s, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `hsl(${o.hue * 360},85%,${o.inside ? 55 + 8 * Math.sin(t * 2) : 40}%)`; ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,0.6)'; ctx.beginPath(); ctx.arc(cx - R * 0.3, cy - R * 0.35, R * 0.3, 0, Math.PI * 2); ctx.fill();
      o._s = [cx, cy, R];
    }
  }
  function drawGlow(ctx, V, now, t) {
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (const o of kpos.values()) {
      if (!o.inside || !o._s) continue;
      const [cx, cy, R] = o._s, Rg = R * 5 * (0.85 + 0.15 * Math.sin(t * 2));
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, Rg);
      g.addColorStop(0, `hsla(${o.hue * 360},95%,65%,0.35)`); g.addColorStop(1, `hsla(${o.hue * 360},95%,50%,0)`);
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, Rg, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  return { size: f => [f.w || 1200, f.h || 800], ingest, draw, drawGlow };
})();
