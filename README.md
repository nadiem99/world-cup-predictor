# 🏆 World Cup 2026 — AI Models vs. Nadiem

A fun benchmark: how well do AI models (and a human, Nadiem) predict the **2026 FIFA World Cup
knockout stage**? Before the Round of 32, everyone calls the **entire bracket once** — all the
way to the champion. That single prediction is locked in; as the real tournament plays out,
each bracket is scored against what happened. One prediction, one leaderboard.

- **Round of 32 kicks off Sunday, June 28, 2026** — brackets must be collected before then.
- Models are queried through **OpenRouter** (one API key reaches Claude, OpenAI, Gemini,
  Qwen, and open-source models).
- **Zero dependencies** — pure Python standard library (3.9+). Nothing to `pip install`.

## Scoring

Points for every team you correctly predict to **reach a stage**, weighted by depth:

| Reaches | Points (per correct team) |
|---|---|
| Round of 16 | **+1** |
| Quarter-finals | **+2** |
| Semi-finals | **+3** |
| Final | **+5** |
| Champion | **+10** |
| Third place | **+3** |

Highest total wins. Tune any of these constants at the top of [`src/score.py`](src/score.py).

## Setup (once)

```bash
cd "/Users/nadiemahmed/Coding/world cup predictor"
cp .env.example .env          # then paste your OpenRouter key into .env
python -m src.models check    # verify the model ids in config/models.json are live
```

`models check` lists any ids that need fixing and suggests valid alternatives.
Edit [`config/models.json`](config/models.json) to add/remove models or set `"enabled": false`.

Curious about cost? `python -m src.collect estimate` prints an offline token/call
ballpark — no key needed.

## Workflow

**Once, before the Round of 32 kicks off:**

1. **Fill the R32 teams** in `data/fixtures/R32.json` (the 32 qualifiers in their official
   bracket slots). The bracket prompt is built from these matchups.
2. **Collect the one-shot brackets:**
   ```bash
   python -m src.collect bracket            # all models in parallel (--workers N to tune)
   python -m src.collect me                 # enter your own bracket (interactive)
   make enter                               # …or a nicer point-and-click version (private, local-only)
   ```

**Then, as the tournament plays out** — automatically, every night:

A nightly GitHub Action ([`refresh-results.yml`](.github/workflows/refresh-results.yml))
looks up the day's finished knockout results, records them, and redeploys the leaderboard.
See [docs/DEPLOY.md](docs/DEPLOY.md#nightly-auto-refresh-hands-off-results) (needs an
`OPENROUTER_API_KEY` repo secret). To do it by hand instead:

3. **Enter results** as matches finish in `data/results/<ROUND>.json` (`R32`, `R16`, `QF`,
   `SF`, `TP`, `F`). Blank templates exist for every round (`python -m src.scaffold all`).
   Then `python -m src.advance` fills the next round's fixtures (and the third-place match)
   from the winners, so the bracket tree stays current.
4. **Score & build the site:**
   ```bash
   python -m src.score    # prints the leaderboard + writes data/scores.json
   python -m src.site     # writes output/index.html — open it in a browser
   ```
   Or just run `make site`. The site has four tabs: **Leaderboard** (the bracket standings),
   **Bracket** (connected tree of the real tournament, with flags), **Predictions** (each
   entrant's bracket vs. reality), and **About**.

## Layout

```
config/models.json        model roster (OpenRouter ids, display names, enabled flags)
data/fixtures/<R>.json     the real fixtures (R32 = the qualifiers you slot in)
data/results/<R>.json      the real outcomes you enter as rounds finish
data/bracket.json          knockout wiring (which slots feed which) for scoring + the tree
data/predictions/bracket/*.json  one-shot full-bracket predictions (one per model + Nadiem)
output/index.html          the generated public website (leaderboard · bracket · predictions · about)
local/enter.html           PRIVATE point-and-click bracket entry (git-ignored, never deployed)
src/      collect.py · score.py · advance.py · fetch_results.py · site.py · enter.py · scaffold.py · models.py · prompts.py · common.py · flags.py
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
