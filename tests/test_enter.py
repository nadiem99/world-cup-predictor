import json
import tempfile
import unittest
from pathlib import Path

from src import common, enter, flags


class TestFlags(unittest.TestCase):
    def test_lookup_is_case_accent_punct_tolerant(self):
        self.assertEqual(flags.flag_code("United States"), "us")
        self.assertEqual(flags.flag_code("  brazil "), "br")
        self.assertEqual(flags.flag_code("Cote d'Ivoire"), "ci")
        self.assertEqual(flags.flag_code("Côte d'Ivoire"), "ci")  # accented
        self.assertEqual(flags.flag_code("England"), "gb-eng")

    def test_placeholders_have_no_flag(self):
        for ph in ("Winner E", "Runner-up A", "3rd A/B/C/D/F", "", None, "TBD"):
            self.assertIsNone(flags.flag_code(ph))


class TestEnter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.fx = root / "fixtures"
        self._orig = (enter.FIXTURES_DIR, enter.DATA_DIR)
        enter.FIXTURES_DIR = self.fx
        enter.DATA_DIR = root
        common.save_json(self.fx / "R32.json", {"round": "R32", "label": "Round of 32",
            "matches": [{"id": "R32-1", "home": "Brazil", "away": "Canada"},
                        {"id": "R32-2", "home": "Spain", "away": "Mexico"}]})
        common.save_json(root / "bracket.json", {"slots": {"R16-1": ["R32-1", "R32-2"]}})

    def tearDown(self):
        enter.FIXTURES_DIR, enter.DATA_DIR = self._orig
        self.tmp.cleanup()

    def test_gather_shape(self):
        d = enter.gather()
        self.assertEqual(sorted(d.keys()), ["bracket", "flags", "human"])
        self.assertEqual(len(d["bracket"]["r32"]), 2)
        self.assertEqual(d["bracket"]["r32"][0]["home"], "Brazil")
        self.assertEqual(d["bracket"]["slots"]["R16-1"], ["R32-1", "R32-2"])
        self.assertEqual(d["flags"]["Brazil"], "br")
        self.assertIn("slug", d["human"])

    def test_build_html_embeds_valid_json(self):
        html = enter.build_html(enter.gather())
        self.assertNotIn("/*__DATA__*/", html)
        a = html.index("window.DATA = ") + len("window.DATA = ")
        b = html.index(";\n(function", a)
        json.loads(html[a:b])  # raises if the embedded JSON is malformed


if __name__ == "__main__":
    unittest.main()
