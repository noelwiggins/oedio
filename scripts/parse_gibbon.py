#!/usr/bin/env python3
"""Parse a Project Gutenberg Gibbon volume (Milman/Guizot HTML edition) into
oedio reader-data pages, with footnotes extracted as structured per-page data
rather than left inline.

Each Gutenberg <div class="chapter"> block (Gutenberg's own chapter/part
split, e.g. "Chapter XV: Part IV") becomes one reader page. This is a *text*
edition -- it is not page-aligned to any physical scan, so "image" is left
empty. A separate facsimile component (real LOC/IA scans) ships alongside it
in the megabook for readers who want the physical page, unaligned.

Footnote markers in the body text are replaced with a token:
    \u27e6fn:CH.N\u27e7
which the reader's JS turns into a clickable superscript. Footnote text is
pulled out into a parallel "footnotes" array on the same page object, each
tagged type="commentary" (contains an editorial "Note:" insertion, the
Milman/Guizot convention) or type="citation" (Gibbon's own source citation).
This is a heuristic, not a scholarly classification -- flagged in STATUS.md.

Usage: python3 parse_gibbon.py <input.html> <volume_number> <output.json>
"""
import json
import re
import sys
from bs4 import BeautifulSoup, NavigableString, Tag

FN_MARKER_RE = re.compile(r"linknoteref-(\d+\.\S+)")


def clean_footnote_text(raw: str, fn_id: str) -> str:
    """Strip the leading 'N ( return )' boilerplate and enclosing brackets."""
    # The (return) link is removed before this is called; what's left is
    # "<fn_id> [ ... ]" (possibly with a trailing whitespace-mangled id).
    esc_id = re.escape(fn_id.split(".")[-1])
    t = re.sub(rf"^\s*{esc_id}\s*", "", raw).strip()
    t = re.sub(r"^\(\s*\)\s*", "", t).strip()  # empty parens left by removed "(return)" link
    if t.startswith("["):
        t = t[1:]
    if t.endswith("]"):
        t = t[:-1]
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*", " ", t)
    return t.strip()


def classify_footnote(text: str) -> str:
    if "Note:" in text or text.rstrip().endswith("-M.") or text.rstrip().endswith("\u2014M."):
        return "commentary"
    return "citation"


def paragraph_to_text(p: Tag) -> str:
    """Render a <p> to plain text, replacing footnote-ref links with tokens."""
    # Collect matches first, then mutate -- mutating while iterating
    # .descendants corrupts the walk (BeautifulSoup's generator isn't
    # snapshot-safe against in-place tree edits).
    for a in p.find_all("a", id=re.compile(r"^linknoteref-")):
        fn_id = a["id"][len("linknoteref-"):]
        a.replace_with(f"\u27e6fn:{fn_id}\u27e7")
    text = p.get_text("", strip=False)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n", text).strip()
    return text


def parse_chapter_div(div: Tag, chapter_num: int):
    h2 = div.find("h2")
    title = h2.get_text(" ", strip=True) if h2 else f"Chapter {chapter_num}"
    title = re.sub(r"\s+", " ", title).strip()

    footnotes = []
    body_paragraphs = []

    for p in div.find_all("p", recursive=False):
        cls = p.get("class") or []
        if "foot" in cls:
            fn_link = p.find("a", href=re.compile(r"^#linknoteref-"))
            fn_id = None
            if fn_link:
                m = FN_MARKER_RE.search(fn_link["href"])
                if m:
                    fn_id = m.group(1)
                fn_link.decompose()  # drop the "(return)" link before extracting text
            raw = p.get_text(" ", strip=True)
            clean = clean_footnote_text(raw, fn_id) if fn_id else raw
            if fn_id:
                footnotes.append({
                    "id": fn_id,
                    "type": classify_footnote(clean),
                    "text": clean,
                })
            continue
        # anchor-only paragraph marking a footnote definition point, or empty
        if not p.get_text(strip=True) and not p.find("a", id=re.compile(r"^linknote-")) is None and len(p.get_text(strip=True)) == 0:
            continue
        txt = paragraph_to_text(p)
        if txt:
            body_paragraphs.append(txt)

    return {
        "title": title,
        "text": "\n\n".join(body_paragraphs),
        "footnotes": footnotes,
    }


def main():
    if len(sys.argv) != 4:
        print("Usage: parse_gibbon.py <input.html> <volume_number> <output.json>")
        sys.exit(1)
    in_path, vol_num, out_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]

    with open(in_path, encoding="utf-8") as fh:
        soup = BeautifulSoup(fh, "html.parser")

    pages = []
    page_num = 1
    for div in soup.find_all("div", class_="chapter"):
        h2 = div.find("h2")
        anchor = h2.find("a") if h2 else None
        chap_id = anchor.get("id", "") if anchor else ""
        # Skip front matter (intro/preface) -- keep only real numbered chapters
        if not chap_id.startswith("chap"):
            continue
        parsed = parse_chapter_div(div, page_num)
        if not parsed["text"]:
            continue
        pages.append({
            "page": page_num,
            "chapter_id": chap_id,
            "title": parsed["title"],
            "text": parsed["text"],
            "image": "",
            "footnotes": parsed["footnotes"],
        })
        page_num += 1

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(pages, fh, ensure_ascii=False, indent=1)

    total_fn = sum(len(p["footnotes"]) for p in pages)
    print(f"{in_path}: {len(pages)} pages, {total_fn} footnotes -> {out_path}")


if __name__ == "__main__":
    main()
