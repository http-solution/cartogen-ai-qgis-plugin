"""PLAN-023 R11-5: the bounded text excerpt of a file-information report, and the membership of the chart and information families. Offline: no QGIS needed."""
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools import _processing_allowlist as allow
from cartogen_ai.core.agent.tools.processing_allowlist_tools import REPORT_EXCERPT_CHARS, _with_report_fields, report_excerpt


def _file(text):
    handle, path = tempfile.mkstemp(suffix=".html")
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class TestExcerpt(unittest.TestCase):
    def test_the_pre_wrapper_and_entities_are_removed(self):
        path = _file("<pre>Driver: GTiff/GeoTIFF\nSize is 40, 40 &lt;ok&gt; &amp; more</pre>")
        self.addCleanup(os.remove, path)
        self.assertEqual(report_excerpt(path), ("Driver: GTiff/GeoTIFF\nSize is 40, 40 <ok> & more", False))

    def test_a_long_report_is_cut_at_the_limit_and_says_so(self):
        path = _file("<pre>" + "x" * (REPORT_EXCERPT_CHARS + 500) + "</pre>")
        self.addCleanup(os.remove, path)
        text, truncated = report_excerpt(path)
        self.assertEqual((len(text), truncated), (REPORT_EXCERPT_CHARS, True))

    def test_a_missing_file_gives_none_not_an_error(self):
        self.assertIsNone(report_excerpt(os.path.join(tempfile.gettempdir(), "no_such_cartogen_report.html")))

    def test_only_information_reports_get_an_excerpt(self):
        path = _file("<pre>Driver: GPKG</pre>")
        self.addCleanup(os.remove, path)
        info = _with_report_fields({"alg_id": "gdal:ogrinfo", "success": True}, None, {"OUTPUT": path})
        self.assertEqual(info["report_text"], "Driver: GPKG")
        chart = _with_report_fields({"alg_id": "qgis:barplot", "success": True}, None, {"OUTPUT": path})
        self.assertNotIn("report_text", chart)
        self.assertIn("report_files", chart)


class TestFamilies(unittest.TestCase):
    def test_eight_charts_and_three_information_reports_are_approved(self):
        self.assertEqual((len(allow.PLOT_FAMILY), len(allow.INFO_FAMILY)), (8, 3))
        for alg_id in (*allow.PLOT_FAMILY, *allow.INFO_FAMILY):
            self.assertIn(alg_id, allow.ALLOWED_ALGORITHM_IDS)

    def test_the_two_ids_the_probe_did_not_clear_are_not_approved(self):
        self.assertNotIn("gdal:dataset_identify", allow.ALLOWED_ALGORITHM_IDS)
        self.assertNotIn("native:generateelevationprofileimage", allow.ALLOWED_ALGORITHM_IDS)


if __name__ == "__main__":
    unittest.main()
