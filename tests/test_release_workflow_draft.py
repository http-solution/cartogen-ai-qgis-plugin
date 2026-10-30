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


if __name__ == "__main__":
    unittest.main()
