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
- Shortened the layer-cycle crossfade (~half a beat) in both readers: reader.html 1300ms -> 900ms,
  layered.html two-phase ~1150ms -> ~740ms. Held-overlap midpoint kept in both, just tighter.
- Fixed the real cause of "top controls disappearing on scroll" -- reader.html's header/toolbar
  used position:sticky, but mobile switches the WHOLE reader from internal split-panel scrolling
  to plain body-level scrolling (a fundamentally different scroll context), and sticky was
  silently failing to persist across that switch on-device. Replaced with position:fixed on
  mobile (immune to that failure mode) plus a small JS pass that measures the header's actual
  rendered height once (it varies: longer titles, the facsimile note, etc.) and feeds that back
  in as reserved space via a CSS variable, so content never starts hidden underneath it. This
  fix applies automatically to EVERY book that uses reader.html (Bible, Odyssey editions, Paradise
  Lost, Arabian Nights, Leaves of Grass, Wonders -- all of them), not just the Ottoman manuscript,
  satisfying "same framework to all readers" for this specific issue.
  layered.html's Book-chip rail was NOT touched -- it never switches scroll models between
  desktop/mobile (always body-level), so it doesn't share this bug class; left as the
  already-working sticky implementation.
- Note on "same framework to all readers" more broadly: the layer-picker/cycle mechanism itself
  (not just the animation/header fixes) only *activates* where a panel_group exists, i.e. where
  a facsimile has AI-forged transcription+translation siblings. Right now that's only the Ottoman
  Wonders manuscript. Extending the AI-transcription/translation treatment to other facsimile-only
  books (Persian Wonders mss, Flaxman, Doré, Greek Phaeacian) is a separate, larger undertaking
  (a forge_translate.py run per book, real API cost/time) -- not done this session, flagged here
  so it's an explicit future decision rather than assumed-done.
- Slowed the layer-cycle crossfade in both readers so the "tissue paper" overlap is clearly
  perceptible rather than a quick cut. reader.html (Wonders manuscript): keyframe dissolve,
  1300ms, with the outgoing layer settling at 42% opacity and HOLDING there for ~500ms before
  finishing the fade -- long enough to register two stacked layers. layered.html (Odyssey):
  matching two-phase crossfade (rise/settle at partial opacity, then resolve to final), total
  ~1150ms. Cleanup timeouts extended to match in both.
- Fixed layer desync bug: switching layers (via desktop dropdowns or the mobile cycle button)
  was resetting scroll to page 1 every time instead of landing on the page you were just
  reading, so Ottoman/English/Scan drifted apart after any swap. Now tracks currentPageNum
  live (updated by the existing page-visibility observer), renders enough batches to reach
  that page in the newly-loaded layer, and scrolls straight to it (or the nearest page that
  has content, since blanks/covers are legitimately absent from some layers). Switching the
  right panel now also re-syncs the left panel to the same page automatically.
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
