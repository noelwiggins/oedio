# oedio.com — Project Status

**Read this file at the start of any new session on this repo, before starting new work.**
Durable record of in-progress/incomplete work — survives session interruptions.

Last updated: 2026-07-27 (2)

## In progress / known incomplete
- Wonders manuscript forge run: COMPLETE. All 314 pages of the 1553 Ottoman manuscript
  transcribed (nesih -> readable Arabic script) and translated to English via scripts/forge_translate.py
  (273 real text pages, 12 correctly identified as blanks/covers/flyleaves). Both layers live in
  the megabook manifest as wonders-ottoman-1553-transcription / -english. Not yet deployed —
  next step is push + Railway deploy with latestCommit:true, then spot-check a few pages in the
  live reader against the source scans.
- forge_translate.py is now a general-purpose engine: point it at any facsimile component's slug
  + page range + language name and it produces both layers. Reuse directly for future manuscript
  megabooks (Persian Wonders mss are the obvious next target — same forge, different language arg).
- Minor prompt refinement still open: occasional English meta-preamble ("This is a preface
  page... The text reads:") instead of starting the translation directly — cosmetic, not blocking.
- Reinvent-no-wheels additions queued: Wustenfeld's 1849 Arabic critical edition of Qazwini and
  Ethe's 1868 partial German translation (both PD) as further layers; check archive.org/LOC.
- R1 megabook-builder (anchor/asset schema, accounts, "add to my megabook", saved personal
  megabooks) — designed, not started. Then R2 tips rail (Met/AIC/Rijks CC0 + DPLA/NYPL APIs),
  R3 store/gifting, R4 print (flatten-to-PDF + Lulu).
- Turkish classics research (resolved): Dede Korkut (mss in Dresden/Vatican, EN trans. post-1929),
  Sahname-i Selim Han (Topkapi), Husn u Ask (EN trans. 2005) — none possible copyright-free from
  LOC. Delivered instead: Book of Wonders megabook (Ottoman 1553 + Persian 1565 mss + 1866
  lithograph, all facsimile). Gibb's History of Ottoman Poetry (LOC 05036360, 1900-09) is the
  PD path to Ottoman poetry excerpts in English for a future megabook.
- **Cloudflare DNS for oedio.com must be added manually** (ONLY remaining item) (API DNS writes broken account-wide,
  error 7003 — known issue, see memory): dash.cloudflare.com → oedio.com → DNS →
  CNAME | name `@` | target `ar9h7ehp.up.railway.app` | proxied ON.
  Zone ID: 0a8eea69e8135d1f0777c681665c32f6. Custom domain already attached on Railway side.

## Recently completed (this session)
- Mobile layer-cycle button rebuilt as a 3-way pill (was a broken binary toggle that only ever
  reached the text side): tap cycles through every entry in a panel_group with a tissue-paper
  crossfade (DOM clone of the outgoing view fades out over the freshly-swapped-in content,
  reusing the desktop setRightSlot() plumbing so search/TTS/bookmarks stay correctly wired
  after each cycle). Falls back gracefully: dual-language books still cycle
  translation<->original with the same tissue effect; plain facsimile books (no group) keep
  the original tap-to-open-scan behavior. Button label shows the current layer name and
  updates live.
- Independent left/right panel layer pickers for AI-forged page-aligned trios (facsimile +
  transcription + translation share identical pagination/images, so either reader panel can
  hold any of the three -- like map layers over one page). Right panel is the book's full
  reading pipeline (search/TTS/bookmarks/jump-to-page all stay wired, just rebuilt against
  whichever layer is picked); left panel is a lighter synced companion. Backend: PANEL_GROUPS
  in app.py auto-detects <slug>+"-transcription"/"-english" siblings, zero effect on books
  without them (verified 0 picker divs on Bible/Odyssey vs 2 on Wonders Ottoman trio).
  Smart defaults: opening the transcription page now defaults left panel to English
  automatically (the exact gap reported); opening the raw facsimile now shows the
  transcription on the left instead of being hidden entirely.
  Reusable for future forge_translate.py runs on other manuscripts -- the picker appears
  automatically once -transcription/-english siblings exist in the manifest, no template work.
- Layer cycle button is now the primary mobile navigation (layered reader: cycles enabled
  text layers + Source scans with tissue-paper crossfade + scroll anchoring; standard reader:
  text <-> source with overlay fade). Long-press removed everywhere (conflicted with text
  selection / browser image menus). Navigation model: layer controls + cycle button + scroll.
- Layered Reader shipped at /book/odyssey/layers: book-aligned layer stack (B&L + Norgate
  translations toggleable, side-by-side on desktop / stacked mobile), inline page pills opening
  source scans, Flaxman filmstrip per book (proportional page mapping), Greek facsimile cards on
  Books VI-VIII & XIII, streaming audio layers (LibriVox English narration + ancient Greek
  recitation, per book, persistent mini-player), MD3 bottom sheet layer control (FAB on mobile,
  docked panel desktop), Book I-XXIV chip rail with scroll-spy, lazy section rendering,
  History-API-managed overlays, localStorage layer persistence.
  Alignment data: static/reader-data/odyssey-alignment.json (B&L via detected BOOK headings,
  all 24 exact; Norgate/Flaxman via canonical-line-count proportional mapping, validated +/-2pp).
- Known future work for layered mode: passage/line-level alignment (currently book-level),
  user-added illustration layers from external sources (needs accounts/storage), Collins &
  Children's editions not yet in layered view (chapter structures don't map to Books).
- Postgres catalog mirror now seeding (psycopg[binary] 3.2.4 + postgresql+psycopg:// URI +
  RAILPACK_DEPLOY_APT_PACKAGES=libpq-dev env var — same fix chain as jack-wellness).
- Initial build: megabook library shelf, megabook detail page, split-panel reader
  (ported from plentyfish, canonical pattern), facsimile mode for no-OCR editions,
  edition-switcher dropdown inside the reader.
- Odyssey megabook seeded with 6 LOC editions (Butcher & Lang 1921, Norgate 1863,
  Greek Phaeacian episode 1880, Flaxman illustrated 1853, Collins companion 1870,
  Children's Odyssey 1912). Reader-data JSON committed under static/reader-data/.

## Standing project facts
- Stack: Flask + PostgreSQL (optional catalog mirror) + Railway, Cloudflare DNS. Domain: oedio.com.
- Repo: noelwiggins/oedio. Data contract per component: static/reader-data/{slug}.json = [{page, text, image}].
- Manifest is source of truth: data/manifest.json. Postgres mirrors it at startup when DATABASE_URL is set.
- Ingestion: scripts/ingest_loc.py <loc_item_id> <slug> (ALTO XML per-page text + IIIF pct:50 images).
- Facsimile components (facsimile: true in manifest) = image-only reader flow (Greek, plate books).
- Next planned: Internet Archive + Google Books ingesters (same contract), user shelves ("build your own
  megabook"), correction-submission button, two-page spread view.

## How to use this file going forward
- Starting a session: read this first; treat "In progress" items as priority.
- Ending a session with something incomplete: update "In progress" with exactly what's left and why.
- Completing something: move to "Recently completed"; prune periodically.
