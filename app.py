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

from flask import Flask, abort, jsonify, render_template

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(BASE_DIR, "data", "manifest.json")

with open(MANIFEST_PATH) as f:
    MANIFEST = json.load(f)
MEGABOOKS = MANIFEST["megabooks"]


def _page_count(slug):
    path = os.path.join(BASE_DIR, "static", "reader-data", f"{slug}.json")
    try:
        with open(path) as fh:
            return len(json.load(fh))
    except Exception:
        return 0


# Annotate page counts once at startup so templates can show them.
for _mb in MEGABOOKS:
    for _c in _mb["components"]:
        _c["pages"] = _page_count(_c["slug"])


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
PANEL_GROUPS = {}
for _mb in MEGABOOKS:
    _slugs = {c["slug"] for c in _mb["components"]}
    for _c in _mb["components"]:
        _base = _c["slug"]
        _tr, _en = f"{_base}-transcription", f"{_base}-english"
        if _tr in _slugs or _en in _slugs:
            _group = [{"slug": _base, "kind": "image", "label": "Original scan"}]
            if _tr in _slugs:
                _tr_c = next(x for x in _mb["components"] if x["slug"] == _tr)
                _group.append({"slug": _tr, "kind": "text", "label": _tr_c["title"]})
            if _en in _slugs:
                _en_c = next(x for x in _mb["components"] if x["slug"] == _en)
                _group.append({"slug": _en, "kind": "text", "label": _en_c["title"]})
            for _member in [_base, _tr, _en]:
                if _member in _slugs:
                    PANEL_GROUPS[_member] = _group


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


def _find_megabook(mega_slug):
    return next((m for m in MEGABOOKS if m["slug"] == mega_slug), None)


@app.route("/")
def library():
    return render_template("index.html", now=datetime.utcnow(),
                           megabooks=MEGABOOKS, active_page="library")


@app.route("/book/<mega_slug>")
def megabook_page(mega_slug):
    mb = _find_megabook(mega_slug)
    if not mb:
        abort(404)
    # Group components by role, preserving manifest order of first appearance.
    grouped, order = {}, []
    for c in mb["components"]:
        if c["role"] not in grouped:
            grouped[c["role"]] = []
            order.append(c["role"])
        grouped[c["role"]].append(c)
    return render_template("megabook.html", now=datetime.utcnow(), mb=mb,
                           grouped=[(r, grouped[r]) for r in order],
                           active_page="library")


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
        book_source_url=f"https://www.loc.gov/item/{comp['loc_item']}/",
        facsimile=comp["facsimile"],
        is_translated=comp.get("translated", False),
        original_label=comp.get("original_label"),
        start_page=None,
        siblings=siblings,
        panel_group=panel_group,
        left_default=left_default,
        data_url=f"/static/reader-data/{comp.get('data_slug', comp_slug)}.json",
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


@app.route("/healthz")
def healthz():
    return {"ok": True, "megabooks": len(MEGABOOKS)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
