/* Shared helpers for the Darwin pages: fetch, formatting, small SVG charts. */
(function () {
  const D = (window.Darwin = {});

  D.api = async function (url, opts) {
    const o = Object.assign({ headers: {} }, opts || {});
    if (o.body && typeof o.body !== 'string') {
      o.body = JSON.stringify(o.body);
      o.headers['Content-Type'] = 'application/json';
    }
    const r = await fetch(url, o);
    let data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    if (!r.ok) {
      const err = new Error((data && (data.error || (data.errors || []).join('; '))) || ('HTTP ' + r.status));
      err.data = data;
      throw err;
    }
    return data;
  };

  D.esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  D.num = (v, d = 3) => (v == null || isNaN(v)) ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: d });
  D.usd = v => v == null ? '—' : (v < 0.01 ? '$' + Number(v).toFixed(6) : '$' + Number(v).toFixed(4));
  D.pct = v => v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
  D.when = iso => { if (!iso) return '—'; const d = new Date(iso); return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); };
  D.statusClass = s => 's-' + String(s || '').replace(/\s+/g, '-');
  D.pill = s => `<span class="pill ${D.statusClass(s)}">${D.esc(s)}</span>`;
  D.css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  /* Line chart: series = [{name, color, values:[y...], xs?:[x...], dash?}] */
  D.lineChart = function (svg, series, opts) {
    opts = opts || {};
    const W = svg.clientWidth || 600, H = svg.clientHeight || 220;
    const pad = { l: 46, r: 12, t: 12, b: 26 };
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const all = series.flatMap(s => s.values.filter(v => v != null && isFinite(v)));
    if (!all.length) { svg.innerHTML = `<text x="${pad.l}" y="${H / 2}" fill="${D.css('--md-sys-color-on-surface-variant')}" font-size="12">${D.esc(opts.empty || 'No data yet')}</text>`; return; }
    let y0 = opts.yMin != null ? opts.yMin : Math.min(...all), y1 = opts.yMax != null ? opts.yMax : Math.max(...all);
    if (y1 - y0 < 1e-9) { y1 += 1; y0 -= opts.yMin != null ? 0 : 1; }
    const n = Math.max(...series.map(s => s.values.length));
    const xs = series[0].xs || [...Array(n).keys()];
    let x0 = xs[0], x1 = xs[xs.length - 1];
    if (x1 === x0) { x0 -= 0.5; x1 += 0.5; }   // centre a single point
    const X = x => pad.l + (x - x0) / (x1 - x0) * (W - pad.l - pad.r);
    const Y = y => H - pad.b - (y - y0) / (y1 - y0) * (H - pad.t - pad.b);
    const grid = D.css('--md-sys-color-outline-variant'), txt = D.css('--md-sys-color-on-surface-variant');
    let h = '';
    for (let i = 0; i <= 4; i++) {
      const yv = y0 + (y1 - y0) * i / 4, yy = Y(yv);
      h += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${yy}" y2="${yy}" stroke="${grid}" stroke-width="1" opacity=".6"/>`;
      h += `<text x="${pad.l - 6}" y="${yy + 4}" text-anchor="end" font-size="10.5" fill="${txt}" font-family="IBM Plex Mono, monospace">${D.num(yv, Math.abs(y1) < 10 ? 2 : 0)}</text>`;
    }
    h += `<text x="${W - pad.r}" y="${H - 6}" text-anchor="end" font-size="10.5" fill="${txt}" font-family="IBM Plex Mono, monospace">${D.esc(opts.xLabel || '')} ${D.num(xs[xs.length - 1], 0)}</text>`;
    h += `<text x="${pad.l}" y="${H - 6}" font-size="10.5" fill="${txt}" font-family="IBM Plex Mono, monospace">${D.num(xs[0], 0)}</text>`;
    (opts.markers || []).forEach(m => {
      const xx = X(m.x);
      h += `<line x1="${xx}" x2="${xx}" y1="${pad.t}" y2="${H - pad.b}" stroke="${D.css('--md-sys-color-tertiary')}" stroke-dasharray="3 4"/>`;
      h += `<text x="${xx + 4}" y="${pad.t + 10}" font-size="10.5" fill="${D.css('--md-sys-color-tertiary')}">${D.esc(m.label)}</text>`;
    });
    series.forEach(s => {
      const sx = s.xs || xs;
      const pts = s.values.map((v, i) => (v == null || !isFinite(v)) ? null : `${X(sx[i]).toFixed(1)},${Y(v).toFixed(1)}`).filter(Boolean).join(' ');
      h += `<polyline fill="none" stroke="${s.color}" stroke-width="${s.width || 2}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ''} stroke-linejoin="round" points="${pts}"/>`;
      if (opts.dots || s.values.length <= 40)   // markers keep short series (even a single day) visible
        s.values.forEach((v, i) => { if (v != null && isFinite(v) && !s.dash) h += `<circle cx="${X(sx[i]).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="3" fill="${s.color}"/>`; });
    });
    svg.innerHTML = h;
  };

  D.spark = function (svg, values, color) {
    const W = svg.clientWidth || 160, H = svg.clientHeight || 34;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const v = values.filter(x => x != null && isFinite(x));
    if (v.length < 2) { svg.innerHTML = ''; return; }
    const lo = Math.min(...v), hi = Math.max(...v), r = hi - lo || 1;
    const pts = values.map((y, i) => `${(i / (values.length - 1) * (W - 2) + 1).toFixed(1)},${(H - 3 - (y - lo) / r * (H - 6)).toFixed(1)}`).join(' ');
    svg.innerHTML = `<polyline fill="none" stroke="${color}" stroke-width="1.6" points="${pts}"/>`;
  };

  /* Genome bars: shows where genome a (and optional b) sit within each gene's range. */
  D.genomeBars = function (el, genes, a, b, labels) {
    const ca = D.css('--md-sys-color-primary'), cb = D.css('--md-sys-color-tertiary');
    let h = `<div class="legend" style="margin-bottom:8px"><span><i style="--c:${ca}"></i>${D.esc(labels[0])}</span>${b ? `<span><i style="--c:${cb}"></i>${D.esc(labels[1])}</span>` : ''}</div>`;
    genes.forEach(([name, lo, hi]) => {
      const pa = (a[name] - lo) / (hi - lo) * 100;
      const pb = b ? (b[name] - lo) / (hi - lo) * 100 : null;
      h += `<div class="gb"><span class="mono">${name}</span><div class="track">` +
        (pb != null ? `<div class="mark" style="left:calc(${pb}% - 1px);background:${cb}"></div>` : '') +
        `<div class="mark" style="left:calc(${pa}% - 1px);background:${ca}"></div></div>` +
        `<span class="mono small muted">${D.num(a[name], 2)}${b ? ' / ' + D.num(b[name], 2) : ''}</span></div>`;
    });
    el.innerHTML = h;
  };

  /* Creature colour from diet preference: amber specialist → green specialist. */
  D.dietColor = function (pref, alpha) {
    const a = [233, 191, 109], g = [125, 216, 181];
    const t = Math.max(0, Math.min(1, pref));
    const c = a.map((v, i) => Math.round(v + (g[i] - v) * t));
    return `rgba(${c[0]},${c[1]},${c[2]},${alpha == null ? 1 : alpha})`;
  };

  /* Leaving Darwin: the bookcase swings back to the library. */
  D.exitToLibrary = function (e) {
    if (e) e.preventDefault();
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.documentElement.classList.add('portal-out');
    setTimeout(() => { location.href = '/?from=darwin'; }, reduce ? 200 : 700);
  };
})();
