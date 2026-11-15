/* ALGOLYSIS — the dark side of every panel.
   Each world runs one simulation in which decay feeds new growth; the dark side is a way of seeing it. Turn the panel
   over (a swipe left or right) and the same moment is drawn from below: the dead, the decomposers and the flows of returned
   material, in a night palette of aubergine, bone and phosphor green.
   AlgoLysis.toggle() · .isDark() · .flip(now) -> { dark, angle, turning } · .project(g, src, rect, flip) · .attachSwipe(el, rect, cb)
   AlgoLysis.drawGauge(ctx, x, y, w, h, gsl, u)   three needles: genesis, stasis, lysis
   AlgoLysis.grid(under, key, rgb, scale)         a soft canvas from a hex-encoded coarse grid
   AlgoLysis.mycelium(ctx, id, x, y, r, s, t, glow)
   AlgoLysis.mushroom(ctx, x, y, r, look, fruit, dark, t)                                                             */
(function () {
  'use strict';
  const INK = '#2a1d14';
  const PAL = { night: '#140c18', soil: '#2a1a22', bone: '#e8dcc4', phos: '#7dffb0', amber: '#e7a23b', violet: '#b48cff', ash: '#6b5a6e' };
  let dark = false, listeners = [];
  // the turn: p runs 0 → 1 as the panel rotates half a revolution about its vertical axis, dir is ±1 (which way it
  // spins). At p = 0.5 the panel is edge-on and the other face comes round. A drag sets p directly; on release the
  // panel either completes the turn or falls back, and settles with a small overshoot like a heavy board on a pivot.
  let turn = null;                 // { dir, p, from, mode: 'drag'|'anim', a0, a1, t0, dur, commit }
  const TURN_MS = 1250;

  function commit(want) {
    if (want === dark) return dark;
    dark = want;
    try { localStorage.setItem('algo-dark', dark ? '1' : '0'); } catch (e) {}
    const d = dark; setTimeout(() => listeners.forEach(f => { try { f(d); } catch (e) {} }), 420);
    return dark;
  }
  function animate(to, dur, dir) {
    const now = performance.now();
    if (!turn) turn = { dir: dir || 1, p: 0, from: dark };
    turn.mode = 'anim'; turn.a0 = turn.p; turn.a1 = to; turn.t0 = now; turn.dur = dur;
  }
  // a programmatic turn (keyboard, toggle()): a full, unhurried half revolution
  function toggle(force, dir) {
    const want = force == null ? !dark : !!force;
    if (want === dark && !turn) return dark;
    if (turn) return dark;
    turn = { dir: dir || 1, p: 0, from: dark };
    animate(1, TURN_MS, dir);
    commit(want);
    return dark;
  }
  // easing: slow to start (the board's weight), fast through the edge, then a gentle settle past and back
  const easeInOut = k => k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
  function settle(k) {                       // ends at 1 with a soft overshoot of about 3%
    const c = 1.25; return 1 + (c + 1) * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2);
  }
  // a damped spring for everything a hand sets going: once the board passes edge-on it is caught and carried over,
  // keeping the speed the finger gave it, accelerating into its seat and settling with one soft bounce
  const SPRING_W = 0.0115, SPRING_Z = 0.62;            // natural frequency (per ms) and damping ratio
  function spring(to, v0) {
    if (!turn) return;
    turn.mode = 'spring'; turn.to = to; turn.v = v0 || 0; turn.last = performance.now();
  }
  function stepSpring(now) {
    let dt = Math.min(64, now - turn.last); turn.last = now;
    while (dt > 0) {                                 // small fixed substeps keep it smooth whatever the frame rate
      const h = Math.min(4, dt); dt -= h;
      const a = SPRING_W * SPRING_W * (turn.to - turn.p) - 2 * SPRING_Z * SPRING_W * turn.v;
      turn.v += a * h; turn.p += turn.v * h;
    }
    if (Math.abs(turn.to - turn.p) < 0.002 && Math.abs(turn.v) < 0.00008) turn = null;
  }
  function step(now) {
    if (turn && turn.mode === 'spring') return stepSpring(now);
    if (!turn || turn.mode !== 'anim') return;
    const k = Math.min(1, (now - turn.t0) / turn.dur);
    if (turn.a0 === 0 && turn.a1 === 1) {
      // a full turn from rest: ease in (the board's weight), sweep through the edge, then rock once past and back
      if (k < 0.86) turn.p = easeInOut(k / 0.86);
      else { const q = (k - 0.86) / 0.14; turn.p = 1 + 0.022 * Math.sin(q * Math.PI) * (1 - q); }
    } else {
      turn.p = turn.a0 + (turn.a1 - turn.a0) * settle(k);   // finishing or falling back after a drag
    }
    if (k >= 1) turn = null;
  }
  // what to draw now: which face, and the panel's rotation (radians, within ±90°) for the projection
  function flip(now) {
    step(now);
    if (!turn) return { dark, angle: 0, turning: false, sx: 1 };
    const p = turn.p, th = turn.dir * Math.PI * p;
    const back = p > 0.5;                               // the second face has come round
    const face = back ? !turn.from : turn.from;
    const angle = back ? th - turn.dir * Math.PI : th;
    return { dark: face, angle, p, turning: true, sx: Math.cos(angle) };
  }

  // draw the turning panel: src holds the face (same pixel coordinates as the destination), r is the window.
  // The face is cut into vertical strips and each strip is placed and scaled by true perspective, so the near edge
  // swells and the far edge shrinks as the board swings; it is shaded as it turns from the light, shows its thickness
  // when edge-on, and lifts off its seat a little in the middle of the turn.
  function project(g, src, r, f, opts) {
    const o = opts || {}, N = o.strips || Math.round(36 + 220 * Math.abs(Math.sin(f.angle) * Math.cos(f.angle))), cx = r.x + r.w / 2, cy = r.y + r.h / 2, hw = r.w / 2;
    const th = f.angle, c = Math.cos(th), sn = Math.sin(th), D = r.w * 2.2;
    const lift = 1 - 0.07 * Math.sin(Math.PI * Math.min(1, Math.max(0, f.p)));
    g.save();
    g.fillStyle = o.cavity || '#07040a'; g.fillRect(r.x, r.y, r.w, r.h);       // the empty seat behind the board
    const sh = g.createRadialGradient(cx, cy, 0, cx, cy, r.w * 0.6);
    sh.addColorStop(0, 'rgba(0,0,0,0)'); sh.addColorStop(1, 'rgba(0,0,0,0.6)'); g.fillStyle = sh; g.fillRect(r.x, r.y, r.w, r.h);
    const P = u => { const x = u * hw, z = x * sn, k = D / (D + z) * lift; return { x: cx + x * c * k, h: r.h * k }; };
    const L0 = P(-1), R0 = P(1);
    // the shadow it casts on the seat: two offset layers make a soft edge without a costly blur
    for (const [o, al] of [[0.035, 0.22], [0.02, 0.3]]) {
      const d = r.w * o;
      g.fillStyle = `rgba(0,0,0,${al})`;
      g.beginPath(); g.moveTo(L0.x + d, cy - L0.h / 2 + d); g.lineTo(R0.x + d, cy - R0.h / 2 + d);
      g.lineTo(R0.x + d, cy + R0.h / 2 + d); g.lineTo(L0.x + d, cy + L0.h / 2 + d); g.closePath(); g.fill();
    }
    let prev = P(-1);
    const sw = r.w / N;
    for (let i = 0; i < N; i++) {
      const nx = P(-1 + 2 * (i + 1) / N), x0 = Math.min(prev.x, nx.x), w = Math.abs(nx.x - prev.x) + 0.8, h = (prev.h + nx.h) / 2;
      if (w > 0.3) g.drawImage(src, r.x + i * sw, r.y, sw, r.h, x0, cy - h / 2, w, h);
      prev = nx;
    }
    // light: the face darkens as it turns away, with a highlight sliding across toward the near edge
    const near = sn > 0 ? L0 : R0, far = sn > 0 ? R0 : L0, a = Math.abs(sn);
    const quad = () => { g.beginPath(); g.moveTo(L0.x, cy - L0.h / 2); g.lineTo(R0.x, cy - R0.h / 2); g.lineTo(R0.x, cy + R0.h / 2); g.lineTo(L0.x, cy + L0.h / 2); g.closePath(); };
    const gr = g.createLinearGradient(near.x, 0, far.x, 0);
    gr.addColorStop(0, `rgba(255,248,230,${0.16 * a})`); gr.addColorStop(0.25, 'rgba(0,0,0,0)');
    gr.addColorStop(1, `rgba(0,0,0,${0.7 * a})`);
    quad(); g.fillStyle = gr; g.fill();
    // the board's thickness, seen as it comes edge-on
    const t = r.w * 0.022 * a, ex = near.x, dirx = sn > 0 ? -1 : 1;
    if (t > 0.5) {
      const eg = g.createLinearGradient(ex, 0, ex + dirx * t, 0);
      eg.addColorStop(0, '#f6e3a5'); eg.addColorStop(0.5, '#b8902e'); eg.addColorStop(1, '#6a4c12');
      g.fillStyle = eg; g.fillRect(Math.min(ex, ex + dirx * t), cy - near.h / 2, t, near.h);
    }
    g.restore();
  }

  // swipe left or right across the window to turn the panel; the board follows the finger
  // getRect() returns the window in CSS pixels (the coordinates of pointer events)
  function attachSwipe(el, getRect, onTurn) {
    let st = null, dragged = false;
    el.style.touchAction = 'none';
    el.addEventListener('pointerdown', e => {
      const r = getRect(); if (!r || (turn && turn.mode !== 'drag')) return;
      const x = e.clientX, y = e.clientY;
      if (x < r.x || x > r.x + r.w || y < r.y || y > r.y + r.h) return;
      st = { x0: x, y0: y, id: e.pointerId, live: false, hist: [[x, performance.now()]], w: r.w };
      dragged = false;
    });
    el.addEventListener('pointermove', e => {
      if (!st || e.pointerId !== st.id || st.caught) return;
      const dx = e.clientX - st.x0, dy = e.clientY - st.y0;
      if (!st.live) {
        if (Math.abs(dx) < 14 || Math.abs(dx) < 1.4 * Math.abs(dy)) { if (Math.abs(dy) > 30) st = null; return; }
        st.live = true; dragged = true;
        try { el.setPointerCapture(e.pointerId); } catch (er) {}
        turn = { dir: dx > 0 ? 1 : -1, p: 0, from: dark, mode: 'drag' };
      }
      // half the window's width of travel swings the board edge-on; the dead zone is taken out so it starts smoothly
      turn.p = Math.max(0, Math.min(1, (Math.abs(dx) - 14) / (st.w * 0.6))) * (Math.sign(dx) === turn.dir ? 1 : 0);
      st.hist.push([e.clientX, performance.now()]); if (st.hist.length > 6) st.hist.shift();
      if (turn.p >= 0.5) {                           // past edge-on: the spring takes it from the finger
        st.caught = true;
        spring(1, Math.max(0.0018, pv(st)));
        commit(!turn.from); if (onTurn) { const d = dark; setTimeout(() => onTurn(d), 420); }
      }
    });
    const pv = s0 => {                               // the finger's speed, in turns per ms, in the turning direction
      const h = s0.hist; if (h.length < 2) return 0;
      const v = (h[h.length - 1][0] - h[0][0]) / Math.max(1, h[h.length - 1][1] - h[0][1]);
      return turn ? v * turn.dir / (s0.w * 0.6) : 0;
    };
    const end = e => {
      if (!st || e.pointerId !== st.id) return;
      const s0 = st; st = null;
      if (!s0.live || !turn || s0.caught) return;
      const v = pv(s0), fling = v * s0.w * 0.6 > 0.35;   // a flick faster than 0.35 px/ms carries it over
      const go = turn.p > 0.3 || fling;
      spring(go ? 1 : 0, go ? Math.max(0.0015, v) : Math.min(0, v));
      if (go) { commit(!turn.from); if (onTurn) { const d = dark; setTimeout(() => onTurn(d), 420); } }
    };
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
    // a drag must not also count as a tap on whatever it started over
    el.addEventListener('click', e => { if (dragged) { dragged = false; e.stopImmediatePropagation(); e.preventDefault(); } }, true);
    addEventListener('keydown', e => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      if (turn) return;
      toggle(null, e.key === 'ArrowRight' ? 1 : -1); if (onTurn) onTurn(dark);
    });
  }

  // ── the gauge: genesis · stasis · lysis ──────────────────────────────
  function drawGauge(g, x, y, w, h, gsl, u) {
    const v = gsl || [0, 0, 0];
    g.save();
    const r = Math.min(w * 0.46, h * 0.82), cx = x + w / 2, cy = y + h * 0.9;
    // dial face
    g.beginPath(); g.roundRect ? g.roundRect(x, y, w, h, u * 0.01) : g.rect(x, y, w, h);
    g.fillStyle = dark ? '#1a1220' : '#fbf3dc'; g.fill(); g.lineWidth = u * 0.004; g.strokeStyle = '#8a7a6a'; g.stroke();
    const A0 = Math.PI * 1.12, A1 = Math.PI * 1.88;
    // three coloured arcs, one per needle's range
    const cols = ['#a8c94a', '#f2b33d', '#b48cff'];
    g.lineWidth = Math.max(1.5, h * 0.06);
    cols.forEach((c, i) => {
      g.strokeStyle = c; g.globalAlpha = 0.5;
      g.beginPath(); g.arc(cx, cy, r * (0.95 - i * 0.11), A0, A1); g.stroke();
    });
    g.globalAlpha = 1;
    // ticks
    g.strokeStyle = dark ? '#c9bfae' : INK; g.lineWidth = Math.max(1, u * 0.0012);
    for (let i = 0; i <= 10; i++) {
      const a = A0 + (A1 - A0) * i / 10, r0 = r * (i % 5 ? 0.98 : 0.93);
      g.beginPath(); g.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0); g.lineTo(cx + Math.cos(a) * r * 1.04, cy + Math.sin(a) * r * 1.04); g.stroke();
    }
    // needles, with a little life in them
    const t = performance.now() / 1000;
    v.forEach((val, i) => {
      const jit = Math.sin(t * (1.3 + i * 0.7) + i) * 0.006;
      const a = A0 + (A1 - A0) * Math.max(0, Math.min(1, val + jit)), len = r * (0.92 - i * 0.11);
      g.strokeStyle = cols[i]; g.lineWidth = Math.max(1.5, u * 0.0028); g.lineCap = 'round';
      g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(a) * len, cy + Math.sin(a) * len); g.stroke();
      g.strokeStyle = INK; g.lineWidth = Math.max(0.6, u * 0.0008); g.stroke();
    });
    g.fillStyle = INK; g.beginPath(); g.arc(cx, cy, Math.max(2, u * 0.006), 0, 7); g.fill();
    // letters
    g.font = `${Math.max(7, Math.round(h * 0.17))}px Righteous, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'top';
    ['G', 'S', 'L'].forEach((s, i) => { g.fillStyle = cols[i]; g.fillText(s, x + w * (0.2 + 0.3 * i), y + h * 0.06); });
    g.restore();
  }

  // ── grids from the world (hex bytes), cached as tiny canvases that the browser smooths when it scales them ──
  const gridCache = new Map();
  function grid(under, key, rgb, scale) {
    if (!under || !under[key]) return null;
    const hex = under[key], id = key + hex.length + hex.slice(0, 64) + hex.slice(-64);
    let c = gridCache.get(key);
    if (c && c._id === id) return c;
    const gx = under.gx, gy = under.gy;
    c = c || document.createElement('canvas'); c.width = gx; c.height = gy; c._id = id;
    const g = c.getContext('2d'), img = g.createImageData(gx, gy);
    for (let i = 0; i < gx * gy; i++) {
      const v = parseInt(hex.substr(i * 2, 2), 16) / 255;
      img.data[i * 4] = rgb[0]; img.data[i * 4 + 1] = rgb[1]; img.data[i * 4 + 2] = rgb[2];
      img.data[i * 4 + 3] = Math.round(255 * Math.min(1, Math.pow(v, 0.6) * (scale || 1)));
    }
    g.putImageData(img, 0, 0);
    gridCache.set(key, c);
    return c;
  }

  // ── mycelium: branching threads, the same shape for the same colony ──
  const mycCache = new Map();
  function rand(seed) { let s = seed >>> 0 || 1; return () => ((s = Math.imul(s ^ (s >>> 15), 2246822507) ^ Math.imul(s ^ (s >>> 13), 3266489909), (s ^= s >>> 16) >>> 0) / 4294967296); }
  function threads(id, rb) {
    const key = id + ':' + rb;
    let p = mycCache.get(key);
    if (p) return p;
    const R = rand(id * 7919 + 13), segs = [];
    const arms = 5 + Math.floor(R() * 4);
    function grow(x, y, a, len, depth) {
      let px = x, py = y;
      const n = Math.max(2, Math.round(len / 6));
      for (let i = 0; i < n; i++) {
        a += (R() - 0.5) * 0.7;
        const nx = px + Math.cos(a) * len / n, ny = py + Math.sin(a) * len / n;
        segs.push([px, py, nx, ny, depth]); px = nx; py = ny;
        if (depth < 3 && R() < 0.22) grow(px, py, a + (R() < 0.5 ? -1 : 1) * (0.5 + R() * 0.6), len * (0.35 + R() * 0.3), depth + 1);
      }
    }
    for (let k = 0; k < arms; k++) grow(0, 0, k / arms * Math.PI * 2 + R() * 0.6, rb * (0.6 + R() * 0.45), 0);
    if (mycCache.size > 600) mycCache.clear();
    mycCache.set(key, segs);
    return segs;
  }
  // each colony's threads are drawn once into a sprite (they only change when the colony's reach does), and each
  // frame the sprite is placed with its slow pulse as opacity: thousands of strokes become one image
  const mycSprites = new Map();
  function mycSprite(id, rb, s, glow) {
    const sk = Math.round(s * 20) / 20, key = id + ':' + rb + ':' + sk + ':' + Math.round(glow * 10);
    let c = mycSprites.get(key);
    if (c) return c;
    const segs = threads(id, rb);
    let ext = 4;
    for (const q of segs) ext = Math.max(ext, Math.abs(q[0]), Math.abs(q[1]), Math.abs(q[2]), Math.abs(q[3]));
    const pad = 4, half = Math.ceil(ext * sk + pad);
    c = document.createElement('canvas'); c.width = c.height = half * 2; c._half = half;
    const g = c.getContext('2d');
    g.translate(half, half); g.scale(sk, sk); g.lineCap = 'round';
    for (const pass of [0, 1]) {
      g.strokeStyle = pass ? 'rgba(200,255,220,0.55)' : `rgba(125,255,176,${0.16 * (0.6 + glow)})`;
      for (let d = 0; d <= 3; d++) {                       // one path per thread depth: a handful of strokes
        g.lineWidth = (pass ? 0.55 : 2.4) * (1.6 - d * 0.35) / Math.max(0.5, sk * 0.6);
        g.beginPath();
        for (const [x0, y0, x1, y1, dd] of segs) if (dd === d) { g.moveTo(x0, y0); g.lineTo(x1, y1); }
        g.stroke();
      }
    }
    if (mycSprites.size > 500) mycSprites.clear();
    mycSprites.set(key, c);
    return c;
  }
  const warmCv = document.createElement('canvas'); warmCv.width = warmCv.height = 4;
  function warmMycelium(id, r, s, glow) {           // build ahead of time, and draw once so the browser has it ready
    const before = mycSprites.size, c = mycSprite(id, Math.round(r / 6) * 6, s, glow);
    if (mycSprites.size !== before) warmCv.getContext('2d').drawImage(c, 0, 0, 4, 4);
  }
  function mycelium(g, id, x, y, r, s, t, glow) {
    const rb = Math.round(r / 6) * 6, c = mycSprite(id, rb, s, glow);
    const pulse = 0.75 + 0.25 * Math.sin(t * 0.8 + id), a0 = g.globalAlpha;
    g.globalAlpha = a0 * pulse;
    g.drawImage(c, x - c._half, y - c._half);
    g.globalAlpha = a0;
  }

  // ── a mushroom, in the decal style of the board ──────────────────────
  // look = [hue, cap, size, glow, rate, cold, spore, tox, spots, hue2]
  function mushroom(g, x, y, r, look, fruit, isDark, t) {
    const [hue, capS, , glow, , , , tox, spots, hue2] = look;
    const k = Math.max(0, Math.min(1, fruit)), R = r * (0.4 + 0.6 * k);
    if (R < 0.6) return;
    const S = 30 + 55 * Math.min(1, 0.3 + tox * 0.8), Lt = 52 + 10 * (1 - capS);
    const capCol = isDark ? `hsla(${hue * 360},60%,${30 + 40 * glow}%,1)` : `hsl(${hue * 360},${S}%,${Lt}%)`;
    g.save(); g.translate(x, y);
    if (glow > 0.3) {                                      // foxfire
      const gr = g.createRadialGradient(0, -R * 0.4, 0, 0, -R * 0.4, R * (2 + 2 * glow));
      gr.addColorStop(0, `rgba(125,255,176,${(isDark ? 0.55 : 0.25) * glow})`); gr.addColorStop(1, 'rgba(125,255,176,0)');
      g.fillStyle = gr; g.beginPath(); g.arc(0, -R * 0.4, R * (2 + 2 * glow), 0, 7); g.fill();
    }
    g.lineWidth = Math.max(0.8, R * 0.13); g.strokeStyle = isDark ? '#0b0710' : INK; g.lineJoin = 'round';
    // stem
    g.fillStyle = isDark ? '#cfc2a8' : '#f4ead2';
    g.beginPath(); g.roundRect ? g.roundRect(-R * 0.18, -R * 0.35, R * 0.36, R * 0.95, R * 0.12) : g.rect(-R * 0.18, -R * 0.35, R * 0.36, R * 0.95);
    g.fill(); g.stroke();
    // cap: flat and wide (0) to tall and conical (1)
    const cw = R * (1.05 - 0.35 * capS), chh = R * (0.45 + 0.75 * capS);
    g.fillStyle = capCol;
    g.beginPath(); g.moveTo(-cw, -R * 0.3);
    g.quadraticCurveTo(-cw * (0.9 - 0.5 * capS), -R * 0.3 - chh * 1.25, 0, -R * 0.3 - chh);
    g.quadraticCurveTo(cw * (0.9 - 0.5 * capS), -R * 0.3 - chh * 1.25, cw, -R * 0.3);
    g.closePath(); g.fill(); g.stroke();
    if (spots > 0.45) {                                   // spots, the warning of the toxic ones
      g.fillStyle = isDark ? 'rgba(232,220,196,0.8)' : `hsl(${hue2 * 360},40%,92%)`;
      for (let i = 0; i < 4; i++) { g.beginPath(); g.arc((i - 1.5) * cw * 0.42, -R * 0.3 - chh * (0.35 + 0.25 * (i % 2)), R * 0.11, 0, 7); g.fill(); }
    }
    g.restore();
  }

  function onChange(f) { listeners.push(f); }
  try { if (localStorage.getItem('algo-dark') === '1' && new URLSearchParams(location.search).get('dark') !== '0') { dark = true; } } catch (e) {}
  if (new URLSearchParams(location.search).get('dark') === '1') dark = true;

  window.AlgoLysis = { toggle, isDark: () => dark, flip, project, attachSwipe, isTurning: () => !!turn, drawGauge, grid, mycelium,
    warmMycelium, mushroom, onChange, PAL };
})();
