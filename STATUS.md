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
- Cartography (7 historical Caribbean maps)

**Total:** 14 megabooks, 76 components registered

**Reader-data coverage: 76/76 components have data files (100%)**

## All content now present

### Literature
- Odyssey: 7 editions (Butcher-Lang 1921, Norgate 1863, Collins 1870, Childrens 1912,
  Phaeacian Greek 1880, Flaxman plates 1853, Doré Gallery 1890)
- Bible: KJV 1837, Variorum 1898, Doré Bible, Greek NT 1881
- Paradise Lost: 3 editions (1852, 1868 Doré, Milton Works 1881)
- Arabian Nights: 3 editions (1910, 1915, 1924 illustrated)
- Leaves of Grass: 3 editions (1897, 1900, 1921)
- Book of Wonders: Ottoman 1553 + transcription + English; Persian 1565 + layers; Persian 1866

### Natural Sciences / Plant Medicine
All 33 botanical components now have reader-data:
- Ancient: Ebers Papyrus, Dioscorides, Charaka Samhita, Bencao Gangmu, Bencao Jing,
  Badianus Manuscript, Cobo Historia
- Asian: Dongui Bogam (corpus + 25-vol manuscript, 1423 pages), Tibetan Gyushi,
  Canon of Avicenna, Kampo, Yamato Honzo, Honzo Wamyo, Persian/Avestan
- African: West African, South African, East African
- Americas: North American, Amazonian, Maya, Philippine, Australian
- European: Bald's Leechbook (279pp BL IIIF), Leechdoms Anglo-Saxon (546pp),
  Erbario Italian (202pp), Matthioli 1544 (448pp), Welsh Myddfai, Norse,
  Russian Travnik, Commission E, AHP, WHO Monographs

### Caribbean Travel & History
- Travel: Coleridge 1826, Down the Islands 1887, Gossip of the Caribbees 1893,
  Trinidad 1866, West Indies 1911
- History: Emancipation 1838, French Colonies 1867, Sailing Directions 1868, Pinkerton 1811

### Cartography
7 historical maps: Roggeveen 1675, Blaeu 1634, Thornton 1680, Coronelli 1690,
Schenk 1710, Bellin 1758, Lopez 1781

## Pending — needs implementation

1. **section.html template** — landing page for each section
2. **index.html update** — section navigation cards on homepage  
3. **Matthioli English translation** — Forge job pending (47 segments)
4. **Deeper Dongui-bogam / dongui-bogam-ms pages** — currently show corpus text;
   could link to the 1,423 scan pages in static/reader-data/dongui-vol-*.json
5. **Cartography viewer** — maps currently have 1-page stubs; 
   full DZI deep-zoom viewer needed (reference: PlentyFish /historical-maps)
6. **PlentyFish redirect** — plentyfish.ai should surface Oedio travel/cartography sections
