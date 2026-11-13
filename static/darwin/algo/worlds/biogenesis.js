/* BIOGENESIS: a cream dish of flat round cells, tinted by its three nutrients; above it, on a gold band, the tree of
   life draws itself: each lineage a coloured line from its birth to now (or to its end), branching from its parent. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  let d = null, W = 1200, H = 640, fieldCanvas = null;

  function ingest(f) {
    d = f; W = f.w; H = f.h;
    // the nutrient field as a small image, smoothed when drawn
    const c = fieldCanvas || document.createElement('canvas');
    c.width = f.gx; c.height = f.gy;
    const g = c.getContext('2d'), img = g.createImageData(f.gx, f.gy), n = f.gx * f.gy, F = f.field;
    for (let i = 0; i < n; i++) {
      const a = F[i] / 10, b = F[n + i] / 10, cc = F[2 * n + i] / 10;
      img.data[i * 4] = 246 - 30 * b - 10 * cc; img.data[i * 4 + 1] = 231 - 25 * a - 20 * cc; img.data[i * 4 + 2] = 191 + 40 * a - 50 * b;
      img.data[i * 4 + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    fieldCanvas = c;
  }

  function draw(ctx, V, now, t) {
    if (!d) { ctx.fillStyle = '#f6e7bf'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s); return; }
    const top = d.top;
    // the dish
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(fieldCanvas, V.ox, V.oy + top * V.s, W * V.s, (H - top) * V.s);
    // the tree band
    ctx.fillStyle = '#d8b447'; ctx.fillRect(V.ox, V.oy, W * V.s, top * V.s);
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 2 * V.s);
    ctx.beginPath(); ctx.moveTo(V.ox, V.oy + top * V.s); ctx.lineTo(V.ox + W * V.s, V.oy + top * V.s); ctx.stroke();
    const t0 = d.tmin, t1 = Math.max(d.tick, t0 + 1), X = tk => V.ox + (60 + (tk - t0) / (t1 - t0) * (W - 120)) * V.s;
    const Y = lane => V.oy + (14 + lane * (top - 28)) * V.s;
    const by = new Map(d.tree.map(r => [r[0], r]));
    ctx.lineCap = 'round';
    for (const pass of [0, 1]) {
      for (const [sid, parent, born, died, hue, lane, alive] of d.tree) {
        const end = died > 0 ? died : d.tick, x0 = X(born), x1 = X(end), y = Y(lane);
        ctx.strokeStyle = pass ? `hsl(${hue * 360},60%,${alive ? 48 : 62}%)` : INK;
        ctx.lineWidth = (alive ? 3.2 : 1.6) * V.s + (pass ? 0 : 1.6 * V.s);
        ctx.beginPath();
        const p = by.get(parent);
        if (p) ctx.moveTo(x0, Y(p[5])), ctx.lineTo(x0, y); else ctx.moveTo(x0, y);
        ctx.lineTo(x1, y); ctx.stroke();
      }
    }
    // living tips: a bead at the right edge
    for (const [sid, parent, born, died, hue, lane, alive] of d.tree) {
      if (!alive) continue;
      ctx.fillStyle = `hsl(${hue * 360},65%,55%)`; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 1.2 * V.s);
      ctx.beginPath(); ctx.arc(X(d.tick), Y(lane), 4 * V.s, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
    // cells
    for (const [x, y, m, hue, spec] of d.cells) {
      const X0 = V.ox + x * V.s, Y0 = V.oy + y * V.s, r = 2.2 * Math.sqrt(Math.max(m, 0.5)) * V.s * (1 + 0.04 * Math.sin(t * 2 + x));
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(X0, Y0, r + 1.2 * V.s, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `hsl(${hue * 360},${40 + 40 * spec}%,58%)`; ctx.beginPath(); ctx.arc(X0, Y0, r, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = 'rgba(42,29,20,0.6)'; ctx.beginPath(); ctx.arc(X0 + r * 0.15, Y0 + r * 0.1, r * 0.32, 0, Math.PI * 2); ctx.fill();
    }
  }
  return { size: f => [f.w || 1200, f.h || 640], ingest, draw };
})();
