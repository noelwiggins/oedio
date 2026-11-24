/* Listening to Barricelli's universe. The simulation's own events become music, so his ideas can be heard:
   · Copying is a canon. Each symbioorganism gets its own recorded instrument; whenever its genes are copied into new cells,
     it plays the gene that was copied most. A gene's number is its interval: +3 moves three cells right and sounds three
     steps up the scale, −2 two steps down. So an organism repeats its own small motif wherever it multiplies.
   · Cooperation is harmony: organisms that live by landing on each other sound together, in one mode (D Dorian).
   · Parasites follow their host: they sound only when the host does, a moment late, a little out of tune.
   · Collisions: annihilation is a dry tick, fusion a struck note at the sum, a mutation a note between the keys.
   · Loose genes are a faint scatter of high piano notes that thins as organisms take over.
   · Birth announces the newcomer's motif; extinction is a low organ note and that instrument falls silent; a crossing
     interleaves the parents; self-repair rises; takeover ("organized homogeneity") is a drone; an exchange with the
     parallel universe sweeps across the stereo field. With the parallel universe on, the visible universe sounds on the
     left, its twin on the right.
   Generations run on the audio clock while listening, so every sound lands with its row on the printout. */
(function () {
  'use strict';
  const D = window.Darwin;
  D.BarricelliSound = function (api, el) {
    const btn = el.querySelector('#bx-listen'), status = el.querySelector('#bx-listen-status');
    const INST = ['marimba', 'clarinet', 'vibes', 'violin', 'piano', 'cello', 'flute', 'saxello', 'glock', 'organ', 'pipe', 'claps'];
    const VOICES = ['clarinet', 'vibes', 'violin', 'cello', 'flute', 'saxello', 'organ'];   // marimba and glockenspiel are kept for collisions
    const CENTER = { marimba: 62, clarinet: 62, vibes: 69, violin: 74, cello: 50, flute: 79, saxello: 69, organ: 57, glock: 86, piano: 62 };
    const SCALE = [0, 2, 3, 5, 7, 9, 10];
    const deg = (v, c) => c + 12 * Math.floor(v / 7) + SCALE[((v % 7) + 7) % 7];
    const fold = (m, inst) => { const r = window.Proc.INSTRUMENTS[inst].range; while (m < r[0]) m += 12; while (m > r[1]) m -= 12; return m; };
    let kit = null, on = false, timer = null, nextT = 0, T = 0, genDur = 0.15, prev = [null, null], named = 0;
    const voice = new Map();                                 // organism key → instrument
    const voiceOf = o => { if (!voice.has(o.key)) voice.set(o.key, VOICES[named++ % VOICES.length]); return voice.get(o.key); };
    const play = (inst, m, dur, vel, t, pan, shape) => kit && kit.play(inst, typeof m === 'number' ? m : 60, dur, Math.max(0.02, Math.min(1, vel)), t, pan, shape);
    const lastHost = new Map();                              // organism id → [pitch, time] of its latest note, for parasites

    api.onGeneration = () => {
      if (!on || !kit) return;
      const st = api.state(), two = st.U.length === 2, side = (x, u) => two ? (u ? 0.1 + 0.8 * x : -0.9 + 0.8 * x) : -0.85 + 1.7 * x;
      st.U.forEach((U, u) => {
        const A = U.A, N = A.length, P = prev[u], marks = U.marks;
        if (u === 0) {
          // copying: which organisms' genes appeared in new cells this generation, and where
          const stat = new Map();
          for (let j = 0; j < N; j++) {
            const v = A[j]; if (!v || (P && P[j] === v)) continue;
            const o = st.geneOrg.get(v); if (!o || !o.confirmed || !o.alive) continue;
            let s = stat.get(o.key); if (!s) stat.set(o.key, s = { o, n: 0, pos: 0, by: new Map() });
            s.n++; s.pos += j; s.by.set(v, (s.by.get(v) || 0) + 1);
          }
          [...stat.values()].sort((a, b) => b.n - a.n).slice(0, 6).forEach(s => {
            const inst = voiceOf(s.o); let g = 0, best = -1; s.by.forEach((c, v) => { if (c > best) { best = c; g = v; } });
            const m = fold(deg(g, CENTER[inst]), inst), vel = 0.32 + 0.12 * Math.log2(1 + s.n);
            play(inst, m, genDur * 1.8, vel, T, side(s.pos / s.n / N, 0));
            lastHost.set(s.o.id, [m, inst, vel]);
          });
          // parasites: heard only when their host is, a little late and a little flat
          st.parasites.slice(0, 2).forEach(p => {
            const h = lastHost.get(p.host); if (!h) return;
            play(h[1], h[0] + (p.gene > 0 ? 2 : -2) - 0.3, genDur * 1.2, h[2] * 0.5, T + genDur * 0.4, 0.35);
          });
          lastHost.clear();
        }
        // collisions, by the norm of the region they happen in
        let c0 = 0, p0 = 0, sums = [], muts = [];
        for (let j = 0; j < N; j++) if (marks[j]) {
          const nm = U.norm(j);
          if (nm === 'sum' && A[j]) sums.push([A[j], j]); else if (nm === 'random' && A[j]) muts.push([A[j], j]); else { c0++; p0 += j; }
        }
        // a light pulse: each universe takes alternate generations, and a kind of collision sounds at most every few
        if (st.gen % (two ? 2 : 1) === u) {
          if (c0 && st.gen % 4 < 2) play('claps', 60, 0.2, 0.03 + 0.012 * Math.min(c0, 8), T + genDur * 0.5, side(p0 / c0 / N, u));
          if (sums.length && st.gen % 3 === 0) { const [v, j] = sums[0]; play('marimba', fold(deg(v, 74), 'marimba'), genDur, 0.2, T + genDur * 0.25, side(j / N, u)); }
          if (muts.length && st.gen % 5 === 0) { const [v, j] = muts[0]; play('glock', fold(deg(v, 88), 'glock') + 0.5, genDur, 0.12, T + genDur * 0.75, side(j / N, u)); }
        }
        // loose genes: one faint high note, fewer as organisms take over
        let loose = 0, pick = -1; const start = (st.gen * 37) % N;
        for (let q = 0; q < N; q++) { const j = (start + q) % N, v = A[j]; if (!v) continue; const o = u === 0 ? st.geneOrg.get(v) : null; if (o && o.confirmed) continue; loose++; if (pick < 0) pick = j; }
        if (pick >= 0 && st.gen % 4 === u * 2) play('piano', fold(deg(A[pick], 86), 'piano'), genDur * 2, 0.03 + 0.1 * loose / N, T, side(pick / N, u));
        prev[u] = A.slice();
      });
    };

    api.onEvent = (kind, d) => {
      if (!on || !kit) return;
      const motif = (o, t0, gap, dir) => { const inst = voiceOf(o), g = dir ? o.genes.slice().sort((a, b) => a - b) : o.genes; g.forEach((v, i) => play(inst, fold(deg(v, CENTER[inst]), inst), 0.5, 0.55, t0 + i * gap, 0)); };
      if (kind === 'born') motif(d.o, T, 0.16);
      else if (kind === 'repair') motif(d.o, T, 0.1, true);
      else if (kind === 'cross') { (d.parents || []).slice(0, 2).forEach((p, k) => motif(p, T + k * 0.08, 0.16)); motif(d.o, T + 0.9, 0.14); }
      else if (kind === 'dead') { play('pipe', fold(deg(d.o.genes[0], 38), 'pipe'), 3.2, 0.4, T, 0); voice.delete(d.o.key); }
      else if (kind === 'parasite') { const h = [...api.state().orgs.values()].find(o => o.id === d.p.host); if (h) { const inst = voiceOf(h), m = fold(deg(h.genes[0], CENTER[inst]), inst); play(inst, m, 0.6, 0.5, T, -0.2); play(inst, m + (d.p.gene > 0 ? 2 : -2) - 0.3, 0.6, 0.3, T + 0.18, 0.4); } }
      else if (kind === 'takeover') { play('pipe', 38, 8, 0.45, T, 0, 'swell'); play('pipe', 45, 8, 0.38, T, 0, 'swell'); }
      else if (kind === 'exchange') [74, 77, 79, 81, 84, 86, 88].forEach((m, i) => play('glock', m, 0.3, 0.25, T + i * 0.06, -0.9 + i * 0.3));
    };

    function schedule() {
      const now = kit.ctx.currentTime;
      if (!api.playing) { nextT = now + 0.05; return; }
      while (nextT < now + 0.12) {
        genDur = 1 / Math.max(2, Math.min(10, api.state().gps));        // listening runs at up to ten generations a second
        T = nextT; api.tick(); nextT += genDur;
      }
    }
    function showLoading(L) {
      const wait = L.want.filter(k => !L.done.includes(k));
      status.textContent = wait.length ? `Loading recordings (${L.done.length} of ${L.want.length})…` : 'Listening. Each organism has its own instrument; the legend below says what you are hearing.';
    }
    btn.addEventListener('click', () => {
      on = !on;
      if (on) {
        if (!kit) { kit = new window.Proc.Kit(INST); kit.onload = showLoading; showLoading(kit.loading); }
        kit.ctx.resume(); api.external = true; prev = [null, null]; nextT = kit.ctx.currentTime + 0.1;
        timer = setInterval(schedule, 25); btn.textContent = 'Stop listening'; btn.classList.add('on');
      } else {
        clearInterval(timer); api.external = false; btn.textContent = 'Listen'; btn.classList.remove('on'); status.textContent = '';
      }
    });
    D.BarricelliSoundState = () => ({ on, kit, voice });
  };
})();
