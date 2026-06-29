import json
import unittest

from src import fetch_results as fr

URL = "https://www.bbc.com/sport/football/example"


def _match(home, away, rnd="1/16", finished=True, score="2 - 1", reason="fulltime_short", url="/m"):
    return {"round": rnd, "home": {"name": home}, "away": {"name": away},
            "status": {"finished": finished, "scoreStr": score, "reason": {"shortKey": reason}},
            "pageUrl": url}


def _detail_html(teams, who_lost):
    data = {"props": {"pageProps": {"header": {
        "teams": teams, "status": {"whoLostOnPenalties": who_lost}}}}}
    return '<script id="__NEXT_DATA__" type="application/json">%s</script>' % json.dumps(data)


class TestPendingMatches(unittest.TestCase):
    def test_skips_unknown_teams_and_already_recorded(self):
        fixtures = {
            "R32": {"matches": [
                {"id": "R32-1", "home": "Germany", "away": "Paraguay"},
                {"id": "R32-2", "home": "France", "away": "Sweden"}]},
            "R16": {"matches": [{"id": "R16-1", "home": "", "away": ""}]},  # teams not known yet
        }
        results = {
            "R32": {"matches": [
                {"id": "R32-1", "home_goals": 2, "away_goals": 0, "advances": "Germany"},  # recorded
                {"id": "R32-2", "home_goals": None, "away_goals": None, "advances": ""}]},
            "R16": {"matches": [{"id": "R16-1", "home_goals": None, "away_goals": None, "advances": ""}]},
        }
        pend = fr.pending_matches(fixtures, results)
        self.assertEqual([p["id"] for p in pend], ["R32-2"])
        self.assertEqual(pend[0]["home"], "France")


class TestApplyResults(unittest.TestCase):
    def _pend_results(self):
        pend = {"R32-2": {"id": "R32-2", "round": "R32", "home": "France", "away": "Sweden"}}
        results = {"R32": {"matches": [
            {"id": "R32-2", "home_goals": None, "away_goals": None, "advances": "", "decided_by": "regulation"}]}}
        return pend, results

    def test_records_valid_result(self):
        pend, results = self._pend_results()
        returned = [{"id": "R32-2", "home_goals": 1, "away_goals": 0, "advances": "france",
                     "decided_by": "extra_time", "source": URL}]
        changed, summary, skipped = fr.apply_results(returned, pend, results)
        m = results["R32"]["matches"][0]
        self.assertEqual((m["home_goals"], m["away_goals"], m["advances"], m["decided_by"]),
                         (1, 0, "France", "extra_time"))
        self.assertEqual(changed, {"R32"})
        self.assertEqual((len(summary), skipped), (1, []))

    def test_canonicalizes_winner_to_fixture_spelling(self):
        pend = {"R32-7": {"id": "R32-7", "round": "R32",
                          "home": "United States", "away": "Bosnia and Herzegovina"}}
        results = {"R32": {"matches": [
            {"id": "R32-7", "home_goals": None, "away_goals": None, "advances": "", "decided_by": "regulation"}]}}
        returned = [{"id": "R32-7", "home_goals": 2, "away_goals": 1, "advances": "UNITED STATES",
                     "source": URL}]
        fr.apply_results(returned, pend, results)
        self.assertEqual(results["R32"]["matches"][0]["advances"], "United States")

    def test_rejects_bad_winner_and_leaves_data_untouched(self):
        pend, results = self._pend_results()
        returned = [{"id": "R32-2", "home_goals": 1, "away_goals": 0, "advances": "Brazil", "source": URL}]
        changed, summary, skipped = fr.apply_results(returned, pend, results)
        self.assertEqual(changed, set())
        self.assertEqual(skipped, [("R32-2", "winner is not one of the two teams")])
        self.assertEqual(results["R32"]["matches"][0]["advances"], "")  # unchanged

    def test_skips_unknown_id_and_non_integer_goals(self):
        pend, results = self._pend_results()
        returned = [
            {"id": "R99-9", "home_goals": 1, "away_goals": 0, "advances": "France", "source": URL},
            {"id": "R32-2", "home_goals": "x", "away_goals": 0, "advances": "France", "source": URL},
        ]
        changed, summary, skipped = fr.apply_results(returned, pend, results)
        self.assertEqual(changed, set())
        self.assertEqual(len(skipped), 2)
        self.assertEqual(results["R32"]["matches"][0]["home_goals"], None)


class TestValidateResult(unittest.TestCase):
    """The consistency guards that stop fabricated/garbled results."""

    def setUp(self):
        self.pend = {"id": "R32-1", "round": "R32", "home": "Germany", "away": "Paraguay"}

    def _r(self, **kw):
        base = {"home_goals": 1, "away_goals": 0, "advances": "Germany",
                "decided_by": "regulation", "source": URL}
        base.update(kw)
        return base

    def test_level_score_in_regulation_is_rejected(self):
        # the exact fabrication seen in the wild: 0-0 with a winner "in regulation"
        with self.assertRaises(ValueError) as cm:
            fr.validate_result(self._r(home_goals=0, away_goals=0, decided_by="regulation"), self.pend)
        self.assertIn("penalties", str(cm.exception))

    def test_level_score_decided_by_penalties_is_accepted(self):
        winner, decided, hg, ag = fr.validate_result(
            self._r(home_goals=0, away_goals=0, decided_by="penalties"), self.pend)
        self.assertEqual((winner, decided, hg, ag), ("Germany", "penalties", 0, 0))

    def test_decisive_score_by_penalties_is_rejected(self):
        with self.assertRaises(ValueError):
            fr.validate_result(self._r(home_goals=2, away_goals=1, decided_by="penalties"), self.pend)

    def test_winner_must_be_higher_scoring_side(self):
        with self.assertRaises(ValueError):
            fr.validate_result(self._r(home_goals=0, away_goals=2, advances="Germany"), self.pend)

    def test_bare_citation_marker_source_is_rejected(self):
        with self.assertRaises(ValueError) as cm:
            fr.validate_result(self._r(source="[10]"), self.pend)
        self.assertIn("source", str(cm.exception))

    def test_missing_source_is_rejected(self):
        with self.assertRaises(ValueError):
            fr.validate_result(self._r(source=""), self.pend)


