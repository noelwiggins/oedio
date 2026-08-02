# Oedio STATUS — Library of Alexandria

Last updated: 2026-08-02

## Live site
- URL: oedio.com
- 14 megabooks, 76 components, 100% reader-data coverage
- 5 sections: Literature, Natural Sciences, Travel, Cartography, History

## What was completed this session
- [x] 76/76 manifest components now have reader-data files
- [x] 29 botanical corpus books built from Plantacopia corpus segments
- [x] 7 Caribbean cartography map stubs pushed
- [x] balds-leechbook-ms (279pp) and leechdoms-cockayne (546pp) copied from Plantacopia
- [x] section.html template: section landing page with megabook grid cards
- [x] index.html rebuilt: 5 section navigation cards + full spine shelf below
- [x] app.py syntax error fixed (library() route)
- [x] Matthioli 1544 corpus (30 clean segments) added to Plantacopia corpus

## Pending
1. Deploy verification — confirm Railway redeploys cleanly after app.py fix
2. Cartography section — maps have 1-page stubs; DZI deep-zoom viewer needed
   (reference: PlentyFish /historical-maps viewer)
3. Deeper Dongui-bogam reader — could expose the 1,423 scan pages from dongui-vol-*.json
   via the standard reader rather than the corpus-text stub
4. Matthioli English translation layer — could be added as second reader panel
   once Forge job produces full English output (currently Italian only)
5. PlentyFish redirect — plentyfish.ai should link to Oedio travel/cartography sections

<!-- deploy trigger 2026-08-02T22:34:29.959234 -->
