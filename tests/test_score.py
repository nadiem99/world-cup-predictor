import tempfile
import unittest
from pathlib import Path

from src import common, score


class TestScoreMatch(unittest.TestCase):
    """_score_match is non-stacking: exact scoreline=3, else advancer=1, else 0."""

    def test_exact(self):
        pts, adv, sc = score._score_match(
            {"home_goals": 1, "away_goals": 2, "advances": "B"},
            {"home_goals": 1, "away_goals": 2, "advances": "B"})
        self.assertEqual(pts, 3)
        self.assertTrue(adv and sc)

    def test_advancer_only(self):
        pts, adv, sc = score._score_match(
            {"home_goals": 2, "away_goals": 0, "advances": "B"},
            {"home_goals": 1, "away_goals": 0, "advances": "B"})
        self.assertEqual(pts, 1)
        self.assertTrue(adv)
        self.assertFalse(sc)

    def test_nothing(self):
        pts, _, _ = score._score_match(
            {"home_goals": 0, "away_goals": 0, "advances": "A"},
            {"home_goals": 1, "away_goals": 0, "advances": "B"})
        self.assertEqual(pts, 0)

    def test_advancer_case_insensitive(self):
        _, adv, _ = score._score_match(
            {"home_goals": 3, "away_goals": 1, "advances": "canada"},
            {"home_goals": 0, "away_goals": 0, "advances": "Canada"})
        self.assertTrue(adv)

    def test_exact_draw_with_wrong_shootout_pick_still_3(self):
        # nailed the 1-1 but picked the wrong penalty winner -> scoreline wins, 3
        pts, adv, sc = score._score_match(
            {"home_goals": 1, "away_goals": 1, "advances": "A"},
            {"home_goals": 1, "away_goals": 1, "advances": "B"})
        self.assertEqual(pts, 3)
        self.assertTrue(sc)
        self.assertFalse(adv)


class _ScoreBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.results = root / "results"
        self.preds = root / "predictions"
        self._orig = (score.RESULTS_DIR, score.PRED_DIR)
        score.RESULTS_DIR = self.results
        score.PRED_DIR = self.preds

    def tearDown(self):
        score.RESULTS_DIR, score.PRED_DIR = self._orig
        self.tmp.cleanup()


class TestComputeMain(_ScoreBase):
    def test_aggregate_two_rounds(self):
        common.save_json(self.results / "R32.json", {"matches": [
            {"id": "R32-1", "home_goals": 0, "away_goals": 2, "advances": "Canada"}]})
        common.save_json(self.results / "R16.json", {"matches": [
            {"id": "R16-1", "home_goals": 1, "away_goals": 0, "advances": "Canada"}]})
        common.save_json(self.preds / "R32" / "m.json", {"slug": "m", "name": "M", "predictions": [
            {"id": "R32-1", "home": "SA", "away": "Canada",
             "home_goals": 0, "away_goals": 2, "advances": "Canada"}]})  # exact -> 3
        common.save_json(self.preds / "R16" / "m.json", {"slug": "m", "name": "M", "predictions": [
            {"id": "R16-1", "home": "Canada", "away": "X",
             "home_goals": 2, "away_goals": 1, "advances": "Canada"}]})  # advancer -> 1
        main = score.compute_main()
        self.assertEqual(main["rounds"], ["R32", "R16"])
        row = main["rows"][0]
        self.assertEqual(row["points"], 4)
        self.assertEqual(row["exact"], 1)
        self.assertEqual(row["correct"], 2)
        self.assertEqual(row["by_round"], {"R32": 3, "R16": 1})


class TestComputeBracket(_ScoreBase):
    def test_stage_and_champion_bonus(self):
        common.save_json(self.results / "R32.json", {"matches": [
            {"id": "R32-1", "home_goals": 1, "away_goals": 0, "advances": "Canada"},
            {"id": "R32-2", "home_goals": 2, "away_goals": 1, "advances": "USA"}]})
        common.save_json(self.results / "F.json", {"matches": [
            {"id": "F-1", "home_goals": 1, "away_goals": 0, "advances": "Canada"}]})
        common.save_json(self.preds / "bracket" / "m.json", {"slug": "m", "name": "M", "rounds": {
            "R16": ["Canada", "USA", "Brazil"], "QF": [], "SF": [], "F": [],
            "champion": "Canada", "third": ""}})
        b = score.compute_bracket()
        row = b["rows"][0]
        # R16: Canada+USA correct = 2*1 = 2; champion +10 => 12
        self.assertEqual(row["points"], 12)
        self.assertTrue(b["have_results"])


class TestActualBracket(_ScoreBase):
    def test_derivation_normalized(self):
        common.save_json(self.results / "R32.json", {"matches": [
            {"id": "R32-1", "home_goals": 1, "away_goals": 0, "advances": "Canada"}]})
        ab = score.actual_bracket()
        self.assertIn("canada", ab["R16"])  # advancers are normalized lower-case


if __name__ == "__main__":
    unittest.main()
