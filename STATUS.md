# Oedio STATUS — Library of Alexandria

Last updated: 2026-08-02

## 🚨 ACTION REQUIRED: Manual Railway Redeploy

Railway auto-deploy is not picking up GitHub commits for this repo.
The live site (oedio.com) is running OLD code with only 6 megabooks.

**To deploy the new code:**
1. Go to railway.app → oedio project
2. Click the web service → Deployments
3. Click "Redeploy" on the latest deployment, or trigger a new deployment

All code changes are committed and ready. Once Railway redeploys:
- Homepage will show 5 section navigation cards + all 14 megabook spines
- /section/<slug> routes will work
- All 76 components have reader-data

## Code state (all committed to GitHub main)

- app.py: section_page() route added, _page_count() fast version (skips >500KB files), syntax OK
- templates/index.html: 5 section cards + spine shelf
- templates/section.html: megabook grid for each section
- data/manifest.json: 14 megabooks, 76 components, 5 sections
- static/reader-data/: 76 JSON files present (100% coverage)
- Procfile: gunicorn --timeout 120 --preload --workers 1

## Content state

**14 megabooks, 76 components, 100% reader-data coverage**

### Literature (6 megabooks)
Odyssey (7 eds), Bible (4 eds), Paradise Lost (3 eds), Arabian Nights (3 eds),
Leaves of Grass (3 eds), Book of Wonders (7 eds)

### Natural Sciences (5 megabooks)
Ancient & Classical (7 books), Asian Botanical (8 books), African (3 books),
Americas (5 books), European (10 books)

### Travel & Exploration (1 megabook)
Caribbean Travellers (5 books)

### Cartography (1 megabook)
7 historical Caribbean maps

### History & Society (1 megabook)
4 Caribbean primary documents

## Pending (post-redeploy)
1. Cartography maps — 1-page stubs; DZI deep-zoom viewer needed
2. Deeper Dongui-bogam reader — could expose 1,423 scan pages
3. Matthioli English translation layer
4. PlentyFish → Oedio redirect for travel/cartography content
