import unittest

from src import fetch_results as fr

URL = "https://www.bbc.com/sport/football/example"


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


if __name__ == "__main__":
    unittest.main()
