/* PSYCHOGENESIS: a polka-dot meadow strewn with eight kinds of flat symbol (four shapes in two colours). Creatures are
   round decals whose faces show their mood: afraid (wide eyes, small mouth, cool blue), hungry (open mouth, orange),
   content (smile, gold), curious (one raised brow and a feeler, green). */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  const MOOD = ['#8fd0ff', '#ee7d22', '#f2b33d', '#a8c94a'];
  const KCOL = ['#e5602a', '#3f97b5'];
  let d = null, W = 1200, H = 640;
  const cr = new Map();
  const LAG = 800;

  function ingest(f, now) {
    d = f; W = f.w; H = f.h;
    const seen = new Set();
    for (const c of f.creatures) {
      const [id, x, y, h, mood, hue, lr] = c;
      seen.add(id);
      let o = cr.get(id);
      if (!o) { o = { x0: x, y0: y, x1: x, y1: y, h0: h, h1: h, t0: now, t1: now, born: now }; cr.set(id, o); }
      else { const p = pos(o, now); Object.assign(o, { x0: p.x, y0: p.y, h0: p.h, x1: x, y1: y, h1: h, t0: now, t1: now + LAG }); }
      Object.assign(o, { mood, hue, lr });
    }
    for (const [id] of cr) if (!seen.has(id)) cr.delete(id);
  }
  function pos(o, now) {
    const f = o.t1 > o.t0 ? Math.min(1, Math.max(0, (now - o.t0) / (o.t1 - o.t0))) : 1;
    let dh = o.h1 - o.h0; dh = ((dh + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
    return { x: o.x0 + (o.x1 - o.x0) * f, y: o.y0 + (o.y1 - o.y0) * f, h: o.h0 + dh * f };
  }
  function shape(ctx, k, X, Y, s) {
    ctx.fillStyle = KCOL[k % 2]; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, s * 0.18);
    ctx.beginPath();
    const kind = k >> 1;
    if (kind === 0) ctx.arc(X, Y, s, 0, Math.PI * 2);
    else if (kind === 1) ctx.rect(X - s * 0.9, Y - s * 0.9, s * 1.8, s * 1.8);
    else if (kind === 2) { ctx.moveTo(X, Y - s * 1.1); ctx.lineTo(X + s, Y + s * 0.8); ctx.lineTo(X - s, Y + s * 0.8); ctx.closePath(); }
    else for (let i = 0; i < 10; i++) { const r = i % 2 ? s * 0.5 : s * 1.15, a = i * Math.PI / 5 - Math.PI / 2; i ? ctx.lineTo(X + Math.cos(a) * r, Y + Math.sin(a) * r) : ctx.moveTo(X + Math.cos(a) * r, Y + Math.sin(a) * r); }
    ctx.fill(); ctx.stroke();
  }

  function draw(ctx, V, now, t) {
    ctx.fillStyle = '#a8c94a'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    ctx.fillStyle = 'rgba(251,243,220,0.35)';
    for (let y = 20; y < H; y += 40) for (let x = (y / 40 % 2) * 20 + 10; x < W; x += 40) { ctx.beginPath(); ctx.arc(V.ox + x * V.s, V.oy + y * V.s, 4 * V.s, 0, Math.PI * 2); ctx.fill(); }
    if (!d) return;
    const T = d.things, s = 5 * V.s;
    for (let i = 0; i < T.length; i += 3) shape(ctx, T[i + 2], V.ox + T[i] * V.s, V.oy + T[i + 1] * V.s, s);
    for (const o of cr.values()) {
      const p = pos(o, now), X = V.ox + p.x * V.s, Y = V.oy + p.y * V.s, R = 9 * V.s, m = o.mood;
      const bob = Math.sin(t * 6 + o.x1) * 0.8 * V.s;
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(X, Y + bob, R + 1.4 * V.s, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `hsl(${o.hue * 360},50%,72%)`; ctx.beginPath(); ctx.arc(X, Y + bob, R, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = MOOD[m]; ctx.beginPath(); ctx.arc(X, Y + bob, R * 0.72, 0, Math.PI * 2); ctx.fill();
      // the face looks where it is going
      const fx = Math.cos(p.h) * R * 0.18, fy = Math.sin(p.h) * R * 0.18, cy = Y + bob;
      const eyeR = m === 0 ? R * 0.2 : R * 0.13;
      ctx.fillStyle = '#fbf3dc';
      for (const sx of [-1, 1]) { ctx.beginPath(); ctx.arc(X + fx + sx * R * 0.3, cy + fy - R * 0.15, eyeR, 0, Math.PI * 2); ctx.fill(); }
      ctx.fillStyle = INK;
      for (const sx of [-1, 1]) { ctx.beginPath(); ctx.arc(X + fx + sx * R * 0.3 + fx * 0.3, cy + fy - R * 0.15 + fy * 0.3, eyeR * 0.5, 0, Math.PI * 2); ctx.fill(); }
      ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, R * 0.11); ctx.beginPath();
      if (m === 0) ctx.arc(X + fx, cy + fy + R * 0.32, R * 0.09, 0, Math.PI * 2);
      else if (m === 1) { ctx.ellipse(X + fx, cy + fy + R * 0.3, R * 0.2, R * 0.14, 0, 0, Math.PI * 2); }
      else if (m === 2) ctx.arc(X + fx, cy + fy + R * 0.12, R * 0.3, 0.2 * Math.PI, 0.8 * Math.PI);
      else { ctx.moveTo(X + fx - R * 0.2, cy + fy + R * 0.32); ctx.lineTo(X + fx + R * 0.2, cy + fy + R * 0.28); }
      ctx.stroke();
      if (m === 3) { ctx.beginPath(); ctx.moveTo(X + fx + R * 0.1, Y + bob - R); ctx.quadraticCurveTo(X + fx + R * 0.6, Y + bob - R * 1.9, X + fx + R * 0.9, Y + bob - R * 1.6); ctx.stroke(); ctx.fillStyle = '#a8c94a'; ctx.beginPath(); ctx.arc(X + fx + R * 0.9, Y + bob - R * 1.6, R * 0.18, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
    }
  }
  return { size: f => [f.w || 1200, f.h || 640], ingest, draw };
})();
