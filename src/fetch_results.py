"""Fetch finished 2026 World Cup knockout results via an OpenRouter web-search model.

Drives the nightly GitHub Actions refresh. Reads the fixtures and current results,
asks a web-search-capable model for the FINAL scores of any not-yet-recorded match
whose two teams are known, validates every answer against the fixtures, and writes
the confirmed ones into data/results/<ROUND>.json. Conservative by design: anything
the model will not confirm as finished is left untouched for a future run, and a
returned winner that isn't one of the match's two fixture teams is discarded.

  OPENROUTER_API_KEY=... python -m src.fetch_results
  OPENROUTER_API_KEY=... python -m src.fetch_results --dry-run   # change nothing

Env:
  RESULTS_FETCH_MODEL   OpenRouter model id (default perplexity/sonar-pro). Use a model
                        that ALWAYS searches the web and grounds its answer in sources —
                        a dedicated search model declines honestly when a match hasn't
                        finished, whereas a general model with an optional ':online' plugin
                        may skip the search and hallucinate a plausible-looking score.
  REFRESH_SUMMARY_FILE  optional path; a one-line-per-match summary (with sources) is
                        written here for the workflow to use as a commit-message body.
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .common import (
    FIXTURES_DIR, RESULTS_DIR, ROUND_LABELS, ROUND_ORDER,
    OpenRouter, extract_json, load_json, save_json,
)

DEFAULT_MODEL = "perplexity/sonar-pro"  # always web-searches; declines instead of hallucinating
DECIDED_BY = ("regulation", "extra_time", "penalties")
_BARE_CITATION = re.compile(r"^\s*\[?\d+\]?\s*$")  # e.g. "[10]" — a citation index, not a source


def _norm(s):
    return str(s or "").strip().lower()


def _bad_source(s):
    """True if the cited source is empty or a bare citation marker like '[10]'."""
    s = str(s or "").strip()
    return (not s) or bool(_BARE_CITATION.match(s))


def validate_result(r, pend):
    """Validate one model result for pending match `pend`; the last line of defence
    against fabricated/garbled data reaching the public leaderboard.

    Returns (winner, decided_by, home_goals, away_goals) or raises ValueError(reason).
    Enforces internal consistency: a level full-time score can only be settled by a
    penalty shootout, a decisive score never is, and the team that advances must be
    the higher-scoring side. Also requires a real (non-citation-marker) source.
    """
    try:
        hg, ag = int(r["home_goals"]), int(r["away_goals"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("non-integer goals")
    if hg < 0 or ag < 0:
        raise ValueError("negative goals")

    adv = _norm(r.get("advances"))
    if adv == _norm(pend["home"]):
        winner = pend["home"]            # store the fixture's exact spelling
    elif adv == _norm(pend["away"]):
        winner = pend["away"]
    else:
        raise ValueError("winner is not one of the two teams")

    decided = r.get("decided_by") if r.get("decided_by") in DECIDED_BY else "regulation"
    if hg == ag:
        if decided != "penalties":
            raise ValueError("level score must be decided by penalties")
    else:
        if decided == "penalties":
            raise ValueError("decisive score cannot be decided by penalties")
        higher = pend["home"] if hg > ag else pend["away"]
        if _norm(winner) != _norm(higher):
            raise ValueError("the team that advances must be the higher-scoring side")

    if _bad_source(r.get("source")):
        raise ValueError("missing or non-specific source")
    return winner, decided, hg, ag


def _utc_today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def pending_matches(fixtures_by_round, results_by_round):
    """Matches whose two teams are known but whose result isn't recorded yet."""
    pend = []
    for rnd in ROUND_ORDER:
        fx = (fixtures_by_round.get(rnd) or {}).get("matches", [])
        res = {m.get("id"): m for m in (results_by_round.get(rnd) or {}).get("matches", [])}
        for m in fx:
            home, away = m.get("home"), m.get("away")
            if not home or not away:
                continue  # teams not determined yet (an earlier round is unfinished)
            r = res.get(m.get("id")) or {}
            if r.get("home_goals") is not None and r.get("away_goals") is not None:
                continue  # already recorded — never overwrite
            pend.append({"id": m.get("id"), "round": rnd, "home": home, "away": away})
    return pend


