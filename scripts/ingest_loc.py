#!/usr/bin/env python3
"""Ingest a LOC digitized book into the oedio reader-data contract:
   static/reader-data/{slug}.json  =  [{"page": N, "text": "...", "image": "..."}]
Usage: python3 ingest_loc.py <loc_item_id> <slug>
"""
import json, sys, re, os
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "oedio.com book ingester (noel@harmonyball.com)"}

def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()

def alto_text(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""
    ns = root.tag.split("}")[0].strip("{")
    out = []
    for tl in root.iter("{%s}TextLine" % ns):
        words = [s.get("CONTENT", "") for s in tl if s.tag.endswith("String")]
        out.append(" ".join(w for w in words if w))
    return "\n".join(out).strip()

def main(item_id, slug):
    d = json.loads(get(f"https://www.loc.gov/item/{item_id}/?fo=json"))
    files = d["resources"][0]["files"]
    pages = []
    for i, page_files in enumerate(files, start=1):
        img = next((f["url"] for f in page_files
                    if f.get("mimetype") == "image/jpeg" and "/pct:50" in f.get("url", "")), None)
        if not img:
            img = next((f["url"] for f in page_files if f.get("mimetype") == "image/jpeg"), "")
        alto = next((f["url"] for f in page_files
                     if f.get("mimetype") == "text/xml" and f.get("url", "").endswith(".alto.xml")), None)
        pages.append({"page": i, "image": img, "_alto": alto})

    def fetch_text(p):
        if not p["_alto"]:
            p["text"] = ""
            return
        for attempt in range(3):
            try:
                p["text"] = alto_text(get(p["_alto"]))
                return
            except Exception:
                pass
        p["text"] = ""

    with ThreadPoolExecutor(max_workers=40) as ex:
        list(ex.map(fetch_text, pages))

    for p in pages:
        p.pop("_alto", None)
    out = [{"page": p["page"], "text": p["text"], "image": p["image"]} for p in pages]
    os.makedirs("static/reader-data", exist_ok=True)
    path = f"static/reader-data/{slug}.json"
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    n_text = sum(1 for p in out if len(p["text"]) > 40)
    print(f"{slug}: {len(out)} pages, {n_text} with substantive text -> {path}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
