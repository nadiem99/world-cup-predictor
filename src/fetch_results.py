"""Fetch finished 2026 World Cup knockout results from FotMob (deterministic).

Replaces the earlier LLM-based fetcher, which was too non-deterministic to
auto-publish (it both fabricated and under-reported the same match across runs).
This reads FotMob's public league page for the 2026 World Cup (league 77), pulls
the match list embedded in the page's __NEXT_DATA__ JSON, and for each
not-yet-recorded fixture whose two teams are known, copies the real full-time
score across — orienting it to our home/away and resolving the winner (penalty
shootouts via the match page's `whoLostOnPenalties`). No API key, no model,
standard library only.

  python -m src.fetch_results
  python -m src.fetch_results --dry-run    # print what would change; write nothing

Env:
  FOTMOB_MATCHES_URL    override the source page (default: the 2026 World Cup matches tab).
  REFRESH_SUMMARY_FILE  optional path; a one-line-per-match summary is written here for
                        the workflow to use as a commit-message body.
"""
import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

from .common import FIXTURES_DIR, RESULTS_DIR, ROUND_ORDER, load_json, save_json

FOTMOB_URL = "https://www.fotmob.com/leagues/77/matches/world-cup"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
# normalized FotMob team name -> normalized fixture name, for the few that differ
_ALIASES = {"usa": "unitedstates"}
DECIDED_BY = ("regulation", "extra_time", "penalties")
_BARE_CITATION = re.compile(r"^\s*\[?\d+\]?\s*$")
_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL)
_SCORE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def _norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    n = re.sub(r"[^a-z0-9]+", "", s.lower())
    return _ALIASES.get(n, n)


# ---------------------------------------------------------------------------
# Which fixtures still need a result
# ---------------------------------------------------------------------------
def pending_matches(fixtures_by_round, results_by_round, include_recorded=False):
    """Matches whose two teams are known.

    By default returns only those whose result isn't recorded yet (the nightly
    fill path). With include_recorded=True it returns every known-team fixture —
    used by --reconcile to re-check already-recorded matches against FotMob."""
    pend = []
    for rnd in ROUND_ORDER:
        fx = (fixtures_by_round.get(rnd) or {}).get("matches", [])
        res = {m.get("id"): m for m in (results_by_round.get(rnd) or {}).get("matches", [])}
        for m in fx:
            home, away = m.get("home"), m.get("away")
            if not home or not away:
                continue  # teams not determined yet (an earlier round is unfinished)
            r = res.get(m.get("id")) or {}
            recorded = r.get("home_goals") is not None and r.get("away_goals") is not None
            if recorded and not include_recorded:
                continue  # already recorded — fill path never overwrites
            pend.append({"id": m.get("id"), "round": rnd, "home": home, "away": away})
    return pend


# ---------------------------------------------------------------------------
# FotMob source
# ---------------------------------------------------------------------------
def _fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _next_data(html):
    m = _NEXT_DATA.search(html or "")
    if not m:
        raise ValueError("FotMob page did not contain __NEXT_DATA__")
    return json.loads(m.group(1))


def all_matches(data):
    return (((data.get("props") or {}).get("pageProps") or {})
            .get("fixtures") or {}).get("allMatches") or []


def knockout_finished(matches):
    """FotMob knockout matches that have finished, normalized to simple dicts.

    Knockout rounds carry non-numeric round ids (1/16, 1/8, 1/4, 1/2, bronze,
    final); the group stage uses "1"/"2"/"3", which we skip so a group game with
    the same two teams can never be mistaken for the knockout meeting."""
    out = []
    for mm in matches or []:
        if str(mm.get("round")).isdigit():
            continue
        st = mm.get("status") or {}
        if not st.get("finished"):
            continue
        home = (mm.get("home") or {}).get("name")
        away = (mm.get("away") or {}).get("name")
        score = _SCORE.match(str(st.get("scoreStr") or ""))
        if not home or not away or "/" in home or "/" in away or not score:
            continue  # undetermined slot (e.g. "Netherlands/Morocco") or no score
        reason = (st.get("reason") or {}).get("shortKey") or (st.get("reason") or {}).get("short")
        out.append({"home": home, "away": away,
                    "hg": int(score.group(1)), "ag": int(score.group(2)),
                    "reason": str(reason or ""),
                    "url": "https://www.fotmob.com" + (mm.get("pageUrl") or "")})
    return out


