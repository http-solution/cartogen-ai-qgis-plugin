"""DEF-9 (round-3 smoke, every row): the evidence collector's log_cartogenai.txt and log_all.txt were empty (37 of 41 files) on QGIS 4.2.3 although the
signal was connected. QGIS 4 hands the slot a PyQt6 enum for the message level, and `int()` of a plain enum raises TypeError, which the collector's slot
did before it appended anything. The slot must record the line whatever the level object is."""
import enum
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import collect_evidence as ce  # noqa: E402


class _PlainEnumLevel(enum.Enum):
    """Like Qgis.MessageLevel under PyQt6: an Enum, not an IntEnum, so int(level) raises."""
    Info = 0
    Warning = 1
    Critical = 2


class TestOnMessage(unittest.TestCase):
    def setUp(self):
        self._saved = list(ce._STATE["lines"])
        ce._STATE["lines"].clear()
        ce._STATE.pop("previous", None)
        self.addCleanup(lambda: (ce._STATE["lines"].clear(), ce._STATE["lines"].extend(self._saved)))

    def test_a_plain_enum_level_is_recorded_with_its_value(self):
        ce._on_message("hello", "CartogenAI", _PlainEnumLevel.Critical)
        self.assertEqual(len(ce._STATE["lines"]), 1)
        _time, tag, level, message = ce._STATE["lines"][0]
        self.assertEqual((tag, level, message), ("CartogenAI", 2, "hello"))

    def test_an_int_level_still_works(self):
        ce._on_message("x", "Agent", 1)
        self.assertEqual(ce._STATE["lines"][0][2], 1)

    def test_an_unreadable_level_still_records_the_line(self):
        ce._on_message("y", "Tools", object())
        self.assertEqual(len(ce._STATE["lines"]), 1)
        self.assertEqual(ce._STATE["lines"][0][3], "y")

    def test_the_call_never_raises(self):
        for n, level in enumerate((None, "info", 3.5, _PlainEnumLevel.Info)):
            ce._on_message(f"z{n}", "t", level)
        self.assertEqual(len(ce._STATE["lines"]), 4)

    def test_the_same_line_arriving_through_a_second_connection_is_recorded_once(self):
        ce._STATE.pop("previous", None)
        ce._on_message("dup", "CartogenAI", 0)
        ce._on_message("dup", "CartogenAI", 0)
        self.assertEqual(len(ce._STATE["lines"]), 1)
        ce._on_message("other", "CartogenAI", 0)
        self.assertEqual(len(ce._STATE["lines"]), 2)

    def test_a_repeated_line_a_moment_later_is_a_new_line(self):
        import datetime
        ce._STATE.pop("previous", None)
        ce._on_message("again", "Agent", 0)
        line, _when = ce._STATE["previous"]
        ce._STATE["previous"] = (line, datetime.datetime.now() - datetime.timedelta(seconds=1))
        ce._on_message("again", "Agent", 0)
        self.assertEqual(len(ce._STATE["lines"]), 2)


if __name__ == "__main__":
    unittest.main()
