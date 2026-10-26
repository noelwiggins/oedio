/* Barricelli's Symbiosis — a live reconstruction of Nils Aall Barricelli's numerical evolution experiments
   (Institute for Advanced Study, Princeton, 1953–56), running in the browser.

   Rules (after Barricelli's published norms):
   · The universe is a ring of cells. Each cell is empty or holds a non-zero integer, a "gene".
   · Shift norm: a gene n at position a copies itself to a+n in the next generation (positive genes move right,
     negative genes left).
   · Symbiotic replication: if the cell it lands on held a gene m in the current generation, it copies itself again
     to a+m; if that cell held a gene too, again, and so on (up to 6 times, never to the same cell twice).
     A gene alone just drifts. Genes that land on each other multiply: that is where cooperation starts.
   · Collision norms: when different genes arrive in the same cell, a norm decides. "0": they annihilate.
     "sum": they fuse into their sum. "random": a random new gene appears half the time (a mutation).
     "mixed": different stretches of the universe use different norms (Barricelli's remedy against takeover).
   · Optional: a parallel universe, with a stretch of cells exchanged every 50 generations (his other remedy).

   Organisms are detected, not designed: whenever gene n replicates by landing on gene m, that is a "uses" link
   n → m. Over the last 12 generations, genes that use each other in a closed loop (a strongly connected group)
   form a symbioorganism. A gene that keeps using an organism's genes without being used back is a parasite. */