def _decided_by(reason):
    r = str(reason).lower()
    if "pen" in r:
        return "penalties"
    if "extra" in r or "aet" in r:
        return "extra_time"
    return "regulation"


def _penalty_winner(match_url, fetch=_fetch):
    """Resolve a shootout winner from a match page via header.status.whoLostOnPenalties.

    Returns the winning team's FotMob name, or None if not determinable."""
    try:
        hdr = (((_next_data(fetch(match_url)).get("props") or {}).get("pageProps") or {})
               .get("header")) or {}
    except Exception:
        return None
    teams = hdr.get("teams") or []
    lost = (hdr.get("status") or {}).get("whoLostOnPenalties")
    if not lost or len(teams) != 2:
        return None
    ln = _norm(lost)
    for i, t in enumerate(teams):
        if _norm(t.get("name")) == ln or str(t.get("id")) == str(lost):
            return teams[1 - i].get("name")  # the other team won
    return None


def fotmob_results(pending, finished, fetch=_fetch):
    """Map FotMob finished knockout matches onto our pending fixtures.

    Returns (results, unresolved); results are dicts shaped for apply_results."""
    by_pair = {frozenset((_norm(f["home"]), _norm(f["away"]))): f for f in finished}
    results, unresolved = [], []
    for p in pending:
        f = by_pair.get(frozenset((_norm(p["home"]), _norm(p["away"]))))
        if not f:
            continue
        if _norm(p["home"]) == _norm(f["home"]):
            hg, ag = f["hg"], f["ag"]
        else:
            hg, ag = f["ag"], f["hg"]            # orient the score to our home/away
        if hg == ag:                              # a knockout draw was settled on penalties
            win_name = _penalty_winner(f["url"], fetch=fetch)
            winner = (p["home"] if win_name and _norm(win_name) == _norm(p["home"])
                      else p["away"] if win_name and _norm(win_name) == _norm(p["away"]) else None)
            if not winner:
                unresolved.append((p["id"], "drawn knockout — penalty winner not available yet"))
                continue
            decided = "penalties"
        else:
            winner = p["home"] if hg > ag else p["away"]
            decided = _decided_by(f["reason"])
            if decided == "penalties":            # a decisive score is never on penalties
                decided = "regulation"
        results.append({"id": p["id"], "home_goals": hg, "away_goals": ag,
                        "advances": winner, "decided_by": decided, "source": f["url"]})
    return results, unresolved


# ---------------------------------------------------------------------------
# Validation safety net + merge into the results files
# ---------------------------------------------------------------------------
def _bad_source(s):
    """True if the cited source is empty or a bare citation marker like '[10]'."""
    s = str(s or "").strip()
    return (not s) or bool(_BARE_CITATION.match(s))


