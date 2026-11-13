/* NOOGENESIS: a night field. Blooms travel round dotted orbits and blink; dark blooms show only as a faint outline.
   Foragers are moth-like decals with a row of lit dots on their backs, one per neuron kept; a signalling forager glows. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  let d = null, W = 1200, H = 680;
  const ag = new Map();
  const LAG = 800;

  function ingest(f, now) {
    d = f; W = f.w; H = f.h;
    const seen = new Set();
    for (const [id, x, y, h, nn, glow, hue] of f.foragers) {
      seen.add(id);
      let o = ag.get(id);
      if (!o) { o = { x0: x, y0: y, h0: h, x1: x, y1: y, h1: h, t0: now, t1: now, born: now }; ag.set(id, o); }
      else { const p = pos(o, now); Object.assign(o, { x0: p.x, y0: p.y, h0: p.h, x1: x, y1: y, h1: h, t0: now, t1: now + LAG }); }
      Object.assign(o, { nn, glow, hue, seen: now });
    }
    for (const [id, o] of ag) if (!seen.has(id)) ag.delete(id);
  }
  function pos(o, now) {
    const f = o.t1 > o.t0 ? Math.min(1, Math.max(0, (now - o.t0) / (o.t1 - o.t0))) : 1;
    let dh = o.h1 - o.h0; dh = ((dh + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
    return { x: o.x0 + (o.x1 - o.x0) * f, y: o.y0 + (o.y1 - o.y0) * f, h: o.h0 + dh * f };
  }

  function draw(ctx, V, now, t) {
    ctx.fillStyle = '#1f3552'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    // a halftone of stars
    ctx.fillStyle = 'rgba(251,243,220,0.18)';
    for (let i = 0; i < 160; i++) { const x = (i * 97.3) % W, y = (i * 53.7 + (i % 7) * 31) % H; ctx.fillRect(V.ox + x * V.s, V.oy + y * V.s, 1.6 * V.s, 1.6 * V.s); }
    if (!d) return;
    // orbits and blooms
    for (const [bx, by, lit, food, cx, cy, r] of d.blooms) {
      ctx.setLineDash([3 * V.s, 7 * V.s]); ctx.strokeStyle = 'rgba(216,180,71,0.45)'; ctx.lineWidth = Math.max(1, 1.4 * V.s);
      ctx.beginPath(); ctx.arc(V.ox + cx * V.s, V.oy + cy * V.s, r * V.s, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
      const X = V.ox + bx * V.s, Y = V.oy + by * V.s, R = (8 + food * 0.35) * V.s;
      if (lit) {
        for (let k = 0; k < 8; k++) {
          ctx.fillStyle = k % 2 ? '#f2b33d' : '#e5602a'; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 1.2 * V.s);
          ctx.beginPath(); ctx.ellipse(X + Math.cos(k * Math.PI / 4 + t * 0.3) * R * 0.8, Y + Math.sin(k * Math.PI / 4 + t * 0.3) * R * 0.8, R * 0.55, R * 0.3, k * Math.PI / 4 + t * 0.3, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        }
        ctx.fillStyle = '#fbf3dc'; ctx.beginPath(); ctx.arc(X, Y, R * 0.45, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      } else {
        ctx.strokeStyle = 'rgba(251,243,220,0.22)'; ctx.lineWidth = Math.max(1, 1.2 * V.s); ctx.setLineDash([2 * V.s, 3 * V.s]);
        ctx.beginPath(); ctx.arc(X, Y, R, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
      }
    }
    // foragers
    for (const o of ag.values()) {
      const p = pos(o, now), X = V.ox + p.x * V.s, Y = V.oy + p.y * V.s, s = 7 * V.s, flap = Math.sin(t * 9 + o.x1) * 0.35;
      ctx.save(); ctx.translate(X, Y); ctx.rotate(p.h);
      ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 1.1 * V.s);
      ctx.fillStyle = `hsl(${o.hue * 360},55%,${o.glow ? 72 : 60}%)`;
      for (const side of [-1, 1]) {
        ctx.beginPath(); ctx.ellipse(-s * 0.2, side * s * (0.75 + flap * side * 0.2), s * 0.75, s * 0.55, side * (0.6 + flap), 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      }
      ctx.fillStyle = '#fbf3dc'; ctx.beginPath(); ctx.ellipse(0, 0, s * 1.05, s * 0.36, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      // the brain: one lit dot per neuron kept
      for (let k = 0; k < o.nn; k++) {
        ctx.fillStyle = '#c9b6ff'; ctx.beginPath(); ctx.arc(s * 0.75 - k * s * 0.22, 0, s * 0.11, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
      o._s = [X, Y, s];
    }
  }
  function drawGlow(ctx, V, now, t) {
    if (!d) return;
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (const [bx, by, lit, food] of d.blooms) {
      if (!lit) continue;
      const X = V.ox + bx * V.s, Y = V.oy + by * V.s, R = (30 + food) * V.s;
      const g = ctx.createRadialGradient(X, Y, 0, X, Y, R);
      g.addColorStop(0, 'rgba(255,200,90,0.35)'); g.addColorStop(1, 'rgba(255,200,90,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(X, Y, R, 0, Math.PI * 2); ctx.fill();
    }
    for (const o of ag.values()) {
      if (!o.glow || !o._s) continue;
      const [X, Y, s] = o._s, R = s * 4.5 * (0.8 + 0.2 * Math.sin(t * 6 + o.x1));
      const g = ctx.createRadialGradient(X, Y, 0, X, Y, R);
      g.addColorStop(0, `hsla(${o.hue * 360},90%,70%,0.55)`); g.addColorStop(1, `hsla(${o.hue * 360},90%,60%,0)`);
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(X, Y, R, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  return { size: f => [f.w || 1200, f.h || 680], ingest, draw, drawGlow };
})();
