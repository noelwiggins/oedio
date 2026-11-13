/* COSMOGENESIS: deep blue space with a faint printed starfield. Gas is a fine dust, aqua when pristine and warming to
   orange as it is enriched; stars are jewel lamps (blue when massive, gold, red when small) with tiny planets circling;
   explosions ring outward; dead stars are dark beads. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  let d = null, W = 1200, H = 640;
  const GAS = ['#8fd3c8', '#a6d6bf', '#bcd8a8', '#d2d58f', '#e6cd78', '#f2b33d', '#f09a36', '#ee7d22', '#e5602a', '#e58bb0'];

  function ingest(f) { d = f; W = f.w; H = f.h; }
  function starColour(m) { return m >= 27 ? '#8fd0ff' : m >= 23 ? '#fbf3dc' : m >= 21 ? '#f2b33d' : '#e5602a'; }

  function draw(ctx, V, now, t) {
    ctx.fillStyle = '#16233d'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    ctx.fillStyle = 'rgba(251,243,220,0.12)';
    for (let i = 0; i < 220; i++) { const x = (i * 131.7) % W, y = (i * 71.3 + (i % 11) * 17) % H; ctx.fillRect(V.ox + x * V.s, V.oy + y * V.s, 1.4 * V.s, 1.4 * V.s); }
    if (!d) return;
    // gas
    const g = d.gas, r = Math.max(1.6, 2.4 * V.s);
    for (let i = 0; i < g.length; i += 3) { ctx.fillStyle = GAS[g[i + 2]]; ctx.globalAlpha = 0.75; ctx.fillRect(V.ox + g[i] * V.s - r / 2, V.oy + g[i + 1] * V.s - r / 2, r, r); }
    ctx.globalAlpha = 1;
    // remnants
    const R = d.remnants;
    for (let i = 0; i < R.length; i += 2) { ctx.fillStyle = '#0b1220'; ctx.strokeStyle = 'rgba(201,182,255,0.5)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(V.ox + R[i] * V.s, V.oy + R[i + 1] * V.s, 1.8 * V.s, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
    // explosions
    for (const [x, y, age] of d.flashes) {
      const p = age / 120, X = V.ox + x * V.s, Y = V.oy + y * V.s;
      ctx.strokeStyle = `rgba(242,179,61,${0.8 * (1 - p)})`; ctx.lineWidth = Math.max(1.5, 3 * V.s * (1 - p));
      ctx.beginPath(); ctx.arc(X, Y, (6 + 60 * p) * V.s, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = `rgba(229,96,42,${0.6 * (1 - p)})`; ctx.beginPath(); ctx.arc(X, Y, (3 + 38 * p) * V.s, 0, Math.PI * 2); ctx.stroke();
    }
    // stars and their planets
    for (const [id, x, y, m, pl, life, gen] of d.stars) {
      const mc = Math.min(45, Math.max(20, m)), X = V.ox + x * V.s, Y = V.oy + y * V.s, Rs = (2.4 + (mc - 20) * 0.16) * V.s * (life > 0.9 ? 1.3 : 1);
      for (let k = 0; k < pl; k++) {
        const orb = Rs + (4 + k * 3) * V.s, a = t * (0.9 - k * 0.12) + id * 1.7 + k * 2;
        ctx.strokeStyle = 'rgba(251,243,220,0.18)'; ctx.lineWidth = 0.8; ctx.beginPath(); ctx.arc(X, Y, orb, 0, Math.PI * 2); ctx.stroke();
        ctx.fillStyle = ['#a8c94a', '#3f97b5', '#d9c27a', '#e58bb0'][k % 4];
        ctx.beginPath(); ctx.arc(X + Math.cos(a) * orb, Y + Math.sin(a) * orb, 1.4 * V.s, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(X, Y, Rs + 1.1 * V.s, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = starColour(mc); ctx.beginPath(); ctx.arc(X, Y, Rs, 0, Math.PI * 2); ctx.fill();
    }
  }
  function drawGlow(ctx, V, now, t) {
    if (!d) return;
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (const [id, x, y, m, pl, life] of d.stars) {
      const mc = Math.min(45, Math.max(20, m)), X = V.ox + x * V.s, Y = V.oy + y * V.s, R = (7 + (mc - 20) * 0.45) * V.s * (0.9 + 0.1 * Math.sin(t * 3 + id));
      const g = ctx.createRadialGradient(X, Y, 0, X, Y, R);
      const c = mc >= 27 ? '143,208,255' : mc >= 21 ? '255,214,120' : '255,140,80';
      g.addColorStop(0, `rgba(${c},0.38)`); g.addColorStop(1, `rgba(${c},0)`);
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(X, Y, R, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  return { size: f => [f.w || 1200, f.h || 640], ingest, draw, drawGlow };
})();
