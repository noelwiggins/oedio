/* ALGOGENESIS — generative soundscape.
   In the spirit of Brian Eno's Music for Airports: every living kind on a panel is a tape loop of a single note.
   The loops have different lengths and drift in and out of phase, so the harmony never repeats. Nothing is
   composed; everything you hear comes from what the world is doing:
     · each kind (a Coast species, or a lineage on a concept panel) is one loop. Its pitch comes from its genes and
       stays the same for its whole life. Its loudness follows how many there are; its register follows its body.
     · a new variant arrives as a high seed-chime, then joins the loops.
     · a kind that becomes established swells once, like a breath.
     · an extinction is a last falling note into a long echo, and that loop goes silent for good.
     · births, meals, divisions, stars dying make a soft rain of notes; more activity, more rain.
     · as the panel's own measure of progress rises (body complexity, catalysis, memory, metals…) the tones grow
       richer in overtones and a high halo opens above them. You can hear evolution getting somewhere.
     · a milestone rings a chord and moves the whole piece up a fifth into a new key.
     · a drone under it all follows the total population, and darkens at night.
   AlgoSound.init(slug) · feed(liveFrame) · toggle() · start() · stop() · isOn() · level()
   AlgoSound.drawGrille(ctx, x, y, size, u)  · AlgoSound.legend()                                                    */
