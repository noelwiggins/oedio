#!/usr/bin/env python3
"""Fix a real ingestion bug found via audit_pagination_grounding.py: some
components' reader-data pages were built by iterating image filenames in
lexicographic (string) order rather than numeric order -- so "pg.10.jpg"
sorted before "pg.2.jpg", scrambling the true reading sequence throughout
the whole book even though each individual page object's text and image
stayed correctly paired with each other.

This re-sorts by the real page number embedded in each image filename and
reassigns sequential page=1..N in true reading order. Text stays attached
to its own image (both are fields on the same object being reordered
together) -- only the array position and page number change.

Run: python3 scripts/fix_scrambled_page_order.py <slug> [<slug> ...]
"""
import json
import re
import sys
import urllib.parse

PAT = re.compile(r"pg\.\s*(\d+)\.jpg", re.IGNORECASE)


def fix_component(slug):
    path = f"static/reader-data/{slug}.json"
    with open(path, encoding="utf-8") as fh:
        pages = json.load(fh)

    parsed = []
    for p in pages:
        decoded = urllib.parse.unquote(p.get("image", "") or "")
        m = PAT.search(decoded)
        if not m:
            print(f"  SKIPPING {slug}: page {p.get('page')} has no parseable "
                  f"number in image filename ({decoded[:80]}) -- aborting, "
                  f"not safe to reorder with an unplaceable page")
            return False
        parsed.append((int(m.group(1)), p))

    parsed.sort(key=lambda x: x[0])
    new_pages = []
    for i, (real_num, p) in enumerate(parsed, start=1):
        new_p = dict(p)
        new_p["page"] = i
        new_pages.append(new_p)

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(new_pages, fh, ensure_ascii=False, indent=1)
    print(f"  Fixed {slug}: {len(new_pages)} pages re-sorted into true reading order "
          f"(real page numbers ranged {parsed[0][0]}-{parsed[-1][0]})")
    return True


def main():
    slugs = sys.argv[1:]
    if not slugs:
        print("Usage: fix_scrambled_page_order.py <slug> [<slug> ...]")
        sys.exit(1)
    for slug in slugs:
        fix_component(slug)


if __name__ == "__main__":
    main()
