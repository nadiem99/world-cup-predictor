"""Prompt construction and response parsing for per-round and full-bracket predictions."""
from .common import extract_json

SYSTEM = (
    "You are an expert football (soccer) analyst making predictions for the 2026 FIFA World Cup "
    "knockout stage. Give a single best prediction for each match — your single most likely "
    "outcome, not a range or probabilities. Reply with ONLY the requested JSON and nothing else."
)


def _as_json(text):
    """Parse a model response to JSON, recovering double-encoded strings.

    Some models return the JSON as a quoted string (a JSON string whose value
    is itself JSON). When that happens we parse the inner payload too, so the
    caller always gets the underlying object/array rather than a bare string.
    """
    data = extract_json(text)
    if isinstance(data, str):
        try:
            data = extract_json(data)
        except Exception:
            pass
    return data


def round_prompt(round_label, matches):
    fixtures = "\n".join(
        '  - id "%s": %s vs %s' % (m["id"], m["home"], m["away"]) for m in matches
    )
    schema = (
        "{\n"
        '  "predictions": [\n'
        '    {"id": "<match id>", "home_goals": <int>, "away_goals": <int>, '
        '"advances": "<team that goes through>"}\n'
        "  ]\n"
        "}"
    )
    return (
        "Predict every match in the %s of the 2026 FIFA World Cup.\n\n"
        "Fixtures:\n%s\n\n"
        "For each match give the score at the end of regulation + extra time "
        "(do NOT add penalty-shootout goals to the score), and name the team that advances "
        "(if your score is a draw, name the team you think wins the shootout). "
        "Use the exact team names shown above.\n\n"
        "Respond with ONLY this JSON shape:\n%s" % (round_label, fixtures, schema)
    )


def parse_round(text, matches):
    data = _as_json(text)
    if isinstance(data, dict):
        preds = data.get("predictions", [])
    elif isinstance(data, list):
        preds = data
    else:
        raise ValueError("round response was not valid JSON")
    valid_ids = {m["id"] for m in matches}
    name_by_id = {m["id"]: (m["home"], m["away"]) for m in matches}
    out = []
    seen = set()
    for p in preds:
        mid = str(p.get("id"))
        if mid not in valid_ids or mid in seen:
            continue
        seen.add(mid)
        home, away = name_by_id[mid]
        out.append({
            "id": mid,
            "home": home,
            "away": away,
            "home_goals": int(p["home_goals"]),
            "away_goals": int(p["away_goals"]),
            "advances": str(p.get("advances", "")).strip(),
        })
    return out


def bracket_prompt(r32_matches):
    fixtures = "\n".join(
        "  - %s vs %s" % (m["home"], m["away"]) for m in r32_matches
    )
    schema = (
        "{\n"
        '  "R16": ["<16 teams that win their Round of 32 match>"],\n'
        '  "QF":  ["<8 teams that reach the quarter-finals>"],\n'
        '  "SF":  ["<4 teams that reach the semi-finals>"],\n'
        '  "F":   ["<2 finalists>"],\n'
        '  "champion": "<world champion>",\n'
        '  "third": "<third-place team>"\n'
        "}"
    )
    return (
        "Predict the FULL knockout bracket of the 2026 FIFA World Cup, all the way to the "
        "champion, based on the Round of 32 matchups below.\n\n"
        "Round of 32 matchups:\n%s\n\n"
        "List the teams that reach each stage. Each list must contain teams from the previous "
        "stage. Use exact team names from the matchups above.\n\n"
        "Respond with ONLY this JSON shape:\n%s" % (fixtures, schema)
    )


def parse_bracket(text):
    data = _as_json(text)
    if not isinstance(data, dict):
        raise ValueError("bracket response was not a JSON object")
    rounds = {}
    for key in ("R16", "QF", "SF", "F"):
        rounds[key] = [str(t).strip() for t in data.get(key, []) if str(t).strip()]
    rounds["champion"] = str(data.get("champion", "")).strip()
    rounds["third"] = str(data.get("third", "")).strip()
    return rounds
