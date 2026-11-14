/* ALGOGENESIS — the fossil record of the Coast.
   Every kind of animal and flower that has ever lived on the panel is kept in an archive on the server. This file
   draws each one from its genes (the same flat decal style as the board), shows them in a browsable cabinet of
   specimens with their history, and feeds the tray's fossil window a slowly moving strip of imprints.
   AlgoFossils.mount({ api, onOpen, onClose }) · .open() · .close() · .isOpen() · .place({x,y,w,h} css px)
   AlgoFossils.drawStrip(ctx, x, y, w, h, t)  — paint the tray window (canvas pixels)                                 */
(function () {
  'use strict';
  const INK = '#2a1d14', CREAM = '#fbf3dc';
  const DAY_WORD = d => d == null ? '—' : `day ${Math.floor(d).toLocaleString()}`;

  // ── drawing a specimen from its genes ────────────────────────────────
  // animal look = [hue, sat, hue2, pattern, glow, segs, limbs, size, tail, crest, fin, diet]
  function animal(g, look, cx, cy, box, opt) {
    const [hue, sat, hue2, pattern, glow, segs0, limbs, size, tail, crest, fin, diet] = look;
    const segs = Math.max(1, Math.round(segs0)), legs = Math.round(limbs);
    // the body in unit space: head at the right, segments trailing left in a gentle S
    const pts = []; let x = 0, y = 0, ang = Math.PI;
    for (let i = 0; i < segs; i++) {
      const r = (1 - 0.5 * i / Math.max(segs, 2)) * (i === 0 ? 1.05 : 1);
      pts.push([x, y, r, ang]);
      ang = Math.PI + Math.sin(0.8 - i * 0.9) * 0.22 * (fin > 0.5 ? 1 : 0.5);
      x += Math.cos(ang) * 1.05; y += Math.sin(ang) * 1.05;
    }
    const last = pts[pts.length - 1], tl = 1.2 + 3 * tail, sp = 0.35 + 0.4 * fin;
    // the envelope, to fit the box
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    const grow = (px, py, r) => { x0 = Math.min(x0, px - r); x1 = Math.max(x1, px + r); y0 = Math.min(y0, py - r); y1 = Math.max(y1, py + r); };
    for (const [px, py, r] of pts) grow(px, py, r * (legs ? 2.3 : 1.25) + (crest > 0.25 ? r * (0.6 + 1.6 * crest) : 0));
    if (tail > 0.15) grow(last[0] - tl, last[1], tl * Math.sin(sp) + 0.2);
    const k = box * 0.84 / Math.max(x1 - x0, (y1 - y0) * 1.15, 3.2);
    const Lt = 48 + 14 * (1 - sat), S = 25 + 70 * sat;
    const base = `hsl(${hue * 360},${S}%,${Lt}%)`, alt = `hsl(${hue2 * 360},${Math.max(45, S)}%,${Math.min(70, Lt + 8)}%)`;
    const ow = 0.22;
    g.save(); g.translate(cx - (x0 + x1) / 2 * k, cy - (y0 + y1) / 2 * k); g.scale(k, k);
    g.lineCap = 'round'; g.lineJoin = 'round';
    if (glow > 0.12 && !(opt && opt.fossil)) {
      for (const [px, py, r] of pts) {
        const R = r * (2.2 + 4 * glow), gr = g.createRadialGradient(px, py, 0, px, py, R);
        gr.addColorStop(0, `hsla(${hue * 360},95%,62%,${0.45 * glow})`); gr.addColorStop(1, `hsla(${hue * 360},95%,50%,0)`);
        g.fillStyle = gr; g.beginPath(); g.arc(px, py, R, 0, 7); g.fill();
      }
    }
    if (legs > 0) {
      for (const pass of [0, 1]) {
        g.strokeStyle = pass ? alt : INK;
        for (let j = 0; j < legs; j++) {
          const i = Math.min(pts.length - 1, Math.round((j + 0.5) * pts.length / legs - 0.5));
          const [px, py, r, a] = pts[i], step = Math.sin(j * 1.7) * 0.35;
          g.lineWidth = r * 0.26 + (pass ? 0 : ow * 1.2);
          for (const side of [-1, 1]) {
            const la = a + side * (Math.PI / 2 + step * side), len = r * 2.1;
            g.beginPath(); g.moveTo(px, py);
            g.lineTo(px + Math.cos(la) * len * 0.6, py + Math.sin(la) * len * 0.6);
            g.lineTo(px + Math.cos(la + 0.6 * side) * len, py + Math.sin(la + 0.6 * side) * len); g.stroke();
          }
        }
      }
    }
    if (tail > 0.15) {
      const [tx, ty, , a] = last;
      g.fillStyle = alt; g.strokeStyle = INK; g.lineWidth = ow;
      g.beginPath(); g.moveTo(tx, ty);
      g.lineTo(tx + Math.cos(a - sp) * tl, ty + Math.sin(a - sp) * tl);
      g.quadraticCurveTo(tx + Math.cos(a) * tl * 0.6, ty + Math.sin(a) * tl * 0.6, tx + Math.cos(a + sp) * tl, ty + Math.sin(a + sp) * tl);
      g.closePath(); g.fill(); g.stroke();
    }
    if (crest > 0.25) {
      for (const pass of [0, 1]) {
        g.strokeStyle = pass ? alt : INK;
        for (const [px, py, r, a] of pts) {
          g.lineWidth = r * 0.2 + (pass ? 0 : ow);
          const n = a + Math.PI / 2, len = r * (0.6 + 1.6 * crest);
          g.beginPath(); g.moveTo(px + Math.cos(n) * r * 0.7, py + Math.sin(n) * r * 0.7);
          g.lineTo(px + Math.cos(n) * (r + len), py + Math.sin(n) * (r + len)); g.stroke();
        }
      }
    }
    g.fillStyle = INK;
    for (const [px, py, r] of pts) { g.beginPath(); g.arc(px, py, r + ow, 0, 7); g.fill(); }
    for (let i = pts.length - 1; i >= 0; i--) {
      const [px, py, r] = pts[i];
      g.fillStyle = (pattern > 0.33 && pattern <= 0.66 && i % 2 === 1) ? alt : base;
      g.beginPath(); g.arc(px, py, r, 0, 7); g.fill();
      if (pattern > 0.66) {
        g.fillStyle = alt; g.beginPath();
        g.arc(px + r * 0.35, py - r * 0.25, r * 0.3, 0, 7); g.arc(px - r * 0.3, py + r * 0.3, r * 0.24, 0, 7); g.fill();
      }
    }
    const [hx, hy, hr] = pts[0];
    g.fillStyle = CREAM; g.beginPath(); g.arc(hx + hr * 0.45, hy, hr * 0.3, 0, 7); g.fill();
    g.fillStyle = INK; g.beginPath(); g.arc(hx + hr * 0.55, hy, hr * 0.15, 0, 7); g.fill();
    if (diet > 0.6) { g.strokeStyle = CREAM; g.lineWidth = hr * 0.18; g.beginPath(); g.arc(hx + hr * 0.75, hy, hr * 0.35, -1, 1); g.stroke(); }
    g.restore();
  }
  // flower look = [hue, petals, size, height, sat, hue2, nectar]
  function flower(g, look, cx, cy, box) {
    const [hue, petals, , , sat, hue2] = look;
    const n = Math.max(3, Math.round(petals)), R = box * 0.4;
    const Lt = 56 + 8 * (1 - sat), S = 45 + 50 * sat;
    g.save(); g.translate(cx, cy); g.lineJoin = 'round';
    g.lineWidth = Math.max(1, R * 0.07); g.strokeStyle = INK; g.fillStyle = `hsl(${hue * 360},${S}%,${Lt}%)`;
    for (let i = 0; i < n; i++) {
      g.save(); g.rotate(i / n * Math.PI * 2 - Math.PI / 2);
      g.beginPath(); g.ellipse(R * 0.5, 0, R * 0.5, R * 0.26 * (1 + 2.5 / n), 0, 0, 7); g.fill(); g.stroke();
      g.restore();
    }
    g.fillStyle = `hsl(${hue2 * 360},75%,58%)`;
    g.beginPath(); g.arc(0, 0, R * 0.26, 0, 7); g.fill(); g.stroke();
    g.restore();
  }
  function specimen(g, f, cx, cy, box, opt) {
    if (!f.look) return;
    if (f.kind === 'animal') animal(g, f.look, cx, cy, box, opt); else flower(g, f.look, cx, cy, box);
  }
  function portrait(f, px, dpr, opt) {
    const c = document.createElement('canvas'); c.width = c.height = Math.round(px * dpr);
    const g = c.getContext('2d');
    specimen(g, f, c.width / 2, c.height / 2, c.width, opt);
    if (opt && opt.fossil) {        // an imprint in stone: the shape kept, the colour turned to umber
      g.globalCompositeOperation = 'source-atop'; g.fillStyle = 'rgba(214,180,120,0.72)'; g.fillRect(0, 0, c.width, c.height);
    }
    return c;
  }

  // ── words for a kind ─────────────────────────────────────────────────
  function diet(v) { return v > 0.6 ? 'hunter — eats other animals' : v < 0.35 ? 'pollinator — lives on nectar' : 'omnivore — nectar and flesh'; }
  function pattern(v) { return v > 0.66 ? 'spotted' : v > 0.33 ? 'banded' : 'plain'; }
  function lasted(f, nowDay) {
    const end = f.gone == null ? nowDay : f.gone;
    if (end == null) return '—';
    const d = Math.max(0, end - f.born);
    return d < 1 ? 'less than a day' : `${Math.round(d).toLocaleString()} day${Math.round(d) === 1 ? '' : 's'}`;
  }
  function bodyRows(f) {
    const L = f.look || [];
    if (f.kind === 'animal') {
      const [, , , pat, glow, segs, limbs, size, tail, crest, fin, dt] = L;
      return [['Way of life', diet(dt)], ['Body', `${segs} segment${segs === 1 ? '' : 's'}, ${limbs ? limbs + ' pair' + (limbs === 1 ? '' : 's') + ' of legs' : 'no legs'}`],
              ['Moves by', fin > 0.5 ? 'swimming, with broad fins' : limbs ? 'walking and paddling' : 'drifting and wriggling'],
              ['Markings', `${segs > 1 || pat > 0.66 ? pattern(pat) : 'plain'}${crest > 0.25 ? ', crested' : ''}${tail > 0.15 ? ', tailed' : ''}`],
              ['Light', glow > 0.3 ? 'glows brightly at night' : glow > 0.12 ? 'a faint glow at night' : 'none'],
              ['Size', size < 0.4 ? 'small' : size < 0.8 ? 'middling' : 'large']];
    }
    const [, petals, size, height, , , nectar] = L;
    return [['Petals', Math.round(petals)], ['Bloom', size < 1 ? 'small' : size < 1.6 ? 'middling' : 'large'],
            ['Stands', height < 1 ? 'low' : height < 1.5 ? 'medium' : 'tall'],
            ['Nectar', nectar < 0.35 ? 'little' : nectar < 0.7 ? 'some' : 'rich']];
  }

  // ── the cabinet of specimens ─────────────────────────────────────────
  const css = `
  #fossils { position: fixed; z-index: 30; background: var(--cream, #fbf3dc); color: #2a1d14; border-radius: 2.4vmin;
    border: .9vmin solid #ee7d22; box-shadow: 0 0 0 .35vmin #2a1d14, 0 2vmin 5vmin rgba(0,0,0,.55); display: flex; flex-direction: column;
    opacity: 0; transform: translateY(2vmin) scale(.985); transition: opacity .35s, transform .35s; pointer-events: none; overflow: hidden; }
  #fossils.open { opacity: 1; transform: none; pointer-events: auto; }
  #fossils header { padding: 2.2vmin 3vmin 1.2vmin; border-bottom: .3vmin solid #2a1d14; background: #f6e7bf; }
  #fossils h2 { margin: 0; font: 400 3.6vmin "Righteous", sans-serif; letter-spacing: .06em; color: #b9560c; text-transform: uppercase; }
  #fossils .sum { font: 400 1.9vmin/1.4 "IBM Plex Mono", monospace; margin: .4vmin 0 1.2vmin; }
  #fossils .bar { display: flex; flex-wrap: wrap; gap: 1vmin; align-items: center; }
  #fossils .chip { font: 500 1.7vmin "IBM Plex Mono", monospace; letter-spacing: .06em; text-transform: uppercase; padding: .9vmin 1.6vmin;
    border-radius: 3vmin; border: .25vmin solid #2a1d14; background: #fbf3dc; color: #2a1d14; cursor: pointer; }
  #fossils .chip.on { background: #2a1d14; color: #fbf3dc; }
  #fossils .sep { width: .25vmin; height: 3.4vmin; background: rgba(42,29,20,.3); margin: 0 .6vmin; }
  #fossils .x, #fossils .back { position: absolute; top: 1.6vmin; width: 5vmin; height: 5vmin; border-radius: 50%; border: .3vmin solid #2a1d14;
    background: #ee7d22; color: #2a1d14; font: 400 2.8vmin "Righteous", sans-serif; cursor: pointer; line-height: 1; z-index: 2; }
  #fossils .x { right: 1.8vmin; } #fossils .back { right: 8vmin; display: none; }
  #fossils.detail .back { display: block; }
  #fossils.detail .scroll { margin-top: 8.2vmin; border-top: .3vmin solid #2a1d14; padding-top: 2.4vmin; }
  #fossils .scroll { overflow-y: auto; flex: 1; padding: 2vmin 2.6vmin 3vmin; -webkit-overflow-scrolling: touch; }
  #fossils .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(19vmin, 1fr)); gap: 1.6vmin; }
  #fossils .tile { background: #fffaf0; border: .25vmin solid #2a1d14; border-radius: 1.6vmin; padding: 1vmin 1vmin 1.2vmin; cursor: pointer;
    display: flex; flex-direction: column; align-items: center; text-align: center; position: relative; }
  #fossils .tile:active { transform: translateY(.3vmin); }
  #fossils canvas { position: static; inset: auto; display: block; }
  #fossils .tile canvas { width: 15vmin; height: 15vmin; }
  #fossils .tile.gone canvas { filter: sepia(.55) saturate(.7); }
  #fossils .tile b { font: italic 500 2.3vmin/1.15 "Cormorant Garamond", Georgia, serif; margin-top: .4vmin; }
  #fossils .tile small { font: 400 1.45vmin "IBM Plex Mono", monospace; color: #6b5340; margin-top: .3vmin; }
  #fossils .tag { position: absolute; top: .8vmin; left: .8vmin; font: 500 1.2vmin "IBM Plex Mono", monospace; letter-spacing: .1em;
    padding: .3vmin .8vmin; border-radius: 2vmin; border: .2vmin solid #2a1d14; text-transform: uppercase; }
  #fossils .tag.live { background: #a8c94a; } #fossils .tag.dead { background: #d9c6a0; }
  #fossils .more, #fossils .empty { grid-column: 1 / -1; text-align: center; font: 400 1.9vmin "IBM Plex Mono", monospace; padding: 2vmin; color: #6b5340; }
  #fossils .d-top { display: grid; grid-template-columns: 34vmin 1fr; gap: 3vmin; align-items: start; }
  #fossils .d-top canvas { width: 34vmin; height: 34vmin; background: #fffaf0; border: .3vmin solid #2a1d14; border-radius: 2vmin; }
  #fossils .d-top.gone canvas { filter: sepia(.45) saturate(.75); }
  #fossils h3 { margin: 0; font: italic 500 5vmin/1.05 "Cormorant Garamond", Georgia, serif; }
  #fossils .kind { font: 500 1.6vmin "IBM Plex Mono", monospace; letter-spacing: .12em; text-transform: uppercase; color: #8a5a2b; margin: .6vmin 0 1.4vmin; }
  #fossils table { border-collapse: collapse; width: 100%; font: 400 1.95vmin/1.45 "IBM Plex Mono", monospace; }
  #fossils td { padding: .55vmin 0; border-bottom: .15vmin dashed rgba(42,29,20,.25); vertical-align: top; }
  #fossils td:last-child { text-align: right; font-weight: 500; padding-left: 2vmin; }
  #fossils h4 { font: 400 2.2vmin "Righteous", sans-serif; letter-spacing: .08em; text-transform: uppercase; color: #b9560c; margin: 3vmin 0 1.2vmin; }
  #fossils .line { display: flex; gap: 1.2vmin; overflow-x: auto; padding-bottom: 1vmin; align-items: stretch; }
  #fossils .line .tile { flex: 0 0 15vmin; }
  #fossils .line .tile canvas { width: 11vmin; height: 11vmin; }
  #fossils .line .tile b { font-size: 1.9vmin; }
  #fossils .arrow { align-self: center; font: 400 3vmin "Righteous", sans-serif; color: #8a5a2b; }
  #fossils .entry { margin: 0 0 1.6vmin; }
  #fossils .entry b { display: block; font: 500 1.5vmin "IBM Plex Mono", monospace; letter-spacing: .12em; color: #8a5a2b; text-transform: uppercase; }
  #fossils .entry p { margin: .3vmin 0 0; font: italic 400 2.6vmin/1.38 "Cormorant Garamond", Georgia, serif; }
  #fossils p.note { font: 400 1.9vmin/1.5 "IBM Plex Mono", monospace; margin: 0 0 1vmin; color: #4a3626; }
  @media (max-aspect-ratio: 1/1) { #fossils .d-top { grid-template-columns: 1fr; } }`;

  let api = '', root, scroll, grid, sumEl, opts = {}, state = { kind: 'all', status: 'all', sort: 'peak', notable: false },
      items = [], total = 0, loading = false, nowDay = null, idleT = null, isOpen = false, reqNo = 0;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const getJSON = u => fetch(api + u, { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
  const DPR = () => Math.min(window.devicePixelRatio || 1, 2);
  const vmin = () => Math.min(innerWidth, innerHeight) / 100;

  function mount(o) {
    opts = o || {}; api = opts.api || '/darwin/api/algo';
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    root = document.createElement('div'); root.id = 'fossils'; root.setAttribute('role', 'dialog'); root.setAttribute('aria-label', 'The fossil record');
    root.innerHTML = `<button class="back" type="button" aria-label="Back to all specimens">‹</button><button class="x" type="button" aria-label="Close">×</button>
      <header><h2>The fossil record</h2><div class="sum">Opening the archive…</div><div class="bar">
        <button class="chip" data-k="kind" data-v="all">All</button><button class="chip" data-k="kind" data-v="animal">Animals</button><button class="chip" data-k="kind" data-v="plant">Flowers</button>
        <span class="sep"></span><button class="chip" data-k="status" data-v="all">Ever</button><button class="chip" data-k="status" data-v="living">Living</button><button class="chip" data-k="status" data-v="gone">Gone</button>
        <span class="sep"></span><button class="chip" data-k="sort" data-v="peak">Most numerous</button><button class="chip" data-k="sort" data-v="oldest">Oldest</button><button class="chip" data-k="sort" data-v="newest">Newest</button><button class="chip" data-k="sort" data-v="lost">Lately lost</button>
        <span class="sep"></span><button class="chip" data-k="notable" data-v="1">Established only</button>
      </div></header><div class="scroll"><div class="grid"></div></div>`;
    document.body.appendChild(root);
    scroll = root.querySelector('.scroll'); grid = root.querySelector('.grid'); sumEl = root.querySelector('.sum');
    root.querySelector('.x').onclick = close;
    root.querySelector('.back').onclick = () => showList();
    root.querySelector('.bar').addEventListener('click', e => {
      const b = e.target.closest('.chip'); if (!b) return;
      if (b.dataset.k === 'notable') state.notable = !state.notable; else state[b.dataset.k] = b.dataset.v;
      reload();
    });
    scroll.addEventListener('scroll', () => {
      poke();
      if (!root.classList.contains('detail') && scroll.scrollTop + scroll.clientHeight > scroll.scrollHeight - vmin() * 30) more();
    });
    root.addEventListener('pointerdown', poke);
    refreshStrip(); setInterval(refreshStrip, 120000);
  }
  function place(r) { if (!root) return; Object.assign(root.style, { left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px' }); }
  function poke() { clearTimeout(idleT); idleT = setTimeout(close, 120000); }
  function open() {
    if (!root) return;
    isOpen = true; root.classList.add('open'); poke();
    if (!items.length) reload(); else if (root.classList.contains('detail')) {} else syncChips();
    opts.onOpen && opts.onOpen();
  }
  function close() { if (!root) return; isOpen = false; root.classList.remove('open'); clearTimeout(idleT); opts.onClose && opts.onClose(); }
  function syncChips() {
    root.querySelectorAll('.chip').forEach(b => b.classList.toggle('on', b.dataset.k === 'notable' ? state.notable : state[b.dataset.k] === b.dataset.v));
  }
  function query(offset) {
    return `/fossils?kind=${state.kind}&status=${state.status}&sort=${state.sort}${state.notable ? '&notable=1' : ''}&offset=${offset}&limit=48`;
  }
  function reload() {
    syncChips(); showList(); items = []; total = 0; grid.innerHTML = ''; scroll.scrollTop = 0; more(true);
  }
  function summary(c) {
    if (!c) return '';
    return `${c.all.toLocaleString()} kinds have lived on this coast — ${c.animal.toLocaleString()} animals and ${c.plant.toLocaleString()} flowers. ` +
           `${c.living.toLocaleString()} are alive now; ${c.gone.toLocaleString()} are gone. ${c.notable.toLocaleString()} ever grew past eight at once.`;
  }
  function more(first) {
    if (loading || (!first && items.length >= total)) return;
    loading = true; const my = ++reqNo;
    getJSON(query(items.length)).then(d => {
      if (my !== reqNo) return;
      loading = false; total = d.total; sumEl.textContent = summary(d.counts);
      if (d.now_day != null) nowDay = d.now_day;
      const frag = document.createDocumentFragment();
      for (const f of d.items) { items.push(f); frag.appendChild(tile(f, 15)); }
      grid.querySelector('.more') && grid.querySelector('.more').remove();
      grid.appendChild(frag);
      if (!items.length) grid.innerHTML = '<div class="empty">Nothing in the archive matches yet.</div>';
      else if (items.length < total) { const m = document.createElement('div'); m.className = 'more'; m.textContent = `${items.length.toLocaleString()} of ${total.toLocaleString()} — scroll for more`; grid.appendChild(m); }
    }).catch(() => { loading = false; if (my === reqNo) sumEl.textContent = 'The archive could not be opened just now.'; });
  }
  function tile(f, vm) {
    const el = document.createElement('div'); el.className = 'tile' + (f.gone != null ? ' gone' : '');
    const c = portrait(f, vm * vmin(), DPR()); el.appendChild(c);
    el.insertAdjacentHTML('beforeend', `<span class="tag ${f.gone == null ? 'live' : 'dead'}">${f.gone == null ? 'living' : 'gone'}</span>` +
      `<b>${esc(f.name)}</b><small>${f.gone == null ? `since ${DAY_WORD(f.born)}` : `${DAY_WORD(f.born)} – ${Math.floor(f.gone).toLocaleString()}`}</small>`);
    el.onclick = () => showDetail(f.sid);
    return el;
  }
  function showList() {
    root.classList.remove('detail');
    root.querySelector('header').style.display = '';
    if (!grid.isConnected) { scroll.innerHTML = ''; scroll.appendChild(grid); scroll.scrollTop = root._listTop || 0; }
  }
  function showDetail(sid) {
    if (!root.classList.contains('detail')) root._listTop = scroll.scrollTop;
    root.classList.add('detail'); root.querySelector('header').style.display = 'none';
    scroll.innerHTML = '<p class="note">Taking the specimen from its drawer…</p>'; scroll.scrollTop = 0;
    getJSON(`/fossils/${sid}`).then(f => {
      if (f.now_day != null) nowDay = f.now_day;
      const gone = f.gone != null;
      const rows = [['Arose', f.parent == null ? `${DAY_WORD(f.born)} — the first of its line` : DAY_WORD(f.born)],
                    ['Generation at its birth', f.gen.toLocaleString()],
                    [gone ? 'Last seen' : 'Status', gone ? DAY_WORD(f.gone) : 'living now'],
                    [gone ? 'Lasted' : 'So far', lasted(f, nowDay)],
                    ['Most numerous', f.peak ? `${f.peak.toLocaleString()} at once${f.peak_day != null ? ', ' + DAY_WORD(f.peak_day) : ''}` : 'never counted alive'],
                    ['Home', f.zone ? f.zone : '—'], ...bodyRows(f)];
      const wrap = document.createElement('div');
      wrap.innerHTML = `<div class="d-top${gone ? ' gone' : ''}"><div class="pic"></div><div><h3>${esc(f.name)}</h3>
        <div class="kind">${f.kind === 'animal' ? 'Animal' : 'Flower'} · specimen no. ${f.sid.toLocaleString()}${gone ? ' · extinct' : ''}</div>
        <table>${rows.map(([a, b]) => `<tr><td>${esc(a)}</td><td>${esc(b)}</td></tr>`).join('')}</table></div></div>`;
      wrap.querySelector('.pic').appendChild(portrait(f, 34 * vmin(), DPR()));
      // lineage: oldest ancestor on the left, this kind, then the kinds it gave rise to
      const anc = (f.ancestors || []).slice().reverse();
      if (anc.length) {
        const h = document.createElement('h4'); h.textContent = `Descended from (${anc.length} generation${anc.length === 1 ? '' : 's'} of kinds)`; wrap.appendChild(h);
        const line = document.createElement('div'); line.className = 'line';
        anc.forEach((a, i) => {
          if (a.name == null) { line.insertAdjacentHTML('beforeend', '<div class="tile"><b>…</b><small>older than the archive</small></div>'); }
          else line.appendChild(tile(a, 11));
          line.insertAdjacentHTML('beforeend', '<span class="arrow">›</span>');
        });
        line.insertAdjacentHTML('beforeend', `<div class="tile" style="border-width:.45vmin"><b>${esc(f.name)}</b><small>this kind</small></div>`);
        wrap.appendChild(line); setTimeout(() => { line.scrollLeft = line.scrollWidth; }, 0);
      }
      if (f.n_children) {
        const h = document.createElement('h4'); h.textContent = `Gave rise to ${f.n_children.toLocaleString()} kind${f.n_children === 1 ? '' : 's'}`; wrap.appendChild(h);
        const line = document.createElement('div'); line.className = 'line';
        f.children.forEach(k => line.appendChild(tile(k, 11)));
        if (f.n_children > f.children.length) line.insertAdjacentHTML('beforeend', `<div class="tile"><b>+${(f.n_children - f.children.length).toLocaleString()}</b><small>more</small></div>`);
        wrap.appendChild(line);
      }
      const hist = [...(f.events || []).map(e => ({ day: e.day, head: e.kind, text: e.text, sans: true })),
                    ...(f.journal || []).map(j => ({ day: j.day, head: 'the naturalist', text: j.text }))].sort((a, b) => a.day - b.day);
      const h = document.createElement('h4'); h.textContent = 'In the record'; wrap.appendChild(h);
      const story = [{ day: f.born, head: 'arose', text: f.parent == null ? 'Appeared without a known ancestor: one of the founders, a migrant, or a line older than the archive.' : `Split from ${(anc[anc.length - 1] || {}).name || 'an older kind'} when its genes drifted far enough to make it a kind of its own.` }];
      if (f.peak && f.peak_day != null) story.push({ day: f.peak_day, head: 'at its height', text: `${f.peak.toLocaleString()} alive at once${f.zone ? `, most of them in ${f.zone}` : ''}.` });
      story.push(...hist);
      if (gone) story.push({ day: f.gone + 0.001, head: 'gone', text: `The last of its kind died ${lasted(f, nowDay)} after the first was born.${f.n_children ? ' Its line goes on in the kinds that came from it.' : ''}` });
      story.sort((a, b) => a.day - b.day);
      wrap.insertAdjacentHTML('beforeend', story.map(e => `<div class="entry"><b>${esc(DAY_WORD(e.day))} · ${esc(e.head)}</b><p>${esc(e.text)}</p></div>`).join(''));
      scroll.innerHTML = ''; scroll.appendChild(wrap);
    }).catch(() => { scroll.innerHTML = '<p class="note">This specimen could not be found.</p>'; });
  }

  // ── the tray window: a slow procession of imprints, oldest on the left ─
  let strip = [], stripCache = new Map(), stripPx = 0;
  function refreshStrip() {
    getJSON('/fossils?notable=1&sort=newest&limit=36').then(d => {
      if (d.now_day != null) nowDay = d.now_day;
      strip = d.items.slice().reverse();
    }).catch(() => {});
  }
  function drawStrip(g, x, y, w, h, t) {
    if (!strip.length) return false;
    const sz = Math.round(h * 0.74);
    if (sz !== stripPx) { stripCache.clear(); stripPx = sz; }
    const step = sz * 0.92, span = strip.length * step, off = (t * sz * 0.09) % span;
    g.save();
    for (let i = 0; i < strip.length; i++) {
      let px = x + w - span + i * step - off + step * 0.5;
      while (px < x - step) px += span;
      while (px > x + w + step) px -= span;
      if (px < x - step || px > x + w + step) continue;
      const f = strip[i]; let c = stripCache.get(f.sid);
      if (!c) { c = portrait(f, sz, 1, { fossil: true }); stripCache.set(f.sid, c); }
      g.globalAlpha = f.gone == null ? 0.95 : 0.7;
      g.drawImage(c, px - sz / 2, y + (h - sz) / 2, sz, sz);
    }
    g.restore();
    return true;
  }

  window.AlgoFossils = { mount, open, close, place, drawStrip, isOpen: () => isOpen, specimen, portrait };
})();
