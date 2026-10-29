/* Barricelli's Symbiosis — animated explainers.
   Small, self-contained animations that run the same rules as the main universe (shift norm, symbiotic
   replication with a chain limit of 6, collision norms), slowed down and zoomed in so each rule can be watched.
   Every animation only runs while it is on screen. */
(function () {
  const D = window.Darwin || (window.Darwin = {});
  const POS = '#e9bf6d', NEG = '#9ab8ff', HAZ = '#ff8a7a', JADE = '#7dd8b5', VIO = '#d79bff';
  const MONO = '"IBM Plex Mono", ui-monospace, monospace';
  const sign = v => (v > 0 ? '+' : '−') + Math.abs(v);
  const mod = (a, n) => ((a % n) + n) % n;
  function mulberry(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

  // ── the rules, returning every move so it can be drawn ─────────────────
  function step(A, K, normOf, rng) {
    const N = A.length, hit = new Array(N), moves = [];
    for (let a = 0; a < N; a++) {
      const n = A[a]; if (!n) continue;
      const t = mod(a + n, N), ts = [t], via = [null];
      (hit[t] || (hit[t] = [])).push(n);
      let m = A[t], k = 0;
      while (m && k < 6) {
        const t2 = mod(a + m, N);
        if (ts.includes(t2)) break;
        ts.push(t2); via.push(m); (hit[t2] || (hit[t2] = [])).push(n);
        m = A[t2]; k++;
      }
      moves.push({ a, v: n, ts, via });
    }
    const B = new Int16Array(N), coll = new Set();
    for (let j = 0; j < N; j++) {
      const h = hit[j]; if (!h) continue;
      if (h.every(x => x === h[0])) { B[j] = h[0]; continue; }
      coll.add(j);
      const nm = normOf(j);
      if (nm === 'sum') { const v = [...new Set(h)].reduce((s, x) => s + x, 0); B[j] = v && Math.abs(v) <= K ? v : 0; }
      else if (nm === 'random') { if (rng() < 0.5) { const v = Math.floor(rng() * 2 * K) - K; B[j] = v >= 0 ? v + 1 : v; } else B[j] = 0; }
      else B[j] = 0;
    }
    return { B, moves, coll };
  }
  const regionNorm = N => j => ['0', 'sum', 'random', '0'][Math.floor(j * 4 / N)];
  const distinct = A => { const s = new Set(); A.forEach(v => { if (v) s.add(v); }); return s.size; };
  const alive = A => A.reduce((s, v) => s + (v ? 1 : 0), 0);

  // ── canvas helpers ──────────────────────────────────────────────────────
  function fit(cv) {
    const dpr = Math.min(2, window.devicePixelRatio || 1), W = cv.clientWidth, H = cv.clientHeight;
    if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    const c = cv.getContext('2d'); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { c, W, H };
  }
  function geneColor(v, K, dim) {
    if (dim) { const l = 30 + Math.abs(v) / K * 22; return v > 0 ? `hsl(38 30% ${l}%)` : `hsl(218 30% ${l}%)`; }
    return v > 0 ? POS : NEG;
  }
  function cellRow(c, A, x0, y, cw, ch, opts = {}) {
    for (let j = 0; j < A.length; j++) {
      const x = x0 + j * cw;
      c.fillStyle = 'rgba(255,255,255,.05)'; c.fillRect(x + 1, y, cw - 2, ch);
      const v = A[j]; if (!v) continue;
      c.fillStyle = opts.color ? opts.color(v, j) : geneColor(v, 8);
      c.globalAlpha = opts.alpha ?? 1;
      c.fillRect(x + 1, y, cw - 2, ch);
      c.globalAlpha = 1;
      if (cw >= 16 && ch >= 14) { c.fillStyle = '#0b1210'; c.font = `600 ${Math.min(12, cw * 0.45)}px ${MONO}`; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(sign(v), x + cw / 2, y + ch / 2 + 0.5); }
    }
  }

  // Animations register here and are driven by one requestAnimationFrame loop.
  const anims = [];
  function register(root, a) {
    a.visible = false;
    const io = new IntersectionObserver(es => es.forEach(e => { a.visible = e.isIntersecting; }), { threshold: 0.05 });
    io.observe(root); anims.push(a);
    const btn = root.querySelector('[data-replay]'); if (btn) btn.onclick = () => a.reset();
    a.reset();
  }
  let last = 0;
  function loop(ts) {
    const dt = Math.min(0.1, (ts - (last || ts)) / 1000); last = ts;
    if (!document.hidden) anims.forEach(a => { if (a.visible) { a.update(dt); a.draw(); } });
    requestAnimationFrame(loop);
  }

  // ── 1 & 2: a zoomed strip; copies fly from cell to cell, the printout grows underneath ──
  // spec: {N, init: [[cell, gene]], K, norm, gens, caption(st)}
  function zoomStrip(root, spec) {
    const cv = root.querySelector('canvas'), cap = root.querySelector('.bxe-cap');
    const a = { A: null, hist: [], tr: null, p: 0, hold: 0, gen: 0 };
    const rng = mulberry(7);
    a.reset = () => {
      a.A = new Int16Array(spec.N); spec.init.forEach(([i, v]) => { a.A[i] = v; });
      a.hist = [a.A.slice()]; a.tr = null; a.p = 0; a.hold = 0.8; a.gen = 0;
      if (cap) cap.innerHTML = spec.caption({ gen: 0, n: alive(a.A), tr: null });
    };
    a.update = dt => {
      if (a.hold > 0) { a.hold -= dt; return; }
      if (!a.tr) {
        if (a.gen >= spec.gens) { a.reset(); return; }
        a.tr = step(a.A, spec.K || 8, () => spec.norm || '0', rng); a.p = 0;
      }
      a.p += dt / (spec.secs || 1.15);
      if (a.p >= 1) {
        a.A = a.tr.B; a.gen++; a.hist.push(a.A.slice()); if (a.hist.length > 14) a.hist.shift();
        if (cap) cap.innerHTML = spec.caption({ gen: a.gen, n: alive(a.A), tr: a.tr });
        a.tr = null; a.hold = a.gen >= spec.gens ? 2.2 : 0.25;
      }
    };
    a.draw = () => {
      const { c, W, H } = fit(cv); c.clearRect(0, 0, W, H);
      const N = spec.N, cw = W / N, ch = Math.min(26, cw * 0.95), zy = 70;
      // the zoom row: this generation, with copies in flight
      cellRow(c, a.A, 0, zy, cw, ch, { alpha: a.tr ? 1 - 0.55 * Math.max(0, a.p - 0.75) / 0.25 : 1 });
      c.fillStyle = 'rgba(221,228,224,.55)'; c.font = `500 10px ${MONO}`; c.textAlign = 'left'; c.textBaseline = 'alphabetic';
      c.fillText(`generation ${a.gen}`, 2, zy + ch + 14);
      if (a.tr && a.p < 0.9 && a.tr.moves.reduce((s, mv) => s + mv.ts.length - 1, 0) > 4) { c.fillStyle = VIO; c.textAlign = 'right'; c.fillText('violet = extra copies from landing on a gene', W - 2, zy + ch + 14); }
      if (a.tr) {
        const nChained = a.tr.moves.reduce((s, mv) => s + mv.ts.length - 1, 0);
        const p = Math.min(1, a.p / 0.8), ease = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
        a.tr.moves.forEach(mv => {
          mv.ts.forEach((t, k) => {
            const x1 = mv.a * cw + cw / 2, x2 = t * cw + cw / 2, dist = Math.abs(x2 - x1), h = 18 + Math.min(46, dist * 0.35) + k * 6;
            const chained = k > 0, col = mv.v > 0 ? POS : NEG;
            // the path
            c.strokeStyle = chained ? VIO : col; c.globalAlpha = 0.5; c.lineWidth = 1.2; c.setLineDash(chained ? [3, 3] : []);
            c.beginPath(); c.moveTo(x1, zy); c.quadraticCurveTo((x1 + x2) / 2, zy - h * 2, x2, zy); c.stroke(); c.setLineDash([]); c.globalAlpha = 1;
            // the travelling copy
            const q = chained ? Math.max(0, Math.min(1, (ease - 0.25) / 0.75)) : ease;
            const bx = (1 - q) * (1 - q) * x1 + 2 * (1 - q) * q * (x1 + x2) / 2 + q * q * x2;
            const by = (1 - q) * (1 - q) * zy + 2 * (1 - q) * q * (zy - h * 2) + q * q * zy;
            if (q > 0) {
              c.fillStyle = col; c.beginPath(); c.roundRect(bx - 11, by - 9, 22, 16, 4); c.fill();
              c.fillStyle = '#0b1210'; c.font = `600 10px ${MONO}`; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(sign(mv.v), bx, by - 1);
            }
            if (chained && p < 0.9 && nChained <= 4) {    // why it copied again: it met this gene
              const mx = t * cw + cw / 2; c.fillStyle = VIO; c.font = `500 9.5px ${MONO}`; c.textAlign = 'center'; c.textBaseline = 'alphabetic';
              c.fillText(`met ${sign(mv.via[k])}`, mx, zy + ch + 28 + (k - 1) * 11);
            }
          });
        });
        if (a.p > 0.8) a.tr.coll.forEach(j => { c.strokeStyle = HAZ; c.lineWidth = 2; c.strokeRect(j * cw + 1, zy, cw - 2, ch); });
      }
      // the printout so far
      const py = zy + ch + 50, rh = Math.max(4, Math.min(9, (H - py - 4) / 14));
      c.fillStyle = 'rgba(221,228,224,.45)'; c.font = `500 9.5px ${MONO}`; c.textAlign = 'left'; c.textBaseline = 'alphabetic';
      c.fillText('the printout: one row per generation', 2, py - 5);
      a.hist.forEach((row, k) => { for (let j = 0; j < N; j++) if (row[j]) { c.fillStyle = geneColor(row[j], 8); c.fillRect(j * cw + 0.5, py + k * rh, cw - 1, rh - 1); } });
    };
    register(root, a);
  }

  // ── 3: one collision, three norms ─────────────────────────────────────
  function collisions(root) {
    const cvs = [...root.querySelectorAll('canvas')], norms = ['0', 'sum', 'random'];
    const init = new Int16Array(9); init[1] = 2; init[6] = -3;   // +2 jumps right two, −3 jumps left three: both land in cell 3
    const a = { p: 0, hold: 0.6, results: null };
    a.reset = () => { a.p = 0; a.hold = 0.6; a.results = norms.map(nm => step(init, 8, () => nm, Math.random)); };
    a.update = dt => { if (a.hold > 0) { a.hold -= dt; return; } a.p += dt / 1.6; if (a.p > 2.4) a.reset(); };
    a.draw = () => cvs.forEach((cv, k) => {
      const { c, W, H } = fit(cv); c.clearRect(0, 0, W, H);
      const N = 9, cw = W / N, ch = Math.min(24, cw * 0.9), y1 = 46, y2 = H - ch - 18;
      cellRow(c, init, 0, y1, cw, ch);
      const p = Math.min(1, a.p);
      [[1, 2], [6, -3]].forEach(([s, v]) => {
        const x1 = s * cw + cw / 2, x2 = 3 * cw + cw / 2, q = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
        const bx = x1 + (x2 - x1) * q, by = y1 + ch + (y2 - y1 - ch) * q;
        c.strokeStyle = v > 0 ? POS : NEG; c.globalAlpha = .45; c.beginPath(); c.moveTo(x1, y1 + ch); c.lineTo(x2, y2); c.stroke(); c.globalAlpha = 1;
        if (p < 1) { c.fillStyle = v > 0 ? POS : NEG; c.beginPath(); c.roundRect(bx - 11, by - 8, 22, 16, 4); c.fill(); c.fillStyle = '#0b1210'; c.font = `600 10px ${MONO}`; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(sign(v), bx, by); }
      });
      const out = a.results[k].B;
      if (a.p >= 1) {
        cellRow(c, out, 0, y2, cw, ch);
        const flash = Math.max(0, 1 - (a.p - 1) * 2);
        c.strokeStyle = `rgba(255,138,122,${0.3 + 0.7 * flash})`; c.lineWidth = 2; c.strokeRect(3 * cw + 1, y2, cw - 2, ch);
        c.fillStyle = 'rgba(221,228,224,.85)'; c.font = `500 10.5px ${MONO}`; c.textAlign = 'center'; c.textBaseline = 'alphabetic';
        const v = out[3];
        c.fillText(norms[k] === '0' ? 'both destroyed' : norms[k] === 'sum' ? `fused: +2 + (−3) = ${sign(v)}` : v ? `a new gene: ${sign(v)}` : 'nothing (this time)', W / 2, H - 4);
      } else {
        for (let j = 0; j < N; j++) { c.fillStyle = 'rgba(255,255,255,.05)'; c.fillRect(j * cw + 1, y2, cw - 2, ch); }
      }
      c.fillStyle = 'rgba(221,228,224,.55)'; c.font = `500 9.5px ${MONO}`; c.textAlign = 'left'; c.textBaseline = 'alphabetic';
      c.fillText('now', 2, y1 - 6); c.fillText('next', 2, y2 - 6);
    });
    register(root, a);
  }

  // ── 4: the "uses" graph — how organisms and parasites are told apart ─────
  function usesGraph(root) {
    const cv = root.querySelector('canvas');
    const nodes = [
      { g: 3, x: .14, y: .36, org: 'A' }, { g: -2, x: .14, y: .76, org: 'A' },
      { g: 5, x: .56, y: .26, org: 'B' }, { g: -4, x: .70, y: .76, org: 'B' }, { g: 1, x: .42, y: .76, org: 'B' },
      { g: 6, x: .90, y: .28, org: null }];
    const edges = [[3, -2], [-2, 3], [5, -4], [-4, 1], [1, 5], [6, -4], [6, 1]];
    const colorOf = { A: JADE, B: POS };
    const a = { t: 0 };
    a.reset = () => { a.t = 0; };
    a.update = dt => { a.t += dt; };
    a.draw = () => {
      const { c, W, H } = fit(cv); c.clearRect(0, 0, W, H);
      const P = g => { const n = nodes.find(n => n.g === g); return [n.x * W, n.y * H]; };
      // organism hulls
      [['A', [3, -2]], ['B', [5, -4, 1]]].forEach(([o, gs]) => {
        const pts = gs.map(P), cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
        const rx = Math.max(...pts.map(p => Math.abs(p[0] - cx))) * 1.25 + 34, ry = Math.max(...pts.map(p => Math.abs(p[1] - cy))) * 1.15 + 30;
        c.fillStyle = colorOf[o] + '14'; c.strokeStyle = colorOf[o] + '88'; c.setLineDash([4, 4]); c.lineWidth = 1.2;
        c.beginPath(); c.ellipse(cx, cy, rx, ry, 0, 0, 7); c.fill(); c.stroke(); c.setLineDash([]);
        c.fillStyle = colorOf[o]; c.font = `600 11px ${MONO}`; c.textAlign = 'center'; c.textBaseline = 'alphabetic';
        c.fillText(`organism ${o}`, cx, Math.max(12, cy - ry - 6));
      });
      edges.forEach(([u, v], k) => {
        const [x1, y1] = P(u), [x2, y2] = P(v), dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy), ux = dx / L, uy = dy / L;
        const back = edges.some(([p, q]) => p === v && q === u), off = back ? 6 : 0, nx = -uy * off, ny = ux * off;
        const sx = x1 + ux * 20 + nx, sy = y1 + uy * 20 + ny, ex = x2 - ux * 22 + nx, ey = y2 - uy * 22 + ny;
        const par = u === 6, col = par ? VIO : '#dde4e0';
        c.strokeStyle = col; c.globalAlpha = par ? .8 : .45; c.lineWidth = 1.4;
        c.beginPath(); c.moveTo(sx, sy); c.lineTo(ex, ey); c.stroke();
        c.beginPath(); c.moveTo(ex, ey); c.lineTo(ex - ux * 8 - uy * 4, ey - uy * 8 + ux * 4); c.lineTo(ex - ux * 8 + uy * 4, ey - uy * 8 - ux * 4); c.closePath(); c.fillStyle = col; c.fill();
        c.globalAlpha = 1;
        // pulses: each pulse is one copy made by landing on that gene
        for (let q = 0; q < 2; q++) {
          const f = ((a.t * 0.55 + k * 0.17 + q * 0.5) % 1);
          c.fillStyle = par ? VIO : (nodes.find(n => n.g === u).g > 0 ? POS : NEG);
          c.beginPath(); c.arc(sx + (ex - sx) * f, sy + (ey - sy) * f, 2.6, 0, 7); c.fill();
        }
      });
      nodes.forEach(n => {
        const x = n.x * W, y = n.y * H;
        c.fillStyle = '#0b1210'; c.strokeStyle = n.org ? colorOf[n.org] : VIO; c.lineWidth = 2;
        c.beginPath(); c.arc(x, y, 18, 0, 7); c.fill(); c.stroke();
        c.fillStyle = n.g > 0 ? POS : NEG; c.font = `600 12px ${MONO}`; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(sign(n.g), x, y + 0.5);
      });
      const [px, py] = P(6);
      c.fillStyle = VIO; c.font = `600 11px ${MONO}`; c.textAlign = 'center'; c.textBaseline = 'alphabetic'; c.fillText('parasite', px, py - 26);
    };
    register(root, a);
  }

  // ── 5 & 6: whole universes, printout style ──────────────────────────────
  // panels: [{title, N, K, seed, norm:'0'|'mixed', partner?}]; exchange: swap a stretch between panels 0 and 1 every `every` generations
  function universes(root, spec) {
    const cvs = [...root.querySelectorAll('canvas')], stats = [...root.querySelectorAll('.bxe-stat')];
    const ROWS = 110;
    const a = { gen: 0, acc: 0, U: [], swap: null };
    a.reset = () => {
      a.gen = 0; a.acc = 0; a.swap = null;
      a.U = spec.panels.map(p => {
        const rng = mulberry(p.seed), A = new Int16Array(p.N);
        for (let i = 0; i < p.N; i++) if (rng() < 0.3) { const v = Math.floor(rng() * 2 * p.K) - p.K; A[i] = v >= 0 ? v + 1 : v; }
        return { ...p, rng, A, rows: [A.slice()], coll: [new Set()], div: [distinct(A)] };
      });
    };
    a.update = dt => {
      a.acc += dt * (spec.gps || 26);
      let n = 0;
      while (a.acc >= 1 && n < 8) {
        a.acc -= 1; n++; a.gen++;
        a.U.forEach(u => {
          const r = step(u.A, u.K, u.norm === 'mixed' ? regionNorm(u.N) : () => u.norm, u.rng);
          u.A = r.B; u.rows.push(u.A.slice()); u.coll.push(r.coll); if (u.rows.length > ROWS) { u.rows.shift(); u.coll.shift(); }
          if (a.gen % 10 === 0) { u.div.push(distinct(u.A)); if (u.div.length > 120) u.div.shift(); }
        });
        if (spec.exchange && a.gen % spec.exchange.every === 0) {
          const [x, y] = a.U, N = x.N, s = Math.floor(x.rng() * N), L = N >> 3;
          for (let j = s; j < s + L; j++) { const t = x.A[j % N]; x.A[j % N] = y.A[j % N]; y.A[j % N] = t; }
          a.swap = { s, L, at: a.gen };
        }
      }
      if (a.gen >= (spec.gens || 1200)) a.reset();
    };
    a.draw = () => {
      a.U.forEach((u, k) => {
        const { c, W, H } = fit(cvs[k]); c.fillStyle = '#0b1210'; c.fillRect(0, 0, W, H);
        const cw = W / u.N, rh = H / ROWS, y0 = H - u.rows.length * rh;
        u.rows.forEach((row, r) => { for (let j = 0; j < u.N; j++) if (row[j]) { c.fillStyle = geneColor(row[j], u.K, true); c.fillRect(j * cw, y0 + r * rh, Math.max(1, cw - 0.3), Math.max(1, rh)); } });
        if (u.norm === 'mixed') {
          c.strokeStyle = 'rgba(255,255,255,.35)'; c.setLineDash([3, 4]);
          for (let s = 1; s < 4; s++) { c.beginPath(); c.moveTo(s * W / 4, 0); c.lineTo(s * W / 4, H); c.stroke(); }
          c.setLineDash([]);
          c.font = `600 9px ${MONO}`; c.textAlign = 'center';
          ['norm 0', 'sum', 'random', 'norm 0'].forEach((t, s) => { const x = (s + 0.5) * W / 4, tw = c.measureText(t).width + 10;
            c.fillStyle = 'rgba(6,12,10,.85)'; c.fillRect(x - tw / 2, H - 15, tw, 13); c.fillStyle = 'rgba(255,255,255,.75)'; c.fillText(t, x, H - 5); });
        }
        if (spec.exchange && a.swap && k < 2 && a.gen - a.swap.at < 18) {
          const f = 1 - (a.gen - a.swap.at) / 18, { s, L } = a.swap;
          c.fillStyle = `rgba(215,155,255,${0.35 * f})`; c.strokeStyle = `rgba(215,155,255,${0.9 * f})`; c.lineWidth = 2;
          [[s, Math.min(L, u.N - s)], [0, Math.max(0, s + L - u.N)]].forEach(([x, w]) => { if (w > 0) { c.fillRect(x * cw, H - 14 * rh, w * cw, 14 * rh); c.strokeRect(x * cw, H - 14 * rh, w * cw, 14 * rh); } });
          c.fillStyle = `rgba(215,155,255,${f})`; c.font = `600 10px ${MONO}`; c.textAlign = 'center';
          const lbl = k === 0 ? '⇅ swapped with the other universe' : '⇅ swapped', lw = c.measureText(lbl).width / 2 + 4;
          c.fillText(lbl, Math.min(W - lw, Math.max(lw, (s + L / 2) * cw)), H - 14 * rh - 6);
        }
        // diversity trace
        const d = u.div, mx = Math.max(16, ...d);
        c.fillStyle = 'rgba(6,12,10,.8)'; c.fillRect(W - 134, 8, 130, 32);
        c.fillStyle = 'rgba(125,216,181,.8)'; c.font = `500 8.5px ${MONO}`; c.textAlign = 'left'; c.fillText('different genes', W - 130, 17);
        c.strokeStyle = JADE; c.lineWidth = 1.5; c.beginPath();
        d.forEach((v, i) => { const x = W - 130 + i * (122 / 119), y = 38 - v / mx * 18; i ? c.lineTo(x, y) : c.moveTo(x, y); }); c.stroke();
        const now = distinct(u.A), top = (() => { const m = new Map(); let n = 0; u.A.forEach(v => { if (v) { m.set(v, (m.get(v) || 0) + 1); n++; } }); return n ? Math.max(...m.values()) / n : 0; })();
        if (stats[k]) stats[k].innerHTML = `<b>${u.title}</b> · generation ${a.gen} · <span style="color:${now <= 3 ? HAZ : JADE}">${now} different genes</span> · commonest gene holds ${Math.round(top * 100)}% of cells${now <= 3 && a.gen > 150 ? ' · <span style="color:' + HAZ + '">takeover</span>' : ''}`;
      });
    };
    register(root, a);
  }

  D.BarricelliExplain = function (el) {
    const q = s => el.querySelector(s);
    zoomStrip(q('#bxe-drift'), { N: 24, init: [[2, 3]], gens: 16, secs: 0.9,
      caption: s => `Generation ${s.gen}. One gene, <b style="color:${POS}">+3</b>, alone on a ring of 24 cells: every generation it copies itself three cells to the right and the old copy is gone. It never multiplies. <span class="muted">Copies: ${s.n}.</span>` });
    zoomStrip(q('#bxe-pair'), { N: 24, init: [[2, 3], [5, -2]], gens: 14, secs: 1.25,
      caption: s => `Generation ${s.gen}. <b style="color:${POS}">+3</b> and <b style="color:${NEG}">−2</b>. When a copy lands on a cell that already holds a gene, it copies itself again, as far as <i>that</i> gene says (dashed violet paths). These two keep landing on each other, so they multiply: <b>${s.n}</b> genes now, from 2. ${s.tr && s.tr.coll.size ? `<span style="color:${HAZ}">${s.tr.coll.size} collision${s.tr.coll.size > 1 ? 's' : ''} (red) destroyed some copies.</span>` : ''}` });
    collisions(q('#bxe-coll'));
    usesGraph(q('#bxe-graph'));
    universes(q('#bxe-take'), { gps: 30, gens: 900, panels: [
      { title: 'One rule everywhere (norm 0)', N: 128, K: 8, seed: 4, norm: '0' },
      { title: 'Mixed norms by region', N: 128, K: 8, seed: 4, norm: 'mixed' }] });
    universes(q('#bxe-exch'), { gps: 30, gens: 1300, exchange: { every: 50 }, panels: [
      { title: 'Universe 1 (exchanging)', N: 128, K: 8, seed: 5, norm: 'mixed' },
      { title: 'Universe 2 (exchanging)', N: 128, K: 8, seed: 105, norm: 'mixed' },
      { title: 'Control: universe 1 on its own', N: 128, K: 8, seed: 5, norm: 'mixed' }] });
    requestAnimationFrame(loop);
  };
})();
