import tempfile
import unittest
from pathlib import Path

from src import common, score


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
