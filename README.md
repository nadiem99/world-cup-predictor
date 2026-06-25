# 🏆 World Cup 2026 — AI Models vs. Nadiem

A fun benchmark: how well do AI models (and a human, Nadiem) predict the **2026 FIFA World Cup
knockout rounds**? Each round, every model gets the real fixtures and predicts the
score + who advances. Points are tallied into a leaderboard.

- **Round of 32 kicks off Sunday, June 28, 2026** — predictions must be collected before then.
- Models are queried through **OpenRouter** (one API key reaches Claude, OpenAI, Gemini,
  Qwen, and open-source models).
- **Zero dependencies** — pure Python standard library (3.9+). Nothing to `pip install`.

## Two contests at once

1. **Per-round (main):** before each round, each model predicts only that round's real
   fixtures. Fair (early mistakes don't compound) and the primary leaderboard.
2. **One-shot bracket (bonus):** collected once before R32 — each model calls the whole
   bracket to the champion. A separate "called-it-from-the-start" leaderboard.

## Scoring

**Per round** (best of the two — they do *not* stack, so a match is worth at most 3):
| Outcome | Points |
|---|---|
| Exact regulation/extra-time scoreline (penalty shootout ignored) | **3** |
| else correct advancing team only | **1** |

**Bracket bonus:** +1/+2/+3/+5 per team correctly predicted to reach the
R16/QF/SF/Final, champion **+10**, third place **+3**.

Tune any of these constants at the top of [`src/score.py`](src/score.py).

## Setup (once)

```bash
cd "/Users/nadiemahmed/Coding/world cup predictor"
cp .env.example .env          # then paste your OpenRouter key into .env
python -m src.models check    # verify the model ids in config/models.json are live
```

`models check` lists any ids that need fixing and suggests valid alternatives.
Edit [`config/models.json`](config/models.json) to add/remove models or set `"enabled": false`.

Curious about cost? `python -m src.collect estimate all` prints an offline token/call
ballpark — no key needed.

## Workflow each round

1. **Enter the fixtures** for the round in `data/fixtures/<ROUND>.json`
   (`R32`, `R16`, `QF`, `SF`, `TP`, `F`). Blank templates for every round already exist
   (regenerate/add with `python -m src.scaffold all`); the opening R32 match is pre-filled.
2. **Collect predictions — before kickoff:**
   ```bash
   python -m src.collect round R32          # all models in parallel (--workers N to tune)
   python -m src.collect me round R32       # enter your own picks (interactive)
   ```
   (Do `python -m src.collect bracket` and `... me bracket` once, before R32, for the bonus.)
3. **Enter results** as matches finish in `data/results/<ROUND>.json`.
4. **Score & build the site:**
   ```bash
   python -m src.score    # prints tables + writes data/scores.json
   python -m src.site     # writes output/index.html — open it in a browser
   ```
   Or just run `make site`. The site has four tabs: **Leaderboard** (sortable, with
   per-round sparklines), **Bracket** (connected tree), a browsable **Predictions** archive
   (every model's picks), and **About**.

## Layout

```
config/models.json        model roster (OpenRouter ids, display names, enabled flags)
data/fixtures/<R>.json     the real fixtures you enter per round
data/results/<R>.json      the real outcomes you enter per round
data/bracket.json          knockout wiring (which slots feed which) for the bracket tree
data/predictions/<R>/*.json  one file per model (+ Nadiem) per round
data/predictions/bracket/*.json  one-shot full-bracket predictions
output/index.html          the generated website (leaderboard · bracket · predictions · about)
src/      collect.py · score.py · site.py · scaffold.py · models.py · prompts.py · common.py
tests/    stdlib unittest suite · Makefile · docs/DEPLOY.md
```

## Develop & publish

- `make site` build · `make serve` preview at :8000 · `make test` run tests · `make clean`
- Tests run in CI on every push ([.github/workflows/ci.yml](.github/workflows/ci.yml)).
- Publish to GitHub Pages — see [docs/DEPLOY.md](docs/DEPLOY.md). Pushing to `main` rebuilds
  and redeploys automatically.

## Notes
- Team names are matched case-insensitively. Keep names consistent between fixtures,
  results, and what models output (the collector locks home/away names to your fixtures,
  so only the `advances` field needs to match — usually fine).
- Every raw model response is saved in its prediction file for auditing; failures are
  written to `*.error.json` and skipped so one bad model never blocks the rest.
```
