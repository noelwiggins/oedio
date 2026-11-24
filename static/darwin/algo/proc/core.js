/* Process music core: the shared engine under AlgoRiley and AlgoReich.
   A score (deterministic, seeded, stepped) says what each player does; this file plays it on recorded instruments, draws it,
   takes the listener's controls at step boundaries (so a saved session replays exactly), and exports audio, MIDI and the
   session. Recordings come from the same library as AlgoGlass (samples/manifest.json). Nothing here synthesizes a tone. */
(function () {
  'use strict';
  const BASE = '/static/darwin/algo/glass/samples/';

  // ── seeded randomness for scores ──
  function rng(seed) { let a = seed >>> 0; return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

  // ── the instruments: where each one's recordings are in the manifest, and how it is played ──
  //  mallet: struck and left to ring; held: a sustained recording, looped for long notes; bowed: Iowa strings with a
  //  player's vibrato; piano: the Salamander grand with its damper; choir: four sections; clap: one-shots
  const INSTRUMENTS = {
    piano:    { label: 'Piano', type: 'piano', range: [33, 100], pan: -0.2, send: 0.3 },
    marimba:  { label: 'Marimba', type: 'mallet', set: m => m.proc.marimba, range: [41, 96], pan: 0.15, send: 0.28, ring: 1.6 },
    vibes:    { label: 'Vibraphone', type: 'mallet', set: m => m.proc.vibes, range: [53, 89], pan: 0.3, send: 0.36, ring: 3.2 },
    glock:    { label: 'Glockenspiel', type: 'mallet', set: m => m.proc.glock, range: [79, 108], pan: -0.35, send: 0.34, ring: 2.2 },
    claps:    { label: 'Claps', type: 'clap', set: m => m.proc.claps, range: [0, 127], pan: 0, send: 0.25 },
    organ:    { label: 'Organ', type: 'held', set: m => ({ p: m.ens.ren8, f: m.ens.renfull }), range: [36, 84], pan: -0.1, send: 0.35, gain: 0.32 },
    pipe:     { label: 'Pipe organ', type: 'held', set: m => ({ p: m.organ }), range: [24, 96], pan: 0, send: 0.4, gain: 0.4 },
    saxello:  { label: 'Soprano sax', type: 'held', set: m => ({ p: m.ens.saxello }), range: [56, 87], pan: 0.2, send: 0.38, gain: 0.4 },
    tenorsax: { label: 'Tenor sax', type: 'held', set: m => m.proc.tenorsax, range: [44, 76], pan: -0.25, send: 0.36, gain: 0.42 },
    clarinet: { label: 'Clarinet', type: 'held', set: m => m.proc.clarinet, short: m => m.proc.clarinetstac, range: [50, 89], pan: 0.25, send: 0.38, gain: 0.42 },
    flute:    { label: 'Flute', type: 'held', set: m => ({ p: m.ens.flute }), range: [60, 96], pan: 0.35, send: 0.4, gain: 0.32 },
    violin:   { label: 'Violin', type: 'bowed', set: m => m.violin2, range: [55, 96], pan: 0.3, send: 0.4, gain: 0.42 },
    cello:    { label: 'Cello', type: 'bowed', set: m => m.cello, range: [36, 72], pan: -0.15, send: 0.36, gain: 0.5 },
    choir:    { label: 'Choir', type: 'choir', set: m => m.choir, range: [45, 79], pan: 0.05, send: 0.45 },
  };

  class Kit {
    constructor(insts) {
      const A = this.ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: 'playback' });
      this.insts = insts;
      this.out = A.createGain(); this.out.gain.value = 0.8;
      const drive = A.createGain(); drive.gain.value = 1.3;
      const sat = A.createWaveShaper(); sat.curve = this.tanhCurve(1.4); sat.oversample = '2x';
      const trim = A.createGain(); trim.gain.value = 0.8;
      const air = A.createBiquadFilter(); air.type = 'lowpass'; air.frequency.value = 15000;
      const hp = A.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 35;
      const comp = A.createDynamicsCompressor(); comp.threshold.value = -16; comp.ratio.value = 2.5; comp.knee.value = 12; comp.attack.value = 0.015; comp.release.value = 0.3;
      this.out.connect(drive); drive.connect(sat); sat.connect(trim); trim.connect(air); air.connect(hp); hp.connect(comp); comp.connect(A.destination);
      this.rec = A.createMediaStreamDestination(); comp.connect(this.rec);
      this.verb = A.createConvolver(); this.verb.buffer = this.impulse(3.2);
      this.verbIn = A.createGain(); this.verbIn.gain.value = 0.35;
      const pre = A.createDelay(0.1); pre.delayTime.value = 0.02; this.verbIn.connect(pre); pre.connect(this.verb); this.verb.connect(this.out);
      this.bus = {}; this.send = {};
      for (const n of insts) {
        const I = INSTRUMENTS[n], g = A.createGain(); g.gain.value = 0.8;
        const pan = A.createStereoPanner(); pan.pan.value = I.pan; g.connect(pan); pan.connect(this.out);
        const sd = A.createGain(); sd.gain.value = I.send; pan.connect(sd); sd.connect(this.verbIn);
        this.bus[n] = g; this.send[n] = sd;
      }
      this.samples = {}; this.live = 0; this.rr = 0; this.tuning = null; this.loops = {};
      this.loading = { want: insts.slice(), done: [] };
      this.load();
    }
    async load() {
      const A = this.ctx, man = this.man = await (await fetch(BASE + 'manifest.json?v=6')).json();
      const get = async f => A.decodeAudioData(await (await fetch(BASE + f)).arrayBuffer());
      const list = async l => (await Promise.all((l || []).map(async e => { try { return Object.assign({}, e, { buf: await get(e.f) }); } catch (er) { return null; } }))).filter(Boolean);
      const layers = async o => { const r = {}; for (const [k, l] of Object.entries(o || {})) r[k] = await list(l); return r; };
      const done = n => { this.loading.done.push(n); if (this.onload) this.onload(this.loading); };
      await Promise.all(this.insts.map(async n => {
        const I = INSTRUMENTS[n];
        if (I.type === 'piano') {
          const NOTE = { C: 0, Ds: 3, Fs: 6, A: 9 }, names = ['A0']; for (let o = 1; o <= 7; o++) for (const x of ['C', 'Ds', 'Fs', 'A']) names.push(x + o); names.push('C8');
          this.samples.piano = { p: await list(names.map(x => { const m = x.match(/^([A-G]s?)(\d)/); return { f: `piano/${x}.mp3`, m: 12 * (+m[2] + 1) + NOTE[m[1]] }; })) };
        } else if (I.type === 'choir') {
          const C = {}; for (const [sec, vowels] of Object.entries(man.choir)) { C[sec] = {}; for (const vw of ['ah', 'oo']) C[sec][vw] = await list(vowels[vw]); }
          this.samples.choir = C;
        } else {
          this.samples[n] = await layers(I.set(man));
          if (I.short) this.samples[n + ':short'] = await layers(I.short(man));
        }
        done(n);
      }));
    }
    ready(n) { return !!this.samples[n]; }
    nearest(list, m) { let b = list[0]; for (const e of list) if (Math.abs(e.m - m) < Math.abs(b.m - m)) b = e; return b; }
    layer(S, vel) { return S.f && S.f.length && (vel > 0.62 || !S.p || !S.p.length) ? S.f : S.p; }
    loopOf(e, a0, b0) {                                    // a seamless loop found by correlation in the decoded audio
      if (e.loop) return e.loop;
      const buf = e.buf, x = buf.getChannelData(0), sr = buf.sampleRate, W = Math.floor(sr * 0.012), R = Math.floor(sr * 0.025);
      const a = Math.floor(Math.min(a0, buf.duration * 0.3) * sr), bc = Math.floor(Math.min(b0, buf.duration - 0.2) * sr);
      let ea = 0; for (let j = 0; j < W; j += 2) ea += x[a + j] * x[a + j];
      let best = -2, bi = bc;
      for (let b = bc - R; b < bc + R && b + W < x.length; b++) { let s = 0, eb = 0; for (let j = 0; j < W; j += 2) { s += x[a + j] * x[b + j]; eb += x[b + j] * x[b + j]; } const cr = s / Math.sqrt(ea * eb + 1e-12); if (cr > best) { best = cr; bi = b; } }
      return (e.loop = [a / sr, bi / sr]);
    }
    // just intonation (The Harp of New Albion): each pitch class retuned against the tonic, in cents from equal temperament
    detune(m) {
      if (!this.tuning) return 0;
      const JI = [0, 112, 204, 316, 386, 498, 590, 702, 814, 884, 1018, 1088], k = ((m - this.tuning) % 12 + 12) % 12;
      return JI[k] - 100 * k;
    }
    // the time-lag accumulator: two tape loops of different lengths feeding back into themselves on one instrument's bus
    accumulate(n, on, times) {
      const A = this.ctx; if (!this.bus[n]) return;
      if (on && !this.loops[n]) {
        const out = A.createGain(); out.gain.value = 0; out.connect(this.out); const sd = A.createGain(); sd.gain.value = 0.3; out.connect(sd); sd.connect(this.verbIn);
        const nodes = [out, sd];
        (times || [3.1, 4.9]).forEach((T, i) => {
          const d = A.createDelay(8); d.delayTime.value = T; const fb = A.createGain(); fb.gain.value = 0.62; const lp = A.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 5200 - 900 * i;
          const p = A.createStereoPanner(); p.pan.value = i ? 0.55 : -0.55;
          this.bus[n].connect(d); d.connect(lp); lp.connect(fb); fb.connect(d); lp.connect(p); p.connect(out); nodes.push(d, fb, lp, p);
        });
        out.gain.setTargetAtTime(0.8, A.currentTime, 0.5); this.loops[n] = nodes;
      } else if (!on && this.loops[n]) {
        const nodes = this.loops[n]; delete this.loops[n];
        nodes[0].gain.setTargetAtTime(0, A.currentTime, 1.2); setTimeout(() => nodes.forEach(x => { try { x.disconnect(); } catch (e) {} }), 9000);
      }
    }
    play(inst, m, dur, vel, t, pan, shape) {
      const swell = (g, amp, t0, L) => { g.gain.cancelScheduledValues(t0); g.gain.setValueAtTime(0.0001, t0); g.gain.linearRampToValueAtTime(amp, t0 + L * 0.5); g.gain.linearRampToValueAtTime(0.0001, t0 + L); };
      const I = INSTRUMENTS[inst], S = this.samples[inst]; if (!I || !S || this.live > 140) return;
      const A = this.ctx, dest = this.bus[inst], nodes = [];
      let out = dest;
      if (pan !== undefined && pan !== null) { const p = A.createStereoPanner(); p.pan.value = Math.max(-1, Math.min(1, pan)); p.connect(dest); out = p; nodes.push(p); }
      if (I.type === 'clap') {
        const list = S.p, e = list[this.rr++ % list.length], src = A.createBufferSource(), g = A.createGain();
        src.buffer = e.buf; src.playbackRate.value = 0.97 + 0.06 * ((this.rr * 7919) % 100) / 100; g.gain.value = 0.6 * (0.35 + 0.65 * vel);
        src.connect(g); g.connect(out); src.start(t); nodes.push(src, g); return this.done(nodes, src);
      }
      if (I.type === 'choir') {
        const sec = m >= 64 ? 'S' : m >= 57 ? 'A' : m >= 48 ? 'T' : 'B', vw = dur > 1.2 ? 'ah' : 'oo';
        const e = this.nearest(S[sec][vw], m), src = A.createBufferSource(); src.buffer = e.buf; src.playbackRate.value = Math.pow(2, (m - e.m) / 12);
        src.detune.value = this.detune(m);
        const L = Math.max(0.25, dur), len = e.buf.duration / src.playbackRate.value;
        if (L + 0.4 > len - 0.8) { const [a, b] = this.loopOf(e, 1.4, Math.min(4.6, e.buf.duration - 1)); src.loop = true; src.loopStart = a; src.loopEnd = b; }
        const g = A.createGain(), amp = 0.45 * (0.35 + 0.65 * vel); g.gain.setValueAtTime(amp, t); g.gain.setTargetAtTime(0, t + L, 0.3); if (shape === 'swell') swell(g, amp, t, L);
        src.connect(g); g.connect(out); src.start(t); src.stop(t + L + 1.6); nodes.push(src, g); return this.done(nodes, src);
      }
      if (I.type === 'bowed') return this.bowed(S, inst, m, dur, vel, t, out, nodes, shape === 'swell' && swell);
      const shortSet = this.samples[inst + ':short'];
      const set = I.type === 'piano' ? S.p : (shortSet && dur < 0.3 ? this.layer(shortSet, vel) : this.layer(S, vel));
      if (!set || !set.length) return;
      const e = this.nearest(set, m), src = A.createBufferSource();
      src.buffer = e.buf; src.playbackRate.value = Math.pow(2, (m - e.m) / 12); src.detune.value = this.detune(m);
      const lp = A.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 2200 + 11000 * vel * vel; lp.Q.value = 0.3;
      const g = A.createGain(), len = e.buf.duration / src.playbackRate.value;
      let stop;
      if (I.type === 'piano') {
        const amp = 0.5 * (0.12 + 0.88 * Math.pow(vel, 1.4)), hold = Math.min(len, Math.max(this.pedal ? 4 : 1.2, dur * 2));
        g.gain.setValueAtTime(amp, t); g.gain.setTargetAtTime(0, t + hold, this.pedal ? 0.6 : 0.18); stop = t + Math.min(len, hold + 2);
      } else if (I.type === 'mallet') {
        const amp = 0.55 * (0.25 + 0.75 * vel); g.gain.setValueAtTime(amp, t);
        const hold = Math.max(dur * 1.3, 0.25); if (hold < I.ring) g.gain.setTargetAtTime(0, t + hold, I.ring * 0.25);   // the player damps it
        stop = t + Math.min(len, hold + I.ring);
      } else {                                              // held: organ, saxes, clarinet, flute
        const L = Math.max(0.1, dur);
        if (L + 0.4 > len - 0.4) { const [a, b] = this.loopOf(e, 1.0, Math.min(4.2, e.buf.duration - 0.5)); src.loop = true; src.loopStart = a; src.loopEnd = b; }
        const amp = (I.gain || 0.4) * (0.35 + 0.65 * vel);
        g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(amp, t + 0.015); g.gain.setValueAtTime(amp, t + L); g.gain.setTargetAtTime(0, t + L, 0.09);
        if (shape === 'swell') swell(g, amp, t, L);
        stop = t + L + 0.7;
      }
      src.connect(lp); lp.connect(g); g.connect(out); src.start(t); src.stop(stop); nodes.push(src, lp, g);
      this.done(nodes, src);
    }
    bowed(S, inst, m, dur, vel, t, out, nodes, swell) {
      const A = this.ctx, I = INSTRUMENTS[inst], L = Math.max(0.12, dur), short = L < 0.36;
      const [lo, hi, w] = vel < 0.5 ? ['pp', 'mf', vel / 0.5] : ['mf', 'ff', (vel - 0.5) / 0.5];
      const g = A.createGain(), amp = I.gain * (0.45 + 0.55 * vel); g.connect(out); nodes.push(g);
      g.gain.setValueAtTime(amp, t); g.gain.setValueAtTime(amp, t + L); g.gain.setTargetAtTime(0, t + L, short ? 0.05 : 0.13);
      if (swell) swell(g, amp, t, L);
      let vib = null;
      if (!short) {                                        // a player's vibrato: after the bow, growing, never quite regular
        const o = A.createOscillator(); o.frequency.value = 5.1 + Math.random() * 0.9;
        const d = A.createGain(); d.gain.setValueAtTime(0, t + 0.22); d.gain.linearRampToValueAtTime(11 + 7 * vel, t + 0.9);
        o.connect(d); o.start(t); o.stop(t + L + 1); nodes.push(o, d); vib = d;
      }
      let last = null;
      for (const [layer, wt] of [[lo, 1 - w], [hi, w]]) {
        if (wt < 0.06 || !S[layer] || !S[layer].length) continue;
        const e = this.nearest(S[layer], m), src = A.createBufferSource(), sg = A.createGain();
        src.buffer = e.buf; src.playbackRate.value = Math.pow(2, (m - e.m) / 12); src.detune.value = this.detune(m); sg.gain.value = Math.sqrt(wt);
        if (vib) vib.connect(src.detune);
        if (L + 0.4 > e.buf.duration / src.playbackRate.value - 0.3) { const [a, b] = this.loopOf(e, 1.0, Math.min(4.5, e.buf.duration - 0.6)); src.loop = true; src.loopStart = a; src.loopEnd = b; }
        src.connect(sg); sg.connect(g); src.start(t); src.stop(t + L + 0.8); nodes.push(src, sg); last = src;
      }
      if (last) this.done(nodes, last);
    }
    done(nodes, last) { this.live++; last.onended = () => { this.live--; for (const n of nodes) { try { n.disconnect(); } catch (e) {} } }; }
    tanhCurve(k) { const n = 2048, c = new Float32Array(n); for (let i = 0; i < n; i++) { const x = i / (n - 1) * 2 - 1; c[i] = Math.tanh(k * x) / Math.tanh(k); } return c; }
    impulse(sec) {
      const A = this.ctx, sr = A.sampleRate, n = Math.floor(sr * sec), b = A.createBuffer(2, n, sr);
      for (let ch = 0; ch < 2; ch++) {
        const d = b.getChannelData(ch); let lp = 0;
        for (let i = 0; i < n; i++) { const t = i / n, k = 0.12 + 0.8 * t; lp = lp * k + (Math.random() * 2 - 1) * (1 - k); d[i] = lp * Math.pow(1 - t, 2.6) * 1.6 * Math.min(1, i / (sr * 0.008)); }
        for (let r = 0; r < 9; r++) { const at = Math.floor(sr * (0.007 + r * 0.011 + (ch ? 0.003 : 0) + Math.random() * 0.006)); if (at < n) d[at] += (Math.random() < 0.5 ? -1 : 1) * 0.5 * Math.pow(0.82, r); }
      }
      return b;
    }
  }

  // ── a standard MIDI file from the note log (seconds → ticks at a fixed 120 BPM, so any tempo changes are exact) ──
  const GM = { piano: 0, marimba: 12, vibes: 11, glock: 9, organ: 19, pipe: 19, saxello: 64, tenorsax: 66, clarinet: 71, flute: 73, violin: 40, cello: 42, choir: 52 };
  function midiFile(log) {
    const insts = [...new Set(log.map(e => e[1]))], tracks = [];
    const vlq = n => { const b = [n & 127]; while ((n >>= 7)) b.unshift((n & 127) | 128); return b; };
    const trk = evs => { evs.sort((a, b) => a[0] - b[0] || a[2] - b[2]); const out = []; let last = 0; for (const [t, bytes] of evs) { out.push(...vlq(Math.max(0, t - last)), ...bytes); last = t; } out.push(0, 0xff, 0x2f, 0); return [0x4d, 0x54, 0x72, 0x6b, ...[24, 16, 8, 0].map(s => (out.length >> s) & 255), ...out]; };
    tracks.push(trk([[0, [0xff, 0x51, 3, 0x07, 0xa1, 0x20]]]));
    insts.forEach((n, i) => {
      const ch = n === 'claps' ? 9 : i % 9 + (i >= 9 ? 1 : 0), evs = [[0, [0xc0 | ch, GM[n] || 0]]];
      for (const [t, inst, m, d, v] of log) if (inst === n) {
        const key = n === 'claps' ? 39 : Math.max(0, Math.min(127, Math.round(m))), a = Math.round(t * 960), b = Math.round((t + Math.max(0.05, d)) * 960), vel = Math.max(1, Math.min(127, Math.round(v * 127)));
        evs.push([a, [0x90 | ch, key, vel]]); evs.push([b, [0x80 | ch, key, 0]]);
      }
      tracks.push(trk(evs));
    });
    const head = [0x4d, 0x54, 0x68, 0x64, 0, 0, 0, 6, 0, 1, 0, tracks.length, 0x01, 0xe0];
    return new Uint8Array([...head, ...tracks.flat()]);
  }

  // ── the page: transport, controls, chips, mixer, picture, exports, sessions ──
  function start(cfg) {
    const $ = id => document.getElementById(id);
    const G = cfg.Score, INST = cfg.instruments;
    let settings = Object.assign({ seed: cfg.seed, vol: {} }, JSON.parse(JSON.stringify(cfg.defaults)));
    for (const n of INST) if (settings.vol[n] === undefined) settings.vol[n] = 0.8;
    let score = new G(settings.seed), kit = null, playing = false, timer = null, nextT = 0, start0 = null, log = [], pending = [], replay = null;
    const timeline = [], noteLog = [];
    const applyCtl = () => { for (const k of Object.keys(cfg.defaults)) if (k !== 'vol') score.ctl[k] = clone(settings[k]); };
    const clone = v => v && typeof v === 'object' ? JSON.parse(JSON.stringify(v)) : v;
    applyCtl();

    // controls that change the score apply at the next step and are logged by step; mixer moves apply at once
    function change(key, value) {
      if (key.startsWith('vol.')) { const n = key.slice(4); settings.vol[n] = value; if (kit && kit.bus[n]) kit.bus[n].gain.setTargetAtTime(value, kit.ctx.currentTime, 0.05); return; }
      if (playing) pending.push([key, value]); else apply(key, value);
    }
    function apply(key, value) {
      settings[key] = clone(value); score.ctl[key] = clone(value);
      if (playing || replay) log.push([score.step, key, clone(value)]);
      if (cfg.onControl) cfg.onControl(key, value, kit, settings);
      syncControls();
    }
    function stepSec() { return score.stepSec(); }
    function tick() {
      if (!kit) return;
      const ahead = document.hidden ? 1.6 : 0.35;
      while (nextT < kit.ctx.currentTime + ahead) {
        if (replay && replay.has(score.step)) for (const [k, v] of replay.get(score.step)) apply(k, v);
        else while (pending.length) { const [k, v] = pending.shift(); apply(k, v); }
        const d = stepSec(), r = score.advance();
        if (r.tuning !== undefined) kit.tuning = r.tuning;
        for (const n of r.notes) {
          const [inst, m, len, vel, , off, pan, shape] = n;
          const t = nextT + (off || 0) * d;
          kit.play(inst, m, len * d, vel, t, pan, shape);
          noteLog.push([+(t - start0).toFixed(4), inst, m, +(len * d).toFixed(4), vel]);
        }
        timeline.push({ t: nextT, d, view: r.view, notes: r.notes });
        if (timeline.length > 600) timeline.splice(0, 100);
        nextT += d;
      }
    }
    function play() {
      if (!kit) {
        kit = new Kit(INST); kit.onload = showLoading; showLoading(kit.loading);
        for (const n of INST) kit.bus[n].gain.value = settings.vol[n];
        if (cfg.onControl) for (const k of Object.keys(cfg.defaults)) cfg.onControl(k, settings[k], kit, settings);
      }
      kit.ctx.resume();
      if (start0 === null) { start0 = kit.ctx.currentTime + 0.1; nextT = start0; snapshot0 = JSON.parse(JSON.stringify(settings)); }
      else nextT = Math.max(nextT, kit.ctx.currentTime + 0.05);
      playing = true; $('pr-play').textContent = 'Pause'; timer = setInterval(tick, 50); tick();
    }
    function pause() { playing = false; clearInterval(timer); $('pr-play').textContent = 'Play'; }
    let snapshot0 = null;
    function restart(keepReplay) {
      const was = playing; pause();
      score = new G(settings.seed); applyCtl();
      log = []; pending = []; timeline.length = 0; noteLog.length = 0; start0 = null;
      if (!keepReplay) { replay = null; $('pr-replay').hidden = true; }
      if (was) play();
    }
    function showLoading(L) {
      const wait = L.want.filter(k => !L.done.includes(k)).map(k => INSTRUMENTS[k].label.toLowerCase());
      $('pr-loadstat').textContent = wait.length ? 'Loading recordings: ' + wait.join(', ') + '…' : '';
    }

    // ── controls built from the score's description ──
    const host = $('pr-controls');
    for (const c of cfg.controls) {
      const row = document.createElement('div'); row.className = 'ag-row';
      const lab = document.createElement('span'); lab.className = 'ag-read'; lab.style.width = '96px'; lab.textContent = c.label; row.appendChild(lab);
      if (c.type === 'seg') {
        const seg = document.createElement('span'); seg.className = 'ag-seg';
        for (const [v, l] of c.options) { const L = document.createElement('label'), i = document.createElement('input'); i.type = 'radio'; i.name = 'pr-' + c.key; i.value = v; L.appendChild(i); L.append(l); i.addEventListener('change', () => i.checked && change(c.key, c.num ? +v : v)); seg.appendChild(L); }
        row.appendChild(seg);
      } else if (c.type === 'range') {
        const i = document.createElement('input'); i.type = 'range'; i.min = c.min; i.max = c.max; i.step = c.step || 1; i.id = 'pr-' + c.key;
        const o = document.createElement('output'); o.className = 'ag-read'; o.id = 'pr-' + c.key + '-out';
        i.addEventListener('input', () => { o.textContent = (c.fmt || (x => x))(+i.value); }); i.addEventListener('change', () => change(c.key, +i.value));
        row.appendChild(i); row.appendChild(o);
      } else if (c.type === 'check') {
        const L = document.createElement('label'), i = document.createElement('input'); i.type = 'checkbox'; i.id = 'pr-' + c.key; L.appendChild(i); L.append(c.text || ''); i.addEventListener('change', () => change(c.key, i.checked)); row.appendChild(L);
      }
      if (c.hint) { const h = document.createElement('p'); h.className = 'ag-read pr-hint'; h.style.flexBasis = '100%'; h.style.margin = '0 0 0 106px'; h.style.fontSize = '12px'; h.style.opacity = '.75'; h.textContent = c.hint; row.appendChild(h); }
      host.appendChild(row);
    }
    // instrument chips: the score assigns its players to whichever are chosen
    const chips = $('pr-chips');
    for (const n of INST) { const L = document.createElement('label'), i = document.createElement('input'); L.className = 'ag-chip'; i.type = 'checkbox'; i.dataset.inst = n; L.appendChild(i); L.append(INSTRUMENTS[n].label); chips.appendChild(L);
      i.addEventListener('change', () => { let on = INST.filter(x => x === n ? i.checked : settings.ens.includes(x)); if (!on.length) { i.checked = true; return; } change('ens', on); }); }
    // mixer
    const mix = $('pr-mixer');
    for (const n of INST) { const s = document.createElement('span'); s.textContent = INSTRUMENTS[n].label; const r = document.createElement('input'); r.type = 'range'; r.min = 0; r.max = 1; r.step = 0.01; r.id = 'pr-vol-' + n; r.addEventListener('input', () => change('vol.' + n, +r.value)); mix.appendChild(s); mix.appendChild(r); }
    function syncControls() {
      for (const c of cfg.controls) {
        if (c.type === 'seg') document.querySelectorAll(`input[name=pr-${c.key}]`).forEach(i => { i.checked = String(settings[c.key]) === i.value; });
        else if (c.type === 'range') { $('pr-' + c.key).value = settings[c.key]; $('pr-' + c.key + '-out').textContent = (c.fmt || (x => x))(settings[c.key]); }
        else if (c.type === 'check') $('pr-' + c.key).checked = !!settings[c.key];
      }
      document.querySelectorAll('#pr-chips input').forEach(i => { i.checked = settings.ens.includes(i.dataset.inst); });
      for (const n of INST) $('pr-vol-' + n).value = settings.vol[n];
      if (cfg.describe) $('pr-note').textContent = cfg.describe(settings);
    }
    syncControls();

    $('pr-play').addEventListener('click', () => playing ? pause() : play());
    $('pr-restart').addEventListener('click', () => { settings.seed = (settings.seed * 1103515245 + 12345) % 2147483647 || 7; $('pr-seed').textContent = settings.seed; restart(); });
    $('pr-seed').textContent = settings.seed;

    // ── picture ──
    const cv = $('pr-canvas'), cx = cv.getContext('2d');
    function frame() {
      const r = cv.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
      if (cv.width !== Math.round(r.width * dpr)) { cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr); }
      const now = kit ? kit.ctx.currentTime : 0;
      let i = timeline.length - 1; while (i > 0 && timeline[i].t > now) i--;
      cfg.draw(cx, cv.width, cv.height, { now, at: timeline[i], timeline, settings, playing, dpr, kit });
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    $('pr-full').addEventListener('click', () => { const st = $('pr-stage'); document.fullscreenElement ? document.exitFullscreen() : (st.requestFullscreen || st.webkitRequestFullscreen).call(st); });

    // ── exports ──
    const save = (blob, name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); };
    let rec = null, parts = [];
    $('pr-rec').addEventListener('click', () => {
      if (!kit) play();
      if (rec) { rec.stop(); return; }
      parts = []; rec = new MediaRecorder(kit.rec.stream); rec.ondataavailable = e => parts.push(e.data);
      rec.onstop = () => { save(new Blob(parts, { type: rec.mimeType }), `${cfg.name}-${settings.seed}.webm`); rec = null; $('pr-rec').textContent = 'Record audio'; $('pr-rec').classList.remove('on'); };
      rec.start(); $('pr-rec').textContent = 'Stop and save'; $('pr-rec').classList.add('on');
    });
    $('pr-midi').addEventListener('click', () => save(new Blob([midiFile(noteLog)], { type: 'audio/midi' }), `${cfg.name}-${settings.seed}.mid`));
    $('pr-save').addEventListener('click', () => save(new Blob([JSON.stringify({ app: cfg.name, version: 1, seed: (snapshot0 || settings).seed, settings: snapshot0 || settings, log }, null, 1)], { type: 'application/json' }), `${cfg.name}-session-${settings.seed}.json`));
    $('pr-load').addEventListener('change', async e => { const f = e.target.files[0]; if (!f) return; loadSession(JSON.parse(await f.text())); e.target.value = ''; });
    function loadSession(s) {
      if (s.app !== cfg.name) { $('pr-replay').hidden = false; $('pr-replay').textContent = 'That session belongs to another piece.'; return; }
      settings = Object.assign(settings, JSON.parse(JSON.stringify(s.settings))); $('pr-seed').textContent = settings.seed;
      replay = new Map(); for (const [st, k, v] of s.log) { if (!replay.has(st)) replay.set(st, []); replay.get(st).push([k, v]); }
      restart(true); syncControls(); if (kit) for (const n of INST) kit.bus[n].gain.value = settings.vol[n];
      $('pr-replay').hidden = false; $('pr-replay').textContent = `Replaying a session: seed ${settings.seed}, ${s.log.length} control changes`;
      play();
    }
    window.ProcPlayer = { get score() { return score; }, get kit() { return kit; }, change, play, pause, restart, noteLog, get log() { return log; }, loadSession, settings: () => settings, INSTRUMENTS };
  }

  window.Proc = { rng, Kit, INSTRUMENTS, midiFile, start };
})();
