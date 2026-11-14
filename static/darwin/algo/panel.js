/* ALGOGENESIS panel — a living world inside a vintage pachinko cabinet.
   Every animal is drawn from its own genes (segments, legs, tail, crest, colour, pattern, glow, age); every flower from
   its own genes (petals, colours, size). The landscape is flat plains of colour, one per zone, outlined like a
   screen-printed playfield. All words live behind the keys in the tray.
   Query options: ?quiet=1 hides the keys. */
(function () {
  'use strict';
  const API = (document.body.dataset.api && document.body.dataset.api.indexOf('__') !== 0) ? document.body.dataset.api : '/api';
  const Q = new URLSearchParams(location.search);
  if (Q.get('quiet') === '1') document.body.classList.add('quiet');
  const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
  const veil = document.getElementById('veil'), keys = document.getElementById('keys'), card = document.getElementById('card');
  const INK = '#2a1d14', CREAM = '#fbf3dc', ORANGE = '#ee7d22', RIM = '#b9560c';
  let W = 1200, H = 800, terrain = null, terrCanvas = null, terrSea = null, pins = [];
  let L = {};                                   // layout, in canvas pixels
  let live = null;
  const animals = new Map(), plants = new Map();
  const LAG = 1100;

  // ── layout: cabinet, chrome bezel, playfield, tray ───────────────────
  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(innerWidth * dpr); cv.height = Math.round(innerHeight * dpr);
    const cw = cv.width, ch = cv.height, u = Math.min(cw, ch);
    const m = u * 0.035, trayH = ch * 0.15;
    const pf = { x: m, y: m, w: cw - 2 * m, h: ch - trayH - m * 1.6 };          // playfield window
    const s = Math.max(pf.w / W, pf.h / H);         // the world fills the window; the rail and bezel crop its edges
    L = { dpr, cw, ch, u, m, trayH, pf, s, ox: pf.x + (pf.w - W * s) / 2, oy: pf.y + (pf.h - H * s) / 2,
          tray: { x: m, y: ch - trayH - m * 0.4, w: cw - 2 * m, h: trayH } };
    // the guide rail: a great circle through the playfield, as on a pachinko board
    L.rail = { cx: pf.x + pf.w / 2, cy: pf.y + pf.h * 0.58, r: Math.min(pf.w * 0.485, pf.h * 0.86) };
    terrCanvas = null; flowerCache.clear(); placeKeys();
  }
  addEventListener('resize', resize);

  function placeKeys() {
    const t = L.tray, d = L.dpr;
    keys.style.left = 'auto'; keys.style.right = ((L.cw - (t.x + t.w) + L.u * 0.03) / d) + 'px';
    // fit the knobs and keys beside the fossil window: shrink them on narrow screens rather than overlap
    keys.style.transform = 'translateY(-50%)'; keys.style.transformOrigin = 'right center';
    const gsz = t.h * 0.56, leftLimit = t.x + L.u * 0.06 + gsz + L.u * 0.04 + t.w * 0.2 + L.u * 0.04 + L.u * 0.14;
    const allowed = (t.x + t.w - L.u * 0.03) - leftLimit, natural = keys.offsetWidth * d;
    const k = natural > 0 ? Math.min(1, allowed / natural) : 1;
    keys.style.transform = `translateY(-50%) scale(${Math.max(0.45, k).toFixed(3)})`;
    keys.style.top = ((t.y + t.h / 2) / d) + 'px';
    const pf = L.pf, cw = Math.min(pf.w * 0.5, L.u * 0.95), chh = pf.h * 0.78;
    card.style.width = (cw / d) + 'px'; card.style.maxHeight = (chh / d) + 'px';
    card.style.left = ((pf.x + (pf.w - cw) / 2) / d) + 'px'; card.style.top = ((pf.y + pf.h * 0.1) / d) + 'px';
    if (window.AlgoFossils) {
      const fw = Math.min(pf.w * 0.9, L.u * 1.5), fh = pf.h * 0.92;
      AlgoFossils.place({ x: (pf.x + (pf.w - fw) / 2) / d, y: (pf.y + (pf.h - fh) / 2) / d, w: fw / d, h: fh / d });
    }
  }

  // ── data ─────────────────────────────────────────────────────────────
  async function getJSON(u) { const r = await fetch(API + u, { cache: 'no-store' }); return r.json(); }
  async function loadTerrain() {
    try {
      const t = await getJSON('/terrain');
      if (t.standby) { setTimeout(loadTerrain, 4000); return; }
      terrain = t; W = t.w; H = t.h; resize();
    } catch (e) { setTimeout(loadTerrain, 4000); }
  }
  async function poll() {
    try { const d = await getJSON('/live'); if (!d.standby) ingest(d); } catch (e) { }
    setTimeout(poll, 700);
  }
  function ingest(d) {
    const now = performance.now();
    if (live && d.tick === live.tick) return;
    live = d;
    if (window.AlgoDials) AlgoDials.update(d.dials);
    feedSound(d);
    const seen = new Set();
    for (const a of d.animals) {
      const [id, x, y, h, sp, grown, parent, ...look] = a;
      seen.add(id);
      let o = animals.get(id);
      if (!o) { o = { id, x0: x, y0: y, h0: h, x1: x, y1: y, h1: h, t0: now, t1: now, born: now, phase: Math.random() * 6.28 }; animals.set(id, o); }
      else { const p = pos(o, now); o.x0 = p.x; o.y0 = p.y; o.h0 = p.h; o.x1 = x; o.y1 = y; o.h1 = h; o.t0 = now; o.t1 = now + LAG; o.dead = 0; }
      o.look = look; o.sp = sp; o.grown = grown; o.parent = parent;
    }
    for (const [id, o] of animals) if (!seen.has(id) && !o.dead) o.dead = now;
    const pseen = new Set();
    for (const p of d.plants) {
      const [id, x, y, hue, petals, size, height, sat, hue2, nectar, sp] = p;
      pseen.add(id);
      let o = plants.get(id);
      if (!o) { o = { id, x, y, born: now }; plants.set(id, o); }
      Object.assign(o, { hue, petals: Math.round(petals), size, height, sat, hue2, nectar, sp, dead: 0 });
    }
    for (const [id, o] of plants) if (!pseen.has(id) && !o.dead) o.dead = now;
    veil.classList.add('gone');
    if (openCard && openCard !== 'dial') renderCard(openCard, true);
  }
  function pos(o, now) {
    const f = o.t1 > o.t0 ? Math.min(1, Math.max(0, (now - o.t0) / (o.t1 - o.t0))) : 1;
    let dh = o.h1 - o.h0; dh = ((dh + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
    return { x: o.x0 + (o.x1 - o.x0) * f, y: o.y0 + (o.y1 - o.y0) * f, h: o.h0 + dh * f, moving: Math.hypot(o.x1 - o.x0, o.y1 - o.y0) / Math.max(1, (o.t1 - o.t0) / 1000) };
  }

  // ── the landscape: flat plains of colour, one per zone ───────────────
  const ZONES = [            // [upper bound of height above sea, colour, name]
    [-0.42, [43, 95, 134], 'deep'], [-0.16, [63, 151, 181], 'sea'], [0.0, [143, 211, 200], 'shallows'],
    [0.045, [246, 231, 191], 'shore'], [0.30, [168, 201, 74], 'meadow'], [0.58, [242, 179, 61], 'upland'],
    [9, [229, 96, 42], 'heights']];
  function zoneOf(d) { for (let i = 0; i < ZONES.length; i++) if (d <= ZONES[i][0]) return i; return ZONES.length - 1; }
  function hAt(x, y) {
    const gx = x / W * terrain.gx - 0.5, gy = y / H * terrain.gy - 0.5;
    const x0 = Math.max(0, Math.min(terrain.gx - 1, Math.floor(gx))), y0 = Math.max(0, Math.min(terrain.gy - 1, Math.floor(gy)));
    const x1 = Math.min(terrain.gx - 1, x0 + 1), y1 = Math.min(terrain.gy - 1, y0 + 1);
    const fx = Math.max(0, Math.min(1, gx - x0)), fy = Math.max(0, Math.min(1, gy - y0)), T = terrain.h_, n = terrain.gx;
    return (T[y0 * n + x0] * (1 - fx) + T[y0 * n + x1] * fx) * (1 - fy) + (T[y1 * n + x0] * (1 - fx) + T[y1 * n + x1] * fx) * fy;
  }
  function buildTerrain(sea) {
    const ts = Math.min(L.s, 1600 / W), tw = Math.round(W * ts), th = Math.round(H * ts), step = 1 / ts;
    const zone = new Uint8Array(tw * th);
    for (let py = 0; py < th; py++) for (let px = 0; px < tw; px++) zone[py * tw + px] = zoneOf(hAt(px * step, py * step) - sea);
    const c = document.createElement('canvas'); c.width = tw; c.height = th;
    const g = c.getContext('2d'), img = g.createImageData(tw, th), D = img.data;
    const ow = Math.max(1, Math.round(1.6 * ts));         // outline weight
    for (let py = 0; py < th; py++) {
      for (let px = 0; px < tw; px++) {
        const z = zone[py * tw + px];
        let edge = false;
        for (let k = 1; k <= ow && !edge; k++) {
          if (px + k < tw && zone[py * tw + px + k] !== z) edge = true;
          else if (py + k < th && zone[(py + k) * tw + px] !== z) edge = true;
        }
        let col = ZONES[z][1];
        // a fine halftone screen on the water, like old printed playfields
        if (!edge && z <= 1 && (px % 7 === 3) && (py % 7 === 3)) col = col.map(v => v * 0.86);
        const k4 = (py * tw + px) * 4;
        if (edge) { D[k4] = 42; D[k4 + 1] = 29; D[k4 + 2] = 20; } else { D[k4] = col[0]; D[k4 + 1] = col[1]; D[k4 + 2] = col[2]; }
        D[k4 + 3] = 255;
      }
    }
    g.putImageData(img, 0, 0);
    terrCanvas = c; terrSea = sea;
    // brass pins along the coast and the hill lines, as on a pachinko board
    pins = [];
    const grid = 26;
    for (let y = grid / 2; y < H; y += grid) for (let x = grid / 2 + ((y / grid) % 2) * grid / 2; x < W; x += grid) {
      const z = zoneOf(hAt(x, y) - sea);
      const zr = zoneOf(hAt(x + grid * 0.6, y) - sea), zd = zoneOf(hAt(x, y + grid * 0.6) - sea);
      if ((z !== zr || z !== zd) && Math.max(z, zr, zd) >= 2) pins.push([x, y, 0]);
    }
    // a fan of pins under the top of the rail, as on a real board (screen positions, so stored as fractions)
    for (let k = 0; k < 3; k++) for (let a = 1.18 * Math.PI; a <= 1.82 * Math.PI + 1e-6; a += Math.PI / (22 + k * 4))
      pins.push([a, 0.9 - k * 0.055, 1]);
  }

  // ── flowers: flat symbols, no stems ──────────────────────────────────
  const flowerCache = new Map();
  function flowerSprite(p, open) {
    const key = `${Math.round(p.hue * 36)}|${p.petals}|${Math.round(p.sat * 3)}|${Math.round(p.hue2 * 8)}|${open ? 1 : 0}`;
    let s = flowerCache.get(key);
    if (s) return s;
    const R = Math.max(8, Math.round(11 * L.s));
    s = document.createElement('canvas'); s.width = s.height = R * 2 + 6;
    const g = s.getContext('2d'); g.translate(R + 3, R + 3);
    const hue = p.hue * 360, Lt = 56 + 8 * (1 - p.sat), S = 45 + 50 * p.sat;
    const n = p.petals, pr = open ? R : R * 0.62;
    g.lineWidth = Math.max(1, R * 0.11); g.strokeStyle = INK; g.fillStyle = `hsl(${hue},${S}%,${Lt}%)`;
    for (let i = 0; i < n; i++) {
      g.save(); g.rotate(i / n * Math.PI * 2 - Math.PI / 2);
      g.beginPath(); g.ellipse(pr * 0.5, 0, pr * 0.5, pr * (open ? 0.26 : 0.18) * (1 + 2.5 / n), 0, 0, Math.PI * 2); g.fill(); g.stroke();
      g.restore();
    }
    g.fillStyle = `hsl(${p.hue2 * 360},75%,58%)`;
    g.beginPath(); g.arc(0, 0, R * 0.26, 0, Math.PI * 2); g.fill(); g.stroke();
    flowerCache.set(key, s);
    return s;
  }
  function drawPlants(now, t, light) {
    const open = light > 0.25, list = [...plants.values()].sort((a, b) => a.y - b.y);
    for (const p of list) {
      let a = Math.min(1, (now - p.born) / 1500);
      if (p.dead) { a = Math.max(0, 1 - (now - p.dead) / 1500); if (a <= 0) { plants.delete(p.id); continue; } }
      const X = L.ox + p.x * L.s, Y = L.oy + p.y * L.s;
      const spr = flowerSprite(p, open), k = (0.42 + 0.38 * p.size) * (0.75 + 0.25 * p.nectar) * Math.min(1, a + 0.3) / 1.7;
      const w = spr.width * k, rot = Math.sin(t * 0.5 + p.x * 0.03) * 0.15;
      ctx.globalAlpha = a;
      ctx.save(); ctx.translate(X, Y); ctx.rotate(rot); ctx.drawImage(spr, -w / 2, -w / 2, w, w); ctx.restore();
    }
    ctx.globalAlpha = 1;
  }

  // ── animals: flat decal shapes with an ink outline ───────────────────
  // look = [hue, sat, hue2, pattern, glow, segs, limbs, size, tail, crest, fin, diet]
  function animalGeometry(o, now, t) {
    const p = pos(o, now);
    const [hue, sat, hue2, pattern, glow, segs, limbs, size, tail, crest, fin, diet] = o.look;
    const s = L.s, X = L.ox + p.x * s, Y = L.oy + p.y * s;
    const r0 = (1.6 + 1.6 * size) * s * 1.95 * (o.grown || 1), gap = r0 * 1.05;
    const ph = t * (2.5 + Math.min(4, p.moving * 0.25)) + o.phase;
    const pts = []; let ang = p.h + Math.PI, cx = X, cy = Y;
    for (let i = 0; i < segs; i++) {
      pts.push([cx, cy, r0 * (1 - 0.5 * i / Math.max(segs, 2)) * (i === 0 ? 1.05 : 1), ang]);
      ang = p.h + Math.PI + Math.sin(ph - i * 0.9) * 0.28 * (fin > 0.5 ? 1 : 0.4) * Math.min(1, i / 2 + 0.3);
      cx += Math.cos(ang) * gap; cy += Math.sin(ang) * gap;
    }
    return { p, pts, r0, ph, X, Y };
  }
  function drawAnimal(o, now, t, light, glowLayer) {
    let alpha = Math.min(1, (now - o.born) / 900);
    if (o.dead) { alpha = Math.max(0, 1 - (now - o.dead) / 1200); if (alpha <= 0) { animals.delete(o.id); return; } }
    const { p, pts, r0, ph } = animalGeometry(o, now, t);
    o._head = pts[0];
    const [hue, sat, hue2, pattern, glow, segs, limbs, size, tail, crest, fin, diet] = o.look;
    const Lt = 48 + 14 * (1 - sat), S = 25 + 70 * sat;
    const base = `hsl(${hue * 360},${S}%,${Lt}%)`, alt = `hsl(${hue2 * 360},${Math.max(45, S)}%,${Math.min(70, Lt + 8)}%)`;
    const ow = Math.max(1, r0 * 0.22);
    ctx.globalAlpha = alpha; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    // legs
    if (limbs > 0) {
      for (const pass of [0, 1]) {
        ctx.strokeStyle = pass ? alt : INK; ctx.lineWidth = Math.max(1, r0 * 0.26) + (pass ? 0 : ow * 1.2);
        for (let k = 0; k < limbs; k++) {
          const i = Math.min(pts.length - 1, Math.round((k + 0.5) * pts.length / limbs - 0.5));
          const [px, py, r, a] = pts[i], step = Math.sin(ph * 1.6 + k * 1.7) * 0.5;
          for (const side of [-1, 1]) {
            const la = a + side * (Math.PI / 2 + step * side), len = r * 2.1;
            ctx.beginPath(); ctx.moveTo(px, py);
            ctx.lineTo(px + Math.cos(la) * len * 0.6, py + Math.sin(la) * len * 0.6);
            ctx.lineTo(px + Math.cos(la + 0.6 * side) * len, py + Math.sin(la + 0.6 * side) * len); ctx.stroke();
          }
        }
      }
    }
    // tail
    const last = pts[pts.length - 1];
    if (tail > 0.15) {
      const [tx, ty, r, a] = last, tl = r0 * (1.2 + 3 * tail), sp = 0.35 + 0.4 * fin;
      ctx.fillStyle = alt; ctx.strokeStyle = INK; ctx.lineWidth = ow;
      ctx.beginPath(); ctx.moveTo(tx, ty);
      ctx.lineTo(tx + Math.cos(a - sp) * tl, ty + Math.sin(a - sp) * tl);
      ctx.quadraticCurveTo(tx + Math.cos(a) * tl * 0.6, ty + Math.sin(a) * tl * 0.6, tx + Math.cos(a + sp) * tl, ty + Math.sin(a + sp) * tl);
      ctx.closePath(); ctx.fill(); ctx.stroke();
    }
    // crest
    if (crest > 0.25) {
      for (const pass of [0, 1]) {
        ctx.strokeStyle = pass ? alt : INK; ctx.lineWidth = Math.max(1, r0 * 0.2) + (pass ? 0 : ow);
        for (const [px, py, r, a] of pts) {
          const nrm = a + Math.PI / 2, len = r * (0.6 + 1.6 * crest);
          ctx.beginPath(); ctx.moveTo(px + Math.cos(nrm) * r * 0.7, py + Math.sin(nrm) * r * 0.7);
          ctx.lineTo(px + Math.cos(nrm) * (r + len), py + Math.sin(nrm) * (r + len)); ctx.stroke();
        }
      }
    }
    // body: an ink silhouette, then the colours
    ctx.fillStyle = INK;
    for (const [px, py, r] of pts) { ctx.beginPath(); ctx.arc(px, py, r + ow, 0, Math.PI * 2); ctx.fill(); }
    for (let i = pts.length - 1; i >= 0; i--) {
      const [px, py, r] = pts[i];
      ctx.fillStyle = (pattern > 0.33 && pattern <= 0.66 && i % 2 === 1) ? alt : base;
      ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill();
      if (pattern > 0.66 && r > 2) {
        ctx.fillStyle = alt; ctx.beginPath();
        ctx.arc(px + r * 0.35, py - r * 0.25, r * 0.3, 0, Math.PI * 2); ctx.arc(px - r * 0.3, py + r * 0.3, r * 0.24, 0, Math.PI * 2); ctx.fill();
      }
    }
    // eye
    const [hx, hy, hr] = pts[0];
    ctx.fillStyle = CREAM; ctx.beginPath(); ctx.arc(hx + Math.cos(p.h) * hr * 0.45, hy + Math.sin(p.h) * hr * 0.45, Math.max(0.9, hr * 0.3), 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(hx + Math.cos(p.h) * hr * 0.55, hy + Math.sin(p.h) * hr * 0.55, Math.max(0.6, hr * 0.15), 0, Math.PI * 2); ctx.fill();
    if (diet > 0.6) {
      ctx.strokeStyle = CREAM; ctx.lineWidth = Math.max(0.8, hr * 0.18);
      ctx.beginPath(); ctx.arc(hx + Math.cos(p.h) * hr * 0.75, hy + Math.sin(p.h) * hr * 0.75, hr * 0.35, p.h - 1.0, p.h + 1.0); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    if (glow > 0.12 && light < 0.85) glowLayer.push([pts, hue, glow, alpha, t + o.phase]);
  }
  // a dotted thread from each young animal to the parent that cares for it
  function drawFamilies(now) {
    ctx.save(); ctx.setLineDash([2 * L.dpr, 4 * L.dpr]); ctx.lineWidth = Math.max(1, 1.1 * L.dpr); ctx.strokeStyle = 'rgba(251,243,220,0.75)';
    for (const o of animals.values()) {
      if (!o.parent || o.dead || !o._head) continue;
      const par = animals.get(o.parent);
      if (!par || par.dead || !par._head) continue;
      const [x1, y1] = o._head, [x2, y2] = par._head;
      if (Math.hypot(x1 - x2, y1 - y2) > 60 * L.s) continue;
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
    ctx.restore();
  }
  function drawGlow(list, light) {
    if (!list.length) return;
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    const dark = Math.min(1, (0.85 - light) / 0.6);
    for (const [pts, hue, glow, alpha, ph] of list) {
      const pulse = 0.75 + 0.25 * Math.sin(ph * 1.7);
      for (const [px, py, r] of pts) {
        const R = r * (2.5 + 5 * glow) * pulse, g = ctx.createRadialGradient(px, py, 0, px, py, R);
        g.addColorStop(0, `hsla(${hue * 360},95%,68%,${0.6 * glow * alpha * dark})`); g.addColorStop(1, `hsla(${hue * 360},95%,50%,0)`);
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(px, py, R, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.restore();
  }

  // ── the cabinet ──────────────────────────────────────────────────────
  function rrect(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function chrome(x0, y0, x1, y1) {
    const g = ctx.createLinearGradient(x0, y0, x1, y1);
    g.addColorStop(0, '#f4f6f7'); g.addColorStop(0.25, '#9aa3aa'); g.addColorStop(0.5, '#eef1f3'); g.addColorStop(0.75, '#7d868e'); g.addColorStop(1, '#dfe4e7');
    return g;
  }
  function drawCabinet() {
    const { cw, ch, u } = L;
    const g = ctx.createLinearGradient(0, 0, 0, ch);
    g.addColorStop(0, '#f6913a'); g.addColorStop(0.5, ORANGE); g.addColorStop(1, '#d9661a');
    ctx.fillStyle = g; ctx.fillRect(0, 0, cw, ch);
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = u * 0.004; rrect(u * 0.01, u * 0.01, cw - u * 0.02, ch - u * 0.02, u * 0.03); ctx.stroke();
  }
  function drawBezel() {
    const { pf, u } = L, b = u * 0.012;
    ctx.lineWidth = b; ctx.strokeStyle = chrome(pf.x, pf.y, pf.x + pf.w, pf.y + pf.h);
    rrect(pf.x - b / 2, pf.y - b / 2, pf.w + b, pf.h + b, u * 0.018); ctx.stroke();
    ctx.lineWidth = u * 0.002; ctx.strokeStyle = INK; rrect(pf.x - b, pf.y - b, pf.w + 2 * b, pf.h + 2 * b, u * 0.022); ctx.stroke();
  }
  function drawRailAndDecals(t, night) {
    const { pf, rail, u } = L;
    // the board outside the rail: a cream printed surface with corner fans
    ctx.save();
    ctx.beginPath(); ctx.rect(pf.x, pf.y, pf.w, pf.h); ctx.arc(rail.cx, rail.cy, rail.r, 0, Math.PI * 2, true); ctx.clip('evenodd');
    ctx.fillStyle = 'rgba(251,243,220,0.80)'; ctx.fillRect(pf.x, pf.y, pf.w, pf.h);
    const fans = [[pf.x, pf.y, 0], [pf.x + pf.w, pf.y, Math.PI / 2], [pf.x + pf.w, pf.y + pf.h, Math.PI], [pf.x, pf.y + pf.h, -Math.PI / 2]];
    const cols = ['#e5602a', '#a8c94a', '#f2b33d', '#3f97b5'];
    for (const [fx, fy, rot] of fans) {
      ctx.save(); ctx.translate(fx, fy); ctx.rotate(rot);
      const R = Math.min(pf.w, pf.h) * 0.19;
      for (let k = 0; k < 7; k++) {
        ctx.fillStyle = cols[k % 4]; ctx.strokeStyle = INK; ctx.lineWidth = u * 0.0025;
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, R * (k % 2 ? 0.86 : 1), k * Math.PI / 14, (k + 1) * Math.PI / 14); ctx.closePath(); ctx.fill(); ctx.stroke();
      }
      ctx.fillStyle = CREAM; ctx.beginPath(); ctx.arc(0, 0, R * 0.42, 0, Math.PI / 2); ctx.lineTo(0, 0); ctx.closePath(); ctx.fill(); ctx.stroke();
      // a jewel lamp that lights at night
      const jx = R * 0.62, jy = R * 0.62, jr = R * 0.09;
      ctx.fillStyle = night > 0.3 ? `hsl(${(rot * 57 + 20) % 360},95%,${55 + 15 * Math.sin(t * 2 + rot)}%)` : '#c0392b';
      ctx.beginPath(); ctx.arc(jx * 0.72, jy * 0.72, jr, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.restore();
    }
    ctx.restore();
    // the chrome rail, with its toothed lower arcs
    ctx.save();
    ctx.lineWidth = u * 0.011; ctx.strokeStyle = chrome(rail.cx - rail.r, rail.cy - rail.r, rail.cx + rail.r, rail.cy + rail.r);
    ctx.beginPath(); ctx.arc(rail.cx, rail.cy, rail.r, 0, Math.PI * 2); ctx.stroke();
    ctx.lineWidth = u * 0.002; ctx.strokeStyle = INK;
    ctx.beginPath(); ctx.arc(rail.cx, rail.cy, rail.r + u * 0.0065, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(rail.cx, rail.cy, rail.r - u * 0.0065, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = 'rgba(42,29,20,0.55)'; ctx.lineWidth = u * 0.0018;
    for (let a = 0.18 * Math.PI; a < 0.82 * Math.PI; a += Math.PI / 140) {
      const r1 = rail.r - u * 0.009, r2 = rail.r - u * 0.019;
      ctx.beginPath(); ctx.moveTo(rail.cx + Math.cos(a) * r1, rail.cy + Math.sin(a) * r1); ctx.lineTo(rail.cx + Math.cos(a) * r2, rail.cy + Math.sin(a) * r2); ctx.stroke();
    }
    ctx.restore();
  }
  function drawPins(night, t) {
    const r = Math.max(2, 2.3 * L.s), R = L.rail;
    for (const [x, y, onRail] of pins) {
      const X = onRail ? R.cx + Math.cos(x) * R.r * y : L.ox + x * L.s, Y = onRail ? R.cy + Math.sin(x) * R.r * y : L.oy + y * L.s;
      if (onRail && Y < L.pf.y + r * 3) continue;
      ctx.fillStyle = 'rgba(42,29,20,0.35)'; ctx.beginPath(); ctx.arc(X + r * 0.5, Y + r * 0.6, r, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#b8954a'; ctx.beginPath(); ctx.arc(X, Y, r, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = night > 0.4 && ((x * 13 + y * 7 + Math.floor(t * 2)) % 11 === 0) ? '#fff6c8' : '#f3e2a4';
      ctx.beginPath(); ctx.arc(X - r * 0.3, Y - r * 0.3, r * 0.4, 0, Math.PI * 2); ctx.fill();
    }
  }
  function drawTray(strata, t) {
    const T = L.tray, u = L.u;
    // ribbed gold plate
    rrect(T.x, T.y, T.w, T.h, u * 0.02);
    const g = ctx.createLinearGradient(0, T.y, 0, T.y + T.h);
    g.addColorStop(0, '#ecd27a'); g.addColorStop(0.5, '#d8b447'); g.addColorStop(1, '#b8902c');
    ctx.fillStyle = g; ctx.fill(); ctx.lineWidth = u * 0.003; ctx.strokeStyle = INK; ctx.stroke();
    ctx.save(); rrect(T.x, T.y, T.w, T.h, u * 0.02); ctx.clip();
    ctx.strokeStyle = 'rgba(120,88,20,0.35)'; ctx.lineWidth = Math.max(1, u * 0.0015);
    for (let x = T.x; x < T.x + T.w; x += u * 0.007) { ctx.beginPath(); ctx.moveTo(x, T.y); ctx.lineTo(x, T.y + T.h); ctx.stroke(); }
    ctx.restore();
    // screws
    for (const [sx, sy] of [[T.x + u * 0.02, T.y + u * 0.02], [T.x + T.w - u * 0.02, T.y + u * 0.02], [T.x + u * 0.02, T.y + T.h - u * 0.02], [T.x + T.w - u * 0.02, T.y + T.h - u * 0.02]]) {
      ctx.fillStyle = chrome(sx - 5, sy - 5, sx + 5, sy + 5); ctx.beginPath(); ctx.arc(sx, sy, u * 0.008, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = INK; ctx.lineWidth = u * 0.0015; ctx.stroke(); ctx.beginPath(); ctx.moveTo(sx - u * 0.005, sy); ctx.lineTo(sx + u * 0.005, sy); ctx.stroke();
    }
    // speaker grille
    const gx = T.x + u * 0.06, gy = T.y + T.h * 0.22, gs = T.h * 0.56;
    L.grille = { x: gx, y: gy, w: gs, h: gs };           // the speaker: touch it for sound
    if (window.AlgoSound) AlgoSound.drawGrille(ctx, gx, gy, gs, u);
    else {
      rrect(gx, gy, gs, gs, u * 0.01); ctx.fillStyle = '#c9a63c'; ctx.fill(); ctx.strokeStyle = INK; ctx.lineWidth = u * 0.002; ctx.stroke();
      ctx.fillStyle = 'rgba(42,29,20,0.55)';
      for (let i = 1; i < 7; i++) for (let j = 1; j < 7; j++) { ctx.beginPath(); ctx.arc(gx + gs * i / 7, gy + gs * j / 7, u * 0.003, 0, Math.PI * 2); ctx.fill(); }
    }
    // nameplate (it is also a key: touch it to read about the machine)
    const nx = gx + gs + u * 0.04, nw = T.w * 0.2, nh = T.h * 0.38, ny = T.y + T.h * 0.31;
    L.nameplate = { x: nx, y: ny, w: nw, h: nh };
    rrect(nx, ny, nw, nh, nh / 2); ctx.fillStyle = CREAM; ctx.fill(); ctx.lineWidth = u * 0.004; ctx.strokeStyle = INK; ctx.stroke();
    rrect(nx + u * 0.005, ny + u * 0.005, nw - u * 0.01, nh - u * 0.01, nh / 2); ctx.lineWidth = u * 0.0015; ctx.stroke();
    ctx.fillStyle = INK; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    let fs = nh * 0.5; ctx.font = `${fs}px Righteous, sans-serif`;
    while (ctx.measureText('ALGOGENESIS').width > nw * 0.84 && fs > 6) { fs -= 1; ctx.font = `${fs}px Righteous, sans-serif`; }
    ctx.fillText('ALGOGENESIS', nx + nw / 2, ny + nh / 2 + fs * 0.05);
    ctx.textBaseline = 'alphabetic';
    // the fossil window: one column per epoch, the newest on the right
    const kl = keys.getBoundingClientRect().left * L.dpr;
    const wx = nx + nw + u * 0.04, ww = Math.max(u * 0.08, (kl > 0 ? kl - u * 0.03 : T.x + T.w * 0.64) - wx), wy = T.y + T.h * 0.18, wh = T.h * 0.64;
    L.fossilWin = { x: wx, y: wy, w: ww, h: wh };
    rrect(wx, wy, ww, wh, u * 0.01); ctx.fillStyle = '#1b130d'; ctx.fill(); ctx.lineWidth = u * 0.006; ctx.strokeStyle = chrome(wx, wy, wx + ww, wy + wh); ctx.stroke();
    ctx.save(); rrect(wx, wy, ww, wh, u * 0.01); ctx.clip();
    const imprints = window.AlgoFossils ? AlgoFossils.drawStrip.bind(null, ctx, wx, wy, ww, wh, t) : null;
    if (strata && strata.length) {
      ctx.globalAlpha = imprints ? 0.32 : 1;      // the strata lie behind the imprints, like layers of rock
      const n = strata.length, cwid = Math.max(2, Math.min(ww / Math.max(n, 40), u * 0.02)), pad = wh * 0.08, hh = wh - 2 * pad;
      for (let i = 0; i < n; i++) {
        const Ly = strata[i], x = wx + ww - (n - i) * cwid - u * 0.006;
        if (x + cwid < wx) continue;
        const tot = Ly.animals.reduce((a, b) => a + b.n, 0) || 1; let yy = wy + pad;
        for (const a of Ly.animals) {
          const hg = hh * 0.68 * a.n / tot, [hue, sat] = a.look;
          ctx.fillStyle = `hsl(${hue * 360},${30 + 65 * sat}%,55%)`; ctx.fillRect(x, yy, cwid - 1, hg); yy += hg;
        }
        const ptot = Ly.plants.reduce((a, b) => a + b.n, 0) || 1; yy += hh * 0.02;
        for (const p of Ly.plants) { const hg = hh * 0.3 * p.n / ptot; ctx.fillStyle = `hsl(${p.hue * 360},60%,62%)`; ctx.fillRect(x, yy, cwid - 1, hg); yy += hg; }
      }
      ctx.globalAlpha = 1;
    }
    if (imprints) imprints();
    ctx.restore();
    // glass glare
    ctx.fillStyle = 'rgba(255,255,255,0.08)'; ctx.beginPath(); ctx.moveTo(wx, wy); ctx.lineTo(wx + ww * 0.3, wy); ctx.lineTo(wx + ww * 0.15, wy + wh); ctx.lineTo(wx, wy + wh); ctx.closePath(); ctx.fill();
  }

  // ── cards behind the keys ────────────────────────────────────────────
  let openCard = null, cardTimer = null;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmt = n => (n == null ? '—' : Number(n).toLocaleString());
  const hueCss = h => `hsl(${h * 360},65%,55%)`;
  function renderCard(kind, refresh) {
    const h2 = card.querySelector('h2'), body = card.querySelector('.body');
    const d = live || {}, s = d.stats || {};
    let title = '', html = '';
    if (kind === 'world') {
      title = 'The world now';
      const gens = s.mean_generation != null ? Math.round(s.mean_generation) : null;
      html = `<table>
        <tr><td>World</td><td>${esc(d.name || '')}</td></tr>
        <tr><td>Days and nights</td><td>${fmt(Math.floor(d.day || 0))}</td></tr>
        <tr><td>Generations</td><td>${fmt(gens)}</td></tr>
        <tr><td>Epochs in the fossil record</td><td>${fmt((d.strata || []).length)}</td></tr>
        <tr><td>Animals · species</td><td>${fmt(s.animals)} · ${fmt(s.animal_species)}</td></tr>
        <tr><td>Flowers · species</td><td>${fmt(s.plants)} · ${fmt(s.plant_species)}</td></tr>
        <tr><td>Body complexity, mean · most</td><td>${s.complexity_mean ?? '—'} · ${s.complexity_max ?? '—'}</td></tr>
        <tr><td>Colour · glow · choosiness</td><td>${s.colour_mean ?? '—'} · ${s.glow_mean ?? '—'} · ${s.choosy_mean ?? '—'}</td></tr>
        <tr><td>Hunters · pollinators</td><td>${Math.round((s.predators || 0) * 100)}% · ${Math.round((s.pollinators || 0) * 100)}%</td></tr>
        <tr><td>On land</td><td>${Math.round((s.on_land || 0) * 100)}%</td></tr>
        <tr><td>Pollinations so far</td><td>${fmt(s.pollinations)}</td></tr></table>
        <p class="note" style="margin-top:1.6vmin">${(d.events || []).slice(-4).reverse().map(e => `Day ${fmt(Math.floor(e.day))}: ${esc(e.text)}`).join('<br>')}</p>`;
    } else if (kind === 'journal') {
      title = 'The journal';
      if (!refresh || !body.dataset.loaded) {
        getJSON('/chronicle?n=40').then(rows => {
          if (openCard !== 'journal') return;
          body.dataset.loaded = '1';
          body.innerHTML = rows.map(r => `<div class="entry"><b>Day ${fmt(Math.floor(r.day))}${r.kind === 'genesis' ? ' · genesis' : ''}</b><p>${esc(r.text)}</p></div>`).join('') || '<p class="note">The first entry is written at the end of the first epoch.</p>';
        }).catch(() => {});
        html = '<p class="note">Opening the journal…</p>';
      } else return;
    } else if (kind === 'fossils') {
      title = 'The fossil record';
      const last = (d.strata || []).slice(-1)[0];
      html = `<p class="note">The window in the tray lays down one column per epoch (twelve days and nights), newest on the right: the leading animals in their colours above, the leading flowers below.</p>` +
        (last ? `<p class="note"><b>The latest layer, day ${fmt(Math.floor(last.day))}</b></p><table>` +
          last.animals.map(a => `<tr><td><span class="sw" style="background:${hueCss(a.look[0])}"></span>${esc(a.name)}</td><td>${fmt(a.n)}</td></tr>`).join('') +
          last.plants.map(p => `<tr><td><span class="sw" style="background:${hueCss(p.hue)}"></span>${esc(p.name)} · ${Math.round(p.petals)} petals</td><td>${fmt(p.n)}</td></tr>`).join('') + '</table>'
          : '<p class="note">The first layer is laid down at the end of the first epoch.</p>');
    } else if (kind === 'families') {
      title = 'Families';
      html = `<p class="note">Young animals are born small and slow, and easy prey until they grow. A parent carrying the gene for care shares its food with the young that stay close and stands over them when a hunter comes; the young of caring parents follow them. On the board a dotted thread joins a youngster to the parent looking after it.</p>
        <p class="note">Care costs the parent food, so it spreads only if more of its young survive because of it.</p>
        <table><tr><td>Young animals</td><td>${Math.round((s.young || 0) * 100)}%</td></tr>
        <tr><td>Young with a living parent</td><td>${fmt(s.families)}</td></tr>
        <tr><td>Care, average gene</td><td>${s.care_mean ?? '—'}</td></tr></table>`;
    } else {
      title = 'Algogenesis';
      html = `<p class="note">A living world inside the cabinet. Nothing in it is scripted: every animal and flower is drawn from its own genes, and they change only when evolution pays for the change.</p>
        <p class="note">Flowers set seed only when an animal brings pollen from another flower of their kind, so flowers and pollinators evolve together. Mates are chosen by colour and display, which only animals in good condition can afford, and the same brightness makes them easier for hunters to find. By day colour shows; at night only light does.</p>
        <p class="note">Each species carries its own enemies, so no one kind can take over, and lost lineages can return from refugia after a crash.</p>
        <p class="note">About ${fmt(Math.round((s.mean_generation || 0) / Math.max(1, (d.tick || 1) / ((d.tps || 20) * 60))))} generations pass every hour here.</p>`;
    }
    h2.textContent = title;
    if (kind === 'about' && window.AlgoSound) html += '<h3 style="font:400 2.2vmin Righteous,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#b9560c;margin:2.4vmin 0 1vmin">What you hear</h3>' + AlgoSound.legend();
    if (html) { body.innerHTML = html; if (kind !== 'journal') delete body.dataset.loaded; }
  }
  function toggleCard(kind) {
    if (kind === 'fossils' && window.AlgoFossils) {   // the fossil record is a cabinet of its own
      closeCard();
      if (AlgoFossils.isOpen()) AlgoFossils.close(); else AlgoFossils.open();
      return;
    }
    if (window.AlgoFossils && AlgoFossils.isOpen()) AlgoFossils.close();
    document.querySelectorAll('.key').forEach(k => k.classList.toggle('on', k.dataset.card === kind && openCard !== kind));
    if (openCard === kind) { closeCard(); return; }
    openCard = kind; card.querySelector('.body').dataset.loaded = ''; renderCard(kind, false); card.classList.add('open');
    clearTimeout(cardTimer); cardTimer = setTimeout(closeCard, 60000);
  }
  function closeCard() { openCard = null; card.classList.remove('open'); document.querySelectorAll('.key').forEach(k => k.classList.remove('on')); }
  keys.addEventListener('click', e => { const b = e.target.closest('.key'); if (b) toggleCard(b.dataset.card); });
  card.querySelector('.x').onclick = closeCard;
  cv.addEventListener('click', e => {
    const x = e.clientX * L.dpr, y = e.clientY * L.dpr, n = L.nameplate, f = L.fossilWin;
    if (n && x > n.x && x < n.x + n.w && y > n.y && y < n.y + n.h) return toggleCard('about');
    const sg = L.grille;
    if (sg && window.AlgoSound && x > sg.x && x < sg.x + sg.w && y > sg.y && y < sg.y + sg.h) {
      if (AlgoSound.toggle()) { feedSound(live); showCard('Listening', AlgoSound.legend()); } else if (openCard === 'dial') closeCard();
      return;
    }
    if (f && x > f.x && x < f.x + f.w && y > f.y && y < f.y + f.h) return toggleCard('fossils');
    if (openCard) closeCard();
    if (window.AlgoFossils && AlgoFossils.isOpen()) AlgoFossils.close();
  });

  // ── the frame loop ───────────────────────────────────────────────────
  let smoothLight = 1;
  function frame() {
    requestAnimationFrame(frame);
    if (!L.cw) return;
    const now = performance.now(), t = now / 1000;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    drawCabinet();
    if (!terrain) { drawTray(null, t); return; }
    const sea = live ? live.sea : 0;
    if (!terrCanvas || Math.abs(terrSea - sea) > 0.004) buildTerrain(sea);
    smoothLight += ((live ? live.light : 1) - smoothLight) * 0.02;
    const night = Math.max(0, 1 - smoothLight);
    const pf = L.pf;
    ctx.save(); rrect(pf.x, pf.y, pf.w, pf.h, L.u * 0.018); ctx.clip();
    ctx.fillStyle = CREAM; ctx.fillRect(pf.x, pf.y, pf.w, pf.h);
    ctx.drawImage(terrCanvas, L.ox, L.oy, W * L.s, H * L.s);
    drawPins(night, t);
    drawPlants(now, t, smoothLight);
    const glowLayer = [];
    for (const o of [...animals.values()]) drawAnimal(o, now, t, smoothLight, glowLayer);
    drawFamilies(now);
    drawRailAndDecals(t, night);
    if (night > 0.01) { ctx.fillStyle = `rgba(14,10,40,${0.55 * night})`; ctx.fillRect(pf.x, pf.y, pf.w, pf.h); }
    drawGlow(glowLayer, smoothLight);
    ctx.restore();
    drawBezel();
    drawTray(live && live.strata, t);
    if (night > 0.01) { ctx.fillStyle = `rgba(14,10,40,${0.12 * night})`; ctx.fillRect(0, 0, L.cw, L.ch); }
  }

  // ── kiosk niceties ───────────────────────────────────────────────────
  let idle;
  addEventListener('pointermove', () => { document.body.classList.add('awake'); clearTimeout(idle); idle = setTimeout(() => document.body.classList.remove('awake'), 2500); });
  addEventListener('dblclick', () => { (document.documentElement.requestFullscreen || function () {}).call(document.documentElement); });
  if (navigator.wakeLock) navigator.wakeLock.request('screen').catch(() => {});
  if (document.fonts) document.fonts.ready.then(() => { terrCanvas = terrCanvas; });

  function feedSound(d) { if (window.AlgoSound && d) AlgoSound.feed(d); }
  if (window.AlgoSound) AlgoSound.init('coast');
  function showCard(title, html) {
    openCard = 'dial'; card.querySelector('h2').textContent = title; card.querySelector('.body').innerHTML = html;
    card.classList.add('open'); document.querySelectorAll('.key').forEach(k => k.classList.remove('on'));
    clearTimeout(cardTimer); cardTimer = setTimeout(closeCard, 60000);
  }
  if (window.AlgoFossils) {
    AlgoFossils.mount({ api: API,
      onOpen: () => document.querySelectorAll('.key').forEach(k => k.classList.toggle('on', k.dataset.card === 'fossils')),
      onClose: () => document.querySelectorAll('.key[data-card="fossils"]').forEach(k => k.classList.remove('on')) });
  }
  getJSON('/meta').then(m => { if (window.AlgoDials) { AlgoDials.mount({ container: keys, post: API + '/dial', dials: m.dials || [], show: showCard }); placeKeys(); } }).catch(() => {});

  resize();
  loadTerrain();
  poll();
  requestAnimationFrame(frame);
})();
