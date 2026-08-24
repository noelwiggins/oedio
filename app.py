"""oedio.com — the megabook library.

A megabook is one work compiled from multiple public-domain (pre-1929)
digitized editions: original languages, competing translations, illustrated
printings, commentaries. Prototype sources everything from the Library of
Congress; the reader-data contract ([{page, text, image}] per component)
is source-agnostic so Internet Archive / Google Books ingest can be added
without touching the reader.
"""
import json
import os
import re
import sqlite3
import functools
import urllib.request
import urllib.error
from datetime import datetime

from flask import Flask, abort, jsonify, render_template, request

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-6"


def _call_claude(prompt, max_tokens=1200):
    """A direct, live call to Claude for on-demand reader-assist features
    (chapter overviews, page notes, contextual Q&A) -- distinct from the
    forge translation pipeline, which runs offline and writes to disk.
    These are short, user-triggered calls, not bulk background jobs."""
    if not ANTHROPIC_API_KEY:
        return None
    body = json.dumps({
        "model": ANTHROPIC_MODEL, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=45)
        data = json.loads(resp.read())
        return data["content"][0]["text"]
    except Exception as e:
        print(f"_call_claude failed: {e}")
        return None

# ── R2 reader-data base URL ──────────────────────────────────────────────────
# Set R2_BASE_URL in Railway env to serve reader-data from Cloudflare R2.
# Falls back to /static/reader-data/ (repo files) when not set.
_R2_BASE = os.environ.get("R2_BASE_URL", "").rstrip("/")
def _reader_url(slug):
    if _R2_BASE:
        return f"{_R2_BASE}/reader-data/{slug}.json"
    return f"/static/reader-data/{slug}.json"


app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BASE_DIR, "data", "manifest.json")

with open(MANIFEST_PATH) as f:
    MANIFEST = json.load(f)
MEGABOOKS = MANIFEST["megabooks"]
SECTIONS  = MANIFEST.get("sections", [])
SECTION_MAP = {s["slug"]: s for s in SECTIONS}


@app.context_processor
def inject_site_index():
    """Every page gets a light-weight index of every section and title on
    the site, for the header's Index dropdown -- no page needs to remember
    to pass this in explicitly."""
    by_section = {}
    for mb in MEGABOOKS:
        by_section.setdefault(mb.get("section", "_other"), []).append(
            {"slug": mb["slug"], "title": mb["title"]})
    site_index = []
    for s in SECTIONS:
        titles = sorted(by_section.get(s["slug"], []), key=lambda t: t["title"])
        if titles:
            site_index.append({"section_title": s["title"], "section_slug": s["slug"], "titles": titles})
    return {"site_index": site_index}


def _page_count(slug):
    """Fast page count: use file size to estimate, never load large files."""
    path = os.path.join(BASE_DIR, "static", "reader-data", f"{slug}.json")
    try:
        file_size = os.path.getsize(path)
        if file_size == 0:
            return 0
        if file_size > 500_000:
            # Large file: estimate pages from size (rough: 5KB per page average)
            return max(1, int(file_size / 5000))
        with open(path) as fh:
            data = json.load(fh)
            return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


# Page counts computed lazily per-request in megabook_page() to avoid startup I/O.
# Set to 0 here so templates that reference c["pages"] don't KeyError.
for _mb in MEGABOOKS:
    for _c in _mb["components"]:
        _c["pages"] = 0


