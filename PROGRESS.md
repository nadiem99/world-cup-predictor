# World Cup 2026 Predictor — Project Status

_Last updated: 2026-06-28_

A fun benchmark comparing how well AI models — and **Nadiem** — predict the **2026 FIFA
World Cup knockout stage**. Everyone calls the **full bracket once** before the Round of 32;
brackets are scored against real results and ranked on a single static leaderboard.

- **Repo:** https://github.com/nadiem99/world-cup-predictor
- **Live site:** https://nadiem99.github.io/world-cup-predictor/ (auto-deploys on every push to `main`)

## ⏱️ Key dates
- **Group stage finalizes:** ~June 27, 2026
- **Round of 32 kicks off:** Sunday, June 28, 2026
- **Final:** July 19, 2026
- **Hard deadline:** the one-shot brackets must be collected **before June 28**.

## ✅ Decisions locked in
- **Collection:** OpenRouter API (one key reaches Claude, OpenAI, Gemini, Qwen, and
  open-source models).
- **Single contest (one-shot bracket):** everyone (models + Nadiem) calls the **full
  bracket once**, before R32, all the way to the champion. No per-round re-picking — that
  contest was removed 2026-06-28 to simplify. One leaderboard.
- **Scoring:** points per team correctly predicted to reach a stage — R16 **+1** / QF
  **+2** / SF **+3** / Final **+5** — champion **+10**, third **+3**. Highest total wins.
- **Deliverable:** Python (stdlib only, no deps) + JSON data + a single self-contained
  static HTML site. Human competitor is **Nadiem**.

## ✅ Done so far

| Area | What | Commit |
|---|---|---|
| Core tool | `collect` · `score` · `site` · `models` · `prompts` · `common` | `beb4ac0` |
| Reliability | request retries/backoff, parallel collection (`--workers`), JSON mode, offline `collect estimate` | `296580b` |
| Tests + CI | stdlib `unittest` suite + GitHub Actions CI (Python 3.9 & 3.12) | `a19837f` |
| Scaffolding | `scaffold` tool, R16/QF/SF/TP/F templates, `data/bracket.json` wiring map | `64f70fc` |
| Deploy | GitHub Pages workflow, `Makefile`, `docs/DEPLOY.md` | `32fdf5c` |
| Site polish | connected bracket tree, sortable leaderboard + sparklines, About tab, mobile | `998c42d` |
| Docs | README updated for all tooling | `d967db3` |
| Bracket data | R32 populated with **projected** matchups (later superseded) | `d3ec05a` |
| Bracket structure | **R32→R16 adjacency confirmed** vs official FIFA 2026 bracket; R32 slots re-laid in official order (match #73–88) with group-position descriptors; `bracket.json` wiring verified | `6c37170` |
| Site restyle | editorial **serif** theme, warm espresso palette, scroll-reveal + hover animations | `b63c0da` |
| **Published** | public repo + GitHub Pages **live** (CI + deploy green) | live |
| Model API wiring | per-model overrides, generalized HTTP-400 fallback, `models ping` smoke test, +8 tests | `398d4c1` |
| Flags + private input | country flag images in the bracket; local-only `enter.html` guided picker (git-ignored, never deployed), `make enter` | _recent_ |
| R32 finalized | real 32 qualifiers slotted from the official bracket (cross-checked Wikipedia + CBS) | _recent_ |
| Simplified to one-shot | removed the per-round contest entirely; the **one-shot bracket is the single scored leaderboard** for models + Nadiem (`score`/`collect`/`site`/`enter` trimmed, docs + tests updated) | _this change_ |

## 📋 Runbook — operational steps

### A. Finalize the R32 bracket (~June 27, once all 12 groups end)
The 32 qualifiers (12 winners, 12 runners-up, 8 best third-placed) are now known.
1. **Get the official slotting.** From the official FIFA bracket, note which teams fill
   each match **#73–88**. The 8 third-placed teams are assigned to specific matches by
   FIFA's best-thirds table — use the **official** assignment, don't guess.
2. **Fill the teams** in [`data/fixtures/R32.json`](data/fixtures/R32.json): replace each
   match's `home`/`away` placeholders (e.g. `"Winner E"`, `"3rd A/B/C/D/F"`) with the real
   teams. Each match's `match_no` + `slot` tell you exactly which group-position goes
   there. **Keep `id`, `match_no`, `slot`, and the match order unchanged** — the bracket
   tree and `data/bracket.json` wiring depend on it. Optionally fill `kickoff`/`venue`.
3. **Pick canonical team names and stay consistent** (e.g. always `"United States"`, never
   sometimes `"USA"`). The same strings are used in results and matched against model
   replies, case-insensitively.
4. **Verify:** `make site`, open the Bracket tab, confirm real teams land in the right
   slots and the halves look right. Then commit + push (auto-redeploys).

### B. Collect the one-shot brackets (before June 28 kickoff)
0. `.env` has your key. Validate the roster: `python -m src.models check` (ids exist) **and**
   `python -m src.models ping` (each actually responds). Fix or `"enabled": false` any FAIL.
1. Cost ballpark: `python -m src.collect estimate`.
2. **Models' brackets — must be before R32 kicks off:** `python -m src.collect bracket`.
3. **Nadiem's bracket:** either the **private web tool** `make enter` (builds `local/enter.html`,
   a guided picker that downloads `nadiem.json` ready to drop into `data/predictions/bracket/`)
   — or the CLI `python -m src.collect me`. The web tool is **local-only** (git-ignored, never
   deployed); the public site stays read-only for everyone else.
