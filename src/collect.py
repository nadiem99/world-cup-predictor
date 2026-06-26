"""Collect predictions from models (via OpenRouter) or enter your own.

Usage (run from the project root):
  python -m src.collect round R32                 # all enabled models, Round of 32
  python -m src.collect round R32 --only gpt-5,qwen3-max
  python -m src.collect round R32 --workers 8     # parallel requests (default 6)
  python -m src.collect bracket                   # one-shot full-bracket, all models
  python -m src.collect bracket --only claude-opus-4.8
  python -m src.collect estimate all              # offline token/cost ballpark (no key)
  python -m src.collect estimate round R32        # estimate a single round
  python -m src.collect estimate bracket          # estimate the bracket prompt
  python -m src.collect me round R32              # enter YOUR picks for a round
  python -m src.collect me bracket                # enter YOUR full-bracket picks
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from . import prompts
from .common import (
    FIXTURES_DIR, PRED_DIR, ROUND_ORDER, OpenRouter, enabled_models, load_json,
    load_models_config, model_kwargs, save_json,
)

DEFAULT_WORKERS = 6


def _now():
    return datetime.now(timezone.utc).isoformat()


def _est_tokens(text):
    """Rough token estimate: ~4 chars per token (offline heuristic)."""
    return len(text) // 4


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


def _run_parallel(models, worker, workers):
    """Run ``worker(model)`` across models in a thread pool.

    ``worker`` returns a (ok, line) tuple; lines print as each finishes (live,
    unordered), then a summary is printed sorted by slug. Returns the number of
    successes. urllib calls are IO-bound, so threads give real concurrency.
    """
    n_workers = max(1, min(int(workers), len(models))) if models else 1
    results_by_slug = {}
    ok_count = 0
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(worker, m): m for m in models}
        for fut in as_completed(futures):
            m = futures[fut]
            try:
                ok, line = fut.result()
            except Exception as e:  # worker is defensive, but never let one kill the run
                ok, line = False, "  FAIL %-18s %s" % (m["slug"], e)
            results_by_slug[m["slug"]] = (ok, line)
            if ok:
                ok_count += 1
            print(line)
    print("\nSummary (%d ok / %d total):" % (ok_count, len(models)))
    for slug in sorted(results_by_slug):
        print(results_by_slug[slug][1])
    return ok_count


def collect_round(round_label, only=None, workers=DEFAULT_WORKERS):
    fx = _load_fixtures(round_label)
    matches = fx["matches"]
    label = fx.get("label", round_label)
    client = OpenRouter()
    models = _select(load_models_config(), only)
    print("Collecting %s predictions from %d models (%d workers)...\n"
          % (label, len(models), workers))

    def worker(m):
        out_path = PRED_DIR / round_label / ("%s.json" % m["slug"])
        try:
            raw = client.chat(m["id"], prompts.SYSTEM,
                              prompts.round_prompt(label, matches),
                              **model_kwargs(m))
            preds = prompts.parse_round(raw, matches)
            save_json(out_path, {
                "round": round_label, "model": m["id"], "slug": m["slug"],
                "name": m["name"], "collected_at": _now(),
                "predictions": preds, "raw": raw,
            })
            return True, "  ok   %-18s %d/%d matches parsed" % (
                m["slug"], len(preds), len(matches))
        except Exception as e:
            save_json(PRED_DIR / round_label / ("%s.error.json" % m["slug"]),
                      {"slug": m["slug"], "model": m["id"], "error": str(e),
                       "collected_at": _now()})
            return False, "  FAIL %-18s %s" % (m["slug"], e)

    _run_parallel(models, worker, workers)
    print("\nSaved to %s" % (PRED_DIR / round_label))


def collect_bracket(only=None, workers=DEFAULT_WORKERS):
    fx = _load_fixtures("R32")
    matches = fx["matches"]
    client = OpenRouter()
    models = _select(load_models_config(), only)
    print("Collecting one-shot full-bracket predictions from %d models (%d workers)...\n"
          % (len(models), workers))

    def worker(m):
        out_path = PRED_DIR / "bracket" / ("%s.json" % m["slug"])
        try:
            raw = client.chat(m["id"], prompts.SYSTEM, prompts.bracket_prompt(matches),
                              **model_kwargs(m))
            rounds = prompts.parse_bracket(raw)
            save_json(out_path, {
                "model": m["id"], "slug": m["slug"], "name": m["name"],
                "collected_at": _now(), "rounds": rounds, "raw": raw,
            })
            return True, "  ok   %-18s champion: %s" % (
                m["slug"], rounds.get("champion") or "?")
        except Exception as e:
            save_json(PRED_DIR / "bracket" / ("%s.error.json" % m["slug"]),
                      {"slug": m["slug"], "model": m["id"], "error": str(e),
                       "collected_at": _now()})
            return False, "  FAIL %-18s %s" % (m["slug"], e)

    _run_parallel(models, worker, workers)
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


# ---------------------------------------------------------------------------
# Offline cost estimate — builds the same prompts, no network/key required
# ---------------------------------------------------------------------------
def _estimate_prompt_tokens(kind, round_label=None):
    """Build a prompt offline and return its estimated token count, or None if
    the required fixtures are missing. ``kind`` is "round" or "bracket"."""
    path = FIXTURES_DIR / ("%s.json" % (round_label if kind == "round" else "R32"))
    fx = load_json(path)
    if not fx or not fx.get("matches"):
        return None
    matches = fx["matches"]
    if kind == "round":
        label = fx.get("label", round_label)
        user = prompts.round_prompt(label, matches)
    else:
        user = prompts.bracket_prompt(matches)
    return _est_tokens(prompts.SYSTEM) + _est_tokens(user)


def _available_rounds():
    """Round labels (in ROUND_ORDER) that currently have a fixtures file."""
    out = []
    for r in ROUND_ORDER:
        if (FIXTURES_DIR / ("%s.json" % r)).exists():
            out.append(r)
    return out


def estimate(target, round_label=None):
    """Print an offline token/cost ballpark. No network, no API key required.

    target is "round" (with round_label), "bracket", or "all".
    """
    models = enabled_models(load_models_config())
    n_models = len(models)

    # Build the list of (description, per-call-token-estimate) work items.
    items = []  # list of (label, per_call_tokens)
    if target == "round":
        toks = _estimate_prompt_tokens("round", round_label)
        if toks is None:
            raise SystemExit(
                "No fixtures for %s (looked in %s)."
                % (round_label, FIXTURES_DIR / ("%s.json" % round_label))
            )
        items.append(("round %s" % round_label, toks))
    elif target == "bracket":
        toks = _estimate_prompt_tokens("bracket")
        if toks is None:
            raise SystemExit("No R32 fixtures to build a bracket prompt from.")
        items.append(("bracket", toks))
    else:  # all
        rounds = _available_rounds()
        if not rounds:
            raise SystemExit("No fixtures files found in %s." % FIXTURES_DIR)
        for r in rounds:
            toks = _estimate_prompt_tokens("round", r)
            if toks is not None:
                items.append(("round %s" % r, toks))
        bracket_toks = _estimate_prompt_tokens("bracket")
        if bracket_toks is not None:
            items.append(("bracket", bracket_toks))

    print("Offline prompt-size estimate (heuristic: ~4 chars/token, input only)")
    print("Enabled models: %d\n" % n_models)

    grand_input = 0
    total_calls = 0
    for label, per_call in items:
        calls = n_models
        subtotal = per_call * calls
        grand_input += subtotal
        total_calls += calls
        print("  %-14s ~%5d tok/call  x %2d models = ~%7d input tokens"
              % (label, per_call, calls, subtotal))

    print("\n  Total API calls implied: %d (%d work item(s) x %d models)"
          % (total_calls, len(items), n_models))
    print("  Total estimated INPUT tokens: ~%d" % grand_input)
    print("\nNote: input-prompt tokens only; output/completion tokens not included.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Collect World Cup predictions.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("round", help="collect a round from models")
    pr.add_argument("round_label", help="e.g. R32, R16, QF, SF, TP, F")
    pr.add_argument("--only", help="comma-separated slugs to limit to")
    pr.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                    help="parallel model requests (default %d)" % DEFAULT_WORKERS)

    pb = sub.add_parser("bracket", help="collect one-shot full bracket from models")
    pb.add_argument("--only", help="comma-separated slugs to limit to")
    pb.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                    help="parallel model requests (default %d)" % DEFAULT_WORKERS)

    pe = sub.add_parser(
        "estimate",
        help="offline token/cost ballpark — no network or API key needed")
    esub = pe.add_subparsers(dest="est_cmd", required=True)
    er = esub.add_parser("round", help="estimate one round")
    er.add_argument("round_label", help="e.g. R32, R16, QF, SF, TP, F")
    esub.add_parser("bracket", help="estimate the one-shot bracket prompt")
    esub.add_parser("all", help="estimate every round with fixtures + bracket")

    pm = sub.add_parser("me", help="enter your own predictions")
    msub = pm.add_subparsers(dest="me_cmd", required=True)
    mr = msub.add_parser("round")
    mr.add_argument("round_label")
    msub.add_parser("bracket")

    args = p.parse_args(argv)
    if args.cmd == "round":
        collect_round(args.round_label, args.only, args.workers)
    elif args.cmd == "bracket":
        collect_bracket(args.only, args.workers)
    elif args.cmd == "estimate":
        if args.est_cmd == "round":
            estimate("round", args.round_label)
        elif args.est_cmd == "bracket":
            estimate("bracket")
        else:
            estimate("all")
    elif args.cmd == "me":
        if args.me_cmd == "round":
            enter_round(args.round_label)
        else:
            enter_bracket()


if __name__ == "__main__":
    main(sys.argv[1:])
