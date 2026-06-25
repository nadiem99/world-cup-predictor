"""Scoring engine.

Per-round contest (main leaderboard) — NON-STACKING:
  * exact regulation/extra-time scoreline -> EXACT_POINTS (3)
  * else correct advancing team           -> RESULT_POINTS (1)
  * else                                   -> 0
  (Penalty shootouts are ignored for the scoreline. Note: a 1-1 that you nailed but
  picked the wrong shootout winner still scores the exact 3 here — flip the order in
  _score_match if you'd rather require the advancer to also be correct.)

One-shot bracket (bonus leaderboard): points for each team correctly predicted to
reach a stage, weighted by depth, plus champion/third bonuses.
"""
import sys

from .common import (
    DATA_DIR, PRED_DIR, RESULTS_DIR, ROUND_ORDER, load_json, save_json,
)

EXACT_POINTS = 3   # exact regulation/extra-time scoreline
RESULT_POINTS = 1  # correct advancer only (scoreline wrong)

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


def _score_match(pred, result):
    """Return (points, advancer_correct, scoreline_correct). Non-stacking: 3 / 1 / 0."""
    advancer_correct = _norm(pred.get("advances")) == _norm(result.get("advances"))
    scoreline_correct = (
        int(pred["home_goals"]) == int(result["home_goals"])
        and int(pred["away_goals"]) == int(result["away_goals"])
    )
    if scoreline_correct:
        pts = EXACT_POINTS
    elif advancer_correct:
        pts = RESULT_POINTS
    else:
        pts = 0
    return pts, advancer_correct, scoreline_correct


def _score_round(round_label, results_by_id):
    out = {}
    pred_dir = PRED_DIR / round_label
    if not pred_dir.exists():
        return out
    for f in sorted(pred_dir.glob("*.json")):
        if f.name.endswith(".error.json"):
            continue
        pred = load_json(f) or {}
        slug = pred.get("slug", f.stem)
        points = exact = correct = scored = 0
        for p in pred.get("predictions", []):
            r = results_by_id.get(p.get("id"))
            if not r:
                continue
            scored += 1
            pts, adv_ok, sc_ok = _score_match(p, r)
            points += pts
            correct += 1 if adv_ok else 0
            exact += 1 if sc_ok else 0
        out[slug] = {"name": pred.get("name", slug), "points": points,
                     "exact": exact, "correct": correct, "scored": scored}
    return out


def compute_main():
    rounds_present = [r for r in ROUND_ORDER if _round_results(r)]
    per_round = {r: _score_round(r, _round_results(r)) for r in rounds_present}
    names = {}
    for r in rounds_present:
        for slug, d in per_round[r].items():
            names.setdefault(slug, d["name"])
    rows = []
    for slug, name in names.items():
        total = {"slug": slug, "name": name, "points": 0, "exact": 0,
                 "correct": 0, "scored": 0, "by_round": {}}
        for r in rounds_present:
            d = per_round[r].get(slug)
            if not d:
                continue
            for k in ("points", "exact", "correct", "scored"):
                total[k] += d[k]
            total["by_round"][r] = d["points"]
        rows.append(total)
    rows.sort(key=lambda x: (-x["points"], -x["exact"], x["name"].lower()))
    return {"rounds": rounds_present, "rows": rows}


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
    return {"main": compute_main(), "bracket": compute_bracket()}


def _print_main(main):
    if not main["rows"]:
        print("No scored matches yet (need predictions AND results).")
        return
    print("MAIN LEADERBOARD  (rounds: %s)" % ", ".join(main["rounds"]))
    print("%-4s %-18s %6s %6s %8s %7s" %
          ("#", "model", "pts", "exact", "results", "played"))
    for i, r in enumerate(main["rows"], 1):
        print("%-4d %-18s %6d %6d %8d %7d" %
              (i, r["name"][:18], r["points"], r["exact"], r["correct"], r["scored"]))


def _print_bracket(bracket):
    if not bracket["rows"]:
        print("\nNo bracket predictions yet.")
        return
    print("\nBRACKET BONUS  (%s)" %
          ("scored" if bracket["have_results"] else "no knockout results yet"))
    print("%-4s %-18s %6s  %s" % ("#", "model", "pts", "champion pick"))
    for i, r in enumerate(bracket["rows"], 1):
        print("%-4d %-18s %6d  %s" % (i, r["name"][:18], r["points"], r["champion_pick"]))


def main(argv=None):
    scores = get_scores()
    _print_main(scores["main"])
    _print_bracket(scores["bracket"])
    save_json(DATA_DIR / "scores.json", scores)
    print("\nWrote %s" % (DATA_DIR / "scores.json"))


if __name__ == "__main__":
    main(sys.argv[1:])
