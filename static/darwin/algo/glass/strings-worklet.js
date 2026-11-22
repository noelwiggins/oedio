/* AlgoGlass — a struck-string piano voice, physically modelled (extended Karplus–Strong).

   Each note is three strings, slightly out of tune with one another. Each string is a delay line one period long,
   with a fractional-delay allpass for exact tuning, two dispersion allpasses that make the upper partials run sharp
   the way a stiff steel string's do, and a loss filter that takes the treble away faster than the bass. The hammer
   is a short, soft burst whose brightness follows how hard the key was struck. When the damper falls the losses rise
   and the string falls silent. Because the sound comes from a vibrating model rather than fixed waveforms, every note
   is slightly different and decays the way a string does, which is most of what makes it sound acoustic.

   processorOptions: { f, vel, start (frame), ring (seconds before the damper), t60 (seconds), seed } */
class StruckString extends AudioWorkletProcessor {
  constructor(opt) {
    super();
    const o = opt.processorOptions, sr = sampleRate;
    this.start = o.start; this.damp = o.start + Math.floor(o.ring * sr); this.end = this.damp + Math.floor(0.6 * sr);
    let seed = (o.seed * 2654435761) >>> 0;
    const rnd = () => { seed ^= seed << 13; seed >>>= 0; seed ^= seed >>> 17; seed ^= seed << 5; seed >>>= 0; return seed / 4294967296; };
    const f0 = o.f, vel = o.vel;
    // stiffness: more for the short, thick bass strings' upper partials and for the very top
    const disp = Math.max(-0.75, Math.min(-0.05, -0.5 + 0.004 * (Math.log2(f0 / 27.5) * 12)));
    this.strings = [-1.7, 0.15, 1.9].map((cents, si) => {
      const f = f0 * Math.pow(2, (cents + (rnd() - 0.5) * 0.9) / 1200);
      const dispDelay = 2 * (1 - disp) / (1 + disp);                        // the dispersion allpasses' delay at low frequency
      const total = sr / f - dispDelay - 0.5;                               // 0.5 for the loss filter
      const N = Math.max(2, Math.floor(total)), frac = total - N;
      const ap = (1 - frac) / (1 + frac);                                   // tuning allpass coefficient
      const buf = new Float32Array(N + 1);
      // the hammer: a soft, low-passed burst, brighter for harder blows, shaped by a raised cosine
      let lp = 0; const k = 0.25 + 0.6 * (1 - vel);                         // smoothing: softer blows are darker
      const width = Math.max(2, Math.floor(N * (0.5 + 0.4 * (1 - vel))));
      for (let i = 0; i < width; i++) { lp = lp * k + (rnd() * 2 - 1) * (1 - k); buf[i] = lp * 0.5 * (1 - Math.cos(2 * Math.PI * i / width)); }
      let mean = 0; for (let i = 0; i < N; i++) mean += buf[i]; mean /= N; for (let i = 0; i < N; i++) buf[i] -= mean;   // no DC
      // losses per round trip, from the decay time; the loss filter darkens the tone as it rings
      const g = Math.pow(10, -3 / (o.t60 * f));
      const bright = Math.max(0.05, Math.min(0.5, 0.18 + 0.3 * (1 - vel) + 0.12 * Math.log2(f0 / 220)));
      return { buf, N, i: 0, ap, apX: 0, apY: 0, d1x: 0, d1y: 0, d2x: 0, d2y: 0, disp, g, b: bright, lpY: 0, gain: si === 1 ? 0.4 : 0.3 };
    });
    // the string's energy passes slowly between the three strings (two-stage decay)
    this.couple = 0.0025;
  }
  process(inputs, outputs) {
    const out = outputs[0][0], n = out.length, f0 = currentFrame;
    if (f0 + n < this.start) { out.fill(0); return true; }
    if (f0 > this.end) return false;
    const S = this.strings;
    for (let k = 0; k < n; k++) {
      const fr = f0 + k;
      if (fr < this.start) { out[k] = 0; continue; }
      const damping = fr > this.damp ? 0.9965 : 1;
      let sum = 0, mix = 0;
      for (const s of S) mix += s.lpY;
      mix /= S.length;
      for (const s of S) {
        const x = s.buf[s.i];
        // loss filter (one-pole lowpass) and round-trip gain, with a little energy shared between the strings
        s.lpY = (1 - s.b) * x + s.b * s.lpY;
        let y = (s.lpY * (1 - this.couple) + mix * this.couple) * s.g * damping;
        // dispersion: two first-order allpasses
        let d = s.disp * y + s.d1x - s.disp * s.d1y; s.d1x = y; s.d1y = d; y = d;
        d = s.disp * y + s.d2x - s.disp * s.d2y; s.d2x = y; s.d2y = d; y = d;
        // fractional tuning allpass
        d = s.ap * y + s.apX - s.ap * s.apY; s.apX = y; s.apY = d;
        s.buf[s.i] = d;
        s.i = s.i + 1 >= s.N ? 0 : s.i + 1;
        sum += x * s.gain;
      }
      out[k] = sum;
    }
    return true;
  }
}
registerProcessor('struck-string', StruckString);
