# oedio.com — Project Status

**Read this file at the start of any new session on this repo, before starting new work.**
Durable record of in-progress/incomplete work — survives session interruptions.

Last updated: 2026-07-29

## In progress / known incomplete
- forge_translate.py has a real (not just cosmetic) parsing gap: on badly damaged/water-stained
  pages the model sometimes prepends explanatory prose before the JSON object instead of
  responding with only JSON. The script's parser doesn't strip that prose, so `json.loads` throws
  and the page silently comes back as "0 new" / stays empty forever on retry (this bit 2 of the
  207 Persian lithograph pages — pp 2 and 205, both water-damaged). Worth hardening the script
  itself (e.g. regex out the last `{...}` block, or add an explicit "no other prose before or
  after" instruction to the prompt) rather than hand-fixing case by case next time.
- Reinvent-no-wheels additions queued: Wustenfeld's 1849 Arabic critical edition of Qazwini and
  Ethe's 1868 partial German translation (both PD) as further Book of Wonders layers; check
  archive.org/LOC.
- Extending the AI-transcription/translation treatment to the remaining facsimile-only books
  (Persian 1565 Wonders mss, Doré, Greek Phaeacian) is still a separate, larger undertaking (a
  forge_translate.py run per book, real API cost/time) — not started.
- R1 megabook-builder (anchor/asset schema, accounts, "add to my megabook", saved personal
  megabooks) — designed, not started. Then R2 tips rail (Met/AIC/Rijks CC0 + DPLA/NYPL APIs),
  R3 store/gifting, R4 print (flatten-to-PDF + Lulu).
- Turkish classics research (resolved): Dede Korkut (mss in Dresden/Vatican, EN trans. post-1929),
  Sahname-i Selim Han (Topkapi), Husn u Ask (EN trans. 2005) — none possible copyright-free from
  LOC. Delivered instead: Book of Wonders megabook (Ottoman 1553 + Persian 1565 mss + 1866
  lithograph, all facsimile). Gibb's History of Ottoman Poetry (LOC 05036360, 1900-09) is the
  PD path to Ottoman poetry excerpts in English for a future megabook.
- **Cloudflare DNS for oedio.com must be added manually** (ONLY remaining item, still open) (API
  DNS writes broken account-wide, error 7003 — known issue, see memory): dash.cloudflare.com →
  oedio.com → DNS → CNAME | name `@` | target `ar9h7ehp.up.railway.app` | proxied ON.
  Zone ID: 0a8eea69e8135d1f0777c681665c32f6. Custom domain already attached on Railway side.

## Recently completed (this session)
- **Persian lithograph 1866 forge run: COMPLETE.** All 207 pages transcribed (Persian, printed
  Tehran-tradition text) and translated to English via scripts/forge_translate.py (203 real
  text pages, 4 correctly identified as blanks/covers/plates: pp 1, 204, 206, 207). Two pages
  (2, 205) needed a manual one-off fix outside the script due to the prose-preamble parsing gap
  noted above (water damage triggered the model to explain the damage before giving JSON) —
  fixed by re-calling the API directly with a regex-tolerant parser and merging the result in.
- Wired wonders-persian-1866-transcription / wonders-persian-1866-english into
  data/manifest.json as siblings of wonders-persian-1866 — PANEL_GROUPS auto-detected the trio
  with zero code changes (same mechanism as the Ottoman trio), verified with a local simulation
  before pushing.
- Pushed (commits baa9a40, c27759f) and deployed to Railway with latestCommit:true — confirmed
  SUCCESS status, then spot-checked the live reader at
  /book/book-of-wonders/read/wonders-persian-1866: both new layers ("Persian lithograph text
  (AI transcription)" and "Persian lithograph, English (AI translation)") render correctly in
  the panel picker.
- ANTHROPIC_API_KEY for local forge runs is stored as a Railway variable on the oedio service
  itself (projectId 38351cd0-c3fb-45a0-bb1a-ac96c9430d52, environmentId
  0aa1dbcb-0a8b-4218-984c-125c1469087c, serviceId d0f7adff-5ead-43dd-8ea7-8145308e7c89) — pull it
  from there at the start of any session that needs to run forge_translate.py locally (fresh
  containers don't have it staged). Also note $HOME is /root in this container, not
  /home/claude — stage the key at ~/.anthropic_key (i.e. /root/.anthropic_key), not
  /home/claude/.anthropic_key, or export ANTHROPIC_API_KEY directly.
- Wonders Ottoman manuscript forge run (from prior session): confirmed still live and correct,
  no regressions from this session's work.

## Standing project facts
- Stack: Flask + PostgreSQL (optional catalog mirror) + Railway, Cloudflare DNS. Domain: oedio.com.
- Repo: noelwiggins/oedio. Data contract per component: static/reader-data/{slug}.json = [{page, text, image}].
- Manifest is source of truth: data/manifest.json. Postgres mirrors it at startup when DATABASE_URL is set.
- Ingestion: scripts/ingest_loc.py <loc_item_id> <slug> (ALTO XML per-page text + IIIF pct:50 images).
- Facsimile components (facsimile: true in manifest) = image-only reader flow (Greek, plate books).
- forge_translate.py <slug> <start> <end> <lang> [description] [--no-translation]: resumable,
  merges into existing -transcription/-english files, skips already-done pages. Needs
  ANTHROPIC_API_KEY (see note above on where to get it). Runs slower than expected under the
  280s-ish tool-call window here — plan on chaining several calls in overlapping ranges (the
  resume logic makes re-running a superset range cheap and safe) rather than one big call.
- Next planned: Internet Archive + Google Books ingesters (same contract), user shelves ("build
  your own megabook"), correction-submission button, two-page spread view.

## How to use this file going forward
- Starting a session: read this first; treat "In progress" items as priority.
- Ending a session with something incomplete: update "In progress" with exactly what's left and why.
- Completing something: move to "Recently completed"; prune periodically.
