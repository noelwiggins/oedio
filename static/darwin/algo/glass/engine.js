/* Algo — a generative composition engine after the structural ideas of Philip Glass.

   One numerical system drives one score, and the score drives two outputs: sound and image. Nothing in the score uses
   Math.random: the numbers come from a seeded generator (mulberry32, seed 1976 by default), and every musical decision
   is a function of those numbers, the eighth-note step, and the controls in force at that step. Controls are logged by
   the step at which they take effect, so a session replays exactly.

   Layout of this file
     rng / Numbers      the seeded sequence: 16 digits, played four times, then two positions mutate
     Score              chords, additive phrases, rhythmic cycles, movements and silences → note events per step
     Audio              synthesis (piano, organ, violin, voice), voice sampler (harmonizer, vocoder), mixer, reverb
     Exports            MIDI file, WAV encoding, session JSON
   window.Glass = { Numbers, Score, Audio, midiFile, wavBytes, CHORDS, MOVEMENTS, INSTRUMENTS } */
(function () {
  'use strict';

  // ── the seeded generator ──────────────────────────────────────────────
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const hash = (...v) => { let h = 2166136261; for (const x of v) { h ^= (x | 0) + 0x9e3779b9; h = Math.imul(h, 16777619); h ^= h >>> 13; } return (h >>> 0) / 4294967296; };

  // ── the number sequence ───────────────────────────────────────────────
  // 16 digits 0–9; the whole sequence is played four times; then two distinct positions get new, different digits,
  // and the changed sequence is played four times; and so on, for ever, from the same generator.
  class Numbers {
    constructor(seed) {
      this.seed = seed; this.rand = mulberry32(seed);
      this.seq = Array.from({ length: 16 }, () => Math.floor(this.rand() * 10));
      this.pos = 0; this.rep = 0; this.gen = 0; this.count = 0;
      this.history = [];             // every number drawn: [count, value, generation, position]
      this.mutations = [];           // [count, generation, position, from, to]
      this.changed = new Set();      // positions changed by the latest mutation
    }
    next() {
      if (this.pos === 16) {
        this.pos = 0; this.rep++;
        if (this.rep === 4) {
          this.rep = 0; this.gen++;
          const a = Math.floor(this.rand() * 16);
          let b = Math.floor(this.rand() * 15); if (b >= a) b++;
          this.changed = new Set([a, b]);
          for (const p of [a, b]) {
            const from = this.seq[p];
            let to = Math.floor(this.rand() * 9); if (to >= from) to++;
            this.seq[p] = to;
            this.mutations.push([this.count, this.gen, p, from, to]);
          }
        }
      }
      const v = this.seq[this.pos];
      this.history.push([this.count, v, this.gen, this.pos]);
      if (this.history.length > 20000) this.history.splice(0, 5000);
      this.pos++; this.count++;
      return { n: v, pos: this.pos - 1, rep: this.rep, gen: this.gen, count: this.count - 1, mutated: this.changed.has(this.pos - 1) };
    }
  }

  // ── harmony ───────────────────────────────────────────────────────────
  // F minor → D♭ major → A major → B7. Pitches as MIDI numbers of the root-position chord around middle C.
  const CHORDS = [
    { name: 'F minor', short: 'Fm', notes: [53, 56, 60], colour: '#5b8cff', shape: 'circle' },
    { name: 'D♭ major', short: 'D♭', notes: [49, 53, 56], colour: '#f0b44c', shape: 'triangle' },
    { name: 'A major', short: 'A', notes: [57, 61, 64], colour: '#e5534b', shape: 'square' },
    { name: 'B7', short: 'B7', notes: [59, 63, 66, 69], colour: '#a77bf3', shape: 'hexagon' },
  ];
  function voicing(ci, inv) {                     // root, first or second inversion
    const v = CHORDS[ci].notes.slice();
    for (let k = 0; k < inv; k++) v.push(v.shift() + 12);
    return v;
  }
  // the k-th tone of the chord climbing through octaves (k may exceed the chord size)
  const tone = (v, k) => v[((k % v.length) + v.length) % v.length] + 12 * Math.floor(k / v.length);

  // Euclidean rhythm: k attacks spread as evenly as possible over n steps, rotated by r
  function euclid(k, n, r) {
    const out = new Array(n).fill(false);
    k = Math.max(0, Math.min(n, k));
    for (let i = 0; i < k; i++) out[(Math.floor(i * n / k) + r) % n] = true;
    return out;
  }

  // ── large-scale architecture ──────────────────────────────────────────
  const MOVEMENTS = [
    { name: 'I · Introduction', layers: ['piano', 'organ'], grow: 0.0, maxLen: 4, sustain: 0.0, rest: 0.05 },
    { name: 'II · Accumulation', layers: ['piano', 'organ', 'violin', 'voice'], grow: 1.0, maxLen: 7, sustain: 0.0, rest: 0.0 },
    { name: 'III · Harmonic transformation', layers: ['organ', 'violin', 'voice'], grow: 0.4, maxLen: 6, sustain: 0.5, rest: 0.05, slow: 2 },
    { name: 'IV · Rhythmic complexity', layers: ['piano', 'organ', 'violin', 'voice'], grow: 1.0, maxLen: 7, sustain: 0.0, rest: 0.0, mutate: true },
    { name: 'V · Reduction and stillness', layers: ['organ', 'piano', 'violin'], grow: -1, maxLen: 3, sustain: 0.6, rest: 0.25, slow: 2 },
  ];
  const CHORDS_PER_MOVEMENT = 12, BRIDGE = 2;     // the last two chords of a movement lean into the next
  const INSTRUMENTS = ['piano', 'organ', 'violin', 'voice'];
  const CYCLE = { piano: 5, organ: 7, violin: 11 };
  // the material every phrase is cut from: chord-tone degrees; a phrase of length L is its first L notes, so adding a
  // note keeps everything that was there and the newcomer grows out of the same line
  const LINE = [0, 2, 1, 3, 2, 4, 3];

  // ── the score: one step (an eighth note) at a time ────────────────────
  class Score {
    constructor(seed) { this.reset(seed); }
    reset(seed) {
      this.seed = seed; this.nums = new Numbers(seed);
      this.step = 0; this.chordCount = -1; this.chordEnd = 0; this.mov = 0; this.inMov = -1;
      this.ctl = { complexity: 55, lead: 0, tempo: 112 };
      this.L = 3; this.dir = 1; this.voiceCycle = 5;
      this.chord = null; this.chords = []; this.silences = [];
      this.finishing = false; this.finished = false; this.stopAt = Infinity;
    }
    // a new number: the next chord, its length, its arpeggio density, its inversion, and what happens to the phrase
    nextChord() {
      const d = this.nums.next(), N = d.n, cc = ++this.chordCount;
      if (++this.inMov >= CHORDS_PER_MOVEMENT) { this.inMov = 0; this.mov = (this.mov + 1) % MOVEMENTS.length; }
      const mi = this.mov, M = MOVEMENTS[mi], inMov = this.inMov;
      const bridge = inMov >= CHORDS_PER_MOVEMENT - BRIDGE ? (inMov - (CHORDS_PER_MOVEMENT - BRIDGE) + 1) / (BRIDGE + 1) : 0;
      const c = this.ctl.complexity / 100;
      const ci = cc % 4;
      let beats = 8 + 4 * (N % 3);
      if (M.slow) beats = Math.round(beats * (1 + (M.slow - 1) * (0.5 + 0.5 * (1 - c))));   // slow movements stretch chords
      const len = beats * 2;                                              // in eighth notes
      const density = 3 + (N % 4), inv = N % 3;
      // additive phrase: the numbers decide when a note is added or taken away; the movement and the complexity set the
      // ceiling; at each end the phrase turns round (3 → 7 → 3)
      const ceiling = Math.max(3, Math.min(M.maxLen, 3 + Math.round(4 * Math.min(1, c * 1.25))));
      let changed = 0;
      if (M.grow < 0) { if (this.L > 3 && N % 2 === 0) { this.L--; changed = -1; } }
      else if (N >= 6 - Math.round(2 * M.grow) || (M.grow > 0.5 && N === 0)) {
        if (this.dir > 0 && this.L >= ceiling) this.dir = -1;
        else if (this.dir < 0 && this.L <= 3) this.dir = 1;
        const nl = Math.max(3, Math.min(ceiling, this.L + this.dir));
        changed = nl - this.L; this.L = nl;
      }
      if (this.L > ceiling) { this.L = ceiling; changed = -1; }
      this.voiceCycle = 3 + (N % 6);                                      // the voice sampler's own cycle: 3 to 8 eighths
      // which layers play: the movement's layers, fewer at low complexity, a bridge bringing the next movement's in
      const nextM = MOVEMENTS[(mi + 1) % MOVEMENTS.length];
      const maxLayers = 1 + Math.round(3 * c);
      let layers = M.layers.slice(0, Math.max(1, Math.min(M.layers.length, maxLayers, mi === 1 ? 1 + Math.floor(inMov / 3) : 9)));
      if (bridge > 0) for (const l of nextM.layers) if (!layers.includes(l) && bridge > 0.5 && layers.length < maxLayers + 1) layers.push(l);
      if (mi === 4) layers = layers.slice(0, Math.max(1, layers.length - Math.floor(inMov / 4)));   // reduction: layers leave
      // silences, decided by the numbers and the architecture
      const sil = { stopped: [], onlyOne: null, sustain: false, restBeats: 0 };
      for (let i = 0; i < INSTRUMENTS.length; i++) if ((N + i * 3 + cc) % 11 === 0 && mi !== 1) sil.stopped.push(INSTRUMENTS[i]);
      if (N === 9 && (c < 0.5 || mi === 4)) sil.onlyOne = layers[0];
      if (M.sustain > 0 && hash(this.seed, cc, N) < M.sustain * (1.2 - c)) sil.sustain = true;
      const restChance = M.rest + 0.25 * Math.max(0, 0.4 - c);
      if (N === 0 || hash(this.seed, cc, 7) < restChance) sil.restBeats = Math.min(beats - 2, 2 + 2 * (this.nums.seq[(d.pos + 1) % 16] % 4));
      layers = layers.filter(l => !sil.stopped.includes(l) || layers.length === 1);
      if (sil.onlyOne) layers = [sil.onlyOne];
      this.chord = {
        cc, ci, N, len, beats, density, inv, L: this.L, changed, mi, bridge, start: this.step, layers, sil,
        v: voicing(ci, inv), num: d, voiceCycle: this.voiceCycle, complexity: this.ctl.complexity,
      };
      this.chordEnd = this.step + len;
      this.chords.push(this.chord); if (this.chords.length > 400) this.chords.shift();
      if (sil.restBeats) { this.silences.push([this.step, this.step + sil.restBeats * 2]); if (this.silences.length > 200) this.silences.shift(); }
      if (this.finishing && mi === 4 && inMov === CHORDS_PER_MOVEMENT - 1) this.stopAt = this.chordEnd;
      return this.chord;
    }
    // when the user's chosen duration runs out, the piece heads into its last movement and ends there
    finish() {
      if (this.finishing) return;
      this.finishing = true;
      if (this.mov !== 4) { this.mov = 4; this.inMov = -1; }     // the next chord begins the reduction
    }
    // every note that starts on this step: [instrument, midi, length in steps, velocity, part]
    advance() {
      const s = this.step;
      if (s >= this.stopAt) { this.finished = true; return { step: s, notes: [], chord: this.chord, newChord: false }; }
      let newChord = false;
      if (!this.chord || s >= this.chordEnd) { this.nextChord(); newChord = true; }
      const C = this.chord, k = s - C.start, c = this.ctl.complexity / 100, notes = [];
      const resting = k < C.sil.restBeats * 2;
      const on = l => C.layers.includes(l) && !resting;
      const cell = LINE.slice(0, C.L);
      const v = C.v;
      if (!resting && C.sil.sustain) {
        // a chord held without rhythm: the organ only, once, for the whole chord
        if (k === C.sil.restBeats * 2) for (const m of v) notes.push(['organ', m - 12, C.len - k, 0.5, 'hold']);
      } else if (!resting) {
        // the lead arpeggio, played on the dial's instrument: density attacks per bar (Euclidean), stepping through the phrase
        const bar = euclid(C.density, 8, C.inv);
        if (bar[k % 8]) {
          const idx = Math.floor(k / 8) * C.density + bar.slice(0, k % 8 + 1).filter(Boolean).length - 1;
          notes.push(['lead', tone(v, cell[idx % C.L]) + 12, 2, 0.62 + 0.1 * (idx % C.L === 0), 'lead']);
        }
        // piano: a cycle of 5 eighths, the phrase walked in fives, so its alignment with the bar keeps moving
        if (on('piano')) {
          const p = s % CYCLE.piano, hits = euclid(Math.min(C.density, 4) - (c < 0.3 ? 1 : 0), CYCLE.piano, C.inv);
          if (hits[p]) { const i = Math.floor(s / CYCLE.piano) + p; notes.push(['piano', tone(v, cell[i % C.L]), 2, 0.5, 'cycle']); }
        }
        // organ: the chord, sustained and re-voiced on a cycle of 7
        if (on('organ') && (s % CYCLE.organ === 0 || k === 0)) {
          const m = Math.floor(s / CYCLE.organ) % 2 === 0 ? v : voicing(C.ci, (C.inv + 1) % 3);
          for (const x of m) notes.push(['organ', x - 12, Math.min(CYCLE.organ, C.len - k), 0.35, 'cycle']);
        }
        // violin: a cycle of 11, long bowed notes from the phrase, an octave up
        if (on('violin') && c > 0.2) {
          const p = s % CYCLE.violin, hits = euclid(2 + Math.round(2 * c), CYCLE.violin, C.N % CYCLE.violin);
          if (hits[p]) { const i = Math.floor(s / CYCLE.violin) * 3 + p; notes.push(['violin', tone(v, cell[(i + 1) % C.L]) + 12, 4 + Math.round(3 * (1 - c)), 0.45, 'cycle']); }
        }
        // voice: its cycle is chosen afresh by each number (3–8 eighths)
        if (on('voice') && c > 0.35) {
          const vc = C.voiceCycle, p = s % vc;
          if (p === 0 || (c > 0.75 && p === Math.floor(vc / 2))) notes.push(['voice', tone(v, cell[Math.floor(s / vc) % C.L]), vc, 0.5, 'cycle']);
        }
      }
      this.step++;
      return { step: s, notes, chord: C, newChord, resting };
    }
  }

  // ── audio ─────────────────────────────────────────────────────────────
  const mtof = m => 440 * Math.pow(2, (m - 69) / 12);
  class Audio {
    constructor() {
      const A = this.ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: 'playback' });
      this.out = A.createGain(); this.out.gain.value = 0.8;
      const comp = A.createDynamicsCompressor(); comp.threshold.value = -16; comp.ratio.value = 3; comp.attack.value = 0.01; comp.release.value = 0.3;
      const hp = A.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 45;
      this.out.connect(hp); hp.connect(comp); comp.connect(A.destination);
      this.rec = A.createMediaStreamDestination(); comp.connect(this.rec);
      // reverb: a decaying noise impulse, darker as it fades
      this.verb = A.createConvolver(); this.verb.buffer = this.impulse(3.4);
      this.verbIn = A.createGain(); this.verbIn.gain.value = 0.35;
      this.verbIn.connect(this.verb); this.verb.connect(this.out);
      this.bus = {}; this.send = {};
      for (const n of INSTRUMENTS) {
        const g = A.createGain(); g.gain.value = 0.8; g.connect(this.out);
        const sd = A.createGain(); sd.gain.value = n === 'voice' ? 0.45 : 0.3; g.connect(sd); sd.connect(this.verbIn);
        this.bus[n] = g; this.send[n] = sd;
      }
      // the lead line has its own fader per instrument, so the dial can crossfade between them
      this.lead = {}; this.leadOn = 0;
      for (let i = 0; i < 4; i++) { const g = A.createGain(); g.gain.value = i === 0 ? 1 : 0; g.connect(this.bus[INSTRUMENTS[i]]); this.lead[i] = g; }
      this.leadRecent = [0, -1, -1, -1];                                  // when each was last faded out
      this.vibrato = A.createOscillator(); this.vibrato.frequency.value = 5.4; this.vibrato.start();
      this.voice = { buffer: null, mode: 'harmonizer', clarity: 0.6, wet: 0.45, layers: 2, speed: 1, reps: 1, trim: [0, 1], base: 57, bands: null };
      this.live = 0;                                                      // notes sounding, for a polyphony cap
    }
    impulse(sec) {
      const A = this.ctx, n = Math.floor(A.sampleRate * sec), b = A.createBuffer(2, n, A.sampleRate);
      for (let ch = 0; ch < 2; ch++) {
        const d = b.getChannelData(ch); let lp = 0;
        for (let i = 0; i < n; i++) { const t = i / n, k = 0.25 + 0.7 * t; lp = lp * k + (Math.random() * 2 - 1) * (1 - k); d[i] = lp * Math.pow(1 - t, 2.2) * 1.8; }
      }
      return b;
    }
    setLead(i, at) {                                                      // the dial: a 250 ms crossfade
      const A = this.ctx, t = at || A.currentTime;
      for (let k = 0; k < 4; k++) {
        const g = this.lead[k].gain; g.cancelScheduledValues(t); g.setValueAtTime(g.value, t);
        g.linearRampToValueAtTime(k === i ? 1 : 0, t + 0.25);
        if (k !== i && this.leadOn === k) this.leadRecent[k] = t + 0.3;
      }
      this.leadOn = i;
    }
    // play one score note; returns nothing. inst may be 'lead' (goes to the dial's instrument, and to the one fading out)
    play(inst, midi, dur, vel, t) {
      if (this.live > 48) return;
      if (inst === 'lead') {
        for (let k = 0; k < 4; k++) if (k === this.leadOn || this.leadRecent[k] > t) this.voiceFor(INSTRUMENTS[k], midi, dur, vel, t, this.lead[k]);
        return;
      }
      this.voiceFor(inst, midi, dur, vel, t, this.bus[inst]);
    }
    voiceFor(inst, midi, dur, vel, t, dest) {
      if (inst === 'piano') return this.piano(midi, dur, vel, t, dest);
      if (inst === 'organ') return this.organ(midi, dur, vel, t, dest);
      if (inst === 'violin') return this.violin(midi, dur, vel, t, dest);
      return this.voiceNote(midi, dur, vel, t, dest);
    }
    _done(nodes, last) {                                                  // tidy every node a note made, when its last source ends
      this.live++;
      last.onended = () => { this.live--; for (const n of nodes) { try { n.disconnect(); } catch (e) {} } };
    }
    piano(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), nodes = [], out = A.createGain(), lp = A.createBiquadFilter();
      lp.type = 'lowpass'; lp.frequency.value = Math.min(12000, 1800 + 5000 * vel); out.connect(lp); lp.connect(dest); nodes.push(out, lp);
      const T = Math.max(0.6, 3.2 - (m - 48) * 0.035), end = t + T;
      let last = null;
      for (let k = 1; k <= 6; k++) {
        const o = A.createOscillator(), g = A.createGain();
        o.frequency.value = f * k * Math.sqrt(1 + 0.0004 * k * k);
        const a = vel * 0.16 / Math.pow(k, 1.25);
        g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(a, t + 0.004);
        g.gain.setTargetAtTime(0, t + 0.004, T / (2.5 + k * 0.9));
        o.connect(g); g.connect(out); o.start(t); o.stop(end); nodes.push(o, g); last = o;
      }
      // the hammer: a very short knock of filtered noise
      const nb = A.createBufferSource(), nbuf = A.createBuffer(1, 1024, A.sampleRate), d = nbuf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
      nb.buffer = nbuf; const bp = A.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = f * 3; bp.Q.value = 1.2;
      const ng = A.createGain(); ng.gain.value = 0.05 * vel;
      nb.connect(bp); bp.connect(ng); ng.connect(out); nb.start(t); nb.stop(t + 0.03); nodes.push(nb, bp, ng);
      this._done(nodes, last);
    }
    organ(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), nodes = [], g = A.createGain(), L = dur;
      const amp = vel * 0.075;
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(amp, t + 0.06);
      g.gain.setValueAtTime(amp, t + Math.max(0.07, L - 0.05)); g.gain.linearRampToValueAtTime(0, t + L + 0.25);
      g.connect(dest); nodes.push(g);
      const dep = A.createGain(); dep.gain.value = 4; this.vibrato.connect(dep); nodes.push(dep);
      let last = null;
      [[1, 1], [2, 0.6], [3, 0.35], [4, 0.28], [6, 0.12], [8, 0.08]].forEach(([h, a]) => {
        const o = A.createOscillator(), og = A.createGain(); o.frequency.value = f * h; og.gain.value = a;
        dep.connect(o.detune); o.connect(og); og.connect(g); o.start(t); o.stop(t + L + 0.3); nodes.unshift(o, og); last = o;
      });
      this._done(nodes, last);
    }
    violin(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), nodes = [], L = dur;
      const g = A.createGain(), lp = A.createBiquadFilter(), pk1 = A.createBiquadFilter(), pk2 = A.createBiquadFilter();
      lp.type = 'lowpass'; lp.frequency.value = 4200; lp.Q.value = 0.5;
      pk1.type = 'peaking'; pk1.frequency.value = 1100; pk1.Q.value = 1.4; pk1.gain.value = 6;
      pk2.type = 'peaking'; pk2.frequency.value = 2700; pk2.Q.value = 2; pk2.gain.value = 5;
      const amp = vel * 0.06;
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(amp * 0.7, t + 0.09); g.gain.linearRampToValueAtTime(amp, t + Math.min(L * 0.6, 0.6));
      g.gain.setValueAtTime(amp, t + Math.max(0.12, L - 0.08)); g.gain.linearRampToValueAtTime(0, t + L + 0.35);
      g.connect(lp); lp.connect(pk1); pk1.connect(pk2); pk2.connect(dest); nodes.push(g, lp, pk1, pk2);
      // vibrato that arrives after the bow has settled
      const dep = A.createGain(); dep.gain.setValueAtTime(0, t); dep.gain.linearRampToValueAtTime(9, t + Math.min(0.5, L * 0.5)); this.vibrato.connect(dep); nodes.push(dep);
      let last = null;
      for (const det of [-6, 5]) {
        const o = A.createOscillator(); o.type = 'sawtooth'; o.frequency.value = f; o.detune.value = det;
        dep.connect(o.detune); o.connect(g); o.start(t); o.stop(t + L + 0.4); nodes.unshift(o); last = o;
      }
      this._done(nodes, last);
    }
    // the voice: a recorded word or phrase, reharmonised; with nothing recorded, a sung vowel
    voiceNote(m, dur, vel, t, dest) {
      const V = this.voice, chord = this.currentChord || [m];
      const tones = [m]; for (const x of chord) if (tones.length < V.layers && (x % 12) !== (m % 12)) tones.push(x + 12 * Math.round((m - x) / 12));
      for (let r = 0; r < V.reps; r++) {
        const tt = t + r * (dur / V.reps);
        for (let i = 0; i < tones.length; i++) {
          const g = vel * (i === 0 ? 1 : 0.6) / Math.sqrt(tones.length);
          if (!V.buffer) this.vowel(tones[i], dur / V.reps, g, tt, dest);
          else if (V.mode === 'vocoder') this.vocode(tones[i], dur / V.reps, g, tt, dest);
          else this.harmonize(tones[i], dur / V.reps, g, tt, dest);
        }
      }
    }
    vowel(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), nodes = [], g = A.createGain(), L = Math.max(0.3, dur);
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vel * 0.05, t + 0.12); g.gain.setValueAtTime(vel * 0.05, t + L * 0.8); g.gain.linearRampToValueAtTime(0, t + L + 0.2);
      g.connect(dest); nodes.push(g);
      const o = A.createOscillator(); o.type = 'sawtooth'; o.frequency.value = f;
      const dep = A.createGain(); dep.gain.value = 7; this.vibrato.connect(dep); dep.connect(o.detune); nodes.push(dep);
      for (const [fr, q, a] of [[700, 8, 1], [1150, 10, 0.6], [2800, 12, 0.25]]) {
        const bp = A.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = fr; bp.Q.value = q;
        const bg = A.createGain(); bg.gain.value = a * 3; o.connect(bp); bp.connect(bg); bg.connect(g); nodes.push(bp, bg);
      }
      o.start(t); o.stop(t + L + 0.25); nodes.unshift(o);
      this._done(nodes, o);
    }
    trimmed() {
      const V = this.voice, b = V.buffer, s0 = Math.floor(V.trim[0] * b.length), s1 = Math.max(s0 + 64, Math.floor(V.trim[1] * b.length));
      return [s0 / b.sampleRate, (s1 - s0) / b.sampleRate];
    }
    harmonize(m, dur, vel, t, dest) {
      // pitch-shift by playback rate to each chord tone; a high shelf restores some brightness as clarity rises
      const A = this.ctx, V = this.voice, [off, len] = this.trimmed(), nodes = [];
      const rate = Math.pow(2, (m - V.base) / 12) * V.speed;
      const src = A.createBufferSource(); src.buffer = V.buffer; src.playbackRate.value = rate;
      const sh = A.createBiquadFilter(); sh.type = 'highshelf'; sh.frequency.value = 2500; sh.gain.value = (V.clarity - 0.5) * 16;
      const lp = A.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 2000 + 9000 * V.clarity;
      const g = A.createGain(), play = Math.min(len / rate, Math.max(0.15, dur + 0.4));
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vel * 0.9, t + 0.015);
      g.gain.setValueAtTime(vel * 0.9, t + Math.max(0.02, play - 0.06)); g.gain.linearRampToValueAtTime(0, t + play);
      src.connect(sh); sh.connect(lp); lp.connect(g); g.connect(dest);
      src.start(t, off, len); src.stop(t + play + 0.02); nodes.push(src, sh, lp, g);
      this._done(nodes, src);
    }
    // the vocoder: the recording's spectral envelope, measured once in 16 bands, shapes a synthesizer playing the chord
    analyse() {
      const V = this.voice, b = V.buffer; if (!b) return;
      const sr = b.sampleRate, x = b.getChannelData(0), FR = 200, hop = Math.floor(sr / FR);
      const centres = Array.from({ length: 16 }, (_, i) => 150 * Math.pow(5200 / 150, i / 15));
      V.bands = centres.map(fc => {
        // a two-pole bandpass in plain JS, rectified and smoothed to an envelope at 200 frames a second
        const w = 2 * Math.PI * fc / sr, q = 4, alpha = Math.sin(w) / (2 * q), a0 = 1 + alpha;
        const b0 = alpha / a0, b2 = -alpha / a0, a1 = -2 * Math.cos(w) / a0, a2 = (1 - alpha) / a0;
        let x1 = 0, x2 = 0, y1 = 0, y2 = 0, env = 0; const out = new Float32Array(Math.ceil(x.length / hop));
        for (let i = 0; i < x.length; i++) {
          const y = b0 * x[i] + b2 * x2 - a1 * y1 - a2 * y2; x2 = x1; x1 = x[i]; y2 = y1; y1 = y;
          const r = Math.abs(y); env = r > env ? env + (r - env) * 0.2 : env + (r - env) * 0.002;
          if (i % hop === 0) out[i / hop] = env;
        }
        let mx = 1e-6; for (const v of out) mx = Math.max(mx, v); for (let i = 0; i < out.length; i++) out[i] /= mx;
        return { fc, env: out };
      });
      V.frames = FR;
    }
    vocode(m, dur, vel, t, dest) {
      const A = this.ctx, V = this.voice; if (!V.bands) this.analyse();
      const [off, len] = this.trimmed(), f0 = Math.floor(off * V.frames), f1 = Math.floor((off + len) * V.frames);
      const play = Math.max(0.15, len / V.speed), nodes = [];
      const carrier = A.createOscillator(); carrier.type = 'sawtooth'; carrier.frequency.value = mtof(m);
      const c2 = A.createOscillator(); c2.type = 'sawtooth'; c2.frequency.value = mtof(m) * 1.004;
      const sum = A.createGain(); sum.gain.value = 0.5; carrier.connect(sum); c2.connect(sum); nodes.push(sum);
      const out = A.createGain(); out.gain.setValueAtTime(0, t); out.gain.linearRampToValueAtTime(vel * 0.6, t + 0.01);
      out.gain.setValueAtTime(vel * 0.6, t + play - 0.04); out.gain.linearRampToValueAtTime(0, t + play); out.connect(dest); nodes.push(out);
      for (const band of V.bands) {
        const bp = A.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = band.fc; bp.Q.value = 3 + 9 * V.clarity;
        const g = A.createGain(); g.gain.value = 0;
        const seg = band.env.slice(f0, Math.max(f0 + 2, f1));
        const curve = new Float32Array(seg.length); for (let i = 0; i < seg.length; i++) curve[i] = seg[i] * 2.2;
        g.gain.setValueCurveAtTime(curve, t, play);
        sum.connect(bp); bp.connect(g); g.connect(out); nodes.push(bp, g);
      }
      carrier.start(t); c2.start(t); carrier.stop(t + play + 0.02); c2.stop(t + play + 0.02); nodes.unshift(carrier, c2);
      this._done(nodes, carrier);
    }
    // estimate the recording's pitch (autocorrelation over its loudest half-second), so the harmonizer tunes it to the chord
    detectPitch() {
      const V = this.voice, b = V.buffer; if (!b) return;
      const x = b.getChannelData(0), sr = b.sampleRate, W = Math.min(x.length, Math.floor(sr * 0.5));
      let best = 0, at = 0; for (let i = 0; i + W < x.length; i += Math.floor(W / 4)) { let e = 0; for (let j = 0; j < W; j += 8) e += x[i + j] * x[i + j]; if (e > best) { best = e; at = i; } }
      const lo = Math.floor(sr / 500), hi = Math.floor(sr / 70); let bestLag = 0, bestC = 0;
      for (let lag = lo; lag < hi; lag++) { let c = 0; for (let j = 0; j < W - lag; j += 2) c += x[at + j] * x[at + j + lag]; if (c > bestC) { bestC = c; bestLag = lag; } }
      if (bestLag) V.base = 69 + 12 * Math.log2((sr / bestLag) / 440);
    }
    setVoice(buffer) {
      const A = this.ctx;
      if (buffer && buffer.numberOfChannels > 1) {                       // fold to mono
        const m = A.createBuffer(1, buffer.length, buffer.sampleRate), d = m.getChannelData(0);
        for (let ch = 0; ch < buffer.numberOfChannels; ch++) { const s = buffer.getChannelData(ch); for (let i = 0; i < s.length; i++) d[i] += s[i] / buffer.numberOfChannels; }
        buffer = m;
      }
      this.voice.buffer = buffer; this.voice.bands = null;
      if (buffer) { this.detectPitch(); this.analyse(); }
    }
  }

  // ── exports ───────────────────────────────────────────────────────────
  // a Standard MIDI File (format 1): a tempo track and one track per instrument; the eighth note is 240 ticks
  function midiFile(events, tempos) {
    const PPQ = 480, E = 240, vlq = n => { const b = [n & 0x7f]; while ((n >>= 7)) b.unshift((n & 0x7f) | 0x80); return b; };
    const track = evs => {                                       // evs: [tick, bytes]
      evs.sort((a, b) => a[0] - b[0] || (a[1][0] & 0xf0) - (b[1][0] & 0xf0));
      const out = []; let last = 0;
      for (const [tk, bytes] of evs) { out.push(...vlq(tk - last), ...bytes); last = tk; }
      out.push(0, 0xff, 0x2f, 0);
      return [0x4d, 0x54, 0x72, 0x6b, (out.length >>> 24) & 255, (out.length >>> 16) & 255, (out.length >>> 8) & 255, out.length & 255, ...out];
    };
    const tracks = [];
    const tt = tempos.map(([step, bpm]) => { const us = Math.round(60000000 / bpm); return [step * E, [0xff, 0x51, 3, (us >>> 16) & 255, (us >>> 8) & 255, us & 255]]; });
    tt.push([0, [0xff, 0x03, 4, 0x41, 0x6c, 0x67, 0x6f]]);       // track name "Algo"
    tracks.push(track(tt));
    const PROG = { piano: 0, organ: 19, violin: 40, voice: 52 };
    INSTRUMENTS.forEach((name, ch) => {
      const evs = [[0, [0xc0 | ch, PROG[name]]], [0, [0xff, 0x03, name.length, ...[...name].map(c => c.charCodeAt(0))]]];
      for (const [step, inst, midi, len, vel] of events) if (inst === name) {
        const v = Math.max(1, Math.min(127, Math.round(vel * 127))), n = Math.max(0, Math.min(127, midi));
        evs.push([step * E, [0x90 | ch, n, v]], [(step + len) * E - 1, [0x80 | ch, n, 0]]);
      }
      tracks.push(track(evs));
    });
    const head = [0x4d, 0x54, 0x68, 0x64, 0, 0, 0, 6, 0, 1, 0, tracks.length, (PPQ >> 8) & 255, PPQ & 255];
    return new Uint8Array([...head, ...tracks.flat()]);
  }
  // 16-bit PCM WAV from an AudioBuffer (for saving the voice sample inside a session)
  function wavBytes(buf) {
    const ch = buf.numberOfChannels, n = buf.length, sr = buf.sampleRate, bytes = new DataView(new ArrayBuffer(44 + n * ch * 2));
    const w = (o, s) => { for (let i = 0; i < s.length; i++) bytes.setUint8(o + i, s.charCodeAt(i)); };
    w(0, 'RIFF'); bytes.setUint32(4, 36 + n * ch * 2, true); w(8, 'WAVE'); w(12, 'fmt '); bytes.setUint32(16, 16, true);
    bytes.setUint16(20, 1, true); bytes.setUint16(22, ch, true); bytes.setUint32(24, sr, true); bytes.setUint32(28, sr * ch * 2, true);
    bytes.setUint16(32, ch * 2, true); bytes.setUint16(34, 16, true); w(36, 'data'); bytes.setUint32(40, n * ch * 2, true);
    let o = 44; const data = []; for (let c = 0; c < ch; c++) data.push(buf.getChannelData(c));
    for (let i = 0; i < n; i++) for (let c = 0; c < ch; c++) { const v = Math.max(-1, Math.min(1, data[c][i])); bytes.setInt16(o, v < 0 ? v * 0x8000 : v * 0x7fff, true); o += 2; }
    return new Uint8Array(bytes.buffer);
  }

  window.Glass = { Numbers, Score, Audio, midiFile, wavBytes, CHORDS, MOVEMENTS, INSTRUMENTS, CYCLE, LINE, hash, mulberry32, voicing, euclid };
})();