# ---------------------------------------------------------------------------
# Panel groups: when a facsimile component has AI-forged sibling layers
# (a "-transcription" and/or "-english" derived from its own page images,
# via scripts/forge_translate.py), all three share identical pagination and
# identical source images. That makes them swappable independently in the
# reader's two panels -- like map layers, but for a single page rather than
# a whole book. PANEL_GROUPS maps every member slug to the same group list,
# so the dropdowns show the same set of choices no matter which one you
# opened. Books without derived layers (the vast majority) get an empty
# group and the reader behaves exactly as before -- no dropdowns rendered.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Panel groups: components that map page-for-page onto the same base scan
# (a transcription, one or more translations -- historical or AI-generated
# -- a facing commentary keyed to the same pages) are swappable in the
# reader via the floating layer toggle, with the scan as the fixed
# orientation point every other layer aligns against.
#
# Two ways a component joins a group:
#   1. Implicit (the original convention): a "{base}-transcription" or
#      "{base}-english" slug is auto-detected as belonging to "{base}".
#   2. Explicit: any component can set "layer_of": "<base_slug>" and an
#      optional "layer_kind" (e.g. "translation", "commentary") to join a
#      group without following the naming convention -- this is what lets
#      a title carry more than one translation (an old historical one
#      alongside an AI one) or a non-text layer like a critical essay.
# Books without any of this get an empty group and the reader behaves
# exactly as before -- no layer toggle rendered.
# ---------------------------------------------------------------------------
PANEL_GROUPS = {}
for _mb in MEGABOOKS:
    _by_slug = {c["slug"]: c for c in _mb["components"]}
    _members_of = {}  # base_slug -> ordered list of member slugs

    for _c in _mb["components"]:
        _base = _c.get("layer_of")
        if _base and _base in _by_slug:
            _members_of.setdefault(_base, [_base]).append(_c["slug"])

    for _base in _by_slug:
        _tr, _en = f"{_base}-transcription", f"{_base}-english"
        if _tr in _by_slug or _en in _by_slug:
            _lst = _members_of.setdefault(_base, [_base])
            if _tr in _by_slug and _tr not in _lst: _lst.append(_tr)
            if _en in _by_slug and _en not in _lst: _lst.append(_en)

    for _base, _member_slugs in _members_of.items():
        _group = []
        for _slug in _member_slugs:
            _mc = _by_slug[_slug]
            _data_slug = _mc.get("data_slug", _slug)
            if _slug == _base:
                _group.append({"slug": _slug, "data_slug": _data_slug, "kind": "image", "label": "Original scan"})
            else:
                _group.append({"slug": _slug, "data_slug": _data_slug, "kind": _mc.get("layer_kind", "text"), "label": _mc["title"]})
        for _slug in _member_slugs:
            PANEL_GROUPS[_slug] = _group


# ---------------------------------------------------------------------------
# Optional Postgres catalog. The manifest is the source of truth; the DB
# mirrors it so future features (reading progress, user shelves, corrections)
# have somewhere to live. App runs fine with no DATABASE_URL.
# ---------------------------------------------------------------------------
db = None
if os.environ.get("DATABASE_URL"):
    try:
        from flask_sqlalchemy import SQLAlchemy

        uri = os.environ["DATABASE_URL"]
        if uri.startswith("postgres://"):
            uri = uri.replace("postgres://", "postgresql+psycopg://", 1)
        elif uri.startswith("postgresql://"):
            uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)
        app.config["SQLALCHEMY_DATABASE_URI"] = uri
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db = SQLAlchemy(app)

        class Megabook(db.Model):
            __tablename__ = "megabooks"
            slug = db.Column(db.String(80), primary_key=True)
            title = db.Column(db.String(200))
            author = db.Column(db.String(200))
            meta = db.Column(db.JSON)

        class Component(db.Model):
            __tablename__ = "components"
            slug = db.Column(db.String(80), primary_key=True)
            megabook_slug = db.Column(db.String(80), db.ForeignKey("megabooks.slug"))
            title = db.Column(db.String(300))
            role = db.Column(db.String(80))
            year = db.Column(db.Integer)
            loc_item = db.Column(db.String(40))
            facsimile = db.Column(db.Boolean, default=False)
            meta = db.Column(db.JSON)

        with app.app_context():
            db.create_all()
            for mb in MEGABOOKS:
                row = db.session.get(Megabook, mb["slug"]) or Megabook(slug=mb["slug"])
                row.title, row.author = mb["title"], mb["author"]
                row.meta = {"description": mb["description"]}
                db.session.add(row)
                for c in mb["components"]:
                    cr = db.session.get(Component, c["slug"]) or Component(slug=c["slug"])
                    cr.megabook_slug = mb["slug"]
                    cr.title, cr.role, cr.year = c["title"], c["role"], c["year"]
                    cr.loc_item, cr.facsimile = c["loc_item"], c["facsimile"]
                    cr.meta = {"contributor": c["contributor"], "note": c["note"]}
                    db.session.add(cr)
            db.session.commit()
    except Exception as e:  # never let catalog mirroring take the site down
        print(f"[oedio] Postgres catalog unavailable, running from manifest: {e}")
        db = None


