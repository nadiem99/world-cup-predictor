"""Collect predictions from models (via OpenRouter) or enter your own.

Usage (run from the project root):
  python -m src.collect round R32                 # all enabled models, Round of 32
  python -m src.collect round R32 --only gpt-5,qwen3-max
  python -m src.collect bracket                   # one-shot full-bracket, all models
  python -m src.collect bracket --only claude-opus-4.8
  python -m src.collect me round R32              # enter YOUR picks for a round
  python -m src.collect me bracket                # enter YOUR full-bracket picks
"""
import argparse
import sys
from datetime import datetime, timezone

from . import prompts
from .common import (
    FIXTURES_DIR, PRED_DIR, OpenRouter, enabled_models, load_json,
    load_models_config, save_json,
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _select(cfg, only):
    models = enabled_models(cfg)
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        models = [m for m in models if m["slug"] in wanted]
        missing = wanted - {m["slug"] for m in models}
        if missing:
            print("warning: unknown slug(s): %s" % ", ".join(sorted(missing)))
    return models


def _load_fixtures(round_label):
    path = FIXTURES_DIR / ("%s.json" % round_label)
    fx = load_json(path)
    if not fx or not fx.get("matches"):
        raise SystemExit(
            "No fixtures at %s. Create it first (see README / data/fixtures)." % path
        )
    return fx


def collect_round(round_label, only=None):
    fx = _load_fixtures(round_label)
    matches = fx["matches"]
    label = fx.get("label", round_label)
    client = OpenRouter()
    models = _select(load_models_config(), only)
    print("Collecting %s predictions from %d models...\n" % (label, len(models)))
    for m in models:
        out_path = PRED_DIR / round_label / ("%s.json" % m["slug"])
        try:
            raw = client.chat(m["id"], prompts.SYSTEM,
                              prompts.round_prompt(label, matches))
            preds = prompts.parse_round(raw, matches)
            save_json(out_path, {
                "round": round_label, "model": m["id"], "slug": m["slug"],
                "name": m["name"], "collected_at": _now(),
                "predictions": preds, "raw": raw,
            })
            print("  ok   %-18s %d/%d matches parsed" % (m["slug"], len(preds), len(matches)))
        except Exception as e:
            save_json(PRED_DIR / round_label / ("%s.error.json" % m["slug"]),
                      {"slug": m["slug"], "model": m["id"], "error": str(e),
                       "collected_at": _now()})
            print("  FAIL %-18s %s" % (m["slug"], e))
    print("\nSaved to %s" % (PRED_DIR / round_label))


def collect_bracket(only=None):
    fx = _load_fixtures("R32")
    matches = fx["matches"]
    client = OpenRouter()
    models = _select(load_models_config(), only)
    print("Collecting one-shot full-bracket predictions from %d models...\n" % len(models))
    for m in models:
        out_path = PRED_DIR / "bracket" / ("%s.json" % m["slug"])
        try:
            raw = client.chat(m["id"], prompts.SYSTEM, prompts.bracket_prompt(matches))
            rounds = prompts.parse_bracket(raw)
            save_json(out_path, {
                "model": m["id"], "slug": m["slug"], "name": m["name"],
                "collected_at": _now(), "rounds": rounds, "raw": raw,
            })
            print("  ok   %-18s champion: %s" % (m["slug"], rounds.get("champion") or "?"))
        except Exception as e:
            save_json(PRED_DIR / "bracket" / ("%s.error.json" % m["slug"]),
                      {"slug": m["slug"], "model": m["id"], "error": str(e),
                       "collected_at": _now()})
            print("  FAIL %-18s %s" % (m["slug"], e))
    print("\nSaved to %s" % (PRED_DIR / "bracket"))


# ---------------------------------------------------------------------------
# Interactive human entry
# ---------------------------------------------------------------------------
def _ask_int(prompt):
    while True:
        v = input(prompt).strip()
        if v.lstrip("-").isdigit():
            return int(v)
        print("  please enter a whole number")


def enter_round(round_label):
    fx = _load_fixtures(round_label)
    human = load_models_config().get("human", {"slug": "you", "name": "You"})
    matches = fx["matches"]
    print("\nEnter YOUR %s predictions (score at end of extra time; no shootout goals).\n"
          % fx.get("label", round_label))
    preds = []
    for m in matches:
        print("%s vs %s" % (m["home"], m["away"]))
        hg = _ask_int("  %s goals: " % m["home"])
        ag = _ask_int("  %s goals: " % m["away"])
        if hg > ag:
            adv = m["home"]
        elif ag > hg:
            adv = m["away"]
        else:
            adv = input("  draw — who advances on penalties? ").strip() or m["home"]
        preds.append({"id": m["id"], "home": m["home"], "away": m["away"],
                      "home_goals": hg, "away_goals": ag, "advances": adv})
        print()
    save_json(PRED_DIR / round_label / ("%s.json" % human["slug"]), {
        "round": round_label, "model": "human", "slug": human["slug"],
        "name": human["name"], "collected_at": _now(), "predictions": preds, "raw": ""})
    print("Saved your picks to %s" % (PRED_DIR / round_label / ("%s.json" % human["slug"])))


def enter_bracket():
    fx = _load_fixtures("R32")
    human = load_models_config().get("human", {"slug": "you", "name": "You"})
    print("\nEnter YOUR full-bracket picks. Separate team names with commas.\n")
    def ask_list(label, n):
        while True:
            raw = input("%s (%d teams): " % (label, n)).strip()
            teams = [t.strip() for t in raw.split(",") if t.strip()]
            if len(teams) == n:
                return teams
            print("  expected %d teams, got %d" % (n, len(teams)))
    rounds = {
        "R16": ask_list("Round of 16 (R32 winners)", 16),
        "QF": ask_list("Quarter-finalists", 8),
        "SF": ask_list("Semi-finalists", 4),
        "F": ask_list("Finalists", 2),
    }
    rounds["champion"] = input("Champion: ").strip()
    rounds["third"] = input("Third place: ").strip()
    save_json(PRED_DIR / "bracket" / ("%s.json" % human["slug"]), {
        "model": "human", "slug": human["slug"], "name": human["name"],
        "collected_at": _now(), "rounds": rounds, "raw": ""})
    print("Saved your bracket to %s" % (PRED_DIR / "bracket" / ("%s.json" % human["slug"])))


def main(argv=None):
    p = argparse.ArgumentParser(description="Collect World Cup predictions.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("round", help="collect a round from models")
    pr.add_argument("round_label", help="e.g. R32, R16, QF, SF, TP, F")
    pr.add_argument("--only", help="comma-separated slugs to limit to")

    pb = sub.add_parser("bracket", help="collect one-shot full bracket from models")
    pb.add_argument("--only", help="comma-separated slugs to limit to")

    pm = sub.add_parser("me", help="enter your own predictions")
    msub = pm.add_subparsers(dest="me_cmd", required=True)
    mr = msub.add_parser("round")
    mr.add_argument("round_label")
    msub.add_parser("bracket")

    args = p.parse_args(argv)
    if args.cmd == "round":
        collect_round(args.round_label, args.only)
    elif args.cmd == "bracket":
        collect_bracket(args.only)
    elif args.cmd == "me":
        if args.me_cmd == "round":
            enter_round(args.round_label)
        else:
            enter_bracket()


if __name__ == "__main__":
    main(sys.argv[1:])
