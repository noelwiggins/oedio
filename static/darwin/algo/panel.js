/* ALGOGENESIS panel renderer.
   Draws whatever the engine reports: every animal from its own genes (segments, legs, tail, crest, colour,
   pattern, glow), every flower from its own genes (petals, colours, height). Nothing here is decoration
   chosen by hand except the landscape palette and the type.
   Query options: ?quiet=1 hides the text, ?nochron=1 hides the journal, ?strata=0 hides the fossil band. */
(function () {
  'use strict';
  const API = (document.body.dataset.api && document.body.dataset.api.indexOf('__') !== 0) ? document.body.dataset.api : '/api';
  const Q = new URLSearchParams(location.search);
  const QUIET = Q.get('quiet') === '1', NOCHRON = Q.get('nochron') === '1', STRATA = Q.get('strata') !== '0';
  const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
  const veil = document.getElementById('veil');
  let W = 1200, H = 800, terrain = null, terrCanvas = null, terrSea = null;
  let view = { s: 1, ox: 0, oy: 0, cw: 0, ch: 0 };
  let live = null, lastFetch = 0;
  const animals = new Map(), plants = new Map();
  const LAG = 1100;                          // ms behind the newest frame, so motion is always interpolated
  let chron = [], chronIdx = 0, chronAt = 0;

  // ── layout ───────────────────────────────────────────────────────────
  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(innerWidth * dpr); cv.height = Math.round(innerHeight * dpr);
    const s = Math.min(cv.width / W, cv.height / H);
    view = { s, ox: (cv.width - W * s) / 2, oy: (cv.height - H * s) / 2, cw: cv.width, ch: cv.height, dpr };
    terrCanvas = null;
    flowerCache.clear();
  }
  addEventListener('resize', resize);

  // ── data ─────────────────────────────────────────────────────────────
  async function getJSON(u) { const r = await fetch(API + u, { cache: 'no-store' }); return r.json(); }

  async function loadTerrain() {
    const t = await getJSON('/terrain');
    if (t.standby) { setTimeout(loadTerrain, 4000); return; }
    terrain = t; W = t.w; H = t.h; resize();
  }

  async function poll() {
    try {
      const d = await getJSON('/live');
      if (!d.standby) ingest(d);
    } catch (e) { /* the panel keeps drawing the last world it saw */ }
    setTimeout(poll, 700);
  }

  function ingest(d) {
    const now = performance.now();
    if (live && d.tick === live.tick) return;
    live = d; lastFetch = now;
    const seen = new Set();
    for (const a of d.animals) {
      const [id, x, y, h, sp, ...look] = a;
      seen.add(id);
      let o = animals.get(id);
      if (!o) { o = { id, x0: x, y0: y, h0: h, x1: x, y1: y, h1: h, t0: now, t1: now, born: now, look, sp, phase: Math.random() * 6.28 }; animals.set(id, o); }
      else { const p = pos(o, now); o.x0 = p.x; o.y0 = p.y; o.h0 = p.h; o.x1 = x; o.y1 = y; o.h1 = h; o.t0 = now; o.t1 = now + LAG; o.look = look; o.dead = 0; }
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
    if (d.chronicle && d.chronicle.length) {
      const fresh = d.chronicle.map(c => c.text).join('|') !== chron.map(c => c.text).join('|');
      if (fresh) { chron = d.chronicle.slice(0, 6); chronIdx = 0; chronAt = now; }
    }
    veil.classList.add('gone');
  }

  function pos(o, now) {
    const f = o.t1 > o.t0 ? Math.min(1, Math.max(0, (now - o.t0) / (o.t1 - o.t0))) : 1;
    let dh = o.h1 - o.h0; dh = ((dh + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
    return { x: o.x0 + (o.x1 - o.x0) * f, y: o.y0 + (o.y1 - o.y0) * f, h: o.h0 + dh * f, moving: Math.hypot(o.x1 - o.x0, o.y1 - o.y0) / Math.max(1, (o.t1 - o.t0) / 1000) };
  }

  // ── the landscape ────────────────────────────────────────────────────
  const STOPS = [   // height above sea → colour (deep water to highland)
    [-1.0, [4, 12, 26]], [-0.45, [7, 26, 46]], [-0.18, [12, 52, 70]], [-0.05, [26, 92, 100]], [-0.005, [58, 132, 128]],
    [0.0, [196, 182, 140]], [0.03, [168, 160, 112]], [0.08, [92, 116, 70]], [0.25, [62, 92, 56]], [0.5, [92, 96, 70]],
    [0.75, [128, 120, 98]], [1.2, [176, 170, 156]]];
  function ramp(v) {
    for (let i = 1; i < STOPS.length; i++) if (v <= STOPS[i][0]) {
      const [a, ca] = STOPS[i - 1], [b, cb] = STOPS[i], f = (v - a) / (b - a);
      return [ca[0] + (cb[0] - ca[0]) * f, ca[1] + (cb[1] - ca[1]) * f, ca[2] + (cb[2] - ca[2]) * f];
    }
    return STOPS[STOPS.length - 1][1];
  }
  function hAt(x, y) {          // bilinear height in world units
    const gx = x / W * terrain.gx - 0.5, gy = y / H * terrain.gy - 0.5;
    const x0 = Math.max(0, Math.min(terrain.gx - 1, Math.floor(gx))), y0 = Math.max(0, Math.min(terrain.gy - 1, Math.floor(gy)));
    const x1 = Math.min(terrain.gx - 1, x0 + 1), y1 = Math.min(terrain.gy - 1, y0 + 1);
    const fx = Math.max(0, Math.min(1, gx - x0)), fy = Math.max(0, Math.min(1, gy - y0)), T = terrain.h_, n = terrain.gx;
    return (T[y0 * n + x0] * (1 - fx) + T[y0 * n + x1] * fx) * (1 - fy) + (T[y1 * n + x0] * (1 - fx) + T[y1 * n + x1] * fx) * fy;
  }
  function buildTerrain(sea) {
    const ts = Math.min(view.s, 1600 / W);            // the land is smooth, so it needs no more than ~1600 px
    const tw = Math.round(W * ts), th = Math.round(H * ts);
    const c = document.createElement('canvas'); c.width = tw; c.height = th;
    const g = c.getContext('2d'), img = g.createImageData(tw, th), D = img.data;
    const step = 1 / ts;
    for (let py = 0; py < th; py++) {
      for (let px = 0; px < tw; px++) {
        const wx = px * step, wy = py * step, h = hAt(wx, wy), d = h - sea;
        // light from the north-west: a little relief shading
        const hx = hAt(wx + 4, wy) - hAt(wx - 4, wy), hy = hAt(wx, wy + 4) - hAt(wx, wy - 4);
        const shade = d > 0 ? Math.max(0.72, Math.min(1.25, 1 - (hx + hy) * 6)) : 1 + Math.max(-0.1, Math.min(0.1, -(hx + hy) * 2));
        const col = ramp(d);
        const contour = d > 0 && Math.abs(((d * 14) % 1 + 1) % 1 - 0.5) > 0.47 ? 0.9 : 1;     // faint survey contours
        const k = (py * tw + px) * 4;
        D[k] = col[0] * shade * contour; D[k + 1] = col[1] * shade * contour; D[k + 2] = col[2] * shade * contour; D[k + 3] = 255;
      }
    }
    g.putImageData(img, 0, 0);
    terrCanvas = c; terrSea = sea;
  }

  // ── flowers: drawn once per kind, then stamped ───────────────────────
  const flowerCache = new Map();
  function flowerSprite(p, open) {
    const key = `${Math.round(p.hue * 40)}|${p.petals}|${Math.round(p.sat * 4)}|${Math.round(p.hue2 * 10)}|${open ? 1 : 0}`;
    let s = flowerCache.get(key);
    if (s) return s;
    const R = Math.max(6, Math.round(5.5 * view.s * 1.6));
    s = document.createElement('canvas'); s.width = s.height = R * 2 + 4;
    const g = s.getContext('2d'); g.translate(R + 2, R + 2);
    const hue = p.hue * 360, L = 58 + 10 * (1 - p.sat), S = 35 + 60 * p.sat;
    const n = p.petals, pr = open ? R : R * 0.55;
    for (let i = 0; i < n; i++) {
      g.save(); g.rotate(i / n * Math.PI * 2);
      const grd = g.createLinearGradient(0, 0, pr, 0);
      grd.addColorStop(0, `hsla(${hue},${S}%,${L - 18}%,0.95)`); grd.addColorStop(1, `hsla(${hue},${S}%,${L + 8}%,0.95)`);
      g.fillStyle = grd; g.beginPath(); g.ellipse(pr * 0.52, 0, pr * 0.5, pr * (open ? 0.24 : 0.16) * (1 + 3 / n), 0, 0, Math.PI * 2); g.fill();
      g.restore();
    }
    g.fillStyle = `hsl(${p.hue2 * 360},70%,${open ? 62 : 45}%)`; g.beginPath(); g.arc(0, 0, R * 0.2, 0, Math.PI * 2); g.fill();
    flowerCache.set(key, s);
    return s;
  }

  // ── animals ──────────────────────────────────────────────────────────
  // look = [hue, sat, hue2, pattern, glow, segs, limbs, size, tail, crest, fin, diet]
  function drawAnimal(o, now, t, light, glowLayer) {
    const p = pos(o, now);
    const [hue, sat, hue2, pattern, glow, segs, limbs, size, tail, crest, fin, diet] = o.look;
    let alpha = Math.min(1, (now - o.born) / 900);
    if (o.dead) { alpha = Math.max(0, 1 - (now - o.dead) / 1200); if (alpha <= 0) { animals.delete(o.id); return; } }
    const s = view.s, X = view.ox + p.x * s, Y = view.oy + p.y * s;
    const r0 = (1.6 + 1.6 * size) * s * 1.55, gap = r0 * 1.05;
    const speedPhase = t * (2.5 + Math.min(4, p.moving * 0.25)) + o.phase;
    // a spine trailing behind the head, swaying like a swimmer (or stepping like a walker)
    const pts = [];
    let ang = p.h + Math.PI, cx = X, cy = Y;
    for (let i = 0; i < segs; i++) {
      const r = r0 * (1 - 0.55 * i / Math.max(segs, 2)) * (i === 0 ? 1.05 : 1);
      pts.push([cx, cy, r, ang]);
      ang = p.h + Math.PI + Math.sin(speedPhase - i * 0.9) * 0.28 * (fin > 0.5 ? 1 : 0.4) * Math.min(1, i / 2 + 0.3);
      cx += Math.cos(ang) * gap; cy += Math.sin(ang) * gap;
    }
    const L = 42 + 18 * (1 - sat), S = 18 + 72 * sat;
    const base = `hsla(${hue * 360},${S}%,${L}%,${alpha})`, alt = `hsla(${hue2 * 360},${Math.max(40, S)}%,${Math.min(72, L + 10)}%,${alpha})`;
    ctx.lineCap = 'round';
    // legs
    if (limbs > 0) {
      ctx.strokeStyle = `hsla(${hue * 360},${S * 0.6}%,${L - 14}%,${alpha})`; ctx.lineWidth = Math.max(1, r0 * 0.28);
      for (let k = 0; k < limbs; k++) {
        const i = Math.min(pts.length - 1, Math.round((k + 0.5) * pts.length / limbs - 0.5));
        const [px, py, r, a] = pts[i], step = Math.sin(speedPhase * 1.6 + k * 1.7) * 0.5;
        for (const side of [-1, 1]) {
          const la = a + side * (Math.PI / 2 + step * side), len = r * 2.1;
          ctx.beginPath(); ctx.moveTo(px, py);
          ctx.lineTo(px + Math.cos(la) * len * 0.6, py + Math.sin(la) * len * 0.6);
          ctx.lineTo(px + Math.cos(la + 0.6 * side) * len, py + Math.sin(la + 0.6 * side) * len); ctx.stroke();
        }
      }
    }
    // tail fin
    const last = pts[pts.length - 1];
    if (tail > 0.15) {
      const [tx, ty, r, a] = last, tl = r0 * (1.2 + 3 * tail), spread = 0.35 + 0.4 * fin;
      ctx.fillStyle = `hsla(${hue2 * 360},${S}%,${L + 6}%,${alpha * 0.85})`;
      ctx.beginPath(); ctx.moveTo(tx, ty);
      ctx.lineTo(tx + Math.cos(a - spread) * tl, ty + Math.sin(a - spread) * tl);
      ctx.quadraticCurveTo(tx + Math.cos(a) * tl * 0.6, ty + Math.sin(a) * tl * 0.6, tx + Math.cos(a + spread) * tl, ty + Math.sin(a + spread) * tl);
      ctx.closePath(); ctx.fill();
    }
    // body: back to front so the head sits on top
    for (let i = pts.length - 1; i >= 0; i--) {
      const [px, py, r] = pts[i];
      const striped = pattern > 0.33 && pattern <= 0.66 && i % 2 === 1;
      ctx.fillStyle = striped ? alt : base;
      ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `rgba(255,255,255,${0.16 * alpha})`;
      ctx.beginPath(); ctx.arc(px - r * 0.3, py - r * 0.3, r * 0.5, 0, Math.PI * 2); ctx.fill();
      if (pattern > 0.66 && r > 2) {
        ctx.fillStyle = alt;
        ctx.beginPath(); ctx.arc(px + r * 0.35, py - r * 0.25, r * 0.28, 0, Math.PI * 2); ctx.arc(px - r * 0.3, py + r * 0.3, r * 0.22, 0, Math.PI * 2); ctx.fill();
      }
    }
    // crest: spines along the back
    if (crest > 0.25) {
      ctx.strokeStyle = alt; ctx.lineWidth = Math.max(1, r0 * 0.18);
      for (let i = 0; i < pts.length; i++) {
        const [px, py, r, a] = pts[i], nrm = a + Math.PI / 2, len = r * (0.6 + 1.6 * crest);
        ctx.beginPath(); ctx.moveTo(px + Math.cos(nrm) * r * 0.7, py + Math.sin(nrm) * r * 0.7);
        ctx.lineTo(px + Math.cos(nrm) * (r + len), py + Math.sin(nrm) * (r + len)); ctx.stroke();
      }
    }
    // eyes, and a mouth for hunters
    const [hx, hy, hr] = pts[0];
    for (const side of [-0.55, 0.55]) {
      const ea = p.h + side;
      ctx.fillStyle = `rgba(12,14,20,${alpha * 0.85})`; ctx.beginPath(); ctx.arc(hx + Math.cos(ea) * hr * 0.62, hy + Math.sin(ea) * hr * 0.62, Math.max(0.6, hr * 0.14), 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `rgba(255,255,255,${alpha * 0.7})`; ctx.beginPath(); ctx.arc(hx + Math.cos(ea) * hr * 0.6 - hr * 0.04, hy + Math.sin(ea) * hr * 0.6 - hr * 0.05, Math.max(0.3, hr * 0.05), 0, Math.PI * 2); ctx.fill();
    }
    if (diet > 0.6) {
      ctx.strokeStyle = `rgba(255,236,220,${alpha * 0.8})`; ctx.lineWidth = Math.max(0.8, hr * 0.15);
      ctx.beginPath(); ctx.arc(hx + Math.cos(p.h) * hr * 0.75, hy + Math.sin(p.h) * hr * 0.75, hr * 0.35, p.h - 1.0, p.h + 1.0); ctx.stroke();
    }
    if (glow > 0.12 && light < 0.85) glowLayer.push([pts, hue, glow, alpha, t + o.phase]);
  }

  function drawGlow(list, light) {
    if (!list.length) return;
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    const dark = Math.min(1, (0.85 - light) / 0.6);
    for (const [pts, hue, glow, alpha, ph] of list) {
      const pulse = 0.75 + 0.25 * Math.sin(ph * 1.7);
      for (let i = 0; i < pts.length; i++) {
        const [px, py, r] = pts[i], R = r * (2.5 + 5 * glow) * pulse;
        const g = ctx.createRadialGradient(px, py, 0, px, py, R);
        g.addColorStop(0, `hsla(${hue * 360},90%,70%,${0.55 * glow * alpha * dark})`);
        g.addColorStop(1, `hsla(${hue * 360},90%,50%,0)`);
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(px, py, R, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.restore();
  }

  // ── plants ───────────────────────────────────────────────────────────
  function drawPlants(now, t, light) {
    const s = view.s, open = light > 0.25;
    const list = [...plants.values()].sort((a, b) => a.y - b.y);
    for (const p of list) {
      let a = Math.min(1, (now - p.born) / 1500);
      if (p.dead) { a = Math.max(0, 1 - (now - p.dead) / 1500); if (a <= 0) { plants.delete(p.id); continue; } }
      const X = view.ox + p.x * s, Y = view.oy + p.y * s;
      const sway = Math.sin(t * 0.9 + p.x * 0.05) * 0.12;
      const hgt = (4 + 9 * p.height) * s * Math.min(1, a + 0.2);
      const tipx = X + Math.sin(sway) * hgt, tipy = Y - Math.cos(sway) * hgt;
      ctx.globalAlpha = a;
      ctx.strokeStyle = `rgba(48,${78 + 30 * p.sat},44,0.9)`; ctx.lineWidth = Math.max(1, 0.55 * s);
      ctx.beginPath(); ctx.moveTo(X, Y); ctx.quadraticCurveTo(X + sway * hgt * 0.3, Y - hgt * 0.5, tipx, tipy); ctx.stroke();
      ctx.fillStyle = 'rgba(64,102,52,0.85)';
      ctx.beginPath(); ctx.ellipse(X + 1.6 * s, Y - hgt * 0.35, 1.8 * s, 0.7 * s, -0.6 + sway, 0, Math.PI * 2); ctx.fill();
      const spr = flowerSprite(p, open);
      const k = (0.45 + 0.4 * p.size) * (0.7 + 0.3 * p.nectar) / 1.6;
      const w = spr.width * k;
      ctx.drawImage(spr, tipx - w / 2, tipy - w / 2, w, w);
    }
    ctx.globalAlpha = 1;
  }

  // ── the fossil record: a band along the bottom, one column per epoch ─
  function drawStrata(strata) {
    if (!STRATA || !strata || !strata.length) return 0;
    const bandH = Math.round(view.ch * 0.075), y0 = view.ch - bandH, x0 = view.ox, w = W * view.s;
    const grd = ctx.createLinearGradient(0, y0 - bandH * 0.6, 0, view.ch);
    grd.addColorStop(0, 'rgba(2,4,7,0)'); grd.addColorStop(0.4, 'rgba(2,4,7,0.82)'); grd.addColorStop(1, 'rgba(2,4,7,0.95)');
    ctx.fillStyle = grd; ctx.fillRect(x0, y0 - bandH * 0.6, w, bandH * 1.6);
    const n = strata.length, cw = Math.min(w / Math.max(n, 60), 14), top = y0 + bandH * 0.18, hh = bandH * 0.62;
    for (let i = 0; i < n; i++) {
      const L = strata[i], x = x0 + w - (n - i) * cw;
      const tot = L.animals.reduce((a, b) => a + b.n, 0) || 1;
      let yy = top;
      for (const a of L.animals) {
        const hgt = hh * 0.7 * a.n / tot, [hue, sat, , , glow] = a.look;
        ctx.fillStyle = `hsl(${hue * 360},${20 + 70 * sat}%,${40 + 30 * glow}%)`; ctx.fillRect(x, yy, cw - 1, hgt); yy += hgt;
      }
      const ptot = L.plants.reduce((a, b) => a + b.n, 0) || 1;
      for (const p of L.plants) {
        const hgt = hh * 0.3 * p.n / ptot;
        ctx.fillStyle = `hsl(${p.hue * 360},55%,58%)`; ctx.fillRect(x, yy, cw - 1, hgt); yy += hgt;
      }
    }
    if (!QUIET) {
      ctx.fillStyle = 'rgba(190,205,205,0.55)'; ctx.font = `${Math.round(bandH * 0.15)}px "IBM Plex Mono", monospace`;
      ctx.textAlign = 'left'; ctx.fillText('THE FOSSIL RECORD · ONE LAYER PER EPOCH · LEADING ANIMALS ABOVE, FLOWERS BELOW', x0 + 14, view.ch - bandH * 0.08);
    }
    return bandH;
  }

  // ── words ────────────────────────────────────────────────────────────
  function wrap(text, maxW) {
    const words = text.split(/\s+/), lines = []; let line = '';
    for (const w of words) { const t = line ? line + ' ' + w : w; if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; } else line = t; }
    if (line) lines.push(line);
    return lines;
  }
  function drawText(now, bandH) {
    if (QUIET || !live) return;
    const s = view.ch / 1000, x0 = view.ox + 34 * s * 1.4, st = live.stats || {};
    ctx.textAlign = 'left';
    ctx.fillStyle = 'rgba(232,236,228,0.9)'; ctx.font = `500 ${Math.round(30 * s)}px "Cormorant Garamond", Georgia, serif`;
    ctx.fillText('Algogenesis', x0, view.oy + 56 * s);
    ctx.fillStyle = 'rgba(200,212,208,0.7)'; ctx.font = `${Math.round(13 * s)}px "IBM Plex Mono", monospace`;
    const day = Math.floor(live.day || 0).toLocaleString();
    ctx.fillText(`${(live.name || '').toUpperCase()} · DAY ${day} · EPOCH ${(live.strata || []).length}`, x0, view.oy + 80 * s);
    ctx.fillText(`${st.animals || 0} ANIMALS · ${st.animal_species || 0} SPECIES · ${st.plants || 0} FLOWERS`, x0, view.oy + 100 * s);
    if (NOCHRON || !chron.length) return;
    if (now - chronAt > 45000) { chronIdx = (chronIdx + 1) % chron.length; chronAt = now; }
    const c = chron[chronIdx], age = (now - chronAt) / 1000, fade = Math.min(1, age / 2, (45 - age) / 2);
    const boxW = Math.min(W * view.s * 0.36, 620 * s * 1.3);
    ctx.font = `italic ${Math.round(19 * s)}px "Cormorant Garamond", Georgia, serif`;
    const lines = wrap(c.text, boxW), lh = 24 * s;
    const bx = view.ox + W * view.s - boxW - 34 * s * 1.4, by = view.ch - bandH - 26 * s - lines.length * lh;
    ctx.fillStyle = `rgba(4,8,12,${0.42 * fade})`;
    ctx.fillRect(bx - 16 * s, by - 34 * s, boxW + 32 * s, lines.length * lh + 46 * s);
    ctx.fillStyle = `rgba(200,212,208,${0.65 * fade})`; ctx.font = `${Math.round(11.5 * s)}px "IBM Plex Mono", monospace`;
    ctx.fillText(`FROM THE JOURNAL · DAY ${Math.floor(c.day).toLocaleString()}`, bx, by - 12 * s);
    ctx.fillStyle = `rgba(236,232,220,${0.92 * fade})`; ctx.font = `italic ${Math.round(19 * s)}px "Cormorant Garamond", Georgia, serif`;
    lines.forEach((l, i) => ctx.fillText(l, bx, by + 8 * s + i * lh));
  }

  // ── the frame loop ───────────────────────────────────────────────────
  let smoothLight = 1;
  function frame(nowMs) {
    requestAnimationFrame(frame);
    if (!terrain) return;
    const now = performance.now(), t = now / 1000;
    const sea = live ? live.sea : 0;
    if (!terrCanvas || Math.abs(terrSea - sea) > 0.004) buildTerrain(sea);
    const light = live ? live.light : 1;
    smoothLight += (light - smoothLight) * 0.02;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#020407'; ctx.fillRect(0, 0, view.cw, view.ch);
    ctx.save();
    ctx.beginPath(); ctx.rect(view.ox, view.oy, W * view.s, H * view.s); ctx.clip();
    ctx.drawImage(terrCanvas, view.ox, view.oy, W * view.s, H * view.s);
    // the sea moves: slow bands of light across the water
    ctx.save(); ctx.globalCompositeOperation = 'soft-light';
    for (let k = 0; k < 3; k++) {
      const yy = view.oy + ((t * 6 * (k + 1) + k * 260) % (H + 200) - 100) * view.s;
      const g = ctx.createLinearGradient(0, yy - 60 * view.s, 0, yy + 60 * view.s);
      g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(0.5, `rgba(180,230,255,${0.10 * smoothLight})`); g.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = g; ctx.fillRect(view.ox, yy - 60 * view.s, W * view.s, 120 * view.s);
    }
    ctx.restore();
    drawPlants(now, t, smoothLight);
    const glowLayer = [];
    for (const o of [...animals.values()]) drawAnimal(o, now, t, smoothLight, glowLayer);
    // night falls: a cool veil, then everything that glows shows through it
    const night = Math.max(0, 1 - smoothLight);
    if (night > 0.01) {
      ctx.fillStyle = `rgba(3,8,26,${0.72 * night})`; ctx.fillRect(view.ox, view.oy, W * view.s, H * view.s);
      ctx.save(); ctx.globalCompositeOperation = 'lighter';
      for (const p of plants.values()) {          // flowers holding nectar give off a faint light at night
        if (p.nectar > 0.6 && ((p.id * 7) % 5 === 0)) {
          const X = view.ox + p.x * view.s, Y = view.oy + (p.y - 8 * p.height) * view.s;
          ctx.fillStyle = `hsla(${p.hue * 360},70%,60%,${0.05 * night})`; ctx.beginPath(); ctx.arc(X, Y, 6 * view.s, 0, Math.PI * 2); ctx.fill();
        }
      }
      ctx.restore();
    }
    drawGlow(glowLayer, smoothLight);
    // a soft vignette
    const vg = ctx.createRadialGradient(view.cw / 2, view.ch / 2, Math.min(view.cw, view.ch) * 0.35, view.cw / 2, view.ch / 2, Math.max(view.cw, view.ch) * 0.75);
    vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,0.45)');
    ctx.fillStyle = vg; ctx.fillRect(view.ox, view.oy, W * view.s, H * view.s);
    ctx.restore();
    const bandH = drawStrata(live && live.strata);
    drawText(now, bandH);
  }

  // ── kiosk niceties: hide the cursor, offer full screen on movement ───
  let idle;
  addEventListener('mousemove', () => { document.body.classList.add('awake'); clearTimeout(idle); idle = setTimeout(() => document.body.classList.remove('awake'), 2500); });
  document.getElementById('fs').onclick = () => { (document.documentElement.requestFullscreen || function () {}).call(document.documentElement); };
  if (navigator.wakeLock) navigator.wakeLock.request('screen').catch(() => {});

  resize();
  loadTerrain();
  poll();
  requestAnimationFrame(frame);
})();
