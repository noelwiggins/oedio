/* Algo — the player: one scheduler feeding the audio engine and the picture from the same events, the controls, the
   voice recorder, and the exports. The score is in engine.js (window.Glass). */
(function () {
  'use strict';
  const G = window.Glass, $ = id => document.getElementById(id), TAU = Math.PI * 2;
  const INST = G.INSTRUMENTS, LABEL = { piano: 'Piano', organ: 'Organ', violin: 'Violin', voice: 'Voice sampler' };

  // ── state ─────────────────────────────────────────────────────────────
  let audio = null, score = new G.Score(1976), playing = false, timer = null, nextT = 0, startT = 0;
  let log = [], pending = [], replay = null;      // log: [step, key, value]; replay: a loaded session's log, by step
  const timeline = [];                            // [audio time, step, result] for the picture (recent)
  const noteLog = [];                             // [step, instrument, midi, length, velocity] for MIDI export
  const tempoLog = [[0, 112]];
  const settings = { seed: 1976, complexity: 55, tempo: 112, lead: 0, master: 0.8, duration: 0,
    vol: { piano: 0.8, organ: 0.7, violin: 0.75, voice: 0.8 },
    voice: { mode: 'harmonizer', clarity: 0.6, wet: 0.45, reverb: 0.35, layers: 2, speed: 1, reps: 1, loop: false, trim: [0, 1] } };
  let midiOut = null;
  const stepDur = () => 60 / score.ctl.tempo / 2;

  // ── control changes: applied on a step boundary, logged by that step, replayable exactly ──
  function change(key, value) {
    if (key === 'seed') { settings.seed = value; restart(); return; }
    pending.push([key, value]);
    if (!playing) applyNow(key, value, null);
  }
  function applyNow(key, value, at) {
    const k = key.split('.');
    if (k[0] === 'complexity') { score.ctl.complexity = value; settings.complexity = value; }
    else if (k[0] === 'tempo') { score.ctl.tempo = value; settings.tempo = value; }
    else if (k[0] === 'lead') { settings.lead = value; score.ctl.lead = value; if (audio) audio.setLead(value, at); }
    else if (k[0] === 'master') { settings.master = value; if (audio) audio.out.gain.setTargetAtTime(value, at || audio.ctx.currentTime, 0.03); }
    else if (k[0] === 'vol') { settings.vol[k[1]] = value; if (audio) audio.bus[k[1]].gain.setTargetAtTime(value, at || audio.ctx.currentTime, 0.03); }
    else if (k[0] === 'voice') {
      settings.voice[k[1]] = value;
      if (audio) {
        const V = audio.voice;
        if (k[1] === 'reverb') audio.verbIn.gain.setTargetAtTime(value, audio.ctx.currentTime, 0.05);
        else if (k[1] === 'wet') audio.send.voice.gain.setTargetAtTime(value, audio.ctx.currentTime, 0.05);
        else if (k[1] !== 'loop') V[k[1]] = value;
      }
    }
  }

  // ── the scheduler: precise audio time, independent of the picture's frame rate ──
  function tick() {
    if (!playing || !audio) return;
    const A = audio.ctx, ahead = document.hidden ? 1.6 : 0.3;
    if (settings.duration && A.currentTime - startT > settings.duration * 60) score.finish();
    while (nextT < A.currentTime + ahead) {
      const step = score.step;
      if (replay) for (const [s, key, value] of (replay.get(step) || [])) applyNow(key, value, nextT);
      for (const [key, value] of pending) { applyNow(key, value, nextT); log.push([step, key, value, +(nextT - startT).toFixed(3)]); }
      if (score.ctl.tempo !== tempoLog[tempoLog.length - 1][1]) tempoLog.push([step, score.ctl.tempo]);
      pending = [];
      const r = score.advance();
      if (score.finished) { stop(true); break; }
      if (r.newChord) audio.currentChord = r.chord.v;
      const d = stepDur();
      for (const [inst, midi, len, vel] of r.notes) {
        audio.play(inst, midi, len * d, vel, nextT);
        const name = inst === 'lead' ? INST[settings.lead] : inst;
        noteLog.push([step, name, midi, len, vel]); if (noteLog.length > 200000) noteLog.splice(0, 50000);
        if (midiOut) sendMidi(name, midi, len * d, vel, nextT);
      }
      timeline.push([nextT, step, r]); if (timeline.length > 3000) timeline.splice(0, 1000);
      nextT += d;
    }
  }
  function sendMidi(name, midi, dur, vel, t) {
    const ch = INST.indexOf(name), at = performance.now() + (t - audio.ctx.currentTime) * 1000;
    try { midiOut.send([0x90 | ch, midi, Math.round(vel * 127)], at); midiOut.send([0x80 | ch, midi, 0], at + dur * 1000); } catch (e) {}
  }
  function ensureAudio() {
    if (audio) return;
    audio = new G.Audio();
    for (const [k, v] of Object.entries(settings.vol)) audio.bus[k].gain.value = v;
    audio.out.gain.value = settings.master; audio.setLead(settings.lead);
    Object.assign(audio.voice, { mode: settings.voice.mode, clarity: settings.voice.clarity, layers: settings.voice.layers, speed: settings.voice.speed, reps: settings.voice.reps, trim: settings.voice.trim });
    audio.verbIn.gain.value = settings.voice.reverb; audio.send.voice.gain.value = settings.voice.wet;
    if (pendingVoice) { pendingVoice(audio.ctx); pendingVoice = null; }
  }
  function play() {
    ensureAudio(); audio.ctx.resume();
    if (!playing) {
      playing = true;
      if (score.step === 0) { startT = audio.ctx.currentTime + 0.1; nextT = startT; if (!replay) start0 = snapshot(); }
      else nextT = Math.max(nextT, audio.ctx.currentTime + 0.05);
      timer = setInterval(tick, 25); tick();
    }
    $('ag-play').textContent = 'Pause'; $('ag-play').classList.add('on');
  }
  function pause() { playing = false; clearInterval(timer); $('ag-play').textContent = 'Play'; $('ag-play').classList.remove('on'); }
  function stop(ended) { pause(); if (ended) $('ag-status').textContent = 'The piece has ended. Restart to hear it again.'; }
  function restart(keepReplay) {
    const was = playing; pause();
    score = new G.Score(settings.seed);
    score.ctl.complexity = settings.complexity; score.ctl.tempo = settings.tempo; score.ctl.lead = settings.lead;
    log = []; pending = []; timeline.length = 0; noteLog.length = 0; tempoLog.length = 0; tempoLog.push([0, settings.tempo]);
    if (!keepReplay) { replay = null; $('ag-replay').hidden = true; }
    start0 = snapshot();
    $('ag-status').textContent = '';
    if (was || keepReplay) play();
  }
  let start0 = null;
  const snapshot = () => ({ complexity: settings.complexity, tempo: settings.tempo, lead: settings.lead, master: settings.master, vol: { ...settings.vol }, voice: { ...settings.voice, trim: settings.voice.trim.slice() } });

  // ── the picture: the same events, drawn as they sound ──────────────────
  const cv = $('ag-canvas'), cx = cv.getContext('2d');
  let W = 0, H = 0, DPR = 1;
  function fit() {
    const r = cv.getBoundingClientRect(); DPR = Math.min(2, window.devicePixelRatio || 1);
    W = Math.max(320, r.width); H = Math.max(180, r.height);
    cv.width = Math.round(W * DPR); cv.height = Math.round(H * DPR);
  }
  new ResizeObserver(fit).observe(cv); fit();
  const LANE = { piano: 0.2, violin: 0.32, voice: 0.68, organ: 0.8 };
  function poly(c, x, y, r, n, rot) {
    c.beginPath();
    if (n === 0) { c.arc(x, y, r, 0, TAU); return; }
    for (let i = 0; i <= n; i++) { const a = rot + i / n * TAU - Math.PI / 2; c[i ? 'lineTo' : 'moveTo'](x + Math.cos(a) * r, y + Math.sin(a) * r); }
    c.closePath();
  }
  const SIDES = { circle: 0, triangle: 3, square: 4, hexagon: 6 };
  function nowStep(t) {                    // the step sounding at audio time t, fractional, from the scheduled timeline
    for (let i = timeline.length - 1; i >= 0; i--) {
      const [tt, s] = timeline[i];
      if (tt <= t) { const nx = timeline[i + 1]; const d = nx ? nx[0] - tt : stepDur(); return s + Math.min(1, (t - tt) / d); }
    }
    return timeline.length ? timeline[0][1] : 0;
  }
  function draw() {
    requestAnimationFrame(draw);
    const c = cx; c.setTransform(DPR, 0, 0, DPR, 0, 0);
    c.fillStyle = '#07090c'; c.fillRect(0, 0, W, H);
    const t = audio ? audio.ctx.currentTime : 0, now = nowStep(t);
    const SPAN = 112, px = W / SPAN, playX = W * 0.84, xOf = s => playX - (now - s) * px;
    // stillness: during a rest everything dims and a single horizon remains
    const cur = timeline.length ? (timeline.find(e => e[1] === Math.floor(now)) || timeline[timeline.length - 1])[2] : null;
    const still = cur && cur.resting ? 1 : 0;
    // the rhythmic cycles: three lanes of marks every 5, 7 and 11 eighths; where two coincide, a line joins them
    c.lineWidth = 1;
    const s0 = Math.floor(now - SPAN * 0.9), s1 = Math.ceil(now + SPAN * 0.2);
    for (let s = s0; s <= s1; s++) {
      const x = xOf(s), hits = [];
      for (const [name, n] of [['piano', 5], ['organ', 7], ['violin', 11]]) if (((s % n) + n) % n === 0) {
        hits.push(name);
        c.strokeStyle = `rgba(200,210,230,${0.14 - 0.08 * still})`; c.beginPath(); c.moveTo(x, H * LANE[name] - 4); c.lineTo(x, H * LANE[name] + 4); c.stroke();
      }
      if (hits.length >= 2) {
        c.strokeStyle = `rgba(200,210,230,${hits.length === 3 ? 0.35 : 0.1})`; c.setLineDash([2, 5]);
        c.beginPath(); c.moveTo(x, H * LANE[hits[0]]); c.lineTo(x, H * LANE[hits[hits.length - 1]]); c.stroke(); c.setLineDash([]);
      }
    }
    // chords: one shape each, in its colour, as wide as it lasts; inversion turns it; the phrase grows rings inside it;
    // arpeggio density sets how many rays it has. The same number in the same place gives the same motif.
    const seen = new Set();
    for (const [, , r] of timeline) {
      const C = r.chord; if (!C || seen.has(C.cc)) continue; seen.add(C.cc);
      const x0 = xOf(C.start), x1 = xOf(C.start + C.len);
      if (x1 < -50 || x0 > W + 50) continue;
      const ch = G.CHORDS[C.ci], n = SIDES[ch.shape], xm = (x0 + Math.min(x1, playX + 2)) / 2, yc = H * 0.5;
      const live = now >= C.start && now < C.start + C.len;
      const age = Math.max(0, (now - (C.start + C.len)) / SPAN);
      const R = Math.min((x1 - x0) * 0.42, H * 0.26) * (C.sil.sustain ? 1.1 : 1);
      const rot = C.inv * TAU / (n ? n * 3 : 6) + (live ? (now - C.start) * 0.002 : 0);
      const a = Math.max(0, (1 - age * 1.3)) * (live ? 1 : 0.55) * (1 - 0.6 * still);
      if (a <= 0.01) continue;
      c.globalAlpha = a;
      c.strokeStyle = ch.colour; c.lineWidth = live ? 1.6 : 1;
      if (C.num.mutated) c.setLineDash([6, 4]);
      poly(c, xm, yc, R, n, rot); c.stroke(); c.setLineDash([]);
      // the phrase: one ring per note in it, each a little smaller and turned; growing and shrinking with the phrase
      for (let k = 1; k <= C.L; k++) {
        c.globalAlpha = a * (0.5 - k * 0.05);
        poly(c, xm, yc, R * (1 - k * 0.11), n, rot + k * (C.changed > 0 ? 0.12 : C.changed < 0 ? -0.12 : 0.06)); c.stroke();
      }
      // rays: one per arpeggio attack, lengths fixed by the number and the chord (so a recurring motif recurs)
      c.globalAlpha = a * 0.7; c.lineWidth = 0.8;
      for (let k = 0; k < C.density * 2; k++) {
        const ang = rot + k / (C.density * 2) * TAU, len = R * (0.35 + 0.65 * G.hash(C.ci, C.N, C.L, k));
        c.beginPath(); c.moveTo(xm + Math.cos(ang) * R * 0.15, yc + Math.sin(ang) * R * 0.15); c.lineTo(xm + Math.cos(ang) * len, yc + Math.sin(ang) * len); c.stroke();
        c.fillStyle = ch.colour; c.beginPath(); c.arc(xm + Math.cos(ang) * len, yc + Math.sin(ang) * len, 1.6, 0, TAU); c.fill();
      }
      c.globalAlpha = 1; c.lineWidth = 1;
    }
    // the notes: a point on its instrument's lane; at the moment it sounds, it flares and reaches toward the chord
    for (const [tt, s, r] of timeline) {
      if (!r.notes.length) continue;
      const x = xOf(s); if (x < -10 || x > W + 10) continue;
      const C = r.chord, col = G.CHORDS[C.ci].colour, dt = t - tt;
      for (const [inst, midi, len, vel] of r.notes) {
        const name = inst === 'lead' ? INST[settings.lead] : inst, y = H * LANE[name] + (inst === 'lead' ? -10 : 0) + (60 - midi) * 0.6;
        const w = Math.max(2, len * px);
        c.globalAlpha = 0.35 * (1 - 0.5 * still); c.fillStyle = col; c.fillRect(x, y - 1, w, 2);
        if (dt >= 0 && dt < 0.5) {
          const k = 1 - dt / 0.5;
          c.globalAlpha = 0.8 * k; c.beginPath(); c.arc(x, y, 2 + 10 * vel * k, 0, TAU); c.strokeStyle = col; c.stroke();
          c.globalAlpha = 0.18 * k; c.beginPath(); c.moveTo(x, y); c.lineTo(Math.min(playX, xOf(C.start + C.len / 2)), H * 0.5); c.stroke();
        }
        c.globalAlpha = dt >= 0 ? 0.9 : 0.25; c.beginPath(); c.arc(x, y, 1.8 + vel * 1.5, 0, TAU); c.fill();
      }
    }
    c.globalAlpha = 1;
    // the playhead and the horizon
    c.strokeStyle = 'rgba(220,225,235,0.12)'; c.beginPath(); c.moveTo(playX, 0); c.lineTo(playX, H); c.stroke();
    c.strokeStyle = `rgba(220,225,235,${0.05 + 0.12 * still})`; c.beginPath(); c.moveTo(0, H * 0.5); c.lineTo(W, H * 0.5); c.stroke();
    // a quiet caption
    if (cur && cur.chord) {
      const C = cur.chord;
      c.fillStyle = 'rgba(220,225,235,0.55)'; c.font = '12px "IBM Plex Mono", monospace';
      c.fillText(`${G.MOVEMENTS[C.mi].name}   ${G.CHORDS[C.ci].name}   N=${C.N}   phrase ${C.L}   ${C.sil.restBeats && cur.resting ? 'silence' : C.sil.sustain ? 'held' : ''}`, 14, H - 14);
    }
    if (videoRec) composite();
    panel(cur);
  }

  // ── the readouts beside the picture ───────────────────────────────────
  let lastPanel = '';
  function panel(cur) {
    const N = score.nums, key = N.count + ':' + score.chordCount;
    if (key === lastPanel) return; lastPanel = key;
    const cells = $('ag-seq').children, at = (N.pos + 15) % 16;
    for (let i = 0; i < 16; i++) {
      cells[i].textContent = N.seq[i];
      cells[i].className = (i === at ? 'now ' : '') + (N.changed.has(i) && N.gen > 0 ? 'mut' : '');
    }
    $('ag-seqinfo').textContent = `repetition ${N.rep + 1} of 4 · generation ${N.gen} · ${N.count} numbers · ${N.mutations.length / 2} mutations`;
    const C = score.chord;
    if (C) {
      $('ag-mov').textContent = G.MOVEMENTS[C.mi].name;
      $('ag-chord').textContent = `${G.CHORDS[C.ci].name} · ${['root', 'first', 'second'][C.inv]} inversion · ${C.beats} beats · ${C.density} attacks a bar`;
      $('ag-phrase').textContent = `phrase of ${C.L} notes${C.changed > 0 ? ' (growing)' : C.changed < 0 ? ' (shrinking)' : ''} · voice cycle ${C.voiceCycle} · playing: ${C.layers.map(l => LABEL[l]).join(', ') || 'silence'}`;
      const hist = N.history.slice(-48).map(h => h[1]).join(' ');
      $('ag-hist').textContent = hist;
    }
  }

  // ── dials ─────────────────────────────────────────────────────────────
  function dial(el, opts) {
    // opts: { min, max, value, steps (array of labels for detents), onChange }
    const svg = el, knob = svg.querySelector('.knob'), mark = svg.querySelector('.mark'), arc = svg.querySelector('.arc');
    const A0 = -135, A1 = 135;
    let value = opts.value;
    const toAngle = v => A0 + (v - opts.min) / (opts.max - opts.min) * (A1 - A0);
    function render() {
      const a = toAngle(value);
      mark.setAttribute('transform', `rotate(${a} 100 100)`);
      if (arc) {
        const r = 84, p = ang => [100 + r * Math.sin(ang * Math.PI / 180), 100 - r * Math.cos(ang * Math.PI / 180)];
        const [x0, y0] = p(A0), [x1, y1] = p(a);
        arc.setAttribute('d', `M ${x0} ${y0} A ${r} ${r} 0 ${a - A0 > 180 ? 1 : 0} 1 ${x1} ${y1}`);
      }
      svg.setAttribute('aria-valuenow', value);
      if (opts.steps) svg.querySelectorAll('.det').forEach((d, i) => d.classList.toggle('on', i === value));
      if (opts.out) opts.out.textContent = opts.steps ? opts.steps[value] : Math.round(value);
    }
    function set(v, fire) {
      v = Math.max(opts.min, Math.min(opts.max, v)); if (opts.steps) v = Math.round(v);
      if (v === value) return; value = v; render(); if (fire) opts.onChange(value);
    }
    function fromPointer(e) {
      const r = svg.getBoundingClientRect(), x = e.clientX - (r.left + r.width / 2), y = e.clientY - (r.top + r.height / 2);
      let a = Math.atan2(x, -y) * 180 / Math.PI; a = Math.max(A0, Math.min(A1, a));
      set(opts.min + (a - A0) / (A1 - A0) * (opts.max - opts.min), true);
    }
    let drag = false;
    svg.addEventListener('pointerdown', e => { drag = true; svg.setPointerCapture(e.pointerId); fromPointer(e); });
    svg.addEventListener('pointermove', e => { if (drag) fromPointer(e); });
    svg.addEventListener('pointerup', () => { drag = false; });
    svg.addEventListener('keydown', e => {
      const d = opts.steps ? 1 : 2;
      if (e.key === 'ArrowRight' || e.key === 'ArrowUp') { set(value + d, true); e.preventDefault(); }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') { set(value - d, true); e.preventDefault(); }
    });
    svg.addEventListener('wheel', e => { e.preventDefault(); set(value + (e.deltaY < 0 ? 1 : -1) * (opts.steps ? 1 : 2), true); }, { passive: false });
    if (opts.steps) svg.querySelectorAll('.det').forEach((d, i) => d.addEventListener('pointerdown', e => { e.stopPropagation(); set(i, true); }));
    render();
    return { set: v => set(v, false), get: () => value };
  }
  const instDial = dial($('ag-inst'), { min: 0, max: 3, value: 0, steps: INST.map(n => LABEL[n]), out: $('ag-inst-out'), onChange: v => change('lead', v) });
  const cxDial = dial($('ag-cx'), { min: 0, max: 100, value: 55, out: $('ag-cx-out'), onChange: v => change('complexity', Math.round(v)) });

  // ── sliders and buttons ───────────────────────────────────────────────
  const bind = (id, key, conv) => { const el = $(id); el.addEventListener('input', () => change(key, conv ? conv(el.value) : +el.value)); return el; };
  bind('ag-master', 'master');
  bind('ag-tempo', 'tempo').addEventListener('input', () => { $('ag-tempo-out').textContent = $('ag-tempo').value; });
  for (const n of INST) bind('ag-vol-' + n, 'vol.' + n);
  bind('ag-clarity', 'voice.clarity'); bind('ag-wet', 'voice.wet'); bind('ag-reverb', 'voice.reverb');
  bind('ag-layers', 'voice.layers'); bind('ag-speed', 'voice.speed'); bind('ag-reps', 'voice.reps');
  $('ag-speed').addEventListener('input', () => { $('ag-speed-out').textContent = (+$('ag-speed').value).toFixed(2) + '×'; });
  document.querySelectorAll('input[name=ag-mode]').forEach(r => r.addEventListener('change', () => change('voice.mode', r.value)));
  $('ag-play').onclick = () => (playing ? pause() : play());
  $('ag-restart').onclick = () => restart(!!replay);
  $('ag-seed-go').onclick = () => { const v = parseInt($('ag-seed').value, 10); if (Number.isFinite(v)) change('seed', v); };
  $('ag-duration').onchange = () => { settings.duration = +$('ag-duration').value; log.push([score.step, 'duration', settings.duration]); };
  $('ag-full').onclick = () => { const st = $('ag-stage'); (document.fullscreenElement ? document.exitFullscreen() : (st.requestFullscreen || st.webkitRequestFullscreen).call(st)); };
  const seqBox = $('ag-seq'); for (let i = 0; i < 16; i++) seqBox.appendChild(document.createElement('span'));

  // ── the voice: record, trim, loop, play ───────────────────────────────
  let recorder = null, chunks = [], pendingVoice = null, preview = null;
  $('ag-rec').onclick = async () => {
    if (recorder) { recorder.stop(); return; }
    ensureAudio(); await audio.ctx.resume();
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
    catch (e) { $('ag-voice-status').textContent = 'The microphone is not available: ' + e.message; return; }
    chunks = []; recorder = new MediaRecorder(stream);
    recorder.ondataavailable = e => chunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(chunks, { type: recorder.mimeType }); recorder = null;
      $('ag-rec').textContent = 'Record'; $('ag-rec').classList.remove('on');
      try {
        const buf = await audio.ctx.decodeAudioData(await blob.arrayBuffer());
        audio.setVoice(buf); settings.voice.trim = [0, 1]; audio.voice.trim = [0, 1]; $('ag-trim0').value = 0; $('ag-trim1').value = 1;
        log.push([score.step, 'voice.recorded', +buf.duration.toFixed(2)]);
        $('ag-voice-status').textContent = `Recorded ${buf.duration.toFixed(1)} s · sung pitch ≈ ${noteName(audio.voice.base)}`;
        drawWave();
      } catch (e) { $('ag-voice-status').textContent = 'Could not read the recording: ' + e.message; }
    };
    recorder.start(); $('ag-rec').textContent = 'Stop'; $('ag-rec').classList.add('on');
    $('ag-voice-status').textContent = 'Recording… say or sing a word or a short phrase.';
  };
  $('ag-vplay').onclick = () => {
    if (!audio || !audio.voice.buffer) return;
    if (preview) { try { preview.stop(); } catch (e) {} preview = null; $('ag-vplay').textContent = 'Play'; return; }
    const [off, len] = audio.trimmed(), src = audio.ctx.createBufferSource();
    src.buffer = audio.voice.buffer; src.loop = settings.voice.loop; src.loopStart = off; src.loopEnd = off + len;
    src.connect(audio.bus.voice); src.start(0, off, settings.voice.loop ? undefined : len);
    src.onended = () => { preview = null; $('ag-vplay').textContent = 'Play'; src.disconnect(); };
    preview = src; $('ag-vplay').textContent = 'Stop';
  };
  $('ag-vclear').onclick = () => { if (audio) audio.setVoice(null); log.push([score.step, 'voice.cleared', 1]); drawWave(); $('ag-voice-status').textContent = 'No recording: the voice sampler sings a vowel.'; };
  $('ag-loop').onchange = () => change('voice.loop', $('ag-loop').checked);
  for (const [id, k] of [['ag-trim0', 0], ['ag-trim1', 1]]) $(id).addEventListener('input', () => {
    const t = [+$('ag-trim0').value, +$('ag-trim1').value]; if (t[1] - t[0] < 0.02) return;
    change('voice.trim', t); drawWave();
  });
  function drawWave() {
    const c = $('ag-wave'), g = c.getContext('2d'), r = c.getBoundingClientRect();
    c.width = Math.round(r.width * DPR); c.height = Math.round(r.height * DPR); g.setTransform(DPR, 0, 0, DPR, 0, 0);
    g.clearRect(0, 0, r.width, r.height);
    const b = audio && audio.voice.buffer;
    if (!b) { g.fillStyle = 'rgba(190,201,195,.4)'; g.font = '12px "IBM Plex Sans"'; g.fillText('no recording yet', 10, r.height / 2 + 4); return; }
    const d = b.getChannelData(0), n = Math.floor(r.width), t = settings.voice.trim;
    for (let i = 0; i < n; i++) {
      let mx = 0; const a = Math.floor(i / n * d.length), z = Math.floor((i + 1) / n * d.length);
      for (let j = a; j < z; j += 4) mx = Math.max(mx, Math.abs(d[j]));
      const inside = i / n >= t[0] && i / n <= t[1];
      g.fillStyle = inside ? '#7dd8b5' : 'rgba(125,216,181,.25)';
      g.fillRect(i, r.height / 2 - mx * r.height * 0.48, 1, Math.max(1, mx * r.height * 0.96));
    }
  }
  const noteName = m => ['C', 'C♯', 'D', 'E♭', 'E', 'F', 'F♯', 'G', 'A♭', 'A', 'B♭', 'B'][((Math.round(m) % 12) + 12) % 12] + (Math.floor(Math.round(m) / 12) - 1);

  // ── exports ───────────────────────────────────────────────────────────
  const download = (blob, name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); };
  const stamp = () => new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-');
  const pickType = (kinds) => kinds.find(k => window.MediaRecorder && MediaRecorder.isTypeSupported(k)) || '';
  let audioRec = null, videoRec = null, vcv = null, vcx = null;
  $('ag-rec-audio').onclick = () => {
    if (audioRec) { audioRec.stop(); return; }
    ensureAudio();
    const type = pickType(['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus']), parts = [];
    audioRec = new MediaRecorder(audio.rec.stream, type ? { mimeType: type, audioBitsPerSecond: 256000 } : undefined);
    audioRec.ondataavailable = e => parts.push(e.data);
    audioRec.onstop = () => { download(new Blob(parts, { type: audioRec.mimeType }), `algo-${settings.seed}-${stamp()}.${audioRec.mimeType.includes('mp4') ? 'm4a' : 'webm'}`); audioRec = null; $('ag-rec-audio').textContent = 'Record audio'; $('ag-rec-audio').classList.remove('on'); };
    audioRec.start(1000); $('ag-rec-audio').textContent = 'Stop and save audio'; $('ag-rec-audio').classList.add('on');
    if (!playing) play();
  };
  function composite() {                       // the picture, letterboxed into a 16:9 frame for the video
    vcx.fillStyle = '#07090c'; vcx.fillRect(0, 0, 1280, 720);
    const s = Math.min(1280 / cv.width, 720 / cv.height), w = cv.width * s, h = cv.height * s;
    vcx.drawImage(cv, (1280 - w) / 2, (720 - h) / 2, w, h);
  }
  $('ag-rec-video').onclick = () => {
    if (videoRec) { videoRec.stop(); return; }
    ensureAudio();
    if (!vcv) { vcv = document.createElement('canvas'); vcv.width = 1280; vcv.height = 720; vcx = vcv.getContext('2d'); }
    if (!vcv.captureStream) { $('ag-status').textContent = 'This browser cannot record video from a canvas.'; return; }
    const stream = vcv.captureStream(30); audio.rec.stream.getAudioTracks().forEach(t => stream.addTrack(t));
    const type = pickType(['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4']), parts = [];
    const rec = new MediaRecorder(stream, type ? { mimeType: type, videoBitsPerSecond: 6e6 } : undefined);
    rec.ondataavailable = e => parts.push(e.data);
    rec.onstop = () => { download(new Blob(parts, { type: rec.mimeType }), `algo-${settings.seed}-${stamp()}.${rec.mimeType.includes('mp4') ? 'mp4' : 'webm'}`); videoRec = null; $('ag-rec-video').textContent = 'Record video'; $('ag-rec-video').classList.remove('on'); };
    composite(); rec.start(1000); videoRec = rec; $('ag-rec-video').textContent = 'Stop and save video'; $('ag-rec-video').classList.add('on');
    if (!playing) play();
  };
  $('ag-midi').onclick = () => {
    if (!noteLog.length) { $('ag-status').textContent = 'Nothing has played yet.'; return; }
    const base = noteLog[0][0];
    download(new Blob([G.midiFile(noteLog.map(e => [e[0] - base, ...e.slice(1)]), tempoLog.map(([s, b]) => [Math.max(0, s - base), b]))], { type: 'audio/midi' }), `algo-${settings.seed}-${stamp()}.mid`);
  };
  // a session: the seed, the controls at the start, every change by step, the voice sample, and the numbers so far
  $('ag-save').onclick = () => {
    const sess = { app: 'oedio-algo', version: 1, saved: new Date().toISOString(), seed: settings.seed, start: start0 || settings,
      duration: settings.duration, log: log.slice(), steps: score.step, numbers: score.nums.history.map(h => h[1]).join(''),
      mutations: score.nums.mutations, voice: null };
    if (audio && audio.voice.buffer) {
      const bytes = G.wavBytes(audio.voice.buffer); let bin = ''; for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
      sess.voice = { wav: btoa(bin), base: audio.voice.base };
    }
    download(new Blob([JSON.stringify(sess)], { type: 'application/json' }), `algo-session-${settings.seed}-${stamp()}.json`);
  };
  $('ag-load').onclick = () => $('ag-file').click();
  $('ag-file').onchange = async () => {
    const f = $('ag-file').files[0]; if (!f) return;
    let sess; try { sess = JSON.parse(await f.text()); } catch (e) { $('ag-status').textContent = 'That file is not an Algo session.'; return; }
    if (sess.app !== 'oedio-algo') { $('ag-status').textContent = 'That file is not an Algo session.'; return; }
    loadSession(sess);
  };
  function loadSession(sess) {
    settings.seed = sess.seed; $('ag-seed').value = sess.seed;
    const st = sess.start || {};
    Object.assign(settings, { complexity: st.complexity ?? 55, tempo: st.tempo ?? 112, lead: st.lead ?? 0, master: st.master ?? 0.8 });
    Object.assign(settings.vol, st.vol || {}); Object.assign(settings.voice, st.voice || {});
    settings.duration = sess.duration || 0; $('ag-duration').value = String(settings.duration);
    cxDial.set(settings.complexity); instDial.set(settings.lead); $('ag-tempo').value = settings.tempo; $('ag-tempo-out').textContent = settings.tempo;
    $('ag-master').value = settings.master; for (const n of INST) $('ag-vol-' + n).value = settings.vol[n];
    if (sess.voice && sess.voice.wav) {
      const bin = atob(sess.voice.wav), bytes = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const decode = ctx => { ctx.decodeAudioData(bytes.buffer.slice(0)).then(b => { audio.setVoice(b); drawWave(); }); return null; };
      if (audio) decode(audio.ctx); else pendingVoice = decode;
    }
    replay = new Map();
    for (const [s, k, v] of sess.log || []) { if (!replay.has(s)) replay.set(s, []); replay.get(s).push([s, k, v]); }
    $('ag-replay').hidden = false; $('ag-replay').textContent = `Replaying a session: seed ${sess.seed}, ${sess.log.length} control changes`;
    restart(true);
    if (audio) { audio.setLead(settings.lead); for (const n of INST) audio.bus[n].gain.value = settings.vol[n]; }
  }
  // Web MIDI: send the score to a synthesizer or a DAW
  $('ag-midi-connect').onclick = async () => {
    if (!navigator.requestMIDIAccess) { $('ag-status').textContent = 'This browser has no Web MIDI.'; return; }
    try {
      const acc = await navigator.requestMIDIAccess(), sel = $('ag-midi-out'); sel.innerHTML = '<option value="">MIDI out: off</option>';
      for (const o of acc.outputs.values()) { const op = document.createElement('option'); op.value = o.id; op.textContent = o.name; sel.appendChild(op); }
      sel.hidden = false; sel.onchange = () => { midiOut = sel.value ? acc.outputs.get(sel.value) : null; };
      $('ag-status').textContent = acc.outputs.size ? 'Choose a MIDI output.' : 'No MIDI outputs found.';
    } catch (e) { $('ag-status').textContent = 'MIDI access was refused.'; }
  };
  document.addEventListener('keydown', e => { if (e.code === 'Space' && e.target === document.body) { e.preventDefault(); playing ? pause() : play(); } });

  drawWave(); requestAnimationFrame(draw);
  window.AlgoPlayer = { get score() { return score; }, get audio() { return audio; }, get log() { return log; }, noteLog, timeline, change, play, pause, restart, loadSession };
})();
