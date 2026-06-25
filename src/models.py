"""Inspect the live OpenRouter catalogue and validate config/models.json.

  python -m src.models list            # all available model ids
  python -m src.models list qwen       # filter by substring
  python -m src.models check           # verify the ids in config/models.json exist
"""
import sys

from .common import OpenRouter, enabled_models, load_models_config


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


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] == "list":
        cmd_list(argv[1] if len(argv) > 1 else None)
    elif argv[0] == "check":
        cmd_check()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
