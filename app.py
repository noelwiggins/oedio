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
from datetime import datetime

from flask import Flask, abort, jsonify, render_template, request

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
            if _slug == _base:
                _group.append({"slug": _slug, "kind": "image", "label": "Original scan"})
            else:
                _group.append({"slug": _slug, "kind": _mc.get("layer_kind", "text"), "label": _mc["title"]})
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
