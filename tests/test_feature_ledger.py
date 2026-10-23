"""The feature ledger (docs/FEATURE_LEDGER.json) lists work that was finished and must not be broken again. This test keeps the ledger honest:
every source file it names exists, every guard test it names still exists (found by parsing the test file, so a deleted or renamed guard fails
here instead of silently leaving a feature unprotected), and every entry says what has and has not been hand-verified."""
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = json.loads((ROOT / "docs" / "FEATURE_LEDGER.json").read_text(encoding="utf-8"))["features"]


def _test_exists(reference):
    """'tests/x.py::Class::test_name' or 'tests/x.py::test_name' or 'tests/x.py::Class' (a whole class)."""
    path, *names = reference.split("::")
    file = ROOT / path
    if not file.is_file():
        return False
    node = ast.parse(file.read_text(encoding="utf-8"))
    for name in names:
        children = [c for c in ast.iter_child_nodes(node) if isinstance(c, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and c.name == name]
        if not children:
            return False
        node = children[0]
    return True


class TestFeatureLedger(unittest.TestCase):
    def test_ids_are_unique_and_entries_complete(self):
        ids = [e["id"] for e in LEDGER]
        self.assertEqual(len(ids), len(set(ids)))
        for entry in LEDGER:
            for key in ("id", "feature", "since", "sources", "guards", "hand_verified"):
                self.assertTrue(entry.get(key), f"{entry.get('id')}: missing {key}")

    def test_every_source_file_exists(self):
        missing = [f"{e['id']}: {s}" for e in LEDGER for s in e["sources"] if not (ROOT / s).exists()]
        self.assertEqual(missing, [])

    def test_every_guard_test_still_exists(self):
        missing = [f"{e['id']}: {g}" for e in LEDGER for g in e["guards"] if not _test_exists(g)]
        self.assertEqual(missing, [], "a guard test was deleted or renamed: restore it or update the ledger in the same change")

    def test_hand_verified_is_never_an_empty_claim(self):
        for entry in LEDGER:
            self.assertGreater(len(entry["hand_verified"]), 8, entry["id"])


if __name__ == "__main__":
    unittest.main()
