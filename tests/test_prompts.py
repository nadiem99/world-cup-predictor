import unittest

from src import prompts

MATCHES = [
    {"id": "R32-1", "home": "South Africa", "away": "Canada"},
    {"id": "R32-2", "home": "USA", "away": "Mexico"},
]


class TestBracket(unittest.TestCase):
    def test_prompt_lists_matchups(self):
        p = prompts.bracket_prompt(MATCHES)
        self.assertIn("South Africa vs Canada", p)

    def test_parse(self):
        txt = ('{"R16":["Canada","USA"],"QF":["Canada"],"SF":[],"F":[],'
               '"champion":"Canada","third":""}')
        r = prompts.parse_bracket(txt)
        self.assertEqual(r["R16"], ["Canada", "USA"])
        self.assertEqual(r["QF"], ["Canada"])
        self.assertEqual(r["champion"], "Canada")
        self.assertEqual(r["third"], "")

    def test_parse_double_encoded(self):
        inner = '{"R16":["Canada"],"QF":[],"SF":[],"F":[],"champion":"Canada","third":""}'
        txt = __import__("json").dumps(inner)
        r = prompts.parse_bracket(txt)
        self.assertEqual(r["R16"], ["Canada"])
        self.assertEqual(r["champion"], "Canada")

    def test_parse_non_object_raises(self):
        # a bare JSON array is not a valid bracket — raise cleanly, don't crash
        with self.assertRaises(ValueError):
            prompts.parse_bracket('["Canada","USA"]')


if __name__ == "__main__":
    unittest.main()
