import unittest

from src import fetch_results as fr


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
                     "decided_by": "extra_time", "source": "bbc.com"}]
        changed, summary, skipped = fr.apply_results(returned, pend, results)
        m = results["R32"]["matches"][0]
        self.assertEqual((m["home_goals"], m["away_goals"], m["advances"], m["decided_by"]),
                         (1, 0, "France", "extra_time"))
        self.assertEqual(changed, {"R32"})
        self.assertEqual(len(summary), 1)
        self.assertEqual(skipped, [])

    def test_canonicalizes_winner_to_fixture_spelling(self):
        pend = {"R32-7": {"id": "R32-7", "round": "R32",
                          "home": "United States", "away": "Bosnia and Herzegovina"}}
        results = {"R32": {"matches": [
            {"id": "R32-7", "home_goals": None, "away_goals": None, "advances": "", "decided_by": "regulation"}]}}
        returned = [{"id": "R32-7", "home_goals": 2, "away_goals": 1, "advances": "USA"}]
        # "USA" matches neither spelling -> rejected (we only accept the exact fixture names)
        changed, summary, skipped = fr.apply_results(returned, pend, results)
        self.assertEqual(changed, set())
        self.assertEqual(skipped, [("R32-7", "winner not one of the two teams")])
        # but the verbatim name in a different case IS accepted and stored canonically
        returned2 = [{"id": "R32-7", "home_goals": 2, "away_goals": 1, "advances": "UNITED STATES"}]
        fr.apply_results(returned2, pend, results)
        self.assertEqual(results["R32"]["matches"][0]["advances"], "United States")

    def test_rejects_bad_winner_and_leaves_data_untouched(self):
        pend, results = self._pend_results()
        returned = [{"id": "R32-2", "home_goals": 1, "away_goals": 0, "advances": "Brazil"}]
        changed, summary, skipped = fr.apply_results(returned, pend, results)
        self.assertEqual(changed, set())
        self.assertEqual(summary, [])
        self.assertEqual(results["R32"]["matches"][0]["advances"], "")  # unchanged

    def test_skips_unknown_id_and_non_integer_goals(self):
        pend, results = self._pend_results()
        returned = [
            {"id": "R99-9", "home_goals": 1, "away_goals": 0, "advances": "France"},   # not pending
            {"id": "R32-2", "home_goals": "x", "away_goals": 0, "advances": "France"},  # bad goals
        ]
        changed, summary, skipped = fr.apply_results(returned, pend, results)
        self.assertEqual(changed, set())
        self.assertEqual(len(skipped), 2)
        self.assertEqual(results["R32"]["matches"][0]["home_goals"], None)

    def test_invalid_decided_by_falls_back_to_regulation(self):
        pend, results = self._pend_results()
        returned = [{"id": "R32-2", "home_goals": 3, "away_goals": 3, "advances": "Sweden",
                     "decided_by": "coin_toss"}]
        fr.apply_results(returned, pend, results)
        self.assertEqual(results["R32"]["matches"][0]["decided_by"], "regulation")
        self.assertEqual(results["R32"]["matches"][0]["advances"], "Sweden")


if __name__ == "__main__":
    unittest.main()
