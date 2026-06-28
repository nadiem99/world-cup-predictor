import json
import tempfile
import unittest
from pathlib import Path

from src import common, score, site


class TestSite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.fx = root / "fixtures"
        self.res = root / "results"
        self.pred = root / "predictions"
        self._orig = (score.RESULTS_DIR, score.PRED_DIR, site.FIXTURES_DIR, site.PRED_DIR)
        score.RESULTS_DIR = self.res
        score.PRED_DIR = self.pred
        site.FIXTURES_DIR = self.fx
        site.PRED_DIR = self.pred
        common.save_json(self.fx / "R32.json", {"round": "R32", "label": "Round of 32",
            "matches": [{"id": "R32-1", "home": "Spain", "away": "Canada"}]})
        common.save_json(self.res / "R32.json", {"matches": [
            {"id": "R32-1", "home_goals": 0, "away_goals": 2, "advances": "Canada"}]})
        # one-shot bracket prediction: correctly placed Canada into the R16
        common.save_json(self.pred / "bracket" / "m.json", {"slug": "m", "name": "M",
            "provider": "Anthropic", "rounds": {"R16": ["Canada", "Spain"], "QF": [],
            "SF": [], "F": [], "champion": "Canada", "third": ""}})

    def tearDown(self):
        score.RESULTS_DIR, score.PRED_DIR, site.FIXTURES_DIR, site.PRED_DIR = self._orig
        self.tmp.cleanup()

    def test_gather_data_is_bracket_only(self):
        d = site.gather_data()
        for k in ("generated", "scoring", "bracket_board", "fixtures", "results",
                  "bracket_predictions", "actual_bracket", "flags"):
            self.assertIn(k, d)
        # per-round contest is gone
        self.assertNotIn("leaderboard", d)
        self.assertNotIn("round_predictions", d)
        # Canada correctly placed in R16 -> 1 pt on the single leaderboard
        self.assertEqual(d["bracket_board"]["rows"][0]["points"], 1)
        self.assertEqual(d["bracket_predictions"][0]["slug"], "m")

    def test_build_html_embeds_valid_json(self):
        html = site.build_html(site.gather_data())
        self.assertNotIn("/*__DATA__*/", html)
        a = html.index("window.DATA = ") + len("window.DATA = ")
        b = html.index(";\n(function", a)
        json.loads(html[a:b])  # raises if the embedded JSON is malformed


if __name__ == "__main__":
    unittest.main()
