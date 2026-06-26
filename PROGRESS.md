# World Cup 2026 Predictor — Project Status

_Last updated: 2026-06-25_

A fun benchmark comparing how well AI models — and **Nadiem** — predict the **2026 FIFA
World Cup knockout rounds**. Models are queried via OpenRouter, scored against real
results, and ranked on a static leaderboard site. Intended to be shared publicly.

## ⏱️ Key dates
- **Group stage finalizes:** ~June 27, 2026
- **Round of 32 kicks off:** Sunday, June 28, 2026 (opener: South Africa vs Canada, LA)
- **Final:** July 19, 2026
- **Hard deadline:** baseline predictions (one-shot bracket + R32) must be collected
  **before June 28**.

## ✅ Decisions locked in
- **Collection:** OpenRouter API (one key reaches Claude, OpenAI, Gemini, Qwen, and
  open-source models).
- **Two contests:** (1) **per-round** — models re-predict each round from the real
  fixtures (the main leaderboard); (2) **one-shot bracket** — a full bracket called once
  before R32 (bonus board).
- **Scoring (non-stacking, per match):** exact regulation/ET scoreline = **3**, else
  correct advancing team = **1**, else 0. Bracket bonus: reach R16 **+1** / QF **+2** /
  SF **+3** / Final **+5** per correct team, champion **+10**, third **+3**.
- **Deliverable:** Python (stdlib only, no deps) + JSON data + a single self-contained
  static HTML site. Human competitor is **Nadiem**.

## ✅ Done so far

Built, tested, and committed (8 commits on `main`):

| Area | What | Commit |
|---|---|---|
| Core tool | `collect` · `score` · `site` · `models` · `prompts` · `common` | `beb4ac0` |
| Reliability | request retries/backoff, parallel collection (`--workers`), JSON mode, offline `collect estimate` cost command | `296580b` |
| Tests + CI | 32-test stdlib `unittest` suite + GitHub Actions CI (Python 3.9 & 3.12) | `a19837f` |
| Scaffolding | `scaffold` tool, R16/QF/SF/TP/F templates, `data/bracket.json` wiring map | `64f70fc` |
| Deploy | GitHub Pages workflow, `Makefile`, `docs/DEPLOY.md` | `32fdf5c` |
| Site polish | connected bracket tree, sortable leaderboard + per-round sparklines, About tab, mobile, "Nadiem" rename | `998c42d` |
| Docs | README updated for all tooling | `d967db3` |
| Bracket data | R32 populated with **projected** matchups (provisional, Jun 25) | `d3ec05a` |
| Bracket structure | **R32→R16 adjacency confirmed** against official FIFA 2026 bracket; R32 slots re-laid in official order (match #73–88) with group-position descriptors; `bracket.json` wiring verified correct | _uncommitted_ |

Also done (not committed — these are throwaway/generated):
- **24-model roster** spanning 13 labs in `config/models.json` (Anthropic, OpenAI, Google,
  xAI, DeepSeek, Qwen, Meta, Mistral, Moonshot, Zhipu, MiniMax, Amazon, Cohere) + Nadiem.
- **Mock-data preview** built to `output/index.html` so the look/feel of the populated
  leaderboard, bracket tree, and predictions views could be confirmed.

### The site (4 tabs)
- **Leaderboard** — sortable columns, per-round sparklines, per-round / bracket-bonus toggle.
- **Bracket** — connected knockout tree with live scores; model selector overlays any
  model's one-shot bracket (green = team that actually reached that stage).
- **Predictions** — browse any model's picks for any round or the baseline bracket.
- **About** — scoring methodology.

## 🔜 Work still to do

### Before June 28 (setup + baseline collection)
1. **Add the OpenRouter key** — `cp .env.example .env`, paste key.
2. **Validate model IDs** — `python -m src.models check` (the 24 IDs are best-guess for
   mid-2026; fix or disable any flagged MISSING). _Needs the key._
3. **Fill in R32 teams** — once the group stage ends (~Jun 27), replace the
   group-position placeholders in `data/fixtures/R32.json` (`Winner E`, `3rd A/B/C/D/F`, …)
   with the confirmed teams. Each match carries its FIFA `match_no` and a `slot` descriptor
   telling you exactly which group-position belongs there — **keep the ids and order
   unchanged** (the bracket tree depends on it).
4. ~~Confirm R32→R16 adjacency against the official FIFA bracket~~ — **DONE.** Verified
   against the official 2026 knockout bracket; R32 slots are now in official "leaf" order so
   `data/bracket.json`'s sequential wiring is exactly correct (see `r32_slots` in that file).
5. **Collect the baseline** — `python -m src.collect bracket` and
   `python -m src.collect round R32` (all models), plus
   `python -m src.collect me bracket` / `me round R32` for Nadiem's picks.

### During the tournament (each round)
6. **Per round:** scaffold/enter fixtures, `collect round <R>` + `me round <R>` before
   kickoff, enter results in `data/results/<R>.json` as matches finish.
7. **Rebuild + publish:** `make site` (score + build), then commit/push to redeploy.

### Nice-to-haves / open questions
- **Visual sign-off** on the look (palette, columns, bracket connectors, title) — open
  `output/index.html` and note any tweaks.
- **Publish** to GitHub Pages (create repo, enable Pages → GitHub Actions; see
  `docs/DEPLOY.md`).
- **Roster size** — confirm whether to keep all 24 models or trim the priciest
  (Opus, Grok 4, Gemini 3 Pro, o4-mini, R1) to cut cost.
- **Cost** — estimated **~$2–5** total for the whole tournament across 24 models
  (under ~$10 worst case); verify empirically after the first real collection via the
  OpenRouter activity page.

## 🔧 Quick command reference
```bash
make site            # score predictions + build output/index.html
make serve           # preview at http://localhost:8000
make test            # run the 32-test suite
python -m src.models check          # validate model ids (needs key)
python -m src.collect estimate all  # offline cost ballpark (no key)
python -m src.scaffold all          # (re)create round templates
python -m src.collect round R32     # collect a round from all models
python -m src.collect me round R32  # enter Nadiem's picks
```

## 🗂️ Repo layout
```
config/models.json           24-model roster + Nadiem
data/fixtures/<R>.json        fixtures you enter per round (R32 = projected)
data/results/<R>.json         outcomes you enter per round
data/bracket.json             knockout wiring for the tree
data/predictions/...          collected predictions (per round + bracket)
src/                          collect · score · site · scaffold · models · prompts · common
tests/                        stdlib unittest suite
.github/workflows/            ci.yml + deploy-pages.yml
Makefile · docs/DEPLOY.md     build shortcuts + publishing
output/index.html             generated site (git-ignored)
```
