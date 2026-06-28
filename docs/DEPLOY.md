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
3. Commit and push. The workflow rebuilds and redeploys automatically.

> Note: `output/` and `data/scores.json` are git-ignored — they are generated artifacts,
> rebuilt by the workflow (and by `make site`) from the committed `data/` inputs.
