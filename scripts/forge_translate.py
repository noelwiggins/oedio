#!/usr/bin/env python3
"""oedio manuscript/facsimile forge: HTR + AI translation for any page-image
component, hand-written or printed, in any script or language.

Takes an existing facsimile component ({slug}.json with page images) and
produces one or two derived layers in the standard [{page, text, image}]
contract:
  {slug}-transcription.json  -- transcribed text in its original script
  {slug}-english.json        -- an AI English translation (skipped if the
                                 source is already English -- use --no-translation)

Usage:
  python3 forge_translate.py <slug> <start_page> <end_page> <lang> [description] [--no-translation]

<lang> is used in the prompt (e.g. "Ottoman Turkish", "Persian", "Ancient Greek", "English").
[description] optionally overrides the default work description sentence.
Resumable: merges into existing output files, skipping already-done pages.
"""
import base64, json, os, re, sys, time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

API_KEY = os.environ.get("ANTHROPIC_API_KEY") or open(
    os.path.expanduser("~/.anthropic_key")).read().strip()
MODEL = "claude-sonnet-4-6"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROMPT_TRANSLATE = """This is a page from {description}, in {lang}.

1. Transcribe ALL visible text on the page exactly as written, in its original script, preserving line order. Include marginalia only if clearly part of the text tradition (ignore modern pencil shelf-marks, stamps, catalog numbers, or library annotations). If the page is damaged or partly illegible, transcribe whatever is legible and mark unreadable portions as [illegible] -- do not add any commentary about the damage.
2. Then translate the transcribed text into clear, readable English. Preserve the flavor of the original without archaism.

If the page contains no body text (binding, blank leaf, cover, plate with no caption, ruler/color chart), respond with exactly: NO_TEXT

Respond ONLY with the JSON object below and nothing else -- no markdown fences, no preamble, no explanation of the page's condition, before or after:
{{"transcription": "...", "english": "..."}}"""

PROMPT_NO_TRANSLATE = """This is a page from {description}, printed in {lang}.

Transcribe ALL visible body text on the page exactly as written (this is a clean OCR pass -- correct only obvious scanning artifacts, not wording). Include captions under illustrations but not modern library stamps or shelf-marks. If the page is damaged or partly illegible, transcribe whatever is legible and mark unreadable portions as [illegible] -- do not add any commentary about the damage.

If the page contains no body text (binding, blank leaf, cover, or a plate with no caption), respond with exactly: NO_TEXT

Respond ONLY with the JSON object below and nothing else -- no markdown fences, no preamble, no explanation of the page's condition, before or after:
{{"transcription": "..."}}"""


def fetch_image_b64(url):
    req = urllib.request.Request(url, headers={"User-Agent": "oedio forge"})
    data = urllib.request.urlopen(req, timeout=60).read()
    return base64.b64encode(data).decode()


def call_claude(img_b64, lang, description, want_translation):
    prompt = (PROMPT_TRANSLATE if want_translation else PROMPT_NO_TRANSLATE).format(
        lang=lang, description=description)
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/jpeg", "data": img_b64}},
            {"type": "text", "text": prompt}
        ]}]
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages",
        data=body, headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"})
    for attempt in range(3):
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=90).read())
            return "".join(b.get("text", "") for b in resp.get("content", []))
        except Exception:
            if attempt == 2:
                return None
            time.sleep(10 * (attempt + 1))


def load_layer(path, source_pages):
    if os.path.exists(path):
        return {p["page"]: p for p in json.load(open(path))}
    return {p["page"]: {"page": p["page"], "text": "", "image": p["image"]}
            for p in source_pages}


def main(slug, start, end, lang, description=None, want_translation=True):
    src_path = f"{BASE}/static/reader-data/{slug}.json"
    source = json.load(open(src_path))
    by_page = {p["page"]: p for p in source}
    description = description or "a rare, digitized public-domain book"
    t_path = f"{BASE}/static/reader-data/{slug}-transcription.json"
    e_path = f"{BASE}/static/reader-data/{slug}-english.json" if want_translation else None
    t_layer = load_layer(t_path, source)
    e_layer = load_layer(e_path, source) if want_translation else None

    todo = [pg for pg in range(start, end + 1)
            if pg in by_page and not t_layer[pg]["text"]]
    print(f"{slug}: processing {len(todo)} pages ({start}-{end})")

    def work(pg):
        try:
            img = fetch_image_b64(by_page[pg]["image"])
            out = call_claude(img, lang, description, want_translation)
            if out is None:
                return pg, None, None
            out = out.strip()
            if out.startswith("NO_TEXT") or out == "":
                return pg, "\u2014", "\u2014"
            out = out.strip("`").replace("json\n", "", 1) if out.startswith("`") else out
            try:
                d = json.loads(out)
            except Exception:
                m = re.search(r"\{.*\}", out, re.DOTALL)
                if not m:
                    raise
                d = json.loads(m.group())
            tr = d.get("transcription", "")
            en = d.get("english", "") if want_translation else None
            if tr.strip() == "NO_TEXT":
                tr, en = "\u2014", ("\u2014" if want_translation else None)
            return pg, tr, en
        except Exception:
            return pg, None, None

    done = 0
    processed = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(work, pg): pg for pg in todo}
        for fut in as_completed(futures):
            pg, tr, en = fut.result()
            processed += 1
            if tr is not None:
                t_layer[pg]["text"] = tr
                if want_translation:
                    e_layer[pg]["text"] = en
                done += 1
            if processed % 5 == 0:
                json.dump(sorted(t_layer.values(), key=lambda p: p["page"]),
                          open(t_path, "w"), ensure_ascii=False)
                if want_translation:
                    json.dump(sorted(e_layer.values(), key=lambda p: p["page"]),
                              open(e_path, "w"), ensure_ascii=False)

    json.dump(sorted(t_layer.values(), key=lambda p: p["page"]),
              open(t_path, "w"), ensure_ascii=False)
    if want_translation:
        json.dump(sorted(e_layer.values(), key=lambda p: p["page"]),
                  open(e_path, "w"), ensure_ascii=False)
    n_t = sum(1 for p in t_layer.values() if p["text"] and p["text"] != "\u2014")
    print(f"done: {done} new; layer now has {n_t} transcribed pages -> {t_path}")


if __name__ == "__main__":
    a = sys.argv
    no_translate = "--no-translation" in a
    a = [x for x in a if x != "--no-translation"]
    desc = a[5] if len(a) > 5 else None
    main(a[1], int(a[2]), int(a[3]), a[4], desc, not no_translate)
