/* Algogenesis — zoom and pan for every panel.

   The world is drawn through one mapping (scale s, offset ox, oy). This keeps a zoom factor z and a centre (cx, cy)
   in world units, and turns the panel's fitted mapping into the zoomed one each frame:

     AlgoZoom.attach(canvas, { key, rect })   rect() -> the window in canvas pixels plus dpr
     AlgoZoom.view({ s, ox, oy, pf, w, h })   -> { s, ox, oy, z }  (the mapping to draw with this frame)
     AlgoZoom.isZoomed() · .pointers() · .reset() · .onSettle(fn)

   Gestures: pinch (two fingers) or trackpad pinch / ctrl-wheel / wheel to zoom about the point under the hand; one
   finger drags the view while zoomed in; double-tap zooms in to that spot, double-tap again comes back out;
   keys + − 0. At z = 1 a one-finger swipe still turns the panel over (lysis.js). Zoom eases toward its target, and
   is remembered per panel, so a viewer can leave the panel resting on a few flowers. Below z = 1 the whole world
   shows, uncropped by the bezel. */
(function () {
  'use strict';
  const ZMAX = 14;
  let z = 1, zt = 1, cx = null, cy = null, ct = null, last = null, key = null, rectFn = null;
  let zmin = 0.85, settleFns = [], settleTimer = 0, moving = false;
  const ptrs = new Map();
  let pinch = null, pan = null, tapAt = 0, tapX = 0, tapY = 0;

  function save() {
    try { localStorage.setItem(key, JSON.stringify({ z: zt, cx: ct ? ct[0] : cx, cy: ct ? ct[1] : cy })); } catch (e) {}
  }
  function settled() {
    clearTimeout(settleTimer);
    settleTimer = setTimeout(() => { moving = false; save(); settleFns.forEach(f => { try { f(); } catch (e) {} }); }, 260);
  }
  function touch() { moving = true; settled(); }

  // the fitted mapping (b) zoomed by z about the world centre (cx, cy), kept inside the world when zoomed in
  function view(b) {
    const fit = b.s, w = b.w, h = b.h, pf = b.pf;
    zmin = Math.min(1, Math.min(pf.w / w, pf.h / h) / fit);       // all of the world, uncropped
    if (cx == null) { cx = w / 2; cy = h / 2; }
    // ease toward the target (wheel steps and double-taps glide; a pinch sets the target every move)
    const now = performance.now(), dt = Math.min(100, now - (view.t || now)); view.t = now;
    const k = pinch ? 1 : 1 - Math.exp(-dt / 110);           // glide on elapsed time, the same on any device
    z += (zt - z) * k; if (Math.abs(zt - z) < 1e-4) z = zt;
    if (ct) { cx += (ct[0] - cx) * k; cy += (ct[1] - cy) * k; if (Math.hypot(ct[0] - cx, ct[1] - cy) < 0.01) { cx = ct[0]; cy = ct[1]; ct = null; } }
    const s = fit * z;
    // keep the window inside the world (when the world is larger than the window)
    const hw = pf.w / 2 / s, hh = pf.h / 2 / s;
    cx = w > 2 * hw ? Math.min(w - hw, Math.max(hw, cx)) : w / 2;
    cy = h > 2 * hh ? Math.min(h - hh, Math.max(hh, cy)) : h / 2;
    last = { s, ox: pf.x + pf.w / 2 - cx * s, oy: pf.y + pf.h / 2 - cy * s, z, fit, w, h, pf };
    return last;
  }
  // world point under a pointer, using the mapping drawn last
  function worldAt(px, py) { return last ? [(px - last.ox) / last.s, (py - last.oy) / last.s] : [0, 0]; }
  // zoom to zn keeping the world point under (px, py) where it is
  function zoomAbout(zn, px, py, glide) {
    if (!last) return;
    zn = Math.max(zmin, Math.min(ZMAX, zn));
    const [wx, wy] = worldAt(px, py), sN = last.fit * zn, pf = last.pf;
    const ncx = wx - (px - (pf.x + pf.w / 2)) / sN, ncy = wy - (py - (pf.y + pf.h / 2)) / sN;
    zt = zn;
    if (glide) ct = [ncx, ncy]; else { z = zn; cx = ncx; cy = ncy; ct = null; }
    touch();
  }

  function attach(cv, opts) {
    key = 'algo-zoom:' + opts.key; rectFn = opts.rect;
    try { const v = JSON.parse(localStorage.getItem(key) || 'null'); if (v && v.z) { z = zt = v.z; cx = v.cx; cy = v.cy; } } catch (e) {}
    const P = e => { const r = rectFn(); return r ? [e.clientX * r.dpr, e.clientY * r.dpr, r] : null; };
    const inside = (x, y, r) => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;

    cv.addEventListener('pointerdown', e => {
      const q = P(e); if (!q || !inside(q[0], q[1], q[2])) return;
      ptrs.set(e.pointerId, [q[0], q[1]]);
      if (ptrs.size === 2) {                                   // a pinch begins
        const [a, b] = [...ptrs.values()];
        pinch = { d0: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, z0: zt, mid: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] };
        pinch.w = worldAt(pinch.mid[0], pinch.mid[1]); pan = null;
        try { cv.setPointerCapture(e.pointerId); } catch (er) {}
      } else if (ptrs.size === 1 && zt > 1.02) {                // zoomed in: one finger moves the view
        pan = { x: q[0], y: q[1], cx: ct ? ct[0] : cx, cy: ct ? ct[1] : cy, moved: false };
      }
      // double-tap: in to 3× at that spot, or back out
      const now = performance.now();
      if (ptrs.size === 1 && now - tapAt < 320 && Math.hypot(q[0] - tapX, q[1] - tapY) < 40 * q[2].dpr) {
        tapAt = 0;
        if (zt < 1.5) zoomAbout(3, q[0], q[1], true);
        else { zt = 1; ct = null; touch(); }
      } else { tapAt = now; tapX = q[0]; tapY = q[1]; }
    });
    cv.addEventListener('pointermove', e => {
      if (!ptrs.has(e.pointerId)) return;
      const q = P(e); if (!q) return;
      ptrs.set(e.pointerId, [q[0], q[1]]);
      if (pinch && ptrs.size >= 2) {
        const [a, b] = [...ptrs.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
        const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], zn = Math.max(zmin, Math.min(ZMAX, pinch.z0 * d / pinch.d0));
        // the world point first under the fingers stays under them, as they spread and move
        const sN = last.fit * zn, pf = last.pf;
        zt = z = zn; cx = pinch.w[0] - (mid[0] - (pf.x + pf.w / 2)) / sN; cy = pinch.w[1] - (mid[1] - (pf.y + pf.h / 2)) / sN; ct = null;
        touch();
      } else if (pan && last) {
        const dx = q[0] - pan.x, dy = q[1] - pan.y;
        if (!pan.moved && Math.hypot(dx, dy) < 6 * q[2].dpr) return;
        pan.moved = true;
        cx = pan.cx - dx / last.s; cy = pan.cy - dy / last.s; ct = null;
        try { cv.setPointerCapture(e.pointerId); } catch (er) {}
        touch();
      }
    });
    const up = e => {
      ptrs.delete(e.pointerId);
      if (ptrs.size < 2) pinch = null;
      if (ptrs.size === 0) pan = null;
      if (zt < 1.03 && zt > 0.97) { zt = 1; }                 // a pinch that ends near the fitted view snaps to it
    };
    cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
    cv.addEventListener('wheel', e => {
      const q = P(e); if (!q || !inside(q[0], q[1], q[2])) return;
      e.preventDefault();
      const f = Math.exp(-e.deltaY * (e.ctrlKey ? 0.012 : 0.0016));   // ctrl = trackpad pinch: finer steps
      zoomAbout(zt * f, q[0], q[1], !e.ctrlKey);
    }, { passive: false });
    addEventListener('keydown', e => {
      if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
      const r = rectFn(); if (!r || !last) return;
      const mx = r.x + r.w / 2, my = r.y + r.h / 2;
      if (e.key === '+' || e.key === '=') zoomAbout(zt * 1.5, mx, my, true);
      else if (e.key === '-' || e.key === '_') zoomAbout(zt / 1.5, mx, my, true);
      else if (e.key === '0') { zt = 1; ct = null; touch(); }
    });
  }

  window.AlgoZoom = {
    attach, view,
    isZoomed: () => zt > 1.02 || z > 1.02,
    pointers: () => ptrs.size,
    moving: () => moving || Math.abs(zt - z) > 1e-3 || !!ct,
    level: () => z,
    reset: () => { zt = 1; ct = null; touch(); },
    onSettle: fn => settleFns.push(fn),
  };
})();
