# Oedio STATUS — Library of Alexandria

Last updated: 2026-10-13

## DARWIN (2026-10-13) — evolutionary discovery engine behind the secret volume

Built from Noel's "Darwin Master LLM Build Command" brief (75 sections). **Phase 1 nucleus is live**
at `/darwin/`; long-term plan: Oedio's domain may become Darwin's, with the book reader moving to its own URL.

**Entry**: a slim green spine, "ORIGIN OF SPECIES", filed beside Science on the homepage rotunda
(`templates/index.html`, `addSecretVolume` / `openPortal`). Click → it tips like a lever → the library
swings round (revolving bookcase, `bookcase-turn`) → `/darwin/?via=portal` swings in. Footer link
"Back through the bookcase" reverses it (`/?from=darwin`). Darwin pages send `noindex`.

**Code** (`darwin/`): `life.py` (Life World simulator), `core.py` (Darwin Core loop, operators,
validation helpers), `runner.py` (experiment worker subprocess), `store.py` (schema + Ledger),
`world_live.py` (shared live terrarium), `snapshot.py`, `openlab.py` (goal → feasibility),
`costs.py` (rates, caps), `web.py` (blueprint). Templates `templates/darwin/`, assets `static/darwin/`.
Tests: `python -m pytest tests/test_darwin.py -q` (20 tests, throwaway SQLite).

**How it works**
- Life World: vectorised numpy, W independent worlds × M slots. Genome = 10 genes (speed, sense, size,
  diet pref, 4 steering weights, repro threshold/share). Finite energy stores scale with size.
  Objectives: forage (food eaten), survive (endurance through a famine: ticks alive + ticks the remaining
  store would last), thrive (population with reproduction).
- **Determinism is bit-exact and batch-independent**: every random field is drawn without the world axis
  and broadcast; no sin/cos ever runs on world-shaped arrays (SIMD rounding differs with array length —
  headings are unit vectors rotated by per-slot factors). Verified: a genome scores identically alone or
  in a batch; REPLAY reproduces digests; production E-000001 matched a local run of the same seed.
- Core: islands + migration, tournament, elitism, point/multi mutation, uniform/blend crossover, distant
  recombination, immigrants, disturbances (scarcity/hazard shock, diet shift, mutation burst). Stops on
  generation limit, stagnation, cancel, CPU cap or budget (60% of cap for evolution, 40% reserved for
  validation). Fitness cache keyed by (genome, conditions).
- Validation: evolved best vs gen-0 best on 8 disjoint held-out seeds (≥7/8 wins and sign-test p≤0.05 →
  "replicated"), then perturbed conditions (→ "robust"); optional random-search baseline at equal
  evaluation count. Claims are filed only when training improved; otherwise `failure.no_improvement`.
- Ledger: `darwin_events`, append-only via DB triggers (SQLite + Postgres), SHA-256 chained,
  `/darwin/api/ledger/verify`. Claim status history also append-only.
- Worker: web spawns `python -m darwin.runner work`; one experiment per process (re-execs for the next),
  kernel RLIMIT_CPU at 1.25× cap; stale "running" rows (no heartbeat) are marked failed, never deleted.
- Live world: server-side, advances at 10 TPS while watched, frames every 2 ticks (client interpolates),
  stats every 50 ticks, checkpoint every 300 ticks; eras numbered from `world.genesis` events.
- Costs: compute = CPU-s × Railway $0.000463/vCPU-min (estimated); LLM = API token counts × price table
  in `costs.py` (billed). Kept separate everywhere.

**Access**: visitors can watch, read everything, run $0.10 experiments (45 CPU-s each, 3/hour/IP,
1800 CPU-s/day shared, queue ≤4). Owner passphrase (Railway var `DARWIN_OWNER_KEY`, login at
`/darwin/owner`) unlocks budgets to $10 and the LLM feasibility assessment (claude-sonnet-4-6).
`DARWIN_SALT` hashes visitor IPs.

**Status of brief sections**: see `/darwin/system` (capability table, also in every Snapshot).
Operational: Core, Life Lab, lineage, costs, LLM accounting, Ledger, claims, validation, replay,
Time Machine re-simulation, Snapshot ZIP + compare. Experimental: random baseline, Open Lab.
Planned: pause/resume, Discovery/Failure Memory reuse (Phase 2), more baselines, holdout worlds,
ablations; Web/Space/Operations Labs (Phase 3); meta-evolution, hybrid learning, transfer, external
review import (Phase 4); Reality Gap.

**Known / next**
- Thrive evaluations are ~3.5× slower (Python reproduction loop); a visitor's thrive run hits the 45 CPU-s
  cap early (shown in the estimate). Vectorising reproduction is the fix.
- LLM price table in `darwin/costs.py` (Sonnet 4.6 $3/$15 per MTok) was not re-verified this session.
- Gotcha: never put a literal `%` in SQL sent through `exec_driver_sql` with psycopg (read as a placeholder).


## Book Studio (2026-10-13) — print-to-PDF book designer

Any megabook -> `/book/<mega>/studio` (entry points: "Make a book" card on the
megabook page; book icon in the reader toolbar, preselects that edition's scan +
English + transcription via `?base=<slug>`).

- Pick up to 4 sources (scan / transcription / translation, AI-tagged), choose
  page range, spread or single-page mode, per-side layout (full page, bleed, or 2
  panels split h/v with auto-balanced ratio), covers (6 cloth colours, 5 foils),
  frontispiece, title, colophon, dedication (inscription lines), contents
  (ranges / detected headings / custom), foil monogram (4 styles), trim + quality.
- Live preview uses the SAME HTML generators as the PDF (`bookbuilder.py`,
  `mode="web"` vs `mode="pdf"`), posted into iframes via `/studio/preview`.
