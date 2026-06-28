"""Scoring engine — one-shot bracket only.

Everyone (models + Nadiem) predicts the FULL bracket once, before the Round of 32.
As the real rounds play out you enter the results (data/results/<R>.json); each
prediction earns points for every team it correctly placed into a stage, weighted
by depth, plus champion/third bonuses. There is a single leaderboard.
"""
import sys

from .common import DATA_DIR, PRED_DIR, RESULTS_DIR, load_json, save_json

BRACKET_STAGE_POINTS = {"R16": 1, "QF": 2, "SF": 3, "F": 5}
CHAMPION_BONUS = 10
THIRD_BONUS = 3


def _norm(s):
    return str(s or "").strip().lower()


def _round_results(round_label):
    res = load_json(RESULTS_DIR / ("%s.json" % round_label))
    out = {}
    if not res:
        return out
    for m in res.get("matches", []):
        if m.get("home_goals") is not None and m.get("away_goals") is not None:
            out[m["id"]] = m
    return out


def _advancers(round_label):
    return {_norm(m.get("advances")) for m in _round_results(round_label).values()
            if m.get("advances")}


def actual_bracket():
    """Teams that actually reached each stage (derived from results)."""
    champ_set = _advancers("F")
    third_set = _advancers("TP")
    return {
        "R16": _advancers("R32"), "QF": _advancers("R16"),
        "SF": _advancers("QF"), "F": _advancers("SF"),
        "champion": next(iter(champ_set)) if champ_set else None,
        "third": next(iter(third_set)) if third_set else None,
    }


def compute_bracket():
    actual = actual_bracket()
    champion, third = actual["champion"], actual["third"]
    have_results = any(actual[s] for s in ("R16", "QF", "SF", "F")) or bool(champion)

    bdir = PRED_DIR / "bracket"
    rows = []
    if bdir.exists():
        for f in sorted(bdir.glob("*.json")):
            if f.name.endswith(".error.json"):
                continue
            pred = load_json(f) or {}
            rounds = pred.get("rounds", {})
            pts = 0
            detail = {}
            for stage, weight in BRACKET_STAGE_POINTS.items():
                got = sum(1 for t in rounds.get(stage, []) if _norm(t) in actual[stage])
                detail[stage] = got * weight
                pts += got * weight
            if champion and _norm(rounds.get("champion")) == _norm(champion):
                detail["champion"] = CHAMPION_BONUS
                pts += CHAMPION_BONUS
            if third and _norm(rounds.get("third")) == _norm(third):
                detail["third"] = THIRD_BONUS
                pts += THIRD_BONUS
            rows.append({"slug": pred.get("slug", f.stem), "name": pred.get("name", f.stem),
                         "points": pts, "detail": detail,
                         "champion_pick": rounds.get("champion", "")})
        rows.sort(key=lambda x: (-x["points"], x["name"].lower()))
    return {"rows": rows, "have_results": have_results}


def get_scores():
    return {"bracket": compute_bracket()}


def _print_bracket(bracket):
    if not bracket["rows"]:
        print("No bracket predictions yet.")
        return
    print("LEADERBOARD  (%s)" %
          ("scored" if bracket["have_results"] else "no knockout results yet"))
    print("%-4s %-18s %6s  %s" % ("#", "entrant", "pts", "champion pick"))
    for i, r in enumerate(bracket["rows"], 1):
        print("%-4d %-18s %6d  %s" % (i, r["name"][:18], r["points"], r["champion_pick"]))


def main(argv=None):
    scores = get_scores()
    _print_bracket(scores["bracket"])
    save_json(DATA_DIR / "scores.json", scores)
    print("\nWrote %s" % (DATA_DIR / "scores.json"))


if __name__ == "__main__":
    main(sys.argv[1:])