# Every megabook needs a single, consistent "Open Reader" entry point --
# the Odyssey has a true book-aligned layered reader; everything else opens
# into the standard reader on a sensibly chosen default edition (prefer a
# real text edition over a pure facsimile, so the first thing a reader sees
# is text+scan, not a bare image stream).
for _mb in MEGABOOKS:
    _default = next((c for c in _mb["components"] if not c["facsimile"]), _mb["components"][0])
    _mb["default_read_slug"] = _default["slug"]


def _find_megabook(mega_slug):
    return next((m for m in MEGABOOKS if m["slug"] == mega_slug), None)


@app.route("/")
def library():
    return render_template("index.html", now=datetime.utcnow(),
        sections=SECTIONS,
        megabooks_by_section={s["slug"]: [mb for mb in MEGABOOKS if mb.get("section") == s["slug"]] for s in SECTIONS},
                           megabooks=MEGABOOKS, active_page="library")


@functools.lru_cache(maxsize=1)
def _search_db():
    """Cached read-only connection to the full-text search index (see
    scripts/build_search_index.py). Contentless FTS5 -- the index itself
    holds no page text, only the inverted index + page metadata, so it
    stays small enough to commit to the repo. Returns None if the index
    hasn't been built yet, so search degrades gracefully rather than 500ing."""
    path = "data/search_index.sqlite"
    if not os.path.exists(path):
        return None
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    return con


def _fts_query(q):
    """Turn a raw user query into an FTS5 MATCH expression: each word is a
    separate prefix term, ANDed together, so 'ginger fever' requires both
    words to appear somewhere on the page (not as an exact phrase)."""
    words = re.findall(r"\w+", q)
    if not words:
        return None
    return " AND ".join(f'"{w}"*' for w in words)


