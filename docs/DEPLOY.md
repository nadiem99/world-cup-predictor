# Deploying the leaderboard

The site is a single self-contained `output/index.html` with no external assets, so it
hosts anywhere static. The repo ships a GitHub Pages workflow that rebuilds and publishes
it on every push to `main`.

## Local preview

```bash
make site      # runs `python -m src.score` then `python -m src.site` -> output/index.html
make serve     # serves output/ at http://localhost:8000
```

Or just open `output/index.html` directly in a browser (it works over `file://`).

## Publish with GitHub Pages

1. Create a GitHub repo and push this project to `main`.
2. In the repo, go to **Settings → Pages** and set **Source: GitHub Actions**.
3. That's it. [`.github/workflows/deploy-pages.yml`](../.github/workflows/deploy-pages.yml)
   runs on every push to `main` (and via **Actions → Deploy to GitHub Pages → Run workflow**):
   it runs `python -m src.score` and `python -m src.site`, uploads `output/` as a Pages
   artifact, and deploys it. The published URL appears in the workflow's `deploy` job.

No build dependencies are installed — the tool is pure standard library.

## How updates reach the public site

The published leaderboard reflects whatever is committed under `data/` — the fixtures,
results, and one-shot bracket predictions. The typical loop:

1. Once, before R32: collect the brackets (`python -m src.collect bracket`, `... me`).
2. Enter results as matches finish in `data/results/<R>.json` — this scores the brackets.
   Then `python -m src.advance` to fill the next round's fixtures (Bracket-tab tree).
3. Commit and push. The workflow rebuilds and redeploys automatically.

> Note: `output/` and `data/scores.json` are git-ignored — they are generated artifacts,
> rebuilt by the workflow (and by `make site`) from the committed `data/` inputs.

## Nightly auto-refresh (hands-off results)

[`.github/workflows/refresh-results.yml`](../.github/workflows/refresh-results.yml) runs
every night (~08:06 UTC) so step 2 above happens on its own. Each run it:

1. Reads the day's finished knockout results from **FotMob** (`python -m src.fetch_results`).
   It parses FotMob's public 2026 World Cup league page, matches each finished knockout game
   to the corresponding fixture by team pairing, copies the full-time score across (resolving
   penalty shootouts via the match page), and skips anything not yet finished.
2. Propagates winners into the next round's fixtures (`python -m src.advance`).
3. Re-scores and runs the test suite.
4. Only if something changed, commits the new results to `main` (citing the FotMob source)
   and triggers the Pages deploy.

**No setup, no secrets, no API key** — the fetch is deterministic and standard-library only.
It records only what FotMob reports as finished, with internal-consistency guards (a level
score must go to penalties, the advancing team must be the higher scorer, etc.).

Test it any time without waiting for the cron: **Actions → Nightly results refresh → Run
workflow**. Dry-run locally with `python -m src.fetch_results --dry-run` (writes nothing). To
point at a different source page, set the `FOTMOB_MATCHES_URL` env var.
