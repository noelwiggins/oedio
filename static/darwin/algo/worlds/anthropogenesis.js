/* ANTHROPOGENESIS: a continent in flat bands of colour (ice, tundra, steppe, grassland, forest), with the ice line moving.
   Each band of people is a little cluster of figures; bands that keep fire have a campfire that blazes at night,
   painted bands carry a red handprint, and a tool mark grows beside bands as their tools improve. */
window.ALGO_WORLD = (function () {
  'use strict';
  const INK = '#2a1d14';
  const ZONE = ['#eef4f2', '#c9e3df', '#d9c27a', '#a8c94a', '#6b8f2a'];
  let d = null, W = 1200, H = 640, landCanvas = null, zkey = '';
  const bands = new Map();
  const LAG = 900;

  function ingest(f, now) {
    d = f; W = f.w; H = f.h;
    const key = f.zones.join('');
    if (key !== zkey) { zkey = key; landCanvas = null; }
    const seen = new Set();
    for (const b of f.bands) {
      const [id, x, y] = b;
      seen.add(id);
      let o = bands.get(id);
      if (!o) { o = { x0: x, y0: y, x1: x, y1: y, t0: now, t1: now, born: now }; bands.set(id, o); }
      else { const p = pos(o, now); Object.assign(o, { x0: p.x, y0: p.y, x1: x, y1: y, t0: now, t1: now + LAG }); }
      o.b = b;
    }
    for (const [id] of bands) if (!seen.has(id)) bands.delete(id);
  }
  function pos(o, now) {
    const f = o.t1 > o.t0 ? Math.min(1, Math.max(0, (now - o.t0) / (o.t1 - o.t0))) : 1;
    return { x: o.x0 + (o.x1 - o.x0) * f, y: o.y0 + (o.y1 - o.y0) * f };
  }

  function buildLand(V) {
    // smooth the zone grid into flat, outlined plains (nearest-zone on a fine raster)
    const tw = Math.round(Math.min(W * V.s, 1400)), th = Math.round(tw * H / W), c = document.createElement('canvas');
    c.width = tw; c.height = th;
    const g = c.getContext('2d'), img = g.createImageData(tw, th), Dd = img.data, gx = d.gx, gy = d.gy, Z = d.zones;
    const zoneAt = (px, py) => {
      const fx = px / tw * gx - 0.5, fy = py / th * gy - 0.5;
      const x0 = Math.max(0, Math.min(gx - 1, Math.round(fx + 0.25 * Math.sin(py / 9)))), y0 = Math.max(0, Math.min(gy - 1, Math.round(fy + 0.25 * Math.sin(px / 11))));
      return Z[y0 * gx + x0];
    };
    const zs = new Uint8Array(tw * th);
    for (let y = 0; y < th; y++) for (let x = 0; x < tw; x++) zs[y * tw + x] = zoneAt(x, y);
    for (let y = 0; y < th; y++) for (let x = 0; x < tw; x++) {
      const z = zs[y * tw + x], edge = (x + 1 < tw && zs[y * tw + x + 1] !== z) || (y + 1 < th && zs[(y + 1) * tw + x] !== z);
      const hex = edge ? INK : ZONE[z], k = (y * tw + x) * 4;
      Dd[k] = parseInt(hex.slice(1, 3), 16); Dd[k + 1] = parseInt(hex.slice(3, 5), 16); Dd[k + 2] = parseInt(hex.slice(5, 7), 16); Dd[k + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    landCanvas = c;
  }

  function figure(ctx, x, y, s, hue) {
    ctx.fillStyle = `hsl(${hue * 360},45%,38%)`;
    ctx.beginPath(); ctx.arc(x, y - s * 1.6, s * 0.45, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.moveTo(x - s * 0.55, y); ctx.lineTo(x, y - s * 1.2); ctx.lineTo(x + s * 0.55, y); ctx.closePath(); ctx.fill();
  }

  function draw(ctx, V, now, t, light) {
    if (!d) { ctx.fillStyle = ZONE[3]; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s); return; }
    if (!landCanvas) buildLand(V);
    ctx.drawImage(landCanvas, V.ox, V.oy, W * V.s, H * V.s);
    for (const o of bands.values()) {
      const [id, , , size, tools, fire, lang, art, hue] = o.b, p = pos(o, now);
      const X = V.ox + p.x * V.s, Y = V.oy + p.y * V.s, s = 3.2 * V.s, n = Math.max(1, Math.min(9, Math.round(size / 7)));
      // ground disc
      ctx.fillStyle = 'rgba(42,29,20,0.18)'; ctx.beginPath(); ctx.ellipse(X, Y + s * 0.3, s * (3 + n * 0.5), s * 1.6, 0, 0, Math.PI * 2); ctx.fill();
      for (let k = 0; k < n; k++) {
        const a = k / n * Math.PI * 2 + id, r = n > 1 ? s * (1.6 + n * 0.25) : 0;
        figure(ctx, X + Math.cos(a) * r, Y + Math.sin(a) * r * 0.5 + s * 0.6, s, hue);
      }
      if (fire) {
        ctx.fillStyle = '#e5602a'; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 0.8 * V.s);
        const fl = 1 + 0.2 * Math.sin(t * 8 + id);
        ctx.beginPath(); ctx.moveTo(X - s * 0.8, Y); ctx.quadraticCurveTo(X, Y - s * 2.6 * fl, X + s * 0.8, Y); ctx.closePath(); ctx.fill(); ctx.stroke();
        ctx.fillStyle = '#f2b33d'; ctx.beginPath(); ctx.moveTo(X - s * 0.4, Y); ctx.quadraticCurveTo(X, Y - s * 1.4 * fl, X + s * 0.4, Y); ctx.closePath(); ctx.fill();
        o._fire = [X, Y - s];
      } else o._fire = null;
      // tools: a stack of chevrons, one per five levels (up to six)
      const tk = Math.min(6, Math.ceil(tools / 5));
      ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, 1.1 * V.s);
      for (let k = 0; k < tk; k++) { const yy = Y - s * (3.2 + k * 0.9); ctx.beginPath(); ctx.moveTo(X + s * 3.4, yy + s * 0.5); ctx.lineTo(X + s * 4.1, yy); ctx.lineTo(X + s * 4.8, yy + s * 0.5); ctx.stroke(); }
      if (art) { ctx.fillStyle = '#c0392b'; ctx.beginPath(); ctx.arc(X - s * 3.6, Y - s * 2.4, s * 0.8, 0, Math.PI * 2); ctx.fill(); for (let k = 0; k < 4; k++) { ctx.fillRect(X - s * 4.2 + k * s * 0.4, Y - s * 3.8, s * 0.25, s * 1); } }
      if (lang > 0.5) { ctx.strokeStyle = 'rgba(42,29,20,0.55)'; ctx.lineWidth = Math.max(1, 0.8 * V.s); ctx.beginPath(); ctx.arc(X, Y - s * 3, s * 1.6 * lang, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke(); }
    }
  }
  function drawGlow(ctx, V, now, t, light) {
    if (light > 0.8) return;
    const dark = Math.min(1, (0.8 - light) / 0.6);
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (const o of bands.values()) {
      if (!o._fire) continue;
      const [X, Y] = o._fire, R = 26 * V.s * (0.9 + 0.1 * Math.sin(t * 7 + o.x1));
      const g = ctx.createRadialGradient(X, Y, 0, X, Y, R);
      g.addColorStop(0, `rgba(255,170,70,${0.65 * dark})`); g.addColorStop(1, 'rgba(255,170,70,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(X, Y, R, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  return { size: f => [f.w || 1200, f.h || 640], ingest, draw, drawGlow, resize: () => { landCanvas = null; } };
})();
