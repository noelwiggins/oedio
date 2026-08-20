#!/usr/bin/env python3
"""Audit every component in the manifest for whether its page numbers are
genuinely grounded to a real source (the scan's own sequence number, as in
Odyssey's LOC IIIF URLs .../odysseyofh00home_0001/...) versus synthetic
(assigned by an ingestion script with no tie to any physical page, as in
Gibbon's Gutenberg chapter/part splits).

Three categories:
  GROUNDED    -- has per-page images, and the page number visibly matches
                 the image URL's own sequence number (real source pagination)
  MISMATCHED  -- has per-page images, but the page number does NOT match
                 the image URL's sequence number (drift -- text page 40
                 might not be scan page 40)
  UNGROUNDED  -- no per-page images at all (a text-only reading edition;
                 fine IF the manifest marks it text_only, a real problem
                 if it doesn't, since the reader would silently break)

Run: python3 scripts/audit_pagination_grounding.py
"""
import json
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READER_DATA_DIR = os.path.join(REPO_ROOT, "static", "reader-data")
MANIFEST_PATH = os.path.join(REPO_ROOT, "data", "manifest.json")

DIGIT_RUN_RE = re.compile(r"\d+")


def digit_runs(url):
    """All digit runs in a URL, as (position_index, int_value) pairs --
    position_index lets us track 'the 3rd digit run' across different pages
    even though absolute string position shifts (different digit-count
    zero-padding, etc)."""
    return [int(m) for m in DIGIT_RUN_RE.findall(url or "")]


def find_page_tracking_run(with_images):
    """Real IIIF/scan URL conventions vary wildly by provider (archive.org
    embeds the item id AND year AND sequence; LOC/WDL embeds a barcode AND
    a sequence; British Library ARK embeds a fixed namespace AND a hex-ish
    sequence). Guessing 'the last digit run' breaks depending on provider.
    Instead: look at which digit-run *position* actually changes in lockstep
    with the page number across consecutive pages -- that position is the
    real per-page sequence, regardless of what else is sitting in the URL."""
    runs_per_page = [(p["page"], digit_runs(p["image"])) for p in with_images]
    runs_per_page = [(pg, r) for pg, r in runs_per_page if r]
    if len(runs_per_page) < 3:
        return None
    n_positions = min(len(r) for _, r in runs_per_page)
    best_pos, best_score = None, -1
    for pos in range(n_positions):
        matches = 0
        total = 0
        for i in range(1, len(runs_per_page)):
            pg_delta = runs_per_page[i][0] - runs_per_page[i - 1][0]
            val_delta = runs_per_page[i][1][pos] - runs_per_page[i - 1][1][pos]
            if pg_delta == 0:
                continue
            total += 1
            if val_delta == pg_delta:
                matches += 1
        if total and matches / total > best_score:
            best_score = matches / total
            best_pos = pos
    return (best_pos, best_score) if best_pos is not None else None


def audit_component(mb, comp):
    data_slug = comp.get("data_slug", comp["slug"])
    path = os.path.join(READER_DATA_DIR, f"{data_slug}.json")
    if not os.path.exists(path):
        return {"status": "MISSING_FILE", "detail": path}
    try:
        pages = json.load(open(path, encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"status": "PARSE_ERROR", "detail": str(e)}
    if not isinstance(pages, list) or not pages:
        return {"status": "EMPTY", "detail": ""}

    with_images = [p for p in pages if isinstance(p, dict) and p.get("image")]
    marked_text_only = comp.get("text_only", False)

    if not with_images:
        if marked_text_only:
            return {"status": "UNGROUNDED_LABELED", "detail": f"{len(pages)} pages, no images, correctly marked text_only"}
        else:
            return {"status": "UNGROUNDED_UNLABELED", "detail": f"{len(pages)} pages, no images, NOT marked text_only"}

    result = find_page_tracking_run(with_images)
    if result is None:
        return {"status": "GROUNDED_UNVERIFIABLE", "detail": f"{len(with_images)} pages with images, couldn't find any digit-run tracking the page number"}
    pos, score = result
    if score >= 0.9:
        return {"status": "GROUNDED", "detail": f"{len(with_images)} pages, digit-run #{pos} tracks page number ({score:.0%} of consecutive pairs)"}
    elif score >= 0.5:
        return {"status": "PARTIAL", "detail": f"best digit-run #{pos} only tracks {score:.0%} of consecutive pairs -- possible real drift or non-contiguous scan"}
    else:
        return {"status": "UNGROUNDED_NO_TRACKING", "detail": f"best match only {score:.0%} -- no digit-run reliably tracks page number, image URLs may not correspond to page order at all"}


def main():
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)

    results = {}
    for mb in manifest["megabooks"]:
        for comp in mb.get("components", []):
            key = f"{mb['slug']}/{comp['slug']}"
            results[key] = audit_component(mb, comp)

    by_status = {}
    for key, r in results.items():
        by_status.setdefault(r["status"], []).append((key, r["detail"]))

    order = ["GROUNDED", "GROUNDED_UNVERIFIABLE", "PARTIAL", "UNGROUNDED_NO_TRACKING",
              "UNGROUNDED_LABELED", "UNGROUNDED_UNLABELED",
             "MISSING_FILE", "PARSE_ERROR", "EMPTY"]
    for status in order:
        items = by_status.get(status, [])
        print(f"\n=== {status} ({len(items)}) ===")
        for key, detail in items:
            print(f"  {key}: {detail}")

    print(f"\n\nTOTAL components: {len(results)}")
    for status in order:
        print(f"  {status}: {len(by_status.get(status, []))}")


if __name__ == "__main__":
    main()
