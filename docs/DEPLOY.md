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

1. Asks a web-search-capable model (via OpenRouter) for the FINAL score of any
   not-yet-recorded knockout match whose two teams are known (`python -m src.fetch_results`).
   It is conservative — a match it can't confirm as finished, or a winner that isn't one of
   the two fixture teams, is skipped and left for the next run.
2. Propagates winners into the next round's fixtures (`python -m src.advance`).
3. Re-scores and runs the test suite.
4. Only if something changed, commits the new results to `main` (citing sources) and
   triggers the Pages deploy.

**One-time setup:** add your OpenRouter key as a repository secret —
**Settings → Secrets and variables → Actions → New repository secret**, name
`OPENROUTER_API_KEY`. (Optional: set a `RESULTS_FETCH_MODEL` repo *variable* to override the
default `perplexity/sonar-pro`; use a model that always web-searches and grounds its answer in
sources — a dedicated search model declines when a match hasn't finished, while a general model
with an optional `:online` plugin can skip the search and hallucinate a score.)

Test it any time without waiting for the cron: **Actions → Nightly results refresh → Run
workflow**. Dry-run locally with `python -m src.fetch_results --dry-run` (writes nothing).
