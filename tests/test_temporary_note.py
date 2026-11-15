"""PLAN-021 WP-F (#120), no QGIS needed: the sentence that says a layer is only temporary."""
import unittest

from cartogen_ai.core.agent.results_store import temporary_note


class TestTemporaryNote(unittest.TestCase):
    def test_a_kept_layer_gets_no_note(self):
        self.assertEqual(temporary_note({"persisted": True, "path": "p.gpkg", "table": "t"}), "")

    def test_an_unsaved_project_is_named_as_the_reason(self):
        note = temporary_note({"persisted": False, "reason": "the project has not been saved yet; save it to keep analysis results"})
        self.assertIn("temporary", note)
        self.assertIn("has not been saved yet", note)
        self.assertIn("export_layer", note)

    def test_anything_else_still_says_temporary(self):
        self.assertIn("temporary", temporary_note({"persisted": False}))
        self.assertIn("temporary", temporary_note(None))


if __name__ == "__main__":
    unittest.main()
