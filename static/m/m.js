/* Oedio mobile app. Hash routes:
   #/                       library shelves      #/book/<slug>          a book and its editions
   #/vols/<slug>/<group>    volumes of a set     #/read/<slug>/<work>/<n>[?page=P]  reader
   #/search?q=…&tab=books|pages                  #/saved                                     */
(function () {
  'use strict';
  var view = document.getElementById('view'), topbar = document.getElementById('topbar');
  var cache = {}, YEAR = new Date().getFullYear();

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function get(url) {
    if (cache[url]) return Promise.resolve(cache[url]);
    return fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) { cache[url] = d; return d; });
  }
  function qs(hash) { var o = {}, i = hash.indexOf('?'); if (i < 0) return o; hash.slice(i + 1).split('&').forEach(function (kv) { var p = kv.split('='); if (p[0]) o[decodeURIComponent(p[0])] = decodeURIComponent((p[1] || '').replace(/\+/g, ' ')); }); return o; }
  function words(q) { return (q || '').toLowerCase().match(/[\p{L}\p{N}]+/gu) || []; }
  function hl(text, ws) {
    var h = esc(text);
    (ws || []).forEach(function (w) { if (w.length < 2) return; h = h.replace(new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi'), '<mark>$1</mark>'); });
    return h;
  }
  function spineBg(s) { return s || 'linear-gradient(160deg,#4a4f63,#262938)'; }
  var store = {
    read: function () { try { return JSON.parse(localStorage.getItem('oedio_saved') || '[]'); } catch (e) { return []; } },
    write: function (d) { try { localStorage.setItem('oedio_saved', JSON.stringify(d)); } catch (e) {} }
  };
  function isSaved(key) { return store.read().some(function (x) { return x.key === key; }); }
  function toggleSaved(item) {
    var d = store.read(), i = d.findIndex(function (x) { return x.key === item.key; });
    if (i >= 0) d.splice(i, 1); else d.unshift(item);
    store.write(d); return i < 0;
  }

  var ICON = {
    back: '<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg>',
    save: '<svg viewBox="0 0 24 24"><path d="M6 3h12v18l-6-4-6 4z"/></svg>',
    search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/></svg>'
  };
  function bar(title, back, right) {
    topbar.innerHTML = (back ? '<button class="icon-btn" data-back aria-label="Back">' + ICON.back + '</button>' : '') +
      '<div class="title">' + esc(title || '') + '</div>' + (right || '');
    var b = topbar.querySelector('[data-back]');
    if (b) b.onclick = function () { if (history.length > 1) history.back(); else location.hash = back; };
  }
  function noBar() { topbar.innerHTML = ''; }
  function nav(which) { document.querySelectorAll('#navbar a').forEach(function (a) { a.classList.toggle('on', a.getAttribute('data-nav') === which); }); }
  function foot() { return '<div class="foot"><span>© ' + YEAR + ' Noel Wiggins. All rights reserved.</span><a href="/?view=full">Full site</a></div>'; }
  function loading() { view.innerHTML = '<div class="loading">Loading…</div>'; }
  function searchBox(q, ph) {
    return '<form class="searchbar" role="search" id="sform">' + ICON.search + '<input id="sinput" type="search" enterkeyhint="search" autocomplete="off" placeholder="' + esc(ph || 'Search every page in the library') + '" value="' + esc(q) + '" aria-label="Search">' +
      (q ? '<button type="button" class="clear" aria-label="Clear">×</button>' : '') + '</form>';
  }
  function wireSearch() {
    var f = document.getElementById('sform'), inp = document.getElementById('sinput');
    f.onsubmit = function (e) { e.preventDefault(); var v = inp.value.trim(); if (v.length > 1) location.hash = '#/search?q=' + encodeURIComponent(v); inp.blur(); };
    var c = f.querySelector('.clear'); if (c) c.onclick = function () { inp.value = ''; inp.focus(); };
  }

  // ── lightbox ──────────────────────────────────────────────────────────
  var lb = document.getElementById('lightbox'), lbScroll = lb.querySelector('.lb-scroll'), lbImg = lb.querySelector('img');
  function openLightbox(src, alt) { lbImg.src = src; lbImg.alt = alt || ''; lbScroll.classList.remove('zoom'); lb.hidden = false; document.body.style.overflow = 'hidden'; history.pushState({ lb: 1 }, ''); }
  function closeLightbox(fromPop) { if (lb.hidden) return; lb.hidden = true; document.body.style.overflow = ''; if (!fromPop) history.back(); }
  lb.querySelector('.lb-close').onclick = function () { closeLightbox(false); };
  var lastTap = 0;
  lbScroll.addEventListener('click', function (e) {
    var now = Date.now();
    if (now - lastTap < 320) {
      var zoom = !lbScroll.classList.contains('zoom'), r = lbImg.getBoundingClientRect(), fx = (e.clientX - r.left) / r.width, fy = (e.clientY - r.top) / r.height;
      lbScroll.classList.toggle('zoom', zoom);
      if (zoom) { lbScroll.scrollLeft = fx * lbImg.width - lbScroll.clientWidth / 2; lbScroll.scrollTop = fy * lbImg.height - lbScroll.clientHeight / 2; }
    }
    lastTap = now;
  });
  view.addEventListener('click', function (e) { var z = e.target.closest('[data-zoom]'); if (z) { e.preventDefault(); openLightbox(z.src, z.alt); } });

  // ── library ───────────────────────────────────────────────────────────
  function home() {
    nav('library'); noBar(); loading();
    get('/api/m/library').then(function (d) {
      view.innerHTML = '<div class="wordmark">Oedio</div><p class="lede">Rare books read page by page, beside the original scans, with transcriptions and English translations.</p>' +
        searchBox('') +
        d.sections.map(function (s) {
          return '<div class="shelf-head"><h2>' + esc(s.title) + '</h2><span>' + s.books.length + (s.books.length === 1 ? ' book' : ' books') + '</span></div>' +
            '<p class="shelf-note">' + esc(s.description || '') + '</p><div class="shelf">' +
            s.books.map(function (b, i) {
              var h = 168 + ((b.title.length * 7 + i * 13) % 46);
              return '<a class="spine" href="#/book/' + esc(b.slug) + '" style="height:' + h + 'px;background:' + esc(spineBg(b.spine)) + '" aria-label="' + esc(b.title + (b.author ? ', ' + b.author : '')) + '">' +
                '<b>' + esc(b.title) + '</b>' + (b.author && b.author.length < 22 ? '<i>' + esc(b.author) + '</i>' : '') + '</a>';
            }).join('') + '</div>';
        }).join('') + foot();
      wireSearch();
    }).catch(function () { view.innerHTML = '<div class="empty"><b>The library could not be loaded</b>Check your connection and try again.</div>'; });
  }

  function workRow(slug, w) {
    var tags = [];
    if (w.facsimile) tags.push('<span class="tag">Scan</span>');
    (w.layers || []).forEach(function (l) { tags.push('<span class="tag ' + (l === 'English' ? 'en' : '') + '">' + esc(l) + '</span>'); });
    var href = w.volumes ? '#/vols/' + slug + '/' + encodeURIComponent(w.group) : '#/read/' + slug + '/' + encodeURIComponent(w.slug) + '/1';
    return '<a class="row" href="' + href + '"><div class="txt"><div class="nm">' + esc(w.volumes ? w.title : w.title) + '</div>' +
      '<div class="sub">' + esc([w.contributor, w.year].filter(Boolean).join(', ')) + (w.volumes ? ', ' + w.volumes.length + ' volumes' : '') + '</div>' +
      (tags.length ? '<div class="tags">' + tags.join('') + '</div>' : '') + '</div></a>';
  }

  function book(slug) {
    nav('library'); bar('', '#/'); loading();
    get('/api/m/book/' + encodeURIComponent(slug)).then(function (b) {
      bar('', '#/');
      var roles = [], byRole = {};
      b.works.forEach(function (w) { var r = w.role || 'Editions'; if (!byRole[r]) { byRole[r] = []; roles.push(r); } byRole[r].push(w); });
      var many = b.works.length > 10;
      view.innerHTML = '<div class="bookhero" style="background:' + esc(spineBg(b.spine)) + '"><div class="sect">' + esc(b.section || '') + '</div><h1>' + esc(b.title) + '</h1>' +
        (b.author ? '<div class="by">' + esc(b.author) + '</div>' : '') + '</div>' +
        (b.default ? '<a class="btn block" href="#/read/' + esc(b.slug) + '/' + encodeURIComponent(b.default) + '/1">Start reading</a>' : '') +
        (b.overview || b.description ? '<p class="prose clamp" id="ov">' + esc(b.overview || b.description) + '</p><button class="btn text" id="ovmore">Read more</button>' : '') +
        '<h2 class="sec">' + b.works.length + (b.works.length === 1 ? ' work' : ' works') + ' in this collection</h2>' +
        (many ? '<input class="filter" id="wfilter" type="search" placeholder="Find a work in this collection" aria-label="Find a work">' +
          (roles.length > 1 ? '<div class="chips" id="rchips"><button class="chip on" data-r="">All</button>' + roles.map(function (r) { return '<button class="chip" data-r="' + esc(r) + '">' + esc(r) + '</button>'; }).join('') + '</div>' : '') : '') +
        '<div id="works"></div>' + foot();
      var role = '', term = '';
      function render() {
        var html = '';
        roles.forEach(function (r) {
          if (role && r !== role) return;
          var ws = byRole[r].filter(function (w) { return !term || ((w.title || '') + ' ' + (w.contributor || '') + ' ' + (w.year || '')).toLowerCase().indexOf(term) >= 0; });
          if (!ws.length) return;
          html += (roles.length > 1 ? '<h2 class="sec" style="font-size:17px;margin-top:22px">' + esc(r) + '</h2>' : '') + '<div class="list">' + ws.map(function (w) { return workRow(b.slug, w); }).join('') + '</div>';
        });
        document.getElementById('works').innerHTML = html || '<div class="empty">No works match.</div>';
      }
      render();
      var ov = document.getElementById('ovmore');
      if (ov) ov.onclick = function () { document.getElementById('ov').classList.remove('clamp'); ov.remove(); };
      var wf = document.getElementById('wfilter'); if (wf) wf.oninput = function () { term = wf.value.trim().toLowerCase(); render(); };
      var rc = document.getElementById('rchips');
      if (rc) rc.onclick = function (e) { var c = e.target.closest('.chip'); if (!c) return; role = c.getAttribute('data-r'); rc.querySelectorAll('.chip').forEach(function (x) { x.classList.toggle('on', x === c); }); render(); };
    }).catch(function () { view.innerHTML = '<div class="empty"><b>This book could not be loaded</b><a href="#/">Back to the library</a></div>'; });
  }

  function volumes(slug, group) {
    nav('library'); bar('', '#/book/' + slug); loading();
    get('/api/m/book/' + encodeURIComponent(slug)).then(function (b) {
      var g = b.works.find(function (w) { return w.group === group; });
      if (!g) { view.innerHTML = '<div class="empty"><b>Not found</b></div>'; return; }
      bar(g.title, '#/book/' + slug);
      view.innerHTML = '<p class="dim" style="margin-top:4px">' + esc([g.contributor, g.year].filter(Boolean).join(', ')) + '</p><div class="list">' +
        g.volumes.map(function (v) { return workRow(slug, Object.assign({}, v, { title: v.volume_label || v.title })); }).join('') + '</div>' + foot();
    });
  }

  // ── search ────────────────────────────────────────────────────────────
  function search(params) {
    var q = params.q || '', tab = params.tab || 'pages', ws = words(q);
    nav('search'); noBar();
    view.innerHTML = '<div style="height:calc(env(safe-area-inset-top) + 16px)"></div>' + searchBox(q) + '<div id="sres"></div>';
    wireSearch();
    if (!q) {
      document.getElementById('sres').innerHTML = '<div class="empty"><b>Search the whole library</b>Every page of every book is searchable: try a plant, a place, a person or a phrase.</div>';
      document.getElementById('sinput').focus();
      return;
    }
    document.getElementById('sres').innerHTML = '<div class="loading">Searching…</div>';
    Promise.all([get('/api/search?q=' + encodeURIComponent(q)), get('/api/search/fulltext?q=' + encodeURIComponent(q)).catch(function () { return { results: [] }; })]).then(function (r) {
      var books = r[0].results || [], pages = r[1].results || [];
      if (!books.length && !pages.length) { document.getElementById('sres').innerHTML = '<div class="empty"><b>Nothing found for “' + esc(q) + '”</b>Try fewer or different words.</div>'; return; }
      if (tab === 'pages' && !pages.length) tab = 'books';
      var body = tab === 'books'
        ? books.map(function (b) { return '<a class="hit" href="#/book/' + esc(b.slug) + '"><h3>' + hl(b.title, ws) + '</h3><div class="src">' + esc(b.author || '') + '</div><p>' + hl(b.snippet, ws) + '</p></a>'; }).join('')
        : pages.map(function (h) {
          return '<a class="hit" href="#/read/' + esc(h.megabook_slug) + '/' + encodeURIComponent(h.component_slug) + '/1?page=' + h.page + '"><div class="src">' + esc(h.megabook_title) + '</div>' +
            '<h3>' + esc(h.component_title) + ', page ' + esc(h.page) + '</h3><p>' + hl(h.snippet, ws) + '</p></a>';
        }).join('');
      document.getElementById('sres').innerHTML = '<div class="seg" role="tablist"><button data-tab="pages" class="' + (tab === 'pages' ? 'on' : '') + '">Pages ' + pages.length + '</button>' +
        '<button data-tab="books" class="' + (tab === 'books' ? 'on' : '') + '">Books ' + books.length + '</button></div>' + body;
      document.querySelectorAll('.seg button').forEach(function (bt) { bt.onclick = function () { history.replaceState(null, '', '#/search?q=' + encodeURIComponent(q) + '&tab=' + bt.getAttribute('data-tab')); route(); }; });
    }).catch(function () { document.getElementById('sres').innerHTML = '<div class="empty"><b>Search is unavailable right now</b>Check your connection and try again.</div>'; });
  }

  // ── reader ────────────────────────────────────────────────────────────
  var layerPref = '';
  function reader(slug, work, n, params) {
    document.body.classList.add('reading'); nav('');
    var url = '/api/m/read/' + encodeURIComponent(slug) + '/' + encodeURIComponent(work) + '/' + (parseInt(n, 10) || 1) + (params.page ? '?page=' + encodeURIComponent(params.page) : '');
    if (!view.querySelector('.rd-img, .rd-text')) loading();
    get(url).then(function (d) {
      if (!d.total) { bar('', '#/book/' + slug); view.innerHTML = '<div class="empty"><b>This work has no pages yet</b></div>'; return; }
      if (params.page) history.replaceState(null, '', '#/read/' + slug + '/' + encodeURIComponent(work) + '/' + d.index);
      var key = slug + '/' + work + '/' + d.index, saved = isSaved(key);
      bar(d.work.title, '#/book/' + slug, '<button class="icon-btn ' + (saved ? 'on' : '') + '" id="savebtn" aria-label="Save page">' + ICON.save + '</button>');
      document.getElementById('savebtn').onclick = function () {
        this.classList.toggle('on', toggleSaved({ key: key, title: d.work.title, book: d.book.title, label: d.label || ('Page ' + d.page) }));
      };
      // text layers: the page's own text, then any aligned transcription / translation
      var options = [];
      if (d.text && d.text !== '—') options.push({ label: d.layers.length ? 'Page text' : 'Text', text: d.text });
      d.layers.forEach(function (l) { options.push({ label: l.label, text: l.text }); });
      var hasEnglish = options.some(function (o) { return o.label === 'English'; });
      var pick = options.find(function (o) { return o.label === layerPref; }) || (hasEnglish ? options.find(function (o) { return o.label === 'English'; }) : options[0]);
      var label = d.label || ('Page ' + d.page);
      function textHtml(o) {
        if (!o) return '<p class="rd-empty">No text on this page. Tap the image to look closer.</p>';
        var t = (o.text || '').trim();
        if (!t || t === '—') return '<p class="rd-empty">No text on this page' + (o.label !== 'Text' && o.label !== 'Page text' ? ' in this layer' : '') + '. Tap the image to look closer.</p>';
        return '<p class="rd-text">' + esc(t) + '</p>' + (/English|Original/.test(o.label) ? '<p class="rd-note">AI ' + (o.label === 'English' ? 'translation' : 'transcription') + ' from the page image. Read it against the scan.</p>' : '');
      }
      view.innerHTML = (d.image && !d.work.text_only ? '<img class="rd-img" src="' + esc(d.image) + '" alt="' + esc(label) + '" data-zoom>' : '') +
        '<div class="rd-meta"><span>' + esc(label) + '</span><span>' + d.index + ' of ' + d.total + '</span></div>' +
        (options.length > 1 ? '<div class="seg">' + options.map(function (o) { return '<button data-l="' + esc(o.label) + '" class="' + (o === pick ? 'on' : '') + '">' + esc(o.label) + '</button>'; }).join('') + '</div>' : '') +
        '<div id="rdt">' + textHtml(pick) + '</div>' +
        '<div class="rd-bar"><button class="btn tonal" id="prev"' + (d.index > 1 ? '' : ' disabled') + '>Previous</button>' +
        '<input type="range" min="1" max="' + d.total + '" value="' + d.index + '" aria-label="Go to page">' +
        '<button class="btn" id="next"' + (d.index < d.total ? '' : ' disabled') + '>Next</button></div>';
      window.scrollTo(0, 0);
      view.querySelectorAll('.seg button').forEach(function (bt) {
        bt.onclick = function () {
          layerPref = bt.getAttribute('data-l');
          view.querySelectorAll('.seg button').forEach(function (x) { x.classList.toggle('on', x === bt); });
          document.getElementById('rdt').innerHTML = textHtml(options.find(function (o) { return o.label === layerPref; }));
        };
      });
      function go(i) { location.replace('#/read/' + slug + '/' + encodeURIComponent(work) + '/' + i); }
      document.getElementById('prev').onclick = function () { if (d.index > 1) go(d.index - 1); };
      document.getElementById('next').onclick = function () { if (d.index < d.total) go(d.index + 1); };
      var range = view.querySelector('input[type=range]'); range.onchange = function () { go(parseInt(range.value, 10)); };
      var img = view.querySelector('.rd-img');
      if (img) {
        var sx = 0, sy = 0;
        img.addEventListener('touchstart', function (e) { sx = e.touches[0].clientX; sy = e.touches[0].clientY; }, { passive: true });
        img.addEventListener('touchend', function (e) {
          var dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
          if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) { if (dx < 0 && d.index < d.total) go(d.index + 1); if (dx > 0 && d.index > 1) go(d.index - 1); }
        }, { passive: true });
      }
      if (d.index < d.total) get('/api/m/read/' + encodeURIComponent(slug) + '/' + encodeURIComponent(work) + '/' + (d.index + 1)).then(function (nx) { if (nx.image) { var pre = new Image(); pre.src = nx.image; } }).catch(function () {});
    }).catch(function () { view.innerHTML = '<div class="empty"><b>This page could not be loaded</b>Check your connection and try again.</div>'; });
  }

  function saved() {
    nav('saved'); bar('Saved');
    var d = store.read();
    view.innerHTML = d.length ? '<div class="list">' + d.map(function (x) {
      var p = x.key.split('/');
      return '<a class="row" href="#/read/' + esc(p[0]) + '/' + encodeURIComponent(p[1]) + '/' + esc(p[2]) + '"><div class="txt"><div class="nm">' + esc(x.title) + '</div><div class="sub">' + esc(x.book) + ', ' + esc(x.label) + '</div></div></a>';
    }).join('') + '</div>' + foot() : '<div class="empty"><b>Nothing saved yet</b>Tap the bookmark while reading to keep a page here.</div>' + foot();
  }

  function route() {
    var h = location.hash || '#/', path = h.split('?')[0].replace(/^#/, ''), params = qs(h), parts = path.split('/').filter(Boolean).map(decodeURIComponent);
    if (!lb.hidden) closeLightbox(true);
    if (parts[0] !== 'read') { document.body.classList.remove('reading'); window.scrollTo(0, 0); }
    view.focus({ preventScroll: true });
    switch (parts[0]) {
      case undefined: return home();
      case 'book': return book(parts[1]);
      case 'vols': return volumes(parts[1], parts[2]);
      case 'read': return reader(parts[1], parts[2], parts[3], params);
      case 'search': return search(params);
      case 'saved': return saved();
      default: return home();
    }
  }
  window.addEventListener('hashchange', route);
  window.addEventListener('popstate', function () { if (!lb.hidden) closeLightbox(true); });
  route();
})();
