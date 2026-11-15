"""Round-2 row A1 (2026-11-05): the report said content = frame for legends that were visibly cut. Real QGIS (CI live job; written without a QGIS install, so CI's
first run is its first execution): with far more entries than the frame holds, the legend must be MEASURED (not the frame answering for itself), and the report
must agree with what was done: it fits, or layers were dropped and the title says so."""
import unittest

from tests.test_layout_fit_live import QGIS_LIVE_AVAILABLE, TestLayoutFitsItsFrames

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsProject


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestTheLegendIsMeasured(TestLayoutFitsItsFrames):
    # inherits setUpClass / helpers only; the inherited tests are not re-run here (see load_tests)
    def test_many_entries_are_measured_and_the_report_matches_the_page(self):
        for size, orientation in (("A4", "Landscape"), ("A3", "Portrait")):
            with self.subTest(size=size, orientation=orientation):
                QgsProject.instance().clear()
                self._layers(7, 14)
                check = self._make(page_size=size, page_orientation=orientation)["legend_check"]
                self.assertTrue(check["measured"], check)
                self.assertGreater(check["content_mm"], 0, check)
                if check["fits"]:
                    self.assertLessEqual(check["content_mm"], check["frame_mm"] + 0.5, check)
                else:
                    self.assertGreater(check["content_mm"], check["frame_mm"] + 0.5, check)


    def test_two_columns_are_shorter_than_one_and_the_report_names_what_the_item_has(self):
        # Self-audit 2026-11-06: CI proved the measurement is real but nothing showed that more columns shorten the legend.
        from cartogen_ai.core.agent.tools.layout_style import measure_legend_size
        self._layers(1, 14)
        res = self._make(page_size="A3", page_orientation="Portrait")
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        leg = layout.itemById("LEGEND")
        self.assertEqual(leg.columnCount(), res["legend_check"]["columns"], res["legend_check"])
        leg.setColumnCount(1)
        one = measure_legend_size(leg, layout)[1]
        leg.setColumnCount(2)
        leg.setSplitLayer(True)
        two = measure_legend_size(leg, layout)[1]
        self.assertLess(two, one, (one, two))


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name in ("test_many_entries_are_measured_and_the_report_matches_the_page",
                 "test_two_columns_are_shorter_than_one_and_the_report_names_what_the_item_has"):
        suite.addTests(loader.loadTestsFromName(name, TestTheLegendIsMeasured))
    return suite


if __name__ == "__main__":
    unittest.main()
