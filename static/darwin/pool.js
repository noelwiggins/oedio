/* The tidal pool renderer (life-3.0): draws every creature from its developmental body plan, inside a
   landscape you can zoom out to: open ocean, the simulated bay (open sea · reef shallows · tidal flats),
   beach, land and sky. Nothing about the creatures is invented client-side: positions come from the
   server's frames and bodies from the plans the simulation grew. The landscape outside the bay is scenery
   until life reaches it (land and air are not simulated yet). */
(function () {
  const D = window.Darwin;
  const CELL_COLORS = {
    0: [196, 184, 160],   // skin
    1: [92, 201, 120],    // photo
    2: [235, 96, 82],     // mouth
    3: [235, 235, 245],   // flagellum
    4: [40, 40, 60],      // eye
    5: [140, 150, 165],   // armour
    6: [233, 191, 109],   // store
    7: [170, 120, 235],   // neuron
    8: [240, 140, 190],   // gonad
  };
  D.CELL_COLORS = CELL_COLORS;
  D.CELL_LABELS = ['skin', 'photo', 'mouth', 'flagellum', 'eye', 'armour', 'store', 'neuron', 'gonad'];

  D.geo = function (ma) {
    if (ma == null) return '—';
    if (ma >= 1000) return (ma / 1000).toFixed(3) + ' billion years';
    if (ma >= 1) return ma.toFixed(ma >= 100 ? 0 : 1) + ' million years';
    return Math.round(ma * 1000).toLocaleString() + ' thousand years';
  };

  /* Draw one body plan centred at (cx, cy), rotated by heading `hd` (radians), `u` px per cell. */
  D.drawBody = function (ctx, cells, cx, cy, hd, u, hue, alpha) {
    const c = Math.cos(hd), s = Math.sin(hd);
    const r = Math.max(0.9, u * 0.5);
    cells.forEach(([dx, dy, t]) => {
      const x = cx + (dx * c - dy * s) * u, y = cy + (dx * s + dy * c) * u;
      let col = CELL_COLORS[t];
      if (t === 0) col = hsl(hue, 0.35, 0.68);
      ctx.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},${alpha})`;
      if (t === 3) {
        ctx.strokeStyle = ctx.fillStyle; ctx.lineWidth = Math.max(1, u * 0.25);
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - c * u * 1.1, y - s * u * 1.1); ctx.stroke();
        ctx.beginPath(); ctx.arc(x, y, r * 0.55, 0, 7); ctx.fill();
      } else if (t === 4) {
        ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
        ctx.strokeStyle = `rgba(255,255,255,${0.8 * alpha})`; ctx.lineWidth = Math.max(0.6, u * 0.18);
        ctx.beginPath(); ctx.arc(x, y, r * 0.85, 0, 7); ctx.stroke();
      } else if (t === 5) {
        ctx.fillRect(x - r, y - r, r * 2, r * 2);
      } else {
        ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
      }
    });
  };

  function hsl(h, s, l) {
    h = ((h % 360) + 360) % 360 / 360;
    const f = n => { const k = (n + h * 12) % 12, a = s * Math.min(l, 1 - l); return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)); };
    return [Math.round(f(0) * 255), Math.round(f(8) * 255), Math.round(f(4) * 255)];
  }
  D.hsl = hsl;

  D.bodyThumb = function (canvas, cells, hue) {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = canvas.clientWidth || 64, h = canvas.clientHeight || 64;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!cells || !cells.length) return;
    const xs = cells.map(c => c[0]), ys = cells.map(c => c[1]);
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) + 1;
    const u = Math.min(14, (Math.min(w, h) - 8) / span);
    const mx = (Math.max(...xs) + Math.min(...xs)) / 2, my = (Math.max(...ys) + Math.min(...ys)) / 2;
    D.drawBody(ctx, cells.map(([x, y, t]) => [x - mx, y - my, t]), w / 2, h / 2, 0, u, hue || 0, 1);
  };

  /* Open the realistic 3D viewer for a body plan (loaded on demand). */
  D.view3D = async function (info) {
    const mod = await import('/static/darwin/creature3d.js?v=3');
    mod.open(info);
  };

  // ── landscape ──────────────────────────────────────────────────────
  const LW = 960, LH = 720;            // landscape size in world units
  const BAY = { x: 300, y: 240, w: 240, h: 240 };   // the simulated arena sits on the coast
  function hash(x, y, s) { let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(s, 2147483647); h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; }
  function vnoise(x, y, s) {
    const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const a = hash(xi, yi, s), b = hash(xi + 1, yi, s), c = hash(xi, yi + 1, s), d = hash(xi + 1, yi + 1, s);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }
  function fbm(x, y, s, o) { let t = 0, a = 0.5, f = 1; for (let i = 0; i < (o || 5); i++) { t += a * vnoise(x * f, y * f, s + i); a *= 0.5; f *= 2; } return t; }
  function smooth(e0, e1, x) { const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0))); return t * t * (3 - 2 * t); }
  function coastX(y) {
    // exactly the bay's east edge inside the bay, a natural coastline elsewhere
    const off = (fbm(0.5, y / 90, 11, 4) - 0.5) * 120;
    const inBay = 1 - smooth(0, 70, Math.max(BAY.y - y, y - (BAY.y + BAY.h), 0));
    return BAY.x + BAY.w + (1 - inBay) * off;
  }
  let terrain = null, clouds = null;
  function buildTerrain() {
    const R = 1, w = LW * R, h = LH * R;
    const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
    const g = cv.getContext('2d'), img = g.createImageData(w, h), px = img.data;
    const coast = []; for (let j = 0; j < h; j++) coast.push(coastX(j / R));
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
      const x = i / R, y = j / R, d = coast[j] - x, k = (j * w + i) * 4;
      let r, gg, b;
      if (d > 0) {                      // water: deeper away from the coast
        const depth = smooth(0, 420, d), n = fbm(x / 60, y / 60, 3, 3);
        r = 18 + (1 - depth) * 40 + n * 10; gg = 60 + (1 - depth) * 95 + n * 14; b = 92 + (1 - depth) * 70 + n * 12;
        if (d < 240 && d > 80 && fbm(x / 14, y / 14, 7, 3) > 0.62) { r += 28; gg += 22; b -= 6; }   // reef patches
        if (d < 26) { r += 40 * (1 - d / 26); gg += 30 * (1 - d / 26); b += 6; }                    // surf
      } else {
        const inland = -d, elev = fbm(x / 160, y / 160, 21, 5) + inland / 900;
        if (inland < 34 + fbm(x / 20, y / 20, 5, 2) * 14) {   // beach
          const n = fbm(x / 9, y / 9, 9, 3); r = 214 + n * 20; gg = 192 + n * 18; b = 140 + n * 12;
        } else {
          const n = fbm(x / 25, y / 25, 13, 4);
          const e2 = fbm((x + 1.5) / 160, y / 160, 21, 5) - fbm((x - 1.5) / 160, y / 160, 21, 5);   // hillshade
          const shade = 1 + e2 * 18;
          r = (120 + elev * 70 + n * 30) * shade; gg = (102 + elev * 55 + n * 22) * shade; b = (78 + elev * 40 + n * 18) * shade;
          if (Math.abs(fbm(x / 70, y / 70, 31, 4) - 0.5) < 0.012) { r *= 0.72; gg *= 0.7; b *= 0.68; }   // dry riverbeds
        }
      }
      px[k] = Math.min(255, r); px[k + 1] = Math.min(255, gg); px[k + 2] = Math.min(255, b); px[k + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    terrain = cv;
    const cc = document.createElement('canvas'); cc.width = 480; cc.height = 360;
    const cg = cc.getContext('2d'), ci = cg.createImageData(480, 360), cp = ci.data;
    for (let j = 0; j < 360; j++) for (let i = 0; i < 480; i++) {
      // periodic cloud field so it can scroll forever
      const a = (i / 480) * Math.PI * 2, bb = (j / 360) * Math.PI * 2;
      const v = fbm(3 + Math.cos(a) * 1.6, 3 + Math.sin(a) * 1.6 + Math.cos(bb) * 1.3, 41, 5) * 0.7 + fbm(Math.sin(bb) * 2, i / 120, 43, 4) * 0.3;
      const al = smooth(0.52, 0.72, v);
      const k = (j * 480 + i) * 4; cp[k] = cp[k + 1] = cp[k + 2] = 250; cp[k + 3] = al * 235;
    }
    cg.putImageData(ci, 0, 0); clouds = cc;
  }

  const WATER = { 0: [24, 92, 120], 1: [28, 128, 128], 2: [64, 170, 160] };

  /* Live view. opts: {canvas, tag, onData(d), onSelect(info)} */
  D.PoolView = function (opts) {
    const canvas = opts.canvas, ctx = canvas.getContext('2d');
    let prev = null, cur = null, tPrev = 0, tCur = 0, data = null, failures = 0, plans = {}, names = {};
    const cam = { x: BAY.x + BAY.w / 2, y: BAY.y + BAY.h / 2, s: null, tx: null, ty: null, ts: null };
    let selected = null, hover = null;
    if (!terrain) buildTerrain();

    // controls
    const host = canvas.parentElement;
    const ui = document.createElement('div'); ui.className = 'zoom-ui';
    ui.innerHTML = `<button data-z="pool" title="Creatures in the bay">Bay</button><button data-z="coast" title="The coast">Coast</button>
      <button data-z="land" title="The whole landscape">Landscape</button>`;
    host.appendChild(ui);
    const card = document.createElement('div'); card.className = 'pick-card'; card.hidden = true; host.appendChild(card);
    card.addEventListener('click', e => {
      const a = e.target.closest('[data-a]'); if (!a) return;
      e.stopPropagation();
      if (a.dataset.a === 'x') { select(null); return; }
      if (card.info) {
        a.disabled = true; a.textContent = 'Loading…';
        D.view3D(card.info).catch(err => { const st = card.querySelector('[data-s]'); if (st) st.textContent = '3D view could not load: ' + err.message; })
          .finally(() => { a.disabled = false; a.textContent = 'See it in 3D'; });
      }
    });
    const hint = document.createElement('div'); hint.className = 'pick-hint'; hint.textContent = 'click a creature · scroll or pinch to zoom · drag to pan'; host.appendChild(hint);

    function fitScale() { return Math.max(canvas.clientWidth / LW, canvas.clientHeight / LH); }
    function poolScale() { return Math.min(canvas.clientWidth, canvas.clientHeight) / BAY.w; }
    function goto(z) {
      const W = canvas.clientWidth, H = canvas.clientHeight;
      if (z === 'pool') { cam.tx = BAY.x + BAY.w / 2; cam.ty = BAY.y + BAY.h / 2; cam.ts = poolScale(); }
      if (z === 'coast') { cam.tx = BAY.x + BAY.w * 0.75; cam.ty = BAY.y + BAY.h / 2; cam.ts = poolScale() * 0.42; }
      if (z === 'land') { cam.tx = LW / 2; cam.ty = LH / 2; cam.ts = fitScale(); }
      ui.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.z === z));
    }
    ui.addEventListener('click', e => { const z = e.target.dataset && e.target.dataset.z; if (z) goto(z); });
    function clampCam() {
      const W = canvas.clientWidth, H = canvas.clientHeight;
      cam.s = Math.max(fitScale(), Math.min(poolScale() * 6, cam.s));
      const hw = W / 2 / cam.s, hh = H / 2 / cam.s;
      cam.x = Math.max(hw, Math.min(LW - hw, cam.x)); cam.y = Math.max(hh, Math.min(LH - hh, cam.y));
    }
    const toWorld = (px, py) => [cam.x + (px - canvas.clientWidth / 2) / cam.s, cam.y + (py - canvas.clientHeight / 2) / cam.s];
    canvas.addEventListener('wheel', e => {
      e.preventDefault();
      const r = canvas.getBoundingClientRect(), [wx, wy] = toWorld(e.clientX - r.left, e.clientY - r.top);
      const f = Math.exp(-e.deltaY * 0.0015);
      cam.tx = cam.ty = cam.ts = null;
      cam.s *= f; clampCam();
      const [nx, ny] = toWorld(e.clientX - r.left, e.clientY - r.top);
      cam.x += wx - nx; cam.y += wy - ny; clampCam();
      ui.querySelectorAll('button').forEach(b => b.classList.remove('on'));
    }, { passive: false });
    let drag = null, pinch = null;
    canvas.addEventListener('pointerdown', e => { canvas.setPointerCapture(e.pointerId); drag = { x: e.clientX, y: e.clientY, cx: cam.x, cy: cam.y, moved: 0 }; });
    canvas.addEventListener('pointermove', e => {
      const r = canvas.getBoundingClientRect();
      if (drag && !pinch) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.moved = Math.max(drag.moved, Math.abs(dx) + Math.abs(dy));
        if (drag.moved > 4) { cam.tx = cam.ty = cam.ts = null; cam.x = drag.cx - dx / cam.s; cam.y = drag.cy - dy / cam.s; clampCam(); }
      } else hover = pick(e.clientX - r.left, e.clientY - r.top);
    });
    canvas.addEventListener('pointerup', e => {
      const r = canvas.getBoundingClientRect();
      if (drag && drag.moved <= 4) { const p = pick(e.clientX - r.left, e.clientY - r.top); select(p); }
      drag = null;
    });
    canvas.addEventListener('touchstart', e => { if (e.touches.length === 2) { const [a, b] = e.touches; pinch = { d: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY), s: cam.s }; } }, { passive: true });
    canvas.addEventListener('touchmove', e => { if (pinch && e.touches.length === 2) { e.preventDefault(); const [a, b] = e.touches; cam.tx = cam.ty = cam.ts = null; cam.s = pinch.s * Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) / pinch.d; clampCam(); } }, { passive: false });
    canvas.addEventListener('touchend', () => { pinch = null; });

    function pick(px, py) {
      if (!cur) return null;
      const [wx, wy] = toWorld(px, py);
      let best = null, bd = Math.max(3, 10 / cam.s);
      cur.c.forEach(c => { const d = Math.hypot(BAY.x + c[1] / 10 - wx, BAY.y + c[2] / 10 - wy); if (d < bd) { bd = d; best = c; } });
      return best;
    }
    function infoFor(c) {
      const body = plans[c[4]] || [[0, 0, 1]], counts = {};
      body.forEach(([, , t]) => { counts[D.CELL_LABELS[t]] = (counts[D.CELL_LABELS[t]] || 0) + 1; });
      return { uid: c[0], name: names[c[7]] || 'unnamed lineage', species: c[7], cells: body, hue: c[5], counts, energy: c[6],
               habitat: data && data.env.habitats ? data.env.habitats[Math.min(2, Math.floor((c[1] / 10) / (data.env.basin_w || 80)))] : '' };
    }
    function select(c) {
      selected = c ? c[0] : null;
      if (!c) { card.hidden = true; return; }
      const info = infoFor(c);
      card.hidden = false;
      card.innerHTML = `<canvas></canvas><div><b><i>${D.esc(info.name)}</i></b><br><span data-s>${info.cells.length} cells · ${D.esc(info.habitat)}</span><br>
        <span>${Object.entries(info.counts).map(([k, v]) => `${v} ${k}`).join(', ')}</span></div>
        <button class="btn" data-a="3d">See it in 3D</button><button class="x" aria-label="close" data-a="x">×</button>`;
      D.bodyThumb(card.querySelector('canvas'), info.cells, info.hue);
      card.info = info;
      if (opts.onSelect) opts.onSelect(info);
    }

    function resize() {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
      if (cam.s == null && w) { cam.s = poolScale(); goto('pool'); }
    }
    window.addEventListener('resize', resize); resize();

    function setTag(cls, txt) { if (opts.tag) { opts.tag.className = 'terra-tag' + (cls ? ' ' + cls : ''); opts.tag.querySelector('span').textContent = txt; } }

    async function poll() {
      try {
        const d = await D.api('/darwin/api/pool');
        failures = 0;
        if (!d || d.standby) { setTag('', d && d.note ? d.note : 'starting'); setTimeout(poll, 2000); return; }
        data = d;
        Object.assign(plans, d.plans || {});
        Object.assign(names, d.names || {});
        const f = d.frames && d.frames[d.frames.length - 1];
        if (f && (!cur || f.t > cur.t)) {
          prev = cur; cur = f; tPrev = tCur; tCur = performance.now();
          if (prev && f.t < prev.t) prev = null;
          if (selected != null && !cur.c.some(c => c[0] === selected)) {
            // it died: keep the card (and its 3D view, which only needs the body plan) and say so
            const st = card.querySelector('[data-s]'); if (st) st.textContent = 'this creature has died · ' + st.textContent;
            selected = null;
          }
        }
        setTag(d.stale ? '' : 'live', d.stale ? 'catching up · the pool is saving or restarting' :
          `live · ${D.geo(d.geo_ma)} · tick ${d.tick.toLocaleString()}`);
        if (opts.onData) opts.onData(d);
      } catch (e) {
        failures++;
        setTag('', failures > 2 ? 'connection lost' : 'retrying');
      }
      setTimeout(poll, document.hidden ? 4000 : 1000);
    }

    function draw(ts) {
      resize();
      const W = canvas.clientWidth, H = canvas.clientHeight;
      if (cam.ts != null) {        // glide toward a preset
        const k = 0.12;
        cam.x += (cam.tx - cam.x) * k; cam.y += (cam.ty - cam.y) * k; cam.s *= Math.pow(cam.ts / cam.s, k);
        if (Math.abs(cam.ts / cam.s - 1) < 0.002 && Math.hypot(cam.tx - cam.x, cam.ty - cam.y) < 0.2) { cam.s = cam.ts; cam.ts = null; }
      }
      clampCam();
      const s = cam.s, ox = W / 2 - cam.x * s, oy = H / 2 - cam.y * s;
      const X = wx => ox + wx * s, Y = wy => oy + wy * s;
      ctx.clearRect(0, 0, W, H);
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(terrain, X(0), Y(0), LW * s, LH * s);
      const env = (data && data.env) || {}, A = BAY.w;
      // the bay: habitats with the live tide, light band, nutrients, dead matter, reefs, upwellings
      ctx.save(); ctx.beginPath(); ctx.rect(X(BAY.x), Y(BAY.y), A * s, A * s); ctx.clip();
      const bw = env.basin_w || 80, wl = env.waterline != null ? env.waterline : 0.7;
      for (let h = 0; h < 3; h++) {
        const c = WATER[h]; ctx.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; ctx.fillRect(X(BAY.x + h * bw), Y(BAY.y), bw * s + 1, A * s);
      }
      // exposed flats at low tide: wet sand above the waterline
      const wx0 = BAY.x + 2 * bw + wl * bw;
      const gs = ctx.createLinearGradient(X(wx0), 0, X(BAY.x + A), 0);
      gs.addColorStop(0, 'rgba(168,150,110,.95)'); gs.addColorStop(1, 'rgba(206,186,140,1)');
      ctx.fillStyle = gs; ctx.fillRect(X(wx0), Y(BAY.y), (BAY.x + A - wx0) * s + 1, A * s);
      ctx.fillStyle = 'rgba(255,255,255,.35)'; ctx.fillRect(X(wx0) - 1, Y(BAY.y), Math.max(1, s * 0.6), A * s);   // surf line
      if (data) {
        const light = Math.max(0.05, env.light || 0), band = Y(BAY.y + env.band), bwid = env.width * s;
        [-A * s, 0, A * s].forEach(off => {
          const g = ctx.createLinearGradient(0, band + off - bwid * 1.6, 0, band + off + bwid * 1.6);
          g.addColorStop(0, 'rgba(255,236,170,0)'); g.addColorStop(0.5, `rgba(255,236,170,${0.18 * light})`); g.addColorStop(1, 'rgba(255,236,170,0)');
          ctx.fillStyle = g; ctx.fillRect(X(BAY.x), band + off - bwid * 1.6, A * s, bwid * 3.2);
        });
        const cw = A / 12;
        (env.nutrient || []).forEach((row, j) => row.forEach((v, i) => {
          if (v > 8) { ctx.fillStyle = `rgba(80,210,220,${Math.min(0.14, v / 600)})`; ctx.fillRect(X(BAY.x + i * cw), Y(BAY.y + j * cw), cw * s, cw * s); }
        }));
        (env.detritus || []).forEach((row, j) => row.forEach((v, i) => {
          if (v > 4) { ctx.fillStyle = `rgba(120,85,50,${Math.min(0.55, v / 110)})`;
            for (let k = 0; k < Math.min(6, v / 10); k++) ctx.fillRect(X(BAY.x + i * cw + ((k * 37 + j * 13) % cw)), Y(BAY.y + j * cw + ((k * 23 + i * 17) % cw)), Math.max(1, s * 0.6), Math.max(1, s * 0.6)); }
        }));
        (env.upwellings || []).forEach(([x, y]) => {
          const r = 14 * s, cx = X(BAY.x + x), cy = Y(BAY.y + y);
          const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
          g.addColorStop(0, 'rgba(140,230,240,.22)'); g.addColorStop(1, 'rgba(140,230,240,0)');
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, r, 0, 7); ctx.fill();
        });
        (env.reefs || []).forEach((rx, k) => {
          const gy = k === 0 ? null : (env.straits || [])[k], gh = (env.strait_h || 18) / 2;
          ctx.strokeStyle = 'rgba(222,200,160,.75)'; ctx.lineWidth = Math.max(2, s * 1.4);
          const xx = X(BAY.x + rx) + (k === 0 ? ctx.lineWidth / 2 : 0);
          const segs = gy == null ? [[0, A]] : (() => { const a0 = (gy - gh + A) % A, a1 = (gy + gh) % A; return a0 < a1 ? [[0, a0], [a1, A]] : [[a1, a0]]; })();
          segs.forEach(([y0, y1]) => { ctx.beginPath(); ctx.moveTo(xx, Y(BAY.y + y0)); ctx.lineTo(xx, Y(BAY.y + y1)); ctx.stroke(); });
        });
      }
      // creatures: full bodies when close, dots when far
      if (cur) {
        const k = prev ? Math.min(1, (ts - tCur) / Math.max(300, tCur - tPrev)) : 1;
        const pm = prev ? new Map(prev.c.map(c => [c[0], c])) : null;
        const u = s * 1.05, far = u < 1.4;
        cur.c.forEach(c => {
          let x = c[1] / 10, y = c[2] / 10, hd = c[3] / 100;
          const p = pm && pm.get(c[0]);
          if (p) { const dx = x - p[1] / 10, dy = y - p[2] / 10; if (Math.abs(dx) < A / 2 && Math.abs(dy) < A / 2) { x = p[1] / 10 + dx * k; y = p[2] / 10 + dy * k; } }
          const sx = X(BAY.x + x), sy = Y(BAY.y + y);
          if (sx < -20 || sy < -20 || sx > W + 20 || sy > H + 20) return;
          const body = plans[c[4]] || [[0, 0, 1]];
          if (far) {
            const t = body.length > 3 ? 'rgba(255,240,200,.9)' : `rgba(${CELL_COLORS[body[0][2]].join(',')},.85)`;
            ctx.fillStyle = t; const r = Math.max(0.8, Math.sqrt(body.length) * s * 0.6); ctx.fillRect(sx - r / 2, sy - r / 2, r, r);
          } else D.drawBody(ctx, body, sx, sy, hd, u, c[5], 0.55 + 0.45 * Math.min(1, c[6] / 60));
          if (c[0] === selected || (hover && c[0] === hover[0])) {
            ctx.strokeStyle = c[0] === selected ? 'rgba(255,255,255,.95)' : 'rgba(255,255,255,.5)'; ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.arc(sx, sy, Math.max(6, Math.sqrt(body.length) * u * 0.9 + 4), 0, 7); ctx.stroke();
          }
        });
      }
      ctx.restore();
      const zoomOut = Math.max(0, Math.min(1, (poolScale() * 0.8 - s) / (poolScale() * 0.6)));   // 0 at bay, 1 far out
      // the bay outline and labels when zoomed out
      if (zoomOut > 0.05) {
        ctx.strokeStyle = `rgba(255,255,255,${0.5 * zoomOut})`; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
        ctx.strokeRect(X(BAY.x), Y(BAY.y), A * s, A * s); ctx.setLineDash([]);
      }
      // night falls over the whole landscape
      const day = env.day != null ? env.day : 1;
      ctx.fillStyle = `rgba(6,14,32,${0.5 * (1 - Math.min(1, day * 2.5))})`; ctx.fillRect(0, 0, W, H);
      // the sky: clouds and their shadows, drifting with the wind (fade in as you zoom out)
      if (zoomOut > 0.02 && clouds) {
        const drift = (performance.now() / 1000) * 3, cs = 2.4 * s;
        const tile = (dx, dy, alpha, shadow) => {
          ctx.globalAlpha = alpha;
          const tw = 480 * cs, th = 360 * cs, x0 = ((X(drift + dx) % tw) + tw) % tw - tw, y0 = ((Y(dy) % th) + th) % th - th;
          for (let xx = x0; xx < W; xx += tw) for (let yy = y0; yy < H; yy += th) {
            if (shadow) { ctx.globalCompositeOperation = 'multiply'; }
            ctx.drawImage(clouds, xx, yy, tw, th);
            ctx.globalCompositeOperation = 'source-over';
          }
        };
        tile(-14, 10, 0.18 * zoomOut, true);   // shadows
        tile(0, 0, 0.75 * zoomOut, false);
        ctx.globalAlpha = 1;
      }
      if (zoomOut > 0.25) {
        const a = Math.min(1, (zoomOut - 0.25) * 2);
        ctx.font = '600 11px "IBM Plex Mono", monospace'; ctx.textAlign = 'center';
        const lab = (t, wx, wy, sub) => {
          const x = X(wx), y = Y(wy); if (x < 0 || x > W || y < 0 || y > H) return;
          ctx.fillStyle = `rgba(0,0,0,${0.45 * a})`; const tw = Math.max(ctx.measureText(t).width, sub ? ctx.measureText(sub).width : 0) + 14;
          ctx.fillRect(x - tw / 2, y - 12, tw, sub ? 30 : 18);
          ctx.fillStyle = `rgba(255,255,255,${0.95 * a})`; ctx.fillText(t, x, y + 1);
          if (sub) { ctx.fillStyle = `rgba(255,255,255,${0.7 * a})`; ctx.fillText(sub, x, y + 14); }
        };
        lab('OPEN OCEAN', 190, 380, 'not simulated yet');
        lab("DARWIN'S BAY", BAY.x + BAY.w / 2, BAY.y - 14, 'open sea · reef shallows · tidal flats');
        lab('LAND', 760, 360, 'no life yet');
        lab('SKY', 700, 170, 'no flyers yet');
      }
      requestAnimationFrame(draw);
    }
    poll(); requestAnimationFrame(draw);
    return { goto, select };
  };
})();
