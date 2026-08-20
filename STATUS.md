# Oedio STATUS — Library of Alexandria

Last updated: 2026-08-19

## Gibbon's Decline and Fall — footnote-centric section (2026-08-19)

Added as a new megabook: `gibbon-decline-fall` (history section), 6-volume
group (`gibbon-vol1`..`gibbon-vol6`), 296 pages, 8,542 footnotes.

- **Source**: Project Gutenberg #731–736, the Milman/Guizot 1845 edition —
  the only Gutenberg edition with all footnotes intact (Gibbon's own
  citations + Guizot's editorial corrections, signed "—M.").
- **Pipeline**: `scripts/parse_gibbon.py` splits each volume's HTML on
  Gutenberg's own chapter/part divisions, replaces inline footnote refs
  with `⟦fn:CH.N⟧` tokens, and extracts a parallel `footnotes[]` array per
  page (`type: citation` or `commentary`, heuristically classified by the
  "Note: ... —M." convention). Rerunning it is one command per volume if
  the parse ever needs adjusting.
- **This is a text edition, not a page-aligned facsimile** — Gutenberg's
  web pagination doesn't match any physical scan. No image field is set;
  reader ships in a new `TEXT_ONLY` mode (see below).
- **New reader capability — `TEXT_ONLY` mode**: fixed a real bug where the
  page filter (`pages.filter(p => p.image)`) silently dropped every page
  without a scan image. `text_only: true` on a manifest component now
  keeps all pages and hides the view-scan/grid-view buttons (meaningless
  without images) instead of crashing or rendering blank. Available for
  any future text-only component, not just Gibbon.
- **Footnote panel UI**: inline clickable superscript markers (color-coded
  citation vs. commentary), a right-rail (desktop) / bottom-sheet (mobile)
  panel listing every footnote on the page in view, opens scrolled to
  whichever marker was tapped. New toolbar button, auto-hidden on books
  with no footnote data.
- **AI assistant integration**: "Explain this page" now detects real
  footnote data and glosses what the footnotes *don't* already cover
  (who a cited classical author is, untranslated Latin in an editorial
  note) instead of duplicating them.

**Pending / not done for Gibbon:**
- No real facsimile component paired yet — would need genuine LOC/IA scan
  verification (per the site's own broken-source-audit standard) for a
  period edition; not attempted this session rather than guess a loc_item.
- No maps/illustrations sourced for this megabook yet.
- Footnote `type` classification is a heuristic (looks for "Note:" +
  "—M." signature) — not scholarly-reviewed.

## Homepage: search + Featured grid, ported from Plantacopia's UX (2026-08-19)

Added a prominent search hero (eyebrow + input + quick-search chips) and
a "Featured" card grid to the homepage, matching what you liked about
Plantacopia — done in Oedio's own gold/MD3 visual language rather than
Plantacopia's forest-green palette, since the two sites already have
distinct, coherent identities and grafting one onto the other would clash.

- **New `/api/search` route**: metadata search (title, author,
  description, component roles/notes/contributors) across all 32
  megabooks / 249 components. Tested: "footnote" → Gibbon, "maps" →
  Caribbean Cartography, "homer" → Odyssey + Hesiod. **Not full-text
  across every page** — the corpus is too large (many components run
  thousands of pages) to scan per-keystroke without a real search index.
  That would be the natural next step if deeper search is wanted.
- Results render in an overlay panel (title/author/snippet, click →
  book page), same interaction shape as Plantacopia's search-results-overlay.
- **Featured grid**: 4 hand-picked cards (Gibbon footnote reader, Odyssey
  layered reader, Florentine Codex facsimile, Marcus Aurelius) using the
  existing SVG emblem sprite + per-card accent colors. Curated, not
  algorithmic — update the `FEATURED` array in `templates/index.html` to
  change which books are highlighted.
- Did not port Plantacopia's rotating frontispiece hero (the book-spread
  illustration cycler) — would need curated illustration URLs per
  megabook, which don't exist yet; flagging as a possible follow-up.

**Still pending: the Railway auto-deploy issue above.** Three commits
now sit unpushed to production (`50a03a3`, `b96ea6f`, `90834c7`) —
Gibbon's footnote section, the STATUS.md update, and this search/featured
work are all built, tested locally, and on GitHub `main`, but the live
site is still serving the older commit `6eef216`. Needs the manual
reconnect in the Railway dashboard before any of this goes live.


## Live site
- URL: oedio.com | Railway: web-production-0df99e.up.railway.app
- 32 megabooks · 249 components (once the pending deploy above goes live)
- 7 sections: Literature, Medicine, Travel, History & Society, Religion, Science, Philosophy
- **NOTE**: the counts above reflect GitHub `main`, not necessarily what's
  currently served — see the Railway deploy-stuck note above before
  trusting oedio.com matches this file.

## Architecture — storage

### What lives where
| Data | Location | Size | Notes |
|---|---|---|---|
| manifest.json | GitHub repo | 50KB | Source of truth for megabooks/components |
| reader-data/*.json | GitHub repo → **migrate to R2** | 43MB | Pointer files: image URLs + text |
| Actual scan images | LOC IIIF / BL IIIF / Wikimedia | TB | We hotlink, never copy |
| Postgres DB | Railway | ~50KB | Mirror of manifest — metadata only |

### Image storage philosophy
We do NOT store scan images. We hotlink from institutional IIIF servers:
- Library of Congress (tile.loc.gov) — primary source, billions of pages
- British Library (bl.digirati.io) — Bald's Leechbook, etc.
- Wikimedia Commons — Dongui Bogam (NLK scans), some rate-limiting
- Internet Archive — fallback for IA-hosted books

At 1,000 megabooks our reader-data JSON stays ~300MB total.
The only case to cache images ourselves: Wikimedia rate limiting (R2 cache for Dongui).

## R2 Migration — PENDING SETUP

Both apps are R2-ready. When R2_BASE_URL is set, reader-data is served from R2.
When not set, falls back to /static/reader-data/ (current behavior, no breakage).

### Steps to complete migration

**1. Create Cloudflare R2 bucket**
   - Go to dash.cloudflare.com → R2 Object Storage
   - Create bucket: `oedio-reader-data`
   - Settings: Location = Auto, Default storage class = Standard

**2. Create R2 API token**
   - dash.cloudflare.com → R2 → Manage R2 API Tokens → Create API Token
   - Permissions: Object Read & Write on bucket `oedio-reader-data`
   - Save the Access Key ID and Secret Access Key

**3. (Optional) Custom domain**
   - R2 bucket → Settings → Custom Domains → Add `reader-data.oedio.com`
   - This gives: https://reader-data.oedio.com/reader-data/{slug}.json
   - Alternative: use the auto-assigned https://pub-xxx.r2.dev URL

**4. Run the migration script**
   ```bash
   CF_ACCOUNT_ID=your_account_id \
   CF_R2_ACCESS_KEY=your_access_key \
   CF_R2_SECRET=your_secret \
   python3 scripts/r2_migrate.py
   ```
   This uploads all 143 reader-data JSON files (44MB) to R2.

**5. Set env vars in Railway**
   - Oedio web service → Variables → Add:
     `R2_BASE_URL = https://reader-data.oedio.com`  (or pub-xxx.r2.dev URL)
   - Plantacopia web service → Variables → Add same
   - Both services will redeploy automatically

**6. Remove reader-data from repos (after verifying R2 works)**
   - This keeps repos lean and deploy times fast
   - Script: `python3 scripts/r2_migrate.py --cleanup` (removes GitHub files)

### What's already done
- [x] Oedio app.py: `_reader_url()` uses R2_BASE_URL when set, /static/ fallback
- [x] Plantacopia app.py: `/reader-data/` route redirects to R2 when R2_BASE_URL set
- [x] Migration script: `scripts/r2_migrate.py` (needs CF credentials to run)

## Pending
1. **R2 migration** — needs CF credentials (see above)
2. Cartography maps — 1-page stubs; DZI deep-zoom viewer needed
3. Matthioli English translation layer
4. PlentyFish → Oedio redirect
