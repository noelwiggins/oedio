#!/usr/bin/env python3
"""Ingest a National Diet Library of Japan (dl.ndl.go.jp) item's page scans
into the oedio reader-data contract via its open IIIF v2 manifest.

NDL publishes a genuine, unauthenticated IIIF API for public-domain
holdings -- unlike HathiTrust, which blocks programmatic access entirely
without a registered OAuth key. Confirmed working, no credentials needed.

Usage: python3 ingest_ndl.py <ndl_pid> <slug> [start] [end]
Resumable, same merge semantics as ingest_loc.py / ingest_ia.py.
"""
import json, os, re, sys
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "oedio.com megabook builder (noel@harmonyball.com)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read()


def main(pid, slug, start=1, end=None):
    manifest = json.loads(fetch(f"https://dl.ndl.go.jp/api/iiif/{pid}/manifest.json"))
    canvases = manifest.get("sequences", [{}])[0].get("canvases", [])
    if end:
        canvases = canvases[start - 1:end]
    else:
        canvases = canvases[start - 1:]

    pages = []
    for i, canvas in enumerate(canvases, start=start):
        try:
            img_id = canvas["images"][0]["resource"]["@id"]
            img_url = re.sub(r"/full/full/", "/full/pct:50/", img_id)
            pages.append({"page": i, "text": "", "image": img_url})
        except (KeyError, IndexError):
            continue

    path = f"{BASE}/static/reader-data/{slug}.json"
    if os.path.exists(path):
        prev = json.load(open(path))
        by_page = {p["page"]: p for p in prev}
        for p in pages:
            by_page[p["page"]] = p
        pages = sorted(by_page.values(), key=lambda p: p["page"])

    with open(path, "w") as f:
        json.dump(pages, f, ensure_ascii=False)
    print(f"{slug}: {len(pages)} total pages -> {path}")


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], int(a[3]) if len(a) > 3 else 1, int(a[4]) if len(a) > 4 else None)
