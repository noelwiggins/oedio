# Oedio — session start checklist

1. Read STATUS.md (current state, open items) before doing anything.
2. Credentials live in the user's memory (files /preferences.md and /areas/oedio-keys.md): Railway token, GitHub PAT, Anthropic API key, Railway project/service IDs. Never commit secrets to this repo.
3. Git: push to `origin main` (remote already carries the PAT in the sandbox). If the push is refused by the session proxy, attach the repo with add_repo (push access).
4. Deploy: Railway GraphQL (https://backboard.railway.com/graphql/v2). Pushes to main auto-deploy; poll `deployment(id)` until SUCCESS. Live: web-production-0df99e.up.railway.app (www.oedio.com once DNS is set).
5. Stack: Flask + Postgres, content in static/reader-data/*.json, manifest in data/manifest.json, MD3 theme in static/css/md3-theme.css. Footer: "© {year} Noel Wiggins. All rights reserved."
6. Book Studio (bookbuilder.py, studio.py, templates/studio.html, book_view.html) is documented in STATUS.md; tile.loc.gov blocks Railway IPs, so those scans are fetched by the browser.
7. When a module is verified end-to-end, document the reusable pattern in memory; update STATUS.md at the end of the session.
8. Don't pgrep/pkill -f a pattern that appears in your own command line (kills the shell).
