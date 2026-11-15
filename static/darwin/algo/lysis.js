/* ALGOLYSIS — the dark side of every panel.
   Each world runs one simulation in which decay feeds new growth; the dark side is a way of seeing it. Turn the panel
   over (the moon key) and the same moment is drawn from below: the dead, the decomposers and the flows of returned
   material, in a night palette of aubergine, bone and phosphor green.
   AlgoLysis.toggle() · .isDark() · .flip(now) -> { sx, dark }  (sx: horizontal squash for the turning animation)
   AlgoLysis.drawGauge(ctx, x, y, w, h, gsl, u)   three needles: genesis, stasis, lysis
   AlgoLysis.grid(under, key, rgb, scale)         a soft canvas from a hex-encoded coarse grid
   AlgoLysis.mycelium(ctx, id, x, y, r, s, t, glow)
   AlgoLysis.mushroom(ctx, x, y, r, look, fruit, dark, t)                                                             */
(function () {
  'use strict';
  const INK = '#2a1d14';
  const PAL = { night: '#140c18', soil: '#2a1a22', bone: '#e8dcc4', phos: '#7dffb0', amber: '#e7a23b', violet: '#b48cff', ash: '#6b5a6e' };
  let dark = false, flipAt = -1e9, listeners = [];
  const FLIP_MS = 900;

  function toggle(force) {
    const want = force == null ? !dark : !!force;
    if (want === dark) return dark;
    dark = want; flipAt = performance.now();
    try { localStorage.setItem('algo-dark', dark ? '1' : '0'); } catch (e) {}
    listeners.forEach(f => { try { f(dark); } catch (e) {} });
    return dark;
  }
  // the panel turns over like a card: the old face narrows to an edge, the new face widens from it
  function flip(now) {
    const k = (now - flipAt) / FLIP_MS;
    if (k >= 1) return { sx: 1, dark };
    if (k < 0.5) return { sx: Math.cos(k * Math.PI), dark: !dark };
    return { sx: -Math.cos(k * Math.PI), dark };
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
  function mycelium(g, id, x, y, r, s, t, glow) {
    const rb = Math.round(r / 6) * 6, segs = threads(id, rb);
    const pulse = 0.75 + 0.25 * Math.sin(t * 0.8 + id);
    g.save(); g.translate(x, y); g.scale(s, s); g.lineCap = 'round';
    for (const pass of [0, 1]) {
      g.strokeStyle = pass ? `rgba(200,255,220,${0.55 * pulse})` : `rgba(125,255,176,${0.16 * pulse * (0.6 + glow)})`;
      for (const [x0, y0, x1, y1, d] of segs) {
        g.lineWidth = (pass ? 0.55 : 2.4) * (1.6 - d * 0.35) / Math.max(0.5, s * 0.6);
        g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
      }
    }
    g.restore();
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

  window.AlgoLysis = { toggle, isDark: () => dark, flip, drawGauge, grid, mycelium, mushroom, onChange, PAL };
})();
