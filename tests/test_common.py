import os
import tempfile
import unittest
from pathlib import Path

from src import common


class TestExtractJson(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(common.extract_json('{"a": 1}'), {"a": 1})

    def test_fenced(self):
        txt = "sure:\n```json\n{\"a\": 2}\n```\nbye"
        self.assertEqual(common.extract_json(txt), {"a": 2})

    def test_chatty_object(self):
        txt = 'Here you go: {"predictions": [{"id": "x"}]} done'
        self.assertEqual(common.extract_json(txt), {"predictions": [{"id": "x"}]})

    def test_array(self):
        self.assertEqual(common.extract_json("[1, 2, 3]"), [1, 2, 3])

    def test_braces_inside_string(self):
        txt = 'noise {"k": "a}b{c"} tail'
        self.assertEqual(common.extract_json(txt), {"k": "a}b{c"})

    def test_malformed_raises(self):
        with self.assertRaises(ValueError):
            common.extract_json("no json here at all")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            common.extract_json("")


class TestFirstBalanced(unittest.TestCase):
    def test_nested(self):
        self.assertEqual(common._first_balanced('x {"a": {"b": 1}} y'), '{"a": {"b": 1}}')

    def test_array(self):
        self.assertEqual(common._first_balanced("pre [1, [2]] post"), "[1, [2]]")

    def test_none(self):
        self.assertIsNone(common._first_balanced("nothing here"))


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(common.slugify("Claude Opus 4.8!"), "claude-opus-4.8")

    def test_collapses_and_trims(self):
        self.assertEqual(common.slugify("  A  B  "), "a-b")


class TestJsonIO(unittest.TestCase):
    def test_roundtrip_creates_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "x.json"
            common.save_json(p, {"a": [1, 2], "z": "ü"})
            self.assertEqual(common.load_json(p), {"a": [1, 2], "z": "ü"})

    def test_missing_returns_default(self):
        self.assertEqual(common.load_json("/no/such/file.json", default={"x": 1}), {"x": 1})


class TestLoadEnv(unittest.TestCase):
    def test_parses_and_existing_wins(self):
        key = "WCP_TEST_ENVVAR_XYZ"
        os.environ.pop(key, None)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('# a comment\n%s = "hello"\nNO_EQUALS_LINE\n' % key)
            common.load_env(p)
            self.assertEqual(os.environ.get(key), "hello")
            os.environ[key] = "kept"
            common.load_env(p)  # existing value must win
            self.assertEqual(os.environ[key], "kept")
        os.environ.pop(key, None)


if __name__ == "__main__":
    unittest.main()
