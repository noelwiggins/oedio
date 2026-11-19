/* Algogenesis — smooth motion from irregular frames.

   The server sends a frame every 0.8–1.5 s, and a frame can carry anything from 9 to 30 world steps of movement. Gliding
   from one frame to the next in a fixed time made creatures surge on a 30-step frame, crawl on a 9-step one, and stop
   dead when a frame was late. Instead, positions are kept against the world's own clock (its step counter): every
   creature remembers its last few frames by step, the panel plays the world back about 2.6 s behind the newest frame
   at a steady estimate of the server's step rate, and positions between frames follow a smooth curve (cubic Hermite,
   tangents from the neighbouring frames), so speed and direction change without corners.

   AlgoMotion.clock()            -> a clock; .feed(tick, now) on each new frame, .at(now) -> the step to draw
   AlgoMotion.push(o, tick, x, y, h) remember a frame for an object (h, a heading, optional)
   AlgoMotion.at(o, step)        -> { x, y, h, moving } (moving in world units per second) */
(function () {
  'use strict';
  const KEEP = 8, LEAD = 2.6;                 // frames remembered; seconds of playback delay
  function clock() {
    // where is the server's step counter now, and how fast does it run? a straight line fitted through the last
    // twenty frames (step against arrival time) answers both, and shrugs off any one early or late frame
    const c = { rate: 20, tick: null, pts: [], a: 0, b: 0, rt: null, last: 0 };
    c.feed = (tick, now) => {
      if (c.tick != null && tick < c.tick - 5000) { c.pts = []; c.rt = null; }
      if (c.tick != null && tick <= c.tick) return;
      c.tick = tick; c.pts.push([now / 1000, tick]); if (c.pts.length > 20) c.pts.shift();
      const n = c.pts.length;
      if (n >= 3) {
        let mx = 0, my = 0; for (const [x, y] of c.pts) { mx += x; my += y; } mx /= n; my /= n;
        let sxy = 0, sxx = 0; for (const [x, y] of c.pts) { sxy += (x - mx) * (y - my); sxx += (x - mx) * (x - mx); }
        if (sxx > 0) c.rate = Math.max(0.5, Math.min(2000, sxy / sxx));
        c.a = my - c.rate * mx;
      } else { c.a = tick - c.rate * now / 1000; }
    };
    c.at = now => {
      if (c.tick == null) return 0;
      const target = c.a + c.rate * (now / 1000 - LEAD);
      if (c.rt == null || Math.abs(target - c.rt) > c.rate * 6) { c.rt = target; c.last = now; return c.rt; }
      const dt = Math.max(0, Math.min(0.25, (now - c.last) / 1000));
      // run at the server's rate and drift gently toward the line: never backwards, never a jump
      c.rt += Math.max(0, c.rate * dt + (target - c.rt) * Math.min(1, dt * 0.4));
      c.last = now;
      return c.rt;
    };
    return c;
  }
  function push(o, tick, x, y, h) {
    const s = o._s || (o._s = []);
    const last = s[s.length - 1];
    if (last && tick <= last[0]) { if (tick === last[0]) { last[1] = x; last[2] = y; } return; }
    let hh = h || 0;
    if (last && h != null) { let d = hh - last[3]; d = ((d + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI; hh = last[3] + d; }
    s.push([tick, x, y, hh]);
    if (s.length > KEEP) s.shift();
  }
  function tan(s, i, k) {                     // slope of component k at frame i, from its neighbours (per step)
    const a = s[Math.max(0, i - 1)], b = s[Math.min(s.length - 1, i + 1)];
    return b[0] > a[0] ? (b[k] - a[k]) / (b[0] - a[0]) : 0;
  }
  function at(o, step, rate) {
    const s = o._s;
    if (!s || !s.length) return null;
    const r = { x: s[0][1], y: s[0][2], h: s[0][3], moving: 0 };
    if (s.length === 1 || step <= s[0][0]) return r;
    let i = s.length - 2;
    while (i > 0 && s[i][0] > step) i--;
    const p = s[i], q = s[i + 1];
    if (step >= q[0]) {                          // past the newest frame: coast briefly on the last velocity, then hold
      const over = Math.min(step - q[0], (q[0] - p[0]) * 0.5), vx = tan(s, s.length - 1, 1), vy = tan(s, s.length - 1, 2);
      return { x: q[1] + vx * over * 0.5, y: q[2] + vy * over * 0.5, h: q[3], moving: 0 };
    }
    const D = q[0] - p[0], f = (step - p[0]) / D;
    if (Math.hypot(q[1] - p[1], q[2] - p[2]) > 120) return { x: f < 0.5 ? p[1] : q[1], y: f < 0.5 ? p[2] : q[2], h: q[3], moving: 0 };
    const f2 = f * f, f3 = f2 * f, h00 = 2 * f3 - 3 * f2 + 1, h10 = f3 - 2 * f2 + f, h01 = -2 * f3 + 3 * f2, h11 = f3 - f2;
    const d00 = 6 * f2 - 6 * f, d10 = 3 * f2 - 4 * f + 1, d01 = -6 * f2 + 6 * f, d11 = 3 * f2 - 2 * f;
    const comp = k => {
      const m0 = tan(s, i, k) * D, m1 = tan(s, i + 1, k) * D;
      return [h00 * p[k] + h10 * m0 + h01 * q[k] + h11 * m1, (d00 * p[k] + d10 * m0 + d01 * q[k] + d11 * m1) / D];
    };
    const [x, vx] = comp(1), [y, vy] = comp(2), [h] = comp(3);
    r.x = x; r.y = y; r.h = h; r.moving = Math.hypot(vx, vy) * (rate || 20);
    return r;
  }
  window.AlgoMotion = { clock, push, at, LEAD };
})();
