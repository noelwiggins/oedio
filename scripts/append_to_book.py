#!/usr/bin/env python3
"""Safely append new pages to an EXISTING Oedio component -- for handling
incremental submissions, like a contributor sending more of a manuscript
later. Handles the three things that have to stay in sync: the image files
on disk, the base reader-data JSON, and (if present) the transcription/
translation layer JSONs -- so a future submission can't accidentally
overwrite or renumber pages that are already live.

Usage:
    python3 scripts/append_to_book.py <mega_slug> <comp_slug> <new_images_dir>

Where <new_images_dir> contains the new page images, named so that sorting
them alphabetically gives the correct reading order (e.g. 001.jpg, 002.jpg...).
The images are copied into the component's existing static folder, renumbered
to continue after the current highest page, and appended to reader-data.json
(and to the -transcription/-english layers too, as empty entries ready for
forge_translate.py to fill in with a normal start/end page range call).

This does NOT run transcription itself -- run forge_translate.py separately
afterward, targeting the new page range this script reports.
"""
import json
import os
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(mega_slug, comp_slug, new_images_dir):
    manifest_path = f"{BASE}/data/manifest.json"
    manifest = json.load(open(manifest_path))
    mb = next((b for b in manifest["megabooks"] if b["slug"] == mega_slug), None)
    if not mb:
        print(f"ERROR: no Oedio found with slug '{mega_slug}'")
        return
    comp = next((c for c in mb["components"] if c["slug"] == comp_slug), None)
    if not comp:
        print(f"ERROR: no component '{comp_slug}' found in Oedio '{mega_slug}'")
        return

    data_slug = comp.get("data_slug", comp_slug)
    base_path = f"{BASE}/static/reader-data/{data_slug}.json"
    if not os.path.exists(base_path):
        print(f"ERROR: no existing reader-data file at {base_path}")
        return
    pages = json.load(open(base_path))
    if not pages:
        print("ERROR: existing reader-data is empty -- use the normal ingest scripts instead")
        return

    current_max = max(p["page"] for p in pages)
    # Infer the static image folder from the first existing page's image URL
    # (expects the local /static/manuscripts/<slug>/NNN.jpg convention).
    first_image_url = pages[0]["image"]
    if not first_image_url.startswith("/static/manuscripts/"):
        print("ERROR: this tool only supports the local /static/manuscripts/<slug>/ convention, "
              "not externally-hosted sources -- add those pages with the normal ingest scripts instead.")
        return
    static_dir_rel = os.path.dirname(first_image_url)  # e.g. /static/manuscripts/zia-quran
    static_dir_abs = f"{BASE}{static_dir_rel}"

    new_files = sorted(f for f in os.listdir(new_images_dir) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if not new_files:
        print(f"ERROR: no image files found in {new_images_dir}")
        return

    new_pages = []
    for i, fname in enumerate(new_files):
        new_page_num = current_max + 1 + i
        dest_name = f"{new_page_num:03d}.jpg"
        shutil.copy(os.path.join(new_images_dir, fname), os.path.join(static_dir_abs, dest_name))
        new_pages.append({"page": new_page_num, "image": f"{static_dir_rel}/{dest_name}", "text": ""})

    pages.extend(new_pages)
    json.dump(pages, open(base_path, "w"), ensure_ascii=False)

    # Extend the transcription/translation layers too, if they exist, with
    # empty placeholder entries at the new page numbers -- forge_translate.py
    # fills these in normally when run against the new page range.
    for suffix in ("-transcription", "-english"):
        layer_path = f"{BASE}/static/reader-data/{data_slug}{suffix}.json"
        if os.path.exists(layer_path):
            layer = json.load(open(layer_path))
            layer.extend({"page": p["page"], "text": ""} for p in new_pages)
            json.dump(layer, open(layer_path, "w"), ensure_ascii=False)

    print(f"Appended {len(new_pages)} new pages ({new_pages[0]['page']}-{new_pages[-1]['page']}) "
          f"to '{comp_slug}' in '{mega_slug}'.")
    print(f"Next step -- run forge_translate.py to transcribe/translate them:")
    print(f"  python3 scripts/forge_translate.py {data_slug} {new_pages[0]['page']} {new_pages[-1]['page']} "
          f"\"<language>\" \"<description>\"")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 scripts/append_to_book.py <mega_slug> <comp_slug> <new_images_dir>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
