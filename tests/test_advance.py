import tempfile
import unittest
from pathlib import Path

from src import advance, common


class _AdvanceBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.fixtures = root / "fixtures"
        self.results = root / "results"
        self._orig = (advance.DATA_DIR, advance.FIXTURES_DIR, advance.RESULTS_DIR)
        advance.DATA_DIR = root
        advance.FIXTURES_DIR = self.fixtures
        advance.RESULTS_DIR = self.results

    def tearDown(self):
        advance.DATA_DIR, advance.FIXTURES_DIR, advance.RESULTS_DIR = self._orig
        self.tmp.cleanup()

    def _fx(self, rnd, matches):
        common.save_json(self.fixtures / ("%s.json" % rnd), {"round": rnd, "matches": matches})

    def _res(self, rnd, matches):
        common.save_json(self.results / ("%s.json" % rnd), {"round": rnd, "matches": matches})

    def _bracket(self, obj):
        common.save_json(Path(advance.DATA_DIR) / "bracket.json", obj)

    def _load_fx(self, rnd):
        return {m["id"]: m for m in common.load_json(self.fixtures / ("%s.json" % rnd))["matches"]}


class TestWinnerPropagation(_AdvanceBase):
    def test_r32_winners_fill_r16(self):
        self._bracket({"slots": {"R16-1": ["R32-1", "R32-2"]}})
        self._fx("R32", [{"id": "R32-1", "home": "Canada", "away": "Mexico"},
                         {"id": "R32-2", "home": "USA", "away": "Brazil"}])
        self._fx("R16", [{"id": "R16-1", "home": "", "away": "", "kickoff": "8pm", "venue": "MetLife"}])
        self._res("R32", [{"id": "R32-1", "home_goals": 1, "away_goals": 0, "advances": "Canada"},
                          {"id": "R32-2", "home_goals": 2, "away_goals": 1, "advances": "USA"}])
        advance.advance(quiet=True)
        r16 = self._load_fx("R16")["R16-1"]
        self.assertEqual(r16["home"], "Canada")
        self.assertEqual(r16["away"], "USA")
        self.assertEqual(r16["venue"], "MetLife")  # untouched

    def test_undecided_feeder_leaves_slot_blank(self):
        self._bracket({"slots": {"R16-1": ["R32-1", "R32-2"]}})
        self._fx("R32", [{"id": "R32-1", "home": "Canada", "away": "Mexico"},
                         {"id": "R32-2", "home": "USA", "away": "Brazil"}])
        self._fx("R16", [{"id": "R16-1", "home": "", "away": ""}])
        self._res("R32", [{"id": "R32-1", "home_goals": 1, "away_goals": 0, "advances": "Canada"},
                          {"id": "R32-2", "home_goals": None, "away_goals": None, "advances": ""}])
        filled = advance.advance(quiet=True)
        r16 = self._load_fx("R16")["R16-1"]
        self.assertEqual(r16["home"], "Canada")
        self.assertEqual(r16["away"], "")  # R32-2 undecided -> away stays blank
        self.assertEqual(filled, [("R16-1", "home", "Canada")])


class TestThirdPlaceLosers(_AdvanceBase):
    def test_sf_losers_fill_third_place_and_final(self):
        self._bracket({
            "slots": {"F-1": ["SF-1", "SF-2"]},
            "third_place": {"id": "TP-1", "feeders": ["SF-1-loser", "SF-2-loser"]},
        })
        self._fx("SF", [{"id": "SF-1", "home": "Canada", "away": "Brazil"},
                        {"id": "SF-2", "home": "USA", "away": "France"}])
        self._fx("F", [{"id": "F-1", "home": "", "away": ""}])
        self._fx("TP", [{"id": "TP-1", "home": "", "away": ""}])
        self._res("SF", [{"id": "SF-1", "home_goals": 2, "away_goals": 1, "advances": "Canada"},
                         {"id": "SF-2", "home_goals": 0, "away_goals": 1, "advances": "France"}])
        advance.advance(quiet=True)
        final = self._load_fx("F")["F-1"]
        third = self._load_fx("TP")["TP-1"]
        self.assertEqual((final["home"], final["away"]), ("Canada", "France"))
        self.assertEqual((third["home"], third["away"]), ("Brazil", "USA"))  # the beaten semi-finalists


class TestIdempotent(_AdvanceBase):
    def test_second_run_changes_nothing(self):
        self._bracket({"slots": {"R16-1": ["R32-1", "R32-2"]}})
        self._fx("R32", [{"id": "R32-1", "home": "Canada", "away": "Mexico"},
                         {"id": "R32-2", "home": "USA", "away": "Brazil"}])
        self._fx("R16", [{"id": "R16-1", "home": "", "away": ""}])
        self._res("R32", [{"id": "R32-1", "home_goals": 1, "away_goals": 0, "advances": "Canada"},
                          {"id": "R32-2", "home_goals": 2, "away_goals": 1, "advances": "USA"}])
        self.assertEqual(len(advance.advance(quiet=True)), 2)
        self.assertEqual(advance.advance(quiet=True), [])  # nothing new the second time


if __name__ == "__main__":
    unittest.main()