4. `make site`, then commit + push. (`data/predictions/` is committed — not gitignored — so
   the public leaderboard shows them.)

### C. Each knockout round during the tournament (R16 → Final)
No new predictions — the brackets are already locked. Just record what happened so the
brackets get scored and the tree fills in:
1. Enter that round's fixtures (the two teams per match) in `data/fixtures/<R>.json` so the
   bracket tree shows the column — `python -m src.scaffold round <R>` makes blank stubs.
2. As matches finish, enter outcomes in `data/results/<R>.json` (`home_goals`/`away_goals`/
   `advances`/`decided_by`) using the same match ids. Only matches with goals are scored.
3. `make site`, commit + push to redeploy. Repeat for R16, QF, SF, TP (third place), F.

## 🔌 Model API wiring
- **One OpenRouter key** reaches every model; ids + optional overrides live in
  [`config/models.json`](config/models.json).
- **`OpenRouter.chat()`** ([src/common.py](src/common.py)): retries 429/5xx + timeouts with
  capped exponential backoff (honours `Retry-After`); requests JSON via `response_format`;
  on an **HTTP 400** it drops optional features one at a time (`response_format`, then
  `temperature`) and retries — so a model that rejects either still succeeds.
- **Per-model overrides** (all optional, merged by `model_kwargs()`): `"json_mode": false`,
  `"temperature": 1` (e.g. reasoning models that require the default), `"params": {"max_tokens":
  6000, "provider": {...}}` (merged verbatim into the request).
- **`python -m src.models ping`** calls every model with a 1-token prompt and reports
  ok/latency/error — the real wiring test. Run it after adding the key, and again whenever
  you change ids. `collect … --workers N` controls parallelism (default 6).

## 🔜 Still to do / open questions
- ✅ **Setup complete** — key + $10 credits added; all **24/24** model ids validated and
  responding live (`models ping` all-green, incl. reasoning models — no overrides needed).
- ✅ **R32 teams finalized** (2026-06-28) — real 32 teams slotted into `data/fixtures/R32.json`
  from the official bracket (Wikipedia knockout-stage + CBS Sports, cross-checked; all 12
  winners + 12 runners-up + 8 best-thirds from groups B/D/E/F/I/J/K/L). Site rebuilt; flags live.
- ⚠️ **Collect the brackets NOW** — must be before the Jun 28 R32 kickoff — Runbook B
  (`collect bracket` for the models, `make enter` / `collect me` for Nadiem). This is the
  urgent remaining step.
- **Roster size** — all 24 enabled; ~**$2–5** estimated total, so keeping all is fine. The
  lineup mixes Gemini 3.1 Pro with Gemini 2.5 Pro/Flash — modernize if you prefer.
- _(Optional)_ rotate the API key (it was shared in chat); regenerate at
  https://openrouter.ai/keys and re-stage `.env`.

## 🔧 Quick command reference
```bash
make site                            # score predictions + build output/index.html
make serve                           # preview at http://localhost:8000
make enter                           # build + open the PRIVATE local picks tool (not deployed)
make test                            # run the unit-test suite
python -m src.models check           # validate model ids exist (needs key)
python -m src.models ping            # live: call every model, report ok/latency (needs key)
python -m src.collect estimate       # offline cost ballpark (no key)
python -m src.collect bracket        # one-shot full bracket, all models
python -m src.collect me             # enter Nadiem's bracket (CLI; or use `make enter`)
git push                             # redeploys the live site automatically
```

## 🗂️ Repo layout
```
config/models.json            24-model roster + per-model overrides + Nadiem
data/fixtures/<R>.json         fixtures you enter per round (R32 = official slots)
data/results/<R>.json          outcomes you enter per round
data/bracket.json              knockout wiring (verified vs official FIFA bracket)
data/predictions/...           collected predictions (committed → shown on site)
src/                           collect · score · site · enter · scaffold · models · prompts · common · flags
local/enter.html               PRIVATE picks tool (git-ignored, built by `make enter`, never deployed)
tests/                         stdlib unittest suite
.github/workflows/             ci.yml + deploy-pages.yml
Makefile · docs/DEPLOY.md      build shortcuts + publishing
output/index.html              generated site (git-ignored; built by the deploy workflow)
```
