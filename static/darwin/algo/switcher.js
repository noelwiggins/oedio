/* Algogenesis — the nameplate as a switch: touch the white pill and every panel is listed; touch one to go there.

     AlgoSwitch.toggle({ anchor: {x, y, w, h} in CSS px, current: 'coast' | slug, onAbout: fn })

   The list follows an arc, from the cosmos to people, with the Coast (Algogenesis) first. On the dark side each
   panel goes by its reverse name. The side you are on is kept (it is remembered across panels), and so is each
   panel's own zoom. Keys: ↑ ↓ to move, Enter to go, Esc to close. */
(function () {
  'use strict';
  const PANELS = [
    ['coast', 'Algogenesis', 'Algolysis', 'Life evolving on a coast: plants, animals, fungi'],
    ['folkpop', 'Folk Pop Coast', 'Folk Pop Algolysis', 'The same coast, as a folk-pop fable'],
    ['cosmogenesis', 'Cosmogenesis', 'Cosmophthora', 'The coming into existence of the cosmos'],
    ['protogenesis', 'Protogenesis', 'Protophthora', 'First origin or initial formation'],
    ['biogenesis', 'Biogenesis', 'Biophthora', 'Life arising from preexisting life'],
    ['autopoiesis', 'Autopoiesis', 'Autolysis', "A system's ability to produce and maintain itself"],
    ['morphogenesis', 'Morphogenesis', 'Morpholysis', 'The process by which form and structure develop'],
    ['epigenesis', 'Epigenesis', 'Epilysis', 'Development through successive stages of differentiation'],
    ['ontogeny', 'Ontogeny', 'Ontolysis', 'The development of an organism from its earliest stages'],
    ['palingenesis', 'Palingenesis', 'Palinphthora', 'Rebirth, regeneration, or recreation'],
    ['anagenesis', 'Anagenesis', 'Anaphthora', 'Evolutionary transformation within a lineage'],
    ['noogenesis', 'Noogenesis', 'Noolysis', 'Emergence or evolution of mind and consciousness'],
    ['psychogenesis', 'Psychogenesis', 'Psycholysis', 'The origin and development of psychological processes'],
    ['anthropogenesis', 'Anthropogenesis', 'Anthropophthora', 'The origin and development of humanity'],
  ];
  const href = slug => slug === 'coast' ? '/darwin/algogenesis/panel' : `/darwin/algogenesis/${slug}/panel`;   // folkpop too
  // the page each panel sits in (its title, description and stats around the panel's frame)
  const pageHref = slug => slug === 'coast' ? '/darwin/algogenesis/coast' : `/darwin/algogenesis/${slug}`;   // and /folkpop
  // shown inside one of those pages? then the whole page changes, not just the frame
  function hostPage() {
    try { if (window.top !== window && window.top.location.origin === location.origin) return window.top; } catch (e) {}
    return null;
  }

  const css = `
  #algo-switch { position: fixed; z-index: 80; background: var(--cream, #fbf3dc); color: var(--ink, #2a1d14);
    border-radius: 2.4vmin; padding: 1.4vmin; box-shadow: 0 1.6vmin 5vmin rgba(0,0,0,.45), 0 0 0 .3vmin var(--ink, #2a1d14);
    width: min(92vw, 118vmin); max-height: 72vh; overflow-y: auto; overscroll-behavior: contain; touch-action: pan-y;
    -webkit-overflow-scrolling: touch;
    transform-origin: 50% 100%; opacity: 0; transform: translateY(1.2vmin) scale(.96); pointer-events: none;
    transition: opacity .18s ease, transform .22s cubic-bezier(.2,.8,.3,1.1); }
  #algo-switch.open { opacity: 1; transform: none; pointer-events: auto; }
  #algo-switch .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 36vmin), 1fr)); gap: .6vmin; }
  #algo-switch a, #algo-switch button { display: block; text-align: left; text-decoration: none; color: inherit; font: inherit;
    background: transparent; border: 0; border-radius: 1.6vmin; padding: 1.2vmin 1.6vmin; cursor: pointer; min-height: 48px; }
  #algo-switch a:hover, #algo-switch a:focus-visible, #algo-switch button:hover, #algo-switch button:focus-visible {
    background: rgba(42,29,20,.08); outline: none; }
  #algo-switch a:focus-visible, #algo-switch button:focus-visible { box-shadow: inset 0 0 0 .3vmin var(--rim, #c0392b); }
  #algo-switch .n { display: block; font: 400 clamp(15px, 2.7vmin, 30px) "Righteous", sans-serif; letter-spacing: .05em; text-transform: uppercase; }
  #algo-switch .d { display: block; font-size: clamp(11px, 1.7vmin, 18px); opacity: .7; margin-top: .3vmin; line-height: 1.3; }
  #algo-switch a.here { background: var(--ink, #2a1d14); color: var(--cream, #fbf3dc); }
  #algo-switch a.here .d { opacity: .8; }
  #algo-switch .about { margin-top: .8vmin; border-top: .2vmin solid rgba(42,29,20,.18); padding-top: .8vmin; }
  #algo-switch .about button { width: 100%; font: 400 clamp(13px, 2vmin, 22px) "Righteous", sans-serif; letter-spacing: .06em;
    text-transform: uppercase; color: var(--rim, #c0392b); }
  body.algo-leaving { transition: opacity .22s ease; opacity: 0; }
  @media (prefers-reduced-motion: reduce) { #algo-switch { transition: none; } body.algo-leaving { transition: none; } }`;

  // where the list lives: in the page around the panel when there is one (so it can use the whole screen, above the
  // page's header and bars), otherwise in the panel itself
  let el = null, opts = null, closedAt = 0, openedAt = 0, W = window;
  function target() { return hostPage() || window; }
  function build(Wn) {
    W = Wn; const D = W.document;
    const st = D.createElement('style'); st.textContent = css; D.head.appendChild(st);
    if (W !== window && !D.querySelector('link[href*="family=Righteous"]')) {      // the panel's lettering, for the page too
      const lk = D.createElement('link'); lk.rel = 'stylesheet'; lk.href = 'https://fonts.googleapis.com/css2?family=Righteous&display=swap'; D.head.appendChild(lk);
    }
    el = D.createElement('nav'); el.id = 'algo-switch'; el.setAttribute('aria-label', 'Panels');
    D.body.appendChild(el);
    // close on a touch anywhere else (in the page or in the panel), or Esc; arrows move between panels
    const outside = e => { if (isOpen() && !el.contains(e.target)) { close(); closedAt = performance.now(); } };
    W.addEventListener('pointerdown', outside, true);
    if (W !== window) window.addEventListener('pointerdown', outside, true);
    const keys = e => {
      if (!isOpen()) return;
      if (e.key === 'Escape') { e.preventDefault(); close(); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault(); e.stopImmediatePropagation();
        const items = [...el.querySelectorAll('a, button')], i = items.indexOf(W.document.activeElement);
        items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus();
      }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') e.stopImmediatePropagation();   // not a turn while choosing
    };
    W.addEventListener('keydown', keys, true);
    if (W !== window) window.addEventListener('keydown', keys, true);
    W.addEventListener('scroll', () => { if (isOpen() && performance.now() - openedAt > 600) close(); }, { passive: true });   // the page scrolled away from it
  }
  function isOpen() { return !!el && el.classList.contains('open'); }
  function render() {
    const dark = window.AlgoLysis && AlgoLysis.isDark();
    el.innerHTML = '<div class="grid">' + PANELS.map(([slug, name, lname, desc]) =>
      `<a href="${W === window ? href(slug) : pageHref(slug)}" data-slug="${slug}"${slug === opts.current ? ' class="here" aria-current="page"' : ''}>` +
      `<span class="n">${dark ? lname : name}</span><span class="d">${dark ? name + ' · ' : ''}${desc}</span></a>`).join('') +
      '</div><div class="about"><button type="button">About this panel</button></div>';
    el.querySelectorAll('a').forEach(a => a.addEventListener('click', e => {
      e.preventDefault();
      if (a.dataset.slug === opts.current) { close(); return; }
      W.document.body.classList.add('algo-leaving');                // a short fade, then the next panel
      setTimeout(() => {
        if (W !== window) W.location.href = pageHref(a.dataset.slug);  // the page around it moves too: title, story, stats
        else location.href = a.getAttribute('href');
      }, 200);
    }));
    el.querySelector('.about button').addEventListener('click', () => { close(); if (opts.onAbout) opts.onAbout(); });
  }
  // the screen space the list may use: inside a page, between its sticky header and any bottom bar
  function visibleBand() {
    const band = { top: 0, bottom: W.innerHeight };
    try {
      const d = W.document, bar = d.querySelector('.dw-bar'), bot = d.querySelector('.dw-bottom');
      if (bar) band.top = Math.max(0, bar.getBoundingClientRect().bottom);
      if (bot && W.getComputedStyle(bot).display !== 'none') band.bottom = Math.min(band.bottom, bot.getBoundingClientRect().top);
    } catch (e) {}
    return band;
  }
  // the pill's rectangle in the coordinates of the window the list lives in
  function anchorRect() {
    const a = opts.anchor;
    if (W === window || !window.frameElement) return a;
    const fr = window.frameElement.getBoundingClientRect();
    return { x: fr.x + a.x, y: fr.y + a.y, w: a.w, h: a.h };
  }
  function place() {
    const m = 8;
    let a = anchorRect(), band = visibleBand();
    if (W !== window && (a.y < band.top || a.y + a.h > band.bottom)) {     // the pill itself is off screen: bring it in
      try { window.frameElement.scrollIntoView({ block: 'end', behavior: 'instant' }); } catch (e) {}
      a = anchorRect(); band = visibleBand();
    }
    el.style.maxHeight = '';
    const full = el.scrollHeight + 4, roomAbove = a.y - 12 - (band.top + m), roomAll = band.bottom - band.top - 2 * m;
    el.style.maxHeight = Math.max(160, Math.min(full, roomAbove >= Math.min(full, 320) ? roomAbove : roomAll)) + 'px';
    const r = el.getBoundingClientRect();
    // just above the pill, kept inside the band (over the pill if there is no room above it)
    const y = Math.max(band.top + m, Math.min(band.bottom - r.height - m, a.y - r.height - 12));
    const x = Math.max(m, Math.min(W.innerWidth - r.width - m, a.x + a.w / 2 - r.width / 2));
    el.style.left = x + 'px'; el.style.top = y + 'px';
  }
  function open(o) {
    opts = o; if (!el) build(target());
    render(); el.style.left = '-9999px'; el.style.top = '0px';
    requestAnimationFrame(() => {
      openedAt = performance.now(); place(); el.classList.add('open');
      const h = el.querySelector('a.here') || el.querySelector('a');
      if (h) { h.focus({ preventScroll: true }); el.scrollTop = Math.max(0, h.offsetTop - el.clientHeight / 2 + h.offsetHeight / 2); }   // only the list scrolls
    });
  }
  function close() { if (el) el.classList.remove('open'); }
  function toggle(o) { if (isOpen()) close(); else if (performance.now() - closedAt > 350) open(o); }
  window.AlgoSwitch = { open, close, toggle, isOpen, panels: PANELS };
})();