@app.route("/api/search/fulltext")
def api_search_fulltext():
    """Real full-text search across every indexed page (36k+ pages, ~9M
    words) via SQLite FTS5. Returns page-level hits with a snippet built
    from the actual page text (re-read from the original reader-data JSON
    at request time, since the index itself is contentless) and a direct
    deep link into the reader at that exact page."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"results": [], "query": q})
    con = _search_db()
    if con is None:
        return jsonify({"results": [], "query": q, "error": "search index not built"}), 503

    match_expr = _fts_query(q)
    if not match_expr:
        return jsonify({"results": [], "query": q})

    rows = con.execute(
        """
        SELECT m.megabook_slug, m.megabook_title, m.component_slug, m.component_title, m.page,
               bm25(pages_fts) AS rank
        FROM pages_fts
        JOIN pages_meta m ON m.rowid = pages_fts.rowid
        WHERE pages_fts MATCH ?
        ORDER BY rank
        LIMIT 30
        """,
        (match_expr,),
    ).fetchall()

    words_lower = [w.lower() for w in re.findall(r"\w+", q)]
    results = []
    for megabook_slug, megabook_title, component_slug, component_title, page, rank in rows:
        comp = _find_component(megabook_slug, component_slug)
        data_slug = comp.get("data_slug", component_slug) if comp else component_slug
        text = _page_text(data_slug, page)
        snippet = _build_snippet(text, words_lower) if text else ""
        results.append({
            "megabook_slug": megabook_slug, "megabook_title": megabook_title,
            "component_slug": component_slug, "component_title": component_title,
            "page": page, "snippet": snippet,
        })
    return jsonify({"results": results, "query": q})


def _find_component(megabook_slug, component_slug):
    mb = next((m for m in MEGABOOKS if m["slug"] == megabook_slug), None)
    if not mb:
        return None
    return next((c for c in mb.get("components", []) if c["slug"] == component_slug), None)


@functools.lru_cache(maxsize=256)
def _page_text(data_slug, page_num):
    path = f"static/reader-data/{data_slug}.json"
    if not os.path.exists(path):
        return ""
    pages = json.load(open(path, encoding="utf-8"))
    p = next((x for x in pages if x.get("page") == page_num), None)
    return _strip_fn_tokens((p or {}).get("text", "") or "")


def _build_snippet(text, words_lower, radius=90):
    """Find the first occurrence of any query word and return surrounding
    context, rather than just the start of the page -- a hit 3000
    characters into a page is useless to show as 'the first 90 chars'."""
    low = text.lower()
    pos = -1
    for w in words_lower:
        idx = low.find(w)
        if idx != -1 and (pos == -1 or idx < pos):
            pos = idx
    if pos == -1:
        return text[:180].strip() + ("…" if len(text) > 180 else "")
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


@app.route("/api/search")
def api_search():
    """Site-wide metadata search across every Oedio's title, author,
    description, and component roles/notes/contributors -- fast, one result
    per book, good for "does oedio have anything on X". For real full-text
    search across page content itself, see /api/search/fulltext, which
    queries the SQLite FTS5 index built by scripts/build_search_index.py."""
    q = (request.args.get("q") or "").strip().lower()
    if len(q) < 2:
        return jsonify({"results": [], "query": q})
    terms = [t for t in q.split() if t]
    results = []
    for mb in MEGABOOKS:
        title_l = (mb.get("title") or "").lower()
        author_l = (mb.get("author") or "").lower()
        desc = mb.get("description") or ""
        parts = [title_l, author_l, desc.lower()]
        matched_note = None
        for c in mb.get("components", []):
            note = c.get("note") or ""
            role = c.get("role") or ""
            ctitle = c.get("title") or ""
            contributor = c.get("contributor") or ""
            blob = f"{ctitle} {role} {contributor} {note}".lower()
            parts.append(blob)
            if matched_note is None and terms and all(t in blob for t in terms):
                matched_note = note or ctitle
        haystack = " \n".join(parts)
        if not all(t in haystack for t in terms):
            continue
        score = sum(haystack.count(t) for t in terms)
        if any(t in title_l for t in terms):
            score += 50
        if any(t in author_l for t in terms):
            score += 30
        snippet = matched_note or desc
        results.append({
            "slug": mb["slug"], "title": mb["title"], "author": mb.get("author", ""),
            "section": mb.get("section", ""), "snippet": snippet[:240],
            "spine_color": mb.get("spine_color", ""), "score": score,
        })
    results.sort(key=lambda r: -r["score"])
    return jsonify({"results": results[:24], "query": q})



@app.route("/section/<section_slug>")
def section_page(section_slug):
    section = SECTION_MAP.get(section_slug)
    if not section:
        from flask import abort; abort(404)
    mbs = [mb for mb in MEGABOOKS if mb.get("section") == section_slug]
    from datetime import datetime
    return render_template("section.html", section=section, megabooks=mbs, now=datetime.utcnow(), active_page="library")


@app.route("/book/<mega_slug>")
def megabook_page(mega_slug):
    mb = _find_megabook(mega_slug)
    if not mb:
        abort(404)
    # Compute page counts lazily here (not at startup) to avoid I/O delays
    for c in mb["components"]:
        if c["pages"] == 0:
            c["pages"] = _page_count(c.get("data_slug", c["slug"]))

    # Multi-volume works (set via "group" on each volume's base-scan
    # component) collapse into a single representative spine here, rather
    # than cluttering the shelf with every volume and every one of their
    # own transcription/translation layers as flat peers. Tapping that
    # spine opens a sub-Oedio: a second rotunda of just that work's
    # volumes. Only base-scan components carry "group" -- their own
    # transcription/english siblings are found via PANEL_GROUPS once a
    # specific volume is chosen, same as any other book.
    display_components, seen_groups = [], set()
    for c in mb["components"]:
        grp = c.get("group")
        if grp:
            if grp in seen_groups:
                continue
            seen_groups.add(grp)
            vols = [x for x in mb["components"] if x.get("group") == grp]
            total_pages = sum(v["pages"] for v in vols)
            display_components.append({
                **c, "title": c["group_title"], "is_group": True, "group_slug": grp,
                "pages": total_pages,
                "note": f"{len(vols)} volumes, {total_pages} pages total. " + c.get("note", ""),
            })
        elif not c.get("layer_of") and not c["slug"].endswith(("-transcription", "-english")):
            display_components.append(c)

    # Group components by role, preserving manifest order of first appearance.
    grouped, order = {}, []
    for c in display_components:
        if c["role"] not in grouped:
            grouped[c["role"]] = []
            order.append(c["role"])
        grouped[c["role"]].append(c)

    open_reader_url = (f"/book/{mega_slug}/layers" if mega_slug == "odyssey"
                        else f"/book/{mega_slug}/read/{mb['default_read_slug']}")
    return render_template("megabook.html", now=datetime.utcnow(), mb=mb,
                           grouped=[(r, grouped[r]) for r in order],
                           open_reader_url=open_reader_url,
                           active_page="library")


FN_TOKEN_RE = re.compile(r"\u27e6fn:[^\u27e7]+\u27e7")


def _strip_fn_tokens(text):
    """Remove the \u27e6fn:ID\u27e7 inline footnote-marker tokens (see
    scripts/parse_gibbon.py) before feeding page text to the AI assist
    endpoints -- they're reader-UI plumbing, not prose."""
    return FN_TOKEN_RE.sub("", text or "")