- Build = subprocess per job (`python bookbuilder.py build <jobdir>`), WeasyPrint 70
  (Persian/Arabic/Greek shaping) + pypdf (merge, bookmarks, two-page layout).
  Limits: 4 sources, 800 body pages, 8 jobs/IP/hour, 2 concurrent.
- Hosted viewer `/studio/book/<id>` (PDF.js 3.11.174 from cdnjs, HTTP Range
  streaming, two-page spreads), `/studio/book/<id>.pdf`, `/studio/book/<id>/download`.
  Job ids are unguessable 16-hex; books kept 60 days.
- Files: `bookbuilder.py` (engine), `studio.py` (blueprint), `templates/studio.html`,
  `templates/book_view.html`, `static/fonts/` (OFL TTFs).
- Infra: Railway volume `web-volume` mounted at `/data` (exports in `/data/exports`,
  falls back to `.exports/` locally; override with `OEDIO_EXPORT_DIR`).
  `RAILPACK_DEPLOY_APT_PACKAGES` includes pango/harfbuzz/fontconfig libs for WeasyPrint.
- Known: dense-text pages at 6x9 can drop under 6pt (warning shown, suggests larger trim);
  contents page may show an extra dotted rule (cosmetic).

## Forges (AI transcription/translation) — complete
Persian 1866 (207/207), Persian 1565, Phaeacian Greek, Doré (pages 13-15 content-filter-blocked, marked).
`scripts/forge_translate.py` (delimiter format, resumable). API key: `~/.anthropic_key` / env.

## Open
- Cloudflare apex CNAME must be added manually (`@`->ar9h7ehp.up.railway.app, `www`->02u348je.up.railway.app).
- R2 migration of reader data; roadmap: accounts, tips rail, store, Lulu print.

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

## Corpus-wide pagination grounding audit (2026-08-20)

Noel asked whether all Oedio books use the same algorithm to ground page
numbers to their real source. Investigated what actually makes this work,
then audited the whole corpus against it.

**The algorithm**: for a properly grounded book, `page` in reader-data
JSON is assigned directly from the real source's own scan sequence number
at ingestion time (e.g. Odyssey's `page: 3` has
`.../odysseyofh00home_0003/...` -- the literal 3rd photographed leaf of
that physical LOC item). This isn't something that needs retrofitting
across the library -- it's how the original ingestion pipeline already
worked for every real facsimile component. The one deviation was Gibbon
(built from a web text edition with no scan behind it at all), already
handled correctly via the `text_only` flag added this session rather than
pretending its synthetic page numbers are physical pages.

**Built `scripts/audit_pagination_grounding.py`**: for every one of the
249 components, checks whether page numbers actually track a real
sequence number embedded in the image URLs (tries every digit-run
position in the URL, since real-world schemes vary wildly by provider --
archive.org leaf index, LOC/WDL barcode+sequence, British Library hex ARK,
Princeton content-hash IIIF -- and picks whichever position moves in
lockstep with the page number across consecutive pages). This is a
reusable tool -- rerun it after any future ingestion to catch this class
of bug automatically, which is the actual answer to "make sure all books
use the same algorithm."

**Found one real, serious bug**: `badianus-manuscript` (+ its
transcription and english sibling components) had every single page
misordered -- 134 of 135 pages out of true sequence. The ingestion had
sorted image filenames lexicographically ("pg.1.jpg", "pg.10.jpg",
"pg.100.jpg", "pg.101.jpg", ..., "pg.2.jpg", "pg.20.jpg"...) instead of
numerically, so reader page 2 was showing the manuscript's real page 10,
reader page 3 was showing real page 100, etc., throughout the whole book.
Text and image stayed correctly paired with each other (both came from
the same source file per array entry) -- only the reading *order* was
scrambled. Fixed via new `scripts/fix_scrambled_page_order.py`: re-sorts
by the real number parsed from each image filename, reassigns sequential
`page` 1..135 in true reading order. Verified: page 1 through 6 now show
`pg.1`, `pg. 2`, `pg.3`, `pg.4`, `pg.5`, `pg.6` in order. Backups of the
pre-fix files are in `/tmp` locally if a diff is ever needed (not
committed -- the fix is a straightforward re-sort, verifiably correct).

**Everything else flagged by the audit turned out to be a false positive
from the tool's own URL-parsing limits, verified by hand**: dioscorides
(recto/verso "001a"/"001b" folio naming -- genuinely sequential, my
digit-tracker just can't model the a/b suffix), balds-leechbook-ms
(hex-style British Library ARK ids -- genuinely sequential, "0x" prefix
confused the digit-run parser). Two components are legitimately not
page-through books at all rather than being broken: `garima-gospels` and
`joga-pradipika` are curated illustration sets (a handful of
representative images from different sources/folios, not a full facsimile
read-through), so "page order" doesn't apply to them the way it does to
an actual book. `maya-medicine` uses Princeton's content-hash IIIF urls
(no sequence number embedded at all) -- genuinely unverifiable by URL
alone; would need a manual visual spot-check to confirm, flagged as a
follow-up rather than claimed either way.

**Net result**: 223/249 components confirmed grounded by the tool, the
rest individually accounted for above (1 real bug now fixed, rest false
alarms or legitimately different content type). Rerun
`scripts/audit_pagination_grounding.py` after adding new books to keep
this guarantee.



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

**Railway auto-deploy**: working again (pushes to `main` deploy; verified 2026-10-13 with Darwin).

## Live site
- URL: oedio.com | Railway: web-production-0df99e.up.railway.app
- 32 megabooks · 249 components (once the pending deploy above goes live)
- 7 sections: Literature, Medicine, Travel, History & Society, Religion, Science, Philosophy

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
