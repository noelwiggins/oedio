#!/usr/bin/env python3
"""oedio Book Studio engine.

Turns a "book spec" (JSON) into a giftable PDF: covers, frontispiece, title
page, dedication, contents, and a body where every source page becomes a
spread (or single page) laid out from up to four sources -- scan, AI
transcription, AI translation, a human translation -- as full pages or two
split panels. Optional gilt monogram on the cover.

The same HTML generators feed both the PDF build (WeasyPrint) and the live
in-browser preview, so what you see in the studio is what ends up in the PDF.

CLI (used by the web app, one subprocess per job so the single gunicorn
worker never blocks):  python bookbuilder.py build <jobdir>
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "static", "fonts")
READER_DIR = os.path.join(BASE_DIR, "static", "reader-data")
MANIFEST_PATH = os.path.join(BASE_DIR, "data", "manifest.json")
UA = "oedio.com megabook builder (noel@harmonyball.com)"

MAX_BODY_PAGES = 800
MIN_PT = 4.5   # smallest body type set before trimming (PDF text is vector, so it zooms)
MAX_SOURCES = 4
IMG_PROXY_HOSTS = {"tile.loc.gov"}

TRIMS = {  # name -> (width_pt, height_pt), portrait
    "5.5x8.5": (396.0, 612.0),
    "6x9": (432.0, 648.0),
    "7x10": (504.0, 720.0),
    "8x10": (576.0, 720.0),
    "8.5x11": (612.0, 792.0),
    "a5": (419.53, 595.28),
    "a4": (595.28, 841.89),
}
QUALITY = {  # long-side pixels, JPEG quality, rough average bytes per scanned page
    "email": {"px": 1000, "q": 50, "est": 105_000},
    "standard": {"px": 1600, "q": 66, "est": 250_000},
    "high": {"px": 2400, "q": 80, "est": 540_000},
}
THEMES = {  # cloth colour, darker edge tone
    "oxblood": ("#5c1c1c", "#3f1010"),
    "navy": ("#16243f", "#0c1627"),
    "forest": ("#1f3b2b", "#12251b"),
    "charcoal": ("#26262b", "#141417"),
    "plum": ("#40213f", "#2a1229"),
    "ivory": ("#eee4cc", "#d9cba8"),
}
FOILS = {  # colour, opacity
    "gold": ("#cfa84c", 1.0),
    "silver": ("#cfd4dc", 1.0),
    "copper": ("#c47f48", 1.0),
    "cream": ("#f1e8d2", 1.0),
    "blind": ("#000000", 0.4),
}
IVORY_FOILS = {
    "gold": ("#8a6a1f", 1.0), "silver": ("#6a717d", 1.0), "copper": ("#8a4c20", 1.0),
    "cream": ("#5b4a2a", 1.0), "blind": ("#000000", 0.28),
}
PAPER = "#fdfbf5"
INK = "#29241f"

FONT_FILES = {
    "latin": "EBGaramond_400Regular.ttf",
    "greek": "EBGaramond_400Regular.ttf",
    "arabic": "NotoNaskhArabic_400Regular.ttf",
    "other": "NotoSerif_400Regular.ttf",
    "display": "CormorantGaramond_600SemiBold.ttf",
    "display_italic": "CormorantGaramond_400Regular_Italic.ttf",
}
LINE_HEIGHT = {"latin": 1.36, "greek": 1.44, "arabic": 1.6, "other": 1.42}

logging.getLogger("weasyprint").setLevel(logging.ERROR)
logging.getLogger("fontTools").setLevel(logging.ERROR)


class SpecError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Export storage
# ---------------------------------------------------------------------------
def export_root() -> str:
    env = os.environ.get("OEDIO_EXPORT_DIR")
    if env:
        root = env
    elif os.path.isdir("/data") and os.access("/data", os.W_OK):
        root = "/data/exports"
    else:
        root = os.path.join(BASE_DIR, ".exports")
    os.makedirs(root, exist_ok=True)
    return root


def image_cache_dir(quality: str) -> str:
    d = os.path.join(export_root(), "_imgcache", quality)
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Manifest + source discovery
# ---------------------------------------------------------------------------
_MANIFEST = None


def manifest() -> dict:
    global _MANIFEST
    if _MANIFEST is None:
        with open(MANIFEST_PATH, encoding="utf-8") as fh:
            _MANIFEST = json.load(fh)
    return _MANIFEST


def find_megabook(slug: str):
    return next((m for m in manifest()["megabooks"] if m["slug"] == slug), None)


def _data_path(comp: dict) -> str:
    return os.path.join(READER_DIR, comp.get("data_slug", comp["slug"]) + ".json")


_PAGES_CACHE: dict = {}


def load_pages(comp: dict) -> dict:
    """page number -> reader-data entry. Small LRU so big books don't pile up."""
    path = _data_path(comp)
    mtime = os.stat(path).st_mtime
    hit = _PAGES_CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    pages = {}
    if isinstance(data, list):
        for i, e in enumerate(data):
            if isinstance(e, dict):
                try:
                    n = int(e.get("page") or (i + 1))
                except (TypeError, ValueError):
                    n = i + 1
                pages[n] = e
    _PAGES_CACHE[path] = (mtime, pages)
    while len(_PAGES_CACHE) > 6:
        _PAGES_CACHE.pop(next(iter(_PAGES_CACHE)))
    return pages


def component_group(by_slug: dict, comp: dict) -> str:
    base = comp.get("layer_of")
    if base and base in by_slug:
        return base
    s = comp["slug"]
    for suf in ("-transcription", "-english"):
        if s.endswith(suf) and s[: -len(suf)] in by_slug:
            return s[: -len(suf)]
    return s


def comp_kind(comp: dict) -> str:
    s = comp["slug"]
    if s.endswith("-transcription"):
        return "transcription"
    if s.endswith("-english"):
        return "translation"
    lk = comp.get("layer_kind")
    if lk:
        return lk
    if comp.get("layer_of"):
        return "translation"
    return "edition"


def is_ai(comp: dict) -> bool:
    blob = f"{comp.get('title', '')} {comp.get('contributor') or ''}"
    return bool(re.search(r"\bAI\b", blob)) or "Claude" in blob or "Forge" in blob


def script_of(text: str) -> str:
    ar = gr = ot = la = 0
    for ch in text[:4000]:
        o = ord(ch)
        if 0x600 <= o <= 0x6FF or 0x750 <= o <= 0x77F or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF:
            ar += 1
        elif 0x370 <= o <= 0x3FF or 0x1F00 <= o <= 0x1FFF:
            gr += 1
        elif 0x590 <= o <= 0x5FF or o >= 0x3000:
            ot += 1
        elif ch.isalpha():
            la += 1
    tot = ar + gr + ot + la
    if tot == 0:
        return "latin"
    if ar / tot > 0.3:
        return "arabic"
    if gr / tot > 0.3:
        return "greek"
    if ot / tot > 0.3:
        return "other"
    return "latin"


_PROFILE_CACHE: dict = {}


