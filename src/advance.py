"""Propagate knockout results into the next round's fixtures.

Scoring reads only `data/results/<R>.json` (the `advances` field), but the
Bracket-tab tree on the site reads `data/fixtures/<R>.json`, which start blank
for every round after the Round of 32. This fills them from what actually
happened: each R32 winner flows into the R16 fixtures, each R16 winner into the
QF fixtures, …, and the two beaten semi-finalists into the third-place match —
using the wiring already declared in `data/bracket.json`.

Deterministic and idempotent: a slot is filled only once its feeder match is
decided, an already-set team is never blanked out, and kickoff/venue are left
alone. Run it after entering results, before scoring/building the site:

  python -m src.advance            # propagate; print what it filled
  python -m src.advance --quiet    # silent (for scripts/CI)
"""
import argparse
import sys

from .common import DATA_DIR, FIXTURES_DIR, RESULTS_DIR, load_json, save_json

# Downstream fixture rounds in fill order. SF is filled before TP so the
# third-place match can read the (just-filled) semi-final line-ups to work out
# who lost. R32 is the manually-seeded opening round and is never a target.
ROUND_SEQUENCE = ["R16", "QF", "SF", "F", "TP"]


def _norm(s):
    return str(s or "").strip().lower()


def _index(directory, keep):
    """Map match id -> match dict across every <R>.json in a directory.

    `keep` selects the subset of fields we care about (kept for clarity only;
    the whole match dict is stored)."""
    idx = {}
    for path in sorted(directory.glob("*.json")):
        data = load_json(path) or {}
        for m in data.get("matches", []):
            if m.get("id"):
                idx[m["id"]] = m
    return idx


def _advancer(match_id, results):
    """Team that went through in a decided match (or '' if not decided)."""
    return (results.get(match_id) or {}).get("advances") or ""


def _loser(match_id, results, fixtures):
    """Beaten team of a decided match — needs its fixture line-up to identify."""
    adv = _norm(_advancer(match_id, results))
    fx = fixtures.get(match_id) or {}
    home, away = fx.get("home"), fx.get("away")
    if not adv or not home or not away:
        return ""
    if adv == _norm(home):
        return away
    if adv == _norm(away):
        return home
    return ""  # 'advances' matches neither side — leave it for a human to fix


def _feeder_team(feeder, results, fixtures):
    """Resolve a wiring token ('R32-1' or 'SF-1-loser') to a team name."""
    if feeder.endswith("-loser"):
        return _loser(feeder[: -len("-loser")], results, fixtures)
    return _advancer(feeder, results)


def compute_targets(bracket):
    """Downstream fixture id -> (home_feeder, away_feeder) tokens."""
    targets = {}
    for slot_id, feeders in (bracket.get("slots") or {}).items():
        if isinstance(feeders, list) and len(feeders) == 2:
            targets[slot_id] = (feeders[0], feeders[1])
    tp = bracket.get("third_place") or {}
    if tp.get("id") and len(tp.get("feeders", [])) == 2:
        targets[tp["id"]] = (tp["feeders"][0], tp["feeders"][1])
    return targets


def advance(quiet=False):
    """Fill downstream fixtures from results. Returns a list of (id, side, team)."""
    bracket = load_json(DATA_DIR / "bracket.json") or {}
    results = _index(RESULTS_DIR, ("advances",))
    fixtures = _index(FIXTURES_DIR, ("home", "away"))
    targets = compute_targets(bracket)

    by_round = {}
    for fid, feeders in targets.items():
        by_round.setdefault(fid.split("-")[0], {})[fid] = feeders

    filled = []
    for rnd in ROUND_SEQUENCE:
        if rnd not in by_round:
            continue
        path = FIXTURES_DIR / ("%s.json" % rnd)
        data = load_json(path)
        if not data:
            continue
        match_by_id = {m.get("id"): m for m in data.get("matches", [])}
        changed = False
        for fid, (home_feeder, away_feeder) in by_round[rnd].items():
            m = match_by_id.get(fid)
            if not m:
                continue
            for side, feeder in (("home", home_feeder), ("away", away_feeder)):
                team = _feeder_team(feeder, results, fixtures)
                if team and _norm(m.get(side)) != _norm(team):
                    m[side] = team
                    fixtures[fid] = m  # keep index fresh for the TP loser lookup
                    changed = True
                    filled.append((fid, side, team))
        if changed:
            save_json(path, data)

    if not quiet:
        for fid, side, team in filled:
            print("  %-7s %-5s -> %s" % (fid, side, team))
        print("Filled %d slot(s)." % len(filled) if filled
              else "Nothing to propagate (no newly-decided feeder matches).")
    return filled


def main(argv=None):
    p = argparse.ArgumentParser(description="Propagate results into next-round fixtures.")
    p.add_argument("--quiet", action="store_true", help="suppress per-slot output")
    args = p.parse_args(argv)
    advance(quiet=args.quiet)


if __name__ == "__main__":
    main(sys.argv[1:])
