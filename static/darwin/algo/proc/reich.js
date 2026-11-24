/* AlgoReich: four of Steve Reich's processes, as a deterministic score. The processes are his; every pattern and chord here
   is written from rules, not taken from his pieces.
   · Phase (after Piano Phase): two players repeat the same twelve-note pattern; one gradually pulls ahead until it is a full
     note ahead, holds there, pulls ahead again, until the two are back in unison; then the pattern shortens to eight, four.
   · Clapping (after Clapping Music): a twelve-beat rhythm; one player stays put, the other moves one beat on each section.
   · Build-up (after Drumming): a pattern assembled one beat at a time out of silence, a second player building the same
     pattern a few beats away, voices picking out the melodies that result, then the first player taken apart again.
   · Pulses (after Music for 18 Musicians): a cycle of eleven chords, each held as pulsing eighths that swell and fade with
     the length of a breath, a vibraphone calling each change. */
(function () {
  'use strict';
  const { rng } = window.Proc;
  const fold = (m, inst) => { const r = window.Proc.INSTRUMENTS[inst].range; while (m < r[0]) m += 12; while (m > r[1]) m -= 12; return m; };
  const pick = (ens, pref) => pref.find(x => ens.includes(x)) || ens[0];
  // twelve-beat rhythms of eight claps in four groups; Clapping Music's own grouping and its rotations are left out
  const GROUPS = [[3, 2, 2, 1], [2, 2, 1, 3], [2, 1, 3, 2], [1, 3, 2, 2], [3, 1, 2, 2], [1, 2, 2, 3], [2, 2, 3, 1], [2, 3, 1, 2]];
  const rhythm = g => { const r = []; for (const n of g) { for (let i = 0; i < n; i++) r.push(1); r.push(0); } return r; };
  // the cycle of eleven chords (original voicings around A major and F♯ minor)
  const CYCLE = [
    ['A add9', [45, 57, 61, 64, 71, 73]], ['D/F♯', [42, 54, 62, 66, 69, 76]], ['Bm11', [47, 54, 59, 62, 64, 69]], ['E/G♯', [44, 56, 64, 68, 71, 76]],
    ['F♯m add9', [42, 57, 61, 66, 68, 73]], ['Dmaj9', [38, 57, 61, 64, 66, 69]], ['C♯m7', [37, 56, 61, 64, 68, 71]], ['Bm9', [35, 54, 61, 62, 66, 69]],
    ['Esus4', [40, 57, 59, 64, 69, 71]], ['F♯m7 add11', [42, 57, 59, 64, 66, 73]], ['A add9/C♯', [37, 57, 59, 64, 69, 73]],
  ];
  const MODE = [64, 66, 71, 73, 74, 76, 78];               // the phase patterns' pitches: an E-centred mode, high on the piano

  class ReichScore {
    constructor(seed) { this.seed = seed; this.R = rng(seed ^ 0x2e1c); this.step = 0; this.ctl = { piece: 'phase', tempo: 76, hold: 8, drift: 96, breaths: 6, ens: [] }; this.st = {}; }
    stepSec() { return 15 / this.ctl.tempo; }               // a sixteenth note
    advance() {
      const P = this.ctl.piece, notes = [];
      if (this.st.piece !== P) this.st = { piece: P };      // a new process starts from its beginning
      const view = this[P](notes);
      this.step++;
      return { step: this.step - 1, notes, view };
    }
    // ── phase ──
    newPhasePattern(L) {
      const R = this.R, low = MODE.slice(0, 4), high = MODE.slice(3), a = [], b = [];
      for (let i = 0; i < Math.ceil(L / 2); i++) a.push(low[Math.floor(R() * low.length)]);
      for (let i = 0; i < Math.floor(L / 2); i++) b.push(high[Math.floor(R() * high.length)]);
      const p = []; for (let i = 0; i < L; i++) p.push(i % 2 ? b[(i - 1) / 2] : a[i / 2]);
      return p;
    }
    phase(notes) {
      const S = this.st, c = this.ctl, ens = c.ens;
      if (!S.pat) { S.sec = 0; S.L = 12; S.pat = this.newPhasePattern(12); S.phi = 0; S.mode = 'lock'; S.t = 0; S.from = 0; }
      const L = S.L, n = this.step, iA = pick(ens, ['piano', 'marimba', 'vibes']), iB = pick(ens.filter(x => x !== iA).length ? ens : [iA], ['piano', 'marimba', 'vibes', iA]);
      const instB = ens.includes('piano') && iA === 'piano' ? 'piano' : iB;
      const phiAt = t => S.mode === 'drift' ? S.from + Math.min(1, t / c.drift) : S.phi;
      notes.push([iA, fold(S.pat[n % L], iA), 0.9, 0.55, 'A', 0, -0.55]);
      const p0 = n + phiAt(S.t), p1 = n + 1 + phiAt(S.t + 1);
      for (let k = Math.ceil(p0 - 1e-9); k < p1 - 1e-9; k++) notes.push([instB, fold(S.pat[((k % L) + L) % L], instB), 0.9, 0.55, 'B', (k - p0) / (p1 - p0), 0.55]);
      S.t++;
      if (S.mode === 'lock' && S.t >= c.hold * L) { S.mode = 'drift'; S.t = 0; S.from = S.phi; }
      else if (S.mode === 'drift' && S.t >= c.drift) {
        S.mode = 'lock'; S.t = 0; S.phi = S.from + 1;
        if (S.phi >= L) {                                  // back in unison: the pattern shortens, or a new one begins
          S.phi = 0; S.sec = (S.sec + 1) % 3; S.L = [12, 8, 4][S.sec]; S.pat = S.sec ? S.pat.slice(0, S.L).map((m, i) => i % 2 ? m + 2 : m) : this.newPhasePattern(12);
        }
      }
      return { piece: 'phase', L, pat: S.pat, phi: phiAt(S.t), posA: n % L, mode: S.mode, sec: S.sec, insts: [iA, instB] };
    }
    // ── clapping ──
    clapping(notes) {
      const S = this.st, c = this.ctl, ens = c.ens, R = this.R;
      if (!S.r) { S.r = rhythm(GROUPS[Math.floor(R() * GROUPS.length)]); S.shift = 0; S.t = 0; }
      const n = this.step, k = n % 12, inst = ens.includes('claps') ? 'claps' : pick(ens, ['marimba', 'glock', 'piano']);
      const pitchA = inst === 'claps' ? 60 : fold(64, inst), pitchB = inst === 'claps' ? 60 : fold(71, inst);
      if (S.r[k]) notes.push([inst, pitchA, 0.8, k === 0 ? 0.75 : 0.6, 'A', 0, -0.45]);
      if (S.r[(k + S.shift) % 12]) notes.push([inst, pitchB, 0.8, (k + S.shift) % 12 === 0 ? 0.75 : 0.6, 'B', 0, 0.45]);
      S.t++;
      if (S.t >= c.hold * 12) { S.t = 0; S.shift++; if (S.shift > 12) { S.shift = 0; S.r = rhythm(GROUPS[Math.floor(R() * GROUPS.length)]); } }
      return { piece: 'clapping', r: S.r, shift: S.shift % 12, k, section: S.shift + 1, rep: Math.floor(S.t / 12) + 1 };
    }
    // ── build-up ──
    buildup(notes) {
      const S = this.st, c = this.ctl, ens = c.ens, R = this.R;
      const fam = ['marimba', 'glock', 'vibes', 'piano'].filter(x => ens.includes(x)); if (!fam.length) fam.push(ens[0]);
      if (!S.r) {
        S.r = rhythm(GROUPS[Math.floor(R() * GROUPS.length)]); const pen = [61, 64, 66, 68, 71, 73];
        S.pitch = S.r.map(x => x ? pen[Math.floor(R() * pen.length)] : 0);
        const on = S.r.map((x, i) => x ? i : -1).filter(i => i >= 0), order = [on[0]], rest = on.slice(1);
        while (rest.length) order.push(rest.splice(Math.floor(R() * rest.length), 1)[0]);
        S.order = order; S.a = 1; S.b = 0; S.sh = 2 + Math.floor(R() * 3); S.stage = 'build A'; S.t = 0; S.fam = (S.fam || 0); S.voice = [];
      }
      const inst = fam[S.fam % fam.length], k = this.step % 12, hasA = S.order.slice(0, S.a), hasB = S.order.slice(0, S.b);
      if (hasA.includes(k)) notes.push([inst, fold(S.pitch[k], inst), 1, 0.55, 'A', 0, -0.5]);
      const kb = (k - S.sh + 12) % 12; if (hasB.includes(kb)) notes.push([inst, fold(S.pitch[kb], inst), 1, 0.5, 'B', 0, 0.5]);
      if (S.stage === 'voices' && S.voice.includes(k)) {   // voices sing a melody that the two patterns make together
        const v = pick(ens, ['choir', 'clarinet', 'flute', 'violin']); const m = hasA.includes(k) ? S.pitch[k] : S.pitch[kb];
        if (m && v) notes.push([v, fold(m, v), 3, 0.45, 'voice', 0, 0]);
      }
      S.t++;
      const every = S.stage === 'voices' ? c.hold * 12 : Math.max(12, c.hold * 3);   // a beat added every couple of bars
      if (S.t >= every) {
        S.t = 0;
        if (S.stage === 'build A') { if (++S.a >= S.order.length) S.stage = 'build B'; }
        else if (S.stage === 'build B') { if (++S.b >= S.order.length) { S.stage = 'voices'; S.vt = 0; const both = []; for (let i = 0; i < 12; i++) if (hasA.includes(i) || S.order.includes((i - S.sh + 12) % 12)) both.push(i); S.voice = both.filter((_, i) => i % 3 === 0).slice(0, 4); } }
        else if (S.stage === 'voices') { if (++S.vt >= 3) S.stage = 'reduce'; }
        else if (S.stage === 'reduce') { if (--S.a <= 0) { S.r = null; S.fam++; } }
      }
      return { piece: 'buildup', r: S.r || [], order: S.order, a: S.a, b: S.b, sh: S.sh, k, stage: S.stage, voice: S.voice, inst };
    }
    // ── pulses ──
    pulses(notes) {
      const S = this.st, c = this.ctl, ens = c.ens;
      if (S.ci === undefined) { S.ci = 0; S.t = 0; }
      const B = 24, secLen = c.breaths * B, [name, ch] = CYCLE[S.ci], [, next] = CYCLE[(S.ci + 1) % CYCLE.length];
      const tb = S.t % B, env = Math.sin(Math.PI * (tb + 0.5) / B);             // a breath: swell and fade
      const pul = ['piano', 'marimba'].filter(x => ens.includes(x)); if (!pul.length) pul.push(pick(ens, ['vibes', 'glock', 'organ']));
      if (S.t % 2 === 0) pul.forEach((p, i) => { const tones = i ? ch.slice(1, 4) : ch.slice(3); tones.forEach((m, j) => notes.push([p, fold(m, p), 1.6, 0.2 + 0.4 * env, 'pulse', i ? 1 : 0, i ? 0.45 : -0.45])); });
      if (tb === 0) {                                      // the breathing instruments: one swell per breath
        const winds = ['clarinet', 'choir', 'cello', 'violin', 'organ'].filter(x => ens.includes(x));
        winds.forEach((w, i) => { const tones = w === 'cello' ? [ch[0]] : w === 'violin' ? [ch[5]] : i % 2 ? [ch[2], ch[4]] : [ch[1], ch[3]]; tones.forEach(m => notes.push([w, fold(m, w), B - 1, 0.55, 'breath', 0, i % 2 ? 0.3 : -0.3, 'swell'])); });
      }
      if (S.t === secLen - B && ens.includes('vibes')) [3, 4, 5, 4].forEach((j, i) => notes.push(['vibes', fold(next[j], 'vibes'), 3, 0.6, 'cue', i * 3, 0.2]));
      S.t++;
      if (S.t >= secLen) { S.t = 0; S.ci = (S.ci + 1) % CYCLE.length; }
      return { piece: 'pulses', ci: S.ci, name, env, t: S.t, secLen, names: CYCLE.map(x => x[0]) };
    }
  }

  // ── pictures ──
  const COL = { piano: '#e9e4d8', marimba: '#d98b4f', vibes: '#7fb7d9', glock: '#f2d16b', claps: '#f3efe6', organ: '#b98be0', clarinet: '#6fc2a6', flute: '#9ad7e8', violin: '#e06f6f', cello: '#b4514f', choir: '#f0b8d0' };
  function flash(s, part) { const at = s.at; if (!at) return 0; let f = 0; for (const e of s.timeline.slice(-8)) for (const n of e.notes) if (n[4] === part) { const age = s.now - (e.t + (n[5] || 0) * e.d); if (age >= 0 && age < 0.4) f = Math.max(f, 1 - age / 0.4); } return f; }
  function draw(cx, W, H, s) {
    cx.fillStyle = '#07090c'; cx.fillRect(0, 0, W, H);
    const v = s.at && s.at.view, sc = W / 1000;
    if (!v) { cx.fillStyle = 'rgba(255,255,255,.55)'; cx.font = `${18 * sc}px "IBM Plex Sans", sans-serif`; cx.textAlign = 'center'; cx.fillText('Press Play', W / 2, H / 2); return; }
    cx.font = `${13 * sc}px "IBM Plex Sans", sans-serif`; cx.textAlign = 'center'; cx.fillStyle = 'rgba(255,255,255,.55)';
    if (v.piece === 'phase') {
      // two rings of the same pattern; the inner one turns as the second player pulls ahead
      const x0 = W / 2, y0 = H / 2, R1 = Math.min(W, H) * 0.38, R2 = R1 * 0.7, L = v.L;
      const cur = [v.posA, Math.floor(v.posA + v.phi + 1e-6) % L], pts = [];
      [[R1, 0, '#e9e4d8', 'A'], [R2, v.phi, '#e8a23a', 'B']].forEach(([R, rot, col, part], ring) => {
        cx.strokeStyle = 'rgba(255,255,255,.12)'; cx.lineWidth = 1; cx.beginPath(); cx.arc(x0, y0, R, 0, Math.PI * 2); cx.stroke();
        const f = flash(s, part);
        for (let i = 0; i < L; i++) {
          const a = (i - rot) / L * Math.PI * 2 - Math.PI / 2, on = i === cur[ring], r = (5 + (v.pat[i] - 60) * 0.5) * sc * (on ? 1 + 0.5 * f : 1), x = x0 + Math.cos(a) * R, y = y0 + Math.sin(a) * R;
          cx.fillStyle = col; cx.globalAlpha = on ? 0.55 + 0.45 * f : 0.28; cx.beginPath(); cx.arc(x, y, r, 0, Math.PI * 2); cx.fill();
          if (on) pts.push([x, y, v.pat[i]]);
        }
        cx.globalAlpha = 1;
      });
      if (pts.length === 2) { cx.strokeStyle = pts[0][2] === pts[1][2] ? 'rgba(255,255,255,.8)' : 'rgba(255,255,255,.25)'; cx.lineWidth = 1.5 * sc; cx.beginPath(); cx.moveTo(pts[0][0], pts[0][1]); cx.lineTo(pts[1][0], pts[1][1]); cx.stroke(); }
      const a = v.posA / L * Math.PI * 2 - Math.PI / 2; cx.strokeStyle = 'rgba(255,255,255,.5)'; cx.lineWidth = 2 * sc; cx.beginPath(); cx.moveTo(x0, y0); cx.lineTo(x0 + Math.cos(a) * R1 * 1.08, y0 + Math.sin(a) * R1 * 1.08); cx.stroke();
      cx.fillStyle = 'rgba(255,255,255,.55)'; cx.fillText(`${L}-note pattern · ${v.mode === 'drift' ? 'drifting' : 'locked'} ${v.phi.toFixed(2)} notes apart`, x0, H * 0.97);
    } else if (v.piece === 'clapping') {
      const cw = W * 0.8 / 12, x0 = W * 0.1;
      [['A', 0, -0.12], ['B', v.shift, 0.12]].forEach(([part, sh, dy]) => {
        for (let i = 0; i < 12; i++) { const on = v.r[(i + sh) % 12], cur = i === v.k; cx.fillStyle = on ? (cur ? `rgba(243,239,230,${0.5 + 0.5 * flash(s, part)})` : 'rgba(243,239,230,.35)') : 'rgba(255,255,255,.06)'; cx.fillRect(x0 + i * cw + 3 * sc, H * (0.5 + dy) - cw * 0.4, cw - 6 * sc, cw * 0.8); }
      });
      cx.fillText(`Section ${v.section} of 13 · the second player ${v.shift ? v.shift + ' beat' + (v.shift > 1 ? 's' : '') + ' on' : 'in unison'} · repetition ${v.rep}`, W / 2, H * 0.12);
    } else if (v.piece === 'buildup') {
      const cw = W * 0.8 / 12, x0 = W * 0.1;
      for (let i = 0; i < 12; i++) {
        const inA = v.order && v.order.slice(0, v.a).includes(i), inB = v.order && v.order.slice(0, v.b).includes((i - v.sh + 12) % 12), cur = i === v.k;
        cx.fillStyle = inA ? COL[v.inst] : 'rgba(255,255,255,.06)'; cx.globalAlpha = inA ? (cur ? 1 : 0.5) : 1; cx.fillRect(x0 + i * cw + 3 * sc, H * 0.36, cw - 6 * sc, cw * 0.7);
        cx.fillStyle = inB ? COL[v.inst] : 'rgba(255,255,255,.06)'; cx.globalAlpha = inB ? (cur ? 1 : 0.5) : 1; cx.fillRect(x0 + i * cw + 3 * sc, H * 0.36 + cw, cw - 6 * sc, cw * 0.7);
        if (v.stage === 'voices' && v.voice.includes(i)) { cx.globalAlpha = 0.9; cx.fillStyle = COL.choir; cx.beginPath(); cx.arc(x0 + (i + 0.5) * cw, H * 0.3, 6 * sc, 0, Math.PI * 2); cx.fill(); }
      }
      cx.globalAlpha = 1; cx.fillStyle = 'rgba(255,255,255,.55)';
      cx.fillText({ 'build A': 'The pattern builds, one beat at a time', 'build B': 'A second player builds it, ' + v.sh + ' beats away', voices: 'Voices sing what the two make together', reduce: 'The first player falls away' }[v.stage], W / 2, H * 0.12);
    } else {
      const x0 = W / 2, y0 = H / 2, R = Math.min(W, H) * 0.36, N = v.names.length;
      for (let i = 0; i < N; i++) {
        const a0 = i / N * Math.PI * 2 - Math.PI / 2, a1 = a0 + Math.PI * 2 / N - 0.04, on = i === v.ci;
        cx.strokeStyle = on ? 'rgba(127,183,217,.95)' : 'rgba(255,255,255,.15)'; cx.lineWidth = (on ? 10 : 5) * sc;
        cx.beginPath(); cx.arc(x0, y0, R, a0, on ? a0 + (a1 - a0) * v.t / v.secLen : a1); cx.stroke();
        if (on) { cx.globalAlpha = 0.2; cx.beginPath(); cx.arc(x0, y0, R, a0, a1); cx.stroke(); cx.globalAlpha = 1; }
      }
      cx.fillStyle = `rgba(240,184,208,${0.15 + 0.5 * v.env})`; cx.beginPath(); cx.arc(x0, y0, R * (0.25 + 0.35 * v.env), 0, Math.PI * 2); cx.fill();
      cx.fillStyle = 'rgba(255,255,255,.85)'; cx.font = `${18 * sc}px "IBM Plex Sans", sans-serif`; cx.fillText(v.names[v.ci], x0, y0 + 6 * sc);
      cx.font = `${12 * sc}px "IBM Plex Sans", sans-serif`; cx.fillStyle = 'rgba(255,255,255,.5)'; cx.fillText(`Chord ${v.ci + 1} of ${N}`, x0, H * 0.06);
    }
  }

  const INSTS = ['piano', 'marimba', 'vibes', 'glock', 'claps', 'clarinet', 'flute', 'choir', 'violin', 'cello', 'organ'];
  window.addEventListener('DOMContentLoaded', () => window.Proc.start({
    name: 'algoreich', Score: ReichScore, seed: 1967, instruments: INSTS,
    defaults: { piece: 'phase', tempo: 76, hold: 8, drift: 96, breaths: 6, ens: ['piano', 'marimba', 'vibes', 'glock', 'claps', 'clarinet', 'choir', 'violin', 'cello'], vol: {} },
    controls: [
      { type: 'seg', key: 'piece', label: 'Process', options: [['phase', 'Phase'], ['clapping', 'Clapping'], ['buildup', 'Build-up'], ['pulses', 'Pulses']] },
      { type: 'range', key: 'tempo', label: 'Tempo', min: 50, max: 120, fmt: x => x + ' BPM' },
      { type: 'range', key: 'hold', label: 'Repeats', min: 2, max: 16, fmt: x => x + ' times', hint: 'How long each stage holds before the process moves on' },
      { type: 'range', key: 'drift', label: 'Drift', min: 24, max: 240, step: 12, fmt: x => x < 60 ? 'quick' : x < 150 ? 'gradual' : 'very slow', hint: 'Phase: how slowly the second player pulls a note ahead' },
      { type: 'range', key: 'breaths', label: 'Breaths', min: 3, max: 12, fmt: x => x + ' per chord', hint: 'Pulses: how many breaths each chord lasts' },
    ],
    describe: s => ({ phase: 'Two players, one pattern. One holds steady; the other drifts ahead a note at a time until they meet again.',
      clapping: 'One rhythm, two players. After each section the second moves one beat on; thirteen sections bring them home.',
      buildup: 'A pattern grows out of silence a beat at a time; a second player builds it a few beats away; voices pick out what results.',
      pulses: 'A cycle of eleven chords. Each pulses in eighths and breathes; a vibraphone calls the change.' })[s.piece],
    draw,
  }));
  window.ReichScore = ReichScore;
})();