def _gather_page_context(mb, comp, page_num, lookback=15):
    """Pull the text of the current page plus a lookback window of prior
    pages from the same component, for feeding to the AI-assist endpoints."""
    path = f"static/reader-data/{comp.get('data_slug', comp['slug'])}.json"
    if not os.path.exists(path):
        return "", ""
    pages = json.load(open(path))
    pages_by_num = {p["page"]: p for p in pages}
    current_text = _strip_fn_tokens((pages_by_num.get(page_num) or {}).get("text", "") or "")
    window_text = []
    for p in range(max(1, page_num - lookback), page_num + 1):
        t = _strip_fn_tokens((pages_by_num.get(p) or {}).get("text", "") or "")
        if t and t.strip() != "\u2014":
            window_text.append(t.strip())
    return current_text.strip(), "\n\n".join(window_text)


def _gather_page_footnotes(mb, comp, page_num):
    """Real footnotes (not AI-generated) attached to this page, if the
    component carries them -- see parse_gibbon.py's "footnotes" field."""
    path = f"static/reader-data/{comp.get('data_slug', comp['slug'])}.json"
    if not os.path.exists(path):
        return []
    pages = json.load(open(path))
    page = next((p for p in pages if p.get("page") == page_num), None)
    return (page or {}).get("footnotes") or []


@app.route("/book/<mega_slug>/read/<comp_slug>/ai-overview")
def ai_overview(mega_slug, comp_slug):
    mb = _find_megabook(mega_slug)
    if not mb:
        abort(404)
    comp = next((c for c in mb["components"] if c["slug"] == comp_slug), None)
    if not comp:
        abort(404)
    page_num = request.args.get("page", 1, type=int)
    _, window = _gather_page_context(mb, comp, page_num, lookback=20)
    if not window:
        return jsonify({"error": "No transcribed text available for this section yet."}), 404
    prompt = (
        f"You are a literary scholar giving a reader a quick orientation. Below is an excerpt "
        f"from \"{comp['title']}\" ({comp.get('contributor', '')}, {comp.get('year', '')}), "
        f"part of {mb['title']}, covering roughly the last 20 pages up to where the reader "
        f"currently is.\n\nWrite, in your own words (do not quote long passages):\n"
        f"1. A short plain-language summary of what's happening in this stretch (2-4 sentences).\n"
        f"2. 2-3 salient points worth noting -- a turning point, a key introduction, a theme "
        f"emerging.\n"
        f"3. A brief critical/scholarly aside (1-2 sentences) -- something a knowledgeable "
        f"reader would find genuinely interesting about this section specifically.\n\n"
        f"Keep the whole response under 180 words, plain text, no headers or markdown.\n\n"
        f"---EXCERPT---\n{window[:9000]}"
    )
    result = _call_claude(prompt, max_tokens=500)
    if not result:
        return jsonify({"error": "Couldn't generate an overview right now -- try again in a moment."}), 503
    return jsonify({"overview": result.strip()})


