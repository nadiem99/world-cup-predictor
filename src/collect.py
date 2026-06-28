"""Collect one-shot bracket predictions from models (via OpenRouter) or enter your own.

Everyone predicts the FULL bracket once, before the Round of 32.

Usage (run from the project root):
  python -m src.collect bracket                   # all enabled models
  python -m src.collect bracket --only claude-opus-4.8,gpt-5
  python -m src.collect bracket --workers 8       # parallel requests (default 6)
  python -m src.collect me                        # enter YOUR full-bracket picks
  python -m src.collect estimate                  # offline token/cost ballpark (no key)
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from . import prompts
from .common import (
    FIXTURES_DIR, PRED_DIR, OpenRouter, enabled_models, load_json,
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


def _load_r32():
    path = FIXTURES_DIR / "R32.json"
    fx = load_json(path)
    if not fx or not fx.get("matches"):
        raise SystemExit(
            "No R32 fixtures at %s. Fill in the Round of 32 teams first." % path
        )
    return fx


def run_parallel(models, worker, workers):
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


def collect_bracket(only=None, workers=DEFAULT_WORKERS):
    matches = _load_r32()["matches"]
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

    run_parallel(models, worker, workers)
    print("\nSaved to %s" % (PRED_DIR / "bracket"))


# ---------------------------------------------------------------------------
# Interactive human entry
# ---------------------------------------------------------------------------
def enter_bracket():
    human = load_models_config().get("human", {"slug": "you", "name": "You"})
    print("\nEnter YOUR full-bracket picks. Separate team names with commas.")
    print("(Tip: `make enter` opens a nicer point-and-click version in your browser.)\n")

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
# Offline cost estimate — builds the same prompt, no network/key required
# ---------------------------------------------------------------------------
def estimate():
    """Print an offline token/cost ballpark for the bracket call. No key required."""
    fx = load_json(FIXTURES_DIR / "R32.json")
    if not fx or not fx.get("matches"):
        raise SystemExit("No R32 fixtures to build a bracket prompt from.")
    models = enabled_models(load_models_config())
    n_models = len(models)
    per_call = _est_tokens(prompts.SYSTEM) + _est_tokens(prompts.bracket_prompt(fx["matches"]))

    print("Offline prompt-size estimate (heuristic: ~4 chars/token, input only)")
    print("Enabled models: %d\n" % n_models)
    print("  bracket       ~%5d tok/call  x %2d models = ~%7d input tokens"
          % (per_call, n_models, per_call * n_models))
    print("\n  Total API calls implied: %d (1 bracket call x %d models)"
          % (n_models, n_models))
    print("  Total estimated INPUT tokens: ~%d" % (per_call * n_models))
    print("\nNote: input-prompt tokens only; output/completion tokens not included.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Collect one-shot World Cup bracket predictions.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("bracket", help="collect the one-shot bracket from all models")
    pb.add_argument("--only", help="comma-separated slugs to limit to")
    pb.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                    help="parallel model requests (default %d)" % DEFAULT_WORKERS)

    sub.add_parser("me", help="enter your own one-shot bracket")
    sub.add_parser("estimate",
                   help="offline token/cost ballpark — no network or API key needed")

    args = p.parse_args(argv)
    if args.cmd == "bracket":
        collect_bracket(args.only, args.workers)
    elif args.cmd == "me":
        enter_bracket()
    elif args.cmd == "estimate":
        estimate()


if __name__ == "__main__":
    main(sys.argv[1:])
