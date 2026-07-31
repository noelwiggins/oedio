#!/usr/bin/env python3
"""Strip OCR garbage lines (library stamps, catalog marks, binding noise)
from ingested LOC reader-data files, leaving real prose untouched.

Uses a real English dictionary (pyspellchecker) rather than shape-based
heuristics alone, so "hee"/"Ahh"/"ASR" are correctly rejected while real
but uncommon words, proper nouns, and roman numerals survive. Judges each
LINE by what fraction of its tokens are real words/numbers/names -- a
sentence with one odd proper noun survives; a line of pure stamp-noise
doesn't.

Usage: python3 clean_ocr_garble.py <slug> [--apply]
  Without --apply: dry run, reports what would change.
  With --apply: rewrites the file in place.
"""
import json, re, sys, os
from spellchecker import SpellChecker

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = SpellChecker(distance=1)
# The frequency-corpus dictionary has too many noisy short entries (2-letter
# web-corpus artifacts like "yt", "nan", "pe" register as "known"). For
# tokens that short, require an exact match against a curated real-word
# list instead of trusting the fuzzy dictionary.
SHORT_WORDS = {'a','i','o','ok','us','st','dr','mr','ms','of','to','in','on',
    'at','by','is','it','as','or','be','we','he','my','no','so','up','an',
    'if','do','me','am','ah','oh','ye','em','ha'}

ROMAN_RE = re.compile(r'^[IVXLCDM]+\.?$', re.I)
NUMBER_RE = re.compile(r'^\d+[.,]?\d*$')
WORD_RE = re.compile(r"^[A-Za-zÀ-ÿ'\u2019-]+$")
# Known-good short tokens that a general dictionary might miss or that are
# common in classical-text front matter (names, abbreviations, archaisms).
EXTRA_OK = {'a','i','o','ok','us','st','dr','mr','mrs','ms','ll','ye','thee',
            'thou','thy','hath','doth','tis','twas','oer','em','ere','vol',
            'ed','co','inc','ltd','llc','pp','no','vs'}

def token_plausible(tok):
    t = tok.strip('.,;:!?"()[]{}\u2018\u2019')
    if not t:
        return True
    if NUMBER_RE.match(t) or ROMAN_RE.match(t):
        return True
    if not WORD_RE.match(t):
        return False
    low = t.lower().strip("'-")
    if not low:
        return True
    if low in EXTRA_OK:
        return True
    if len(low) <= 2:
        return low in SHORT_WORDS
    if low in SC:
        return True
    # Capitalized token not in dictionary: treat as a plausible proper noun
    # or title word (name, place, ALL-CAPS heading -- "SAMSON", "MACMILLAN",
    # "ODYSSEY" are all real and common in 19th-c. title pages/headers) as
    # long as it's long enough not to be catalog-stamp noise. Short all-caps
    # fragments (<=3 chars) are excluded by the length check alone -- that's
    # exactly the ASR/MM stamp-code shape, without needing a separate
    # all-caps penalty that would also catch legitimate long title words.
    if t[0].isupper() and len(t) >= 4:
        return True
    return False

def line_is_garbage(line):
    tokens = [t for t in line.split() if t.strip('.,;:!?"()[]{}\u2018\u2019')]
    if not tokens:
        return False
    # Glossary/index lines ("Achilles, a-kil'lez") are real content whose
    # second half is a phonetic spelling that will never match a
    # dictionary. If the line opens with a real word followed immediately
    # by a comma, trust it -- that shape is essentially never OCR noise.
    first_bare = tokens[0].rstrip(',')
    if tokens[0].endswith(',') and token_plausible(first_bare):
        return False
    plausible = sum(1 for t in tokens if token_plausible(t))
    frac = plausible / len(tokens)
    return frac < 0.6

def clean_text(text):
    lines = text.split('\n')
    kept = [l for l in lines if not line_is_garbage(l)]
    # A real prose page has at least one line that reads as a coherent
    # phrase. If everything that survived line-filtering is just scattered
    # short fragments (a handful of tokens, no line with >=4 of them), the
    # page itself is catalog-stamp/binding noise that happened to spell a
    # few short real words by coincidence -- clear it entirely.
    total_tokens = sum(len(l.split()) for l in kept)
    # A real title page, index, or heading is made mostly of substantive
    # words (SAMSON, AGONISTES, PRONUNCIATION, Achilles -- real dictionary
    # words or proper nouns, 4+ letters). Garbage that happens to survive
    # per-line filtering is mostly trivial filler (if, a, an, weld, 4, -)
    # with almost nothing substantive in it. This only applies to short
    # pages -- real narrative pages have hundreds of tokens and never
    # reach this fallback at all.
    def is_substantive(tok):
        bare = tok.strip('.,;:!?"()[]{}\u2018\u2019')
        return len(bare) >= 4 and token_plausible(tok)
    if kept and total_tokens <= 40:
        subst = sum(1 for l in kept for t in l.split() if is_substantive(t))
        if subst / total_tokens < 0.3:
            return ''
    return '\n'.join(kept).strip()

# Books whose OCR is substantially NOT English (transliterated ancient Greek,
# etc.) must never go through this filter -- an English-dictionary check
# will flag every real word as garbage. This isn't a quality judgment on
# those OCR passes, just a hard scope boundary.
NON_ENGLISH_EXCLUDE = {"greek-nt-1881"}

def main(slug, apply_changes):
    if slug in NON_ENGLISH_EXCLUDE:
        print(f"{slug}: skipped -- non-English OCR, this filter doesn't apply")
        return
    path = f"{BASE}/static/reader-data/{slug}.json"
    pages = json.load(open(path))
    changed = 0
    now_empty = 0
    examples = []
    for p in pages:
        if not p.get('text'):
            continue
        cleaned = clean_text(p['text'])
        if cleaned != p['text']:
            changed += 1
            if len(cleaned) < 3:
                now_empty += 1
            if len(examples) < 6:
                examples.append((p['page'], p['text'][:70], cleaned[:70]))
            p['text'] = cleaned
    print(f"{slug}: {changed} pages modified, {now_empty} now effectively blank")
    for pg, before, after in examples:
        print(f"  p.{pg}: {before!r} -> {after!r}")
    if apply_changes and changed:
        json.dump(pages, open(path, 'w'), ensure_ascii=False)
        print(f"  written to {path}")

if __name__ == "__main__":
    main(sys.argv[1], "--apply" in sys.argv)