@app.route("/book/<mega_slug>/read/<comp_slug>/ai-page-notes")
def ai_page_notes(mega_slug, comp_slug):
    mb = _find_megabook(mega_slug)
    if not mb:
        abort(404)
    comp = next((c for c in mb["components"] if c["slug"] == comp_slug), None)
    if not comp:
        abort(404)
    page_num = request.args.get("page", 1, type=int)
    page_text, _ = _gather_page_context(mb, comp, page_num, lookback=0)
    if not page_text or page_text == "\u2014":
        return jsonify({"error": "No transcribed text on this page to annotate."}), 404
    real_footnotes = _gather_page_footnotes(mb, comp, page_num)
    if real_footnotes:
        # This page already carries the author's/editor's real footnotes --
        # generating AI glosses that duplicate them would just be noise.
        # Instead: gloss what the footnotes themselves don't cover (obscure
        # classical names, untranslated Latin/Greek in the notes, historical
        # context a modern reader wouldn't have) so the two layers add up
        # to something neither gives alone.
        fn_digest = "\n".join(
            f"- [{f['type']}] {f['text'][:200]}" for f in real_footnotes[:25]
        )
        prompt = (
            f"You are helping a reader of \"{comp['title']}\" ({comp.get('contributor', '')}, "
            f"{comp.get('year', '')}). This page already has its own real footnotes "
            f"(citations to classical sources, plus editorial notes) -- listed below so you "
            f"don't repeat them.\n\n"
            f"Your job is different: gloss whatever the footnotes assume the reader already "
            f"knows and a modern reader likely doesn't -- who a cited classical author is, "
            f"what an untranslated Latin/Greek phrase in a note means, brief context for a "
            f"person, place, or event mentioned in passing. Skip anything already explained "
            f"by a footnote. Format as a simple list: **Term** — explanation. If nothing "
            f"needs glossing beyond what's already footnoted, say so plainly. Keep it under "
            f"220 words total.\n\n"
            f"---THIS PAGE'S EXISTING FOOTNOTES---\n{fn_digest}\n\n"
            f"---PAGE TEXT---\n{page_text[:6000]}"
        )
    else:
        prompt = (
            f"You are annotating a single page from \"{comp['title']}\" "
            f"({comp.get('contributor', '')}, {comp.get('year', '')}) like footnotes in a scholarly "
            f"edition. Below is the text of just this one page.\n\n"
            f"Identify the people, places, things, and any complex or unusual words/concepts "
            f"mentioned on this specific page, and give a brief explanatory note for each -- "
            f"in your own words, not quoted from any source. Skip anything too minor or obvious "
            f"to be worth a note. Format as a simple list: **Term** — explanation. "
            f"If nothing on the page warrants a note, say so plainly. Keep it under 220 words total.\n\n"
            f"---PAGE TEXT---\n{page_text[:6000]}"
        )
    result = _call_claude(prompt, max_tokens=600)
    if not result:
        return jsonify({"error": "Couldn't generate notes right now -- try again in a moment."}), 503
    return jsonify({"notes": result.strip()})


@app.route("/book/<mega_slug>/read/<comp_slug>/ai-ask")
def ai_ask(mega_slug, comp_slug):
    mb = _find_megabook(mega_slug)
    if not mb:
        abort(404)
    comp = next((c for c in mb["components"] if c["slug"] == comp_slug), None)
    if not comp:
        abort(404)
    page_num = request.args.get("page", 1, type=int)
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"error": "Ask a real question."}), 400
    page_text, window = _gather_page_context(mb, comp, page_num, lookback=8)
    prompt = (
        f"A reader is on page {page_num} of \"{comp['title']}\" ({comp.get('contributor', '')}, "
        f"{comp.get('year', '')}), part of {mb['title']} on oedio.com. Here is the text of "
        f"their current page and the several pages before it, for context:\n\n"
        f"---CONTEXT---\n{window[:7000]}\n---END CONTEXT---\n\n"
        f"The reader's question: \"{q}\"\n\n"
        f"Answer helpfully and directly, in your own words. If the question is about the "
        f"text itself, use the context above. If it goes beyond the text (broader history, "
        f"a modern parallel, an unrelated question), answer from general knowledge -- the "
        f"reader may be asking about something well outside this passage. Keep it focused "
        f"and under 200 words unless the question genuinely needs more."
    )
    result = _call_claude(prompt, max_tokens=700)
    if not result:
        return jsonify({"error": "Couldn't answer right now -- try again in a moment."}), 503
    return jsonify({"answer": result.strip()})