def _profile(comp: dict) -> dict:
    path = _data_path(comp)
    mtime = os.stat(path).st_mtime
    hit = _PROFILE_CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    pages = load_pages(comp)
    nums = sorted(pages)
    step = max(1, len(nums) // 80)
    sample = [pages[n] for n in nums[::step]] or []
    n_img = sum(1 for e in sample if e.get("image"))
    texts = [(e.get("text") or "").strip() for e in sample]
    n_txt = sum(1 for t in texts if len(t) >= 80)
    joined = " ".join(t for t in texts if len(t) >= 80)[:4000]
    thumb = next((e["image"] for e in sample[len(sample) // 8:] if e.get("image")), "")
    snippet = next((t[:170] for t in texts if len(t) >= 80), "")
    prof = {
        "thumb": thumb, "snippet": snippet,
        "pages": max(nums) if nums else 0,
        "img_frac": n_img / len(sample) if sample else 0.0,
        "txt_frac": n_txt / len(sample) if sample else 0.0,
        "script": script_of(joined) if joined else "latin",
    }
    _PROFILE_CACHE[path] = (mtime, prof)
    return prof


def list_sources(mega_slug: str) -> dict:
    mb = find_megabook(mega_slug)
    if not mb:
        raise SpecError("Unknown book")
    by_slug = {c["slug"]: c for c in mb["components"]}
    out = []
    for comp in mb["components"]:
        if not os.path.exists(_data_path(comp)):
            continue
        prof = _profile(comp)
        if not prof["pages"]:
            continue
        group = component_group(by_slug, comp)
        kind = comp_kind(comp)
        ai = is_ai(comp)
        views = []
        if prof["img_frac"] >= 0.5 and (group == comp["slug"] or kind == "edition"):
            views.append("image")
        if kind != "edition" or (prof["txt_frac"] >= (0.6 if comp.get("facsimile") else 0.4)):
            views.append("text")
        for view in views:
            out.append({
                "key": f"{comp['slug']}:{view}",
                "slug": comp["slug"],
                "view": view,
                "title": comp["title"],
                "year": comp.get("year"),
                "contributor": comp.get("contributor", ""),
                "kind": "scan" if view == "image" else kind,
                "ai": ai and view == "text",
                "pages": prof["pages"],
                "group": group,
                "script": prof["script"] if view == "text" else None,
                "thumb": prof["thumb"] if view == "image" else "",
                "snippet": prof["snippet"] if view == "text" else "",
                "short": _short_label(by_slug, comp, view, kind, ai),
            })
    return {
        "megabook": {"slug": mb["slug"], "title": mb["title"], "author": mb.get("author", "")},
        "sources": out,
    }


def _short_label(by_slug, comp, view, kind, ai) -> str:
    base = by_slug.get(component_group(by_slug, comp), comp)
    bt = re.sub(r"\s*\(AI[^)]*\)\s*$", "", base["title"]).strip()
    if len(bt) > 46:
        bt = bt[:45].rstrip() + "…"
    if view == "image":
        return f"Original scan · {bt}"
    layer = {"transcription": "Transcription", "translation": "Translation",
             "commentary": "Commentary"}.get(kind, "Text")
    if ai:
        return f"AI {layer.lower()} · unverified · {bt}"
    contrib = (comp.get("contributor") or "").strip()
    if kind == "translation" and contrib:
        return f"{layer} · {contrib[:40]} · {bt}"
    return f"{layer} · {bt}"


# ---------------------------------------------------------------------------
# Spec normalisation
# ---------------------------------------------------------------------------
def _s(v, n):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _s_multiline(v, n):
    return "\n".join(l.strip() for l in str(v or "").replace("\r", "").split("\n"))[:n].strip()


def _int(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _norm_layout(L, ids, default_src):
    L = L if isinstance(L, dict) else {}
    kind = L.get("layout", "full")
    if kind == "blank":
        return {"layout": "blank"}
    fit = "bleed" if L.get("fit") == "bleed" else "fit"
    if kind == "split":
        panels = [p for p in (L.get("panels") or []) if p in ids][:2]
        while len(panels) < 2:
            panels.append(ids[min(len(panels), len(ids) - 1)])
        ratio = "auto" if L.get("ratio") in (None, "", "auto") else _int(L.get("ratio"), 25, 75, 50)
        return {"layout": "split", "dir": "v" if L.get("dir") == "v" else "h",
                "ratio": ratio, "panels": panels, "fit": fit}
    src = L.get("src") if L.get("src") in ids else default_src
    return {"layout": "full", "src": src, "fit": fit}


def _spread_sources(left, right, ids):
    """Never show one source twice while a chosen source goes unused.

    The Studio form can end up with stale panels (e.g. both panels "A" after sources were removed and
    added back), which printed the same scan three times on a spread. Repeat a source only when there
    are not enough distinct sources to fill every slot."""
    slots = []
    for L in (left, right):
        if not L or L["layout"] == "blank":
            continue
        if L["layout"] == "full":
            slots.append((L, "src", None))
        else:
            slots += [(L, "panels", 0), (L, "panels", 1)]
    get = lambda L, k, i: L[k] if i is None else L[k][i]
    used = [get(*sl) for sl in slots]
    unused = [i for i in ids if i not in used]
    seen = set()
    for L, k, i in slots:
        v = get(L, k, i)
        if v in seen and unused:
            v = unused.pop(0)
            if i is None:
                L[k] = v
            else:
                L[k][i] = v
        seen.add(v)


def is_consecutive(spec: dict) -> bool:
    """Both pages of a spread show the same single source in full: then the book reads straight through,
    page p on the left and p+1 on the right, instead of the same page twice."""
    L, R = spec["left"], spec["right"]
    return (spec["mode"] == "spread" and L["layout"] == "full" and R["layout"] == "full" and L["src"] == R["src"])


def normalize_spec(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise SpecError("Spec must be an object")
    mb = find_megabook(raw.get("megabook", ""))
    if not mb:
        raise SpecError("Unknown book")
    avail = {s["key"]: s for s in list_sources(mb["slug"])["sources"]}
    src_in = raw.get("sources") or []
    if not isinstance(src_in, list) or not src_in:
        raise SpecError("Choose at least one source")
    if len(src_in) > MAX_SOURCES:
        raise SpecError(f"At most {MAX_SOURCES} sources")
    sources, seen = [], set()
    for i, s in enumerate(src_in):
        key = s.get("key") if isinstance(s, dict) else s
        if key not in avail:
            raise SpecError(f"Unknown source: {key}")
        if key in seen:
            raise SpecError("A source can only be chosen once")
        seen.add(key)
        sources.append({"id": "ABCD"[i], "key": key})
    ids = [s["id"] for s in sources]
    first_pages = avail[sources[0]["key"]]["pages"]

    rng = raw.get("range") or {}
    p_from = _int(rng.get("from"), 1, 100000, 1)
    p_to = _int(rng.get("to"), 1, 100000, first_pages)
    p_to = min(p_to, first_pages)
    p_from = min(p_from, p_to)
    if p_to - p_from + 1 > MAX_BODY_PAGES:
        raise SpecError(f"Too many pages (max {MAX_BODY_PAGES}); narrow the page range")

    mode = "single" if raw.get("mode") == "single" else "spread"
    left = _norm_layout(raw.get("left"), ids, ids[0])
    right = _norm_layout(raw.get("right"), ids, ids[min(1, len(ids) - 1)])
    _spread_sources(left, right if mode == "spread" else None, ids)

    c = raw.get("cover") or {}
    theme = c.get("theme") if c.get("theme") in THEMES else "oxblood"
    foil = c.get("foil") if c.get("foil") in FOILS else "gold"
    title_default = mb["title"].split("·")[-1].strip() or mb["title"]
    cover = {
        "title": _s(c.get("title"), 140) or title_default,
        "subtitle": _s(c.get("subtitle"), 200),
        "byline": _s(c.get("byline", mb.get("author", "")), 140),
        "theme": theme, "foil": foil,
        "image": _s(c.get("image", "none"), 20),
    }
    fr = raw.get("frontispiece") or {}
    toc_in = raw.get("toc") or {}
    toc_mode = toc_in.get("mode") if toc_in.get("mode") in ("none", "headings", "ranges", "custom") else "none"
    entries = []
    for e in (toc_in.get("entries") or [])[:300]:
        if isinstance(e, dict):
            t = _s(e.get("title"), 140)
            pg = _int(e.get("page"), 1, 100000, 0)
            if t and pg:
                entries.append({"title": t, "page": pg})
    toc = {"mode": toc_mode, "every": _int(toc_in.get("every"), 1, 500, 25),
           "source": toc_in.get("source") if toc_in.get("source") in ids else ids[0], "entries": entries}
    d = raw.get("dedication") or {}
    ded = {"enabled": bool(d.get("enabled")), "to": _s(d.get("to"), 120),
           "message": _s_multiline(d.get("message"), 700), "from": _s(d.get("from"), 120),
           "date": _s(d.get("date"), 60), "lines": _int(d.get("lines"), 0, 6, 0)}
    m = raw.get("monogram") or {}
    initials = "".join(ch for ch in str(m.get("initials") or "") if ch.isalpha())[:3].upper()
    mono = {"enabled": bool(m.get("enabled")) and bool(initials), "initials": initials,
            "style": m.get("style") if m.get("style") in ("circle", "laurel", "square", "oval") else "circle",
            "position": m.get("position") if m.get("position") in ("back-center", "back-lower-right") else "back-center",
            "also_front": bool(m.get("also_front"))}
    q = raw.get("quality") if raw.get("quality") in QUALITY else "standard"
    trim = raw.get("trim") if raw.get("trim") in TRIMS else "6x9"
    return {
        "megabook": mb["slug"], "sources": sources, "range": {"from": p_from, "to": p_to},
        "mode": mode, "left": left, "right": right, "trim": trim, "quality": q,
        "folios": raw.get("folios", True) is not False, "labels": raw.get("labels", True) is not False,
        "cover": cover,
        "frontispiece": {"image": _s(fr.get("image", "none"), 20)},
        "toc": toc, "dedication": ded, "monogram": mono,
        "colophon": raw.get("colophon", True) is not False,
        "back_text": _s_multiline(raw.get("back_text"), 500),
    }


# ---------------------------------------------------------------------------
# Typography: script-aware font sizing so text always fits its panel
# ---------------------------------------------------------------------------
from PIL import Image, ImageFont, features  # noqa: E402

_RAQM = features.check("raqm")
_PIL_FONTS: dict = {}
_WORD_W: dict = {}


def _pil_font(name):
    f = _PIL_FONTS.get(name)
    if f is None:
        kw = {"layout_engine": ImageFont.Layout.RAQM} if _RAQM else {}
        f = ImageFont.truetype(os.path.join(FONT_DIR, name), 100, **kw)
        _PIL_FONTS[name] = f
    return f


def _word_w(fname, word, rtl):
    k = (fname, word, rtl)
    v = _WORD_W.get(k)
    if v is None:
        f = _pil_font(fname)
        try:
            v = f.getlength(word, direction="rtl") if (rtl and _RAQM) else f.getlength(word)
        except Exception:
            v = f.getlength(word)
        if len(_WORD_W) > 200000:
            _WORD_W.clear()
        _WORD_W[k] = v
    return v


def _paras(text):
    return [[l.split() for l in p.split("\n")] for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _height_for(paras, size, width, fname, rtl, lh):
    scale = size / 100.0
    space = _word_w(fname, " ", rtl) * scale
    lines = 0
    for para in paras:
        for words in para:
            if not words:
                lines += 1
                continue
            cur, n = 0.0, 1
            for wd in words:
                ww = _word_w(fname, wd, rtl) * scale
                if cur == 0.0:
                    cur = ww
                elif cur + space + ww <= width:
                    cur += space + ww
                else:
                    n += 1
                    cur = ww
                if ww > width:
                    n += int(ww // width)
                    cur = ww % width
            lines += n
    gaps = max(0, len(paras) - 1)
    return (lines + gaps * 0.45) * size * lh


def fit_text(text, script, w, h, min_pt=5.6, max_pt=11.5):
    """Largest font size (pt) at which `text` fits w x h. Returns (size, text, trimmed)."""
    fname = FONT_FILES.get(script, FONT_FILES["other"])
    rtl = script == "arabic"
    lh = LINE_HEIGHT.get(script, 1.4)
    width = w * 0.965
    avail = h * 0.965
    paras = _paras(text)
    lo, hi = int(round(min_pt * 10)), int(round(max_pt * 10))   # tenths of a point
    if _height_for(paras, hi / 10.0, width, fname, rtl, lh) <= avail:
        return hi / 10.0, text, False
    if _height_for(paras, lo / 10.0, width, fname, rtl, lh) <= avail:
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if _height_for(paras, mid / 10.0, width, fname, rtl, lh) <= avail:
                lo = mid
            else:
                hi = mid
        return lo / 10.0, text, False
    # Even the smallest size overflows: trim whole words and mark it honestly.
    words = text.split(" ")
    a, b = 0, len(words)
    while a < b:
        mid = (a + b + 1) // 2
        cand = " ".join(words[:mid]) + " […]"
        if _height_for(_paras(cand), min_pt, width, fname, rtl, lh) <= avail:
            a = mid
        else:
            b = mid - 1
    return min_pt, " ".join(words[:a]) + " […]", True


# ---------------------------------------------------------------------------
# Monogram (glyph outlines -> SVG paths, so fonts never matter downstream)
# ---------------------------------------------------------------------------
from fontTools.pens.svgPathPen import SVGPathPen  # noqa: E402
from fontTools.pens.transformPen import TransformPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

_TT: dict = {}


def _tt(name):
    f = _TT.get(name)
    if f is None:
        f = TTFont(os.path.join(FONT_DIR, name))
        _TT[name] = f
    return f


def _text_path(text, font_name, size, cx, cy):
    f = _tt(font_name)
    gs, cmap = f.getGlyphSet(), f.getBestCmap()
    upm = f["head"].unitsPerEm
    scale = size / upm
    cap = getattr(f["OS/2"], "sCapHeight", 0) or int(upm * 0.65)
    glyphs = [cmap.get(ord(ch)) for ch in text]
    glyphs = [g for g in glyphs if g]
    adv = [gs[g].width * scale for g in glyphs]
    total = sum(adv)
    x = cx - total / 2
    baseline = cy + cap * scale / 2
    d = ""
    for g, a in zip(glyphs, adv):
        pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        d += pen.getCommands()
        x += a
    return d, total


def foil_for(theme, foil):
    return (IVORY_FOILS if theme == "ivory" else FOILS)[foil]


def monogram_svg(initials, style="circle", foil="gold", theme="oxblood", size_pt=None) -> str:
    color, op = foil_for(theme, foil)
    n = len(initials)
    font = FONT_FILES["display"]
    parts = []
    if n == 1:
        specs = [(initials[0], 56, 50)]
    elif n == 2:
        specs = [(initials[0], 38, 34), (initials[1], 38, 66)]
    else:
        specs = [(initials[0], 28, 27), (initials[1], 44, 50), (initials[2], 28, 73)]
    if style == "square":
        specs = [(c, s * 0.92, x) for c, s, x in specs]
    letters = ""
    for ch, sz, x in specs:
        d, _ = _text_path(ch, font, sz, x, 50)
        letters += f'<path d="{d}"/>'
    stroke = f'fill="none" stroke="{color}" stroke-opacity="{op}"'
    if style == "circle":
        frame = (f'<circle cx="50" cy="50" r="47" stroke-width="1.8" {stroke}/>'
                 f'<circle cx="50" cy="50" r="42.5" stroke-width="0.7" {stroke}/>')
    elif style == "oval":
        frame = (f'<ellipse cx="50" cy="50" rx="41" ry="47" stroke-width="1.8" {stroke}/>'
                 f'<ellipse cx="50" cy="50" rx="36.5" ry="42.5" stroke-width="0.7" {stroke}/>'
                 + "".join(f'<circle cx="{50 + 44.5 * math.cos(math.radians(a)) * 0.92:.1f}" '
                           f'cy="{50 + 44.5 * math.sin(math.radians(a)):.1f}" r="1.1" fill="{color}" fill-opacity="{op}"/>'
                           for a in range(0, 360, 30)))
    elif style == "square":
        frame = (f'<rect x="6" y="6" width="88" height="88" rx="3" stroke-width="1.8" {stroke}/>'
                 f'<rect x="11" y="11" width="78" height="78" rx="1.5" stroke-width="0.7" {stroke}/>'
                 + "".join(f'<path d="M{cx} {cy-4}L{cx+4} {cy}L{cx} {cy+4}L{cx-4} {cy}Z" fill="{color}" fill-opacity="{op}"/>'
                           for cx, cy in ((11, 11), (89, 11), (11, 89), (89, 89))))
    else:  # laurel
        leaves = ""
        for side in (1, -1):
            for i in range(9):
                ang = math.radians(112 + i * 17.5)
                r = 39
                px = 50 + side * r * math.cos(ang)
                py = 50 + r * math.sin(ang)
                rot = math.degrees(ang) + 90 if side == 1 else 180 - (math.degrees(ang) + 90)
                leaves += (f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="2.6" ry="6.4" '
                           f'transform="rotate({rot:.1f} {px:.1f} {py:.1f})" fill="{color}" fill-opacity="{op}"/>')
        frame = leaves + f'<circle cx="50" cy="50" r="30" stroke-width="0.7" {stroke}/>'
    dim = f' width="{size_pt:.1f}pt" height="{size_pt:.1f}pt"' if size_pt else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"{dim}>{frame}'
            f'<g fill="{color}" fill-opacity="{op}">{letters}</g></svg>')


# ---------------------------------------------------------------------------
# Rendering context + HTML generators (shared by preview and PDF build)
# ---------------------------------------------------------------------------
def esc(s) -> str:
    return html.escape(str(s), quote=True)


class Ctx:
    def __init__(self, raw_spec, mode="pdf", images=None):
        self.spec = normalize_spec(raw_spec)
        self.mode = mode  # "pdf" | "web"
        self.images = images or {}  # url -> local processed path (pdf mode)
        self.mb = find_megabook(self.spec["megabook"])
        self.W, self.H = TRIMS[self.spec["trim"]]
        by_slug = {c["slug"]: c for c in self.mb["components"]}
        avail = {s["key"]: s for s in list_sources(self.mb["slug"])["sources"]}
        self.src = {}
        for s in self.spec["sources"]:
            meta = avail[s["key"]]
            comp = by_slug[meta["slug"]]
            self.src[s["id"]] = {**meta, "id": s["id"], "comp": comp, "pages": load_pages(comp)}
        self.font_base = ("file://" + FONT_DIR) if mode == "pdf" else "/static/fonts"
        self.warnings: list = []
        self.trimmed = 0
        self.small = 0
        c = self.spec["cover"]
        self.theme = c["theme"]
        self.cloth, self.cloth_edge = THEMES[self.theme]
        self.foil, self.foil_op = foil_for(self.theme, c["foil"])
        self.ink_on_cloth = INK if self.theme == "ivory" else "#f2ead8"

    # -- images ------------------------------------------------------------
    def img_src(self, url):
        if not url:
            return ""
        if self.mode == "pdf":
            p = self.images.get(url)
            return ("file://" + p) if p else ""
        host = urllib.parse.urlparse(url).hostname if url.startswith("http") else None
        if host in IMG_PROXY_HOSTS:
            return "/img-proxy?u=" + urllib.parse.quote(url, safe="")
        return url

    def image_url_for(self, ref):
        """'none' | 'first' | 'page:N' -> a scan URL from the first source that has one."""
        if not ref or ref == "none":
            return None
        if ref == "first":
            n = self.spec["range"]["from"]
        elif ref.startswith("page:"):
            try:
                n = int(ref.split(":", 1)[1])
            except ValueError:
                return None
        else:
            return None
        order = sorted(self.src.values(), key=lambda s: 0 if s["view"] == "image" else 1)
        for s in order:
            e = s["pages"].get(n)
            if e and e.get("image"):
                return e["image"]
        return None

    def layout_for(self, side):
        return self.spec["right"] if side == "R" and self.spec["mode"] == "spread" else self.spec["left"]


def _css(ctx: Ctx) -> str:
    fb, W, H = ctx.font_base, ctx.W, ctx.H

    def ff(fam, file, w=400, st="normal"):
        return (f"@font-face{{font-family:'{fam}';src:url('{fb}/{file}');"
                f"font-weight:{w};font-style:{st}}}")

    return (
        ff("EBG", "EBGaramond_400Regular.ttf") + ff("EBG", "EBGaramond_400Regular_Italic.ttf", 400, "italic")
        + ff("EBG", "EBGaramond_700Bold.ttf", 700)
        + ff("Corm", "CormorantGaramond_400Regular.ttf") + ff("Corm", "CormorantGaramond_400Regular_Italic.ttf", 400, "italic")
        + ff("Corm", "CormorantGaramond_600SemiBold.ttf", 600) + ff("Corm", "CormorantGaramond_700Bold.ttf", 700)
        + ff("NaskhAr", "NotoNaskhArabic_400Regular.ttf") + ff("NaskhAr", "NotoNaskhArabic_700Bold.ttf", 700)
        + ff("NSerif", "NotoSerif_400Regular.ttf") + ff("NSerif", "NotoSerif_400Regular_Italic.ttf", 400, "italic")
        + ff("NSerif", "NotoSerif_700Bold.ttf", 700)
        + f"""
@page {{ size:{W:.2f}pt {H:.2f}pt; margin:0 }}
html,body{{margin:0;padding:0;background:#fff}}
.pg{{position:relative;width:{W:.2f}pt;height:{H:.2f}pt;overflow:hidden;background:{PAPER};
  color:{INK};font-family:'EBG','NSerif','NaskhAr',serif;break-after:page;page-break-after:always}}
.pg:last-child{{break-after:auto;page-break-after:auto}}
.abs{{position:absolute}}
.panel{{position:absolute;overflow:hidden}}
.panel img{{display:block;width:100%;height:100%}}
.plabel{{font:600 5.6pt/1 'Corm','EBG',serif;letter-spacing:.14em;text-transform:uppercase;color:#8a8175;
  height:9pt;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ptext p{{margin:0 0 .45em 0}}
.ptext.latin,.ptext.greek{{font-family:'EBG','NSerif','NaskhAr',serif}}
.ptext.arabic{{font-family:'NaskhAr','EBG','NSerif',serif;direction:rtl;text-align:right}}
.ptext.other{{font-family:'NSerif','EBG','NaskhAr',serif}}
.blanknote{{font-style:italic;color:#a39b8d;text-align:center;font-size:8pt;padding-top:30%}}
.folio{{position:absolute;font:7pt/1 'EBG',serif;color:#8a8175;letter-spacing:.06em}}
.cloth{{position:absolute;left:0;top:0;right:0;bottom:0;
  background-image:repeating-linear-gradient(0deg,rgba(255,255,255,.028) 0,rgba(255,255,255,.028) .6pt,transparent .6pt,transparent 2.4pt),
  repeating-linear-gradient(90deg,rgba(0,0,0,.05) 0,rgba(0,0,0,.05) .6pt,transparent .6pt,transparent 2.4pt)}}
.ctr{{text-align:center}}
.disp{{font-family:'Corm','EBG',serif}}
.toc-row{{display:flex;align-items:baseline;font-size:9.6pt;line-height:1.45;margin:0 0 3pt 0}}
.toc-row .t{{flex:0 1 auto;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.toc-row .d{{flex:1 1 auto;border-bottom:.8pt dotted #a69d8d;margin:0 4pt 3pt 4pt;min-width:12pt}}
.toc-row .n{{flex:0 0 auto;font-variant-numeric:tabular-nums}}
"""
    )


def sec(inner, cls="", style="") -> str:
    return f'<section class="pg {cls}" style="{style}">{inner}</section>'


def doc_html(ctx: Ctx, sections) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{_css(ctx)}</style></head>'
            f'<body>{"".join(sections)}</body></html>')


def _foil_style(ctx):
    return f"color:{ctx.foil};opacity:{ctx.foil_op}"


def _margins(ctx, parity):
    W, H = ctx.W, ctx.H
    mo, mi, mt, mbm = W * 0.072, W * 0.10, H * 0.05, H * 0.075
    if parity == "S":
        mo = mi = (mo + mi) / 2
    left, right = (mi, mo) if parity in ("R", "S") else (mo, mi)
    return left, right, mt, mbm


def _split_geometry(ctx, layout, parity, ratio):
    ml, mr, mt, mbm = _margins(ctx, parity)
    cx, cy, cw, ch = ml, mt, ctx.W - ml - mr, ctx.H - mt - mbm
    g = ctx.W * 0.03
    r = ratio / 100.0
    if layout["dir"] == "h":
        h1 = (ch - g) * r
        return (cx, cy, cw, h1), (cx, cy + h1 + g, cw, ch - g - h1)
    w1 = (cw - g) * r
    return (cx, cy, w1, ch), (cx + w1 + g, cy, cw - g - w1, ch)


def _panel_text(ctx, sid, p):
    s = ctx.src[sid]
    if s["view"] != "text":
        return None
    t = ((s["pages"].get(p) or {}).get("text") or "").strip()
    t = re.sub(r"^===\w+===\s*", "", t)
    return t if t and t != "\u2014" else ""


def _auto_ratio(ctx, layout, parity, p):
    """Pick the split ratio for this page so text panels share one comfortable size."""
    a, b = layout["panels"]
    ta, tb = _panel_text(ctx, a, p), _panel_text(ctx, b, p)
    if ta is None and tb is None:
        return 50
    label = 11.0 if ctx.spec["labels"] else 0.0

    def size_for(txt, rect):
        if not txt:
            return 11.5
        return fit_text(txt, script_of(txt), rect[2], rect[3] - label, MIN_PT, 11.5)[0]

    lo, hi = 25.0, 75.0
    if ta is not None and tb is not None:      # two text panels: equalise their sizes
        for _ in range(9):
            mid = (lo + hi) / 2
            ra, rb = _split_geometry(ctx, layout, parity, mid)
            sa, sb = size_for(ta, ra), size_for(tb, rb)
            if abs(sa - sb) < 0.1:
                break
            if sa < sb:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    txt = ta if ta is not None else tb          # text + scan: give the text a comfortable 9.5pt
    text_first = ta is not None
    for _ in range(9):
        mid = (lo + hi) / 2
        ra, rb = _split_geometry(ctx, layout, parity, mid)
        sz = size_for(txt, ra if text_first else rb) if txt else 9.5
        if sz < 9.5:
            if text_first:
                lo = mid
            else:
                hi = mid
        else:
            if text_first:
                hi = mid
            else:
                lo = mid
    return max(30.0, min(70.0, (lo + hi) / 2))


def _rects(ctx, layout, parity, p=None):
    """-> list of (src_id, (x,y,w,h), bleed_edges(bool), fit)"""
    W, H = ctx.W, ctx.H
    ml, mr, mt, mbm = _margins(ctx, parity)
    cx, cy, cw, ch = ml, mt, W - ml - mr, H - mt - mbm
    g = W * 0.03
    kind = layout["layout"]
    if kind == "blank":
        return []
    if kind == "full":
        return [(layout["src"], (cx, cy, cw, ch), layout["fit"] == "bleed", layout["fit"])]
    a, b = layout["panels"]
    ratio = layout["ratio"]
    if ratio == "auto":
        ratio = _auto_ratio(ctx, layout, parity, p) if p is not None else 50
    r1, r2 = _split_geometry(ctx, layout, parity, ratio)
    return [(a, r1, layout["fit"] == "bleed", layout["fit"]), (b, r2, layout["fit"] == "bleed", layout["fit"])]


def _bleed_expand(ctx, rect, content):
    """Stretch a rect outward to the page edge on every side it shares with the content box."""
    x, y, w, h = rect
    cx, cy, cw, ch = content
    x2, y2 = x + w, y + h
    eps = 0.01
    if abs(x - cx) < eps:
        x = 0
    if abs(y - cy) < eps:
        y = 0
    if abs(x2 - (cx + cw)) < eps:
        x2 = ctx.W
    if abs(y2 - (cy + ch)) < eps:
        y2 = ctx.H
    return x, y, x2 - x, y2 - y


def _label_for(src):
    return src["short"]


def img_panel(ctx, entry, rect, fit):
    x, y, w, h = rect
    url = entry.get("image") if entry else None
    src = ctx.img_src(url) if url else ""
    if not src:
        return (f'<div class="panel" style="left:{x:.2f}pt;top:{y:.2f}pt;width:{w:.2f}pt;height:{h:.2f}pt">'
                f'<div class="blanknote">scan unavailable</div></div>')
    cover = "cover" if fit == "bleed" else "contain"
    return (f'<div class="panel" style="left:{x:.2f}pt;top:{y:.2f}pt;width:{w:.2f}pt;height:{h:.2f}pt">'
            f'<img src="{esc(src)}" style="object-fit:{cover}"></div>')


def text_panel(ctx, src, entry, rect, show_label):
    x, y, w, h = rect
    text = ((entry or {}).get("text") or "").strip()
    text = re.sub(r"^===\w+===\s*", "", text)
    label = ""
    lh = 0.0
    if show_label:
        label = f'<div class="plabel">{esc(_label_for(src))}</div>'
        lh = 11.0
    if not text or text == "—":
        body = '<div class="blanknote">— no text on this page —</div>'
        return (f'<div class="panel" style="left:{x:.2f}pt;top:{y:.2f}pt;width:{w:.2f}pt;height:{h:.2f}pt">'
                f'{label}{body}</div>')
    script = script_of(text)
    size, used, trimmed = fit_text(text, script, w, h - lh, MIN_PT, 11.5)
    if trimmed:
        ctx.trimmed += 1
    elif size < 6.0:
        ctx.small += 1
    lhgt = LINE_HEIGHT.get(script, 1.4)
    paras = [p for p in re.split(r"\n\s*\n", used) if p.strip()]
    inner = "".join("<p>" + "<br>".join(esc(l) for l in p.strip().split("\n")) + "</p>" for p in paras)
    align = "justify;hyphens:auto" if (script in ("latin", "greek") and w >= 215) else "left"
    if script == "arabic":
        align = "right"
    lang = {"arabic": "fa" if "persian" in (src["title"] + src["short"]).lower() else "ar",
            "greek": "grc"}.get(script, "en")
    return (f'<div class="panel" style="left:{x:.2f}pt;top:{y:.2f}pt;width:{w:.2f}pt;height:{h:.2f}pt">{label}'
            f'<div class="ptext {script}" lang="{lang}" dir="{"rtl" if script == "arabic" else "ltr"}" '
            f'style="font-size:{size}pt;line-height:{lhgt};text-align:{align}">{inner}</div></div>')


def body_leaf(ctx: Ctx, p: int, side: str) -> str:
    """One physical page of the body. side: 'L' | 'R' | 'S' (single)."""
    parity = side
    layout = ctx.spec["left"] if side in ("L", "S") else ctx.spec["right"]
    if layout["layout"] == "blank":
        return sec("", "blank")
    ml, mr, mt, mbm = _margins(ctx, parity)
    content = (ml, mt, ctx.W - ml - mr, ctx.H - mt - mbm)
    rects = _rects(ctx, layout, parity, p)
    multi = len(rects) > 1
    inner, any_bleed = [], False
    for sid, rect, bleed, fit in rects:
        s = ctx.src[sid]
        entry = s["pages"].get(p)
        if s["view"] == "image":
            if bleed:
                rect = _bleed_expand(ctx, rect, content)
                if len(rects) == 1:
                    any_bleed = True
            inner.append(img_panel(ctx, entry, rect, fit))
        else:
            show = ctx.spec["labels"] and (multi or s["ai"])
            inner.append(text_panel(ctx, s, entry, rect, show))
    folio = ""
    if ctx.spec["folios"] and not any_bleed:
        if parity == "R":
            pos = f"right:{mr:.1f}pt"
        elif parity == "L":
            pos = f"left:{ml:.1f}pt"
        else:
            pos = "left:0;right:0;text-align:center"
        inner.append(f'<div class="folio" style="bottom:{ctx.H * 0.032:.1f}pt;{pos}">{p}</div>')
    return sec("".join(inner), f"body {parity}")


# -- ornaments ---------------------------------------------------------------
def _frame_svg(ctx, inset=22.0, inset2=29.0):
    W, H = ctx.W, ctx.H
    c, op = ctx.foil, ctx.foil_op
    s = f'fill="none" stroke="{c}" stroke-opacity="{op}"'
    corners = ""
    for (x, y, sx, sy) in ((inset2, inset2, 1, 1), (W - inset2, inset2, -1, 1),
                           (inset2, H - inset2, 1, -1), (W - inset2, H - inset2, -1, -1)):
        corners += (f'<path d="M{x + sx * 3} {y + sy * 22}Q{x + sx * 3} {y + sy * 3} {x + sx * 22} {y + sy * 3}" '
                    f'stroke-width="1" {s}/>'
                    f'<circle cx="{x + sx * 3}" cy="{y + sy * 3}" r="2.2" fill="{c}" fill-opacity="{op}"/>')
    return (f'<svg class="abs" style="left:0;top:0" width="{W:.2f}pt" height="{H:.2f}pt" '
            f'viewBox="0 0 {W:.2f} {H:.2f}" xmlns="http://www.w3.org/2000/svg">'
            f'<rect x="{inset}" y="{inset}" width="{W - 2 * inset:.2f}" height="{H - 2 * inset:.2f}" stroke-width="1.6" {s}/>'
            f'<rect x="{inset2}" y="{inset2}" width="{W - 2 * inset2:.2f}" height="{H - 2 * inset2:.2f}" stroke-width=".6" {s}/>'
            f'{corners}</svg>')


def _divider_svg(color, op, width=110.0):
    return (f'<svg width="{width}pt" height="10pt" viewBox="0 0 110 10" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="M0 5H44M66 5H110" stroke="{color}" stroke-opacity="{op}" stroke-width=".8" fill="none"/>'
            f'<path d="M55 0.5L59.5 5L55 9.5L50.5 5Z" fill="{color}" fill-opacity="{op}"/></svg>')


def _fit_display(ctx, text, w, h, max_pt, min_pt, italic=False):
    script = script_of(text)
    if script not in ("latin", "greek"):
        size, used, _ = fit_text(text, script, w, h, min_pt, max_pt)
        return size, used
    f = FONT_FILES["display_italic" if italic else "display"]
    paras = _paras(text)
    size = max_pt
    while size >= min_pt:
        if _height_for(paras, size, w * 0.96, f, False, 1.12) <= h:
            return round(size, 1), text
        size -= 0.5
    return min_pt, text


def _title_block(ctx, text, x, y, w, h, max_pt, min_pt, color, weight=700, italic=False, extra=""):
    size, used = _fit_display(ctx, text, w, h, max_pt, min_pt, italic)
    style = "italic" if italic else "normal"
    return (f'<div class="abs ctr disp" style="left:{x:.1f}pt;top:{y:.1f}pt;width:{w:.1f}pt;height:{h:.1f}pt;'
            f'font-size:{size}pt;line-height:1.12;font-weight:{weight};font-style:{style};color:{color};{extra}">'
            f'{esc(used)}</div>')


def _by_size(W, text):
    """Byline font size that keeps long, letter-spaced names inside the cover."""
    return max(W * 0.02, min(W * 0.034, (W * 0.84) / (max(len(text), 1) * 0.95)))


def cover_front(ctx: Ctx) -> str:
    W, H = ctx.W, ctx.H
    c = ctx.spec["cover"]
    foilc, op = ctx.foil, ctx.foil_op
    parts = [f'<div class="cloth"></div>', _frame_svg(ctx)]
    img_url = ctx.image_url_for(c["image"])
    tw = W * 0.74
    tx = (W - tw) / 2
    if img_url and ctx.img_src(img_url):
        bw, bh = W * 0.50, H * 0.30
        bx, by = (W - bw) / 2, H * 0.115
        parts.append(f'<div class="abs" style="left:{bx - 4:.1f}pt;top:{by - 4:.1f}pt;width:{bw + 8:.1f}pt;height:{bh + 8:.1f}pt;'
                     f'border:1.4pt solid {foilc};opacity:{op}"></div>')
        parts.append(f'<div class="abs" style="left:{bx:.1f}pt;top:{by:.1f}pt;width:{bw:.1f}pt;height:{bh:.1f}pt;'
                     f'background:{PAPER};overflow:hidden"><img src="{esc(ctx.img_src(img_url))}" '
                     f'style="width:100%;height:100%;object-fit:cover;display:block"></div>')
        ty = H * 0.48
    else:
        ty = H * 0.22
    parts.append(_title_block(ctx, c["title"], tx, ty, tw, H * 0.2, W * 0.105, W * 0.045, foilc,
                              extra=f"opacity:{op}"))
    dy = ty + H * 0.2 + 4
    parts.append(f'<div class="abs ctr" style="left:0;width:{W:.1f}pt;top:{dy:.1f}pt">{_divider_svg(foilc, op)}</div>')
    if c["subtitle"]:
        parts.append(_title_block(ctx, c["subtitle"], tx, dy + 16, tw, H * 0.1, W * 0.052, W * 0.034, foilc,
                                  weight=400, italic=True, extra=f"opacity:{op}"))
    if c["byline"]:
        parts.append(f'<div class="abs ctr disp" style="left:{W*0.07:.1f}pt;width:{W*0.86:.1f}pt;top:{H * 0.80:.1f}pt;font-size:{_by_size(W, c["byline"]):.1f}pt;'
                     f'letter-spacing:.22em;text-transform:uppercase;font-weight:600;color:{foilc};opacity:{op}">'
                     f'{esc(c["byline"])}</div>')
    mono = ctx.spec["monogram"]
    if mono["enabled"] and mono["also_front"]:
        sz = W * 0.125
        parts.append(f'<div class="abs" style="left:{(W - sz) / 2:.1f}pt;top:{H * 0.872:.1f}pt">'
                     f'{monogram_svg(mono["initials"], mono["style"], ctx.spec["cover"]["foil"], ctx.theme, sz)}</div>')
    return sec("".join(parts), "cover", f"background:{ctx.cloth}")


def cover_back(ctx: Ctx) -> str:
    W, H = ctx.W, ctx.H
    foilc, op = ctx.foil, ctx.foil_op
    parts = [f'<div class="cloth"></div>', _frame_svg(ctx)]
    txt = ctx.spec["back_text"]
    if txt:
        paras = "".join(f"<p style='margin:0 0 .7em'>{esc(p)}</p>" for p in txt.split("\n") if p.strip())
        parts.append(f'<div class="abs ctr disp" style="left:{W * 0.15:.1f}pt;top:{H * 0.14:.1f}pt;width:{W * 0.7:.1f}pt;'
                     f'font-style:italic;font-size:{W * 0.036:.1f}pt;line-height:1.4;color:{ctx.ink_on_cloth};opacity:.92">{paras}</div>')
    mono = ctx.spec["monogram"]
    if mono["enabled"]:
        if mono["position"] == "back-lower-right":
            sz = W * 0.17
            x, y = W - sz - 46, H - sz - 46
        else:
            sz = W * 0.34
            x, y = (W - sz) / 2, H * 0.5 - sz / 2 + (H * 0.04 if txt else 0)
        parts.append(f'<div class="abs" style="left:{x:.1f}pt;top:{y:.1f}pt">'
                     f'{monogram_svg(mono["initials"], mono["style"], ctx.spec["cover"]["foil"], ctx.theme, sz)}</div>')
    parts.append(f'<div class="abs ctr disp" style="left:0;width:{W:.1f}pt;top:{H * 0.925:.1f}pt;font-size:{W * 0.026:.1f}pt;'
                 f'letter-spacing:.3em;text-transform:uppercase;color:{foilc};opacity:{op * 0.8}">oedio.com</div>')
    return sec("".join(parts), "cover back", f"background:{ctx.cloth}")


def page_frontispiece(ctx: Ctx) -> str:
    url = ctx.image_url_for(ctx.spec["frontispiece"]["image"])
    if not url or not ctx.img_src(url):
        return sec("", "blank")
    W, H = ctx.W, ctx.H
    x, y, w, h = W * 0.1, H * 0.08, W * 0.8, H * 0.78
    cap = esc(ctx.spec["cover"]["title"])
    return sec(f'<div class="panel" style="left:{x:.1f}pt;top:{y:.1f}pt;width:{w:.1f}pt;height:{h:.1f}pt">'
               f'<img src="{esc(ctx.img_src(url))}" style="object-fit:contain"></div>'
               f'<div class="abs ctr disp" style="left:0;width:{W:.1f}pt;top:{H * 0.91:.1f}pt;font-style:italic;'
               f'font-size:{W * 0.03:.1f}pt;color:#7d7467">{cap}</div>', "frontis")


def page_title(ctx: Ctx) -> str:
    W, H = ctx.W, ctx.H
    c = ctx.spec["cover"]
    tw, tx = W * 0.78, W * 0.11
    parts = []
    if c["byline"]:
        parts.append(f'<div class="abs ctr disp" style="left:{W*0.07:.1f}pt;width:{W*0.86:.1f}pt;top:{H * 0.14:.1f}pt;font-size:{_by_size(W, c["byline"]):.1f}pt;'
                     f'letter-spacing:.24em;text-transform:uppercase;font-weight:600;color:#6e655a">{esc(c["byline"])}</div>')
    parts.append(_title_block(ctx, c["title"], tx, H * 0.22, tw, H * 0.2, W * 0.105, W * 0.045, INK))
    parts.append(f'<div class="abs ctr" style="left:0;width:{W:.1f}pt;top:{H * 0.435:.1f}pt">{_divider_svg("#8a6a1f", 1)}</div>')
    if c["subtitle"]:
        parts.append(_title_block(ctx, c["subtitle"], tx, H * 0.47, tw, H * 0.1, W * 0.05, W * 0.032, "#4d453b",
                                  weight=400, italic=True))
    ids = [ctx.src[s["id"]]["short"] for s in ctx.spec["sources"]]
    lines = "".join(f"<div>{esc(t)}</div>" for t in ids)
    parts.append(f'<div class="abs ctr" style="left:{W * 0.1:.1f}pt;width:{W * 0.8:.1f}pt;top:{H * 0.70:.1f}pt;'
                 f'font-size:{W * 0.0205:.1f}pt;line-height:1.55;color:#7d7467;font-style:italic">{lines}</div>')
    month = datetime.now(timezone.utc).strftime("%B %Y")
    parts.append(f'<div class="abs ctr disp" style="left:0;width:{W:.1f}pt;top:{H * 0.9:.1f}pt;font-size:{W * 0.028:.1f}pt;'
                 f'letter-spacing:.26em;text-transform:uppercase;color:#6e655a">oedio.com · {month}</div>')
    return sec("".join(parts), "title")


def page_dedication(ctx: Ctx) -> str:
    d = ctx.spec["dedication"]
    W, H = ctx.W, ctx.H
    if not d["enabled"]:
        return sec("", "blank")
    parts = [f'<div class="abs ctr" style="left:0;width:{W:.1f}pt;top:{H * 0.2:.1f}pt">{_divider_svg("#8a6a1f", 1, 90)}</div>']
    y = H * 0.27
    if d["to"]:
        size, used = _fit_display(ctx, d["to"], W * 0.72, H * 0.12, W * 0.07, W * 0.035, True)
        parts.append(f'<div class="abs ctr disp" style="left:{W * 0.14:.1f}pt;width:{W * 0.72:.1f}pt;top:{y:.1f}pt;'
                     f'font-size:{size}pt;font-style:italic;line-height:1.18;color:{INK}">{esc(used)}</div>')
        y += H * 0.14
    if d["message"]:
        paras = "".join(f"<p style='margin:0 0 .8em'>{esc(p)}</p>" for p in d["message"].split("\n") if p.strip())
        msize, _, _ = fit_text(d["message"], script_of(d["message"]), W * 0.64, H * 0.3, 8.5, W * 0.03)
        parts.append(f'<div class="abs ctr" style="left:{W * 0.18:.1f}pt;width:{W * 0.64:.1f}pt;top:{y:.1f}pt;'
                     f'font-size:{msize}pt;line-height:1.5;font-style:italic;color:#3d362e">{paras}</div>')
    if d["from"] or d["date"]:
        sig = "".join(f"<div>{esc(t)}</div>" for t in (d["from"], d["date"]) if t)
        parts.append(f'<div class="abs ctr disp" style="left:{W * 0.14:.1f}pt;width:{W * 0.72:.1f}pt;top:{H * 0.575:.1f}pt;'
                     f'font-size:{W * 0.04:.1f}pt;font-style:italic;color:#4d453b;line-height:1.4">{sig}</div>')
    if d["lines"]:
        gap = W * 0.055
        base = H * 0.74
        for i in range(d["lines"]):
            parts.append(f'<div class="abs" style="left:{W * 0.2:.1f}pt;width:{W * 0.6:.1f}pt;top:{base + i * gap:.1f}pt;'
                         f'border-bottom:.6pt solid #b9b0a0;height:0"></div>')
    return sec("".join(parts), "dedication")


def page_colophon(ctx: Ctx) -> str:
    W, H = ctx.W, ctx.H
    srcs, seen = [], set()
    for s in ctx.src.values():
        comp = s["comp"]
        if comp["slug"] in seen:
            continue
        seen.add(comp["slug"])
        url = comp.get("source_url") or (f"https://www.loc.gov/item/{comp['loc_item']}/" if comp.get("loc_item") else "")
        srcs.append(f"<p><b>{esc(comp['title'])}</b>"
                    f"{' (' + esc(comp['year']) + ')' if comp.get('year') else ''}<br>"
                    f"{esc(comp.get('contributor', ''))}{('<br>' + esc(url)) if url else ''}</p>")
    ai = any(s["ai"] for s in ctx.src.values())
    ai_note = ("<p><i>Layers marked “AI” were produced by Claude (Anthropic) directly from the page images. "
               "They have not been checked by a scholar and can contain errors, especially on damaged or "
               "unusual pages. Please read them as a guide to the original, not a substitute for it.</i></p>") if ai else ""
    rng = ctx.spec["range"]
    month = datetime.now(timezone.utc).strftime("%B %d, %Y").replace(" 0", " ")
    body = (f"<p class='disp' style='font-size:{W * 0.05:.1f}pt;font-weight:600;margin:0 0 .8em'>About this edition</p>"
            f"<p>Assembled on oedio.com from public-domain sources, pages {rng['from']}–{rng['to']}, {month}.</p>"
            f"{''.join(srcs)}{ai_note}"
            "<p>Typeset in EB Garamond, Cormorant Garamond and Noto Naskh Arabic (SIL Open Font License).</p>")
    return sec(f'<div class="abs" style="left:{W * 0.14:.1f}pt;width:{W * 0.72:.1f}pt;top:{H * 0.14:.1f}pt;'
               f'font-size:{W * 0.0215:.1f}pt;line-height:1.5;color:#4d453b;text-align:left">{body}</div>', "colophon")


def toc_rows_per_page(ctx) -> int:
    return max(8, int((ctx.H * 0.70) / 17.0))


def page_toc(ctx: Ctx, entries, first: bool) -> str:
    W, H = ctx.W, ctx.H
    head = ""
    top = H * 0.09
    if first:
        head = (f'<div class="abs ctr disp" style="left:0;width:{W:.1f}pt;top:{H * 0.09:.1f}pt;font-size:{W * 0.062:.1f}pt;'
                f'font-weight:600;letter-spacing:.08em">Contents</div>'
                f'<div class="abs ctr" style="left:0;width:{W:.1f}pt;top:{H * 0.145:.1f}pt">{_divider_svg("#8a6a1f", 1, 80)}</div>')
        top = H * 0.185
    rows = "".join(f'<div class="toc-row"><span class="t">{esc(e["title"])}</span><span class="d"></span>'
                   f'<span class="n">{e["page"]}</span></div>' for e in entries)
    return sec(f'{head}<div class="abs" style="left:{W * 0.14:.1f}pt;width:{W * 0.72:.1f}pt;top:{top:.1f}pt">{rows}</div>', "toc")


# ---------------------------------------------------------------------------
# Contents (headings) detection + range TOC
# ---------------------------------------------------------------------------
_STRICT = re.compile(r"^(chapter|book|part|section|canto|plate|psalm|sura|surah|volume|vol\.|preface|introduction|"
                     r"prologue|epilogue|appendix)\b", re.I)
_LOOSE = re.compile(r"^(on|of|concerning|description of|the|in the|how|a|an) ", re.I)


def detect_headings(raw_spec: dict, source_id=None, limit=150):
    return _detect_headings(Ctx(raw_spec, mode="web"), source_id, limit)


def _detect_headings(ctx, source_id=None, limit=150):
    sid = source_id if source_id in ctx.src else next(
        (i for i, s in ctx.src.items() if s["view"] == "text"), next(iter(ctx.src)))
    src = ctx.src[sid]
    if src["view"] != "text":
        return []
    rng = ctx.spec["range"]
    strict, loose, last = [], [], None
    for p in range(rng["from"], rng["to"] + 1):
        e = src["pages"].get(p)
        text = ((e or {}).get("text") or "").strip()
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        first = re.sub(r"^[#*_\s]+|[*_\s]+$", "", lines[0]) if lines else ""
        if not (3 <= len(first) <= 80) or first == "—" or first == last:
            continue
        letters = re.sub(r"[^A-Za-z]", "", first)
        is_caps = len(letters) >= 4 and first.upper() == first
        if is_caps or _STRICT.match(first):
            strict.append({"title": first.rstrip(".:"), "page": p})
            last = first
        elif _LOOSE.match(first) and len(first) <= 70 and not first.endswith("."):
            loose.append({"title": first.rstrip(":"), "page": p})
            last = first
    out = strict if len(strict) >= 3 else loose
    if len(out) > limit:
        step = len(out) / limit
        out = [out[int(i * step)] for i in range(limit)]
    return out


def toc_entries(ctx: Ctx):
    t = ctx.spec["toc"]
    rng = ctx.spec["range"]
    if t["mode"] == "none":
        return []
    if t["mode"] == "custom":
        ent = [e for e in t["entries"] if rng["from"] <= e["page"] <= rng["to"]]
    elif t["mode"] == "ranges":
        ent, n = [], t["every"]
        for a in range(rng["from"], rng["to"] + 1, n):
            b = min(a + n - 1, rng["to"])
            ent.append({"title": f"Pages {a}–{b}" if b > a else f"Page {a}", "page": a})
    else:
        ent = _detect_headings(ctx, t["source"])
    for e in ent:
        if len(e["title"]) > 78:
            e["title"] = e["title"][:77].rstrip() + "…"
    return sorted(ent, key=lambda e: e["page"])[:300]


# ---------------------------------------------------------------------------
# Plan (page order, parity rules) -- spreads vs singles
# ---------------------------------------------------------------------------
def build_plan(ctx: Ctx, entries):
    spec = ctx.spec
    spread = spec["mode"] == "spread"
    items = []

    def add(kind, **kw):
        items.append({"kind": kind, **kw})

    def pad(parity):
        if spread and ((len(items) % 2 == 1) != (parity == "verso")):
            add("blank")

    add("cover")
    add("frontispiece")
    add("title")
    ded = spec["dedication"]["enabled"]
    if spec["colophon"] or ded:
        add("colophon" if spec["colophon"] else "blank")
        add("dedication" if ded else "blank")
    toc_start = None
    if entries:
        pad("recto")
        per = toc_rows_per_page(ctx)
        chunks = [entries[i:i + per] for i in range(0, len(entries), per)] or [[]]
        toc_start = len(items)
        for i, ch in enumerate(chunks):
            add("toc", entries=ch, first=(i == 0))
    pad("verso")
    body_start = len(items)
    rng = spec["range"]
    if spread and is_consecutive(spec):
        for p in range(rng["from"], rng["to"] + 1, 2):
            add("body", p=p, side="L")
            if p + 1 <= rng["to"]:
                add("body", p=p + 1, side="R")
            else:
                add("blank")
    else:
        for p in range(rng["from"], rng["to"] + 1):
            if spread:
                add("body", p=p, side="L")
                add("body", p=p, side="R")
            else:
                add("body", p=p, side="S")
    pad("verso")
    add("back")
    return items, body_start, toc_start


def item_html(ctx: Ctx, it) -> str:
    k = it["kind"]
    if k == "cover":
        return cover_front(ctx)
    if k == "back":
        return cover_back(ctx)
    if k == "frontispiece":
        return page_frontispiece(ctx)
    if k == "title":
        return page_title(ctx)
    if k == "colophon":
        return page_colophon(ctx)
    if k == "dedication":
        return page_dedication(ctx)
    if k == "toc":
        return page_toc(ctx, it["entries"], it["first"])
    if k == "body":
        return body_leaf(ctx, it["p"], it["side"])
    return sec("", "blank")


def preview_html(raw_spec: dict, kind: str, p=None, side="L") -> str:
    """Exact single-page HTML for the in-browser preview."""
    ctx = Ctx(raw_spec, mode="web")
    if kind == "body":
        rng = ctx.spec["range"]
        p = max(rng["from"], min(rng["to"], int(p or rng["from"])))
        if ctx.spec["mode"] == "single":
            side = "S"
        if is_consecutive(ctx.spec):
            p = rng["from"] + ((p - rng["from"]) // 2) * 2       # spreads start on from, from+2, ...
            if side == "R":
                p += 1
                if p > rng["to"]:
                    return doc_html(ctx, [sec("", "blank")])
        return doc_html(ctx, [body_leaf(ctx, p, "R" if side == "R" else ("S" if side == "S" else "L"))])
    if kind == "toc":
        ent = toc_entries(ctx)[: toc_rows_per_page(ctx)]
        return doc_html(ctx, [page_toc(ctx, ent or [{"title": "Contents appear here", "page": ctx.spec["range"]["from"]}], True)])
    fn = {"front": cover_front, "back": cover_back, "frontispiece": page_frontispiece, "title": page_title,
          "dedication": page_dedication, "colophon": page_colophon}.get(kind)
    if not fn:
        raise SpecError("Unknown preview kind")
    return doc_html(ctx, [fn(ctx)])


# ---------------------------------------------------------------------------
# Estimate
# ---------------------------------------------------------------------------
def estimate(raw_spec: dict) -> dict:
    ctx = Ctx(raw_spec, mode="web")
    spec = ctx.spec
    n_pages = spec["range"]["to"] - spec["range"]["from"] + 1
    imgs = 0
    consec = is_consecutive(spec)
    sides = ("L",) if consec else (("L", "R") if spec["mode"] == "spread" else ("S",))
    for side in sides:
        lay = ctx.spec["left"] if side in ("L", "S") else ctx.spec["right"]
        ids = []
        if lay["layout"] == "full":
            ids = [lay["src"]]
        elif lay["layout"] == "split":
            ids = lay["panels"]
        imgs += sum(1 for i in ids if ctx.src[i]["view"] == "image") * n_pages
    imgs += (1 if ctx.image_url_for(spec["cover"]["image"]) else 0) + (1 if ctx.image_url_for(spec["frontispiece"]["image"]) else 0)
    q = QUALITY[spec["quality"]]
    text_pages = n_pages * len(sides)
    est_bytes = imgs * q["est"] + text_pages * 6_000 + 400_000
    mult = 2 if spec["mode"] == "spread" and not consec else 1
    return {
        "body_pages": n_pages, "pdf_pages": n_pages * mult + 12, "images": imgs,
        "est_bytes": int(est_bytes), "est_seconds": int(20 + imgs * 0.6 + n_pages * mult * 0.12),
        "email_ok": est_bytes <= 20_000_000,
    }


# ---------------------------------------------------------------------------
# Image fetch + processing
# ---------------------------------------------------------------------------
def _fetch_bytes(url):
    if url.startswith("/static/"):
        with open(os.path.join(BASE_DIR, url.lstrip("/")), "rb") as fh:
            return fh.read()
    last = None
    for attempt in range(4):
        try:
            hdrs = {"User-Agent": UA, "Accept": "image/*,*/*;q=0.8"}
            if attempt % 2 == 1:  # some hosts refuse unfamiliar bot agents from cloud IPs; retry like a browser
                hdrs = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                      "Chrome/124.0 Safari/537.36 oedio.com",
                        "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                        "Referer": "https://www.loc.gov/"}
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read(60_000_000)
        except urllib.error.HTTPError as e:
            last = e
            wait = 2.0 * (attempt + 1)
            if e.code in (429, 503):
                try:
                    wait = max(wait, min(20.0, float(e.headers.get("Retry-After", 0))))
                except (TypeError, ValueError):
                    pass
            elif e.code in (400, 401, 404):
                if attempt >= 1:
                    break
            time.sleep(wait)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2.0 * (attempt + 1))
    raise last


def prepare_image(url, quality):
    q = QUALITY[quality]
    key = hashlib.sha256(url.encode()).hexdigest()
    path = os.path.join(image_cache_dir(quality), key + ".jpg")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    return store_image(url, _fetch_bytes(url), quality)


def store_image(url, data, quality):
    """Downscale/re-encode raw scan bytes into the shared cache (also used for browser-supplied scans)."""
    q = QUALITY[quality]
    key = hashlib.sha256(url.encode()).hexdigest()
    path = os.path.join(image_cache_dir(quality), key + ".jpg")
    Image.MAX_IMAGE_PIXELS = 250_000_000
    im = Image.open(io.BytesIO(data))
    try:
        im.draft("RGB", (q["px"], q["px"]))
    except Exception:  # noqa: BLE001
        pass
    im = im.convert("RGB")
    im.thumbnail((q["px"], q["px"]), Image.LANCZOS)
    tmp = path + ".tmp"
    im.save(tmp, "JPEG", quality=q["q"], optimize=True)
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
class Progress:
    def __init__(self, jobdir):
        self.path = os.path.join(jobdir, "progress.json")
        self.state = {"status": "queued", "stage": "Queued", "pct": 0, "warnings": [], "message": ""}

    def update(self, **kw):
        self.state.update(kw)
        self.state["updated"] = time.time()
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.state, fh)
        os.replace(tmp, self.path)


def plan_image_urls(ctx, items):
    """Every distinct scan URL the finished book will embed."""
    urls = []
    for it in items:
        if it["kind"] == "body":
            lay = ctx.layout_for(it["side"])
            ids = [lay["src"]] if lay["layout"] == "full" else (lay["panels"] if lay["layout"] == "split" else [])
            for sid in ids:
                s = ctx.src[sid]
                if s["view"] == "image":
                    e = s["pages"].get(it["p"])
                    if e and e.get("image"):
                        urls.append(e["image"])
    for ref in (ctx.spec["cover"]["image"], ctx.spec["frontispiece"]["image"]):
        u = ctx.image_url_for(ref)
        if u:
            urls.append(u)
    return list(dict.fromkeys(urls))


# Hosts that refuse our cloud server's IP but allow browser downloads (CORS *): the visitor's
# browser fetches these scans and hands them to the builder.
CLIENT_FETCH_HOSTS = {"tile.loc.gov"}


def client_fetch_urls(raw_spec):
    ctx = Ctx(raw_spec, mode="pdf")
    items, _, _ = build_plan(ctx, toc_entries(ctx))
    out = []
    for u in plan_image_urls(ctx, items):
        h = urllib.parse.urlparse(u).hostname if u.startswith("http") else None
        if h in CLIENT_FETCH_HOSTS and not _cached(u, ctx.spec["quality"]):
            out.append(u)
    return out, ctx.spec["quality"]


def _cached(url, quality):
    key = hashlib.sha256(url.encode()).hexdigest()
    path = os.path.join(image_cache_dir(quality), key + ".jpg")
    return os.path.exists(path) and os.path.getsize(path) > 0


def build_book(jobdir: str):
    prog = Progress(jobdir)
    t0 = time.time()
    try:
        with open(os.path.join(jobdir, "spec.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
        prog.update(status="running", stage="Reading sources", pct=2, started=t0)
        ctx = Ctx(raw, mode="pdf")
        entries = toc_entries(ctx)
        items, body_start, _ = build_plan(ctx, entries)

        # -- 1. scans ----------------------------------------------------------
        urls = plan_image_urls(ctx, items)
        failed = 0
        first_err = ""
        if urls:
            done = 0
            with ThreadPoolExecutor(max_workers=4) as ex:
                futs = {ex.submit(prepare_image, u, ctx.spec["quality"]): u for u in urls}
                for f in as_completed(futs):
                    u = futs[f]
                    try:
                        ctx.images[u] = f.result()
                    except Exception as e:  # noqa: BLE001
                        failed += 1
                        first_err = first_err or f"{type(e).__name__}: {e}"[:160]
                    done += 1
                    if done % 3 == 0 or done == len(urls):
                        prog.update(stage=f"Fetching page scans ({done}/{len(urls)})",
                                    pct=5 + int(55 * done / len(urls)))
        if failed:
            ctx.warnings.append(f"{failed} page scan(s) could not be fetched and appear as 'scan unavailable'. ({first_err})")

        # -- 2. render ---------------------------------------------------------
        from weasyprint import HTML
        from pypdf import PdfReader, PdfWriter

        work = os.path.join(jobdir, "work")
        os.makedirs(work, exist_ok=True)
        CH = 24
        chunk_files = []
        n_chunks = math.ceil(len(items) / CH)
        for ci in range(n_chunks):
            sub = items[ci * CH:(ci + 1) * CH]
            prog.update(stage=f"Typesetting pages ({min(len(items), (ci + 1) * CH)}/{len(items)})",
                        pct=60 + int(32 * ci / max(1, n_chunks)))
            doc = doc_html(ctx, [item_html(ctx, it) for it in sub])
            out = os.path.join(work, f"chunk{ci:03d}.pdf")
            HTML(string=doc, base_url=work).write_pdf(out)
            chunk_files.append(out)

        # -- 3. merge ----------------------------------------------------------
        prog.update(stage="Assembling PDF", pct=94)
        w = PdfWriter()
        for cf in chunk_files:
            w.append(PdfReader(cf))
        step = 2 if ctx.spec["mode"] == "spread" else 1
        spec = ctx.spec
        w.add_outline_item("Front cover", 0)
        w.add_outline_item("Title page", 2)
        for i, it in enumerate(items):
            if it["kind"] == "dedication" and spec["dedication"]["enabled"]:
                w.add_outline_item("Dedication", i)
            if it["kind"] == "toc" and it["first"]:
                w.add_outline_item("Contents", i)
        text_item = w.add_outline_item("Text", body_start)
        for e in entries:
            idx = body_start + (e["page"] - spec["range"]["from"]) * step
            if 0 <= idx < len(items):
                w.add_outline_item(e["title"], idx, parent=text_item)
        w.add_outline_item("Back cover", len(items) - 1)
        title = spec["cover"]["title"]
        w.add_metadata({"/Title": title, "/Author": spec["cover"]["byline"] or "oedio.com",
                        "/Creator": "oedio.com Book Studio", "/Subject": ctx.mb["title"]})
        if spec["mode"] == "spread":
            w.page_layout = "/TwoPageRight"
        w.page_mode = "/UseOutlines" if entries else "/UseNone"
        w.compress_identical_objects(remove_identicals=True, remove_orphans=True)
        final = os.path.join(jobdir, "book.pdf")
        with open(final + ".tmp", "wb") as fh:
            w.write(fh)
        os.replace(final + ".tmp", final)
        shutil.rmtree(work, ignore_errors=True)
        if ctx.trimmed:
            ctx.warnings.append(f"{ctx.trimmed} text panel(s) were too long to fit and end with “[…]”. "
                                "Try a larger page size or fewer panels per page.")
        if ctx.small:
            ctx.warnings.append(f"{ctx.small} text panel(s) use very small type (under 6 pt) to keep every word. "
                                "A larger page size (8.5x11 or A4) makes them easier to read.")
        size = os.path.getsize(final)
        meta = {"title": title, "byline": spec["cover"]["byline"], "pages": len(items), "bytes": size,
                "created": datetime.now(timezone.utc).isoformat(), "mode": spec["mode"], "trim": spec["trim"],
                "megabook": spec["megabook"], "megabook_title": ctx.mb["title"],
                "sources": [ctx.src[s["id"]]["short"] for s in spec["sources"]],
                "range": spec["range"], "spread": spec["mode"] == "spread"}
        with open(os.path.join(jobdir, "meta.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
        prog.update(status="done", stage="Done", pct=100, bytes=size, pages=len(items),
                    warnings=ctx.warnings, seconds=round(time.time() - t0, 1))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        prog.update(status="error", stage="Failed", message=f"{type(e).__name__}: {e}"[:300])
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "build":
        build_book(sys.argv[2])
    else:
        print("usage: bookbuilder.py build <jobdir>")
