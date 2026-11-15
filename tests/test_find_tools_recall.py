"""find_tools finds the right tool when the model describes the operation in plain English (the PLAN-043 fallback, RT-1).

Why: the router misses a needed tool on about half of long multi-step requests it has not seen (10 of 20 in tests/fixtures/routing_blind_long_2.json),
and rule 56 tells the model to call find_tools then. That only helps if find_tools finds the tool. Measured 2026-11-01, top 5 results (the most
the agent loop keeps per call): 26 of 30 blind needs before the synonym table, 29 of 30 after; a "colour ... by value" need never reached
apply_graduated_style because no tool name or description says "colour".

Two sets in tests/fixtures/find_tools_needs.json. "blind": 30 needs written before the synonym table existed. "designed": 17 needs the table was
built against after they failed, so their result is NOT evidence of generalisation. The needs are the assistant's guess at how a model would phrase
a step; no real model was run."""
import json
import unittest
from pathlib import Path

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools.tool_discovery import expand_words, rank_tools

ROWS = json.loads((Path(__file__).resolve().parent / "fixtures" / "find_tools_needs.json").read_text(encoding="utf-8"))
REGISTERED = {t["function"]["name"] for t in TOOLS_SCHEMA}
TOP = 5            # the agent loop keeps at most MAX_FOUND_TOOLS_PER_CALL = 5 of the results


def _hits(set_name):
    rows = [r for r in ROWS if r["set"] == set_name]
    found = sum(bool(set(r["tools"]) & {n for _s, n, _d in rank_tools(r["need"], TOOLS_SCHEMA, limit=TOP)}) for r in rows)
    return found, len(rows)


class TestFindToolsRecall(unittest.TestCase):
    def test_every_tool_named_is_registered(self):
        for row in ROWS:
            self.assertLessEqual(set(row["tools"]), REGISTERED, row["need"])

    def test_blind_needs_are_found_in_the_top_five(self):
        found, total = _hits("blind")
        self.assertEqual(total, 30)
        self.assertGreaterEqual(found, 29, "was 26 of 30 before the synonym table")

    def test_designed_against_needs_are_found_in_the_top_five(self):
        found, total = _hits("designed")
        self.assertEqual(total, 17)
        self.assertGreaterEqual(found, 16, "was 10 of 17 before the synonym table (these were used to build it)")

    def test_a_plain_colour_word_reaches_the_style_tools(self):
        names = [n for _s, n, _d in rank_tools("colour the districts by population", TOOLS_SCHEMA, limit=5)]
        self.assertIn("apply_graduated_style", names)

    def test_synonym_expansion_keeps_the_original_words(self):
        expanded = expand_words({"colour", "districts"})
        self.assertLessEqual({"colour", "districts", "graduated", "style"}, expanded)
        self.assertEqual(expand_words({"zzz"}), {"zzz"})


if __name__ == "__main__":
    unittest.main()
