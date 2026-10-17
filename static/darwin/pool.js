/* The tidal pool renderer (life-3.0): draws every creature from its developmental body plan.
   Shared by the Darwin homepage and /darwin/pool. Nothing is invented client-side: positions come
   from the server's frames and bodies from the plans the simulation grew. */
(function () {
  const D = window.Darwin;
  const CELL_COLORS = {
    0: [196, 184, 160],   // skin
    1: [92, 201, 120],    // photo
    2: [235, 96, 82],     // mouth
    3: [235, 235, 245],   // flagellum
    4: [40, 40, 60],      // eye
    5: [140, 150, 165],   // armour
    6: [233, 191, 109],   // store
    7: [170, 120, 235],   // neuron
    8: [240, 140, 190],   // gonad
  };
  D.CELL_COLORS = CELL_COLORS;
  D.CELL_LABELS = ['skin', 'photo', 'mouth', 'flagellum', 'eye', 'armour', 'store', 'neuron', 'gonad'];

  D.geo = function (ma) {
    if (ma == null) return '—';
    if (ma >= 1000) return (ma / 1000).toFixed(3) + ' billion years';
    if (ma >= 1) return ma.toFixed(ma >= 100 ? 0 : 1) + ' million years';
    return Math.round(ma * 1000).toLocaleString() + ' thousand years';
  };

  /* Draw one body plan centred at (cx, cy), rotated by heading `hd` (radians), `u` px per cell. */
  D.drawBody = function (ctx, cells, cx, cy, hd, u, hue, alpha) {
    const c = Math.cos(hd), s = Math.sin(hd);
    const r = Math.max(0.9, u * 0.5);
    cells.forEach(([dx, dy, t]) => {
      const x = cx + (dx * c - dy * s) * u, y = cy + (dx * s + dy * c) * u;
      let col = CELL_COLORS[t];
      if (t === 0) col = hsl(hue, 0.35, 0.68);
      ctx.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},${alpha})`;
      if (t === 3) {       // flagellum: a short whip pointing backwards
        ctx.strokeStyle = ctx.fillStyle; ctx.lineWidth = Math.max(1, u * 0.25);
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - c * u * 1.1, y - s * u * 1.1); ctx.stroke();
        ctx.beginPath(); ctx.arc(x, y, r * 0.55, 0, 7); ctx.fill();
      } else if (t === 4) { // eye: dark pupil with a light ring
        ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
        ctx.strokeStyle = `rgba(255,255,255,${0.8 * alpha})`; ctx.lineWidth = Math.max(0.6, u * 0.18);
        ctx.beginPath(); ctx.arc(x, y, r * 0.85, 0, 7); ctx.stroke();
      } else if (t === 5) { // armour: square plate
        ctx.fillRect(x - r, y - r, r * 2, r * 2);
      } else {
        ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
      }
    });
  };

  function hsl(h, s, l) {
    h = ((h % 360) + 360) % 360 / 360;
    const f = n => { const k = (n + h * 12) % 12, a = s * Math.min(l, 1 - l); return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)); };
    return [Math.round(f(0) * 255), Math.round(f(8) * 255), Math.round(f(4) * 255)];
  }

  /* Small standalone drawing of a body plan into a <canvas>. */
  D.bodyThumb = function (canvas, cells, hue) {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = canvas.clientWidth || 64, h = canvas.clientHeight || 64;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!cells || !cells.length) return;
    const xs = cells.map(c => c[0]), ys = cells.map(c => c[1]);
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) + 1;
    const u = Math.min(14, (Math.min(w, h) - 8) / span);
    const mx = (Math.max(...xs) + Math.min(...xs)) / 2, my = (Math.max(...ys) + Math.min(...ys)) / 2;
    D.drawBody(ctx, cells.map(([x, y, t]) => [x - mx, y - my, t]), w / 2, h / 2, 0, u, hue || 0, 1);
  };

  /* Live view. opts: {canvas, tag, onData(d)} */
  D.PoolView = function (opts) {
    const canvas = opts.canvas, ctx = canvas.getContext('2d');
    let prev = null, cur = null, tPrev = 0, tCur = 0, data = null, failures = 0, plans = {};

    function resize() {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
    }
    window.addEventListener('resize', resize); resize();

    function setTag(cls, txt) { if (opts.tag) { opts.tag.className = 'terra-tag' + (cls ? ' ' + cls : ''); opts.tag.querySelector('span').textContent = txt; } }

    async function poll() {
      try {
        const d = await D.api('/darwin/api/pool');
        failures = 0;
        if (!d || d.standby) { setTag('', d && d.note ? d.note : 'starting'); setTimeout(poll, 2000); return; }
        data = d;
        Object.assign(plans, d.plans || {});
        const f = d.frames && d.frames[d.frames.length - 1];
        if (f && (!cur || f.t > cur.t)) {
          prev = cur; cur = f; tPrev = tCur; tCur = performance.now();
          if (prev && f.t < prev.t) prev = null;
        }
        setTag(d.stale ? '' : 'live', d.stale ? 'paused · the pool process is restarting' :
          `live · ${D.geo(d.geo_ma)} · tick ${d.tick.toLocaleString()}`);
        if (opts.onData) opts.onData(d);
      } catch (e) {
        failures++;
        setTag('', failures > 2 ? 'connection lost' : 'retrying');
      }
      setTimeout(poll, document.hidden ? 4000 : 1000);
    }

    function draw(ts) {
      resize();
      const W = canvas.clientWidth, H = canvas.clientHeight;
      ctx.clearRect(0, 0, W, H);
      if (data) {
        const A = data.arena, s = W / A, sy = H / A, env = data.env || {};
        // light band: the sunlit stripe of water, brighter by day
        const light = Math.max(0.05, env.light || 0);
        const band = env.band * sy, bw = env.width * sy;
        [-H, 0, H].forEach(off => {
          const g = ctx.createLinearGradient(0, band + off - bw * 1.6, 0, band + off + bw * 1.6);
          g.addColorStop(0, 'rgba(255,236,170,0)'); g.addColorStop(0.5, `rgba(255,236,170,${0.16 * light})`); g.addColorStop(1, 'rgba(255,236,170,0)');
          ctx.fillStyle = g; ctx.fillRect(0, band + off - bw * 1.6, W, bw * 3.2);
        });
        // nutrients (teal) and dead matter (brown), coarse 12x12 fields
        const cw = W / 12, ch = H / 12;
        (env.nutrient || []).forEach((row, j) => row.forEach((v, i) => {
          if (v > 8) { ctx.fillStyle = `rgba(80,190,200,${Math.min(0.14, v / 600)})`; ctx.fillRect(i * cw, j * ch, cw, ch); }
        }));
        (env.detritus || []).forEach((row, j) => row.forEach((v, i) => {
          if (v > 4) { ctx.fillStyle = `rgba(150,110,70,${Math.min(0.5, v / 120)})`;
            for (let k = 0; k < Math.min(6, v / 10); k++) ctx.fillRect(i * cw + ((k * 37 + j * 13) % cw), j * ch + ((k * 23 + i * 17) % ch), 1.5, 1.5); }
        }));
        (env.upwellings || []).forEach(([x, y]) => {
          const r = 14 * s;
          const g = ctx.createRadialGradient(x * s, y * sy, 0, x * s, y * sy, r);
          g.addColorStop(0, 'rgba(110,220,230,.20)'); g.addColorStop(1, 'rgba(110,220,230,0)');
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x * s, y * sy, r, 0, 7); ctx.fill();
        });
        if (cur) {
          const k = prev ? Math.min(1, (ts - tCur) / Math.max(300, tCur - tPrev)) : 1;
          const pm = prev ? new Map(prev.c.map(c => [c[0], c])) : null;
          const u = Math.max(1.6, s * 1.05);
          cur.c.forEach(c => {
            let x = c[1] / 10, y = c[2] / 10, hd = c[3] / 100;
            const p = pm && pm.get(c[0]);
            if (p) {
              let dx = x - p[1] / 10, dy = y - p[2] / 10;
              if (Math.abs(dx) < A / 2 && Math.abs(dy) < A / 2) { x = p[1] / 10 + dx * k; y = p[2] / 10 + dy * k; }
            }
            const body = plans[c[4]] || [[0, 0, 1]];
            D.drawBody(ctx, body, x * s, y * sy, hd, u, c[5], 0.55 + 0.45 * Math.min(1, c[6] / 60));
          });
        }
      }
      requestAnimationFrame(draw);
    }
    poll(); requestAnimationFrame(draw);
  };
})();
