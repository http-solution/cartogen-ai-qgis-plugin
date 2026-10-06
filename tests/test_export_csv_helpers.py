# -*- coding: utf-8 -*-
"""CSV export helpers (rc7 smoke test F13): UTF-8 BOM for Excel, X/Y columns for point layers."""
import csv
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools import export_tools as et


class TestCsvHelpers(unittest.TestCase):
    def _tmp(self, data):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.addCleanup(os.remove, path)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_bom_is_added_once(self):
        path = self._tmp("name\nصنعاء\n".encode("utf-8"))
        self.assertIsNone(et._ensure_utf8_bom(path))
        self.assertIsNone(et._ensure_utf8_bom(path))
        raw = open(path, "rb").read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf\xef\xbb\xbf"))
        self.assertIn("صنعاء", raw.decode("utf-8-sig"))

    def test_sanitizer_still_finds_the_first_column_after_a_bom(self):
        path = self._tmp(b"\xef\xbb\xbfname,x\n=cmd,1\n")
        self.assertIsNone(et._sanitize_csv_formula_injection(path, {"name"}))
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[1][0], "'=cmd")

    def test_geometry_option(self):
        self.assertEqual(et._csv_geometry_option(True), "AS_XY")
        self.assertEqual(et._csv_geometry_option(True, wkt_geometry=True), "AS_WKT")
        self.assertEqual(et._csv_geometry_option(False), "AS_WKT")


if __name__ == "__main__":
    unittest.main()


class TestDashboardHelpers(unittest.TestCase):
    def test_default_path_is_readable_and_timestamped(self):
        import datetime
        path = et._dashboard_output_path("Health Access: Sanaa", now=datetime.datetime(2026, 9, 30, 12, 1, 2))
        name = os.path.basename(path)
        self.assertEqual(name, "Health Access_ Sanaa_20260930_120102.html")
        self.assertNotIn("tmp", name)

    def test_two_dashboards_with_one_title_in_one_second_do_not_overwrite_each_other(self):
        import datetime
        import tempfile
        from unittest import mock
        folder = tempfile.mkdtemp()
        now = datetime.datetime(2026, 9, 30, 12, 1, 2)
        with mock.patch.object(et, "_default_export_dir", return_value=folder):
            first = et._dashboard_output_path("Same", now=now)
            with open(first, "w") as handle:
                handle.write("first")
            second = et._dashboard_output_path("Same", now=now)
            with open(second, "w") as handle:
                handle.write("second")
            third = et._dashboard_output_path("Same", now=now)
        self.assertEqual(len({first, second, third}), 3)
        self.assertTrue(second.endswith("_2.html"))
        with open(first) as handle:
            self.assertEqual(handle.read(), "first")

    def test_notices_are_placed_inside_the_html_and_escaped(self):
        out = et._inject_notices("<html><body>x</body></html>", ["'Roads': showing 2,500 of 139,758 <features>"])
        self.assertIn("showing 2,500 of 139,758 &lt;features&gt;", out)
        self.assertLess(out.index("showing"), out.index("</body>"))

    def test_no_notices_leaves_html_untouched(self):
        self.assertEqual(et._inject_notices("<body></body>", []), "<body></body>")
