import unittest

from src import prompts

MATCHES = [
    {"id": "R32-1", "home": "South Africa", "away": "Canada"},
    {"id": "R32-2", "home": "USA", "away": "Mexico"},
]


class TestRoundPrompt(unittest.TestCase):
    def test_includes_fixtures_and_ids(self):
        p = prompts.round_prompt("Round of 32", MATCHES)
        self.assertIn("South Africa vs Canada", p)
        self.assertIn("R32-2", p)


class TestParseRound(unittest.TestCase):
    def test_basic(self):
        txt = '{"predictions":[{"id":"R32-1","home_goals":0,"away_goals":2,"advances":"Canada"}]}'
        out = prompts.parse_round(txt, MATCHES)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["home"], "South Africa")
        self.assertEqual(out[0]["away"], "Canada")

    def test_locks_names_and_coerces_ints(self):
        # model returns wrong team names and string goals; parser fixes both
        txt = ('{"predictions":[{"id":"R32-1","home":"X","away":"Y",'
               '"home_goals":"1","away_goals":"3","advances":"Canada"}]}')
        out = prompts.parse_round(txt, MATCHES)
        self.assertEqual(out[0]["home"], "South Africa")
        self.assertEqual(out[0]["away"], "Canada")
        self.assertEqual(out[0]["home_goals"], 1)
        self.assertIsInstance(out[0]["home_goals"], int)

    def test_ignores_unknown_and_dedups(self):
        txt = ('{"predictions":['
               '{"id":"R32-1","home_goals":1,"away_goals":0,"advances":"South Africa"},'
               '{"id":"R32-1","home_goals":2,"away_goals":2,"advances":"Canada"},'
               '{"id":"ZZ","home_goals":0,"away_goals":0,"advances":"Q"}]}')
        out = prompts.parse_round(txt, MATCHES)
        self.assertEqual([o["id"] for o in out], ["R32-1"])  # first kept, dup + unknown dropped
        self.assertEqual(out[0]["home_goals"], 1)

    def test_array_form(self):
        txt = '[{"id":"R32-2","home_goals":1,"away_goals":1,"advances":"USA"}]'
        out = prompts.parse_round(txt, MATCHES)
        self.assertEqual(out[0]["advances"], "USA")

    def test_double_encoded_json_string(self):
        # some models return the JSON as a quoted string; we recover the payload
        inner = '{"predictions":[{"id":"R32-1","home_goals":1,"away_goals":0,"advances":"South Africa"}]}'
        txt = __import__("json").dumps(inner)  # a JSON string whose value is JSON
        out = prompts.parse_round(txt, MATCHES)
        self.assertEqual(out[0]["advances"], "South Africa")

    def test_non_json_object_raises_valueerror(self):
        with self.assertRaises(ValueError):
            prompts.parse_round('"just a string"', MATCHES)


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
