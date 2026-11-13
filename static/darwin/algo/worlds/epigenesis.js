/* EPIGENESIS: sixteen chrome pockets, an embryo developing in each. Every cell is a flat dot coloured by its type;
   the embryo swells with each division. A finished embryo glows in its pocket before the pocket is cleared. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  const PAL = ['#fbf3dc', '#e5602a', '#f2b33d', '#a8c94a', '#3f97b5', '#c9b6ff', '#e58bb0', '#8fd3c8',
               '#b9560c', '#6b8f2a', '#2b5f86', '#d8b447', '#7d5ba6', '#c0392b', '#4fa38f', '#f6e7bf'];
  let d = null, W = 1200, H = 640, prev = null, at = 0;

  function ingest(f, now) { prev = d; d = f; W = f.w; H = f.h; at = now; }

  function draw(ctx, V, now, t) {
    ctx.fillStyle = '#f2b33d'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    // a printed sunburst behind the pockets
    ctx.save(); ctx.translate(V.ox + W * V.s / 2, V.oy + H * V.s / 2);
    for (let k = 0; k < 36; k++) {
      ctx.fillStyle = k % 2 ? '#f6c25a' : '#eea83a';
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, W * V.s, k * Math.PI / 18, (k + 1) * Math.PI / 18); ctx.closePath(); ctx.fill();
    }
    ctx.restore();
    if (!d) return;
    const cols = 8, rows = 2, mx = 105, cw = (W - 2 * mx) / cols, ch = H / rows;   // kept inside the rail's window
    d.wells.forEach((w, i) => {
      const cx = V.ox + (mx + (i % cols + 0.5) * cw) * V.s, cy = V.oy + (Math.floor(i / cols) + 0.5) * ch * V.s;
      const R = Math.min(cw, ch) * 0.4 * V.s;
      // the pocket
      const g = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.3, R * 0.1, cx, cy, R * 1.15);
      g.addColorStop(0, '#ffffff'); g.addColorStop(0.5, '#c3cad0'); g.addColorStop(1, '#6c757d');
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(cx, cy, R * 1.17, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R * 1.13, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#fbf3dc'; ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 1.2 * V.s); ctx.stroke();
      // the embryo
      const pos = d.positions[String(w.stage)], n = pos.length;
      const grow = (0.35 + 0.65 * w.stage / 6);
      const cr = R * 0.9 * grow / Math.sqrt(n) * 0.95;
      const breathe = 1 + 0.03 * Math.sin(t * 1.5 + i);
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(cx, cy, R * 0.9 * grow * breathe + cr * 0.9, 0, Math.PI * 2); ctx.fill();
      for (let k = 0; k < n; k++) {
        const [px, py] = pos[k], x = cx + px * R * 0.9 * grow * breathe, y = cy + py * R * 0.9 * grow * breathe;
        ctx.fillStyle = PAL[w.types[k] % 16];
        ctx.beginPath(); ctx.arc(x, y, cr * 1.05, 0, Math.PI * 2); ctx.fill();
      }
      w._c = [cx, cy, R];
    });
  }
  function drawGlow(ctx, V, now, t) {
    if (!d) return;
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (const w of d.wells) {
      if (!w.done || !w._c || !w.score) continue;
      const [cx, cy, R] = w._c, a = Math.min(0.45, w.score / 20);
      const g = ctx.createRadialGradient(cx, cy, R * 0.6, cx, cy, R * 1.5);
      g.addColorStop(0, `rgba(255,230,140,${a})`); g.addColorStop(1, 'rgba(255,230,140,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R * 1.5, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  return { size: f => [f.w || 1200, f.h || 640], ingest, draw, drawGlow };
})();
