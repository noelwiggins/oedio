/* ANAGENESIS: a savanna plain with the herd wandering on it, each animal drawn from its own traits (size, neck, legs,
   tail, armour plates, horn, ears, colour). Across a cream frieze at the top walks the parade of ancestors, one per
   epoch, oldest at the left. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  let d = null, W = 1200, H = 640;
  const herd = new Map();
  const LAG = 900;

  function ingest(f, now) {
    d = f; W = f.w; H = f.h;
    const seen = new Set();
    for (const a of f.animals) {
      const [id, x, y, h, ...g] = a;
      seen.add(id);
      let o = herd.get(id);
      if (!o) { o = { x0: x, y0: y, x1: x, y1: y, t0: now, t1: now }; herd.set(id, o); }
      else { const p = pos(o, now); Object.assign(o, { x0: p.x, y0: p.y, x1: x, y1: y, t0: now, t1: now + LAG }); }
      o.g = g; o.h = h;
    }
    for (const [id] of herd) if (!seen.has(id)) herd.delete(id);
  }
  function pos(o, now) {
    const f = o.t1 > o.t0 ? Math.min(1, Math.max(0, (now - o.t0) / (o.t1 - o.t0))) : 1;
    return { x: o.x0 + (o.x1 - o.x0) * f, y: o.y0 + (o.y1 - o.y0) * f };
  }

  // one animal, facing right (flip < 0 faces left), standing on (X, Y)
  function beast(ctx, X, Y, s, g, flip, step) {
    const [size, neck, legs, tail, armour, horn, ears, hue] = g;
    const bw = 9 * size * s, bh = 5 * size * s, lh = 7 * legs * s, base = Y - lh;
    ctx.save(); ctx.translate(X, 0); ctx.scale(flip, 1); ctx.translate(-X, 0);
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    const body = `hsl(${hue * 360},45%,55%)`, dark = `hsl(${hue * 360},40%,35%)`;
    // legs
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1.5, 2.6 * s * Math.sqrt(size));
    for (const [lx, ph] of [[-0.6, 0], [-0.35, 1], [0.45, 1], [0.7, 0]]) {
      const sw = Math.sin(step + ph * Math.PI) * lh * 0.25;
      ctx.beginPath(); ctx.moveTo(X + lx * bw, base); ctx.lineTo(X + lx * bw + sw, Y); ctx.stroke();
    }
    // tail
    if (tail > 0.05) { ctx.lineWidth = Math.max(1, 1.6 * s); ctx.beginPath(); ctx.moveTo(X - bw, base - bh * 0.5); ctx.quadraticCurveTo(X - bw - tail * 8 * s, base - bh * (0.6 + tail * 0.4), X - bw - tail * 12 * s, base - bh * 0.1); ctx.stroke(); }
    // neck and head
    const nx = X + bw * 0.75, ny = base - bh * 0.6, hx = nx + 3 * s + neck * 4 * s, hy = ny - 3 * s - neck * 12 * s;
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(2, (3.2 + 1.2 * size) * s);
    ctx.beginPath(); ctx.moveTo(nx, ny); ctx.lineTo(hx, hy); ctx.stroke();
    ctx.strokeStyle = body; ctx.lineWidth = Math.max(1, (2 + 1.2 * size) * s);
    ctx.beginPath(); ctx.moveTo(nx, ny); ctx.lineTo(hx, hy); ctx.stroke();
    // body
    ctx.fillStyle = body; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 1.3 * s);
    ctx.beginPath(); ctx.ellipse(X, base - bh * 0.5, bw, bh, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    // armour plates along the back
    if (armour > 0.12) {
      const n = Math.round(3 + armour * 5);
      ctx.fillStyle = dark;
      for (let k = 0; k < n; k++) {
        const a = Math.PI * (1.15 + 0.7 * k / (n - 1)), px = X + Math.cos(a) * bw * 0.92, py = base - bh * 0.5 + Math.sin(a) * bh * 0.92;
        ctx.beginPath(); ctx.moveTo(px - 2 * s, py + 1 * s); ctx.lineTo(px, py - (2 + 5 * armour) * s); ctx.lineTo(px + 2 * s, py + 1 * s); ctx.closePath(); ctx.fill(); ctx.stroke();
      }
    }
    // head, ears, horn, eye
    const hr = (2.4 + 0.8 * size) * s;
    if (ears > 0.1) { ctx.fillStyle = dark; ctx.beginPath(); ctx.ellipse(hx - hr * 0.5, hy - hr * 0.9, hr * 0.35, hr * (0.4 + ears), -0.4, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
    ctx.fillStyle = body; ctx.beginPath(); ctx.ellipse(hx + hr * 0.3, hy, hr * 1.2, hr * 0.8, 0.2, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    if (horn > 0.1) { ctx.fillStyle = '#fbf3dc'; ctx.beginPath(); ctx.moveTo(hx + hr * 0.6, hy - hr * 0.5); ctx.lineTo(hx + hr * (0.9 + horn), hy - hr * (1 + 2.2 * horn)); ctx.lineTo(hx + hr * 1.2, hy - hr * 0.3); ctx.closePath(); ctx.fill(); ctx.stroke(); }
    ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(hx + hr * 0.5, hy - hr * 0.15, Math.max(0.8, hr * 0.18), 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  function draw(ctx, V, now, t) {
    const top = d ? d.top : 150;
    ctx.fillStyle = '#d9c27a'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    // grass tufts and a flat sun-bleached band
    ctx.fillStyle = '#c9b05e';
    for (let y = top + 40; y < H; y += 46) for (let x = (y % 92 ? 0 : 30); x < W; x += 60) { ctx.beginPath(); ctx.moveTo(V.ox + x * V.s, V.oy + y * V.s); ctx.lineTo(V.ox + (x + 6) * V.s, V.oy + (y - 10) * V.s); ctx.lineTo(V.ox + (x + 12) * V.s, V.oy + y * V.s); ctx.fill(); }
    // the frieze of ancestors
    ctx.fillStyle = '#fbf3dc'; ctx.fillRect(V.ox, V.oy, W * V.s, top * V.s);
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 2 * V.s);
    ctx.beginPath(); ctx.moveTo(V.ox, V.oy + top * V.s); ctx.lineTo(V.ox + W * V.s, V.oy + top * V.s); ctx.stroke();
    ctx.strokeStyle = 'rgba(42,29,20,0.35)'; ctx.setLineDash([4 * V.s, 5 * V.s]);
    ctx.beginPath(); ctx.moveTo(V.ox + 70 * V.s, V.oy + (top - 26) * V.s); ctx.lineTo(V.ox + (W - 70) * V.s, V.oy + (top - 26) * V.s); ctx.stroke(); ctx.setLineDash([]);
    if (!d) return;
    const P = d.parade, n = P.length, x0 = 250, span = W - 2 * x0;      // inside the rail's window
    P.forEach((g, i) => {
      const x = x0 + (n > 1 ? i / (n - 1) : 1) * span;
      beast(ctx, V.ox + x * V.s, V.oy + (top - 26) * V.s, V.s * 1.1, g, 1, 0);
    });
    // the herd, nearest last
    const list = [...herd.values()].sort((a, b) => a.y1 - b.y1);
    for (const o of list) {
      const p = pos(o, now), flip = Math.cos(o.h) >= 0 ? 1 : -1;
      beast(ctx, V.ox + p.x * V.s, V.oy + p.y * V.s, V.s * 1.45, o.g, flip, t * 6 + o.x1 * 0.1);
    }
  }
  return { size: f => [f.w || 1200, f.h || 640], ingest, draw };
})();
