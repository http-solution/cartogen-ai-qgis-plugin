"""ML-1: the review sheet for the Arabic and French phrases, and the importer for the reviewed sheet (tools/language_review.py).

Why: the phrases were written by the assistant and have not been read by a fluent speaker. A reviewer works in a plain CSV (what the tool does,
the phrase, a verdict), never in JSON, and the marked sheet must apply cleanly or not at all."""
import importlib.util
import json
import os
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import fold

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTERED = {t["function"]["name"] for t in TOOLS_SCHEMA}
FOLDED_LEN = lambda text: len(fold(text).strip())     # noqa: E731


def _tool():
    spec = importlib.util.spec_from_file_location("language_review", os.path.join(ROOT, "tools", "language_review.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestLanguageReviewTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = _tool()
        cls.table = cls.tool._load()

    def _row(self, lang, tool, phrase="", verdict="", correction=""):
        return {"language": lang, "tool": tool, "what_it_does": "", "phrase": phrase, "verdict": verdict, "correction": correction, "note": ""}

    def test_the_sheet_has_one_row_per_phrase_with_an_english_description(self):
        rows = self.tool.export_rows(self.table, self.tool._tool_descriptions())
        self.assertEqual(len(rows), sum(len(p) for t in self.table.values() for p in t.values()))
        self.assertTrue(all(r["what_it_does"] for r in rows), "every tool needs a description a reviewer can read")
        self.assertTrue(all(r["verdict"] == "" for r in rows))

    def test_an_unmarked_sheet_changes_nothing(self):
        rows = self.tool.export_rows(self.table, {})
        new, problems = self.tool.apply_rows(self.table, rows, REGISTERED, FOLDED_LEN)
        self.assertEqual((new, problems), (self.table, []))

    def test_fix_remove_and_add(self):
        ar = self.table["ar"]["toggle_visibility"]
        fr = self.table["fr"]["toggle_visibility"]
        rows = [self._row("ar", "toggle_visibility", ar[0], "FIX", "اخف الطبقة الان"),
                self._row("ar", "toggle_visibility", ar[1], "REMOVE"),
                self._row("fr", "toggle_visibility", "", "ADD", "cache la couche")]
        new, problems = self.tool.apply_rows(self.table, rows, REGISTERED, FOLDED_LEN)
        self.assertEqual(problems, [])
        self.assertIn("اخف الطبقة الان", new["ar"]["toggle_visibility"])
        self.assertNotIn(ar[0], new["ar"]["toggle_visibility"])
        self.assertNotIn(ar[1], new["ar"]["toggle_visibility"])
        self.assertEqual(new["fr"]["toggle_visibility"], [*fr, "cache la couche"])
        self.assertEqual(self.table["ar"]["toggle_visibility"], ar, "the input table must not be changed")

    def test_a_bad_sheet_is_refused_whole(self):
        phrase = self.table["ar"]["get_crs"][0]
        cases = {
            "unknown verdict": self._row("ar", "get_crs", phrase, "MAYBE"),
            "unregistered tool": self._row("ar", "no_such_tool", "", "ADD", "عبارة طويلة"),
            "too short once folded": self._row("ar", "get_crs", "", "ADD", "ال"),
            "empty fix": self._row("ar", "get_crs", phrase, "FIX", ""),
            "phrase not in the file": self._row("ar", "get_crs", "not there", "REMOVE"),
        }
        for label, row in cases.items():
            _new, problems = self.tool.apply_rows(self.table, [row], REGISTERED, FOLDED_LEN)
            self.assertTrue(problems, label)

    def test_removing_the_last_phrase_of_one_language_is_refused(self):
        rows = [self._row("fr", "get_crs", p, "REMOVE") for p in self.table["fr"]["get_crs"]]
        _new, problems = self.tool.apply_rows(self.table, rows, REGISTERED, FOLDED_LEN)
        self.assertTrue(any("same tools" in p for p in problems), problems)

    def test_the_file_is_written_in_the_format_the_tool_reads(self):
        text = self.tool.DATA.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
