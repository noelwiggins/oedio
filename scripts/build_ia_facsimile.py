#!/usr/bin/env python3
"""Build oedio reader-data pages for a verified Internet Archive facsimile
item, using the canonical direct IIIF image URL (no redirect hop) confirmed
against archive.org's own metadata API -- see the verification steps in
this session's conversation, not guessed identifiers.

Usage: python3 build_ia_facsimile.py <identifier> <page_count> <output.json> [archive_ext]
  archive_ext: 'zip' (default) or 'tar' -- IA stores the per-page JP2 scans
  in either a _jp2.zip or _jp2.tar depending on when/how the item was
  processed; check the item's file listing (or just try both) before
  assuming one.
"""
import json
import sys


def main():
    if len(sys.argv) not in (4, 5):
        print("Usage: build_ia_facsimile.py <identifier> <page_count> <output.json> [archive_ext]")
        sys.exit(1)
    identifier, page_count, out_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    archive_ext = sys.argv[4] if len(sys.argv) == 5 else "zip"

    pages = []
    for leaf in range(page_count):
        url = (
            f"https://iiif.archive.org/image/iiif/2/{identifier}%2f{identifier}_jp2.{archive_ext}"
            f"%2f{identifier}_jp2%2f{identifier}_{leaf:04d}.jp2/full/pct:50/0/default.jpg"
        )
        pages.append({"page": leaf + 1, "text": "", "image": url})

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(pages, fh, ensure_ascii=False, indent=1)
    print(f"{identifier}: {len(pages)} pages -> {out_path}")


if __name__ == "__main__":
    main()