class TestKnockoutFinished(unittest.TestCase):
    def test_filters_to_finished_knockout_with_scores(self):
        matches = [
            _match("Mexico", "South Africa", rnd="1"),                       # group stage
            _match("South Africa", "Canada", rnd="1/16", score="0 - 1"),     # R32, finished
            _match("Canada", "Netherlands/Morocco", rnd="1/8", finished=False),  # undetermined/unplayed
            _match("Spain", "Italy", rnd="final", score="1 - 1", reason="penalties_short"),
        ]
        got = fr.knockout_finished(matches)
        ids = {(m["home"], m["away"]) for m in got}
        self.assertEqual(ids, {("South Africa", "Canada"), ("Spain", "Italy")})
        sac = [m for m in got if m["home"] == "South Africa"][0]
        self.assertEqual((sac["hg"], sac["ag"]), (0, 1))


class TestFotmobResults(unittest.TestCase):
    def test_decisive_result_oriented_to_our_fixture(self):
        # our fixture has the teams in the opposite order to FotMob
        pending = [{"id": "R32-3", "round": "R32", "home": "South Africa", "away": "Canada"}]
        finished = [{"home": "Canada", "away": "South Africa", "hg": 1, "ag": 0,
                     "reason": "fulltime_short", "url": "https://www.fotmob.com/m/x"}]
        results, unresolved = fr.fotmob_results(pending, finished)
        self.assertEqual(unresolved, [])
        self.assertEqual(results[0], {"id": "R32-3", "home_goals": 0, "away_goals": 1,
                                      "advances": "Canada", "decided_by": "regulation",
                                      "source": "https://www.fotmob.com/m/x"})

    def test_team_name_alias_usa(self):
        pending = [{"id": "R32-7", "round": "R32", "home": "United States", "away": "Bosnia and Herzegovina"}]
        finished = [{"home": "USA", "away": "Bosnia and Herzegovina", "hg": 2, "ag": 1,
                     "reason": "fulltime_short", "url": "https://www.fotmob.com/m/y"}]
        results, _ = fr.fotmob_results(pending, finished)
        self.assertEqual(results[0]["advances"], "United States")

    def test_penalty_winner_resolved_from_detail_page(self):
        pending = [{"id": "F-1", "round": "F", "home": "Spain", "away": "Italy"}]
        finished = [{"home": "Spain", "away": "Italy", "hg": 1, "ag": 1,
                     "reason": "penalties_short", "url": "https://www.fotmob.com/m/f"}]
        fake = lambda url, timeout=30: _detail_html(
            [{"name": "Spain", "id": 1}, {"name": "Italy", "id": 2}], who_lost="Italy")
        results, unresolved = fr.fotmob_results(pending, finished, fetch=fake)
        self.assertEqual(unresolved, [])
        self.assertEqual((results[0]["advances"], results[0]["decided_by"]), ("Spain", "penalties"))

    def test_penalty_winner_unresolved_when_missing(self):
        pending = [{"id": "F-1", "round": "F", "home": "Spain", "away": "Italy"}]
        finished = [{"home": "Spain", "away": "Italy", "hg": 1, "ag": 1,
                     "reason": "penalties_short", "url": "https://www.fotmob.com/m/f"}]
        fake = lambda url, timeout=30: _detail_html(
            [{"name": "Spain", "id": 1}, {"name": "Italy", "id": 2}], who_lost=None)
        results, unresolved = fr.fotmob_results(pending, finished, fetch=fake)
        self.assertEqual(results, [])
        self.assertEqual(len(unresolved), 1)


class TestReconcile(unittest.TestCase):
    def test_confirms_matching_and_corrects_drift(self):
        cand = {"R32-3": {"id": "R32-3", "round": "R32", "home": "South Africa", "away": "Canada"},
                "R32-9": {"id": "R32-9", "round": "R32", "home": "Brazil", "away": "Japan"}}
        results = {"R32": {"matches": [
            {"id": "R32-3", "home_goals": 0, "away_goals": 1, "advances": "Canada", "decided_by": "regulation"},
            {"id": "R32-9", "home_goals": 9, "away_goals": 9, "advances": "Japan", "decided_by": "penalties"},
        ]}}
        returned = [
            {"id": "R32-3", "home_goals": 0, "away_goals": 1, "advances": "Canada",
             "decided_by": "regulation", "source": URL},   # already matches -> confirmed
            {"id": "R32-9", "home_goals": 2, "away_goals": 1, "advances": "Brazil",
             "decided_by": "regulation", "source": URL},   # disagrees -> corrected
        ]
        changed, updated, confirmed, skipped = fr.reconcile_results(returned, cand, results)
        self.assertEqual(confirmed, ["R32-3"])
        self.assertEqual(changed, {"R32"})
        self.assertEqual(len(updated), 1)
        self.assertEqual(skipped, [])
        m9 = results["R32"]["matches"][1]
        self.assertEqual((m9["home_goals"], m9["away_goals"], m9["advances"], m9["decided_by"]),
                         (2, 1, "Brazil", "regulation"))


if __name__ == "__main__":
    unittest.main()
