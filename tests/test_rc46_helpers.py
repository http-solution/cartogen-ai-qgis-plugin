"""Plain tests for the small pure helpers added in rc46 (no QGIS): timeout wording, loose layout names."""
import unittest

from cartogen_ai.core.agent.tools._background_processing import AnalysisCancelledError, AnalysisTimedOutError, timeout_message
from cartogen_ai.core.agent.tools._layout_names import resolve_layout


class _Layout:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class TestTimeoutWording(unittest.TestCase):
    def test_the_message_names_the_algorithm_and_the_limit_and_says_nothing_was_added(self):
        text = timeout_message("cellstackpercentile", 300)
        self.assertIn("cellstackpercentile", text)
        self.assertIn("300 seconds", text)
        self.assertIn("nothing was added", text)
        self.assertIn("winding down", timeout_message("x", 300, still_running=True))

    def test_a_timeout_is_a_cancellation_so_existing_handlers_still_stop_cleanly(self):
        self.assertTrue(issubclass(AnalysisTimedOutError, AnalysisCancelledError))


class TestLooseLayoutNames(unittest.TestCase):
    layouts = (_Layout("Layout_Test_Layout"), _Layout("District Map Book"))   # a tuple: shared by every test, never changed

    def test_exact_name_wins(self):
        self.assertIs(resolve_layout(self.layouts, "District Map Book"), self.layouts[1])

    def test_case_spaces_underscores_and_a_leading_layout_are_ignored(self):
        for typed in ("Test Layout", "test_layout", "TESTLAYOUT", "Layout Test Layout"):
            self.assertIs(resolve_layout(self.layouts, typed), self.layouts[0], typed)

    def test_a_name_that_fits_two_layouts_or_none_finds_nothing(self):
        two = [_Layout("Map A"), _Layout("map_a")]
        self.assertIsNone(resolve_layout(two, "mapa"))
        self.assertIsNone(resolve_layout(self.layouts, "Something else"))
        self.assertIsNone(resolve_layout(self.layouts, ""))


if __name__ == "__main__":
    unittest.main()
