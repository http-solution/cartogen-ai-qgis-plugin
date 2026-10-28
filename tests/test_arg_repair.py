"""Windows paths whose backslash escapes were eaten before a tool saw them (1.18.4 smoke, row D6)."""
import unittest

from cartogen_ai.core.agent.arg_repair import repair_path_arguments, repair_windows_path


class TestRepairWindowsPath(unittest.TestCase):
    def test_form_feed_and_backspace_are_turned_back_into_backslash_letters(self):
        # What json.loads gives for the single-backslash text C:\smoke\fixtures\before_fixture.asc
        eaten = "C:\\smoke\x0cixtures\x08efore_fixture.asc"
        self.assertEqual(repair_windows_path(eaten), "C:\\smoke\\fixtures\\before_fixture.asc")

    def test_tab_newline_and_return_in_a_path_are_restored(self):
        self.assertEqual(repair_windows_path("D:\\data\ttables\nout\rx.csv"), "D:\\data\\ttables\\nout\\rx.csv")

    def test_a_clean_path_and_non_paths_are_untouched(self):
        for value in ("C:\\smoke\\fixtures\\a.asc", "C:/smoke/a.asc", "/home/u/a.asc", "a layer\nname", 5, None):
            self.assertEqual(repair_windows_path(value), value)

    def test_arguments_repair_strings_and_lists_but_leave_other_values(self):
        args = {"file_path": "C:\\a\x0cb.csv", "layers": ["C:\\a\x08b.asc", "plain"], "buffer_m": 500, "title": "x\ty"}
        fixed = repair_path_arguments(args)
        self.assertEqual(fixed["file_path"], "C:\\a\\fb.csv")
        self.assertEqual(fixed["layers"], ["C:\\a\\bb.asc", "plain"])
        self.assertEqual(fixed["buffer_m"], 500)
        self.assertEqual(fixed["title"], "x\ty", "a tab in ordinary text is not a path and stays")


if __name__ == "__main__":
    unittest.main()
