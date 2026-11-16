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

  // ── settlements: the division of labour made visible ─────────────────
  // trades: farmers (everyone not in a trade), then toolmakers, builders, potters, traders, priests, smiths, scribes
  const ROLE_COL = ['#5f8a2a', '#8a4b2a', '#d9a441', '#3f7fb5', '#f2b33d', '#8e6bbf', '#c0392b', '#2a1d14'];
  const hash = (a, b) => { let h = (a * 374761393 + b * 668265263) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
  const visible = (V, X, Y, R) => !V.pf || (X + R > V.pf.x && X - R < V.pf.x + V.pf.w && Y + R > V.pf.y && Y - R < V.pf.y + V.pf.h);
  // the layout of a settlement, the same every frame: houses on a sunflower spiral, its fields, its work places
  function plan(T) {
    const [id, , , pop, tier] = T, nH = Math.max(3, Math.min(90, Math.round(pop / 22))), R = 6 + 2.4 * Math.sqrt(nH);
    const houses = [];
    for (let k = 0; k < nH; k++) {
      const r = (tier >= 4 ? 4.5 : 2) + (R - 2) * Math.sqrt((k + 0.5) / nH), a = k * 2.39996 + id;
      houses.push([Math.cos(a) * r, Math.sin(a) * r * 0.62, 0.8 + 0.5 * hash(id, k)]);
    }
    const fields = [];
    if (tier >= 2) for (let k = 0; k < 6 + tier * 2; k++) {
      const a = (k / (6 + tier * 2)) * Math.PI * 2 + hash(id, 99) * 3, r = R + 5 + 3 * hash(id, k + 7);
      fields.push([Math.cos(a) * r, Math.sin(a) * r * 0.62, a, hash(id, k + 31)]);
    }
    const at = (a, r) => [Math.cos(a + id) * r, Math.sin(a + id) * r * 0.62];
    return { nH, R, houses, fields, work: [null, at(0.6, R * 0.55), at(2.2, R * 0.92), at(3.6, R * 0.8), [0, 0], at(4.9, R * 0.35), at(5.7, R * 0.7), at(1.4, R * 0.25)] };
  }
  const plans = new Map();
  const TS = 1.35;                                  // settlements are drawn a third larger than the wandering bands' scale
  function drawRoads(ctx, V) {
    if (!d.roads || !d.roads.length) return;
    ctx.save(); ctx.strokeStyle = 'rgba(138,90,40,0.55)'; ctx.lineWidth = Math.max(1, 1.6 * V.s); ctx.setLineDash([4 * V.s, 3 * V.s]);
    for (const [x1, y1, x2, y2] of d.roads) { ctx.beginPath(); ctx.moveTo(V.ox + x1 * V.s, V.oy + y1 * V.s); ctx.lineTo(V.ox + x2 * V.s, V.oy + y2 * V.s); ctx.stroke(); }
    ctx.restore();
  }
  function drawTowns(ctx, V, now, t, light) {
    if (!d.towns) return;
    for (const T of d.towns) {
      const [id, x, y, pop, tier, built, roles] = T;
      let P = plans.get(id);
      if (!P || P.pop !== pop || P.tier !== tier) { P = plan(T); P.pop = pop; P.tier = tier; plans.set(id, P); }
      const X = V.ox + x * V.s, Y = V.oy + y * V.s, k = V.s * TS, R = P.R;
      if (!visible(V, X, Y, (R + 14) * k)) continue;
      const lod = k * 2.2 >= 3.2;                     // big enough on screen for roofs, doors and walls in detail
      // fields: tilled strips in green and ochre
      for (const [fx, fy, a, h] of P.fields) {
        ctx.save(); ctx.translate(X + fx * k, Y + fy * k); ctx.rotate(a + Math.PI / 2);
        const w = 7 * k, hh = 4 * k;
        ctx.fillStyle = h < 0.5 ? '#b9cf6a' : '#d9c27a'; ctx.fillRect(-w / 2, -hh / 2, w, hh);
        if (lod) { ctx.strokeStyle = 'rgba(42,29,20,0.25)'; ctx.lineWidth = Math.max(0.6, 0.35 * k); for (let q = 1; q < 4; q++) { ctx.beginPath(); ctx.moveTo(-w / 2, -hh / 2 + q * hh / 4); ctx.lineTo(w / 2, -hh / 2 + q * hh / 4); ctx.stroke(); } }
        ctx.restore();
      }
      // ground of the place
      ctx.fillStyle = tier >= 4 ? '#d8c9a8' : '#cdb98a';
      ctx.beginPath(); ctx.ellipse(X, Y, (R + 1.5) * k, (R + 1.5) * 0.62 * k, 0, 0, Math.PI * 2); ctx.fill();
      // walls: a palisade of posts, then stone with towers
      if (tier >= 3) {
        const rw = R + 2.4, n = Math.round(rw * (tier >= 4 ? 1.4 : 2.2));
        ctx.strokeStyle = tier >= 4 ? '#7d7468' : '#6b4a2a'; ctx.lineWidth = Math.max(1, (tier >= 4 ? 1.6 : 0.9) * k);
        ctx.beginPath(); ctx.ellipse(X, Y, rw * k, rw * 0.62 * k, 0, 0, Math.PI * 2); ctx.stroke();
        if (lod) for (let q = 0; q < n; q++) {
          const a = q / n * Math.PI * 2, px = X + Math.cos(a) * rw * k, py = Y + Math.sin(a) * rw * 0.62 * k;
          if (tier >= 4 && q % Math.max(1, Math.round(n / 6)) === 0) { ctx.fillStyle = '#9a9084'; ctx.fillRect(px - 1.3 * k, py - 2.6 * k, 2.6 * k, 2.6 * k); ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.6, 0.3 * k); ctx.strokeRect(px - 1.3 * k, py - 2.6 * k, 2.6 * k, 2.6 * k); }
          else if (tier === 3) { ctx.fillStyle = '#6b4a2a'; ctx.fillRect(px - 0.3 * k, py - 1.4 * k, 0.6 * k, 1.4 * k); }
        }
      }
      // the central place: a hearth, a market square, a citadel
      if (tier >= 4) {
        ctx.fillStyle = '#e8dcc0'; ctx.fillRect(X - 3.2 * k, Y - 2 * k, 6.4 * k, 4 * k);
        if (lod) { ctx.strokeStyle = 'rgba(42,29,20,0.3)'; ctx.lineWidth = Math.max(0.5, 0.25 * k); ctx.strokeRect(X - 3.2 * k, Y - 2 * k, 6.4 * k, 4 * k);
          for (let q = 0; q < 4; q++) { ctx.fillStyle = ['#c0392b', '#f2b33d', '#3f7fb5', '#5f8a2a'][q]; ctx.fillRect(X - 2.6 * k + q * 1.5 * k, Y - 1.4 * k, 1 * k, 0.7 * k); } }
      }
      // houses: round huts, then gabled houses, roofs reddening into tile in towns
      const roof = tier >= 4 ? '#b5543a' : tier >= 2 ? '#8a6a3a' : '#7a5a34';
      for (const [hx, hy, sz] of P.houses) {
        const px = X + hx * k, py = Y + hy * k, w = 2.2 * sz * k;
        if (tier <= 1) {
          ctx.fillStyle = '#a07d4a'; ctx.beginPath(); ctx.arc(px, py, w * 0.55, 0, Math.PI * 2); ctx.fill();
          if (lod) { ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.5, 0.25 * k); ctx.stroke(); ctx.fillStyle = INK; ctx.fillRect(px - 0.2 * k, py, 0.4 * k, w * 0.4); }
        } else {
          ctx.fillStyle = '#efe3c6'; ctx.fillRect(px - w / 2, py - w * 0.3, w, w * 0.6);
          ctx.fillStyle = roof; ctx.beginPath(); ctx.moveTo(px - w * 0.62, py - w * 0.3); ctx.lineTo(px, py - w * 0.85); ctx.lineTo(px + w * 0.62, py - w * 0.3); ctx.closePath(); ctx.fill();
          if (lod) { ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.5, 0.22 * k); ctx.stroke(); ctx.strokeRect(px - w / 2, py - w * 0.3, w, w * 0.6); }
        }
      }
      const has = r => (roles[r] || 0) > 0.005;
      const W8 = P.work;
      // the work places, each where its trade works
      const site = (r, fn) => { if (has(r)) { const [wx, wy] = W8[r + 1]; fn(X + wx * k, Y + wy * k); } };
      if (tier >= 2) { const gx = X + W8[2][0] * 0.4 * k, gy = Y + W8[2][1] * 0.4 * k;                 // the granary
        ctx.fillStyle = '#d9a441'; ctx.beginPath(); ctx.arc(gx, gy, 1.9 * k, Math.PI, 0); ctx.lineTo(gx + 1.9 * k, gy + 1.4 * k); ctx.lineTo(gx - 1.9 * k, gy + 1.4 * k); ctx.closePath(); ctx.fill();
        if (lod) { ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.5, 0.25 * k); ctx.stroke(); } }
      else { ctx.fillStyle = '#e5602a'; ctx.beginPath(); ctx.arc(X, Y, 1.1 * k * (1 + 0.15 * Math.sin(t * 7 + id)), 0, Math.PI * 2); ctx.fill(); }
      site(1, (sx, sy) => { if (!lod) return; ctx.strokeStyle = '#8a6a3a'; ctx.lineWidth = Math.max(0.5, 0.3 * k);       // builders' scaffold
        ctx.strokeRect(sx - 1.5 * k, sy - 3 * k, 3 * k, 3 * k); ctx.beginPath(); ctx.moveTo(sx - 1.5 * k, sy - 3 * k); ctx.lineTo(sx + 1.5 * k, sy); ctx.moveTo(sx + 1.5 * k, sy - 3 * k); ctx.lineTo(sx - 1.5 * k, sy); ctx.stroke(); });
      site(2, (sx, sy) => { ctx.fillStyle = '#9a5a3a'; ctx.beginPath(); ctx.arc(sx, sy, 1.5 * k, Math.PI, 0); ctx.fill();      // potters' kiln, smoking
        smoke(ctx, sx, sy - 1.5 * k, k, t, id); });
      site(4, (sx, sy) => { for (let q = 0; q < 3; q++) { const w = (5 - q * 1.4) * k; ctx.fillStyle = q % 2 ? '#e8dcc0' : '#c9b48a';  // stepped temple
        ctx.fillRect(sx - w / 2, sy - (q + 1) * 1.2 * k, w, 1.2 * k); } if (lod) { ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.5, 0.22 * k); ctx.strokeRect(sx - 2.5 * k, sy - 3.6 * k, 5 * k, 3.6 * k); } });
      site(5, (sx, sy) => { ctx.fillStyle = '#3a2e28'; ctx.fillRect(sx - 1.6 * k, sy - 2 * k, 3.2 * k, 2 * k);               // smiths' forge
        ctx.fillStyle = `rgba(255,120,40,${0.6 + 0.3 * Math.sin(t * 9 + id)})`; ctx.fillRect(sx - 0.7 * k, sy - 1.2 * k, 1.4 * k, 0.9 * k); smoke(ctx, sx, sy - 2 * k, k, t, id + 3); });
      if (tier >= 5) {                                                                                                 // citadel and monument
        const [cx, cy] = W8[7]; ctx.fillStyle = '#b8ad9c'; ctx.fillRect(X + cx * k - 3 * k, Y + cy * k - 4.5 * k, 6 * k, 4.5 * k);
        ctx.fillStyle = '#9a9084'; for (const ox of [-3, 2]) ctx.fillRect(X + cx * k + ox * k, Y + cy * k - 6 * k, 1 * k, 6 * k);
        if (lod) { ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.5, 0.25 * k); ctx.strokeRect(X + cx * k - 3 * k, Y + cy * k - 4.5 * k, 6 * k, 4.5 * k); }
        ctx.fillStyle = '#efe3c6'; ctx.beginPath(); ctx.moveTo(X - 0.7 * k, Y + 0.5 * k); ctx.lineTo(X, Y - 6.5 * k); ctx.lineTo(X + 0.7 * k, Y + 0.5 * k); ctx.closePath(); ctx.fill();
        if (lod) { ctx.strokeStyle = INK; ctx.stroke(); }
      }
      // the people at their work: each figure walks between its home and its trade's place, and back
      const nW = Math.max(3, Math.min(48, Math.round(pop / 14)));
      const shares = [Math.max(0, 1 - roles.reduce((a, v) => a + v, 0)), ...roles];
      let acc = 0, r = 0, cum = shares[0];
      for (let q = 0; q < nW; q++) {
        const u = (q + 0.5) / nW;
        while (u > cum && r < shares.length - 1) { r++; cum += shares[r]; }
        const home = P.houses[q % P.houses.length];
        let wk;
        if (r === 0) { const f = P.fields.length ? P.fields[q % P.fields.length] : [Math.cos(q) * (R + 3), Math.sin(q) * (R + 3) * 0.62]; wk = [f[0], f[1]]; }
        else if (r === 4) wk = [Math.cos(q * 1.7) * 2.2, Math.sin(q * 1.7) * 1.3];             // traders mill about the market
        else { const w0 = W8[r] || [0, 0]; wk = [w0[0] + Math.cos(q) * 1.2, w0[1] + Math.sin(q) * 0.8]; }
        const speed = 0.06 + 0.05 * hash(id, q + 200), ph = (t * speed + hash(id, q + 300)) % 2, e = ph < 1 ? ph : 2 - ph;
        const s2 = e * e * (3 - 2 * e), fx = home[0] + (wk[0] - home[0]) * s2, fy = home[1] + (wk[1] - home[1]) * s2;
        const px = X + fx * k, py = Y + fy * k, rr = Math.max(0.9, 0.75 * k);
        ctx.fillStyle = ROLE_COL[r]; ctx.beginPath(); ctx.arc(px, py - rr, rr, 0, Math.PI * 2); ctx.fill();
        if (lod) { ctx.fillRect(px - rr * 0.6, py - rr * 0.2, rr * 1.2, rr * 1.4); }
      }
    }
  }
  function smoke(ctx, x, y, k, t, seed) {
    for (let q = 0; q < 3; q++) {
      const ph = (t * 0.35 + q / 3 + seed * 0.13) % 1;
      ctx.fillStyle = `rgba(110,100,95,${0.35 * (1 - ph)})`;
      ctx.beginPath(); ctx.arc(x + Math.sin(ph * 5 + seed) * 1.2 * k, y - ph * 7 * k, (0.6 + ph * 1.6) * k, 0, Math.PI * 2); ctx.fill();
    }
  }

  function draw(ctx, V, now, t, light) {
    if (!d) { ctx.fillStyle = ZONE[3]; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s); return; }
    if (!landCanvas) buildLand(V);
    ctx.drawImage(landCanvas, V.ox, V.oy, W * V.s, H * V.s);
    drawRoads(ctx, V);
    for (const o of bands.values()) {
      const [id, , , size, tools, fire, lang, art, hue, farm] = o.b, p = pos(o, now);
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
      if (farm) {                                         // a farming band carries seed: a green sprout beside it
        ctx.strokeStyle = '#5f8a2a'; ctx.lineWidth = Math.max(1, 0.9 * V.s);
        ctx.beginPath(); ctx.moveTo(X - s * 4.4, Y); ctx.lineTo(X - s * 4.4, Y - s * 2); ctx.moveTo(X - s * 4.4, Y - s * 1.2); ctx.quadraticCurveTo(X - s * 5.6, Y - s * 1.8, X - s * 5.4, Y - s * 2.4); ctx.stroke();
      }
      if (lang > 0.5) { ctx.strokeStyle = 'rgba(42,29,20,0.55)'; ctx.lineWidth = Math.max(1, 0.8 * V.s); ctx.beginPath(); ctx.arc(X, Y - s * 3, s * 1.6 * lang, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke(); }
    }
    drawTowns(ctx, V, now, t, light);
  }
  function drawGlow(ctx, V, now, t, light) {
    if (light > 0.8) return;
    const dark = Math.min(1, (0.8 - light) / 0.6);
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    // lit windows: the more people, the more lights after dark
    for (const T of d && d.towns || []) {
      const P = plans.get(T[0]); if (!P) continue;
      const X = V.ox + T[1] * V.s, Y = V.oy + T[2] * V.s, k = V.s * TS;
      if (!visible(V, X, Y, (P.R + 10) * k)) continue;
      const g = ctx.createRadialGradient(X, Y, 0, X, Y, (P.R + 6) * k);
      g.addColorStop(0, `rgba(255,190,90,${0.22 * dark})`); g.addColorStop(1, 'rgba(255,190,90,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(X, Y, (P.R + 6) * k, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `rgba(255,214,140,${0.9 * dark})`;
      for (let q = 0; q < P.houses.length; q += 2) { const [hx, hy] = P.houses[q], w = Math.max(1, 0.7 * k); if (hash(T[0], q + Math.floor(t / 7)) < 0.75) ctx.fillRect(X + hx * k - w / 2, Y + hy * k - w / 2, w, w); }
    }
    for (const o of bands.values()) {
      if (!o._fire) continue;
      const [X, Y] = o._fire, R = 26 * V.s * (0.9 + 0.1 * Math.sin(t * 7 + o.x1));
      const g = ctx.createRadialGradient(X, Y, 0, X, Y, R);
      g.addColorStop(0, `rgba(255,170,70,${0.65 * dark})`); g.addColorStop(1, 'rgba(255,170,70,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(X, Y, R, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  // the dark side, Anthropophthora: the land in ice-blue and soot, living bands as dim embers by size, ruins glowing amber
  // by how much their people knew (blue-white where the ice holds them), and rediscoveries flaring in bone
  function drawDark(ctx, V, now, t) {
    ctx.fillStyle = '#0b0c12'; ctx.fillRect(V.ox, V.oy, W * V.s, H * V.s);
    if (!d) return;
    const gx = d.gx, gy = d.gy, cw = W / gx * V.s, ch = H / gy * V.s;
    for (let k = 0; k < d.zones.length; k++) {
      const z = d.zones[k];
      if (z === 0) ctx.fillStyle = 'rgba(160,190,220,0.16)'; else if (z === 1) ctx.fillStyle = 'rgba(160,190,220,0.07)'; else continue;
      const x0 = Math.round(V.ox + (k % gx) * cw), y0 = Math.round(V.oy + Math.floor(k / gx) * ch);
      ctx.fillRect(x0, y0, Math.round(V.ox + (k % gx + 1) * cw) - x0, Math.round(V.oy + (Math.floor(k / gx) + 1) * ch) - y0);
    }
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (const o of bands.values()) {
      const p = pos(o, now), size = o.b[3], X = V.ox + p.x * V.s, Y = V.oy + p.y * V.s, R = (4 + Math.sqrt(size) * 1.6) * V.s;
      const g = ctx.createRadialGradient(X, Y, 0, X, Y, R);
      g.addColorStop(0, `rgba(229,96,42,${o.b[5] ? 0.45 : 0.25})`); g.addColorStop(1, 'rgba(229,96,42,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(X, Y, R, 0, Math.PI * 2); ctx.fill();
    }
    // living settlements from beneath: their walls in dim bone, their hearths as embers
    for (const T of d.towns || []) {
      const P = plans.get(T[0]) || plan(T), X = V.ox + T[1] * V.s, Y = V.oy + T[2] * V.s, R = (P.R + 2) * V.s;
      const g = ctx.createRadialGradient(X, Y, 0, X, Y, R * 1.4);
      g.addColorStop(0, `rgba(229,96,42,${0.07 + 0.02 * T[4]})`); g.addColorStop(1, 'rgba(229,96,42,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(X, Y, R * 1.4, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = 'rgba(232,220,196,0.35)'; ctx.lineWidth = Math.max(1, 0.8 * V.s);
      ctx.beginPath(); ctx.ellipse(X, Y, R, R * 0.62, 0, 0, Math.PI * 2); ctx.stroke();
    }
    for (const [rx, ry, tools, art, fire, buried, tier = 0] of (d.ruins || [])) {
      const X = V.ox + rx * V.s, Y = V.oy + ry * V.s, R = (6 + 1.2 * Math.sqrt(Math.min(tools, 200)) + 3 * tier) * V.s, col = buried ? '200,225,255' : '231,162,59';
      const g = ctx.createRadialGradient(X, Y, 0, X, Y, R * 1.6);
      g.addColorStop(0, `rgba(${col},0.28)`); g.addColorStop(1, `rgba(${col},0)`);
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(X, Y, R * 1.6, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
    for (const [rx, ry, tools, art, fire, buried, tier = 0] of (d.ruins || [])) {          // the ruin's outline: broken walls
      const X = V.ox + rx * V.s, Y = V.oy + ry * V.s, R = (5 + 1.5 * Math.sqrt(tools) + 5 * tier) * V.s;
      ctx.strokeStyle = buried ? 'rgba(200,225,255,0.7)' : 'rgba(232,220,196,0.75)'; ctx.lineWidth = Math.max(1, 1.2 * V.s);
      for (let k = 0; k < 4; k++) { ctx.beginPath(); ctx.arc(X, Y, R, k * Math.PI / 2 + 0.25, k * Math.PI / 2 + 1.2); ctx.stroke(); }
      if (art) { ctx.fillStyle = 'rgba(192,57,43,0.8)'; ctx.fillRect(X - 1.5 * V.s, Y - 1.5 * V.s, 3 * V.s, 3 * V.s); }
    }
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (const [fx, fy, age] of (d.finds || [])) {
      const p = age / 200, X = V.ox + fx * V.s, Y = V.oy + fy * V.s, R = (10 + 50 * p) * V.s;
      ctx.strokeStyle = `rgba(232,220,196,${0.8 * (1 - p)})`; ctx.lineWidth = Math.max(1, 2 * V.s);
      ctx.beginPath(); ctx.arc(X, Y, R, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
  }
  return { size: f => [f.w || 1200, f.h || 640], ingest, draw, drawGlow, drawDark, resize: () => { landCanvas = null; } };
})();
