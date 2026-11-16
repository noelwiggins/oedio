/* Algogenesis — the nameplate as a switch: touch the white pill and every panel is listed; touch one to go there.

     AlgoSwitch.toggle({ anchor: {x, y, w, h} in CSS px, current: 'coast' | slug, onAbout: fn })

   The list follows an arc, from the cosmos to people, with the Coast (Algogenesis) first. On the dark side each
   panel goes by its reverse name. The side you are on is kept (it is remembered across panels), and so is each
   panel's own zoom. Keys: ↑ ↓ to move, Enter to go, Esc to close. */
(function () {
  'use strict';
  const PANELS = [
    ['coast', 'Algogenesis', 'Algolysis', 'Life evolving on a coast: plants, animals, fungi'],
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
  const href = slug => slug === 'coast' ? '/darwin/algogenesis/panel' : `/darwin/algogenesis/${slug}/panel`;
  // the page each panel sits in (its title, description and stats around the panel's frame)
  const pageHref = slug => slug === 'coast' ? '/darwin/algogenesis/coast' : `/darwin/algogenesis/${slug}`;
  // shown inside one of those pages? then the whole page changes, not just the frame
  function hostPage() {
    try { if (window.top !== window && window.top.location.origin === location.origin) return window.top; } catch (e) {}
    return null;
  }

  const css = `
  #algo-switch { position: fixed; z-index: 60; background: var(--cream, #fbf3dc); color: var(--ink, #2a1d14);
    border-radius: 2.4vmin; padding: 1.4vmin; box-shadow: 0 1.6vmin 5vmin rgba(0,0,0,.45), 0 0 0 .3vmin var(--ink, #2a1d14);
    width: min(92vw, 118vmin); max-height: 72vh; overflow-y: auto; overscroll-behavior: contain;
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

  let el = null, opts = null, closedAt = 0;
  function build() {
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    el = document.createElement('nav'); el.id = 'algo-switch'; el.setAttribute('aria-label', 'Panels');
    document.body.appendChild(el);
    // close on a touch anywhere else, or Esc; arrows move between panels
    addEventListener('pointerdown', e => { if (isOpen() && !el.contains(e.target)) { close(); closedAt = performance.now(); } }, true);
    addEventListener('keydown', e => {
      if (!isOpen()) return;
      if (e.key === 'Escape') { e.preventDefault(); close(); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault(); e.stopImmediatePropagation();
        const items = [...el.querySelectorAll('a, button')], i = items.indexOf(document.activeElement);
        items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus();
      }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') e.stopImmediatePropagation();   // not a turn while choosing
    }, true);
  }
  function isOpen() { return !!el && el.classList.contains('open'); }
  function render() {
    const dark = window.AlgoLysis && AlgoLysis.isDark();
    el.innerHTML = '<div class="grid">' + PANELS.map(([slug, name, lname, desc]) =>
      `<a href="${href(slug)}" data-slug="${slug}"${slug === opts.current ? ' class="here" aria-current="page"' : ''}>` +
      `<span class="n">${dark ? lname : name}</span><span class="d">${dark ? name + ' · ' : ''}${desc}</span></a>`).join('') +
      '</div><div class="about"><button type="button">About this panel</button></div>';
    el.querySelectorAll('a').forEach(a => a.addEventListener('click', e => {
      e.preventDefault();
      if (a.dataset.slug === opts.current) { close(); return; }
      document.body.classList.add('algo-leaving');                  // a short fade, then the next panel
      const host = hostPage();
      setTimeout(() => {
        if (host) host.location.href = pageHref(a.dataset.slug);    // the page around it moves too: title, story, stats
        else location.href = a.getAttribute('href');
      }, 200);
    }));
    el.querySelector('.about button').addEventListener('click', () => { close(); if (opts.onAbout) opts.onAbout(); });
  }
  function place() {
    const a = opts.anchor, r = el.getBoundingClientRect(), m = 8;
    let x = a.x + a.w / 2 - r.width / 2, y = a.y - r.height - 12;
    if (y < m) y = Math.min(innerHeight - r.height - m, a.y + a.h + 12);   // no room above: open below the pill
    x = Math.max(m, Math.min(innerWidth - r.width - m, x));
    el.style.left = x + 'px'; el.style.top = Math.max(m, y) + 'px';
  }
  function open(o) {
    opts = o; if (!el) build();
    render(); el.style.left = '-9999px'; el.style.top = '0px';
    requestAnimationFrame(() => { place(); el.classList.add('open'); const h = el.querySelector('a.here') || el.querySelector('a'); h && h.focus({ preventScroll: true }); h && h.scrollIntoView({ block: 'nearest' }); });
  }
  function close() { if (el) el.classList.remove('open'); }
  function toggle(o) { if (isOpen()) close(); else if (performance.now() - closedAt > 350) open(o); }
  window.AlgoSwitch = { open, close, toggle, isOpen, panels: PANELS };
})();
