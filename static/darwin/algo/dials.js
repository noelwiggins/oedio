/* ALGOGENESIS dials: chrome knobs in the tray that change a panel's environment.
   Drag (or swipe) a knob round to set it; tap it to read what it does. A turned dial eases in over about a minute
   and wears off over about twenty, like food in a tank. The coloured arc shows the dial's effect now; the notch
   shows where it was last set.
   window.AlgoDials.mount({ container, post: url, dials: [specs], show: (title, html) => void })
   window.AlgoDials.update(payload)   payload = {key: [current, target]} from the live frame */
(function () {
  'use strict';
  const ICONS = {
    leaf: '<path d="M5 19c0-8 5-13 14-14-1 9-6 14-14 14z"/><path d="M5 19l8-8"/>',
    fish: '<path d="M3 12c3-4 8-5 12-3l5-3v12l-5-3c-4 2-9 1-12-3z"/><circle cx="8" cy="11" r=".8"/>',
    drop: '<path d="M12 3c4 5 6 8 6 11a6 6 0 0 1-12 0c0-3 2-6 6-11z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>',
    spark: '<path d="M12 2l2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5z"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',
    flame: '<path d="M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-3 2-4 2-7 1 1 2 2 3 3 0-2 0-4 0-6z"/>',
    snow: '<path d="M12 3v18M4 7.5l16 9M4 16.5l16-9"/>',
    wave: '<path d="M2 9c3-3 5 3 8 0s5 3 8 0 3-1 4 0M2 15c3-3 5 3 8 0s5 3 8 0 3-1 4 0"/>',
    star: '<path d="M12 3l2.6 5.6 6 .6-4.5 4 1.3 6-5.4-3.1-5.4 3.1 1.3-6-4.5-4 6-.6z"/>',
    eye: '<path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    people: '<circle cx="8" cy="8" r="3"/><circle cx="16" cy="9" r="2.5"/><path d="M3 20c0-4 2-6 5-6s5 2 5 6M13 20c0-3 1.5-5 3-5s4 2 4 5"/>',
    globe: '<circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c3 3 3 13 0 16M12 4c-3 3-3 13 0 16"/>',
    heart: '<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/>',
    gauge: '<path d="M4 16a8 8 0 1 1 16 0"/><path d="M12 16l4-5"/>',
    atom: '<circle cx="12" cy="12" r="1.6"/><ellipse cx="12" cy="12" rx="9" ry="3.6"/><ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(120 12 12)"/>'
  };
  const SWEEP = 135;                     // degrees either side of top
  const knobs = {};
  let cfg = null;

  const css = document.createElement('style');
  css.textContent = `
  .dial { width: 8.4vmin; height: 8.4vmin; border-radius: 50%; border: 0; padding: 0; position: relative; cursor: grab; touch-action: none;
          background: radial-gradient(circle at 35% 30%, #fff 0, #d8dde2 18%, #8d969e 52%, #e7ebee 70%, #6c757d 100%);
          box-shadow: 0 .5vmin .9vmin rgba(0,0,0,.45); }
  .dial:active { cursor: grabbing; }
  .dial svg.ring { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
  .dial .cap { position: absolute; inset: 22%; border-radius: 50%; background: #2a1d14; display: grid; place-items: center;
               box-shadow: inset 0 .4vmin 0 rgba(255,255,255,.18), inset 0 -.5vmin 0 rgba(0,0,0,.35); transition: transform .25s; }
  .dial .cap svg { width: 56%; height: 56%; fill: none; stroke: var(--c); stroke-width: 2.1; stroke-linecap: round; stroke-linejoin: round; }
  .dial .notch { position: absolute; left: 50%; top: 23%; width: .55vmin; height: 1.8vmin; margin-left: -.275vmin; border-radius: .3vmin;
                 background: #fbf3dc; transform-origin: 50% 2.27vmin; }
  .dial-num { position: absolute; left: 50%; top: -3.6vmin; transform: translateX(-50%); min-width: 4.6vmin; padding: .15vmin .8vmin;
              border-radius: 999px; background: #fbf3dc; border: .25vmin solid #2a1d14; color: #2a1d14; text-align: center;
              font: 400 2.1vmin/1.25 "Righteous", sans-serif; letter-spacing: .02em; pointer-events: none; white-space: nowrap; }
  .dial-num.max { background: var(--c); }
  .dial-sep { width: .35vmin; height: 7vmin; background: rgba(42,29,20,.45); border-radius: .2vmin; margin: 0 .6vmin; }
  body.quiet .dial, body.quiet .dial-sep { display: none; }`;
  document.head.appendChild(css);

  function arcPath(r, a0, a1) {     // degrees from top, clockwise
    const p = a => [50 + r * Math.sin(a * Math.PI / 180), 50 - r * Math.cos(a * Math.PI / 180)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    const large = Math.abs(a1 - a0) > 180 ? 1 : 0, sweep = a1 > a0 ? 1 : 0;
    return `M${x0.toFixed(2)},${y0.toFixed(2)} A${r},${r} 0 ${large} ${sweep} ${x1.toFixed(2)},${y1.toFixed(2)}`;
  }

  function mount(c) {
    cfg = c;
    if (!c.dials || !c.dials.length) return;
    const frag = document.createDocumentFragment();
    for (const spec of c.dials) {
      const b = document.createElement('button');
      b.className = 'dial'; b.type = 'button'; b.style.setProperty('--c', spec.colour);
      b.setAttribute('aria-label', `${spec.label} dial`);
      b.innerHTML = `<svg class="ring" viewBox="0 0 100 100">
          <path d="${arcPath(47, -SWEEP, SWEEP)}" fill="none" stroke="rgba(42,29,20,.55)" stroke-width="5" stroke-linecap="round"/>
          <path class="val" d="" fill="none" stroke="${spec.colour}" stroke-width="5" stroke-linecap="round"/>
          <circle cx="50" cy="3" r="2.2" fill="#2a1d14"/></svg>
        <div class="cap"><svg viewBox="0 0 24 24">${ICONS[spec.icon] || ICONS.gauge}</svg></div><div class="notch"></div><div class="dial-num">0</div>`;
      frag.appendChild(b);
      knobs[spec.key] = { el: b, spec, cur: 0, target: 0, local: null, localAt: 0 };
      wire(knobs[spec.key]);
    }
    const sep = document.createElement('div'); sep.className = 'dial-sep'; frag.appendChild(sep);
    c.container.insertBefore(frag, c.container.firstChild);
    draw();
  }

  function wire(k) {
    let start = null, moved = false;
    const valFromEvent = e => {
      const r = k.el.getBoundingClientRect(), dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
      let deg = Math.atan2(dx, -dy) * 180 / Math.PI;            // 0 at top, clockwise positive
      return Math.max(-1, Math.min(1, deg / SWEEP));
    };
    k.el.addEventListener('pointerdown', e => { start = [e.clientX, e.clientY]; moved = false; k.el.setPointerCapture(e.pointerId); e.preventDefault(); });
    k.el.addEventListener('pointermove', e => {
      if (!start) return;
      if (!moved && Math.hypot(e.clientX - start[0], e.clientY - start[1]) < 6) return;
      moved = true; k.local = valFromEvent(e); k.localAt = performance.now(); draw();
    });
    const end = e => {
      if (!start) return;
      start = null;
      if (!moved) { openCard(k); return; }
      send(k);
    };
    k.el.addEventListener('pointerup', end);
    k.el.addEventListener('pointercancel', () => { start = null; });
    k.el.addEventListener('keydown', e => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowUp') { k.local = Math.min(1, (k.local ?? k.target) + 0.1); k.localAt = performance.now(); draw(); send(k); e.preventDefault(); }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') { k.local = Math.max(-1, (k.local ?? k.target) - 0.1); k.localAt = performance.now(); draw(); send(k); e.preventDefault(); }
    });
  }

  let sendTimer = {};
  function send(k) {
    clearTimeout(sendTimer[k.spec.key]);
    sendTimer[k.spec.key] = setTimeout(() => {
      fetch(cfg.post, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: k.spec.key, value: k.local }) })
        .catch(() => {});
    }, 250);
  }

  function word(spec, v) {
    if (Math.abs(v) < 0.05) return 'left to itself';
    const how = Math.abs(v) > 0.66 ? 'strongly' : Math.abs(v) > 0.33 ? 'well' : 'a little';
    return `${how} toward ${(v > 0 ? spec.high : spec.low).toLowerCase()}`;
  }
  function fmtNum(v) { const n = Math.round(v * 10); return n > 0 ? '+' + n : n < 0 ? '\u2212' + Math.abs(n) : '0'; }
  function openCard(k) {
    if (!cfg.show) return;
    const s = k.spec, esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    cfg.show(`${s.label} dial`, `<p class="note">${esc(s.help)}</p>
      <table><tr><td>Turned left</td><td>${esc(s.low)}</td></tr><tr><td>Turned right</td><td>${esc(s.high)}</td></tr>
      <tr><td>Set now</td><td>${esc(fmtNum(k.target))} · ${esc(word(s, k.target))}</td></tr><tr><td>Taking effect</td><td>${esc(fmtNum(k.cur))} · ${esc(word(s, k.cur))}</td></tr></table>
      <p class="note" style="margin-top:1.4vmin">Drag the knob round to turn it; the number above it runs from \u221210 to +10. A setting takes about a minute to be felt and wears off over about twenty, like food in a tank, so the world always drifts back to its own course. Every turn is written into the world's record.</p>`);
  }

  function draw() {
    const now = performance.now();
    for (const k of Object.values(knobs)) {
      if (k.local !== null && now - k.localAt > 6000) k.local = null;
      const shown = k.local !== null ? k.local : k.target;
      const val = k.el.querySelector('path.val');
      const a = k.cur * SWEEP;
      val.setAttribute('d', Math.abs(a) < 1 ? '' : arcPath(47, Math.min(0, a), Math.max(0, a)));
      k.el.querySelector('.notch').style.transform = `rotate(${shown * SWEEP}deg)`;
      k.el.querySelector('.cap').style.transform = `rotate(${shown * SWEEP * 0.25}deg)`;
      // the setting as a number from -10 to +10, lit at either end
      const num = Math.round(shown * 10), lab = k.el.querySelector('.dial-num');
      lab.textContent = fmtNum(shown);
      lab.classList.toggle('max', Math.abs(num) >= 10);
    }
  }

  function update(payload) {
    if (!payload) return;
    for (const [key, [cur, target]] of Object.entries(payload)) {
      const k = knobs[key];
      if (!k) continue;
      k.cur = cur; k.target = target;
    }
    draw();
  }
  setInterval(draw, 1000);
  window.AlgoDials = { mount, update };
})();
