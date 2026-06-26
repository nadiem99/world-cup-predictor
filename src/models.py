"""Inspect the live OpenRouter catalogue and validate config/models.json.

  python -m src.models list            # all available model ids
  python -m src.models list qwen       # filter by substring
  python -m src.models check           # verify the ids in config/models.json exist
  python -m src.models ping            # live: call every model, report ok/latency
  python -m src.models ping gpt-5,o4-mini   # ping only these slugs
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .common import (
    OpenRouter, enabled_models, load_models_config, model_kwargs,
)


def cmd_list(substr=None):
    data = OpenRouter().list_models()
    rows = []
    for m in data:
        mid = m.get("id", "")
        name = m.get("name", "")
        if substr and substr.lower() not in (mid + " " + name).lower():
            continue
        rows.append((mid, name))
    rows.sort()
    for mid, name in rows:
        print("%-45s %s" % (mid, name))
    print("\n%d model(s)%s" % (len(rows), " matching '%s'" % substr if substr else ""))


def cmd_check():
    live = {m.get("id", "") for m in OpenRouter().list_models()}
    cfg = load_models_config()
    print("Checking %d configured models against the live catalogue...\n"
          % len(enabled_models(cfg)))
    bad = 0
    for m in enabled_models(cfg):
        if m["id"] in live:
            print("  ok      %-18s %s" % (m["slug"], m["id"]))
        else:
            bad += 1
            vendor = m["id"].split("/")[0]
            near = sorted(x for x in live if x.startswith(vendor + "/"))[:6]
            print("  MISSING %-18s %s" % (m["slug"], m["id"]))
            if near:
                print("          try one of: %s" % ", ".join(near))
    if bad:
        print("\n%d id(s) need fixing in config/models.json." % bad)
    else:
        print("\nAll configured model ids are valid. ✓")


def cmd_ping(only=None, workers=6):
    """Actually call every enabled model with a 1-token prompt and report which
    respond. This exercises the real request wiring (auth, per-model overrides,
    the JSON/temperature fallback) — a stronger check than `check`, which only
    confirms an id exists in the catalogue."""
    models = enabled_models(load_models_config())
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        models = [m for m in models if m["slug"] in wanted]
        missing = wanted - {m["slug"] for m in models}
        if missing:
            print("warning: unknown slug(s): %s" % ", ".join(sorted(missing)))
    if not models:
        print("No models to ping.")
        return
    client = OpenRouter()
    print("Pinging %d models (1-token reply each)...\n" % len(models))

    def worker(m):
        kw = model_kwargs(m)
        kw["json_mode"] = False  # a plain 'OK' needs no JSON wrapper
        t0 = time.time()
        try:
            txt = client.chat(m["id"], "Reply with just: OK", "Say OK.",
                              timeout=60, **kw)
            dt = time.time() - t0
            reply = " ".join((txt or "").split())[:24]
            return True, "  ok    %-18s %5.1fs  %s" % (m["slug"], dt, reply)
        except Exception as e:
            dt = time.time() - t0
            return False, "  FAIL  %-18s %5.1fs  %s" % (m["slug"], dt, str(e)[:90])

    n_workers = max(1, min(int(workers), len(models)))
    lines, ok = {}, 0
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(worker, m): m for m in models}
        for fut in as_completed(futures):
            m = futures[fut]
            try:
                good, line = fut.result()
            except Exception as e:  # worker is defensive, but be safe
                good, line = False, "  FAIL  %-18s   ?    %s" % (m["slug"], e)
            lines[m["slug"]] = line
            ok += 1 if good else 0
            print(line)
    print("\nSummary (%d ok / %d total):" % (ok, len(models)))
    for slug in sorted(lines):
        print(lines[slug])
    if ok < len(models):
        print("\nFor any FAIL: check the id with `python -m src.models check`, or set "
              "per-model overrides (json_mode/temperature/params) in config/models.json.")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] == "list":
        cmd_list(argv[1] if len(argv) > 1 else None)
    elif argv[0] == "check":
        cmd_check()
    elif argv[0] == "ping":
        cmd_ping(argv[1] if len(argv) > 1 else None)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
