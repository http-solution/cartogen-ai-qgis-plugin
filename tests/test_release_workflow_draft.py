"""release.yml creates drafts by default: a published release emails every repo watcher (owner report, 2026-10-30)."""
import pathlib
import unittest

WORKFLOW = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"


class TestReleaseIsDraftByDefault(unittest.TestCase):
    def test_draft_input_defaults_to_true_and_is_passed_to_gh(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        block = text.split("      draft:", 1)[1].split("permissions:", 1)[0]
        self.assertIn("default: true", block)
        self.assertIn('inputs.draft }}" = "true"', text)
        self.assertIn("--draft", text)


class TestStatusNote(unittest.TestCase):
    def test_the_note_is_an_optional_input_passed_through_the_environment(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        block = text.split("      status_note:", 1)[1].split("      draft:", 1)[0]
        self.assertIn('default: ""', block)
        self.assertIn("STATUS_NOTE: ${{ inputs.status_note }}", text)
        self.assertNotIn("${{ inputs.status_note }}\"", text.split("run: |", 2)[-1])   # never expanded inside the script body
        self.assertIn('NOTES="$NOTES"', text)


if __name__ == "__main__":
    unittest.main()
