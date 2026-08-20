#!/usr/bin/env python3
"""Build a full-text search index over every page of every component in the
Oedio corpus (~100k pages, ~19M words across 133MB of reader-data JSON).

Uses a *contentless* FTS5 table -- it indexes the text but doesn't store a
copy of it, keeping the committed index file small. At query time, once we
know which page matched, we re-read just that one page's text from the
original reader-data JSON (already on disk) to build a snippet. This avoids
duplicating 94MB of text into the index while still giving real ranked
full-text search with snippets, not just metadata matching.

Run: python3 scripts/build_search_index.py
Output: data/search_index.sqlite
"""
import json
import os
import re
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READER_DATA_DIR = os.path.join(REPO_ROOT, "static", "reader-data")
MANIFEST_PATH = os.path.join(REPO_ROOT, "data", "manifest.json")
DB_PATH = os.path.join(REPO_ROOT, "data", "search_index.sqlite")

FN_TOKEN_RE = re.compile(r"\u27e6fn:[^\u27e7]+\u27e7")


def strip_fn_tokens(text):
    return FN_TOKEN_RE.sub("", text or "")


def main():
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE VIRTUAL TABLE pages_fts USING fts5(text, content='')")
    con.execute("""
        CREATE TABLE pages_meta (
            rowid INTEGER PRIMARY KEY,
            megabook_slug TEXT NOT NULL,
            megabook_title TEXT NOT NULL,
            component_slug TEXT NOT NULL,
            component_title TEXT NOT NULL,
            page INTEGER NOT NULL,
            char_count INTEGER NOT NULL
        )
    """)
    con.execute("CREATE INDEX idx_meta_megabook ON pages_meta(megabook_slug)")

    rowid = 0
    indexed_pages = 0
    skipped_components = []

    for mb in manifest["megabooks"]:
        for comp in mb.get("components", []):
            data_slug = comp.get("data_slug", comp["slug"])
            path = os.path.join(READER_DATA_DIR, f"{data_slug}.json")
            if not os.path.exists(path):
                skipped_components.append(f"{mb['slug']}/{comp['slug']} (no reader-data file)")
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    pages = json.load(fh)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                skipped_components.append(f"{mb['slug']}/{comp['slug']} (parse error: {e})")
                continue
            if not isinstance(pages, list):
                skipped_components.append(f"{mb['slug']}/{comp['slug']} (not a page list)")
                continue

            for p in pages:
                if not isinstance(p, dict):
                    continue
                text = strip_fn_tokens(p.get("text", "") or "")
                if len(text.strip()) < 20:
                    continue  # skip blank/near-blank pages, not worth indexing
                rowid += 1
                con.execute("INSERT INTO pages_fts(rowid, text) VALUES (?, ?)", (rowid, text))
                con.execute(
                    "INSERT INTO pages_meta(rowid, megabook_slug, megabook_title, component_slug, "
                    "component_title, page, char_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (rowid, mb["slug"], mb["title"], comp["slug"], comp.get("title", comp.get("role", "")),
                     p.get("page", 0), len(text)),
                )
                indexed_pages += 1

    con.commit()
    con.execute("INSERT INTO pages_fts(pages_fts) VALUES ('optimize')")
    con.commit()
    con.close()

    size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    print(f"Indexed {indexed_pages} pages, {rowid} rows -> {DB_PATH} ({size_mb:.1f} MB)")
    if skipped_components:
        print(f"Skipped {len(skipped_components)} components:")
        for s in skipped_components:
            print(f"  - {s}")


if __name__ == "__main__":
    main()
