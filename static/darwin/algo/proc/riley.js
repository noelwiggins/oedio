/* AlgoRiley: three of Terry Riley's processes, as a deterministic score.
   · In C: a steady high pulse; a book of short patterns (written here from rules, not Riley's 53); each player repeats a
     pattern as long as they like, moves on at their own pace, never strays far from the others, sometimes rests, and the
     performance ends when everyone has reached the last pattern. Then a new book and a new performance.
   · Time-lag accumulator (A Rainbow in Curved Air, Poppy Nogood): a modal organ ostinato that changes one note at a time,
     a drone, and a soprano sax improvising into two feedback tape loops that pile its phrases into canons.
   · New Albion (The Harp of New Albion): a piano retuned in just intonation, slow arpeggios ringing under the pedal. */
(function () {
  'use strict';
  const { rng } = window.Proc;
  const MODES = [['Dorian', [0, 2, 3, 5, 7, 9, 10]], ['Mixolydian', [0, 2, 4, 5, 7, 9, 10]], ['Aeolian', [0, 2, 3, 5, 7, 8, 10]], ['Lydian', [0, 2, 4, 6, 7, 9, 11]], ['Phrygian', [0, 1, 3, 5, 7, 8, 10]]];
  const NAMES = ['C', 'C♯', 'D', 'E♭', 'E', 'F', 'F♯', 'G', 'A♭', 'A', 'B♭', 'B'];
  // the book's journey: C major, then F♯ and the pull to G, long tones, B♭, fast figures, E minor, and home to G and F
  const STAGES = [
    { n: 7, pcs: [0, 4, 5, 7], durs: [1, 1, 1, 2, 2, 3, 4], rest: 0.08, lo: 60, hi: 72 },
    { n: 6, pcs: [0, 2, 4, 5, 7, 11], durs: [0.5, 1, 1, 2, 2, 4, 6], rest: 0.1, lo: 62, hi: 76 },
    { n: 8, pcs: [2, 4, 6, 7, 9, 11], durs: [0.5, 1, 1, 1, 2, 2, 4], rest: 0.12, lo: 62, hi: 79 },
    { n: 7, pcs: [7, 9, 11, 0, 2, 4, 6], durs: [2, 4, 6, 8, 12], rest: 0.05, lo: 59, hi: 74 },
    { n: 7, pcs: [5, 7, 10, 0, 2, 4], durs: [1, 1, 2, 2, 3, 4], rest: 0.12, lo: 60, hi: 77 },
    { n: 7, pcs: [0, 2, 4, 5, 7, 9, 10], durs: [0.5, 0.5, 0.5, 1, 1, 2], rest: 0.08, lo: 64, hi: 81 },
    { n: 7, pcs: [4, 6, 7, 9, 11, 0, 2], durs: [1, 1, 2, 3, 4, 6], rest: 0.1, lo: 59, hi: 76 },
    { n: 4, pcs: [7, 5, 0, 2], durs: [1, 1, 2, 4], rest: 0.15, lo: 65, hi: 79 },
  ];
  function book(seed) {
    const R = rng(seed), out = [];
    for (const S of STAGES) for (let k = 0; k < S.n; k++) {
      const scale = []; for (let m = S.lo; m <= S.hi; m++) if (S.pcs.includes(m % 12)) scale.push(m);
      const nev = 1 + Math.floor(R() * (S.durs[0] >= 2 ? 3 : 7));
      let i = Math.floor(R() * scale.length), at = 0; const ev = [];
      for (let e = 0; e < nev; e++) {
        const d = S.durs[Math.floor(R() * S.durs.length)];
        if (R() < S.rest && e > 0) { at += d; continue; }
        if (d === 0.5) { ev.push([scale[i], at, 0.5]); i = Math.max(0, Math.min(scale.length - 1, i + (R() < 0.5 ? -1 : 1))); ev.push([scale[i], at + 0.5, 0.5]); at += 1; }
        else { ev.push([scale[i], at, d]); at += d; }
        i = Math.max(0, Math.min(scale.length - 1, i + Math.round((R() - 0.5) * 4)));
      }
      if (!ev.length) ev.push([scale[0], 0, 1]);
      out.push({ ev, len: Math.max(1, Math.ceil(at)) });
    }
    return out;
  }
  const PULSE_PREF = ['piano', 'marimba', 'vibes', 'glock'];
  const SAX_PREF = ['saxello', 'tenorsax', 'clarinet', 'flute', 'violin', 'organ'];
  const fold = (m, inst) => { const r = window.Proc.INSTRUMENTS[inst].range; while (m < r[0]) m += 12; while (m > r[1]) m -= 12; return m; };

  class RileyScore {
    constructor(seed) {
      this.seed = seed; this.R = rng(seed ^ 0x5a17); this.step = 0;
      this.ctl = { piece: 'inc', tempo: 116, players: 8, flow: 50, spread: 3, pulse: true, tuning: 'equal', ens: [] };
      this.perf = 0; this.newPerformance(); this.rb = null; this.ab = null;
    }
    stepSec() { return 30 / this.ctl.tempo; }
    newPerformance() {
      this.book = book(this.seed + 977 * this.perf);
      this.players = []; this.ending = 0;
    }
    ensure() {
      const want = Math.max(2, Math.min(12, this.ctl.players));
      while (this.players.length < want) { const i = this.players.length; this.players.push({ idx: 0, pos: 0, reps: 0, want: 4, rest: i * 6 + (this.step ? 2 : 0), done: false, oct: 0 }); }
      while (this.players.length > want) this.players.pop();
    }
    advance() {
      const P = this.ctl.piece, notes = [], s = this.step;
      let view;
      if (P === 'inc') view = this.inC(notes);
      else if (P === 'rainbow') view = this.rainbow(notes);
      else view = this.albion(notes);
      this.step++;
      return { step: s, notes, view, tuning: this.ctl.tuning === 'just' ? view.tonic : null };
    }
    // ── In C ──
    inC(notes) {
      this.ensure();
      const c = this.ctl, ens = c.ens, R = this.R, n = this.players.length, last = this.book.length - 1;
      const swell = 0.66 + 0.18 * Math.sin(this.step * 2 * Math.PI / 260) + 0.08 * Math.sin(this.step * 2 * Math.PI / 97);
      if (c.pulse) {
        const pi = PULSE_PREF.find(x => ens.includes(x)) || ens[0];
        notes.push([pi, fold(84, pi), 0.9, 0.3, 'pulse', 0, 0]); notes.push([pi, fold(96, pi) === fold(84, pi) ? fold(84, pi) : fold(96, pi), 0.9, 0.18, 'pulse', 0, 0]);
      }
      const active = this.players.filter(p => !p.done);
      const minIdx = active.length ? Math.min(...active.map(p => p.idx)) : last;
      this.players.forEach((p, i) => {
        if (p.done) return;
        if (p.rest > 0) { p.rest--; return; }
        const inst = ens[i % ens.length];
        if (p.pos === 0) {
          const pat = this.book[p.idx], pan = n > 1 ? -0.8 + 1.6 * i / (n - 1) : 0, vel = swell * (0.85 + 0.15 * ((i * 37) % 7) / 7);
          for (const [m, at, len] of pat.ev) notes.push([inst, fold(m + p.oct, inst), len * 0.94, vel, 'p' + i, at, pan]);
          p.pos = pat.len;
        }
        p.pos--;
        if (p.pos === 0) {                                  // the end of one repetition: stay, move on, rest or finish
          p.reps++;
          const len = this.book[p.idx].len, flow = c.flow / 100;
          if (p.reps >= p.want) {
            if (p.idx === last) { if (active.every(q => q.idx === last)) { p.done = R() < 0.35 + 0.1 * this.ending++; } }
            else if (p.idx + 1 - minIdx <= c.spread) {
              p.idx++; p.reps = 0;
              p.want = Math.max(2, Math.round((2 + R() * 10) * (1.6 - flow) * Math.sqrt(Math.max(1, 8 / this.book[p.idx].len))));
              p.oct = R() < 0.15 ? (R() < 0.5 ? 12 : -12) : 0;
            }
          }
          if (!p.done && R() < 0.035 * (n / 8) && this.players.filter(q => q.rest > 0).length < n / 3) p.rest = 8 + Math.floor(R() * 24);
        }
      });
      if (this.players.every(p => p.done)) { if (++this.ending > 40) { this.perf++; this.newPerformance(); } }
      const idxs = this.players.map(p => p.idx);
      return { piece: 'inc', step: this.step, perf: this.perf + 1, book: this.book, players: this.players.map((p, i) => ({ idx: p.idx, inst: ens[i % ens.length], rest: p.rest > 0, done: p.done })),
        lo: Math.min(...idxs), hi: Math.max(...idxs), tonic: 60 };
    }
    // ── the time-lag accumulator ──
    rainbow(notes) {
      const c = this.ctl, ens = c.ens, R = this.R;
      if (!this.rb || this.step % 192 === 0) {
        const [name, iv] = MODES[Math.floor(R() * MODES.length)], tonic = 57 + Math.floor(R() * 7);
        const ost = this.rb && this.rb.ost ? this.rb.ost : Array.from({ length: 6 }, () => Math.floor(R() * 7));
        this.rb = Object.assign(this.rb || { phrase: [], restFor: 4 }, { name, iv, tonic, ost });
      }
      const B = this.rb, deg = d => B.tonic + 12 * Math.floor(d / 7) + B.iv[((d % 7) + 7) % 7];
      if (this.step % 24 === 0 && this.step) B.ost[Math.floor(R() * B.ost.length)] = Math.floor(R() * 9);   // one note changes
      const org = ['organ', 'marimba', 'vibes', 'piano'].find(x => ens.includes(x)) || ens[0];
      for (const half of [0, 0.5]) { const k = (this.step * 2 + half * 2) % B.ost.length; notes.push([org, fold(deg(B.ost[k]) + 12, org), 0.48, 0.42, 'ostinato', half, -0.3]); }
      const drone = ens.includes('pipe') ? 'pipe' : ens.includes('cello') ? 'cello' : null;
      if (drone && this.step % 32 === 0) { notes.push([drone, fold(B.tonic - 24, drone), 33, 0.5, 'drone', 0, 0]); notes.push([drone, fold(B.tonic - 17, drone), 33, 0.42, 'drone', 0, 0]); }
      const sax = SAX_PREF.find(x => ens.includes(x));
      if (sax) {
        if (B.phrase.length) { const [d, len] = B.phrase.shift(); if (d !== null) notes.push([sax, fold(deg(d) + 12, sax), len, 0.55 + 0.2 * R(), 'sax', 0, 0.2]); if (len > 1) B.phrase.unshift([null, len - 1]); }
        else if (B.restFor > 0) B.restFor--;
        else {                                             // a new phrase: a few notes walking the mode, a long one to finish
          let d = Math.floor(R() * 7) + 2; const n = 3 + Math.floor(R() * 8);
          for (let i = 0; i < n; i++) { d += Math.round((R() - 0.5) * 4); B.phrase.push([d, i === n - 1 ? 4 + Math.floor(R() * 6) : 1 + Math.floor(R() * 2)]); }
          B.restFor = 6 + Math.floor(R() * 18);
        }
      }
      if (ens.includes('glock') && this.step % 8 === 3 && R() < 0.5) notes.push(['glock', fold(deg(B.ost[this.step % B.ost.length]) + 24, 'glock'), 2, 0.3, 'spark', 0, -0.5]);
      return { piece: 'rainbow', step: this.step, mode: `${NAMES[B.tonic % 12]} ${B.name}`, tonic: B.tonic, ost: B.ost.slice(), sax, deg: B.ost.map(deg) };
    }
    // ── New Albion: slow arpeggios on a just-tuned piano ──
    albion(notes) {
      const c = this.ctl, ens = c.ens, R = this.R;
      if (!this.ab) this.ab = { tonic: 62, chord: 0, at: 0, next: 0, line: [] };
      const A = this.ab, inst = ['piano', 'vibes', 'marimba', 'organ'].find(x => ens.includes(x)) || ens[0];
      const CH = [[0, 7, 12, 16, 19, 24], [5, 9, 12, 17, 21, 24], [7, 11, 14, 19, 23, 26], [-2, 5, 10, 14, 17, 22], [9, 12, 16, 21, 24, 28], [0, 4, 7, 14, 16, 19]];
      if (this.step >= A.next) {                            // a new chord, arpeggiated upward over three octaves
        A.chord = this.step === 0 ? 0 : Math.floor(R() * CH.length); A.at = this.step; A.next = this.step + 24 + Math.floor(R() * 16);
        CH[A.chord].forEach((iv, k) => notes.push([inst, fold(A.tonic - 24 + iv, inst), 8, 0.38 + 0.05 * k, 'harp', k * 0.75 + (k > 2 ? 0.25 : 0), -0.4 + 0.15 * k]));
        notes.push([inst, fold(A.tonic - 36 + CH[A.chord][0], inst), 12, 0.42, 'harp', 0, -0.5]);
        A.line = []; const n = 2 + Math.floor(R() * 5); let d = CH[A.chord][3];
        for (let i = 0; i < n; i++) { d += [0, 2, 3, 5, 7, -2, -3, -5][Math.floor(R() * 8)]; A.line.push([this.step + 8 + i * (2 + Math.floor(R() * 3)), A.tonic + d]); }
      }
      for (const [st, m] of A.line) if (st === this.step) notes.push([inst, fold(m, inst), 4, 0.5, 'melody', 0, 0.35]);
      return { piece: 'albion', step: this.step, tonic: A.tonic, chord: CH[A.chord].map(iv => A.tonic - 24 + iv), just: c.tuning === 'just' };
    }
  }

  // ── pictures ──
  const COL = { piano: '#e9e4d8', marimba: '#d98b4f', vibes: '#7fb7d9', glock: '#f2d16b', organ: '#b98be0', pipe: '#8f7ad6', saxello: '#e8a23a', tenorsax: '#c9772b', clarinet: '#6fc2a6', flute: '#9ad7e8', violin: '#e06f6f', cello: '#b4514f', choir: '#f0b8d0' };
  const JI = ['1/1', '16/15', '9/8', '6/5', '5/4', '4/3', '45/32', '3/2', '8/5', '5/3', '9/5', '15/8'];
  function draw(cx, W, H, s) {
    cx.fillStyle = '#07090c'; cx.fillRect(0, 0, W, H);
    const at = s.at, v = at && at.view, now = s.now, sc = W / 1000;
    if (!v) { cx.fillStyle = 'rgba(255,255,255,.55)'; cx.font = `${18 * sc}px "IBM Plex Sans", sans-serif`; cx.textAlign = 'center'; cx.fillText('Press Play', W / 2, H / 2); return; }
    // notes as sparks that rise and fade, in the colour of their instrument
    const recent = s.timeline.filter(e => e.t > now - 2.5 && e.t <= now + 0.05);
    if (v.piece === 'inc') {
      const N = v.book.length, cw = W / (N + 2), y0 = H * 0.62;
      for (let k = 0; k < N; k++) {                        // the pattern book: each pattern's contour in its column
        const x = cw * (k + 1), pat = v.book[k], on = k >= v.lo && k <= v.hi;
        cx.fillStyle = on ? 'rgba(255,255,255,.09)' : 'rgba(255,255,255,.035)'; cx.fillRect(x + 1, y0, cw - 2, H * 0.22);
        cx.strokeStyle = on ? 'rgba(255,255,255,.7)' : 'rgba(255,255,255,.25)'; cx.lineWidth = 1.2 * sc; cx.beginPath();
        pat.ev.forEach(([m, a, l]) => { const xx = x + 2 + (cw - 4) * a / pat.len, yy = y0 + H * 0.2 - (m - 58) / 25 * H * 0.18; cx.moveTo(xx, yy); cx.lineTo(xx + (cw - 4) * l / pat.len, yy); });
        cx.stroke();
      }
      cx.fillStyle = 'rgba(255,255,255,.5)'; cx.font = `${12 * sc}px "IBM Plex Sans", sans-serif`; cx.textAlign = 'left';
      cx.fillText(`Performance ${v.perf} · players between patterns ${v.lo + 1} and ${v.hi + 1} of ${N}`, cw, y0 + H * 0.29);
      const stack = {};
      v.players.forEach((p, i) => {                        // the players, standing over the pattern each is playing
        const k = p.idx, h = stack[k] = (stack[k] || 0) + 1, x = cw * (k + 1.5), y = y0 - 14 * sc * h - 6 * sc;
        cx.globalAlpha = p.done ? 0.15 : p.rest ? 0.35 : 1; cx.fillStyle = COL[p.inst] || '#fff';
        cx.beginPath(); cx.arc(x, y, 6 * sc, 0, Math.PI * 2); cx.fill(); cx.globalAlpha = 1;
      });
      // the pulse: a bar of light across the top
      const beat = at.d ? ((now - at.t) / at.d) : 0, pulse = Math.max(0, 1 - beat * 1.6);
      cx.fillStyle = `rgba(255,255,255,${0.08 + 0.35 * pulse * (s.settings.pulse ? 1 : 0)})`; cx.fillRect(0, H * 0.06, W, 3 * sc);
      for (const e of recent) for (const n of e.notes) if (n[4] !== 'pulse') {
        const age = now - (e.t + (n[5] || 0) * e.d); if (age < 0) continue;
        const pi = +String(n[4]).slice(1), p = v.players[pi]; if (!p) continue;
        const x = cw * (p.idx + 1.5) + (n[6] || 0) * 20 * sc, y = Math.max(H * 0.1, y0 - 30 * sc - age * H * 0.1 - (n[1] - 60) * 3 * sc);
        cx.globalAlpha = Math.max(0, 1 - age / 2.5) * 0.85; cx.fillStyle = COL[n[0]] || '#fff';
        cx.beginPath(); cx.arc(x, y, (2.5 + n[2] * 0.8) * sc, 0, Math.PI * 2); cx.fill();
      }
      cx.globalAlpha = 1;
    } else if (v.piece === 'rainbow') {
      const cxm = W / 2, cym = H / 2, R0 = Math.min(W, H) * 0.12;
      cx.fillStyle = 'rgba(255,255,255,.55)'; cx.font = `${14 * sc}px "IBM Plex Sans", sans-serif`; cx.textAlign = 'center'; cx.fillText(v.mode, cxm, H * 0.08);
      v.deg.forEach((m, k) => { const a = k / v.deg.length * Math.PI * 2 + now * 0.6, r = R0 + (m % 12) * 2 * sc; cx.fillStyle = COL.organ; cx.globalAlpha = 0.8; cx.beginPath(); cx.arc(cxm + Math.cos(a) * r, cym + Math.sin(a) * r, 5 * sc, 0, Math.PI * 2); cx.fill(); });
      // the sax's phrases, and their returns from the two tape loops (3.1 s and 4.9 s later), spiralling outward
      for (const e of s.timeline.filter(e => e.t > now - 30 && e.t <= now)) for (const n of e.notes) if (n[4] === 'sax') {
        for (const [lag, k] of [[0, 1], [3.1, 0.62], [6.2, 0.38], [4.9, 0.62], [9.8, 0.38], [8.0, 0.3]]) {
          const age = now - e.t - lag; if (age < 0 || age > 3) continue;
          const a = (n[1] % 12) / 12 * Math.PI * 2 + lag * 0.4, r = R0 * 1.6 + (lag + age) * 14 * sc;
          cx.globalAlpha = k * Math.max(0, 1 - age / 3); cx.strokeStyle = COL[n[0]] || '#fff'; cx.lineWidth = 3 * sc * k;
          cx.beginPath(); cx.arc(cxm, cym, r, a, a + 0.25 + n[2] * 0.05); cx.stroke();
        }
      }
      cx.globalAlpha = 1;
    } else {
      const lo = 26, hi = 98, sx = m => W * 0.05 + (m - lo) / (hi - lo) * W * 0.9;
      for (let m = lo; m <= hi; m++) { cx.strokeStyle = 'rgba(255,255,255,.07)'; cx.lineWidth = 1; cx.beginPath(); cx.moveTo(sx(m), H * 0.12); cx.lineTo(sx(m), H * 0.86); cx.stroke(); }
      for (const e of s.timeline.filter(e => e.t > now - 6 && e.t <= now)) for (const n of e.notes) {
        const age = now - (e.t + (n[5] || 0) * e.d); if (age < 0) continue;
        const x = sx(n[1]), a = Math.max(0, 1 - age / 6), wob = Math.sin(age * 40) * 3 * sc * a;
        cx.strokeStyle = COL[n[0]] || '#fff'; cx.globalAlpha = a; cx.lineWidth = 2.5 * sc; cx.beginPath(); cx.moveTo(x, H * 0.12); cx.quadraticCurveTo(x + wob, H * 0.49, x, H * 0.86); cx.stroke();
      }
      cx.globalAlpha = 1; cx.fillStyle = 'rgba(255,255,255,.5)'; cx.font = `${12 * sc}px "IBM Plex Sans", sans-serif`; cx.textAlign = 'center';
      if (v.just) for (let k = 0; k < 12; k++) cx.fillText(JI[k], sx(v.tonic + k - 12), H * 0.93);
      cx.fillText(v.just ? 'Just intonation on ' + NAMES[v.tonic % 12] : 'Equal temperament', W / 2, H * 0.07);
    }
  }

  const INSTS = ['piano', 'marimba', 'vibes', 'glock', 'organ', 'pipe', 'saxello', 'tenorsax', 'clarinet', 'flute', 'violin', 'cello', 'choir'];
  window.addEventListener('DOMContentLoaded', () => window.Proc.start({
    name: 'algoriley', Score: RileyScore, seed: 1964, instruments: INSTS,
    defaults: { piece: 'inc', tempo: 116, players: 8, flow: 50, spread: 3, pulse: true, tuning: 'equal', ens: ['piano', 'marimba', 'vibes', 'glock', 'organ', 'saxello', 'clarinet', 'flute', 'violin', 'cello'], vol: {} },
    controls: [
      { type: 'seg', key: 'piece', label: 'Process', options: [['inc', 'In C'], ['rainbow', 'Time-lag'], ['albion', 'New Albion']] },
      { type: 'range', key: 'tempo', label: 'Tempo', min: 60, max: 180, fmt: x => x + ' BPM' },
      { type: 'range', key: 'players', label: 'Players', min: 2, max: 12, hint: 'In C: how many players move through the book' },
      { type: 'range', key: 'flow', label: 'Flow', min: 0, max: 100, fmt: x => x < 34 ? 'patient' : x < 67 ? 'moderate' : 'restless', hint: 'How soon a player moves on from a pattern' },
      { type: 'range', key: 'spread', label: 'Spread', min: 1, max: 6, fmt: x => `within ${x} pattern${x > 1 ? 's' : ''}`, hint: 'How far ahead of the slowest player anyone may go' },
      { type: 'check', key: 'pulse', label: 'Pulse', text: 'The high C eighth notes' },
      { type: 'seg', key: 'tuning', label: 'Tuning', options: [['equal', 'Equal'], ['just', 'Just']] },
    ],
    onControl(key, value, kit, settings) {
      if (!kit) return;
      if (key === 'piece' || key === 'ens') for (const n of ['saxello', 'tenorsax', 'clarinet', 'flute', 'violin', 'organ']) kit.accumulate(n, settings.piece === 'rainbow');
      kit.pedal = settings.piece === 'albion';
    },
    describe: s => s.piece === 'inc' ? `${s.players} players, ${s.ens.length} instruments: each repeats a pattern, moves on when ready, and stays within ${s.spread} of the others.`
      : s.piece === 'rainbow' ? 'A modal organ ostinato and drone; the sax improvises into two tape loops that build its phrases into canons.'
      : 'A piano retuned in just intonation: slow arpeggios under the pedal, a few notes of melody above.',
    draw,
  }));
  window.RileyScore = RileyScore;
})();
