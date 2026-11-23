/* AlgoGlass — the player: one scheduler feeding the audio engine and the picture from the same events, the controls, the
   voice recorder, and the exports. The score is in engine.js (window.Glass). */
(function () {
  'use strict';
  const G = window.Glass, $ = id => document.getElementById(id), TAU = Math.PI * 2;
  const INST = G.LEAD, LABEL = { piano: 'Piano', organ: 'Organ', violin: 'Violin', voice: 'Choir', cello: 'Cello', bass: 'Bass' };

  // ── state ─────────────────────────────────────────────────────────────
  let audio = null, score = new G.Score(1976), playing = false, timer = null, nextT = 0, startT = 0;
  let log = [], pending = [], replay = null;      // log: [step, key, value]; replay: a loaded session's log, by step
  const timeline = [];                            // [audio time, step, result] for the picture (recent)
  const noteLog = [];                             // [step, instrument, midi, length, velocity] for MIDI export
  const tempoLog = [[0, 112]];
  const settings = { seed: 1976, complexity: 55, tempo: 112, lead: 0, master: 0.8, duration: 0,
    vol: { piano: 0.8, organ: 0.7, violin: 0.75, voice: 0.8, bass: 0.75, drums: 0.7, cello: 0.75 }, oct: { piano: 0, organ: 0, violin: 0, voice: 0, bass: 0, drums: 0, cello: 0 },
    period: 1, rhythm: 'euclid', triplets: true, knees: true, drums: true, cello: true, ens: null, harmony: 'glass', text: 'choir', preset: 'chamber', engineer: false, picture: 'score', counting: true, intermission: 0, concert: false,
    voice: { mode: 'harmonizer', clarity: 0.6, wet: 0.45, reverb: 0.35, layers: 2, speed: 1, reps: 1, loop: false, trim: [0, 1] } };
  score.ctl.drums = settings.drums; score.ctl.text = settings.text; score.ctl.cello = settings.cello;              // a new page plays the percussion; the Score's own default stays off for old sessions
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
    else if (['period', 'rhythm', 'triplets', 'knees', 'drums', 'cello', 'ens', 'harmony', 'text', 'intermission'].includes(k[0])) {
      settings[k[0]] = value; score.ctl[k[0]] = value;
      if (k[0] === 'ens' || k[0] === 'cello') showEns();
      if (k[0] === 'text' && audio) audio.text = value;
    }
    else if (k[0] === 'preset') { settings.preset = value; relabel(); if (audio) { audio.preset = value; if (value === 'ensemble') audio.loadEnsemble(); } }
    else if (k[0] === 'engineer') { settings.engineer = value; if (audio) { audio.engineer = value; if (score.chord) audio.rideMix(score.chord, at || audio.ctx.currentTime); } }
    else if (k[0] === 'picture' || k[0] === 'counting') { settings[k[0]] = value; }
    else if (k[0] === 'oct') { settings.oct[k[1]] = value; if (audio) audio.oct[k[1]] = value; }
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
      const d = stepDur();
      if (r.newChord) {
        audio.currentChord = r.chord.v; audio.rideMix(r.chord, nextT);
        // in the time-lapse picture, a low chanted voice enters on the slow chords
        const C = r.chord;
        if (settings.picture === 'timelapse' && !C.knee && (C.mi === 2 || C.mi === 4 || C.sil.sustain)) {
          let m = C.v[0] - 24; while (m < 43) m += 12;                       // the choir's basses, low
          audio.choirNote(m, C.len * d * 0.9, 0.5, nextT, 'B:' + (C.mi === 4 ? 'oh' : 'ah'));
        }
      }
      for (const [inst, midi, len, vel, part, off, syl] of r.notes) {
        audio.play(inst, midi, len * d, vel, nextT + (off || 0) * d, syl, part);
        const name = inst === 'lead' ? INST[settings.lead] : inst;
        let om = midi + 12 * (settings.oct[name] || 0); while (om < 24) om += 12; while (om > 108) om -= 12;
        noteLog.push([step + (off || 0), name, om, len, vel]); if (noteLog.length > 200000) noteLog.splice(0, 50000);
        if (midiOut) sendMidi(name, om, len * d, vel, nextT + (off || 0) * d);
      }
      timeline.push([nextT, step, r]); if (timeline.length > 3000) timeline.splice(0, 1000);
      nextT += d;
    }
  }
  function sendMidi(name, midi, dur, vel, t) {
    const ch = G.MIDI_CH(name), at = performance.now() + (t - audio.ctx.currentTime) * 1000;
    try { midiOut.send([0x90 | ch, midi, Math.round(vel * 127)], at); midiOut.send([0x80 | ch, midi, 0], at + dur * 1000); } catch (e) {}
  }
  function ensureAudio() {
    if (audio) return;
    audio = new G.Audio();
    for (const [k, v] of Object.entries(settings.vol)) if (audio.bus[k]) audio.bus[k].gain.value = v;
    audio.out.gain.value = settings.master; audio.setLead(settings.lead); Object.assign(audio.oct, settings.oct);
    audio.preset = settings.preset; audio.engineer = settings.engineer; audio.text = settings.text;
    // say which recordings are still on their way; every instrument waits silently for its own
    audio.onload = L => {
      const names = { piano: 'piano', organ: 'organ', violin2: 'violin', cello: 'cello', bass: 'double bass', drums: 'percussion' };
      const wait = L.want.filter(k => !L.done.includes(k)).map(k => names[k]);
      if (!audio.samples.choir) wait.push('choir');
      if (settings.preset === 'ensemble' && !audio.samples.ens) wait.push('ensemble');
      const el = $('ag-loadstat'); if (el) el.textContent = wait.length ? 'Loading recordings: ' + wait.join(', ') + '…' : '';
    };
    audio.onload({ want: ['piano', 'organ', 'violin2', 'cello', 'bass', 'drums'], done: [] });
    if (settings.text === 'choir') audio.loadChoir();
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
    for (const k of ['period', 'rhythm', 'triplets', 'knees', 'drums', 'cello', 'ens', 'harmony', 'text', 'intermission']) score.ctl[k] = settings[k];
    log = []; pending = []; timeline.length = 0; noteLog.length = 0; tempoLog.length = 0; tempoLog.push([0, settings.tempo]);
    if (!keepReplay) { replay = null; $('ag-replay').hidden = true; }
    start0 = snapshot();
    $('ag-status').textContent = '';
    if (was || keepReplay) play();
  }
  let start0 = null;
  const snapshot = () => ({ complexity: settings.complexity, tempo: settings.tempo, lead: settings.lead, master: settings.master, vol: { ...settings.vol }, oct: { ...settings.oct },
    period: settings.period, rhythm: settings.rhythm, triplets: settings.triplets, knees: settings.knees, drums: settings.drums, cello: settings.cello, ens: settings.ens, harmony: settings.harmony, text: settings.text, preset: settings.preset,
    engineer: settings.engineer, picture: settings.picture, counting: settings.counting, intermission: settings.intermission, voice: { ...settings.voice, trim: settings.voice.trim.slice() } });

  // ── the picture: the same events, drawn as they sound ──────────────────
  const cv = $('ag-canvas'), cx = cv.getContext('2d');
  let W = 0, H = 0, DPR = 1;
  function fit() {
    const r = cv.getBoundingClientRect(); DPR = Math.min(2, window.devicePixelRatio || 1);
    W = Math.max(320, r.width); H = Math.max(180, r.height);
    cv.width = Math.round(W * DPR); cv.height = Math.round(H * DPR);
  }
  new ResizeObserver(fit).observe(cv); fit();
  const LANE = { piano: 0.2, violin: 0.32, voice: 0.68, organ: 0.8, bass: 0.88, drums: 0.92, timpani: 0.9, cello: 0.84 };
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
    if (settings.picture === 'stage') drawStage(c, t, now, cur, still);
    else if (settings.picture === 'dance') drawDance(c, t, now, cur, still);
    else if (settings.picture === 'timelapse') drawLapse(c, t, now, cur, still);
    else drawScore(c, t, now, cur, still, SPAN, px, playX, xOf);
    if (settings.counting && cur && !cur.intermission) drawCount(c, cur);
    if (cur && cur.intermission) { c.fillStyle = 'rgba(220,225,235,0.35)'; c.font = '13px "IBM Plex Sans", sans-serif'; c.textAlign = 'center'; if (!settings.concert) c.fillText('intermission', W / 2, H * 0.5 - 12); c.textAlign = 'left'; }
    // a quiet caption
    if (cur && cur.chord && !settings.concert) {
      const C = cur.chord;
      c.fillStyle = 'rgba(220,225,235,0.55)'; c.font = '12px "IBM Plex Mono", monospace';
      c.fillText(`${C.knee ? 'knee play' : G.MOVEMENTS[C.mi].name}   ${G.CHORDS[C.ci].name}   N=${C.N}   phrase ${C.L}${C.trip ? '   3 against 2: ' + C.trip : ''}   ${C.sil.restBeats && cur.resting ? 'silence' : C.sil.sustain ? 'held' : ''}`, 14, H - 14);
    }
    if (videoRec) composite();
    panel(cur);
  }
  function drawScore(c, t, now, cur, still, SPAN, px, playX, xOf) {
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
      if (xOf(s) < -10 || xOf(s) > W + 10) continue;
      const C = r.chord, col = G.CHORDS[C.ci].colour;
      for (const [inst, midi, len, vel, part, off] of r.notes) {
        const name = inst === 'lead' ? INST[settings.lead] : inst, y = H * LANE[name] + (inst === 'lead' ? -10 : 0) + (60 - midi) * 0.6 + (part === 'triplet' ? 6 : 0);
        const w = Math.max(2, len * px), x = xOf(s + (off || 0));
        const dt = t - (tt + (off || 0) * stepDur());
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
  }

  // ── recent sounds, shared by the picture modes: [audio time, instrument, midi, velocity, chord colour] ──
  function recent(t, secs) {
    const out = [];
    for (let i = timeline.length - 1; i >= 0; i--) {
      const [tt, , r] = timeline[i]; if (tt < t - secs) break; if (tt > t + 0.05) continue;
      for (const [inst, midi, , vel, part, off] of r.notes) out.push([tt + (off || 0) * stepDur(), inst === 'lead' ? INST[settings.lead] : inst, midi, vel, G.CHORDS[r.chord.ci].colour, part]);
    }
    return out;
  }
  const rgba = (hex, a) => `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${a})`;
  // Stage, after Robert Wilson's designs for Einstein on the Beach: a field, a building, a bar of light rising, figures
  // crossing slowly at the speed of their cycles, and in the fourth movement a train
  function drawStage(c, t, now, cur, still) {
    const C = cur && cur.chord, col = C ? G.CHORDS[C.ci].colour : '#5b8cff', hz = H * 0.62;
    const sky = c.createLinearGradient(0, 0, 0, hz); sky.addColorStop(0, '#05070b'); sky.addColorStop(1, rgba(col, 0.16 * (1 - 0.6 * still)));
    c.fillStyle = sky; c.fillRect(0, 0, W, hz);
    c.fillStyle = '#0b0d12'; c.fillRect(0, hz, W, H - hz);
    // the floor: lines running to one vanishing point, crossbars spaced by the piano's five
    c.strokeStyle = 'rgba(200,210,230,0.08)'; c.lineWidth = 1;
    for (let i = -12; i <= 12; i++) { c.beginPath(); c.moveTo(W / 2 + i * 6, hz); c.lineTo(W / 2 + i * W * 0.12, H); c.stroke(); }
    for (let i = 1; i < 9; i++) { const y = hz + (H - hz) * Math.pow(i / 9, 1.8); c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke(); }
    if (!C) return;
    // the bar of light: rises through each movement, brightening with every lead note
    const prog = Math.min(1, (C.cc % 12 + Math.max(0, now - C.start) / C.len) / 12);
    const lead = recent(t, 0.35).filter(e => e[5] === 'lead').length;
    const by = H * 0.9 - prog * H * 0.75, bw = W * 0.46;
    c.fillStyle = `rgba(245,240,225,${(0.35 + 0.25 * Math.min(1, lead)) * (1 - 0.7 * still)})`;
    c.shadowColor = 'rgba(255,250,230,0.8)'; c.shadowBlur = 18; c.fillRect(W / 2 - bw / 2, by, bw, 3); c.shadowBlur = 0;
    // the building: a tower whose storeys are the phrase's notes; its windows light as the instruments play
    const bx = W * 0.78, storeys = C.L, sh = H * 0.07, bwid = W * 0.08;
    c.fillStyle = '#101319'; c.fillRect(bx, hz - storeys * sh, bwid, storeys * sh);
    c.strokeStyle = 'rgba(200,210,230,0.15)'; c.strokeRect(bx, hz - storeys * sh, bwid, storeys * sh);
    const lit = recent(t, 0.6);
    for (let f = 0; f < storeys; f++) for (let w = 0; w < 4; w++) {
      const on = lit.some(e => (e[2] + w * 3 + f * 5) % 7 === 0);
      c.fillStyle = on ? rgba(col, 0.85) : 'rgba(200,210,230,0.06)'; c.fillRect(bx + 6 + w * (bwid - 12) / 4, hz - (f + 1) * sh + 8, (bwid - 12) / 4 - 4, sh - 16);
    }
    // figures crossing the field: one per sound, walking left to right from where they sounded, each instrument on its own plane
    const PLANE = { piano: 0.12, violin: 0.28, voice: 0.45, organ: 0.65, bass: 0.85, timpani: 0.92, drums: 0.97, cello: 0.76 };
    for (const [tt, name, midi, vel, ccol, part] of recent(t, 14)) {
      const age = t - tt, x = W * 0.06 + age * W * 0.06 + (midi % 12) * 4, depth = PLANE[name] ?? 0.5, y = hz + (H - hz) * depth, sc = 0.5 + depth;
      const a = Math.max(0, 1 - age / 14) * (1 - 0.6 * still);
      c.fillStyle = rgba(ccol, 0.75 * a); c.strokeStyle = rgba(ccol, 0.9 * a);
      if (name === 'piano') c.fillRect(x, y - 8 * sc, 6 * sc, 8 * sc);
      else if (name === 'violin') c.fillRect(x, y - 26 * sc, 2 * sc, 26 * sc);
      else if (name === 'organ') c.fillRect(x, y - 4 * sc, 40 * sc, 4 * sc);
      else if (name === 'bass') c.fillRect(x, y - 6 * sc, 26 * sc, 6 * sc);
      else if (name === 'drums') c.fillRect(x, y - 3 * sc, 3 * sc, 3 * sc);
      else if (name === 'cello') { c.beginPath(); c.ellipse(x, y - 8 * sc, 5 * sc, 9 * sc, 0, 0, TAU); c.fill(); }
      else if (name === 'timpani') { c.beginPath(); c.ellipse(x, y - 3 * sc, 9 * sc, 3 * sc, 0, 0, TAU); c.fill(); }
      else { c.beginPath(); c.arc(x, y - 12 * sc, 5 * sc, 0, TAU); c.fill(); c.fillRect(x - 1, y - 8 * sc, 2, 8 * sc); }
    }
    // the train, in the movement of rhythmic complexity
    if (C.mi === 3) {
      const u = ((now - C.start) / Math.max(1, C.len)) % 1, x = -W * 0.4 + u * W * 1.4, y = hz - H * 0.05;
      c.fillStyle = '#14171e'; c.fillRect(x, y, W * 0.35, H * 0.05); c.strokeStyle = 'rgba(200,210,230,0.25)'; c.strokeRect(x, y, W * 0.35, H * 0.05);
      for (let i = 0; i < 10; i++) { c.fillStyle = (i + Math.floor(now)) % 3 ? 'rgba(240,220,160,0.5)' : 'rgba(240,220,160,0.15)'; c.fillRect(x + 8 + i * W * 0.034, y + 6, W * 0.022, H * 0.018); }
    }
  }
  // Dance, after Lucinda Childs and Sol LeWitt (1979): dancers on a floor grid, each travelling a diagonal path in the
  // time of its own cycle, and the same dance projected larger and fainter over the top, as LeWitt's film was
  const dancers = {};
  function drawDance(c, t, now, cur, still) {
    const C = cur && cur.chord, gx = W * 0.12, gy = H * 0.12, gw = W * 0.76, gh = H * 0.76, n = 8;
    c.strokeStyle = 'rgba(200,210,230,0.08)'; c.lineWidth = 1;
    for (let i = 0; i <= n; i++) { c.beginPath(); c.moveTo(gx + gw * i / n, gy); c.lineTo(gx + gw * i / n, gy + gh); c.stroke(); c.beginPath(); c.moveTo(gx, gy + gh * i / n); c.lineTo(gx + gw, gy + gh * i / n); c.stroke(); }
    if (!C) return;
    const col = G.CHORDS[C.ci].colour, sounding = recent(t, 0.3);
    const playing = chosen(), parts = [...new Set([...C.layers.filter(n => playing.includes(n)), INST[settings.lead]])];   // only the instruments in the piece dance
    const CYC = { piano: 5, organ: 7, violin: 11, voice: C.voiceCycle, bass: 8, cello: 13 };
    const pos = (p, u) => {                              // a zigzag of diagonals across the floor, different for each dancer
      const k = G.PARTS.indexOf(p) + 1, pts = [[0, (k * 0.17) % 1], [1, ((k * 0.17) + 0.5) % 1], [0, ((k * 0.17) + 0.25) % 1], [1, ((k * 0.17) + 0.75) % 1]];
      const seg = u * pts.length, i = Math.floor(seg) % pts.length, f = seg - Math.floor(seg), a = pts[i], b = pts[(i + 1) % pts.length];
      return [gx + gw * (a[0] + (b[0] - a[0]) * f), gy + gh * (a[1] + (b[1] - a[1]) * f)];
    };
    const draw1 = (scale, alpha) => {
      for (const p of parts) {
        const u = ((now / (CYC[p] * 4)) + G.PARTS.indexOf(p) * 0.13) % 1;
        let [x, y] = pos(p, u);
        if (scale !== 1) { x = W / 2 + (x - W / 2) * scale; y = H / 2 + (y - H / 2) * scale; }
        const d = dancers[p] || (dancers[p] = []);
        if (scale === 1) { d.push([x, y]); if (d.length > 90) d.shift(); }
        const hit = sounding.some(e => e[1] === p), r = (hit ? 9 : 6) * scale;
        if (scale === 1 && d.length > 2) { c.strokeStyle = rgba(col, 0.25 * alpha * (1 - 0.6 * still)); c.beginPath(); d.forEach(([a, b], i) => c[i ? 'lineTo' : 'moveTo'](a, b)); c.stroke(); }
        c.fillStyle = rgba(col, alpha * (hit ? 1 : 0.7) * (1 - 0.6 * still)); c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill();
        if (hit) { c.strokeStyle = rgba(col, alpha * 0.6); c.beginPath(); c.arc(x, y, r * 2.2, 0, TAU); c.stroke(); }
      }
    };
    draw1(2.1, 0.14);                                   // the film, projected large over the stage
    draw1(1, 0.9);
  }
  // Time-lapse, after Godfrey Reggio's Koyaanisqatsi (1982): streams of light that race when the music is dense and
  // slow to a crawl when it thins, clouds rushing over a city whose windows answer the notes
  const lapse = { parts: [], clouds: [], last: 0, speed: 1 };
  function drawLapse(c, t, now, cur, still) {
    const C = cur && cur.chord, col = C ? G.CHORDS[C.ci].colour : '#5b8cff';
    const dens = recent(t, 2).length / 2;                  // notes a second
    lapse.speed += (0.3 + Math.min(4, dens / 3) * (1 - 0.8 * still) - lapse.speed) * 0.03;
    const dt = Math.min(0.05, Math.max(0, t - lapse.last)); lapse.last = t;
    const sky = c.createLinearGradient(0, 0, 0, H * 0.55); sky.addColorStop(0, '#04060a'); sky.addColorStop(1, rgba(col, 0.12)); c.fillStyle = sky; c.fillRect(0, 0, W, H * 0.55);
    if (lapse.clouds.length < 7) for (let i = 0; i < 7; i++) lapse.clouds.push({ x: Math.random() * W, y: H * (0.05 + Math.random() * 0.3), r: H * (0.08 + Math.random() * 0.1) });
    for (const k of lapse.clouds) {
      k.x += dt * lapse.speed * W * 0.04; if (k.x - k.r * 2 > W) k.x = -k.r * 2;
      const g = c.createRadialGradient(k.x, k.y, 0, k.x, k.y, k.r * 2); g.addColorStop(0, 'rgba(200,205,220,0.09)'); g.addColorStop(1, 'rgba(200,205,220,0)');
      c.fillStyle = g; c.fillRect(k.x - k.r * 2, k.y - k.r * 2, k.r * 4, k.r * 4);
    }
    // the city: towers, their windows lit by notes
    const base = H * 0.7;
    c.fillStyle = '#090b10'; c.fillRect(0, base, W, H - base);
    const notes = recent(t, 0.8);
    for (let i = 0; i < 18; i++) {
      const bw = W / 18, h = H * (0.1 + 0.25 * G.hash(i, 4)), x = i * bw;
      c.fillStyle = '#0d1016'; c.fillRect(x + 2, base - h, bw - 4, h);
      for (let wy = 0; wy < h / 10 - 1; wy++) for (let wx = 0; wx < 3; wx++) {
        const on = notes.some(e => (e[2] * 3 + i * 7 + wy * 5 + wx) % 47 === 0);
        if (on || G.hash(i, wy, wx) > 0.93) { c.fillStyle = on ? rgba(col, 0.9) : 'rgba(240,220,160,0.18)'; c.fillRect(x + 6 + wx * (bw - 12) / 3, base - h + 6 + wy * 10, (bw - 12) / 3 - 3, 4); }
      }
    }
    // the streams of traffic: white one way, red the other, faster as the music thickens
    if (lapse.parts.length < 360) for (let i = 0; i < 360; i++) lapse.parts.push({ lane: i % 6, x: Math.random() * W, v: 0.6 + Math.random() * 0.8 });
    for (const p of lapse.parts) {
      const dir = p.lane % 2 ? -1 : 1, y = base + (H - base) * (0.15 + p.lane * 0.13) + Math.sin((p.x / W) * 6 + p.lane) * 4;
      p.x += dir * dt * lapse.speed * p.v * W * 0.25; if (p.x > W + 20) p.x = -20; if (p.x < -20) p.x = W + 20;
      const len = 4 + lapse.speed * 10 * p.v;
      c.strokeStyle = dir > 0 ? 'rgba(255,245,225,0.55)' : 'rgba(255,90,70,0.55)'; c.lineWidth = 1.4;
      c.beginPath(); c.moveTo(p.x, y); c.lineTo(p.x - dir * len, y); c.stroke();
    }
    c.lineWidth = 1;
  }
  // counting, as the performers count: the repetitions of the phrase, or the knee play's beats, as one large numeral
  function drawCount(c, cur) {
    const n = cur.knee ? cur.count : cur.count % 100;
    if (!n && !cur.knee) return;
    c.save(); c.fillStyle = `rgba(230,232,240,${cur.knee ? 0.22 : 0.1})`; c.font = `300 ${Math.round(H * 0.28)}px "IBM Plex Sans", sans-serif`; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.fillText(String(n), W / 2, H * 0.5); c.restore();
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
  const instSteps = INST.map(n => LABEL[n]);
  const instDial = dial($('ag-inst'), { min: 0, max: INST.length - 1, value: 0, steps: instSteps, out: $('ag-inst-out'),
    onChange: v => { if (!chosen().includes(INST[v])) setInstrument(INST[v], true); change('lead', v); } });
  // ── which instruments play. null = the full ensemble (the original piece); otherwise the list the piece is arranged for.
  // The cello stays an optional extra of the full ensemble, as before, so switching it alone does not rearrange anything.
  const CORE = ['piano', 'organ', 'violin', 'voice', 'bass'];
  const chosen = () => settings.ens ? settings.ens.slice() : [...CORE, ...(settings.cello ? ['cello'] : [])];
  // the names follow the players: in the Glass Ensemble each part is played by the ensemble's own instruments
  const NAMES = {
    chamber: { piano: 'Piano', organ: 'Organ', violin: 'Violin', voice: 'Choir', cello: 'Cello', bass: 'Bass' },
    ensemble: { piano: 'Organ & sax', organ: 'Organ', violin: 'Sax & flute', voice: 'Sopranos', cello: 'Cello', bass: 'Electric bass' },
  };
  const MIXTAG = { piano: ' · 5', organ: ' · 7', violin: ' · 11', voice: '', cello: '', bass: '' };
  function relabel() {
    const N = NAMES[settings.preset] || NAMES.chamber;
    Object.assign(LABEL, N); INST.forEach((n, i) => { instSteps[i] = N[n]; });
    $('ag-inst').querySelectorAll('.det text').forEach((tx, i) => { tx.textContent = N[INST[i]]; });
    $('ag-inst-out').textContent = N[INST[settings.lead]];
    document.querySelectorAll('#ag-ens input[data-inst]').forEach(i => { i.nextSibling.textContent = N[i.dataset.inst]; });
    for (const n of Object.keys(N)) { const r = $('ag-vol-' + n); if (r && r.previousElementSibling) r.previousElementSibling.textContent = N[n] + (n === 'bass' && settings.preset !== 'ensemble' ? ' · ground' : MIXTAG[n]); }
    showEns();
  }
  function showEns() {
    const on = chosen();
    document.querySelectorAll('#ag-ens input[data-inst]').forEach(i => { i.checked = on.includes(i.dataset.inst); });
    $('ag-inst').querySelectorAll('.det').forEach((d, i) => d.classList.toggle('off', !on.includes(INST[i])));
    const names = on.map(n => LABEL[n]);
    $('ag-ens-note').textContent = !settings.ens ? 'All instruments. Switch any off and the piece is rearranged for the rest: their parts pass to the instruments still playing, written for them.'
      : on.length === 1 ? `A piece for ${names[0].toLowerCase()} alone: every part is rewritten for it.` : `A piece for ${names.slice(0, -1).join(', ').toLowerCase()} and ${names[names.length - 1].toLowerCase()}: the other parts are rewritten for them.`;
  }
  function setInstrument(inst, on) {
    let list = chosen().filter(n => n !== inst); if (on) list.push(inst);
    list = INST.filter(n => list.includes(n));
    if (!list.length) { showEns(); return; }                            // at least one instrument always plays
    if (inst === 'cello') change('cello', on);
    change('ens', CORE.every(n => list.includes(n)) ? null : list);
    if (!list.includes(INST[settings.lead])) { const v = INST.indexOf(list[0]); instDial.set(v); change('lead', v); }   // the line moves to one still playing
    settings.ens = CORE.every(n => list.includes(n)) ? null : list; if (inst === 'cello') settings.cello = on; showEns();
  }
  document.querySelectorAll('#ag-ens input[data-inst]').forEach(i => i.addEventListener('change', () => setInstrument(i.dataset.inst, i.checked)));
  const octDials = {};
  for (const n of G.PARTS) if ($('ag-oct-' + n)) octDials[n] = dial($('ag-oct-' + n), { min: 0, max: 4, value: 2, steps: ['−2', '−1', '0', '+1', '+2'], onChange: v => change('oct.' + n, v - 2) });
  const cxDial = dial($('ag-cx'), { min: 0, max: 100, value: 55, out: $('ag-cx-out'), onChange: v => change('complexity', Math.round(v)) });

  // ── sliders and buttons ───────────────────────────────────────────────
  const bind = (id, key, conv) => { const el = $(id); el.addEventListener('input', () => change(key, conv ? conv(el.value) : +el.value)); return el; };
  bind('ag-master', 'master');
  bind('ag-tempo', 'tempo').addEventListener('input', () => { $('ag-tempo-out').textContent = $('ag-tempo').value; });
  for (const n of G.PARTS) bind('ag-vol-' + n, 'vol.' + n);
  bind('ag-clarity', 'voice.clarity'); bind('ag-wet', 'voice.wet'); bind('ag-reverb', 'voice.reverb');
  bind('ag-layers', 'voice.layers'); bind('ag-speed', 'voice.speed'); bind('ag-reps', 'voice.reps');
  $('ag-speed').addEventListener('input', () => { $('ag-speed-out').textContent = (+$('ag-speed').value).toFixed(2) + '×'; });
  document.querySelectorAll('input[name=ag-mode]').forEach(r => r.addEventListener('change', () => change('voice.mode', r.value)));
  $('ag-play').onclick = () => (playing ? pause() : play());
  $('ag-restart').onclick = () => restart(!!replay);
  $('ag-seed-go').onclick = () => { const v = parseInt($('ag-seed').value, 10); if (Number.isFinite(v)) change('seed', v); };
  $('ag-duration').onchange = () => { settings.duration = +$('ag-duration').value; log.push([score.step, 'duration', settings.duration]); };
  $('ag-full').onclick = () => { const st = $('ag-stage'); (document.fullscreenElement ? document.exitFullscreen() : (st.requestFullscreen || st.webkitRequestFullscreen).call(st)); };
  // style: segmented buttons and switches, all logged like every other control
  function seg(name, key, conv) { document.querySelectorAll(`input[name=${name}]`).forEach(r => r.addEventListener('change', () => { if (r.checked) change(key, conv ? conv(r.value) : r.value); })); }
  seg('ag-period', 'period', Number); seg('ag-preset', 'preset'); seg('ag-picture', 'picture');
  for (const [id, key] of [['ag-triplets', 'triplets'], ['ag-knees', 'knees'], ['ag-drums', 'drums'], ['ag-engineer', 'engineer'], ['ag-counting', 'counting']]) $(id).addEventListener('change', () => change(key, $(id).checked));
  $('ag-additive').addEventListener('change', () => change('rhythm', $('ag-additive').checked ? 'additive' : 'euclid'));
  $('ag-text').addEventListener('change', () => { if ($('ag-text').value === 'choir' && audio) audio.loadChoir(); change('text', $('ag-text').value); });
  $('ag-harmony').addEventListener('change', () => change('harmony', $('ag-harmony').value));
  function syncStyleControls() {
    const set = (name, v) => document.querySelectorAll(`input[name=${name}]`).forEach(r => { r.checked = String(r.value) === String(v); });
    set('ag-period', settings.period); set('ag-preset', settings.preset); set('ag-picture', settings.picture);
    $('ag-triplets').checked = settings.triplets; $('ag-drums').checked = settings.drums; relabel(); $('ag-knees').checked = settings.knees; $('ag-engineer').checked = settings.engineer;
    $('ag-counting').checked = settings.counting; $('ag-additive').checked = settings.rhythm === 'additive'; $('ag-text').value = ['choir', 'recording'].includes(settings.text) ? settings.text : 'numbers';   // older sessions' solfège and vowel are the line too $('ag-harmony').value = settings.harmony;
  }
  // concert: four hours, an intermission after each full cycle, full screen, nothing on screen but the picture
  $('ag-concert').onclick = () => {
    settings.concert = true; settings.duration = 240; $('ag-duration').value = '240'; change('intermission', 2);
    const st = $('ag-stage'); (st.requestFullscreen || st.webkitRequestFullscreen).call(st);
    if (!playing) play();
  };
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && settings.concert) { settings.concert = false; change('intermission', 0); } });
  let idle = 0; $('ag-stage').addEventListener('mousemove', () => { $('ag-stage').classList.remove('hide-cursor'); clearTimeout(idle); idle = setTimeout(() => $('ag-stage').classList.add('hide-cursor'), 2500); });
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
        log.push([score.step, 'voice.recorded', +buf.duration.toFixed(2)]); change('text', 'recording'); syncStyleControls();
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
  $('ag-vclear').onclick = () => { if (audio) audio.setVoice(null); log.push([score.step, 'voice.cleared', 1]); drawWave(); $('ag-voice-status').textContent = 'No recording: the choir sings.'; };
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
    audioRec.onstop = () => { download(new Blob(parts, { type: audioRec.mimeType }), `algoglass-${settings.seed}-${stamp()}.${audioRec.mimeType.includes('mp4') ? 'm4a' : 'webm'}`); audioRec = null; $('ag-rec-audio').textContent = 'Record audio'; $('ag-rec-audio').classList.remove('on'); };
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
    rec.onstop = () => { download(new Blob(parts, { type: rec.mimeType }), `algoglass-${settings.seed}-${stamp()}.${rec.mimeType.includes('mp4') ? 'mp4' : 'webm'}`); videoRec = null; $('ag-rec-video').textContent = 'Record video'; $('ag-rec-video').classList.remove('on'); };
    composite(); rec.start(1000); videoRec = rec; $('ag-rec-video').textContent = 'Stop and save video'; $('ag-rec-video').classList.add('on');
    if (!playing) play();
  };
  $('ag-midi').onclick = () => {
    if (!noteLog.length) { $('ag-status').textContent = 'Nothing has played yet.'; return; }
    const base = noteLog[0][0];
    download(new Blob([G.midiFile(noteLog.map(e => [e[0] - base, ...e.slice(1)]), tempoLog.map(([s, b]) => [Math.max(0, s - base), b]))], { type: 'audio/midi' }), `algoglass-${settings.seed}-${stamp()}.mid`);
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
    download(new Blob([JSON.stringify(sess)], { type: 'application/json' }), `algoglass-session-${settings.seed}-${stamp()}.json`);
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
    Object.assign(settings.vol, st.vol || {}); Object.assign(settings.voice, st.voice || {}); Object.assign(settings.oct, st.oct || {});
    for (const k of ['period', 'rhythm', 'triplets', 'knees', 'text', 'preset', 'engineer', 'picture', 'counting', 'intermission']) if (st[k] !== undefined) settings[k] = st[k];
    settings.drums = st.drums ?? false; settings.harmony = st.harmony ?? 'glass'; settings.cello = st.cello ?? false; settings.ens = st.ens ?? null;          // sessions saved before the percussion existed replay without it
    syncStyleControls();
    for (const n of G.PARTS) if (octDials[n]) octDials[n].set((settings.oct[n] || 0) + 2);
    settings.duration = sess.duration || 0; $('ag-duration').value = String(settings.duration);
    cxDial.set(settings.complexity); instDial.set(settings.lead); $('ag-tempo').value = settings.tempo; $('ag-tempo-out').textContent = settings.tempo;
    $('ag-master').value = settings.master; for (const n of G.PARTS) $('ag-vol-' + n).value = settings.vol[n];
    if (sess.voice && sess.voice.wav) {
      const bin = atob(sess.voice.wav), bytes = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const decode = ctx => { ctx.decodeAudioData(bytes.buffer.slice(0)).then(b => { audio.setVoice(b); drawWave(); }); return null; };
      if (audio) decode(audio.ctx); else pendingVoice = decode;
    }
    replay = new Map();
    for (const [s, k, v] of sess.log || []) { if (!replay.has(s)) replay.set(s, []); replay.get(s).push([s, k, v]); }
    $('ag-replay').hidden = false; $('ag-replay').textContent = `Replaying a session: seed ${sess.seed}, ${sess.log.length} control changes`;
    restart(true);
    if (audio) { audio.setLead(settings.lead); for (const n of G.PARTS) audio.bus[n].gain.value = settings.vol[n]; Object.assign(audio.oct, settings.oct); audio.preset = settings.preset; audio.engineer = settings.engineer; audio.text = settings.text; if (settings.text === 'choir') audio.loadChoir(); }
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
