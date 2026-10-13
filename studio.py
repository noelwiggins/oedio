"""Book Studio web layer: sources, live preview, build jobs, hosted streaming viewer.

The heavy lifting lives in bookbuilder.py and runs as a subprocess per job so
the single gunicorn worker never blocks while a book is typeset.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime

from flask import Blueprint, Response, abort, jsonify, render_template, request, send_file

import bookbuilder as bb

bp = Blueprint("studio", __name__)

JOB_ID_RE = re.compile(r"^[0-9a-f]{16}$")
MAX_CONCURRENT = 2
MAX_JOBS_PER_HOUR = 8
KEEP_DAYS = 60
_ip_hits: dict = {}


def _client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    return (xff.split(",")[0].strip() if xff else request.remote_addr) or "?"


def _json_spec():
    if request.content_length and request.content_length > 400_000:
        abort(413)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    return data


def _err(msg, code=400):
    return jsonify({"error": msg}), code


# -- pages ---------------------------------------------------------------------
@bp.route("/book/<mega_slug>/studio")
def studio_page(mega_slug):
    mb = bb.find_megabook(mega_slug)
    if not mb:
        abort(404)
    return render_template("studio.html", now=datetime.utcnow(), mb=mb, active_page="library",
                           base=request.args.get("base", ""))


@bp.route("/api/studio/<mega_slug>/sources")
def api_sources(mega_slug):
    try:
        return jsonify(bb.list_sources(mega_slug))
    except bb.SpecError as e:
        return _err(str(e), 404)


@bp.route("/api/studio/estimate", methods=["POST"])
def api_estimate():
    try:
        return jsonify(bb.estimate(_json_spec()))
    except bb.SpecError as e:
        return _err(str(e))


@bp.route("/api/studio/headings", methods=["POST"])
def api_headings():
    data = _json_spec()
    try:
        return jsonify({"entries": bb.detect_headings(data.get("spec") or {}, data.get("source"))})
    except bb.SpecError as e:
        return _err(str(e))


@bp.route("/api/studio/monogram.svg")
def api_monogram():
    initials = "".join(ch for ch in request.args.get("initials", "AB") if ch.isalpha())[:3].upper() or "AB"
    style = request.args.get("style", "circle")
    foil = request.args.get("foil", "gold")
    theme = request.args.get("theme", "oxblood")
    if style not in ("circle", "laurel", "square", "oval"):
        style = "circle"
    if foil not in bb.FOILS:
        foil = "gold"
    if theme not in bb.THEMES:
        theme = "oxblood"
    svg = bb.monogram_svg(initials, style, foil, theme)
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"})


@bp.route("/studio/preview", methods=["POST"])
def studio_preview():
    """Exact HTML of one page, built by the same code that typesets the PDF."""
    try:
        spec = json.loads(request.form.get("spec", "{}"))
        html_doc = bb.preview_html(spec, request.form.get("kind", "front"),
                                   request.form.get("p"), request.form.get("side", "L"))
    except (bb.SpecError, ValueError, KeyError) as e:
        html_doc = ("<!doctype html><meta charset=utf-8><body style=\"margin:0;font:14px system-ui;color:#777;"
                    f"display:flex;align-items:center;justify-content:center;height:100vh;text-align:center\">"
                    f"<div style='padding:24px'>{bb.esc(e)}</div>")
    return Response(html_doc, mimetype="text/html", headers={"Cache-Control": "no-store"})


# -- jobs ------------------------------------------------------------------------
def _jobdir(job_id):
    if not JOB_ID_RE.match(job_id or ""):
        abort(404)
    d = os.path.join(bb.export_root(), job_id)
    if not os.path.isdir(d):
        abort(404)
    return d


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _running_jobs():
    n = 0
    root = bb.export_root()
    for name in os.listdir(root):
        if JOB_ID_RE.match(name):
            pr = _read_json(os.path.join(root, name, "progress.json"), {})
            if pr.get("status") in ("queued", "running") and time.time() - pr.get("updated", 0) < 240:
                n += 1
    return n


def _cleanup():
    root = bb.export_root()
    now = time.time()
    for name in os.listdir(root):
        if not JOB_ID_RE.match(name):
            continue
        d = os.path.join(root, name)
        try:
            age_days = (now - os.path.getmtime(d)) / 86400
            pr = _read_json(os.path.join(d, "progress.json"), {})
            if age_days > KEEP_DAYS or (pr.get("status") == "error" and age_days > 2):
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


@bp.route("/api/studio/jobs", methods=["POST"])
def api_create_job():
    spec = _json_spec()
    try:
        bb.normalize_spec(spec)
    except bb.SpecError as e:
        return _err(str(e))
    ip = _client_ip()
    hits = [t for t in _ip_hits.get(ip, []) if time.time() - t < 3600]
    if len(hits) >= MAX_JOBS_PER_HOUR:
        return _err("You've built several books this hour. Please try again a little later.", 429)
    if _running_jobs() >= MAX_CONCURRENT:
        return _err("The studio is busy typesetting other books. Please try again in a minute.", 503)
    _cleanup()
    job_id = secrets.token_hex(8)
    d = os.path.join(bb.export_root(), job_id)
    os.makedirs(d)
    with open(os.path.join(d, "spec.json"), "w", encoding="utf-8") as fh:
        json.dump(spec, fh)
    bb.Progress(d).update(status="queued", stage="Queued", pct=1)
    log = open(os.path.join(d, "log.txt"), "wb")
    subprocess.Popen([sys.executable, bb.__file__, "build", d], stdout=log, stderr=log,
                     start_new_session=True, cwd=bb.BASE_DIR)
    hits.append(time.time())
    _ip_hits[ip] = hits
    return jsonify({"id": job_id})


@bp.route("/api/studio/jobs/<job_id>")
def api_job(job_id):
    d = _jobdir(job_id)
    pr = _read_json(os.path.join(d, "progress.json"), {"status": "queued", "stage": "Queued", "pct": 0})
    if pr.get("status") in ("queued", "running") and time.time() - pr.get("updated", time.time()) > 300:
        pr.update(status="error", stage="Failed", message="The build stalled. Please try again.")
    if pr.get("status") == "done":
        pr["meta"] = _read_json(os.path.join(d, "meta.json"), {})
        pr["url"] = f"/studio/book/{job_id}"
        pr["pdf"] = f"/studio/book/{job_id}.pdf"
    return jsonify(pr)


# -- hosted book: stream + download ------------------------------------------------
def _slug(title):
    return re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()[:60] or "book"


def _pdf_path(job_id):
    d = _jobdir(job_id)
    p = os.path.join(d, "book.pdf")
    if not os.path.exists(p):
        abort(404)
    return d, p


@bp.route("/studio/book/<job_id>.pdf")
def book_pdf(job_id):
    _, p = _pdf_path(job_id)
    # conditional=True gives HTTP Range support, so the viewer streams pages on demand
    resp = send_file(p, mimetype="application/pdf", conditional=True, max_age=3600)
    resp.headers["Accept-Ranges"] = "bytes"
    return resp


@bp.route("/studio/book/<job_id>/download")
def book_download(job_id):
    d, p = _pdf_path(job_id)
    meta = _read_json(os.path.join(d, "meta.json"), {})
    return send_file(p, mimetype="application/pdf", as_attachment=True,
                     download_name=f"{_slug(meta.get('title', 'book'))}.pdf", conditional=True)


@bp.route("/studio/book/<job_id>")
def book_view(job_id):
    d, _ = _pdf_path(job_id)
    meta = _read_json(os.path.join(d, "meta.json"), {})
    return render_template("book_view.html", now=datetime.utcnow(), job_id=job_id, meta=meta)
