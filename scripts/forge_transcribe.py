#!/usr/bin/env python3
"""oedio Forge: manuscript transcription + translation engine.

Sends each manuscript page image to Claude (vision) and gets back:
  - a diplomatic transcription in the original script/language
  - an English translation
Output: static/reader-data/{out_slug}.json in the dual-language reader
contract: [{page, text: <original transcription>, translation: <English>, image}]

Usage: python3 forge_transcribe.py <source_slug> <out_slug> <start_page> <end_page> \
         "<language description>" "<work description>"
Merge-appends like ingest_loc.py, so ranges can run in chunks / resume.
Requires ANTHROPIC_API_KEY in the environment.
"""
import base64
import json
import os
import sys
import time
import urllib.request

API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-sonnet-4-6"

SYSTEM = """You are a scholarly transcriber and translator of {language} manuscripts, \
working on {work}. For the manuscript page image provided:
1. Transcribe the main text faithfully in its original script (diplomatic transcription; \
preserve line breaks with \\n; use [...] for illegible passages; ignore later marginalia, \
library stamps, and shelf-marks).
2. Translate the transcribed text into clear, readable English.
3. If the page is blank, a binding/cover, or contains only an illustration, say so briefly.
Respond ONLY with JSON: {{"transcription": "...", "translation": "...", \
"page_note": "one short line: e.g. 'text page', 'illustration: <subject>', 'blank/flyleaf'"}}"""


def fetch_image_b64(url):
    req = urllib.request.Request(url, headers={"User-Agent": "oedio forge (noel@harmonyball.com)"})
    return base64.b64encode(urllib.request.urlopen(req, timeout=60).read()).decode()


def call_claude(img_b64, language, work):
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 4000,
        "system": SYSTEM.format(language=language, work=work),
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
            {"type": "text", "text": "Transcribe and translate this page."}
        ]}]
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
    raw = resp["content"][0]["text"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def main(src_slug, out_slug, start, end, language, work):
    src = json.load(open(f"static/reader-data/{src_slug}.json"))
    by_page = {p["page"]: p for p in src}
    out_path = f"static/reader-data/{out_slug}.json"
    out = json.load(open(out_path)) if os.path.exists(out_path) else []
    done = {p["page"] for p in out}

    for pg in range(start, end + 1):
        if pg in done or pg not in by_page:
            continue
        img_url = by_page[pg]["image"]
        for attempt in range(3):
            try:
                b64 = fetch_image_b64(img_url)
                r = call_claude(b64, language, work)
                note = r.get("page_note", "")
                out.append({
                    "page": pg,
                    "text": r.get("transcription", "") or f"[{note}]",
                    "translation": r.get("translation", "") or f"[{note}]",
                    "page_note": note,
                    "image": img_url,
                })
                print(f"p{pg}: {note[:60]}")
                break
            except Exception as e:
                print(f"p{pg} attempt {attempt+1} failed: {e}")
                time.sleep(20)
        out.sort(key=lambda p: p["page"])
        json.dump(out, open(out_path, "w"), ensure_ascii=False)
        time.sleep(1)
    print(f"{out_slug}: {len(out)} pages transcribed -> {out_path}")


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], int(a[3]), int(a[4]), a[5], a[6])