def build_messages(pending, today):
    lines = ["%s — %s — %s vs %s" % (p["id"], ROUND_LABELS.get(p["round"], p["round"]),
                                     p["home"], p["away"]) for p in pending]
    system = (
        "You are a meticulous football-results checker for the 2026 FIFA World Cup. You report "
        "ONLY results you can verify from a specific, reliable web source. You never guess, never "
        "extrapolate, and never output a placeholder score. Declining to report a match is normal "
        "and expected — most of the time a given match has not been played yet."
    )
    user = (
        "Today is %s. Below are 2026 FIFA World Cup knockout matches we are tracking. Search the "
        "web and report a result for a match ONLY IF it has actually been played and finished.\n\n"
        "IMPORTANT: Many or all of these matches may NOT have been played yet. Treat 'no confirmed "
        "final score' as the normal, expected case. Do NOT guess, do NOT output placeholder or 0-0 "
        "scores, and do NOT include a match unless a specific reliable source reports its FINAL "
        "full-time result. Returning an empty list is the correct answer when nothing has finished.\n\n"
        "Matches (id — round — home vs away):\n%s\n\n"
        "Return ONLY a JSON object of this exact shape:\n"
        '{"results": [{"id": "<id>", "home_goals": <int>, "away_goals": <int>, '
        '"advances": "<team>", "decided_by": "regulation|extra_time|penalties", '
        '"source": "<full source URL>"}]}\n\n'
        "Rules:\n"
        "- Include a match ONLY if it has FINISHED and you can cite a specific source as a full URL.\n"
        "- home_goals/away_goals = full-time score after regulation + extra time, EXCLUDING penalty "
        "shootouts. If the score was level after extra time, set decided_by to \"penalties\".\n"
        "- A decisive score is decided_by \"regulation\" or \"extra_time\", never \"penalties\", and "
        'the "advances" team must be the higher-scoring side.\n'
        '- "advances" MUST be exactly one of the two team names given (verbatim). Use only the listed ids.\n'
        '- If nothing has a confirmed final score, return {"results": []}.'
        % (today, "\n".join(lines))
    )
    return system, user


def apply_results(returned, pend_by_id, results_by_round):
    """Validate model results and merge the valid ones into the results files.

    Mutates the passed results_by_round dicts in place (no IO). Returns
    (changed_rounds:set, summary:list[str], skipped:list[(id, reason)]).
    """
    changed, summary, skipped = set(), [], []
    res_index = {}
    for rnd, data in results_by_round.items():
        for m in (data or {}).get("matches", []):
            res_index[m.get("id")] = (rnd, m)

    for r in returned or []:
        mid = r.get("id") if isinstance(r, dict) else None
        pend = pend_by_id.get(mid)
        if not pend:
            skipped.append((mid, "not a pending match"))
            continue
        try:
            winner, decided, hg, ag = validate_result(r, pend)
        except ValueError as e:
            skipped.append((mid, str(e)))
            continue
        rnd, match = res_index.get(mid, (None, None))
        if not match:
            skipped.append((mid, "no results slot"))
            continue
        match["home_goals"], match["away_goals"] = hg, ag
        match["advances"], match["decided_by"] = winner, decided
        changed.add(rnd)
        summary.append("%s: %s %d-%d %s — %s advances (%s) [%s]" % (
            mid, pend["home"], hg, ag, pend["away"], winner, decided, r.get("source", "")))
    return changed, summary, skipped


def main(argv=None):
    p = argparse.ArgumentParser(description="Fetch finished WC knockout results via OpenRouter.")
    p.add_argument("--dry-run", action="store_true", help="print what would change; write nothing")
    p.add_argument("--today", default=None, help="override today's date (YYYY-MM-DD)")
    args = p.parse_args(argv)

    fixtures_by_round = {rnd: load_json(FIXTURES_DIR / ("%s.json" % rnd)) for rnd in ROUND_ORDER}
    results_by_round = {rnd: load_json(RESULTS_DIR / ("%s.json" % rnd)) for rnd in ROUND_ORDER}

    pending = pending_matches(fixtures_by_round, results_by_round)
    if not pending:
        print("No pending matches (everything with known teams is already recorded).")
        return 0
    print("Pending matches to check: %d" % len(pending))

    system, user = build_messages(pending, args.today or _utc_today())

    try:
        client = OpenRouter()
        model = os.environ.get("RESULTS_FETCH_MODEL") or DEFAULT_MODEL  # empty env -> default
        raw = client.chat(model, system, user, timeout=240)
        data = extract_json(raw)
    except SystemExit:
        raise  # missing API key etc. — surface loudly so setup problems are visible
    except Exception as e:
        print("WARN: results lookup failed (%s); writing nothing this run." % e)
        return 0

    returned = data.get("results") if isinstance(data, dict) else None
    pend_by_id = {p["id"]: p for p in pending}
    changed, summary, skipped = apply_results(returned or [], pend_by_id, results_by_round)

    for mid, why in skipped:
        print("  skip %s — %s" % (mid, why))
    if not summary:
        print("No confirmed finished matches this run.")
        return 0
    for line in summary:
        print("  recorded %s" % line)

    if args.dry_run:
        print("\n[dry-run] %d match(es) would be recorded; no files written." % len(summary))
        return 0

    for rnd in changed:
        save_json(RESULTS_DIR / ("%s.json" % rnd), results_by_round[rnd])
    print("\nRecorded %d match(es) across %d round(s)." % (len(summary), len(changed)))

    summary_path = os.environ.get("REFRESH_SUMMARY_FILE")
    if summary_path:
        body = "Nightly results refresh\n\n" + "\n".join(summary)
        try:
            Path(summary_path).write_text(body, encoding="utf-8")
        except OSError as e:
            print("WARN: could not write summary file: %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
