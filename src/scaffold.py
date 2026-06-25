"""Scaffold empty fixture + result template files for knockout rounds.

  python -m src.scaffold round R16            # 8 blank R16 fixtures + results
  python -m src.scaffold round QF --matches 4
  python -m src.scaffold all                  # R16, QF, SF, TP, F (skips R32; never overwrites)
  python -m src.scaffold round R16 --force    # overwrite even if it already has data

Never overwrites a file that already contains real data unless --force is given,
so it is safe to run after you have started filling rounds in.
"""
import argparse
import sys

from .common import FIXTURES_DIR, RESULTS_DIR, ROUND_LABELS, load_json, save_json

DEFAULT_MATCHES = {"R32": 16, "R16": 8, "QF": 4, "SF": 2, "TP": 1, "F": 1}

FIXTURE_NOTE = ("Fill in each match: home/away set the score orientation used everywhere; "
                "kickoff/venue are optional. Keep the generated ids.")
RESULT_NOTE = ("Fill in each match as it finishes. home_goals/away_goals = score at the end of "
               "regulation+extra time (NOT including a penalty shootout). 'advances' = the team "
               "that goes through. 'decided_by' is one of regulation|extra_time|penalties. "
               "Only matches with non-null goals are scored.")


def _has_real_data(path):
    """True if the file exists and any match looks filled in (not a blank template)."""
    data = load_json(path)
    if not data:
        return False
    for m in data.get("matches", []):
        if (m.get("home") or m.get("away") or m.get("advances")
                or m.get("home_goals") is not None or m.get("away_goals") is not None):
            return True
    return False


def _fixture_template(label, n):
    return {
        "round": label,
        "label": ROUND_LABELS.get(label, label),
        "_note": FIXTURE_NOTE,
        "matches": [{"id": "%s-%d" % (label, i), "home": "", "away": "",
                     "kickoff": "", "venue": ""} for i in range(1, n + 1)],
    }


def _result_template(label, n):
    return {
        "round": label,
        "_note": RESULT_NOTE,
        "matches": [{"id": "%s-%d" % (label, i), "home_goals": None, "away_goals": None,
                     "advances": "", "decided_by": "regulation"} for i in range(1, n + 1)],
    }


def scaffold_round(label, n=None, force=False):
    if label == "R32" and not force:
        print("  skip   R32 is the manually-seeded opening round; use --force to scaffold it")
        return []
    n = n if n is not None else DEFAULT_MATCHES.get(label, 8)
    made = []
    for path, builder in ((FIXTURES_DIR / ("%s.json" % label), _fixture_template),
                          (RESULTS_DIR / ("%s.json" % label), _result_template)):
        if not force and _has_real_data(path):
            print("  skip   %s (already has data; use --force to overwrite)" % path.name)
            continue
        save_json(path, builder(label, n))
        made.append(path)
        print("  wrote  %s (%d matches)" % (path.name, n))
    return made


def scaffold_all(force=False):
    for label in ("R16", "QF", "SF", "TP", "F"):  # never R32 (already seeded)
        print("%s:" % label)
        scaffold_round(label, force=force)


def main(argv=None):
    p = argparse.ArgumentParser(description="Scaffold round fixture/result templates.")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("round", help="scaffold one round")
    pr.add_argument("round_label", help="e.g. R16, QF, SF, TP, F")
    pr.add_argument("--matches", type=int, default=None, help="number of match stubs")
    pr.add_argument("--force", action="store_true", help="overwrite existing data")
    pa = sub.add_parser("all", help="scaffold R16, QF, SF, TP, F (never R32)")
    pa.add_argument("--force", action="store_true", help="overwrite existing data")
    args = p.parse_args(argv)
    if args.cmd == "round":
        scaffold_round(args.round_label, args.matches, args.force)
    else:
        scaffold_all(args.force)


if __name__ == "__main__":
    main(sys.argv[1:])