def validate_result(r, pend):
    """Validate one result for pending match `pend`; the last line of defence
    against garbled data reaching the public leaderboard.

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


def apply_results(returned, pend_by_id, results_by_round):
    """Validate results and merge the valid ones into the results files (in place).

    Returns (changed_rounds:set, summary:list[str], skipped:list[(id, reason)])."""
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


def reconcile_results(returned, cand_by_id, results_by_round):
    """Make FotMob authoritative over already-recorded results too.

    Overwrites a recorded match only when FotMob disagrees with it, so the board
    always matches FotMob. Returns (changed_rounds, updated, confirmed, skipped)."""
    res_index = {}
    for rnd, data in results_by_round.items():
        for m in (data or {}).get("matches", []):
            res_index[m.get("id")] = (rnd, m)

    changed, updated, confirmed, skipped = set(), [], [], []
    for r in returned or []:
        mid = r.get("id") if isinstance(r, dict) else None
        pend = cand_by_id.get(mid)
        if not pend:
            skipped.append((mid, "not a candidate"))
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
        new = (hg, ag, _norm(winner), decided)
        cur = (match.get("home_goals"), match.get("away_goals"),
               _norm(match.get("advances")), match.get("decided_by"))
        if cur == new:
            confirmed.append(mid)
            continue
        match["home_goals"], match["away_goals"] = hg, ag
        match["advances"], match["decided_by"] = winner, decided
        changed.add(rnd)
        updated.append("%s: %s %d-%d %s — %s advances (%s)" % (
            mid, pend["home"], hg, ag, pend["away"], winner, decided))
    return changed, updated, confirmed, skipped


def _write_summary(summary):
    path = os.environ.get("REFRESH_SUMMARY_FILE")
    if not path:
        return
    body = "Nightly results refresh\n\n" + "\n".join(summary)
    try:
        Path(path).write_text(body, encoding="utf-8")
    except OSError as e:
        print("WARN: could not write summary file: %s" % e)


def main(argv=None):
    p = argparse.ArgumentParser(description="Fetch finished WC knockout results from FotMob.")
    p.add_argument("--dry-run", action="store_true", help="print what would change; write nothing")
    p.add_argument("--reconcile", action="store_true",
                   help="re-check ALL recorded knockout results against FotMob, not just blanks, "
                        "and correct any that disagree (FotMob is authoritative)")
    args = p.parse_args(argv)

    fixtures_by_round = {rnd: load_json(FIXTURES_DIR / ("%s.json" % rnd)) for rnd in ROUND_ORDER}
    results_by_round = {rnd: load_json(RESULTS_DIR / ("%s.json" % rnd)) for rnd in ROUND_ORDER}

    candidates = pending_matches(fixtures_by_round, results_by_round, include_recorded=args.reconcile)
    if not candidates:
        print("No recorded matches to reconcile yet." if args.reconcile
              else "No pending matches (everything with known teams is already recorded).")
        return 0
    print("%s %d match(es) against FotMob..." % (
        "Reconciling" if args.reconcile else "Checking", len(candidates)))

    url = os.environ.get("FOTMOB_MATCHES_URL") or FOTMOB_URL
    try:
        finished = knockout_finished(all_matches(_next_data(_fetch(url))))
    except Exception as e:
        print("WARN: could not read FotMob (%s); writing nothing this run." % e)
        return 0

    returned, unresolved = fotmob_results(candidates, finished)
    cand_by_id = {p["id"]: p for p in candidates}
    for mid, why in unresolved:
        print("  skip %s — %s" % (mid, why))

    if args.reconcile:
        changed, updated, confirmed, skipped = reconcile_results(returned, cand_by_id, results_by_round)
        for mid, why in skipped:
            print("  skip %s — %s" % (mid, why))
        print("  %d match(es) already matched FotMob." % len(confirmed))
        for line in updated:
            print("  CORRECTED %s" % line)
        if not updated:
            print("Board already matches FotMob — nothing to correct.")
            return 0
        if args.dry_run:
            print("\n[dry-run] %d match(es) would be corrected; no files written." % len(updated))
            return 0
        for rnd in changed:
            save_json(RESULTS_DIR / ("%s.json" % rnd), results_by_round[rnd])
        print("\nCorrected %d match(es) across %d round(s) from FotMob." % (len(updated), len(changed)))
        _write_summary(updated)
        return 0

    changed, summary, skipped = apply_results(returned, cand_by_id, results_by_round)
    for mid, why in skipped:
        print("  skip %s — %s" % (mid, why))
    if not summary:
        print("No newly-finished knockout matches to record.")
        return 0
    for line in summary:
        print("  recorded %s" % line)
    if args.dry_run:
        print("\n[dry-run] %d match(es) would be recorded; no files written." % len(summary))
        return 0
    for rnd in changed:
        save_json(RESULTS_DIR / ("%s.json" % rnd), results_by_round[rnd])
    print("\nRecorded %d match(es) across %d round(s)." % (len(summary), len(changed)))
    _write_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
