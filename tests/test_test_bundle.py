"""The hand-test bundle must be precise: only open-issue rows whose issue is still open, nothing already closed with evidence."""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _builder():
    spec = importlib.util.spec_from_file_location("build_lean_bundle", ROOT / "tools" / "build_lean_bundle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestBundleSelection(unittest.TestCase):
    def test_only_rows_of_open_issues_are_selected(self):
        builder = _builder()
        open_numbers = builder.open_issue_numbers()
        self.assertIn(150, open_numbers)        # still open after the rc48 hand test
        self.assertNotIn(75, open_numbers)      # closed with evidence at rc40
        self.assertNotIn(80, open_numbers)      # closed on a hand-verified pass, rc48
        for row in builder.open_issue_rows():
            if row["id"] in builder.SETUP_ROWS:
                continue
            cited = {int(n) for n in re.findall(r"#(\d+)", row["source"].split("(")[0])}
            self.assertTrue(cited & open_numbers, f"{row['id']} tests only closed issues: {row['source']}")

    def test_set_up_rows_come_first_and_umbrellas_never_appear(self):
        builder = _builder()
        ids = [r["id"] for r in builder.open_issue_rows()]
        self.assertEqual(ids[:2], list(builder.SETUP_ROWS))
        self.assertNotIn("OI-233", ids)

    def test_every_input_file_a_selected_row_names_is_in_the_inputs_folder(self):
        builder = _builder()
        available = {p.name for p in builder.INPUTS.iterdir()}
        for row in builder.open_issue_rows():
            for name in re.findall(r"smoke_[A-Za-z_]+\.[a-z]+", row["inputs_used"]):
                self.assertIn(name, available, f"{row['id']} needs {name}")


if __name__ == "__main__":
    unittest.main()


class TestPreciseMode(unittest.TestCase):
    def test_the_precise_file_takes_only_the_p_rows_of_the_release_part(self):
        """--precise leaves out the rc48 re-checks (E2c rows), the rc44 tool rows and the plain-language sample: only rows nobody has seen yet."""
        builder = _builder()
        precise = [row for row in builder.EXTRA_ROWS if row[0].startswith("P")]
        self.assertGreaterEqual(len(precise), 20)
        self.assertFalse([row for row in precise if row[0].startswith("E")])
        self.assertTrue([row for row in builder.EXTRA_ROWS if row[0].startswith("E2c")], "the E2c rows exist and must stay out of the precise file")
        self.assertIn("P17 disclaimer", [row[0] for row in precise])
        self.assertIn("P16 lineage", [row[0] for row in precise])
