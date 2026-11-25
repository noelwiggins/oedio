/* Sound on iPhone and iPad.
   · iOS mutes web audio when the ring/silent switch is on. Declaring the page a "playback" session (iOS 17+), and on older
     iOS starting a silent looping <audio> element inside the tap, moves the page into the media category, which plays
     regardless of the switch, as music apps do.
   · iOS also suspends ("interrupts") audio when Safari goes to the background; it is resumed on return and on the next tap.
   · Safari on iPhone gives a page far less memory than a desktop browser, and decoded recordings are large (a second of
     44.1 kHz stereo is 350 KB). On iOS the recordings are therefore decoded at 32 kHz, folded to mono and cut to the
     length the players actually use (long notes loop their steady middle), and the largest optional sets are thinned. */
(function () {
  'use strict';
  const ua = navigator.userAgent || '';
  const iOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const light = iOS || /[?&]light=1/.test(location.search);
  // how much of each recording to keep in light mode, by folder
  const KEEP = [[/^piano\//, 5], [/^choir\//, 3.5], [/^(violin2|cello2)\//, 3.5], [/^organ\//, 4], [/^bass\//, 3], [/^drums\/(gong|cym)/, 5], [/^drums\//, 3], [/^ens\//, 3.5], [/^proc\/clap/, 0.8], [/^proc\//, 3]];
  let silent = null;
  function silentLoop() {
    // 0.5 s of silence as a WAV data URI
    const sr = 8000, n = sr / 2, b = new Uint8Array(44 + n), v = new DataView(b.buffer);
    const w = (o, s) => [...s].forEach((c, i) => b[o + i] = c.charCodeAt(0));
    w(0, 'RIFF'); v.setUint32(4, 36 + n, true); w(8, 'WAVEfmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, sr, true); v.setUint32(28, sr, true); v.setUint16(32, 1, true); v.setUint16(34, 8, true); w(36, 'data'); v.setUint32(40, n, true); b.fill(128, 44);
    let s = ''; b.forEach(x => s += String.fromCharCode(x));
    const a = document.createElement('audio'); a.src = 'data:audio/wav;base64,' + btoa(s); a.loop = true; a.setAttribute('playsinline', ''); a.preload = 'auto';
    return a;
  }
  const watched = new Set();
  window.OedioAudio = {
    iOS, light,
    // the options for new AudioContext(...)
    options() { return light ? { latencyHint: 'playback', sampleRate: 32000 } : { latencyHint: 'playback' }; },
    // call inside the tap that starts the sound
    unlock(ctx) {
      try { if (navigator.audioSession) navigator.audioSession.type = 'playback'; } catch (e) {}
      if (iOS) { try { if (!silent) silent = silentLoop(); if (!navigator.audioSession) silent.play().catch(() => {}); } catch (e) {} }
      try { ctx.resume(); } catch (e) {}
      if (!watched.has(ctx)) {
        watched.add(ctx);
        const wake = () => {
          if (iOS && silent && silent.paused) silent.play().catch(() => {});
          if (ctx.state !== 'running' && ctx.state !== 'closed') ctx.resume().catch(() => {});
        };
        document.addEventListener('visibilitychange', () => { if (!document.hidden) wake(); });
        ['touchend', 'pointerup', 'keydown'].forEach(ev => document.addEventListener(ev, wake, { passive: true }));
        ctx.addEventListener && ctx.addEventListener('statechange', () => { if (ctx.state === 'interrupted' && !document.hidden) setTimeout(wake, 300); });
      }
    },
    // after decoding: in light mode, fold to mono and keep only what is used
    shrink(ctx, buf, file) {
      if (!light || !buf) return buf;
      const rule = KEEP.find(([re]) => re.test(file)), sec = rule ? rule[1] : 4;
      const len = Math.min(buf.length, Math.round(sec * buf.sampleRate));
      if (buf.numberOfChannels === 1 && len === buf.length) return buf;
      const out = ctx.createBuffer(1, len, buf.sampleRate), d = out.getChannelData(0), C = buf.numberOfChannels;
      for (let c = 0; c < C; c++) { const s = buf.getChannelData(c); for (let i = 0; i < len; i++) d[i] += s[i] / C; }
      const f = Math.min(len, Math.round(0.06 * buf.sampleRate));            // no click if a note runs to the end
      if (len < buf.length) for (let i = 0; i < f; i++) d[len - 1 - i] *= i / f;
      return out;
    },
  };
})();
