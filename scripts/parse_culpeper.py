#!/usr/bin/env python3
"""Parse the Project Gutenberg edition of Culpeper's Complete Herbal (1653,
public domain -- author died 1654) into oedio reader-data pages. Each herb
entry (marked by its own <h3>) becomes one reader page, matching the
alphabetical A-Z structure of the original book.

Usage: python3 parse_culpeper.py <input.html> <output.json>
"""
import json
import re
import sys
from bs4 import BeautifulSoup


def main():
    if len(sys.argv) != 3:
        print("Usage: parse_culpeper.py <input.html> <output.json>")
        sys.exit(1)
    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, encoding="utf-8") as fh:
        soup = BeautifulSoup(fh, "html.parser")

    # The body of the herbal is a flat sequence of <h3> (herb name) followed
    # by one or more <p> until the next <h3>. Walk the whole document in
    # order and group paragraphs under their preceding heading.
    body = soup.find("body") or soup
    pages = []
    current_title = None
    current_paras = []
    page_num = 0
    started = False  # skip front matter (epistle, dedication) before the herb entries begin

    def flush():
        nonlocal page_num, current_title, current_paras
        if current_title and current_paras:
            text = "\n\n".join(current_paras)
            if len(text.strip()) >= 20:
                page_num += 1
                pages.append({
                    "page": page_num,
                    "title": current_title,
                    "text": text,
                    "image": "",
                })
        current_title, current_paras = None, []

    for el in body.find_all(["h2", "h3", "p"]):
        if el.name == "h2":
            heading = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if "ENGLISH PHYSICIAN" in heading.upper() and "ENLARGED" in heading.upper():
                started = True
            continue
        if not started:
            continue
        if el.name == "h3":
            flush()
            current_title = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).title()
        elif el.name == "p" and current_title:
            txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if txt:
                current_paras.append(txt)
    flush()

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(pages, fh, ensure_ascii=False, indent=1)

    print(f"{in_path}: {len(pages)} herb entries -> {out_path}")


if __name__ == "__main__":
    main()
