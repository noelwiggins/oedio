# Oedio STATUS — Library of Alexandria

Last updated: 2026-08-02

## Vision

Oedio is a modern Library of Alexandria — a unified digital library where every
great text and every primary source document lives in a single reader with
synchronized facsimile + translation layers.

## Current state

**Sections:** 5 top-level sections in data/manifest.json
- Literature (Odyssey, Bible, Paradise Lost, Arabian Nights, Leaves of Grass, Book of Wonders)
- Natural Sciences / Plant Medicine (5 megabooks, 33 botanical manuscript components)
- Travel & Exploration (Caribbean Travellers — 5 books)
- History & Society (Caribbean primary documents — 4 books)
- Cartography (7 historical Caribbean maps with DZI deep-zoom)

**Total:** 14 megabooks, 76 components

## Imported content

### From Plantacopia (noelwiggins/materia-medica-americana)
Reader-data copied to static/reader-data/:
- balds-leechbook.json (279 pages, BL IIIF)
- leechdoms-anglo-saxon.json (546 pages, IA)
- erbario-italian.json (46 pages, IA)
- matthioli-dioscorides-1544.json (448 pages, IA)
- dongui-vol-01.json through dongui-vol-25.json (all 25 volumes)
- dongui-alignment.json

### From PlentyFish (noelwiggins/plentyfish)
Reader-data copied to static/reader-data/:
- coleridge-1826.json
- down-islands-1887.json
- emancipation-1838.json
- french-colonies-1867.json
- gossip-caribbees-1893.json
- pinkerton-1811.json
- sailing-directions-1868.json
- trinidad-1866.json
- west-indies-1911.json

## In progress

**Forge job #225** — Matthioli 1544 Italian botanical translation (47 segments)
Status: running. Output: static/data/matthioli_1544_b01.json
After completion: rebuild corpus shards in Plantacopia to include Matthioli translations.

## Pending — needs implementation

1. **section.html template** — landing page for each section (literature/natural-science/travel/etc)
   needs: section header, megabook grid, component count
2. **index.html update** — Oedio homepage needs section navigation cards
3. **reader.html** — already handles facsimile + translation layers (full-featured)
4. **Matthioli English translation** — after Forge #225 completes, add english layer to reader
5. **Cartography section** — DZI maps from PlentyFish need a dedicated map viewer
   (existing /historical-maps viewer in PlentyFish is the reference)
6. **PlentyFish redirect** — plentyfish.ai should surface Oedio travel/cartography sections
