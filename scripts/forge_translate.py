#!/usr/bin/env python3
"""oedio manuscript forge: HTR + AI translation for handwritten manuscripts.

Takes an existing facsimile component ({slug}.json with page images) and
produces two derived layers in the standard [{page, text, image}] contract:
  {slug}-transcription.json  -- the original-language text, transcribed
  {slug}-english.json        -- an AI English translation

Usage: python3 forge_translate.py <slug> <start_page> <end_page> [lang_name]
Resumable: merges into existing output files, skipping already-done pages.
"""
import base64, json, os, sys, time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API_KEY = os.environ.get("ANTHROPIC_API_KEY") or open(
    os.path.expanduser("~/.anthropic_key")).read().strip()
MODEL = "claude-sonnet-4-6"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROMPT = """This is a page from a 16th-century {lang} manuscript of Qazwini's 'Aja'ib al-makhluqat (The Wonders of Creation), written in Arabic script (nesih book hand). 

1. Transcribe ALL visible manuscript text on the page exactly as written, in Arabic script, preserving line order. Include marginalia only if clearly part of the text tradition (ignore modern pencil shelf-marks, stamps, or catalog numbers).
2. Then translate the transcribed text into clear, readable English. Preserve the flavor of the original without archaism.

If the page contains no manuscript text (binding, blank leaf, cover, ruler/color chart), respond with exactly: NO_TEXT

Otherwise respond ONLY with JSON in this exact shape, no markdown fences:
{{"transcription": "...", "english": "..."}}"""


def fetch_image_b64(url):
    req = urllib.request.Request(url, headers={"User-Agent": "oedio forge"})
    data = urllib.request.urlopen(req, timeout=60).read()
    return base64.b64encode(data).decode()


def call_claude(img_b64, lang):
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/jpeg", "data": img_b64}},
            {"type": "text", "text": PROMPT.format(lang=lang)}
        ]}]
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages",
        data=body, headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"})
    for attempt in range(4):
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
            return "".join(b.get("text", "") for b in resp.get("content", []))
        except Exception as e:
            if attempt == 3:
                return None
            time.sleep(20 * (attempt + 1))


def load_layer(path, source_pages):
    if os.path.exists(path):
        return {p["page"]: p for p in json.load(open(path))}
    return {p["page"]: {"page": p["page"], "text": "", "image": p["image"]}
            for p in source_pages}


def main(slug, start, end, lang="Ottoman Turkish"):
    src_path = f"{BASE}/static/reader-data/{slug}.json"
    source = json.load(open(src_path))
    by_page = {p["page"]: p for p in source}
    t_path = f"{BASE}/static/reader-data/{slug}-transcription.json"
    e_path = f"{BASE}/static/reader-data/{slug}-english.json"
    t_layer = load_layer(t_path, source)
    e_layer = load_layer(e_path, source)

    todo = [pg for pg in range(start, end + 1)
            if pg in by_page and not t_layer[pg]["text"]]
    print(f"{slug}: processing {len(todo)} pages ({start}-{end})")

    def work(pg):
        try:
            img = fetch_image_b64(by_page[pg]["image"])
            out = call_claude(img, lang)
            if out is None:
                return pg, None, None
            out = out.strip()
            if out.startswith("NO_TEXT") or out == "":
                return pg, "\u2014", "\u2014"  # em-dash marks a checked non-text page
            out = out.strip("`").replace("json\n", "", 1) if out.startswith("`") else out
            d = json.loads(out)
            return pg, d.get("transcription", ""), d.get("english", "")
        except Exception as ex:
            return pg, None, None

    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for pg, tr, en in ex.map(work, todo):
            if tr is not None:
                t_layer[pg]["text"] = tr
                e_layer[pg]["text"] = en
                done += 1
            if done % 10 == 0:  # checkpoint
                json.dump(sorted(t_layer.values(), key=lambda p: p["page"]),
                          open(t_path, "w"), ensure_ascii=False)
                json.dump(sorted(e_layer.values(), key=lambda p: p["page"]),
                          open(e_path, "w"), ensure_ascii=False)

    json.dump(sorted(t_layer.values(), key=lambda p: p["page"]),
              open(t_path, "w"), ensure_ascii=False)
    json.dump(sorted(e_layer.values(), key=lambda p: p["page"]),
              open(e_path, "w"), ensure_ascii=False)
    n_t = sum(1 for p in t_layer.values() if p["text"] and p["text"] != "\u2014")
    print(f"done: {done} new; layer now has {n_t} transcribed pages -> {t_path}")


if __name__ == "__main__":
    a = sys.argv
    main(a[1], int(a[2]), int(a[3]), a[4] if len(a) > 4 else "Ottoman Turkish")