@app.route("/book/<mega_slug>/read/<comp_slug>/download")
def download_text(mega_slug, comp_slug):
    mb = _find_megabook(mega_slug)
    if not mb:
        abort(404)
    comp = next((c for c in mb["components"] if c["slug"] == comp_slug), None)
    if not comp:
        abort(404)
    path = f"static/reader-data/{comp.get('data_slug', comp_slug)}.json"
    if not os.path.exists(path):
        abort(404)
    pages = json.load(open(path))
    real_pages = [p for p in pages if (p.get("text") or "").strip() and p["text"].strip() != "\u2014"]

    lines = [
        comp["title"], "=" * len(comp["title"]), "",
        f"{comp.get('contributor', '')} \u00b7 {comp.get('year', '')}",
        f"Part of the {mb['title']} Oedio on oedio.com", "",
        f"Downloaded for offline reading \u00b7 {comp['url'] if 'url' in comp else f'https://oedio.com/book/{mega_slug}/read/{comp_slug}'}",
        "",
    ]
    if not real_pages:
        lines.append("(This edition is presented as facsimile scans only -- no transcribed or")
        lines.append(" translated text exists yet to include in a text download. View the scans")
        lines.append(" online for the visual content.)")
    else:
        for p in real_pages:
            lines.append(f"--- Page {p['page']} ---")
            lines.append("")
            lines.append(p["text"].strip())
            lines.append("")

    body = "\n".join(lines)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in comp["title"])[:80].strip() or comp_slug
    resp = app.response_class(body, mimetype="text/plain; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{safe_name}.txt"'
    return resp


@app.route("/book/<mega_slug>/search")
def megabook_search(mega_slug):
    mb = _find_megabook(mega_slug)
    if not mb:
        abort(404)
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"results": [], "query": q, "total": 0})
    q_lower = q.lower()
    offset = max(0, request.args.get("offset", 0, type=int))
    limit = min(50, max(1, request.args.get("limit", 30, type=int)))
    SCAN_CAP = 3000  # a defensive ceiling for pathological queries (e.g. single common letters), not a normal result count

    all_results = []
    for c in mb["components"]:
        slug = c["slug"]
        path = f"static/reader-data/{c.get('data_slug', slug)}.json"
        if not os.path.exists(path):
            continue
        try:
            pages = json.load(open(path))
        except Exception:
            continue
        for p in pages:
            text = p.get("text") or ""
            if not text or text.strip() == "\u2014":
                continue
            idx = text.lower().find(q_lower)
            if idx == -1:
                continue
            start = max(0, idx - 90)
            end = min(len(text), idx + len(q) + 90)
            snippet = text[start:end].strip()
            if start > 0:
                snippet = "\u2026" + snippet
            if end < len(text):
                snippet = snippet + "\u2026"
            all_results.append({
                "component_slug": slug, "component_title": c["title"],
                "page": p["page"], "snippet": snippet,
                "match_start": snippet.lower().find(q_lower),
                "match_len": len(q),
                "url": f"/book/{mega_slug}/read/{slug}?page={p['page']}",
            })
            if len(all_results) >= SCAN_CAP:
                break
        if len(all_results) >= SCAN_CAP:
            break

    total = len(all_results)
    page_slice = all_results[offset:offset + limit]
    return jsonify({
        "results": page_slice, "query": q, "total": total,
        "offset": offset, "has_more": offset + limit < total,
        "capped": total >= SCAN_CAP,
    })


@app.route("/book/<mega_slug>/group/<group_slug>")
def volume_group_page(mega_slug, group_slug):
    mb = _find_megabook(mega_slug)
    if not mb:
        abort(404)
    vols = [c for c in mb["components"] if c.get("group") == group_slug]
    if not vols:
        abort(404)
    for c in vols:
        if c["pages"] == 0:
            c["pages"] = _page_count(c.get("data_slug", c["slug"]))
    return render_template("volume_group.html", now=datetime.utcnow(), mb=mb,
                           group_slug=group_slug, group_title=vols[0]["group_title"],
                           volumes=vols, active_page="library")


