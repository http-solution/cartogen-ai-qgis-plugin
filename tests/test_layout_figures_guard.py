"""Key figures on a sitrep layout must come from the data or be marked (1.18.4 smoke B8).

B8: a model read only the field names of admin_units_fixture, then typed 120,000 / 85,000 / 45,000 into create_print_layout; the layer held
94,000 / 76,000 / 52,000. The pure half is tested here without QGIS; the live half (a real layout) is in the class below and runs in CI's
QGIS job - written without a local QGIS, so CI's first run is its first execution."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cartogen_ai.core.agent.tools import layout_style as ls

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


class TestFigureGrounding(unittest.TestCase):
    POOL = ls.build_number_pool([[94000, 76000, 52000], [4000, 9000, 15000]])

    def test_numbers_are_read_at_the_precision_they_are_written(self):
        self.assertEqual(ls.parse_figure_number("94,000"), (94000.0, 0))
        self.assertEqual(ls.parse_figure_number("83.15 percent"), (83.15, 2))
        self.assertIsNone(ls.parse_figure_number("many"))

    def test_the_b8_figures_are_flagged_and_the_layer_figures_are_not(self):
        typed = [{"label": "Tur al Bahah", "value": "120,000"}, {"label": "Khormaksar", "value": "85,000"}, {"label": "Crater", "value": "45,000"}]
        self.assertEqual(ls.unverified_figure_labels(typed, self.POOL), ["Tur al Bahah", "Khormaksar", "Crater"])
        real = [{"label": "Tur al Bahah", "value": "94,000"}, {"label": "Khormaksar", "value": "76,000"}]
        self.assertEqual(ls.unverified_figure_labels(real, self.POOL), [])

    def test_a_total_or_count_of_a_numeric_field_is_grounded(self):
        total = [{"label": "All three", "value": "222,000"}, {"label": "Units", "value": "3 units"}]
        self.assertEqual(ls.unverified_figure_labels(total, self.POOL), [])

    def test_text_with_no_number_cannot_be_checked_and_is_not_flagged(self):
        self.assertEqual(ls.unverified_figure_labels([{"label": "Trend", "value": "rising"}], self.POOL), [])

    def test_an_empty_pool_flags_every_number(self):
        self.assertEqual(ls.unverified_figure_labels([{"label": "A", "value": "5"}], ls.build_number_pool([])), ["A"])

    def test_sitrep_text_marks_only_the_flagged_figure(self):
        text = ls.sitrep_body("Summary", [{"label": "A", "value": "120,000"}, {"label": "B", "value": "94,000"}], None, "", unverified_labels=["A"])
        lines = {line for line in text.splitlines() if line.startswith("- ")}
        self.assertIn("- A: 120,000 " + ls.UNVERIFIED_FIGURE_MARK, lines)
        self.assertIn("- B: 94,000", lines)

    def test_figures_from_rows_takes_the_largest_first_and_formats_them(self):
        rows = [("Crater", 52000), ("Khormaksar", 76000), ("Tur al Bahah", 94000), ("Habil Jabr", 12000.5)]
        self.assertEqual(ls.figures_from_rows(rows, 3), [{"label": "Tur al Bahah", "value": "94,000"}, {"label": "Khormaksar", "value": "76,000"},
                                                        {"label": "Crater", "value": "52,000"}])
        self.assertEqual(ls.figures_from_rows(rows, 1, "lowest"), [{"label": "Habil Jabr", "value": "12,000.50"}])

    def test_figures_from_rows_ignores_missing_numbers(self):
        self.assertEqual(ls.figures_from_rows([("A", None), ("B", 3)], 5), [{"label": "B", "value": "3"}])


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestSitrepLayoutMarksUnverifiedFigures(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=people_in_need:integer", "districts", "memory")
        feats = []
        for i, (name, need) in enumerate([("Crater", 52000), ("Khormaksar", 76000), ("Tur al Bahah", 94000)]):
            f = QgsFeature(layer.fields())
            x = 44.0 + i * 0.1
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 15, {x + 0.09} 15, {x + 0.09} 15.09, {x} 15.09, {x} 15))"))
            f.setAttributes([name, need])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)

    def _body(self, result):
        self.assertTrue(result.get("success"), result)
        layout = QgsProject.instance().layoutManager().layoutByName(result["layout_name"])
        return layout.itemById("BODY_TEXT").text()

    def test_typed_figures_that_are_not_in_the_layer_are_marked_and_reported(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        result = create_print_layout("Figures", template="sitrep", body_text="Summary", key_figures=[
            {"label": "Wrong", "value": "120,000", "source": "memory"}, {"label": "Right", "value": "94,000", "source": "layer"}])
        body = self._body(result)
        self.assertIn("Wrong: 120,000 (memory) " + ls.UNVERIFIED_FIGURE_MARK, body)
        self.assertNotIn("Right: 94,000 (layer) " + ls.UNVERIFIED_FIGURE_MARK, body)
        self.assertIn("Wrong", result["sitrep_warning"])

    def test_key_figures_from_reads_the_numbers_from_the_layer_and_marks_nothing(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        result = create_print_layout("From layer", template="sitrep", body_text="Summary", key_figures_from={
            "layer_name": "districts", "label_field": "name", "value_field": "people_in_need", "top_n": 3})
        body = self._body(result)
        for line in ("Tur al Bahah: 94,000", "Khormaksar: 76,000", "Crater: 52,000"):
            self.assertIn(line, body)
        self.assertNotIn(ls.UNVERIFIED_FIGURE_MARK, body)

    def test_key_figures_from_names_a_missing_field(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        result = create_print_layout("Bad field", template="sitrep", key_figures_from={
            "layer_name": "districts", "label_field": "name", "value_field": "nope"})
        self.assertIn("'nope' is not a field", result["error"])
        self.assertIn("people_in_need", result["error"])


if __name__ == "__main__":
    unittest.main()
