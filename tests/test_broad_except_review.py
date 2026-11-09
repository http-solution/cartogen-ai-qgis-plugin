"""DEF-8: the broad-exception classifier (tools/broad_except_review.py) and the ratchet on what it finds. A handler that does nothing but pass, continue or break
makes a failure vanish; none exists and none may be added. Handlers that swallow an error and return a default are the review list, and its size may only shrink."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import broad_except_review as ber  # noqa: E402

# Counts on 2026-11-09 (551 broad handlers in src/). Lower these when handlers are fixed; never raise them.
MAX_SWALLOW_AND_RETURN = 219


def _handler(code):
    return next(n for n in ast.walk(ast.parse(code)) if isinstance(n, ast.ExceptHandler))


class TestClassify(unittest.TestCase):
    def test_each_class(self):
        cases = {
            "try:\n  x()\nexcept Exception:\n  raise": "reraises",
            "try:\n  x()\nexcept Exception as e:\n  return {'error': str(e)}": "uses_error",
            "try:\n  x()\nexcept Exception:\n  log_event('failed')": "logs",
            "try:\n  x()\nexcept Exception:\n  return None": "returns",
            "try:\n  x()\nexcept Exception:\n  pass": "silent",
            "try:\n  x()\nexcept Exception:\n  continue": "silent",
        }
        for code, expected in cases.items():
            self.assertEqual(ber.classify(_handler(code)), expected, code)

    def test_only_broad_handlers_are_counted(self):
        self.assertTrue(ber._is_broad(_handler("try:\n  x()\nexcept Exception:\n  pass")))
        self.assertTrue(ber._is_broad(_handler("try:\n  x()\nexcept:\n  pass")))
        self.assertTrue(ber._is_broad(_handler("try:\n  x()\nexcept (ValueError, Exception):\n  pass")))
        self.assertFalse(ber._is_broad(_handler("try:\n  x()\nexcept ValueError:\n  pass")))


class TestTheSourceTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.counts, cls.found, cls.suppress = ber.scan()

    def test_no_broad_handler_makes_a_failure_vanish(self):
        silent = [where for kind, where in self.found if kind == "silent"]
        self.assertEqual(silent, [], "a broad handler that only passes, continues or breaks: use contextlib.suppress on purpose, or log it")

    def test_the_swallow_and_return_list_does_not_grow(self):
        self.assertLessEqual(self.counts.get("returns", 0), MAX_SWALLOW_AND_RETURN,
                             "a new broad handler returns a default without logging or reading the error; log it with log_event, or lower the pin if you removed one")


if __name__ == "__main__":
    unittest.main()