(function () {
  const D = window.Darwin;
  const PALETTE = ['#7dd8b5', '#e9bf6d', '#ff8a7a', '#9ab8ff', '#d79bff', '#ffd36e', '#6fe0e8', '#f7a1c4', '#b7e36b', '#ffb07a', '#a0a7ff', '#7fe39b'];
  const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

  function mulberry(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

  function tarjan(nodes, adj) {
    let idx = 0; const I = new Map(), L = new Map(), st = [], on = new Set(), out = [];
    function sc(v) {
      I.set(v, idx); L.set(v, idx); idx++; st.push(v); on.add(v);
      for (const w of adj.get(v) || []) {
        if (!I.has(w)) { sc(w); L.set(v, Math.min(L.get(v), L.get(w))); }
        else if (on.has(w)) L.set(v, Math.min(L.get(v), I.get(w)));
      }
      if (L.get(v) === I.get(v)) { const c = []; let w; do { w = st.pop(); on.delete(w); c.push(w); } while (w !== v); out.push(c); }
    }
    nodes.forEach(v => { if (!I.has(v)) sc(v); });
    return out;
  }

  class Universe {
    constructor(o) {
      Object.assign(this, o);
      this.rng = mulberry(o.seed);
      this.vals = []; for (let v = -o.K; v <= o.K; v++) if (v) this.vals.push(v);
      this.A = new Int16Array(o.N);
      for (let i = 0; i < o.N; i++) if (this.rng() < o.density) this.A[i] = this.vals[Math.floor(this.rng() * this.vals.length)];
      this.marks = new Uint8Array(o.N);   // 1 = a collision happened here this generation
    }
    norm(j) {
      if (this.normName !== 'mixed') return this.normName;
      return ['0', 'sum', 'random', '0'][Math.floor(j * 4 / this.N)];
    }
    step(edges) {
      const N = this.N, A = this.A, hit = new Array(N);
      for (let a = 0; a < N; a++) {
        const n = A[a]; if (!n) continue;
        let t = ((a + n) % N + N) % N; (hit[t] || (hit[t] = [])).push(n);
        const seen = [t]; let m = A[t], k = 0;
        while (m && k < 6) {
          const t2 = ((a + m) % N + N) % N;
          if (seen.includes(t2)) break;
          seen.push(t2); (hit[t2] || (hit[t2] = [])).push(n);
          const key = n * 1000 + m; edges.set(key, (edges.get(key) || 0) + 1);
          m = A[t2]; k++;
        }
      }
      const B = new Int16Array(N); this.marks.fill(0);
      for (let j = 0; j < N; j++) {
        const h = hit[j]; if (!h) continue;
        let same = true; for (let q = 1; q < h.length; q++) if (h[q] !== h[0]) { same = false; break; }
        if (same) { B[j] = h[0]; continue; }
        this.marks[j] = 1;
        const nm = this.norm(j);
        if (nm === 'sum') { const u = [...new Set(h)], v = u.reduce((s, x) => s + x, 0); B[j] = (v !== 0 && Math.abs(v) <= this.K) ? v : 0; }
        else if (nm === 'random') B[j] = this.rng() < 0.5 ? this.vals[Math.floor(this.rng() * this.vals.length)] : 0;
        else B[j] = 0;
      }
      this.A = B;
    }
  }

  D.Barricelli = function (el) {
    const canvas = el.querySelector('#bx-canvas'), ctx = canvas.getContext('2d');
    const lens = el.querySelector('#bx-lens'), list = el.querySelector('#bx-orgs'), log = el.querySelector('#bx-log');
    const stat = el.querySelector('#bx-stat');
    const ctl = id => el.querySelector('#' + id);
    let U = [], gen = 0, rows = [], ROWS = 180, playing = true, edgeWin = [], orgs = new Map(), nextLetter = 0, events = [];
    let lensX = null, lastDraw = 0, acc = 0, homogeneousSince = null;
    const geneOrg = new Map();   // gene value -> organism id (current)

    function settings() {
      return { N: +ctl('bx-n').value, K: +ctl('bx-k').value, density: 0.3, normName: ctl('bx-norm').value,
               exchange: ctl('bx-ex').checked, seed: Math.floor(Math.random() * 1e9) };
    }
    function reset() {
      const s = settings();
      U = [new Universe(s)]; if (s.exchange) U.push(new Universe({ ...s, seed: s.seed + 7 }));
      gen = 0; rows = []; edgeWin = []; orgs = new Map(); nextLetter = 0; events = []; homogeneousSince = null; geneOrg.clear(); parasites = []; noted.clear(); announcedTakeover = null; lastParasiteNote = -999;
      note(`Generation 0: ${s.N} cells seeded at random with genes from −${s.K} to +${s.K} (30% full). Collision norm: ${normLabel(s.normName)}.`, 'start');
      renderList(); renderLog();
    }
    function normLabel(n) { return { '0': 'annihilate (norm 0)', sum: 'fuse into the sum', random: 'random mutation', mixed: 'mixed norms by region' }[n]; }
    function note(text, kind) { events.unshift({ gen, text, kind }); events = events.slice(0, 60); renderLog(); }

    function tick() {
      const edges = new Map();
      U.forEach((u, k) => u.step(k === 0 ? edges : new Map()));
      gen++;
      if (U.length === 2 && gen % 50 === 0) {
        const N = U[0].N, s = Math.floor(U[0].rng() * N), L = N >> 3;
        for (let j = s; j < s + L; j++) { const a = U[0].A[j % N]; U[0].A[j % N] = U[1].A[j % N]; U[1].A[j % N] = a; }
        if (gen % 250 === 0) note(`Exchanged ${L} cells with the parallel universe (Barricelli's remedy against takeover).`, 'info');
      }
      edgeWin.push(edges); if (edgeWin.length > 12) edgeWin.shift();
      rows.push({ A: U[0].A.slice(), m: U[0].marks.slice() }); if (rows.length > ROWS) rows.shift();
      if (gen % 4 === 0) census();
    }

    // ── who is alive: organisms from the "uses" graph ───────────────────
    function census() {
      const tot = new Map();
      edgeWin.forEach(e => e.forEach((k, key) => tot.set(key, (tot.get(key) || 0) + k)));
      // strong links only: a symbioorganism is genes that multiply *each other* (both directions, often)
      let sum = 0; tot.forEach(k => { sum += k; });
      const T = Math.max(8, sum * 0.004);
      const w = (n, m) => tot.get(n * 1000 + m) || 0;
      const adj = new Map(), nodes = new Set(), oneWay = [];
      tot.forEach((k, key) => {
        const n = Math.round(key / 1000), m = key - n * 1000;
        if (n === m || k < T) return;
        if (w(m, n) >= T) { if (!adj.has(n)) adj.set(n, new Set()); adj.get(n).add(m); nodes.add(n); nodes.add(m); }
        else if (w(m, n) < T / 4) oneWay.push([n, m, k]);
      });
      const comps = tarjan([...nodes], adj).filter(c => c.length >= 2).map(c => c.sort((a, b) => a - b));
      const A = U[0].A, count = new Map(); A.forEach(v => { if (v) count.set(v, (count.get(v) || 0) + 1); });
      const occupied = [...count.values()].reduce((a, b) => a + b, 0) || 1;
      const seenIds = new Set();
      geneOrg.clear();
      const matched = new Set();
      const jacc = (a, b) => { const sa = new Set(a); const inter = b.filter(x => sa.has(x)).length; return inter / (a.length + b.length - inter); };
      comps.forEach(genes => {
        const sig = genes.join(',');
        // the same organism keeps its name while its genes drift: match by overlap with a living one
        let o = null, bestJ = 0.45;
        orgs.forEach(c => { if (c.alive && !matched.has(c.key)) { const j = jacc(c.genes, genes); if (j > bestJ) { bestJ = j; o = c; } } });
        if (o) { o.genes = genes; o.sig = sig; }
        const copies = genes.reduce((s, g) => s + (count.get(g) || 0), 0);
        if (!o) {
          // a new symbioorganism: is it a cross between two existing ones?
          const parents = [...orgs.values()].filter(p => p.alive && p.confirmed && p.genes.some(g => genes.includes(g)) && !p.genes.every(g => genes.includes(g)) && !genes.every(g => p.genes.includes(g)));
          o = { key: 'k' + (++candidates), sig, genes, id: '?', color: '#888',
                born: gen, peak: 0, alive: true, copies: 0, hist: [], parents: parents.map(p => p.id), confirmed: false, dips: null };
          orgs.set(o.key, o);
        }
        o.copies = copies; o.peak = Math.max(o.peak, copies); o.alive = true; o.last = gen; o.hist.push(copies); if (o.hist.length > 60) o.hist.shift();
        o.share = copies / occupied;
        seenIds.add(o.key); matched.add(o.key);
        if (!o.confirmed && gen - o.born >= 20 && copies >= 6) {
          o.confirmed = true;     // named only once it has proved it can persist
          o.id = LETTERS[nextLetter % 26] + (nextLetter >= 26 ? Math.floor(nextLetter / 26) : ''); o.color = PALETTE[nextLetter % PALETTE.length]; nextLetter++;
          if (o.parents.length >= 2) note(`Crossing: organism ${o.id} (${fmt(o.genes)}) formed from parts of ${o.parents.slice(0, 2).join(' and ')}.`, 'cross');
          else note(`New symbioorganism ${o.id}: genes ${fmt(o.genes)} that can only multiply by landing on each other.`, 'born');
        }
        // self-repair: lost more than half its copies, then grew back
        if (o.confirmed && o.hist.length > 20) {
          const recent = o.hist.slice(-20), lo = Math.min(...recent), hi0 = recent[0];
          if (!o.dips && lo < hi0 * 0.45 && hi0 > 12) o.dips = { at: gen, lo, from: hi0 };
          if (o.dips && copies >= o.dips.from * 0.85 && gen - o.dips.at < 120) { note(`Self-repair: ${o.id} fell from ${o.dips.from} to ${o.dips.lo} copies and grew back.`, 'repair'); o.dips = null; }
          if (o.dips && gen - o.dips.at >= 120) o.dips = null;
        }
        genes.forEach(g => geneOrg.set(g, o));
      });
      orgs.forEach(o => {
        if (o.alive && !seenIds.has(o.key) && gen - o.last > 16) {
          o.alive = false;
          if (o.confirmed) note(`Organism ${o.id} (${fmt(o.genes)}) went extinct after ${gen - o.born} generations.`, 'dead');
        }
      });
      // parasites: genes that use an organism's genes but are not used back
      parasites = []; const pseen = new Set();
      oneWay.forEach(([g, m]) => {
        if (geneOrg.has(g) || pseen.has(g)) return;
        const host = geneOrg.get(m);
        if (host && host.confirmed && (count.get(g) || 0) >= 3) { pseen.add(g); parasites.push({ gene: g, host: host.id, copies: count.get(g) }); }
      });
      parasites.sort((a, b) => b.copies - a.copies);
      if (parasites[0] && !noted.has('p' + parasites[0].gene + parasites[0].host) && parasites[0].copies >= 6 && gen - lastParasiteNote > 60) {
        lastParasiteNote = gen;
        noted.add('p' + parasites[0].gene + parasites[0].host);
        note(`Parasite: gene ${sign(parasites[0].gene)} multiplies by riding on organism ${parasites[0].host}, which gains nothing from it.`, 'parasite');
      }
      const top = [...orgs.values()].filter(o => o.alive && o.confirmed).sort((a, b) => b.copies - a.copies)[0];
      if (top && top.share > 0.9) {
        if (announcedTakeover !== top.key) { announcedTakeover = top.key; note(`Takeover: organism ${top.id} now fills ${Math.round(top.share * 100)}% of the universe. Barricelli called this "organized homogeneity" and fought it with mixed norms and exchanges.`, 'takeover'); }
      } else if (!top || top.share < 0.7) announcedTakeover = null;
      renderList();
      stat.textContent = `generation ${gen.toLocaleString()} · ${occupied} genes alive · ${[...orgs.values()].filter(o => o.alive && o.confirmed).length} symbioorganisms · ${parasites.length} parasites`;
    }
    let candidates = 0, parasites = [], lastParasiteNote = -999, announcedTakeover = null; const noted = new Set();
    const sign = v => (v > 0 ? '+' : '−') + Math.abs(v);
    const fmt = g => g.map(sign).join(' ');

    // ── drawing: the printout, newest generation at the bottom ──────────
    function colorFor(v) {
      const o = geneOrg.get(v);
      if (o && o.confirmed) return o.color;
      const l = 16 + Math.abs(v) / (U[0] ? U[0].K : 16) * 14;   // loose genes stay dim so organisms stand out
      return v > 0 ? `hsl(28 12% ${l}%)` : `hsl(210 12% ${l}%)`;
    }
    function draw() {
      const dpr = Math.min(2, window.devicePixelRatio || 1), W = canvas.clientWidth, H = canvas.clientHeight;
      if (canvas.width !== Math.round(W * dpr) || canvas.height !== Math.round(H * dpr)) { canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = '#0b1210'; ctx.fillRect(0, 0, W, H);
      if (!rows.length) return;
      const N = rows[0].A.length, cw = W / N, rh = H / ROWS, y0 = H - rows.length * rh;
      rows.forEach((r, k) => {
        const y = y0 + k * rh;
        for (let j = 0; j < N; j++) {
          const v = r.A[j];
          if (v) { ctx.fillStyle = colorFor(v); ctx.fillRect(j * cw, y, Math.max(1, cw - (cw > 2.5 ? 0.4 : 0)), Math.max(1, rh)); }
          else if (r.m[j] && k > rows.length - 40) { ctx.fillStyle = 'rgba(255,255,255,.35)'; ctx.fillRect(j * cw + cw / 2 - 0.5, y + rh / 2 - 0.5, 1, 1); }
        }
      });
      if (ctl('bx-norm').value === 'mixed') {   // region boundaries
        ctx.strokeStyle = 'rgba(255,255,255,.45)'; ctx.setLineDash([3, 4]);
        for (let s = 1; s < 4; s++) { const x = s * W / 4; ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
        ctx.setLineDash([]);
        ctx.font = '600 10px "IBM Plex Mono", monospace'; ctx.textAlign = 'center';
        ['norm 0', 'sum', 'random', 'norm 0'].forEach((t, s) => {
          const x = (s + 0.5) * W / 4, tw = ctx.measureText(t.toUpperCase()).width + 12;
          ctx.fillStyle = 'rgba(6,12,10,.8)'; ctx.fillRect(x - tw / 2, 4, tw, 16);
          ctx.fillStyle = 'rgba(255,255,255,.75)'; ctx.fillText(t.toUpperCase(), x, 15);
        });
      }
      // call-outs: each living organism, at its densest stretch of the newest generation
      const live = [...orgs.values()].filter(o => o.alive && o.confirmed).sort((a, b) => b.copies - a.copies).slice(0, 5);
      const last = rows[rows.length - 1].A, used = [];
      live.forEach((o, rank) => {
        const set = new Set(o.genes), win = Math.max(8, Math.round(N / 24));
        let best = -1, bx = 0, run = 0;
        for (let j = 0; j < N + win; j++) { run += set.has(last[j % N]) ? 1 : 0; if (j >= win) run -= set.has(last[(j - win) % N]) ? 1 : 0; if (run > best && j >= win) { best = run; bx = (j - win / 2) % N; } }
        if (best <= 0) return;
        let x = bx * cw;
        const label = `${o.id} · ${fmt(o.genes)} · ${o.copies} genes`;
        ctx.font = '600 11px "IBM Plex Mono", monospace';
        const tw = ctx.measureText(label).width + 14;
        let lx = Math.min(W - tw - 4, Math.max(4, x - tw / 2)), ly = H - 34 - rank * 26;
        while (used.some(u => Math.abs(u.y - ly) < 24 && Math.abs(u.x - lx) < tw)) ly -= 26;
        used.push({ x: lx, y: ly });
        ctx.strokeStyle = o.color; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(x, H - 2); ctx.lineTo(x, ly + 18); ctx.stroke();
        ctx.beginPath(); ctx.arc(x, H - 3, 3, 0, 7); ctx.fillStyle = o.color; ctx.fill();
        ctx.fillStyle = 'rgba(6,12,10,.86)'; ctx.fillRect(lx, ly, tw, 18);
        ctx.strokeRect(lx, ly, tw, 18);
        ctx.fillStyle = o.color; ctx.textAlign = 'left'; ctx.fillText(label, lx + 7, ly + 13);
      });
      // the lens: the newest generation as Barricelli's printout showed it, as numbers
      const cx = lensX == null ? Math.floor(N / 2) : lensX, half = 24, cells = [];
      for (let j = cx - half; j < cx + half; j++) { const jj = ((j % N) + N) % N, v = last[jj], o = geneOrg.get(v); cells.push(v ? `<span style="color:${o && o.confirmed ? o.color : 'inherit'}">${v > 0 ? '+' : '−'}${Math.abs(v)}</span>` : '<span class="e">·</span>'); }
      lens.innerHTML = `<span class="muted">cells ${((cx - half) % N + N) % N}–${((cx + half - 1) % N + N) % N}:</span> ` + cells.join(' ');
      if (lensX != null) { ctx.strokeStyle = 'rgba(255,255,255,.4)'; ctx.strokeRect((cx - half) * cw, H - rh * 3, half * 2 * cw, rh * 3); }
    }

    function renderList() {
      const live = [...orgs.values()].filter(o => o.confirmed).sort((a, b) => (b.alive - a.alive) || (b.copies - a.copies)).slice(0, 14);
      list.innerHTML = live.length ? live.map(o => {
        const spark = o.hist.length > 1 ? (() => { const mx = Math.max(...o.hist, 1); return `<svg viewBox="0 0 60 18" class="bx-spark"><polyline fill="none" stroke="${o.color}" stroke-width="1.5" points="${o.hist.map((h, i) => `${(i / (o.hist.length - 1) * 60).toFixed(1)},${(17 - h / mx * 16).toFixed(1)}`).join(' ')}"/></svg>`; })() : '';
        return `<div class="bx-org ${o.alive ? '' : 'gone'}"><i style="background:${o.color}"></i><b>${o.id}</b>
          <span class="mono">${fmt(o.genes)}</span>${spark}
          <span class="small muted">${o.alive ? `${o.copies} genes · ${Math.round((o.share || 0) * 100)}%` : 'extinct'} · since gen ${o.born}${o.parents.length >= 2 ? ` · cross of ${o.parents.slice(0, 2).join('×')}` : ''}</span></div>`;
      }).join('') + (parasites.length ? `<div class="small" style="margin-top:8px"><b>Parasites:</b> ${parasites.slice(0, 5).map(p => `gene ${sign(p.gene)} on ${p.host} (${p.copies})`).join(' · ')}</div>` : '')
        : '<p class="small muted">None yet. Watch the first few hundred generations: most random genes die out, and the survivors are groups that multiply by landing on each other.</p>';
    }
    function renderLog() {
      log.innerHTML = events.map(e => `<div class="bx-ev ${e.kind}"><span class="mono small muted">gen ${e.gen}</span> ${D.esc(e.text)}</div>`).join('');
    }

    canvas.addEventListener('pointermove', e => { const r = canvas.getBoundingClientRect(); if (U[0]) lensX = Math.floor((e.clientX - r.left) / r.width * U[0].N); });
    canvas.addEventListener('pointerleave', () => { lensX = null; });
    ctl('bx-play').onclick = () => { playing = !playing; ctl('bx-play').textContent = playing ? 'Pause' : 'Play'; };
    ctl('bx-step').onclick = () => { playing = false; ctl('bx-play').textContent = 'Play'; tick(); };
    ctl('bx-reset').onclick = reset;
    ['bx-n', 'bx-k', 'bx-norm', 'bx-ex'].forEach(id => ctl(id).addEventListener('change', reset));
    function loop(ts) {
      const gps = +ctl('bx-speed').value, dt = Math.min(0.25, (ts - (lastDraw || ts)) / 1000); lastDraw = ts;
      if (playing && !document.hidden) { acc += dt * gps; let n = 0; while (acc >= 1 && n < 40) { tick(); acc -= 1; n++; } }
      draw(); requestAnimationFrame(loop);
    }
    reset(); requestAnimationFrame(loop);
  };
})();
