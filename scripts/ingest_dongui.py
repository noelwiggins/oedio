#!/usr/bin/env python3
"""Ingest Dongui Bogam (東醫寶鑑) volumes from Wikimedia Commons into the
oedio reader-data contract. Adapted from Plantacopia's ingest_dongui.py,
which already confirmed this source works: the National Library of Korea's
own PDF scans, hosted on Wikimedia Commons as
CNTS-00047967907_{N}_東醫寶鑑.pdf (N = 1..25).

Usage: python3 ingest_dongui.py <slug> <volume_n>
Produces static/reader-data/{slug}.json for that single volume.
"""
import json, os, re, sys, time
import urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "oedio.com megabook builder (noel@harmonyball.com)"}

VOLUME_TITLES = {
    1: "Naegyeongpyeon Vol.1 (Internal Medicine)", 16: "Tangaekpyeon Vol.1 (Herbal Medicine)",
}


def get_pdf_info(vol_n):
    fname = f"CNTS-00047967907 {vol_n} \u6771\u91ab\u5bf6\u9451.pdf"
    url = ("https://commons.wikimedia.org/w/api.php?action=query&titles=File:"
           + urllib.parse.quote(fname) + "&prop=imageinfo&iiprop=url|size&format=json")
    req = urllib.request.Request(url, headers=UA)
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    for pid, page in d.get("query", {}).get("pages", {}).items():
        if int(pid) > 0:
            ii = page.get("imageinfo", [{}])
            if ii and ii[0].get("url"):
                return ii[0]["url"], ii[0].get("pagecount")
    return None, None


def build_page_urls(pdf_url, page_count):
    m = re.match(r"https://upload\.wikimedia\.org/wikipedia/commons/([a-f0-9]/[a-f0-9]{2})/(.+\.pdf)", pdf_url)
    if not m:
        return []
    path, filename = m.group(1), m.group(2)
    base = f"https://upload.wikimedia.org/wikipedia/commons/thumb/{path}/{filename}"
    return [{"page": pg, "image": f"{base}/page{pg}-500px-{filename}.jpg", "text": ""}
            for pg in range(1, page_count + 1)]


def verify_pages(pages, max_workers=4):
    def check(p):
        req = urllib.request.Request(p["image"], headers=UA, method="HEAD")
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=25) as r:
                    return r.status == 200
            except Exception:
                if attempt == 3:
                    return False
                time.sleep(2.5)
        return False
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(check, pages))
    # Take the longest reasonable run: real documents don't have gaps, so a
    # single isolated failure (a network blip) shouldn't truncate the whole
    # volume -- only stop once we see several consecutive real gaps,
    # confirming we've actually run past the end of the document.
    valid, consecutive_gaps = [], 0
    for p, ok in zip(pages, results):
        if ok:
            valid.append(p)
            consecutive_gaps = 0
        else:
            consecutive_gaps += 1
            if consecutive_gaps >= 6:
                break
    return valid


def main(slug, volume_n):
    print(f"Volume {volume_n}: fetching PDF info...")
    pdf_url, page_count = get_pdf_info(volume_n)
    if not pdf_url or not page_count:
        print("  ERROR: no PDF or page count found on Wikimedia Commons")
        return
    print(f"  PDF: {pdf_url[:90]}")
    print(f"  Real page count (from MediaWiki metadata): {page_count}")
    pages = build_page_urls(pdf_url, page_count)
    path = f"{BASE}/static/reader-data/{slug}.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(pages, open(path, "w"), ensure_ascii=False)
    print(f"  Saved: {path} ({len(pages)} pages)")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