@app.route("/book/<mega_slug>/read/<comp_slug>")
def reader(mega_slug, comp_slug):
    mb = _find_megabook(mega_slug)
    if not mb:
        abort(404)
    comp = next((c for c in mb["components"] if c["slug"] == comp_slug), None)
    if not comp:
        abort(404)
    siblings = [{"slug": c["slug"],
                 "label": f"{c['title']} ({c['year']})",
                 "url": f"/book/{mega_slug}/read/{c['slug']}"}
                for c in mb["components"]]

    panel_group = PANEL_GROUPS.get(comp_slug)
    left_default = None
    if panel_group:
        # Default the left (secondary) panel to whatever ISN'T already the
        # primary layer you opened, so the two panels never start on the
        # same content. Opening a text layer -> left defaults to the
        # original scan (today's existing appearance, unchanged). Opening
        # the raw facsimile itself -> left defaults to the English layer
        # if one exists, since "let me see the translation" is exactly the
        # gap this feature closes.
        others = [g for g in panel_group if g["slug"] != comp_slug]
        english_opt = next((g for g in others if g["slug"].endswith("-english")), None)
        image_opt = next((g for g in others if g["kind"] == "image"), None)
        left_default = (image_opt or others[0]) if comp["facsimile"] else (english_opt or (others[0] if others else None))
        left_default = left_default or (others[0] if others else None)

    return render_template(
        "reader.html", now=datetime.utcnow(),
        slug=comp_slug,
        mega_slug=mega_slug,
        mega_title=mb["title"],
        book_title=comp["title"],
        book_author=comp["contributor"],
        book_year=comp["year"],
        book_source_url=(comp.get("source_url") or
                          (f"https://www.loc.gov/item/{comp['loc_item']}/" if comp.get("loc_item") else None)),
        book_source_label=comp.get("source_label", "Library of Congress"),
        book_note=comp.get("note"),
        facsimile=comp["facsimile"],
        text_only=comp.get("text_only", False),
        is_translated=comp.get("translated", False),
        original_label=comp.get("original_label"),
        start_page=None,
        siblings=siblings,
        panel_group=panel_group,
        left_default=left_default,
        data_url=_reader_url(comp.get('data_slug', comp_slug)),
        oedio_map=mb.get("map"),
        oedio_illustrations=mb.get("illustrations"),
    )


@app.route("/book/<mega_slug>/layers")
def layered_reader(mega_slug):
    mb = _find_megabook(mega_slug)
    if not mb or mega_slug != "odyssey":  # layered mode ships per-work as alignment data exists
        abort(404)
    return render_template("layered.html", now=datetime.utcnow(), mb=mb,
                           active_page="library")


@app.route("/about")
def about():
    return render_template("about.html", now=datetime.utcnow(), active_page="about")


@app.route("/api/manifest")
def api_manifest():
    return jsonify(MANIFEST)


@app.route("/api/network-probe")
def api_network_probe():
    secret = request.headers.get("X-Ingest-Secret") or request.args.get("secret")
    if secret != os.environ.get("INGEST_QUEUE_SECRET"):
        abort(403)
    import urllib.request
    url = request.args.get("url")
    if not url:
        abort(400)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "oedio.com megabook builder (noel@harmonyball.com)"})
        resp = urllib.request.urlopen(req, timeout=15)
        body = resp.read(300)
        challenged = b"Just a moment" in body or b"cf-browser-verification" in body
        return jsonify({"status": resp.status, "challenged": challenged,
                        "body_sample": body[:150].decode("utf-8", "replace")})
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"})


@app.route("/api/ingest-queue", methods=["POST"])
def api_ingest_queue():
    # Simple shared-secret guard -- this triggers real writes + git pushes,
    # not something to leave open on a public endpoint.
    secret = request.headers.get("X-Ingest-Secret") or request.args.get("secret")
    if secret != os.environ.get("INGEST_QUEUE_SECRET"):
        abort(403)
    from ingest_queue import queue_jobs
    jobs = request.get_json(force=True).get("jobs", [])
    return jsonify(queue_jobs(jobs))


@app.route("/api/ingest-queue/status")
def api_ingest_queue_status():
    from ingest_queue import get_status
    return jsonify(get_status())


@app.route("/healthz")
def healthz():
    return {"ok": True, "megabooks": len(MEGABOOKS)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
