#!/usr/bin/env python3
"""Ingest an Internet Archive item's page scans into the oedio reader-data
contract via its IIIF v3 manifest: static/reader-data/{slug}.json.

Usage: python3 ingest_ia.py <ia_identifier> <slug> [start] [end]
Resumable, same merge semantics as ingest_loc.py.
"""
import json, os, re, sys
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "oedio.com megabook builder (noel@harmonyball.com)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read()


def main(identifier, slug, start=1, end=None):
    manifest = json.loads(fetch(f"https://iiif.archive.org/iiif/{identifier}/manifest.json"))
    items = manifest.get("items", [])
    if end:
        items = items[start - 1:end]
    else:
        items = items[start - 1:]

    pages = []
    for i, canvas in enumerate(items, start=start):
        try:
            body = canvas["items"][0]["items"][0]["body"]
            img_id = body["id"]
            # downscale for reader-friendly size: swap /full/max/ for /full/pct:50/
            img_url = re.sub(r"/full/(max|full)/", "/full/pct:50/", img_id)
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
