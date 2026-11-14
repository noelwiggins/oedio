/* ALGOGENESIS cabinet — the shared pachinko machine every concept panel lives in.
   The world itself is drawn by a plugin (window.ALGO_WORLD, loaded before this file):
     ALGO_WORLD.size(d)               -> [w, h] of the world in its own units
     ALGO_WORLD.ingest(d, now)        -> take a new frame from the server
     ALGO_WORLD.draw(ctx, V, now, t, light)  V = {ox, oy, s, u, dpr, pf} maps world units to the screen
   The cabinet draws the case, the chrome rail and corner fans, night, the gold tray with nameplate and fossil
   window, and the keys and cards that hold every word. ?quiet=1 hides the keys. */
(function () {
  'use strict';
  const API = document.body.dataset.api;
  const WORLD = window.ALGO_WORLD;
  if (new URLSearchParams(location.search).get('quiet') === '1') document.body.classList.add('quiet');
  const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
  const veil = document.getElementById('veil'), keys = document.getElementById('keys'), card = document.getElementById('card');
  const INK = '#2a1d14', CREAM = '#fbf3dc', ORANGE = '#ee7d22';
  let L = {}, live = null, meta = null, size = [1200, 800];

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(innerWidth * dpr); cv.height = Math.round(innerHeight * dpr);
    const cw = cv.width, ch = cv.height, u = Math.min(cw, ch);
    const m = u * 0.035, trayH = ch * 0.15;
    const pf = { x: m, y: m, w: cw - 2 * m, h: ch - trayH - m * 1.6 };
    L = { dpr, cw, ch, u, m, trayH, pf, tray: { x: m, y: ch - trayH - m * 0.4, w: cw - 2 * m, h: trayH } };
    L.rail = { cx: pf.x + pf.w / 2, cy: pf.y + pf.h * 0.58, r: Math.min(pf.w * 0.485, pf.h * 0.86) };
    fit();
    placeKeys();
    if (WORLD.resize) WORLD.resize();
  }
  function fit() {
    const pf = L.pf, [w, h] = size, s = Math.max(pf.w / w, pf.h / h);
    L.V = { s, ox: pf.x + (pf.w - w * s) / 2, oy: pf.y + (pf.h - h * s) / 2, u: L.u, dpr: L.dpr, pf };
  }
  addEventListener('resize', resize);
  function placeKeys() {
    const t = L.tray, d = L.dpr;
    keys.style.left = 'auto'; keys.style.right = ((L.cw - (t.x + t.w) + L.u * 0.03) / d) + 'px';
    keys.style.top = ((t.y + t.h / 2) / d) + 'px';
    // fit the knobs and keys beside the fossil window: shrink them on narrow screens rather than overlap
    keys.style.transform = 'translateY(-50%)'; keys.style.transformOrigin = 'right center';
    const gsz = t.h * 0.56, leftLimit = t.x + L.u * 0.06 + gsz + L.u * 0.04 + t.w * 0.2 + L.u * 0.04 + L.u * 0.14;
    const allowed = (t.x + t.w - L.u * 0.03) - leftLimit, natural = keys.offsetWidth * d;
    const k = natural > 0 ? Math.min(1, allowed / natural) : 1;
    keys.style.transform = `translateY(-50%) scale(${Math.max(0.45, k).toFixed(3)})`;
    const pf = L.pf, cw = Math.min(pf.w * 0.5, L.u * 0.95), chh = pf.h * 0.78;
    card.style.width = (cw / d) + 'px'; card.style.maxHeight = (chh / d) + 'px';
    card.style.left = ((pf.x + (pf.w - cw) / 2) / d) + 'px'; card.style.top = ((pf.y + pf.h * 0.1) / d) + 'px';
  }

  // ── data ─────────────────────────────────────────────────────────────
  async function getJSON(u) { const r = await fetch(API + u, { cache: 'no-store' }); return r.json(); }
  async function loadMeta() {
    try {
      meta = await getJSON('/meta');
      if (window.AlgoDials) { AlgoDials.mount({ container: keys, post: API + '/dial', dials: meta.dials || [], show: showCard }); placeKeys(); }
    } catch (e) { setTimeout(loadMeta, 5000); }
  }
  function showCard(title, html) {
    openCard = 'dial'; card.querySelector('h2').textContent = title; card.querySelector('.body').innerHTML = html;
    card.classList.add('open'); document.querySelectorAll('.key').forEach(k => k.classList.remove('on'));
    clearTimeout(cardTimer); cardTimer = setTimeout(closeCard, 60000);
  }
  async function poll() {
    try {
      const d = await getJSON('/live');
      if (!d.standby && (!live || d.tick !== live.tick)) {
        live = d;
        const sz = WORLD.size(d);
        if (sz[0] !== size[0] || sz[1] !== size[1]) { size = sz; fit(); }
        WORLD.ingest(d, performance.now());
        if (window.AlgoDials) AlgoDials.update(d.dials);
        veil.classList.add('gone');
        if (openCard === 'world') renderCard('world');
      }
    } catch (e) { }
    setTimeout(poll, 800);
  }

  // ── the case ─────────────────────────────────────────────────────────
  function rrect(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function chrome(x0, y0, x1, y1) {
    const g = ctx.createLinearGradient(x0, y0, x1, y1);
    g.addColorStop(0, '#f4f6f7'); g.addColorStop(0.25, '#9aa3aa'); g.addColorStop(0.5, '#eef1f3'); g.addColorStop(0.75, '#7d868e'); g.addColorStop(1, '#dfe4e7');
    return g;
  }
  function drawCase() {
    const { cw, ch, u } = L, g = ctx.createLinearGradient(0, 0, 0, ch);
    g.addColorStop(0, '#f6913a'); g.addColorStop(0.5, ORANGE); g.addColorStop(1, '#d9661a');
    ctx.fillStyle = g; ctx.fillRect(0, 0, cw, ch);
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = u * 0.004; rrect(u * 0.01, u * 0.01, cw - u * 0.02, ch - u * 0.02, u * 0.03); ctx.stroke();
  }
  function drawBezel() {
    const { pf, u } = L, b = u * 0.012;
    ctx.lineWidth = b; ctx.strokeStyle = chrome(pf.x, pf.y, pf.x + pf.w, pf.y + pf.h);
    rrect(pf.x - b / 2, pf.y - b / 2, pf.w + b, pf.h + b, u * 0.018); ctx.stroke();
    ctx.lineWidth = u * 0.002; ctx.strokeStyle = INK; rrect(pf.x - b, pf.y - b, pf.w + 2 * b, pf.h + 2 * b, u * 0.022); ctx.stroke();
  }
  function drawRail(t, night) {
    const { pf, rail, u } = L;
    ctx.save();
    ctx.beginPath(); ctx.rect(pf.x, pf.y, pf.w, pf.h); ctx.arc(rail.cx, rail.cy, rail.r, 0, Math.PI * 2, true); ctx.clip('evenodd');
    ctx.fillStyle = 'rgba(251,243,220,0.80)'; ctx.fillRect(pf.x, pf.y, pf.w, pf.h);
    const fans = [[pf.x, pf.y, 0], [pf.x + pf.w, pf.y, Math.PI / 2], [pf.x + pf.w, pf.y + pf.h, Math.PI], [pf.x, pf.y + pf.h, -Math.PI / 2]];
    const cols = ['#e5602a', '#a8c94a', '#f2b33d', '#3f97b5'];
    for (const [fx, fy, rot] of fans) {
      ctx.save(); ctx.translate(fx, fy); ctx.rotate(rot);
      const R = Math.min(pf.w, pf.h) * 0.19;
      ctx.strokeStyle = INK; ctx.lineWidth = u * 0.0025;
      for (let k = 0; k < 7; k++) {
        ctx.fillStyle = cols[k % 4];
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, R * (k % 2 ? 0.86 : 1), k * Math.PI / 14, (k + 1) * Math.PI / 14); ctx.closePath(); ctx.fill(); ctx.stroke();
      }
      ctx.fillStyle = CREAM; ctx.beginPath(); ctx.arc(0, 0, R * 0.42, 0, Math.PI / 2); ctx.lineTo(0, 0); ctx.closePath(); ctx.fill(); ctx.stroke();
      ctx.fillStyle = night > 0.3 ? `hsl(${(rot * 57 + 20) % 360},95%,${55 + 15 * Math.sin(t * 2 + rot)}%)` : '#c0392b';
      ctx.beginPath(); ctx.arc(R * 0.45, R * 0.45, R * 0.09, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.restore();
    }
    ctx.restore();
    ctx.save();
    ctx.lineWidth = u * 0.011; ctx.strokeStyle = chrome(rail.cx - rail.r, rail.cy - rail.r, rail.cx + rail.r, rail.cy + rail.r);
    ctx.beginPath(); ctx.arc(rail.cx, rail.cy, rail.r, 0, Math.PI * 2); ctx.stroke();
    ctx.lineWidth = u * 0.002; ctx.strokeStyle = INK;
    ctx.beginPath(); ctx.arc(rail.cx, rail.cy, rail.r + u * 0.0065, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(rail.cx, rail.cy, rail.r - u * 0.0065, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = 'rgba(42,29,20,0.55)'; ctx.lineWidth = u * 0.0018;
    for (let a = 0.18 * Math.PI; a < 0.82 * Math.PI; a += Math.PI / 140) {
      const r1 = rail.r - u * 0.009, r2 = rail.r - u * 0.019;
      ctx.beginPath(); ctx.moveTo(rail.cx + Math.cos(a) * r1, rail.cy + Math.sin(a) * r1); ctx.lineTo(rail.cx + Math.cos(a) * r2, rail.cy + Math.sin(a) * r2); ctx.stroke();
    }
    ctx.restore();
  }
  function drawTray() {
    const T = L.tray, u = L.u;
    rrect(T.x, T.y, T.w, T.h, u * 0.02);
    const g = ctx.createLinearGradient(0, T.y, 0, T.y + T.h);
    g.addColorStop(0, '#ecd27a'); g.addColorStop(0.5, '#d8b447'); g.addColorStop(1, '#b8902c');
    ctx.fillStyle = g; ctx.fill(); ctx.lineWidth = u * 0.003; ctx.strokeStyle = INK; ctx.stroke();
    ctx.save(); rrect(T.x, T.y, T.w, T.h, u * 0.02); ctx.clip();
    ctx.strokeStyle = 'rgba(120,88,20,0.35)'; ctx.lineWidth = Math.max(1, u * 0.0015);
    for (let x = T.x; x < T.x + T.w; x += u * 0.007) { ctx.beginPath(); ctx.moveTo(x, T.y); ctx.lineTo(x, T.y + T.h); ctx.stroke(); }
    ctx.restore();
    for (const [sx, sy] of [[T.x + u * 0.02, T.y + u * 0.02], [T.x + T.w - u * 0.02, T.y + u * 0.02], [T.x + u * 0.02, T.y + T.h - u * 0.02], [T.x + T.w - u * 0.02, T.y + T.h - u * 0.02]]) {
      ctx.fillStyle = chrome(sx - 5, sy - 5, sx + 5, sy + 5); ctx.beginPath(); ctx.arc(sx, sy, u * 0.008, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = INK; ctx.lineWidth = u * 0.0015; ctx.stroke(); ctx.beginPath(); ctx.moveTo(sx - u * 0.005, sy); ctx.lineTo(sx + u * 0.005, sy); ctx.stroke();
    }
    const gx = T.x + u * 0.06, gy = T.y + T.h * 0.22, gs = T.h * 0.56;
    rrect(gx, gy, gs, gs, u * 0.01); ctx.fillStyle = '#c9a63c'; ctx.fill(); ctx.strokeStyle = INK; ctx.lineWidth = u * 0.002; ctx.stroke();
    ctx.fillStyle = 'rgba(42,29,20,0.55)';
    for (let i = 1; i < 7; i++) for (let j = 1; j < 7; j++) { ctx.beginPath(); ctx.arc(gx + gs * i / 7, gy + gs * j / 7, u * 0.003, 0, Math.PI * 2); ctx.fill(); }
    // nameplate: the concept's name
    const title = ((meta && meta.title) || 'ALGOGENESIS').toUpperCase();
    const nx = gx + gs + u * 0.035, nw = T.w * 0.2, nh = T.h * 0.38, ny = T.y + T.h * 0.31;
    L.nameplate = { x: nx, y: ny, w: nw, h: nh };
    rrect(nx, ny, nw, nh, nh / 2); ctx.fillStyle = CREAM; ctx.fill(); ctx.lineWidth = u * 0.004; ctx.strokeStyle = INK; ctx.stroke();
    rrect(nx + u * 0.005, ny + u * 0.005, nw - u * 0.01, nh - u * 0.01, nh / 2); ctx.lineWidth = u * 0.0015; ctx.stroke();
    ctx.fillStyle = INK; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    let fs = nh * 0.5; ctx.font = `${fs}px Righteous, sans-serif`;
    while (ctx.measureText(title).width > nw * 0.84 && fs > 6) { fs -= 1; ctx.font = `${fs}px Righteous, sans-serif`; }
    ctx.fillText(title, nx + nw / 2, ny + nh / 2 + fs * 0.05);
    ctx.textBaseline = 'alphabetic';
    // the fossil window
    const kl = keys.getBoundingClientRect().left * L.dpr;
    const wx = nx + nw + u * 0.04, ww = Math.max(u * 0.08, (kl > 0 ? kl - u * 0.03 : T.x + T.w * 0.68) - wx), wy = T.y + T.h * 0.18, wh = T.h * 0.64;
    L.fossilWin = { x: wx, y: wy, w: ww, h: wh };
    rrect(wx, wy, ww, wh, u * 0.01); ctx.fillStyle = '#1b130d'; ctx.fill(); ctx.lineWidth = u * 0.006; ctx.strokeStyle = chrome(wx, wy, wx + ww, wy + wh); ctx.stroke();
    const strata = live && live.strata;
    if (strata && strata.length) {
      ctx.save(); rrect(wx, wy, ww, wh, u * 0.01); ctx.clip();
      const n = strata.length, cwid = Math.max(2, Math.min(ww / Math.max(n, 40), u * 0.02)), pad = wh * 0.08, hh = wh - 2 * pad;
      for (let i = 0; i < n; i++) {
        const x = wx + ww - (n - i) * cwid - u * 0.006;
        if (x + cwid < wx) continue;
        const cols = strata[i].cols || [], tot = cols.reduce((a, c) => a + c[2], 0) || 1;
        let yy = wy + pad;
        for (const [hue, sat, wgt] of cols) {
          const hg = hh * wgt / tot;
          ctx.fillStyle = `hsl(${hue * 360},${20 + 70 * sat}%,${45 + 15 * sat}%)`; ctx.fillRect(x, yy, cwid - 1, hg); yy += hg;
        }
      }
      ctx.restore();
    }
    ctx.fillStyle = 'rgba(255,255,255,0.08)'; ctx.beginPath(); ctx.moveTo(wx, wy); ctx.lineTo(wx + ww * 0.3, wy); ctx.lineTo(wx + ww * 0.15, wy + wh); ctx.lineTo(wx, wy + wh); ctx.closePath(); ctx.fill();
  }

  // ── cards ────────────────────────────────────────────────────────────
  let openCard = null, cardTimer = null;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmt = n => (n == null ? '—' : typeof n === 'number' ? n.toLocaleString() : esc(n));
  function renderCard(kind) {
    const h2 = card.querySelector('h2'), body = card.querySelector('.body');
    const d = live || {}, s = d.stats || {}, m = meta || {};
    if (kind === 'world') {
      h2.textContent = m.title || 'The world now';
      body.innerHTML = `<p class="def">${esc(m.definition || '')}</p><table>` +
        (m.stat_labels || []).map(([k, lab]) => `<tr><td>${esc(lab)}</td><td>${fmt(s[k])}</td></tr>`).join('') +
        `<tr><td>Steps</td><td>${fmt(d.tick)}</td></tr><tr><td>Epochs in the fossil record</td><td>${fmt((d.strata || []).length)}</td></tr></table>` +
        `<p class="note" style="margin-top:1.6vmin">${(d.events || []).slice(-5).reverse().map(e => esc(e.text)).join('<br>')}</p>`;
    } else if (kind === 'journal') {
      h2.textContent = 'The journal';
      body.innerHTML = '<p class="note">Opening the journal…</p>';
      getJSON('/chronicle?n=40').then(rows => {
        if (openCard !== 'journal') return;
        body.innerHTML = rows.map(r => `<div class="entry"><b>Epoch ${fmt(r.epoch)}</b><p>${esc(r.text)}</p></div>`).join('') ||
          '<p class="note">The first entry is written at the end of the first epoch.</p>';
      }).catch(() => {});
    } else if (kind === 'fossils') {
      h2.textContent = 'The fossil record';
      const last = (d.strata || []).slice(-1)[0];
      body.innerHTML = `<p class="note">The window in the tray lays down one column per epoch, newest on the right. Each colour is one of the leading lineages of that epoch, its height its share.</p>` +
        (last ? '<table>' + last.cols.map(c => `<tr><td><span class="sw" style="background:hsl(${c[0] * 360},${20 + 70 * c[1]}%,${45 + 15 * c[1]}%)"></span>lineage</td><td>${fmt(c[2])}</td></tr>`).join('') + '</table>'
          : '<p class="note">The first layer is laid down at the end of the first epoch.</p>');
    } else {
      h2.textContent = m.title || 'Algogenesis';
      body.innerHTML = `<p class="def">${esc(m.definition || '')}</p>` + (m.about || []).map(p => `<p class="note">${esc(p)}</p>`).join('');
    }
  }
  function toggleCard(kind) {
    document.querySelectorAll('.key').forEach(k => k.classList.toggle('on', k.dataset.card === kind && openCard !== kind));
    if (openCard === kind) { closeCard(); return; }
    openCard = kind; renderCard(kind); card.classList.add('open');
    clearTimeout(cardTimer); cardTimer = setTimeout(closeCard, 60000);
  }
  function closeCard() { openCard = null; card.classList.remove('open'); document.querySelectorAll('.key').forEach(k => k.classList.remove('on')); }
  keys.addEventListener('click', e => { const b = e.target.closest('.key'); if (b) toggleCard(b.dataset.card); });
  card.querySelector('.x').onclick = closeCard;
  cv.addEventListener('click', e => {
    const x = e.clientX * L.dpr, y = e.clientY * L.dpr, n = L.nameplate, f = L.fossilWin;
    if (n && x > n.x && x < n.x + n.w && y > n.y && y < n.y + n.h) return toggleCard('about');
    if (f && x > f.x && x < f.x + f.w && y > f.y && y < f.y + f.h) return toggleCard('fossils');
    if (openCard) closeCard();
  });

  // ── frame loop ───────────────────────────────────────────────────────
  let smooth = 1;
  function frame() {
    requestAnimationFrame(frame);
    if (!L.cw) return;
    const now = performance.now(), t = now / 1000;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    drawCase();
    smooth += ((live ? live.light : 1) - smooth) * 0.02;
    const night = Math.max(0, 1 - smooth), pf = L.pf;
    ctx.save(); rrect(pf.x, pf.y, pf.w, pf.h, L.u * 0.018); ctx.clip();
    ctx.fillStyle = CREAM; ctx.fillRect(pf.x, pf.y, pf.w, pf.h);
    if (live) WORLD.draw(ctx, L.V, now, t, smooth);
    drawRail(t, night);
    if (night > 0.01) { ctx.fillStyle = `rgba(14,10,40,${0.55 * night})`; ctx.fillRect(pf.x, pf.y, pf.w, pf.h); }
    if (live && WORLD.drawGlow) WORLD.drawGlow(ctx, L.V, now, t, smooth);
    ctx.restore();
    drawBezel();
    drawTray();
    if (night > 0.01) { ctx.fillStyle = `rgba(14,10,40,${0.12 * night})`; ctx.fillRect(0, 0, L.cw, L.ch); }
  }

  let idle;
  addEventListener('pointermove', () => { document.body.classList.add('awake'); clearTimeout(idle); idle = setTimeout(() => document.body.classList.remove('awake'), 2500); });
  addEventListener('dblclick', () => { (document.documentElement.requestFullscreen || function () {}).call(document.documentElement); });
  if (navigator.wakeLock) navigator.wakeLock.request('screen').catch(() => {});
  resize(); loadMeta(); poll(); requestAnimationFrame(frame);
})();
