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
  const F_MINOR = [0, 2, 3, 5, 7, 8, 10];        // the 1960s line lives in F minor, without chords
  const SOLFEGE = ['do', 'di', 're', 'ri', 'mi', 'fa', 'fi', 'sol', 'si', 'la', 'li', 'ti'];
  const PARTS = ['piano', 'organ', 'violin', 'voice', 'bass'];
  // phonemes for the singing: [voiced, noise, noise Hz, F1, F2, F3, ms (0 = vowel)]
  const PHON = {
    ee: [1, 0, 0, 280, 2250, 2900, 0], ih: [1, 0, 0, 400, 1950, 2550, 0], eh: [1, 0, 0, 530, 1840, 2480, 0], ah: [1, 0, 0, 720, 1100, 2450, 0],
    oh: [1, 0, 0, 480, 880, 2400, 0], oo: [1, 0, 0, 310, 870, 2250, 0], uh: [1, 0, 0, 560, 1200, 2400, 0], ai: [1, 0, 0, 650, 1500, 2450, 0], ei: [1, 0, 0, 470, 2000, 2550, 0],
    s: [0, 1, 6500, 400, 1600, 2600, 85], f: [0, 0.55, 4200, 400, 1400, 2500, 75], th: [0, 0.4, 3800, 400, 1500, 2500, 65], z: [0.35, 0.7, 5500, 300, 1700, 2600, 65],
    v: [0.45, 0.35, 3500, 300, 1200, 2400, 55], t: [0, 0.9, 4200, 400, 1700, 2600, 35], k: [0, 0.8, 1900, 400, 1600, 2500, 40], d: [0.25, 0.4, 3200, 300, 1700, 2600, 35],
    n: [0.55, 0, 0, 260, 1650, 2650, 65], m: [0.55, 0, 0, 260, 1100, 2300, 65], l: [0.7, 0, 0, 360, 1250, 2650, 55], r: [0.7, 0, 0, 430, 1250, 1650, 60], w: [0.7, 0, 0, 300, 640, 2200, 55],
  };
  const WORDS = {
    0: ['z', 'ee', 'r', 'oh'], 1: ['w', 'uh', 'n'], 2: ['t', 'oo'], 3: ['th', 'r', 'ee'], 4: ['f', 'oh', 'r'], 5: ['f', 'ai', 'ee', 'v'],
    6: ['s', 'ih', 'k', 's'], 7: ['s', 'eh', 'v', 'uh', 'n'], 8: ['ei', 'ee', 't'], 9: ['n', 'ai', 'ee', 'n'],
    do: ['d', 'oh'], di: ['d', 'ee'], re: ['r', 'ei'], ri: ['r', 'ee'], mi: ['m', 'ee'], fa: ['f', 'ah'], fi: ['f', 'ee'], sol: ['s', 'oh', 'l'],
    si: ['s', 'ee'], la: ['l', 'ah'], li: ['l', 'ee'], ti: ['t', 'ee'], ah: ['ah'], oh: ['oh'],
  };

  // ── the score: one step (an eighth note) at a time ────────────────────
  class Score {
    constructor(seed) { this.reset(seed); }
    reset(seed) {
      this.seed = seed; this.nums = new Numbers(seed);
      this.step = 0; this.chordCount = -1; this.chordEnd = 0; this.mov = 0; this.inMov = -1;
      // period: 0 = the 1960s (unison lines in fifths, additive rhythm, no harmony), 1 = the 1970s (cycles over slow
      // harmony), 2 = the operas (a repeating ground bass under it all). text: what the voice sings.
      this.ctl = { complexity: 55, lead: 0, tempo: 112, period: 1, rhythm: 'euclid', triplets: true, knees: true, text: 'numbers', intermission: 0 };
      this.L = 3; this.dir = 1; this.voiceCycle = 5;
      this.rhy = [2, 2, 2];                       // additive rhythm: how many eighths each note of the phrase lasts
      this.leadPos = 0; this.leadNext = 0; this.count = 0; this.voiceIdx = 0;
      this.pauseUntil = 0; this.intermissions = 0;
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
      // additive rhythm (after Alla Rakha's lessons, as Glass tells it): the phrase keeps its notes but grows in time,
      // one eighth added to one of its notes at a time, 2+2+2 → 2+2+3 → 2+3+3 …; a zero sends it back to plain twos
      while (this.rhy.length < this.L) this.rhy.push(2);
      this.rhy.length = this.L;
      if (changed) this.count = 0;
      if (N === 0 || this.rhy.every(x => x >= 4)) this.rhy = this.rhy.map(() => 2);   // full grown: begin again from twos
      else if (N % 3 === 1) { let at = cc % this.L; for (let q = 0; q < this.L && this.rhy[at] >= 4; q++) at = (at + 1) % this.L; this.rhy[at]++; }
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
      // three against two: on some chords one instrument breaks into triplets over the others' eighths
      let trip = null;
      if (this.ctl.triplets && this.ctl.period > 0 && hash(this.seed, cc, 3) < 0.2 + 0.5 * c) {
        const cand = layers.filter(l => l !== 'voice');
        if (cand.length) trip = cand[(N + cc) % cand.length];
      }
      // knee plays (Einstein on the Beach): the last chords of a movement become a spare interlude, the organ holding
      // the chord and a voice counting
      const knee = this.ctl.knees && bridge > 0;
      if (knee) { layers = ['organ', 'voice']; sil.sustain = false; sil.restBeats = 0; sil.onlyOne = null; }
      this.chord = {
        cc, ci, N, len, beats, density, inv, L: this.L, changed, mi, bridge, start: this.step, layers, sil, trip, knee,
        v: voicing(ci, inv), num: d, voiceCycle: this.voiceCycle, complexity: this.ctl.complexity, rhy: this.rhy.slice(), period: this.ctl.period,
      };
      // an intermission after each full cycle of five movements, when one is asked for
      if (mi === 0 && inMov === 0 && cc > 0 && this.ctl.intermission > 0) {
        this.pauseUntil = this.step + Math.round(this.ctl.intermission * 60 * this.ctl.tempo * 2 / 60);
        this.chord.start = this.pauseUntil; this.intermissions++;
      }
      this.chordEnd = this.chord.start + len;
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
    // every note that starts on this step: [instrument, midi, length in steps, velocity, part, offset (fraction of a step),
    // syllable]. Offsets carry the triplets; syllables are what the voice sings.
    advance() {
      const s = this.step;
      if (s >= this.stopAt) { this.finished = true; return { step: s, notes: [], chord: this.chord, newChord: false }; }
      let newChord = false;
      if (!this.chord || s >= this.chordEnd) { this.nextChord(); newChord = true; }
      const C = this.chord;
      if (s < this.pauseUntil) { this.step++; return { step: s, notes: [], chord: C, newChord, resting: true, intermission: true, count: this.count }; }
      const k = s - C.start, c = this.ctl.complexity / 100, notes = [], P = C.period;
      const resting = k < C.sil.restBeats * 2;
      const on = l => C.layers.includes(l) && !resting;
      const cell = LINE.slice(0, C.L);
      const v = C.v;
      const sing = m => {                                // the voice's words: the numbers themselves, or solfège
        const t = this.ctl.text;
        if (t === 'numbers') return String(this.nums.seq[this.voiceIdx++ % 16]);
        if (t === 'solfege') return SOLFEGE[((m % 12) + 12) % 12];
        return null;
      };
      const push = (inst, m, len, vel, part, off, syl) => notes.push([inst, m, len, vel, part, off || 0, syl || null]);
      // ── the knee play: organ holds the chord, a voice counts the beats, one to eight ──
      if (C.knee) {
        if (k === 0) for (const m of v) push('organ', m - 12, C.len, 0.42, 'hold');
        if (k % 2 === 0) push('voice', tone(v, (k / 2) % v.length) , 2, 0.55, 'count', 0, String((k / 2) % 8 + 1));
        this.step++;
        return { step: s, notes, chord: C, newChord, resting: false, count: (k / 2) % 8 + 1, knee: true };
      }
      // ── the 1960s: no harmony, one line in parallel fifths, additive rhythm, everyone in unison ──
      if (P === 0) {
        if (!resting && s >= this.leadNext) {
          const i = this.leadPos % C.L, deg = cell[i], len = C.rhy[i];
          const m = 65 + F_MINOR[deg % 7] + 12 * Math.floor(deg / 7);
          push('lead', m, len, 0.6 + 0.1 * (i === 0), 'lead');
          if (on('piano')) push('piano', m - 12, len, 0.5, 'line');
          if (on('organ')) push('organ', m - 19, len, 0.4, 'fifths');                // a fifth below, an octave down
          if (on('violin')) push('violin', m + 7, len, 0.42, 'fifths');              // and a fifth above
          if (on('voice')) push('voice', m - 12, len, 0.45, 'line', 0, sing(m));
          this.leadPos++; if (this.leadPos % C.L === 0) this.count++;
          this.leadNext = s + len;
        }
        this.step++;
        return { step: s, notes, chord: C, newChord, resting, count: this.count };
      }
      if (!resting && C.sil.sustain) {
        // a chord held without rhythm: the organ only, once, for the whole chord
        if (k === C.sil.restBeats * 2) for (const m of v) push('organ', m - 12, C.len - k, 0.5, 'hold');
      } else if (!resting) {
        // the lead line on the dial's instrument: Euclidean attacks through the bar, or additive rhythm through the phrase
        if (this.ctl.rhythm === 'additive') {
          if (s >= this.leadNext) {
            const i = this.leadPos % C.L, len = C.rhy[i];
            push('lead', tone(v, cell[i]) + 12, len, 0.62 + 0.1 * (i === 0), 'lead');
            this.leadPos++; if (this.leadPos % C.L === 0) this.count++;
            this.leadNext = s + len;
          }
        } else {
          const bar = euclid(C.density, 8, C.inv);
          if (bar[k % 8]) {
            const idx = Math.floor(k / 8) * C.density + bar.slice(0, k % 8 + 1).filter(Boolean).length - 1;
            push('lead', tone(v, cell[idx % C.L]) + 12, 2, 0.62 + 0.1 * (idx % C.L === 0), 'lead');
            if (idx % C.L === C.L - 1) this.count++;
          }
        }
        // three against two: the chosen instrument plays rising and falling triplet arpeggios over the eighths
        const trip = C.trip && on(C.trip) ? C.trip : null;
        if (trip) {
          const offs = k % 2 === 0 ? [0, 2 / 3] : [1 / 3];
          offs.forEach((o, n) => {
            const j = Math.round((k + o) * 1.5), up = [0, 1, 2, 3, 2, 1][j % 6];
            push(trip, tone(v, up) + (trip === 'organ' ? -12 : 0), 2 / 3, trip === 'organ' ? 0.32 : 0.46, 'triplet', o);
          });
        }
        // piano: a cycle of 5 eighths, the phrase walked in fives, so its alignment with the bar keeps moving
        if (on('piano') && trip !== 'piano') {
          const p = s % CYCLE.piano, hits = euclid(Math.min(C.density, 4) - (c < 0.3 ? 1 : 0), CYCLE.piano, C.inv);
          if (hits[p]) { const i = Math.floor(s / CYCLE.piano) + p; push('piano', tone(v, cell[i % C.L]), 2, 0.5, 'cycle'); }
        }
        // organ: the chord, sustained and re-voiced on a cycle of 7
        if (on('organ') && trip !== 'organ' && (s % CYCLE.organ === 0 || k === 0)) {
          const m = Math.floor(s / CYCLE.organ) % 2 === 0 ? v : voicing(C.ci, (C.inv + 1) % 3);
          for (const x of m) push('organ', x - 12, Math.min(CYCLE.organ, C.len - k), 0.35, 'cycle');
        }
        // violin: a cycle of 11, long bowed notes from the phrase, an octave up
        if (on('violin') && trip !== 'violin' && c > 0.2) {
          const p = s % CYCLE.violin, hits = euclid(2 + Math.round(2 * c), CYCLE.violin, C.N % CYCLE.violin);
          if (hits[p]) { const i = Math.floor(s / CYCLE.violin) * 3 + p; push('violin', tone(v, cell[(i + 1) % C.L]) + 12, 4 + Math.round(3 * (1 - c)), 0.45, 'cycle'); }
        }
        // voice: its cycle is chosen afresh by each number (3–8 eighths); it sings the numbers, or solfège
        if (on('voice') && c > 0.35) {
          const vc = C.voiceCycle, p = s % vc;
          if (p === 0 || (c > 0.75 && p === Math.floor(vc / 2))) { const m = tone(v, cell[Math.floor(s / vc) % C.L]); push('voice', m, vc, 0.5, 'cycle', 0, sing(m)); }
        }
      }
      // the operas: a ground bass, the same figure every bar, under every chord (the chaconne idea)
      if (P === 2 && !resting) {
        const root = v[0] - 24 - (v[0] - 24 > 40 ? 12 : 0), fig = { 0: [0, 3], 3: [7, 2], 5: [12, 2], 7: [7, 1] }[k % 8];
        if (fig) push('bass', root + fig[0], fig[1], 0.6, 'ground');
      }
      this.step++;
      return { step: s, notes, chord: C, newChord, resting, count: this.count };
    }
  }

  // ── audio ─────────────────────────────────────────────────────────────
  const mtof = m => 440 * Math.pow(2, (m - 69) / 12);
  class Audio {
    constructor() {
      const A = this.ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: 'playback' });
      // the master: a touch of tape-like saturation and a soft top, then gentle compression
      this.out = A.createGain(); this.out.gain.value = 0.8;
      const drive = A.createGain(); drive.gain.value = 1.4;
      const sat = A.createWaveShaper(); sat.curve = this.tanhCurve(1.6); sat.oversample = '2x';
      const trim = A.createGain(); trim.gain.value = 0.78;
      const air = A.createBiquadFilter(); air.type = 'lowpass'; air.frequency.value = 14500; air.Q.value = 0.5;
      const warm = A.createBiquadFilter(); warm.type = 'lowshelf'; warm.frequency.value = 180; warm.gain.value = 3.5;
      const hp = A.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 38;
      const comp = A.createDynamicsCompressor(); comp.threshold.value = -18; comp.ratio.value = 2.5; comp.knee.value = 12; comp.attack.value = 0.02; comp.release.value = 0.35;
      this.out.connect(drive); drive.connect(sat); sat.connect(trim); trim.connect(warm); warm.connect(air); air.connect(hp); hp.connect(comp); comp.connect(A.destination);
      this.rec = A.createMediaStreamDestination(); comp.connect(this.rec);
      // the room: early reflections and a diffuse, darkening tail, different in each ear
      this.verb = A.createConvolver(); this.verb.buffer = this.impulse(3.6);
      this.verbIn = A.createGain(); this.verbIn.gain.value = 0.35;
      const pre = A.createDelay(0.1); pre.delayTime.value = 0.022;
      this.verbIn.connect(pre); pre.connect(this.verb); this.verb.connect(this.out);
      // shared material: one long noise buffer, and the harmonic spectra of each instrument
      const nb = A.createBuffer(1, A.sampleRate * 2, A.sampleRate), nd = nb.getChannelData(0);
      for (let i = 0; i < nd.length; i++) nd[i] = Math.random() * 2 - 1;
      this.noise = nb;
      const wave = amps => { const re = new Float32Array(amps.length + 1), im = new Float32Array(amps.length + 1); amps.forEach((a, k) => { im[k + 1] = a; }); return A.createPeriodicWave(re, im, { disableNormalization: false }); };
      // piano strings struck at about 1/8 of their length: every 8th partial nearly missing, the rest falling away
      this.waves = {
        piano: wave(Array.from({ length: 28 }, (_, k) => ((k + 1) % 8 === 0 ? 0.08 : 1) / Math.pow(k + 1, 1.45))),
        // a principal pipe: strong fundamental and octave, quieter fifth and higher ranks
        organ: wave([1, 0.55, 0.32, 0.22, 0.1, 0.13, 0.05, 0.07, 0.03, 0.04, 0.02, 0.02]),
        // a bowed string: a sawtooth's rich series, slightly softened at the top
        violin: wave(Array.from({ length: 40 }, (_, k) => 1 / Math.pow(k + 1, 1.15) * Math.exp(-k / 16))),
        // a voice: the glottal pulse falls off at about 12 dB an octave
        voice: wave(Array.from({ length: 30 }, (_, k) => 1 / Math.pow(k + 1, 1.9))),
        // the Glass Ensemble: a transistor combo organ (hollow, mostly odd harmonics), a soprano saxophone's reed
        combo: wave(Array.from({ length: 24 }, (_, k) => ((k + 1) % 2 ? 1 : 0.22) / (k + 1))),
        reed: wave(Array.from({ length: 30 }, (_, k) => (k === 0 ? 0.6 : 1) / Math.pow(k + 1, 0.95) * Math.exp(-k / 11))),
      };
      // each instrument's body: the resonances that make a string a violin and a frame a piano
      const BODY = {
        piano: [['peaking', 95, 1.0, 3.5], ['peaking', 220, 1.2, 2], ['peaking', 380, 1.4, 1.5], ['peaking', 1600, 1.6, -2], ['peaking', 3200, 2, 1.5], ['lowpass', 9000, 0.6, 0]],
        organ: [['peaking', 70, 0.9, 3], ['peaking', 250, 1, 1.5], ['peaking', 2400, 1.5, -2.5], ['lowpass', 6500, 0.6, 0]],
        violin: [['highpass', 60, 0.7, 0], ['peaking', 120, 1.6, 3], ['peaking', 290, 3, 5], ['peaking', 480, 2.5, 3], ['peaking', 1150, 2, 2], ['peaking', 2800, 2.5, 4.5],
                 ['peaking', 4300, 2, -4], ['lowpass', 7200, 0.7, 0]],
        voice: [['highpass', 55, 0.7, 0], ['peaking', 160, 1.4, 4], ['peaking', 3000, 1.5, 2], ['lowpass', 8000, 0.6, 0]],
        bass: [['highpass', 28, 0.7, 0], ['peaking', 80, 1.1, 3], ['lowpass', 3200, 0.6, 0]],
      };
      const PAN = { piano: -0.25, organ: 0, violin: 0.3, voice: 0.1, bass: 0 };
      this.panBase = PAN; this.pan = {}; this.ride = {};
      this.bus = {}; this.send = {};
      for (const n of PARTS) {
        const g = A.createGain(); g.gain.value = 0.8;
        const ride = A.createGain(); g.connect(ride); this.ride[n] = ride;        // the sound engineer's hand, separate from the fader
        let last = ride;
        for (const [type, f, q, gain] of BODY[n]) { const b = A.createBiquadFilter(); b.type = type; b.frequency.value = f; b.Q.value = q; b.gain.value = gain; last.connect(b); last = b; }
        const pan = A.createStereoPanner(); pan.pan.value = PAN[n]; last.connect(pan); pan.connect(this.out); this.pan[n] = pan;
        const sd = A.createGain(); sd.gain.value = n === 'voice' ? 0.45 : n === 'violin' ? 0.4 : n === 'bass' ? 0.12 : 0.32; pan.connect(sd); sd.connect(this.verbIn);
        this.bus[n] = g; this.send[n] = sd;
      }
      // the piano's soundboard: a short, woody resonance added to the strings
      this.board = A.createConvolver(); this.board.buffer = this.impulse(0.35, 0.6);
      const bg = A.createGain(); bg.gain.value = 0.35; this.bus.piano.connect(this.board); this.board.connect(bg); bg.connect(this.out);
      // the lead line has its own fader per instrument, so the dial can crossfade between them
      this.lead = {}; this.leadOn = 0;
      for (let i = 0; i < 4; i++) { const g = A.createGain(); g.gain.value = i === 0 ? 1 : 0; g.connect(this.bus[INSTRUMENTS[i]]); this.lead[i] = g; }
      this.leadRecent = [0, -1, -1, -1];                                  // when each was last faded out
      this.vibrato = A.createOscillator(); this.vibrato.frequency.value = 5.4; this.vibrato.start();
      this.tremulant = A.createOscillator(); this.tremulant.frequency.value = 0.7; this.tremulant.start();   // a slow organ swell
      this.voice = { buffer: null, mode: 'harmonizer', clarity: 0.6, wet: 0.45, layers: 2, speed: 1, reps: 1, trim: [0, 1], base: 57, bands: null };
      this.live = 0;                                                      // notes sounding, for a polyphony cap
      this.oct = { piano: 0, organ: 0, violin: 0, voice: 0, bass: 0 };     // each instrument's octave dial
      this.preset = 'chamber'; this.engineer = false; this.text = 'numbers';
      this.ks = false;                                                    // the physically modelled piano, once its worklet has loaded
      if (A.audioWorklet) A.audioWorklet.addModule('/static/darwin/algo/glass/strings-worklet.js?v=1').then(() => { this.ks = true; }).catch(() => {});
    }
    tanhCurve(k) { const n = 2048, c = new Float32Array(n); for (let i = 0; i < n; i++) { const x = i / (n - 1) * 2 - 1; c[i] = Math.tanh(k * x) / Math.tanh(k); } return c; }
    impulse(sec, bright) {
      // a stereo room: a few early reflections, then decorrelated noise that darkens and thins as it decays
      const A = this.ctx, sr = A.sampleRate, n = Math.floor(sr * sec), b = A.createBuffer(2, n, sr), br = bright || 0;
      for (let ch = 0; ch < 2; ch++) {
        const d = b.getChannelData(ch); let lp = 0;
        for (let i = 0; i < n; i++) {
          const t = i / n, k = 0.12 + 0.8 * t * (1 - br);
          lp = lp * k + (Math.random() * 2 - 1) * (1 - k);
          d[i] = lp * Math.pow(1 - t, 2.6) * 1.6 * Math.min(1, i / (sr * 0.008));
        }
        if (sec > 1) for (let r = 0; r < 9; r++) {                    // early reflections off walls at different distances
          const at = Math.floor(sr * (0.007 + r * 0.011 + (ch ? 0.003 : 0) + Math.random() * 0.006));
          if (at < n) d[at] += (Math.random() < 0.5 ? -1 : 1) * 0.5 * Math.pow(0.82, r);
        }
      }
      return b;
    }
    noiseSrc(t) { const s = this.ctx.createBufferSource(); s.buffer = this.noise; s.loop = true; s.start(t, Math.random() * 1.5); return s; }
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
    play(inst, midi, dur, vel, t, syl) {
      this._syl = syl || null;
      if (this.live > 56) return;
      const at = (name, m) => { m += 12 * (this.oct[name] || 0); while (m < 24) m += 12; while (m > 108) m -= 12; return m; };   // fold, never pile up
      if (inst === 'lead') {
        for (let k = 0; k < 4; k++) if (k === this.leadOn || this.leadRecent[k] > t) this.voiceFor(INSTRUMENTS[k], at(INSTRUMENTS[k], midi), dur, vel, t, this.lead[k]);
        return;
      }
      this.voiceFor(inst, at(inst, midi), dur, vel, t, this.bus[inst]);
    }
    // slow, irregular movement on a parameter: what keeps a held note from sounding like a fixed waveform
    wobble(param, depth, t, end, nodes) {
      const A = this.ctx, o = A.createOscillator(), g = A.createGain();
      o.frequency.value = 0.15 + Math.random() * 0.55; g.gain.value = depth;
      o.connect(g); g.connect(param); o.start(t, Math.random() * 3); o.stop(end); nodes.push(o, g);
    }
    voiceFor(inst, midi, dur, vel, t, dest) {
      if (this.preset === 'ensemble') {          // the Philip Glass Ensemble: amplified organs, reeds, soprano, bass
        if (inst === 'piano') return this.comboOrgan(midi, dur, vel, t, dest);
        if (inst === 'organ') return this.comboOrgan(midi, dur, vel * 0.85, t, dest, true);
        if (inst === 'violin') { this.sax(midi, dur, vel, t, dest); return this.flute(midi + 12, dur, vel * 0.45, t, dest); }
        if (inst === 'bass') return this.ebass(midi, dur, vel, t, dest);
        return this.voiceNote(midi + 12, dur, vel, t, dest, true);
      }
      if (inst === 'piano') return this.piano(midi, dur, vel, t, dest);
      if (inst === 'organ') return this.organ(midi, dur, vel, t, dest);
      if (inst === 'violin') return this.violin(midi, dur, vel, t, dest);
      if (inst === 'bass') return this.organ(midi + 12, dur, vel * 1.1, t, dest);     // pedal pipes, with their 16' below
      return this.voiceNote(midi, dur, vel, t, dest);
    }
    // the sound engineer (Kurt Munkacsi mixed the Glass Ensemble live, as one of its members): at each chord the
    // numbers ease each part's level and place somewhere new, slowly
    rideMix(chord, t) {
      for (const n of PARTS) {
        const g = this.ride[n].gain, p = this.pan[n].pan;
        if (!this.engineer) { g.setTargetAtTime(1, t, 1.5); p.setTargetAtTime(this.panBase[n], t, 2); continue; }
        const h = hash(chord.cc, chord.N, PARTS.indexOf(n)), h2 = hash(chord.N, chord.cc * 7, PARTS.indexOf(n) + 11);
        g.setTargetAtTime(0.55 + 0.65 * h, t, 4); p.setTargetAtTime(Math.max(-0.85, Math.min(0.85, this.panBase[n] + (h2 - 0.5) * 1.1)), t, 6);
      }
    }
    _done(nodes, last) {                                                  // tidy every node a note made, when its last source ends
      this.live++;
      last.onended = () => { this.live--; for (const n of nodes) { try { n.disconnect(); } catch (e) {} } };
    }
    // piano: three slightly detuned strings per note, a felt hammer, a brightness that fades faster than the loudness,
    // a quick first decay and a long singing second one, and the soundboard on the bus
    piano(m, dur, vel, t, dest) {
      if (this.ks) return this.stringPiano(m, dur, vel, t, dest);
      const A = this.ctx, f = mtof(m), nodes = [];
      const lp = A.createBiquadFilter(); lp.type = 'lowpass'; lp.Q.value = 0.4;
      const bright = Math.min(14000, f * (3 + 14 * vel * vel) + 900);
      const T2 = Math.max(1.2, 9 - (m - 40) * 0.12), T1 = Math.max(0.25, 1.1 - (m - 40) * 0.012);
      lp.frequency.setValueAtTime(bright, t); lp.frequency.setTargetAtTime(Math.max(f * 2.2, 500), t + 0.01, T1 * 1.6);
      const g = A.createGain(), amp = 0.07 * (0.35 + 0.65 * vel);
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(amp, t + 0.003);
      g.gain.setTargetAtTime(amp * 0.32, t + 0.003, T1 / 2.2);                    // the prompt sound
      g.gain.setTargetAtTime(0, t + T1, T2 / 3);                                   // the long aftersound
      const ring = Math.min(T2, Math.max(1.4, dur * 2.5)), end = t + ring + 0.5;
      g.gain.setTargetAtTime(0, t + ring, 0.12);                                   // the damper comes down
      const pan = A.createStereoPanner(); pan.pan.value = Math.max(-0.6, Math.min(0.6, (m - 64) / 40));
      lp.connect(g); g.connect(pan); pan.connect(dest); nodes.push(lp, g, pan);
      let last = null;
      for (const det of [-1.6, 0.2, 1.9]) {
        const o = A.createOscillator(); o.setPeriodicWave(this.waves.piano);
        o.frequency.value = f; o.detune.value = det + (Math.random() - 0.5) * 0.8;
        const og = A.createGain(); og.gain.value = 0.36; o.connect(og); og.connect(lp);
        o.start(t); o.stop(end); nodes.push(o, og); last = o;
      }
      // the stretched upper partials of a real string, a little sharp of the harmonic series
      for (const [h, a] of [[2, 0.12], [3, 0.06]]) {
        const o = A.createOscillator(), og = A.createGain(); o.frequency.value = f * h * (1 + 0.00035 * h * h);
        og.gain.setValueAtTime(a * amp * 3, t); og.gain.setTargetAtTime(0, t, T1 * 0.8);
        o.connect(og); og.connect(pan); o.start(t); o.stop(t + T1 * 4); nodes.push(o, og);
      }
      // the hammer: a soft thud of felt, lower and shorter for quiet notes
      const nz = this.noiseSrc(t), hb = A.createBiquadFilter(), hg = A.createGain();
      hb.type = 'bandpass'; hb.frequency.value = Math.min(4000, f * 2.5 + 300); hb.Q.value = 0.9;
      hg.gain.setValueAtTime(0.03 * vel, t); hg.gain.setTargetAtTime(0, t, 0.006 + 0.01 * (1 - vel));
      nz.connect(hb); hb.connect(hg); hg.connect(pan); nz.stop(t + 0.08); nodes.push(nz, hb, hg);
      this._done(nodes, last);
    }
    // the physically modelled piano (strings-worklet.js): three strings, hammer, stiffness, damper
    stringPiano(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), sr = A.sampleRate;
      const t60 = Math.max(1.4, Math.min(16, 16 - (m - 28) * 0.2)), ring = Math.min(t60, Math.max(1.8, dur * 3));
      let node;
      try {
        node = new AudioWorkletNode(A, 'struck-string', { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [1],
          processorOptions: { f, vel, start: Math.round(t * sr), ring, t60, seed: (m * 7919 + Math.floor(t * 1000)) | 0 } });
      } catch (e) { this.ks = false; return this.piano(m, dur, vel, t, dest); }
      const g = A.createGain(); g.gain.value = 0.55 * (0.3 + 0.7 * vel);
      const pan = A.createStereoPanner(); pan.pan.value = Math.max(-0.6, Math.min(0.6, (m - 64) / 40));
      node.connect(g); g.connect(pan); pan.connect(dest);
      // the felt hammer's thud, below the string's tone
      const nz = this.noiseSrc(t), hb = A.createBiquadFilter(), hg = A.createGain();
      hb.type = 'lowpass'; hb.frequency.value = Math.min(2500, f * 2 + 200);
      hg.gain.setValueAtTime(0.025 * vel, t); hg.gain.setTargetAtTime(0, t, 0.008);
      nz.connect(hb); hb.connect(hg); hg.connect(pan); nz.stop(t + 0.06);
      this.live++;
      const nodes = [node, g, pan, nz, hb, hg];
      setTimeout(() => { this.live--; for (const n of nodes) { try { n.disconnect(); } catch (e) {} } }, (t - A.currentTime + ring + 1) * 1000);
    }
    // organ: a principal rank and a gently beating celeste, a puff of air as the pipe speaks, a slow swell
    organ(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), nodes = [], L = dur, amp = vel * 0.06;
      const g = A.createGain();
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(amp, t + 0.09);
      g.gain.setValueAtTime(amp, t + Math.max(0.1, L - 0.05)); g.gain.setTargetAtTime(0, t + Math.max(0.1, L - 0.05), 0.09);
      const tg = A.createGain(), swell = A.createGain(); swell.gain.value = 0.07; this.tremulant.connect(swell); swell.connect(tg.gain);   // a swell that multiplies, never leaks
      g.connect(tg); tg.connect(dest); nodes.push(g, tg, swell);
      let last = null;
      this.wobble(tg.gain, 0.04, t, t + L + 0.6, nodes);                  // the wind is never perfectly steady
      for (const [det, a, mul] of [[0, 0.62, 1], [4.5, 0.38, 1], [-3, 0.2, 2], [1.5, m > 48 ? 0.42 : 0.2, 0.5]]) {   // 8', celeste, 4', and a 16' bourdon below
        const o = A.createOscillator(); o.setPeriodicWave(mul === 0.5 ? this.waves.voice : this.waves.organ); o.frequency.value = f * mul;
        o.detune.setValueAtTime(det - 14, t); o.detune.linearRampToValueAtTime(det, t + 0.07);   // the pipe settles onto its pitch
        const og = A.createGain(); og.gain.value = a; o.connect(og); og.connect(g);
        o.start(t); o.stop(t + L + 0.6); nodes.push(o, og); last = o;
      }
      // chiff: the breath at the pipe's mouth before the tone takes over
      const nz = this.noiseSrc(t), cb = A.createBiquadFilter(), cg = A.createGain();
      cb.type = 'bandpass'; cb.frequency.value = Math.min(6000, f * 4); cb.Q.value = 3;
      cg.gain.setValueAtTime(0, t); cg.gain.linearRampToValueAtTime(0.025 * vel, t + 0.015); cg.gain.setTargetAtTime(0.002 * vel, t + 0.02, 0.04);
      cg.gain.setTargetAtTime(0, t + Math.max(0.1, L - 0.05), 0.08);
      nz.connect(cb); cb.connect(cg); cg.connect(dest); nz.stop(t + L + 0.5); nodes.push(nz, cb, cg);
      this._done(nodes, last);
    }
    // violin: two players a few cents apart, bow hair on the string (filtered noise riding the bow pressure), a bow that
    // bites and then opens up, a small scoop into pitch, and a vibrato that arrives late and never quite repeats
    violin(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), nodes = [], L = dur, amp = vel * 0.05;
      const env = A.createGain(), lp = A.createBiquadFilter();
      lp.type = 'lowpass'; lp.Q.value = 0.8;
      lp.frequency.setValueAtTime(900 + f, t); lp.frequency.linearRampToValueAtTime(2600 + 3 * f + 2500 * vel, t + 0.18);
      env.gain.setValueAtTime(0, t); env.gain.linearRampToValueAtTime(amp * 0.85, t + 0.07); env.gain.linearRampToValueAtTime(amp, t + Math.min(0.5, L * 0.5));
      env.gain.setValueAtTime(amp, t + Math.max(0.1, L - 0.08)); env.gain.setTargetAtTime(0, t + Math.max(0.1, L - 0.08), 0.12);
      lp.connect(env); env.connect(dest); nodes.push(lp, env);
      const bow = A.createGain(); env.disconnect(); env.connect(bow); bow.connect(dest); nodes.push(bow);
      this.wobble(bow.gain, 0.08, t, t + L + 0.6, nodes); this.wobble(lp.frequency, 380, t, t + L + 0.6, nodes);   // bow pressure and speed never hold still
      const vib = A.createOscillator(), vd = A.createGain(); vib.frequency.value = 5.2 + Math.random() * 0.8;
      vd.gain.setValueAtTime(0, t); vd.gain.setValueAtTime(0, t + Math.min(0.25, L * 0.3)); vd.gain.linearRampToValueAtTime(11 + 5 * Math.random(), t + Math.min(0.8, L * 0.7));
      const drift = A.createOscillator(), dd = A.createGain(); drift.frequency.value = 0.4 + Math.random() * 0.5; dd.gain.value = 3;
      vib.connect(vd); drift.connect(dd); vib.start(t); drift.start(t); vib.stop(t + L + 0.6); drift.stop(t + L + 0.6); nodes.push(vib, vd, drift, dd);
      let last = null;
      for (const [det, a, p] of [[-5, 0.55, -0.35], [4, 0.5, 0.35]]) {
        const o = A.createOscillator(); o.setPeriodicWave(this.waves.violin); o.frequency.value = f;
        o.detune.setValueAtTime(det - 22, t); o.detune.setTargetAtTime(det, t, 0.04);
        vd.connect(o.detune); dd.connect(o.detune);
        const og = A.createGain(); og.gain.value = a; const pn = A.createStereoPanner(); pn.pan.value = p;
        o.connect(og); og.connect(pn); pn.connect(lp); o.start(t); o.stop(t + L + 0.6); nodes.push(o, og, pn); last = o;
      }
      const nz = this.noiseSrc(t), nb = A.createBiquadFilter(), ng = A.createGain();
      nb.type = 'bandpass'; nb.frequency.value = 2600 + f; nb.Q.value = 1.2;
      ng.gain.setValueAtTime(0, t); ng.gain.linearRampToValueAtTime(0.012 * vel, t + 0.05); ng.gain.setTargetAtTime(0.004 * vel, t + 0.06, 0.15);
      ng.gain.setTargetAtTime(0, t + Math.max(0.1, L - 0.08), 0.1);
      nz.connect(nb); nb.connect(ng); ng.connect(env); nz.stop(t + L + 0.5); nodes.push(nz, nb, ng);
      this._done(nodes, last);
    }
    // the voice: a recorded word or phrase, reharmonised; with nothing recorded, a sung vowel
    voiceNote(m, dur, vel, t, dest, soprano) {
      const V = this.voice, chord = this.currentChord || [m], syl = this._syl;
      const tones = [m]; for (const x of chord) if (tones.length < V.layers && (x % 12) !== (m % 12)) tones.push(x + 12 * Math.round((m - x) / 12));
      for (let r = 0; r < V.reps; r++) {
        const tt = t + r * (dur / V.reps);
        for (let i = 0; i < tones.length; i++) {
          const g = vel * (i === 0 ? 1 : 0.6) / Math.sqrt(tones.length);
          if (syl && !(V.buffer && this.text === 'recording')) this.singSyl(tones[i], dur / V.reps, g, tt, dest, syl, soprano);
          else if (!V.buffer || this.text !== 'recording') this.vowel(tones[i], dur / V.reps, g, tt, dest);
          else if (V.mode === 'vocoder') this.vocode(tones[i], dur / V.reps, g, tt, dest);
          else this.harmonize(tones[i], dur / V.reps, g, tt, dest);
        }
      }
    }
    // the voice with nothing recorded: three singers on an 'ah' that drifts toward 'oh', breath in the sound
    vowel(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), nodes = [], L = Math.max(0.35, dur), amp = vel * 0.05;
      const g = A.createGain();
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(amp, t + 0.16); g.gain.setValueAtTime(amp, t + L * 0.85); g.gain.setTargetAtTime(0, t + L * 0.85, 0.15);
      g.connect(dest); nodes.push(g);
      const src = A.createGain(); src.gain.value = 0.5; nodes.push(src);
      let last = null;
      this.wobble(g.gain, amp * 0.12, t, t + L + 0.6, nodes);
      for (const [det, p, mul] of [[-9, -0.4, 1], [0, 0, 1], [8, 0.4, 1], [-4, 0.15, 0.5]]) {   // three singers and a bass an octave below
        const o = A.createOscillator(); o.setPeriodicWave(this.waves.voice); o.frequency.value = f * mul; o.detune.value = det;
        const vib = A.createGain(); vib.gain.setValueAtTime(0, t); vib.gain.linearRampToValueAtTime(8, t + 0.5); this.vibrato.connect(vib); vib.connect(o.detune);
        const pn = A.createStereoPanner(); pn.pan.value = p; o.connect(pn); pn.connect(src);
        o.start(t); o.stop(t + L + 0.6); nodes.push(o, vib, pn); last = o;
      }
      const nz = this.noiseSrc(t), ng = A.createGain(); ng.gain.value = 0.05; nz.connect(ng); ng.connect(src); nz.stop(t + L + 0.6); nodes.push(nz, ng);
      for (const [f0, f1, q, a] of [[730, 570, 9, 1], [1090, 840, 11, 0.55], [2440, 2410, 14, 0.3], [3300, 3200, 16, 0.12]]) {
        const bp = A.createBiquadFilter(); bp.type = 'bandpass'; bp.Q.value = q;
        bp.frequency.setValueAtTime(f0, t); bp.frequency.linearRampToValueAtTime(f1, t + L);
        const bg = A.createGain(); bg.gain.value = a * 3.2; src.connect(bp); bp.connect(bg); bg.connect(g); nodes.push(bp, bg);
      }
      this._done(nodes, last);
    }
    // ── singing words: a small formant speech synthesizer, so the choir can sing the numbers and solfège ──
    // each phoneme: [voiced level, noise level, noise centre Hz, F1, F2, F3, duration ms (0 = the vowel, which fills the rest)]
    singSyl(m, dur, vel, t, dest, syl, soprano) {
      const A = this.ctx, f = mtof(m), L = Math.max(0.18, dur * 0.95), nodes = [];
      const ph = (WORDS[syl] || WORDS.ah).map(p => PHON[p]);
      const fixed = ph.reduce((a, p) => a + (p[6] || 0), 0) / 1000, vowels = ph.filter(p => !p[6]).length || 1;
      const scale = fixed > L * 0.6 ? (L * 0.6) / fixed : 1, vlen = Math.max(0.06, (L - fixed * scale) / vowels);
      const out = A.createGain(); out.gain.value = vel * (soprano ? 0.18 : 0.22); out.connect(dest); nodes.push(out);
      const vg = A.createGain(), ng = A.createGain(); vg.gain.value = 0; ng.gain.value = 0;
      const src = A.createGain(); vg.connect(src); nodes.push(vg, ng, src);
      let last = null;
      for (const [det, mul, a] of [[-6, 1, 0.55], [5, 1, 0.45]]) {
        const o = A.createOscillator(); o.setPeriodicWave(this.waves.voice); o.frequency.value = f * mul; o.detune.value = det;
        const vib = A.createGain(); vib.gain.setValueAtTime(0, t); vib.gain.linearRampToValueAtTime(soprano ? 14 : 9, t + Math.min(0.6, L)); this.vibrato.connect(vib); vib.connect(o.detune);
        const og = A.createGain(); og.gain.value = a; o.connect(og); og.connect(vg); o.start(t); o.stop(t + L + 0.25); nodes.push(o, vib, og); last = o;
      }
      const nz = this.noiseSrc(t), nb = A.createBiquadFilter(); nb.type = 'bandpass'; nb.Q.value = 1.6;
      nz.connect(nb); nb.connect(ng); ng.connect(out); nz.stop(t + L + 0.25); nodes.push(nz, nb);
      const F = [0, 1, 2].map(i => { const b = A.createBiquadFilter(); b.type = 'bandpass'; b.Q.value = [7, 9, 11][i]; const g = A.createGain(); g.gain.value = [3.2, 2, 1.1][i]; src.connect(b); b.connect(g); g.connect(out); nodes.push(b, g); return b; });
      const lift = soprano ? 1.12 : 1;                                  // a higher voice's formants sit a little higher
      let at = t;
      ph.forEach((p, i) => {
        const d = p[6] ? p[6] / 1000 * scale : vlen, x = Math.min(0.03, d * 0.4);
        vg.gain.setTargetAtTime(p[0], at, x / 2); ng.gain.setTargetAtTime(p[1] * 0.35, at, 0.008);
        if (p[2]) nb.frequency.setValueAtTime(p[2], at);
        for (let k = 0; k < 3; k++) {                                     // glide from the last phoneme's formants to this one's
          if (i === 0) F[k].frequency.setValueAtTime(p[3 + k] * lift, at);
          else { F[k].frequency.setValueAtTime(ph[i - 1][3 + k] * lift, at); F[k].frequency.linearRampToValueAtTime(p[3 + k] * lift, at + x); }
        }
        at += d;
      });
      vg.gain.setTargetAtTime(0, Math.max(at, t + L - 0.05), 0.04); ng.gain.setTargetAtTime(0, at, 0.01);
      this._done(nodes, last);
    }
    // a combo organ (the Farfisa sound of the early ensemble): hollow, buzzy, a quick vibrato, instant on and off;
    // held = sustained chords for the organ part
    comboOrgan(m, dur, vel, t, dest, held) {
      const A = this.ctx, f = mtof(m), nodes = [], L = Math.max(0.12, dur * (held ? 1 : 0.9)), amp = vel * (held ? 0.045 : 0.05);
      const g = A.createGain(), lp = A.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = held ? 2600 : 3800; lp.Q.value = 0.7;
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(amp, t + 0.008); g.gain.setValueAtTime(amp, t + L); g.gain.linearRampToValueAtTime(0, t + L + 0.03);
      g.connect(lp); lp.connect(dest); nodes.push(g, lp);
      const dep = A.createGain(); dep.gain.value = 10; const lfo = A.createOscillator(); lfo.frequency.value = 6.3; lfo.connect(dep); lfo.start(t); lfo.stop(t + L + 0.05); nodes.push(dep, lfo);
      let last = null;
      for (const [mul, a, det] of [[1, 0.6, 0], [2, 0.32, 3], [0.5, held ? 0.3 : 0.12, -2]]) {
        const o = A.createOscillator(); o.setPeriodicWave(this.waves.combo); o.frequency.value = f * mul; o.detune.value = det; dep.connect(o.detune);
        const og = A.createGain(); og.gain.value = a; o.connect(og); og.connect(g); o.start(t); o.stop(t + L + 0.05); nodes.push(o, og); last = o;
      }
      this._done(nodes, last);
    }
    // soprano saxophone: a reed through the horn's resonances, breath, a scoop into the note, a late vibrato
    sax(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), nodes = [], L = Math.max(0.12, dur * 0.95), amp = vel * 0.05;
      const g = A.createGain(), lp = A.createBiquadFilter(); lp.type = 'lowpass'; lp.Q.value = 0.6;
      lp.frequency.setValueAtTime(1200 + f, t); lp.frequency.linearRampToValueAtTime(2800 + 2 * f * vel, t + 0.06);
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(amp, t + 0.035); g.gain.setValueAtTime(amp, t + L); g.gain.setTargetAtTime(0, t + L, 0.04);
      lp.connect(g); nodes.push(g, lp);
      let tail = g;
      for (const [fr, q, gg] of [[700, 1.6, 4], [1600, 2, 3], [2900, 2.5, 2]]) { const b = A.createBiquadFilter(); b.type = 'peaking'; b.frequency.value = fr; b.Q.value = q; b.gain.value = gg; tail.connect(b); tail = b; nodes.push(b); }
      tail.connect(dest);
      const o = A.createOscillator(); o.setPeriodicWave(this.waves.reed); o.frequency.value = f;
      o.detune.setValueAtTime(-30, t); o.detune.setTargetAtTime(0, t, 0.03);
      const vd = A.createGain(); vd.gain.setValueAtTime(0, t); vd.gain.setValueAtTime(0, t + Math.min(0.3, L * 0.5)); vd.gain.linearRampToValueAtTime(12, t + Math.min(0.7, L)); this.vibrato.connect(vd); vd.connect(o.detune);
      o.connect(lp); o.start(t); o.stop(t + L + 0.25); nodes.push(o, vd);
      const nz = this.noiseSrc(t), nb = A.createBiquadFilter(), nng = A.createGain(); nb.type = 'bandpass'; nb.frequency.value = 2200; nb.Q.value = 0.8;
      nng.gain.setValueAtTime(0.018 * vel, t); nng.gain.setTargetAtTime(0.004 * vel, t + 0.03, 0.05); nng.gain.setTargetAtTime(0, t + L, 0.03);
      nz.connect(nb); nb.connect(nng); nng.connect(lp); nz.stop(t + L + 0.2); nodes.push(nz, nb, nng);
      this._done(nodes, o);
    }
    // flute: a nearly pure tone with breath around it, and a soft chiff
    flute(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), nodes = [], L = Math.max(0.12, dur * 0.95), amp = vel * 0.06;
      const g = A.createGain(); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(amp, t + 0.05); g.gain.setValueAtTime(amp, t + L); g.gain.setTargetAtTime(0, t + L, 0.05);
      g.connect(dest); nodes.push(g);
      const o = A.createOscillator(); o.frequency.value = f; const o2 = A.createOscillator(); o2.frequency.value = f * 2; const g2 = A.createGain(); g2.gain.value = 0.12;
      const vd = A.createGain(); vd.gain.value = 7; this.vibrato.connect(vd); vd.connect(o.detune); vd.connect(o2.detune);
      o.connect(g); o2.connect(g2); g2.connect(g); o.start(t); o2.start(t); o.stop(t + L + 0.3); o2.stop(t + L + 0.3); nodes.push(o, o2, g2, vd);
      const nz = this.noiseSrc(t), nb = A.createBiquadFilter(), nng = A.createGain(); nb.type = 'bandpass'; nb.frequency.value = f * 1.5; nb.Q.value = 2.5;
      nng.gain.setValueAtTime(0.5 * amp, t); nng.gain.setTargetAtTime(0.18 * amp, t + 0.04, 0.05); nng.gain.setTargetAtTime(0, t + L, 0.05);
      nz.connect(nb); nb.connect(nng); nng.connect(dest); nz.stop(t + L + 0.3); nodes.push(nz, nb, nng);
      this._done(nodes, o);
    }
    // electric bass: a round fundamental and a plucked, filtered string, fingers not a pick
    ebass(m, dur, vel, t, dest) {
      const A = this.ctx, f = mtof(m), nodes = [], L = Math.max(0.2, dur * 0.95), amp = vel * 0.11;
      const g = A.createGain(); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(amp, t + 0.006); g.gain.setTargetAtTime(amp * 0.55, t + 0.01, 0.25);
      g.gain.setTargetAtTime(0, t + L, 0.05); g.connect(dest); nodes.push(g);
      const lp = A.createBiquadFilter(); lp.type = 'lowpass'; lp.Q.value = 2; lp.frequency.setValueAtTime(900 + 600 * vel, t); lp.frequency.setTargetAtTime(260, t + 0.01, 0.18);
      lp.connect(g); nodes.push(lp);
      const o = A.createOscillator(); o.type = 'sawtooth'; o.frequency.value = f; const og = A.createGain(); og.gain.value = 0.45; o.connect(og); og.connect(lp);
      const s1 = A.createOscillator(); s1.frequency.value = f; const sg = A.createGain(); sg.gain.value = 0.8; s1.connect(sg); sg.connect(g);
      o.start(t); s1.start(t); o.stop(t + L + 0.3); s1.stop(t + L + 0.3); nodes.push(o, og, s1, sg);
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
    const PROG = { piano: 0, organ: 19, violin: 40, voice: 52, bass: 32 };
    PARTS.forEach((name, ch) => {
      const evs = [[0, [0xc0 | ch, PROG[name]]], [0, [0xff, 0x03, name.length, ...[...name].map(c => c.charCodeAt(0))]]];
      for (const [step, inst, midi, len, vel] of events) if (inst === name) {
        const v = Math.max(1, Math.min(127, Math.round(vel * 127))), n = Math.max(0, Math.min(127, midi));
        evs.push([Math.round(step * E), [0x90 | ch, n, v]], [Math.max(Math.round(step * E) + 1, Math.round((step + len) * E) - 1), [0x80 | ch, n, 0]]);
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

  window.Glass = { Numbers, Score, Audio, midiFile, wavBytes, CHORDS, MOVEMENTS, INSTRUMENTS, PARTS, SOLFEGE, CYCLE, LINE, hash, mulberry32, voicing, euclid };
})();