(function () {
  'use strict';
  const mtof = m => 440 * Math.pow(2, (m - 69) / 12);
  const hash = s => { let h = 2166136261; s = String(s); for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0) / 4294967296; };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  // ── one sound world per panel: its instruments, its tuning, its room, its weather ───────────────────────────
  // voice: the loops (voice2 for the second population); chime: a new variant; rain: [stat, instrument, words, scale]
  // room: [reverb seconds, reverb decay, echo seconds, echo feedback]; bed: the background texture; drone: intervals
  const P = {
    coast:          { gain: 0.8, scale: [0, 2, 4, 7, 9], root: 50, voice: 'marimba', voice2: 'pad', chime: 'glass', bed: 'surf', drone: [0, 7, 12],
                      room: [5, 2.2, 1.63, 0.36], progress: ['complexity_mean', 2, 20],
                      rain: [['births', 'drip', 'births'], ['pollinations', 'glass', 'pollinations', 0.004], ['kills', 'thump', 'kills']],
                      sound: 'wooden marimba and breathing pads over a slow surf',
                      words: 'animals are wooden mallet notes, flowers are slow breathing pads; hunters sit lower and darker' },
    protogenesis:   { gain: 1.0, scale: [0, 2, 4, 6, 8, 10], root: 52, voice: 'harmonica', chime: 'celesta', bed: 'deep', drone: [0, 6, 12],
                      room: [7.5, 2, 0.92, 0.42], progress: ['best_activity', 0, 1],
                      rain: [['copies', 'bubble', 'copies made']],
                      sound: 'glass harmonica in whole tones, bubbles rising through deep water',
                      words: 'each family of self-copying chains is a glass-harmonica tone; every copy made is a rising bubble' },
    autopoiesis:    { gain: 1.08, scale: [0, 3, 7, 10, 14], root: 45, voice: 'choir', chime: 'harmonica', bed: 'pulse', drone: [0, 7, 10],
                      room: [4.5, 2.4, 2.1, 0.3], progress: ['mean_cell_age', 0, 3000],
                      rain: [['divisions', 'kalimba', 'cells dividing'], ['repairs', 'drip', 'membrane repairs', 0.02]],
                      sound: 'a soft wordless choir over a slow heartbeat',
                      words: 'each family of cells is a voice in a choir; divisions are thumb-piano notes, repairs are droplets' },
    epigenesis:     { gain: 1.8, scale: [0, 3, 5, 7, 10], root: 48, voice: 'celesta', voice2: 'harmonica', chime: 'celesta', bed: 'shimmer', drone: [0, 12, 19],
                      room: [3.5, 2.6, 0.75, 0.4], progress: ['mean_types', 1, 10],
                      rain: [['embryos', 'kalimba', 'embryos grown']],
                      sound: 'a music box over a faint shimmer, like a nursery at night',
                      words: 'each lineage of embryos is a music-box note; each embryo grown is a thumb-piano note' },
    noogenesis:     { gain: 1.35, scale: [0, 2, 3, 7, 8], root: 45, voice: 'vibes', chime: 'glass', bed: 'brook', drone: [0, 7, 15],
                      room: [5, 2.2, 1.21, 0.38], progress: ['memory', 0, 1],
                      rain: [['meals', 'drip', 'meals found', 0.05], ['dark_meals', 'glass', 'meals found in the dark']],
                      sound: 'vibraphone over a running brook',
                      words: 'each lineage of foragers is a vibraphone note; meals are droplets, meals found in the dark ring as glass' },
    biogenesis:     { gain: 1.9, scale: [0, 2, 4, 7, 9], root: 43, voice: 'handpan', chime: 'kalimba', bed: 'bubbles', drone: [0, 7, 14],
                      room: [4, 2.3, 1.4, 0.35], progress: ['depth', 0, 2500],
                      rain: [['divisions', 'bubble', 'divisions', 0.05]],
                      sound: 'handpan in a warm pool, with bubbles',
                      words: 'each lineage of cells is a handpan note; every division is a bubble' },
    morphogenesis:  { gain: 0.9, scale: [0, 2, 5, 7, 9], root: 41, voice: 'flute', chime: 'kalimba', bed: 'wind', drone: [0, 5, 12],
                      room: [6, 2, 2.4, 0.33], progress: ['mean_height', 1, 12],
                      rain: [['spores', 'drip', 'spores released', 0.05]],
                      sound: 'breathy wooden flute in a high wind',
                      words: 'each lineage of growing forms is a flute; spores are droplets' },
    cosmogenesis:   { gain: 0.85, scale: [0, 7, 12, 14, 19], root: 36, voice: 'bowl', chime: 'glass', bed: 'space', drone: [0, 7, 19],
                      room: [9, 1.8, 3.1, 0.45], progress: ['metals', 0, 60],
                      rain: [['supernovae', 'boom', 'stars exploding'], ['planets_total', 'glass', 'planets formed']],
                      sound: 'singing bowls in a vast dark hall, with distant booms',
                      words: 'clusters of stars are singing bowls; supernovae are distant booms, new planets are glass' },
    anthropogenesis:{ gain: 1.15, scale: [0, 2, 4, 5, 7, 9, 11], root: 48, voice: 'harp', voice2: 'flute', chime: 'harp', bed: 'hearth', drone: [0, 7, 12],
                      room: [3, 2.6, 0.9, 0.3], progress: ['tools_mean', 0, 300],
                      rain: [['people', 'pluck', 'people born', 0.01]],
                      sound: 'harp and flute beside a hearth',
                      words: 'each people is a harp string; the more tools they have, the richer the tone' },
    psychogenesis:  { gain: 2.6, scale: [0, 1, 5, 7, 8], root: 50, voice: 'rhodes', chime: 'vibes', bed: 'tape', drone: [0, 5, 13],
                      room: [3.5, 2.5, 0.55, 0.45], progress: ['learning', 0, 1],
                      rain: [['changes', 'kalimba', 'minds changed'], ['poisoned', 'thump', 'creatures poisoned']],
                      sound: 'a soft electric piano in a small warm room',
                      words: 'each lineage of minds is an electric-piano note; a mind changed is a thumb-piano note' },
    palingenesis:   { gain: 0.72, scale: [0, 2, 5, 7, 10], root: 43, voice: 'cello', chime: 'flute', bed: 'forest', drone: [0, 7, 10],
                      room: [6, 2.1, 1.9, 0.32], progress: ['cover', 0, 100],
                      rain: [['fires', 'crackle', 'fires']],
                      sound: 'bowed strings in a forest, with birds and the crackle of fire',
                      words: 'each kind of tree is a bowed string; fires crackle, and the birds come back with the trees' },
    anagenesis:     { gain: 2.4, scale: [0, 2, 4, 7, 11], root: 47, voice: 'bamboo', chime: 'kalimba', bed: 'patter', drone: [0, 7, 11],
                      room: [4, 2.4, 1.1, 0.34], progress: ['fitness', 0, 1],
                      rain: [['generations', 'drip', 'generations']],
                      sound: 'hollow bamboo chimes in light rain',
                      words: 'each lineage is a bamboo chime; every generation is a raindrop' },
    ontogeny:       { gain: 1.55, scale: [0, 4, 7, 11, 14], root: 52, voice: 'tubular', chime: 'celesta', bed: 'breath', drone: [0, 4, 12],
                      room: [7, 2, 2.7, 0.38], progress: ['mean_score', 0, 3],
                      rain: [['generation', 'celesta', 'generations']],
                      sound: 'tubular bells and slow breathing',
                      words: 'each lineage of bodies is a tubular bell; each generation is a music-box note' },
  };

  // ── the instruments ──────────────────────────────────────────────────
  // fm: one carrier, one modulator.  add: partials [ratio, level, decay share], each slightly detuned so they beat.
  // sub: filtered sawtooth or triangle with vibrato, optional vowel formants and breath.
  const INST = {
    marimba:  { kind: 'fm', ratio: 4, idx: 0.7, a: 0.035, d: 3.4 },
    bell:     { kind: 'fm', ratio: 3.5, idx: 1.1, a: 0.05, d: 7.5 },
    glass:    { kind: 'fm', ratio: 2.76, idx: 0.55, a: 0.08, d: 5.5 },
    pluck:    { kind: 'fm', ratio: 2, idx: 0.8, a: 0.03, d: 2.2 },
    pad:      { kind: 'fm', ratio: 1, idx: 0.35, a: 4, d: 9, sus: 0.7, hold: 3 },
    reed:     { kind: 'fm', ratio: 1, idx: 0.9, a: 1.4, d: 5, sus: 0.6, hold: 1.8 },
    drip:     { kind: 'fm', ratio: 5.1, idx: 0.3, a: 0.025, d: 0.9 },
    thump:    { kind: 'fm', ratio: 0.5, idx: 0.4, a: 0.05, d: 1.4 },
    boom:     { kind: 'fm', ratio: 0.5, idx: 0.25, a: 0.25, d: 5 },
    bubble:   { kind: 'fm', ratio: 1, idx: 0.15, a: 0.02, d: 0.35, rise: 1.6 },
    kalimba:  { kind: 'add', a: 0.012, d: 2.6, parts: [[1, 1, 1], [5.95, 0.16, 0.15], [8.7, 0.05, 0.1]] },
    celesta:  { kind: 'add', a: 0.01, d: 2.8, oct: 1, parts: [[1, 1, 1], [2, 0.3, 0.6], [3, 0.12, 0.4], [4.02, 0.08, 0.3]] },
    harmonica:{ kind: 'add', a: 0.9, d: 5, sus: 0.75, hold: 1.6, trem: [5.5, 0.12], parts: [[1, 1, 1], [2, 0.32, 1], [3, 0.12, 1]] },
    bowl:     { kind: 'add', a: 0.6, d: 13, beat: 0.9, parts: [[1, 1, 1], [2.71, 0.45, 0.9], [5.15, 0.2, 0.7], [8.45, 0.08, 0.5]] },
    tubular:  { kind: 'add', a: 0.015, d: 9, parts: [[1, 0.8, 1], [2.76, 0.5, 0.75], [5.4, 0.28, 0.5], [8.93, 0.1, 0.3]] },
    bamboo:   { kind: 'add', a: 0.008, d: 1.5, oct: 1, parts: [[1, 1, 1], [2.32, 0.4, 0.45], [3.95, 0.15, 0.3]] },
    handpan:  { kind: 'add', a: 0.02, d: 4.8, sag: 0.985, parts: [[1, 1, 1], [2, 0.42, 0.7], [3, 0.12, 0.45]] },
    harp:     { kind: 'add', a: 0.008, d: 3.6, parts: [[1, 1, 1], [2, 0.45, 0.6], [3, 0.25, 0.4], [4, 0.12, 0.3], [5, 0.06, 0.22]] },
    vibes:    { kind: 'add', a: 0.02, d: 5.5, trem: [4.2, 0.35], parts: [[1, 1, 1], [4, 0.22, 0.3], [10, 0.03, 0.08]] },
    rhodes:   { kind: 'add', a: 0.015, d: 4.5, trem: [2.2, 0.15], parts: [[1, 1, 1], [2, 0.22, 0.5], [3, 0.06, 0.3], [14, 0.025, 0.04]] },
    flute:    { kind: 'sub', wave: 'triangle', cut: 4, a: 0.7, d: 3.5, sus: 0.7, hold: 1.8, vib: [5, 9], breath: 0.25 },
    cello:    { kind: 'sub', wave: 'sawtooth', cut: 3.2, a: 1.4, d: 4.5, sus: 0.75, hold: 2.6, vib: [5.4, 12] },
    choir:    { kind: 'sub', wave: 'sawtooth', cut: 9, a: 2.4, d: 6, sus: 0.8, hold: 3.2, vib: [4.6, 10], formants: [700, 1150, 2500], detune: 7 },
  };

  // ── the listener's own settings (this device only; they never touch the world) ───────────────────
  const MIX_DEFAULT = { volume: 0.5, pace: 0, tone: 0, space: 0, rain: 0, drone: 0 };
  let MIX = Object.assign({}, MIX_DEFAULT);
  try { Object.assign(MIX, JSON.parse(localStorage.getItem('algo-sound-mix') || '{}')); } catch (e) {}
  let sleepEnd = 0, sleepMin = 0, sleepT = null;
  const volGain = () => 3.2 * MIX.volume * MIX.volume * sleepFade() * (pal.gain || 1);   // panels levelled to one loudness
  const droneMul = () => MIX.drone <= -0.95 ? 0 : Math.pow(2, MIX.drone * 2);
  const voicesAudible = () => Math.round(clamp(10 + 4 * MIX.pace, 4, 14));
  const rainBudget = () => MIX.rain <= -0.95 ? 0 : Math.max(0, Math.round(3 * Math.pow(2, MIX.rain * 1.3)));
  function sleepFade() {              // the last five minutes of a sleep timer fade slowly to nothing
    if (!sleepEnd) return 1;
    return clamp((sleepEnd - Date.now()) / 300000, 0, 1);
  }
  function applyMix() {
    try { localStorage.setItem('algo-sound-mix', JSON.stringify(MIX)); } catch (e) {}
    if (!A) return;
    const t = A.currentTime;
    if (on) out.gain.setTargetAtTime(volGain(), t, 0.4);
    warm.frequency.setTargetAtTime(2800 * Math.pow(2, MIX.tone * 1.6), t, 0.3);
    wet.gain.setTargetAtTime(0.85 * Math.pow(2, MIX.space * 1.3), t, 0.4);
    dry.gain.setTargetAtTime(0.55 * Math.pow(2, -MIX.space * 0.7), t, 0.4);
    echo.gain.setTargetAtTime(Math.pow(2, MIX.space * 1.2), t, 0.4);
  }
  function setSleep(min) {
    sleepMin = min; sleepEnd = min ? Date.now() + min * 60000 : 0;
    clearInterval(sleepT);
    if (min) sleepT = setInterval(() => {
      if (!on) return;
      if (Date.now() >= sleepEnd) { stop(); setSleep(0); syncMixer(); return; }
      out.gain.setTargetAtTime(volGain(), A.currentTime, 2);
      syncMixer();
    }, 5000);
    if (A && on) out.gain.setTargetAtTime(volGain(), A.currentTime, 1);
  }

  // ── the audio graph ──────────────────────────────────────────────────
  let A = null, out, dry, verb, echo, warm, wet, drone = null, analyser, buf, slug = 'coast', pal = P.coast, on = false;
  let live = 0, noiseBuf = null, lastRainT = 0, voices = new Map(), heard = new Map(), prevStats = null, lastEventTick = null, keyShift = 0, rich = 0.3, light = 1, tickT = null, firstFrame = true, lastLvl = 0;

  const TRIM = 0.45;
  function impulse(sec, decay) {
    const n = Math.floor(A.sampleRate * sec), b = A.createBuffer(2, n, A.sampleRate);
    // a room, not a hiss: the noise is filtered ever darker as it decays, and fades in over 20 ms
    for (let c = 0; c < 2; c++) {
      const d = b.getChannelData(c); let y = 0;
      for (let i = 0; i < n; i++) {
        const f = i / n, cut = 0.5 * Math.pow(1 - f, 3) + 0.015;      // one-pole coefficient: bright early, dark late
        y += cut * ((Math.random() * 2 - 1) - y);
        d[i] = y * Math.pow(1 - f, decay) * Math.min(1, i / (A.sampleRate * 0.02)) * 0.9;
      }
    }
    return b;
  }
  function build() {
    const AC = window.AudioContext || window.webkitAudioContext;
    try { A = new AC({ latencyHint: 'playback' }); } catch (e) { A = new AC(); }   // big buffers: no underrun crackle
    out = A.createGain(); out.gain.value = 0;
    const comp = A.createDynamicsCompressor(); comp.threshold.value = -20; comp.knee.value = 12; comp.ratio.value = 3; comp.attack.value = 0.01; comp.release.value = 0.5;
    // small speakers cannot move deep bass cleanly and rattle like static: keep the sound above ~90 Hz
    const hp1 = A.createBiquadFilter(), hp2 = A.createBiquadFilter(), shelf = A.createBiquadFilter();
    hp1.type = hp2.type = 'highpass'; hp1.frequency.value = hp2.frequency.value = 85; hp1.Q.value = hp2.Q.value = 0.6;
    shelf.type = 'lowshelf'; shelf.frequency.value = 220; shelf.gain.value = -6;
    const trim = A.createGain(); trim.gain.value = TRIM;      // the compressors add make-up gain; take it back
    const lim = A.createDynamicsCompressor(); lim.threshold.value = -1; lim.knee.value = 0; lim.ratio.value = 20; lim.attack.value = 0.002; lim.release.value = 0.15;
    analyser = A.createAnalyser(); analyser.fftSize = 512; buf = new Float32Array(analyser.fftSize);
    warm = A.createBiquadFilter(); warm.type = 'lowpass'; warm.Q.value = 0.5;
    out.connect(hp1); hp1.connect(hp2); hp2.connect(shelf); shelf.connect(warm); warm.connect(comp); comp.connect(trim); trim.connect(lim); lim.connect(analyser); analyser.connect(A.destination);
    dry = A.createGain(); dry.gain.value = 0.55; dry.connect(out);
    // a long hall
    verb = A.createGain(); verb.gain.value = 1;
    getNoise();
    const conv = A.createConvolver(); conv.buffer = impulse(pal.room[0], pal.room[1]); wet = A.createGain(); wet.gain.value = 0.85;
    verb.connect(conv); conv.connect(wet); wet.connect(out);
    // a slow tape echo, darkening on each repeat
    echo = A.createGain(); echo.gain.value = 1;
    const dl = A.createDelay(4); dl.delayTime.value = pal.room[2]; const fb = A.createGain(); fb.gain.value = pal.room[3];
    const lp = A.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 1900;
    echo.connect(dl); dl.connect(lp); lp.connect(fb); fb.connect(dl); lp.connect(verb); const ew = A.createGain(); ew.gain.value = 0.35; lp.connect(ew); ew.connect(out);
    // the drone: root and fifth, slowly beating, through a filter that opens by day
    const dg = A.createGain(); dg.gain.value = 0; const df = A.createBiquadFilter(); df.type = 'lowpass'; df.frequency.value = 400; df.Q.value = 0.7;
    const oscs = pal.drone.map((iv, i) => { const o = A.createOscillator(); o.type = i === 1 ? 'triangle' : 'sine'; o.detune.value = (i - 1) * 4; const g = A.createGain(); g.gain.value = i === 2 ? 0.25 : 0.5; o.connect(g); g.connect(df); o.start(); return { o, iv }; });
    const lfo = A.createOscillator(); lfo.frequency.value = 0.031; const lg = A.createGain(); lg.gain.value = 160; lfo.connect(lg); lg.connect(df.frequency); lfo.start();
    df.connect(dg); dg.connect(dry); dg.connect(verb);
    // the halo: a high shimmer that opens as the panel's measure of progress rises
    const hg = A.createGain(); hg.gain.value = 0; const hf = A.createBiquadFilter(); hf.type = 'bandpass'; hf.Q.value = 6;
    const halo = [24, 31, 36].map((iv, i) => { const o = A.createOscillator(); o.type = 'sine'; o.detune.value = (i - 1) * 7; const g = A.createGain(); g.gain.value = 0.3; o.connect(g); g.connect(hf); o.start(); return { o, iv }; });
    const hl = A.createOscillator(); hl.frequency.value = 0.07; const hlg = A.createGain(); hlg.gain.value = 0.5; hl.connect(hlg); hl.start();
    hf.connect(hg); hg.connect(verb);
    drone = { dg, df, oscs, hg, hf, halo };
    startBed();
    retune(0);
  }
  function root() { return pal.root + keyShift; }
  const lift = m => { while (m < 43) m += 12; return m; };        // nothing below G2 (98 Hz)
  function retune(glide) {
    if (!drone) return;
    const t = A.currentTime, r = lift(root() - 12);
    for (const { o, iv } of drone.oscs) o.frequency.setTargetAtTime(mtof(r + iv), t, glide || 0.01);
    for (const { o, iv } of drone.halo) o.frequency.setTargetAtTime(mtof(root() + iv), t, glide || 0.01);
    drone.hf.frequency.setTargetAtTime(mtof(root() + 31), t, glide || 0.01);
  }

  // ── notes ────────────────────────────────────────────────────────────
  // FM voice: one carrier, one modulator; richness opens the modulation index (more overtones)
  function envelope(env, t, gain, T, opt) {
    env.gain.setValueAtTime(0.0001, t);
    env.gain.exponentialRampToValueAtTime(gain, t + T.a);
    if (T.sus) {
      const h = (T.hold || 1) * (opt.hold || 1);
      env.gain.setTargetAtTime(gain * T.sus, t + T.a, 0.8); env.gain.setTargetAtTime(0.0001, t + T.a + h, T.d / 5);
      env.gain.setValueAtTime(0, t + T.a + h + T.d * 1.6); return t + T.a + h + T.d * 1.65;
    }
    env.gain.exponentialRampToValueAtTime(0.0001, t + T.a + T.d); env.gain.setValueAtTime(0, t + T.a + T.d + 0.05);
    return t + T.a + T.d + 0.1;
  }
  function route(node, opt, srcs, end) {
    let out_ = node;
    if (A.createStereoPanner) { const pan = A.createStereoPanner(); pan.pan.value = opt.pan || 0; node.connect(pan); out_ = pan; }
    out_.connect(dry); const s = A.createGain(); s.gain.value = opt.wet != null ? opt.wet : 0.7; out_.connect(s); s.connect(verb);
    if (opt.echo) { const e = A.createGain(); e.gain.value = opt.echo; out_.connect(e); e.connect(echo); }
    live++; srcs[0].onended = () => { live--; try { out_.disconnect(); node.disconnect(); } catch (e) {} };
    for (const o of srcs) { o.start(srcs.t0); o.stop(end); }
  }
  function note(t, freq, gain, timbre, opt = {}) {
    if (!A || gain <= 0.0005 || live >= 32) return;          // a polyphony ceiling keeps the audio thread relaxed
    const T = INST[timbre] || INST.pluck, r = opt.rich != null ? opt.rich : rich, bright = Math.pow(2, MIX.tone);
    if (T.oct) freq *= Math.pow(2, T.oct);
    while (freq > 2400) freq /= 2;                             // keep everything soft: nothing shrill
    const env = A.createGain(), srcs = []; srcs.t0 = t;
    const end = envelope(env, t, gain, T, opt), span = end - t;
    if (T.kind === 'fm') {
      const c = A.createOscillator(), m = A.createOscillator(), mg = A.createGain(), ratio = opt.ratio || T.ratio;
      c.frequency.setValueAtTime(freq, t); m.frequency.setValueAtTime(freq * ratio, t);
      const g = opt.glide || T.rise;
      if (g) { c.frequency.exponentialRampToValueAtTime(freq * g, t + T.a + T.d); m.frequency.exponentialRampToValueAtTime(freq * g * ratio, t + T.a + T.d); }
      const I = freq * T.idx * (0.12 + 0.9 * r) * (opt.dark ? 0.45 : 1) * bright;
      mg.gain.setValueAtTime(I, t); mg.gain.exponentialRampToValueAtTime(Math.max(1, I * 0.15), t + T.a + T.d);
      m.connect(mg); mg.connect(c.frequency); c.connect(env); srcs.push(c, m);
    } else if (T.kind === 'add') {
      // partials: progress lets the upper ones speak; the tone knob too
      const keep = clamp(0.35 + 0.9 * r, 0.3, 1.25) * bright * (opt.dark ? 0.6 : 1);
      T.parts.forEach(([ratio, lvl, dec], i) => {
        const f = freq * ratio; if (f > 7000) return;
        const o = A.createOscillator(), g = A.createGain();
        o.frequency.setValueAtTime(f, t);
        if (T.beat) o.detune.value = (i % 2 ? 1 : -1) * T.beat * 3;
        if (T.sag) o.frequency.exponentialRampToValueAtTime(f * T.sag, t + 0.25);
        if (opt.glide) o.frequency.exponentialRampToValueAtTime(f * opt.glide, end);
        const L = (i === 0 ? lvl : lvl * keep) / Math.sqrt(T.parts.length);
        g.gain.setValueAtTime(L, t);
        if (dec < 1) g.gain.setTargetAtTime(0, t + T.a, Math.max(0.05, (T.d * dec) / 3));
        o.connect(g); g.connect(env); srcs.push(o);
      });
      if (T.beat) {                                   // a bowl's slow beating: a second fundamental, a breath apart
        const o = A.createOscillator(), g = A.createGain(); o.frequency.value = freq + T.beat; g.gain.value = 0.5;
        o.connect(g); g.connect(env); srcs.push(o);
      }
    } else {                                          // sub: bowed, blown or sung
      const lp = A.createBiquadFilter(); lp.type = 'lowpass'; lp.Q.value = 0.6;
      lp.frequency.setValueAtTime(freq * 1.5, t); lp.frequency.linearRampToValueAtTime(Math.min(5000, freq * T.cut * (0.6 + 0.6 * r) * bright), t + T.a);
      const vib = A.createOscillator(), vg = A.createGain(); vib.frequency.value = T.vib[0]; vg.gain.setValueAtTime(0, t);
      vg.gain.linearRampToValueAtTime(T.vib[1], t + T.a + 0.6); vib.connect(vg); srcs.push(vib);
      const n = T.detune ? 2 : 1;
      for (let i = 0; i < n; i++) {
        const o = A.createOscillator(); o.type = T.wave; o.frequency.setValueAtTime(freq, t);
        if (opt.glide) o.frequency.exponentialRampToValueAtTime(freq * opt.glide, end);
        o.detune.value = n > 1 ? (i ? T.detune : -T.detune) : 0; vg.connect(o.detune);
        const g = A.createGain(); g.gain.value = (T.wave === 'sawtooth' ? 0.45 : 0.9) / n; o.connect(g); g.connect(lp); srcs.push(o);
      }
      if (T.formants) {                               // a vowel: "ah"
        const sum = A.createGain(); sum.gain.value = 2.2;
        T.formants.forEach((F, i) => { const b = A.createBiquadFilter(); b.type = 'bandpass'; b.frequency.value = F; b.Q.value = 6; const g = A.createGain(); g.gain.value = [1, 0.5, 0.2][i]; lp.connect(b); b.connect(g); g.connect(sum); });
        sum.connect(env);
      } else lp.connect(env);
      if (T.breath && noiseBuf) {                     // air over the embouchure
        const ns = A.createBufferSource(); ns.buffer = noiseBuf; ns.loop = true;
        const bp = A.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = Math.min(3000, freq * 2); bp.Q.value = 3;
        const g = A.createGain(); g.gain.value = T.breath * 0.25; ns.connect(bp); bp.connect(g); g.connect(env); srcs.push(ns);
      }
    }
    if (T.trem) {                                     // vibraphone fan, electric-piano tremolo
      const tr = A.createOscillator(), tg = A.createGain(), out2 = A.createGain();
      tr.frequency.value = T.trem[0]; tg.gain.value = T.trem[1] * 0.5; out2.gain.value = 1 - T.trem[1] * 0.5;
      tr.connect(tg); tg.connect(out2.gain); env.connect(out2); srcs.push(tr);
      return route(out2, opt, srcs, end);
    }
    route(env, opt, srcs, end);
  }
  function getNoise() {                 // one buffer of noise, made once
    if (!noiseBuf) {
      const n = A.sampleRate * 4; noiseBuf = A.createBuffer(1, n, A.sampleRate); const d = noiseBuf.getChannelData(0);
      for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    }
    return noiseBuf;
  }

  // ── the weather of each panel: a quiet bed under the music ────────────
  let bedG = null, bedNext = 0, bedAux = 0;
  function loopNoise(type, f, q) {
    const s = A.createBufferSource(); s.buffer = getNoise(); s.loop = true; s.start(A.currentTime, Math.random() * 3);
    const b = A.createBiquadFilter(); b.type = type; b.frequency.value = f; b.Q.value = q; s.connect(b); return b;
  }
  function lfo(rate, depth, target, base) {
    const o = A.createOscillator(), g = A.createGain(); o.frequency.value = rate; g.gain.value = depth; o.connect(g); g.connect(target);
    if (base != null) target.value = base; o.start(); return o;
  }
  function swell(src, rate, lvl) {                 // a gain that rises and falls slowly, like a wave or a breath
    const g = A.createGain(); g.gain.value = lvl * 0.55; lfo(rate, lvl * 0.45, g.gain); src.connect(g); g.connect(bedG); return g;
  }
  function startBed() {
    bedG = A.createGain(); bedG.gain.value = 0; const bw = A.createGain(); bw.gain.value = 0.6;
    bedG.connect(dry); bedG.connect(bw); bw.connect(verb);
    const t = pal.bed;
    if (t === 'surf') { swell(loopNoise('lowpass', 520, 0.5), 0.085, 0.5); swell(loopNoise('lowpass', 900, 0.4), 0.061, 0.22); }
    else if (t === 'deep') { swell(loopNoise('bandpass', 240, 1.8), 0.045, 0.9); }
    else if (t === 'wind') { const b = loopNoise('bandpass', 600, 1.6); lfo(0.037, 260, b.frequency); swell(b, 0.07, 0.75); }
    else if (t === 'forest') { const b = loopNoise('bandpass', 520, 1.4); lfo(0.029, 180, b.frequency); swell(b, 0.05, 0.4); }
    else if (t === 'brook') { const b = loopNoise('bandpass', 760, 1.3); const g = swell(b, 0.13, 0.55); lfo(3.3, 0.08, g.gain); lfo(1.7, 0.06, g.gain); }
    else if (t === 'breath') { swell(loopNoise('bandpass', 560, 1.1), 0.14, 0.7); }
    else if (t === 'hearth') { swell(loopNoise('lowpass', 380, 0.6), 0.03, 0.45); }
    else if (t === 'tape') { swell(loopNoise('lowpass', 300, 0.5), 0.02, 0.35); }
    else if (t === 'space' || t === 'shimmer') {
      const ivs = t === 'space' ? [31, 38, 43] : [36, 40, 43, 47];
      for (const [i, iv] of ivs.entries()) {
        const o = A.createOscillator(); o.frequency.value = mtof(Math.min(84, pal.root + iv)); o.detune.value = (i - 1) * 5; o.start();
        const g = A.createGain(); g.gain.value = 0; lfo(0.03 + i * 0.017, 0.012, g.gain, 0.012); o.connect(g); g.connect(bedG);
      }
      if (t === 'space') swell(loopNoise('lowpass', 260, 0.5), 0.02, 0.35);
    }
  }
  function bedEvents(t) {                          // the beds that are made of small events
    if (!bedG || t < bedNext) return;
    const b = pal.bed, q = clamp(droneMul(), 0, 3), quiet = 0.45 + 0.55 * light;
    if (!q) { bedNext = t + 2; return; }
    if (b === 'pulse') {                           // a resting heartbeat: lub-dub
      const f = mtof(lift(pal.root - 12));
      note(t + 0.05, f, 0.03 * q, 'thump', { wet: 0.5, rich: 0 }); note(t + 0.33, f * 0.94, 0.018 * q, 'thump', { wet: 0.5, rich: 0 });
      bedNext = t + 1.6 + Math.random() * 0.5 + (1 - light) * 0.6;
    } else if (b === 'bubbles') {
      note(t + 0.05, mtof(pal.root + 24 + Math.floor(Math.random() * 12)), 0.008 * q * quiet, 'bubble', { pan: (Math.random() - 0.5) * 1.6, wet: 0.9 });
      bedNext = t + 0.6 + Math.random() * 3.5;
    } else if (b === 'forest') {                   // a bird, now and then, by day
      if (light > 0.3 && Math.random() < 0.8) {
        const f0 = 1600 + Math.random() * 1400, n = 2 + Math.floor(Math.random() * 4), pan = (Math.random() - 0.5) * 1.8;
        for (let i = 0; i < n; i++) chirp(t + 0.1 + i * (0.16 + Math.random() * 0.1), f0 * (1 + (Math.random() - 0.5) * 0.15), 0.006 * q, pan);
      }
      bedNext = t + 5 + Math.random() * 14;
    } else if (b === 'hearth') {
      noise(t + 0.05, 0.12 + Math.random() * 0.2, 0.012 * q, 700 + Math.random() * 900, 1.6);
      bedNext = t + 0.4 + Math.random() * 2.8;
    } else if (b === 'patter') {                   // light rain on leaves
      noise(t + 0.02, 0.06 + Math.random() * 0.05, 0.006 * q * quiet, 1300 + Math.random() * 1500, 2.5);
      bedNext = t + 0.08 + Math.random() * 0.45;
    } else bedNext = t + 5;
  }
  function chirp(t, f, gain, pan) {
    if (live >= 32) return;
    const o = A.createOscillator(), g = A.createGain(); o.frequency.setValueAtTime(f, t);
    o.frequency.exponentialRampToValueAtTime(f * (1.25 + Math.random() * 0.3), t + 0.07); o.frequency.exponentialRampToValueAtTime(f * 0.9, t + 0.14);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + 0.02); g.gain.linearRampToValueAtTime(0, t + 0.15);
    o.connect(g); route(g, { pan, wet: 1.1 }, Object.assign([o], { t0: t }), t + 0.2);
  }
  function noise(t, dur, gain, freq, q) {
    if (live >= 32) return;
    getNoise();
    const s = A.createBufferSource(); s.buffer = noiseBuf; const f = A.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = freq; f.Q.value = q || 1;
    const g = A.createGain(); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + 0.04); g.gain.setTargetAtTime(0, t + 0.06, dur / 4);
    s.connect(f); f.connect(g); g.connect(dry); const w = A.createGain(); w.gain.value = 0.9; g.connect(w); w.connect(verb);
    live++; s.onended = () => { live--; try { g.disconnect(); } catch (e) {} };
    s.start(t, Math.random() * 0.5); s.stop(t + dur + 0.3);
  }
  function boom(t, gain) {
    note(t, mtof(lift(root() - 12)), gain, 'boom', { glide: 0.75, wet: 1.4, rich: 0.1 });
    noise(t + 0.05, 3, gain * 0.08, 160, 1.2);
  }
  // a pitch from the scale: degree within the current key
  function pitch(deg, oct) {
    const S = pal.scale, n = S.length, k = ((deg % n) + n) % n, o = Math.floor(deg / n);
    return mtof(lift(root() + S[k] + 12 * (o + (oct || 0))));
  }

  // ── reading a frame: who is alive, how many, what they are like ────────
  function kindsOf(d) {
    const out = new Map();
    if (slug === 'coast') {
      const anim = new Map(), flor = new Map();
      for (const a of d.animals || []) {
        const sp = a[4], look = a.slice(7);
        const r = anim.get(sp) || { n: 0, look }; r.n++; anim.set(sp, r);
      }
      for (const p of d.plants || []) { const sp = p[10]; const r = flor.get(sp) || { n: 0, p }; r.n++; flor.set(sp, r); }
      const ta = [...anim.values()].reduce((s, r) => s + r.n, 0) || 1, tp = [...flor.values()].reduce((s, r) => s + r.n, 0) || 1;
      for (const [sp, r] of anim) {
        const [hue, , , , glow, segs, , size, , , , diet] = r.look;
        const deg = Math.floor(hue * pal.scale.length * 2);
        out.set('a' + sp, { share: r.n / ta, n: r.n, deg, oct: size > 0.75 ? -1 : size < 0.35 ? 1 : 0, timbre: pal.voice,
                            dark: diet > 0.6, oct2: diet > 0.6 ? -1 : 0, glow, segs, name: (d.names || {})[sp] });
      }
      for (const [sp, r] of flor) {
        const [, , , hue, petals] = r.p;
        out.set('p' + sp, { share: r.n / tp, n: r.n, deg: Math.floor(hue * pal.scale.length * 2) + Math.round(petals), oct: 1, timbre: pal.voice2,
                            name: (d.names || {})[sp] });
      }
    } else {
      const last = (d.strata || []).slice(-1)[0];
      const cols = (last && last.cols) || [];
      const tot = cols.reduce((s, c) => s + (c[2] || 0), 0) || 1;
      const same = {};
      cols.slice().sort((a, b) => b[2] - a[2]).forEach((c, i) => {
        const base = 'h' + Math.round(c[0] * 1000) + ':' + Math.round(c[1] * 100), j = same[base] = (same[base] || 0) + 1;
        const key = base + '#' + j;            // lineages that share a colour are still separate loops
        out.set(key, { share: c[2] / tot, n: c[2], deg: Math.floor(c[0] * pal.scale.length * 2) + (j - 1) * 2, oct: i === 0 ? -1 : i > 3 ? 1 : 0,
                       timbre: i === 0 || !pal.voice2 ? pal.voice : pal.voice2 });
      });
    }
    // every kind keeps its loop; only the fourteen most numerous are loud enough to hear
    const ranked = [...out.entries()].sort((a, b) => b[1].share - a[1].share);
    ranked.forEach(([, v], i) => { v.rank = i; });
    return new Map(ranked);
  }

  function feed(d) {
    if (!d) return;
    const s = d.stats || {};
    light = d.light != null ? d.light : 1;
    const pr = pal.progress;
    if (pr && s[pr[0]] != null) rich = clamp((s[pr[0]] - pr[1]) / (pr[2] - pr[1]), 0, 1);
    const kinds = kindsOf(d);
    if (!A || !on) { prime(d, kinds); return; }
    const t = A.currentTime;
    // the loops: new kinds arrive with a seed-chime, lost kinds leave with a falling note
    let chimes = 2, farewells = 2;            // even a burst of change stays music, not alarm
    for (const [k, v] of kinds) {
      let o = voices.get(k);
      if (!o) {
        const h = hash(slug + k);
        o = { period: 18 + h * 30, next: t + 3 + hash(k + 'p') * 16, pan: (hash(k + 'x') - 0.5) * 1.2 };
        voices.set(k, o);
        const back = heard.get(k);              // a kind that only flickered out for a moment is not new
        if (!firstFrame && (!back || t - back > 90) && chimes-- > 0)
          note(t + Math.random() * 1.5, pitch(v.deg, (v.oct || 0) + 1), 0.022, pal.chime, { pan: o.pan, echo: 0.5, wet: 1.1 });
      }
      Object.assign(o, v, { miss: 0 });
      heard.set(k, t);
    }
    for (const [k, o] of voices) {
      if (kinds.has(k)) continue;
      if (++o.miss < 4) continue;               // gone for several frames running: it has died out here
      voices.delete(k);
      if (!firstFrame && o.rank < 20 && farewells-- > 0)
        note(t + Math.random() * 2, pitch(o.deg, o.oct || 0), 0.03, o.timbre || pal.voice, { glide: 0.8, wet: 1.4, echo: 0.6, pan: o.pan, hold: 2 });
    }
    if (heard.size > 4000) heard.clear();
    // the rain: counters that rose since the last frame
    // spread each batch of rain across the time it took to arrive, so a world that reports every
    // twenty seconds still rains steadily instead of in bursts
    const changed = prevStats && JSON.stringify(pal.rain.map(r => s[r[0]])) !== JSON.stringify(pal.rain.map(r => prevStats[r[0]]));
    const span = clamp(t - (lastRainT || t - 2), 1.5, 30);
    if (changed) lastRainT = t;
    if (prevStats && !firstFrame && changed) {
      const chord = [...voices.values()].filter(v => v.rank < voicesAudible());
      let budget = rainBudget();          // never a downpour
      for (const [key, timbre, , scale] of pal.rain || []) {
        const dv = (s[key] || 0) - (prevStats[key] || 0);
        if (!(dv > 0)) continue;
        const k = Math.min(budget, Math.round(Math.log1p(dv * (scale || 1)) * 1.1 * Math.pow(2, MIX.rain))); budget -= k;
        for (let i = 0; i < k; i++) {
          const v = chord.length ? chord[Math.floor(Math.random() * chord.length)] : { deg: 0, oct: 0 };
          const at = t + 0.1 + Math.random() * span;
          if (timbre === 'boom') boom(at, 0.06);
          else if (timbre === 'crackle') noise(at, 0.3 + Math.random() * 0.5, 0.018, 900 + Math.random() * 1200, 1.5);
          else note(at, pitch(v.deg + (timbre === 'drip' ? 7 : 0), timbre === 'thump' ? -1 : 1), timbre === 'drip' ? 0.011 : 0.018, timbre, { pan: (Math.random() - 0.5) * 1.4, wet: 1 });
        }
      }
    }
    // the events: milestones change key, establishments swell, extinctions mourn
    const ev = d.events || [];
    for (const e of ev) {
      if (e.tick == null || (lastEventTick != null && e.tick <= lastEventTick)) continue;
      if (lastEventTick == null) continue;
      const txt = (e.text || '').toLowerCase(), kind = (e.kind || '').toLowerCase();
      if (kind.includes('milestone') || kind.includes('record')) {
        keyShift = ((keyShift + 7) % 12 + 12) % 12; if (keyShift > 6) keyShift -= 12;
        retune(6);
        [0, 4, 7, 14].forEach((iv, i) => note(t + 0.6 + i * 0.7, mtof(lift(root() + iv)), 0.03, pal.chime, { wet: 1.3, echo: 0.4, pan: (i - 1.5) * 0.4 }));
      } else if (kind.includes('extinct') || txt.includes(' is gone')) {
        note(t + 0.3, pitch(-2, 0), 0.028, pal.voice, { glide: 0.7, wet: 1.6, echo: 0.6, hold: 2.5 });
      } else if (txt.includes('established')) {
        const v = [...voices.values()].find(v => v.name && txt.includes(v.name.toLowerCase())) || { deg: 2, oct: 0 };
        note(t + 0.2, pitch(v.deg, v.oct || 0), 0.035, pal.voice2 || pal.voice, { wet: 1.1, hold: 1.6 });
        note(t + 1.4, pitch(v.deg + 2, v.oct || 0), 0.025, pal.voice2 || pal.voice, { wet: 1.1, hold: 1.4 });
      } else {
        note(t + 0.2, pitch(4, 0), 0.02, pal.chime, { wet: 1.2, echo: 0.4 });
      }
    }
    if (ev.length) lastEventTick = Math.max(lastEventTick == null ? -1 : lastEventTick, ...ev.map(e => e.tick || 0));
    prevStats = Object.assign({}, s);
    // the drone follows the whole population, and the night
    const pop = slug === 'coast' ? ((s.animals || 0) + (s.plants || 0) / 6) : [...kinds.values()].reduce((a, v) => a + (v.n || 0), 0);
    const dl = clamp(0.008 + Math.log1p(pop) * 0.0035, 0.008, 0.035);
    drone.dg.gain.setTargetAtTime(dl * droneMul(), t, 4);
    if (bedG) bedG.gain.setTargetAtTime(0.05 * droneMul() * (0.55 + 0.45 * light), t, 5);
    drone.df.frequency.setTargetAtTime(180 + 500 * light + 300 * rich, t, 6);
    drone.hg.gain.setTargetAtTime((0.002 + 0.025 * rich * rich) * droneMul(), t, 8);
    firstFrame = false;
  }
  function prime(d, kinds) {        // remember the state without sounding it, so turning on does not replay history
    prevStats = Object.assign({}, d.stats || {});
    const ev = d.events || [];
    if (ev.length) lastEventTick = Math.max(...ev.map(e => e.tick || 0));
    else if (lastEventTick == null) lastEventTick = -1;
  }

  // the loops come round on their own clocks
  function scheduler() {
    if (!A || !on) return;
    const t = A.currentTime, dens = (0.8 + 0.5 * (1 - light)) * Math.pow(2, -MIX.pace), audible = voicesAudible();
    bedEvents(t);
    for (const [, o] of voices) {
      if (o.rank >= audible) { while (o.next < t + 0.4) o.next += o.period; continue; }
      while (o.next < t + 0.4) {
        if (o.next > t - 0.5) {
          const g = clamp(0.018 + 0.07 * Math.sqrt(o.share || 0), 0.015, 0.08);
          note(Math.max(o.next, t + 0.02), pitch(o.deg, (o.oct || 0) + (o.oct2 || 0)), g, o.timbre, { pan: o.pan, dark: o.dark, echo: 0.25 + 0.2 * (1 - light), wet: 0.6 + 0.4 * (1 - light) });
          if (o.glow > 0.3) note(o.next + 0.08, pitch(o.deg, (o.oct || 0) + 1), g * 0.2 * o.glow, pal.chime, { pan: o.pan, wet: 1.2 });
        }
        o.next += o.period * dens;
      }
    }
  }

  // ── the mixer: knobs for the listener ─────────────────────────────────
  const KNOBS = [
    { key: 'volume', label: 'Volume', low: 'silent', high: 'full', c: '#f2b33d', unit: true,
      icon: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9c1.5 1.5 1.5 4.5 0 6M18.5 6.5c3 3 3 8 0 11"/>' },
    { key: 'pace', label: 'Pace', low: 'slow, few voices', high: 'lively, many voices', c: '#8fd3c8',
      icon: '<circle cx="12" cy="13" r="7"/><path d="M12 13l3-4M10 3h4"/>' },
    { key: 'tone', label: 'Tone', low: 'soft and dark', high: 'bright and shimmering', c: '#e5602a',
      icon: '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>' },
    { key: 'space', label: 'Space', low: 'close and dry', high: 'a vast hall', c: '#c9b6ff',
      icon: '<path d="M3 20h18M5 20V10l7-6 7 6v10"/><path d="M10 20v-5h4v5"/>' },
    { key: 'rain', label: 'Rain', low: 'none: loops only', high: 'every event sounds', c: '#a8c94a',
      icon: '<path d="M7 16a5 5 0 1 1 1-9.9A6 6 0 0 1 19 9a4 4 0 0 1-1 7.9"/><path d="M9 19l-1 2M13 19l-1 2M17 19l-1 2"/>' },
    { key: 'drone', label: 'Drone', low: 'off', high: 'deep and full', c: '#ee7d22',
      icon: '<path d="M2 12c2-3 4-3 6 0s4 3 6 0 4-3 6 0 2 1 2 1"/>' },
  ];
  const SW = 135;
  function arc(r, a0, a1) {
    const p = a => [50 + r * Math.sin(a * Math.PI / 180), 50 - r * Math.cos(a * Math.PI / 180)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return `M${x0.toFixed(2)},${y0.toFixed(2)} A${r},${r} 0 ${Math.abs(a1 - a0) > 180 ? 1 : 0} ${a1 > a0 ? 1 : 0} ${x1.toFixed(2)},${y1.toFixed(2)}`;
  }
  const mixCss = `
  .mix-top { display: flex; gap: 1.2vmin; flex-wrap: wrap; margin: 0 0 1.4vmin; }
  .mix-btn { font: 500 1.8vmin "IBM Plex Mono", monospace; letter-spacing: .06em; text-transform: uppercase; padding: 1vmin 1.8vmin;
    border-radius: 3vmin; border: .25vmin solid #2a1d14; background: #fbf3dc; color: #2a1d14; cursor: pointer; }
  .mix-btn.on { background: #2a1d14; color: #fbf3dc; }
  .mix { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5vmin 2vmin; padding: 4.2vmin 0 1vmin; }
  .mix-cell { display: flex; flex-direction: column; align-items: center; text-align: center; }
  .mix-cell .dial { margin-bottom: 1vmin; }
  .mix-cell b { font: 400 2vmin "Righteous", sans-serif; letter-spacing: .06em; text-transform: uppercase; }
  .mix-cell small { font: 400 1.4vmin/1.3 "IBM Plex Mono", monospace; color: #6b5340; }`;
  let mixRoot = null;
  function fmt10(k, v) { if (k.unit) return String(Math.round(v * 10)); const n = Math.round(v * 10); return n > 0 ? '+' + n : n < 0 ? '\u2212' + Math.abs(n) : '0'; }
  function mixerHTML() {
    return `<div class="mix-top"><button type="button" class="mix-btn mix-power"></button><button type="button" class="mix-btn mix-sleep"></button>
      <button type="button" class="mix-btn mix-reset">Reset</button></div>
      <div class="mix">${KNOBS.map(k => `<div class="mix-cell"><button type="button" class="dial" data-k="${k.key}" style="--c:${k.c}" aria-label="${k.label}">
        <svg class="ring" viewBox="0 0 100 100"><path d="${arc(47, -SW, SW)}" fill="none" stroke="rgba(42,29,20,.55)" stroke-width="5" stroke-linecap="round"/>
        <path class="val" fill="none" stroke="${k.c}" stroke-width="5" stroke-linecap="round"/><circle cx="50" cy="3" r="2.2" fill="#2a1d14"/></svg>
        <div class="cap"><svg viewBox="0 0 24 24">${k.icon}</svg></div><div class="notch"></div><div class="dial-num">0</div></button>
        <b>${k.label}</b><small>${k.low} \u2194 ${k.high}</small></div>`).join('')}</div>
      <p class="note">These knobs change only how this panel sounds here, never the world itself. Drag a knob round to turn it; double-tap it to put it back. Settings are kept on this device.</p>
      <h3 style="font:400 2.2vmin Righteous,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#b9560c;margin:2.4vmin 0 1vmin">What you hear</h3>${legend()}`;
  }
  function syncMixer() {
    if (!mixRoot || !mixRoot.isConnected) { mixRoot = null; return; }
    for (const k of KNOBS) {
      const el = mixRoot.querySelector(`.dial[data-k="${k.key}"]`); if (!el) continue;
      const v = MIX[k.key], ang = k.unit ? (v * 2 - 1) * SW : v * SW, a0 = k.unit ? -SW : 0;
      el.querySelector('path.val').setAttribute('d', Math.abs(ang - a0) < 1 ? '' : arc(47, Math.min(a0, ang), Math.max(a0, ang)));
      el.querySelector('.notch').style.transform = `rotate(${ang}deg)`;
      el.querySelector('.cap').style.transform = `rotate(${ang * 0.25}deg)`;
      const lab = el.querySelector('.dial-num'); lab.textContent = fmt10(k, v);
      lab.classList.toggle('max', k.unit ? v >= 0.995 : Math.abs(v) >= 0.995);
    }
    const pw = mixRoot.querySelector('.mix-power'); pw.textContent = on ? 'Sound on' : 'Sound off'; pw.classList.toggle('on', on);
    const sl = mixRoot.querySelector('.mix-sleep');
    sl.textContent = sleepEnd ? `Sleep in ${Math.max(1, Math.ceil((sleepEnd - Date.now()) / 60000))} min` : 'Sleep timer: off';
    sl.classList.toggle('on', !!sleepEnd);
  }
  function mountMixer(root) {
    if (!document.getElementById('algo-mix-css')) { const st = document.createElement('style'); st.id = 'algo-mix-css'; st.textContent = mixCss; document.head.appendChild(st); }
    mixRoot = root;
    root.querySelector('.mix-power').onclick = () => { toggle(); syncMixer(); };
    root.querySelector('.mix-sleep').onclick = () => {
      const steps = [0, 15, 30, 60, 90], i = steps.indexOf(sleepMin);
      setSleep(steps[(i + 1) % steps.length]); if (!on && sleepMin) start(); syncMixer();
    };
    root.querySelector('.mix-reset').onclick = () => { Object.assign(MIX, MIX_DEFAULT); applyMix(); syncMixer(); };
    root.querySelectorAll('.dial[data-k]').forEach(el => {
      const k = KNOBS.find(x => x.key === el.dataset.k);
      let drag = null, lastTap = 0;
      const val = e => {
        const r = el.getBoundingClientRect(), deg = Math.atan2(e.clientX - (r.left + r.width / 2), -(e.clientY - (r.top + r.height / 2))) * 180 / Math.PI;
        const f = clamp(deg / SW, -1, 1); return k.unit ? (f + 1) / 2 : f;
      };
      el.addEventListener('pointerdown', e => { drag = [e.clientX, e.clientY, false]; el.setPointerCapture(e.pointerId); e.preventDefault(); });
      el.addEventListener('pointermove', e => {
        if (!drag) return;
        if (!drag[2] && Math.hypot(e.clientX - drag[0], e.clientY - drag[1]) < 6) return;
        drag[2] = true; MIX[k.key] = val(e); applyMix(); syncMixer();
      });
      el.addEventListener('pointerup', () => {
        if (drag && !drag[2]) { const now = performance.now(); if (now - lastTap < 400) { MIX[k.key] = MIX_DEFAULT[k.key]; applyMix(); syncMixer(); } lastTap = now; }
        drag = null;
      });
      el.addEventListener('pointercancel', () => { drag = null; });
      el.addEventListener('keydown', e => {
        const step = e.key === 'ArrowRight' || e.key === 'ArrowUp' ? 0.1 : e.key === 'ArrowLeft' || e.key === 'ArrowDown' ? -0.1 : 0;
        if (!step) return; e.preventDefault();
        MIX[k.key] = clamp(Math.round((MIX[k.key] + step) * 10) / 10, k.unit ? 0 : -1, 1); applyMix(); syncMixer();
      });
    });
    syncMixer();
  }

  // ── on and off ───────────────────────────────────────────────────────
  function start() {
    try {
      if (!A) build();
      if (A.state === 'suspended') A.resume();
      on = true; firstFrame = true;
      out.gain.cancelScheduledValues(A.currentTime); out.gain.setTargetAtTime(volGain(), A.currentTime, 3); applyMix();
      clearInterval(tickT); tickT = setInterval(scheduler, 200);
      try { localStorage.setItem('algo-sound', '1'); } catch (e) {}
    } catch (e) { on = false; }
    return on;
  }
  function stop() {
    on = false;
    if (A) { out.gain.cancelScheduledValues(A.currentTime); out.gain.setTargetAtTime(0, A.currentTime, 0.6); }
    clearInterval(tickT); voices.clear();
    try { localStorage.setItem('algo-sound', '0'); } catch (e) {}
  }
  function toggle() { return on ? (stop(), false) : start(); }
  function level() {
    if (!A || !on) return 0;
    analyser.getFloatTimeDomainData(buf);
    let s = 0; for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i];
    lastLvl = lastLvl * 0.8 + Math.sqrt(s / buf.length) * 0.2 * 6;
    return clamp(lastLvl, 0, 1);
  }
  function init(s) {
    slug = P[s] ? s : 'coast'; pal = P[slug];
    const q = new URLSearchParams(location.search).get('sound');
    let want = q === '1';
    try { if (q == null && localStorage.getItem('algo-sound') === '1') want = true; } catch (e) {}
    if (want) {
      start();
      if (A && A.state === 'suspended') {            // browsers wait for a first touch; the next one anywhere starts it
        const go = () => { A.resume(); removeEventListener('pointerdown', go, true); removeEventListener('keydown', go, true); };
        addEventListener('pointerdown', go, true); addEventListener('keydown', go, true);
      }
    }
    addEventListener('keydown', e => { if (e.key === 's' && !e.metaKey && !e.ctrlKey && !/input|textarea/i.test(e.target.tagName)) toggle(); });
  }

  // the speaker grille in the tray: dots that breathe with the sound when it is on
  function drawGrille(g, gx, gy, gs, u) {
    const lv = level(), audible = on && A && A.state === 'running';
    g.save();
    g.beginPath(); g.roundRect ? g.roundRect(gx, gy, gs, gs, u * 0.01) : g.rect(gx, gy, gs, gs);
    g.fillStyle = audible ? '#d9b84a' : '#c9a63c'; g.fill(); g.strokeStyle = '#2a1d14'; g.lineWidth = u * 0.002; g.stroke();
    for (let i = 1; i < 7; i++) for (let j = 1; j < 7; j++) {
      const dx = i - 3.5, dy = j - 3.5, ring = Math.sqrt(dx * dx + dy * dy) / 3.6;
      const k = audible ? clamp(lv * 1.8 - ring * 0.7 + 0.15, 0, 1) : 0;
      g.fillStyle = k > 0.02 ? `rgba(238,125,34,${0.45 + 0.55 * k})` : 'rgba(42,29,20,0.55)';
      g.beginPath(); g.arc(gx + gs * i / 7, gy + gs * j / 7, u * (0.003 + 0.0022 * k), 0, Math.PI * 2); g.fill();
    }
    if (!audible) {                                    // a small muted-speaker mark so it reads as a button
      const cx = gx + gs * 0.5, cy = gy + gs * 0.5, r = gs * 0.17;
      g.fillStyle = '#fbf3dc'; g.strokeStyle = '#2a1d14'; g.lineWidth = u * 0.0016;
      g.beginPath(); g.arc(cx, cy, r * 1.6, 0, Math.PI * 2); g.fill(); g.stroke();
      g.fillStyle = '#2a1d14'; g.beginPath();
      g.moveTo(cx - r * 0.8, cy - r * 0.35); g.lineTo(cx - r * 0.35, cy - r * 0.35); g.lineTo(cx + r * 0.2, cy - r * 0.8);
      g.lineTo(cx + r * 0.2, cy + r * 0.8); g.lineTo(cx - r * 0.35, cy + r * 0.35); g.lineTo(cx - r * 0.8, cy + r * 0.35); g.closePath(); g.fill();
      g.strokeStyle = '#2a1d14'; g.lineWidth = u * 0.0022; g.beginPath();
      g.moveTo(cx + r * 0.5, cy - r * 0.35); g.lineTo(cx + r * 1.0, cy + r * 0.35); g.moveTo(cx + r * 1.0, cy - r * 0.35); g.lineTo(cx + r * 0.5, cy + r * 0.35); g.stroke();
    }
    g.restore();
  }
  function legend() {
    const p = pal;
    return `<p class="note">This panel's sound: ${esc(p.sound)}. Everything you hear is made by the world as it changes. Nothing is recorded or composed.</p><table>
      <tr><td>A steady loop of one note</td><td>one living kind (${esc(p.words)})</td></tr>
      <tr><td>How loud its loop is</td><td>how many of it there are</td></tr>
      <tr><td>A high chime, then a new loop</td><td>a new variant has appeared</td></tr>
      <tr><td>A soft swelling chord</td><td>a kind has become established</td></tr>
      <tr><td>A falling note into the echo</td><td>a kind has died out; its loop stops</td></tr>
      <tr><td>Rain of small notes</td><td>${esc((p.rain || []).map(r => r[2]).join(', '))}</td></tr>
      <tr><td>Overtones and the high halo</td><td>progress: ${esc(p.progress[0].replace(/_/g, ' '))}, now ${Math.round(rich * 100)}% of the way</td></tr>
      <tr><td>A ringing chord, then a new key</td><td>a milestone</td></tr>
      <tr><td>The drone and the ${esc(p.bed === 'pulse' ? 'heartbeat' : p.bed)} beneath</td><td>the whole population; both darken and thin out at night</td></tr></table>
      <p class="note" style="margin-top:1.4vmin">Tap the speaker grille for the sound knobs (or press S to turn it on and off). Loops now: ${Math.min(14, voices.size)} sounding, ${voices.size} kinds alive.</p>`;
  }
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // tap(): the final output node, for recording a sample of the soundscape
  window.AlgoSound = { init, feed, start, stop, toggle, isOn: () => on, level, drawGrille, legend, mixerHTML, mountMixer, syncMixer, tap: () => A && { ctx: A, node: analyser } };
})();
