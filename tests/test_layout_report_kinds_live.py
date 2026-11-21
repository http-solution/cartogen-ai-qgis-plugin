"""Live run of the field_report and change_report layouts (PLAN-023 R3-6): the text panel of a real layout is read back. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestReportLayouts(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=mean_ndvi:double&field=lost_ha:integer", "fields", "memory")
        feats = []
        for i, (name, ndvi, lost) in enumerate([("North", 0.54, 12), ("South", 0.41, 30)]):
            f = QgsFeature(layer.fields())
            x = 44.0 + i * 0.1
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 15, {x + 0.09} 15, {x + 0.09} 15.09, {x} 15.09, {x} 15))"))
            f.setAttributes([name, ndvi, lost])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)

    def _body(self, result):
        self.assertTrue(result.get("success"), result)
        layout = QgsProject.instance().layoutManager().layoutByName(result["layout_name"])
        return layout.itemById("BODY_TEXT").text()

    def test_a_field_report_has_its_headings_the_figures_from_the_layer_and_the_no_rate_note(self):
        from cartogen_ai.core.agent.tools import layout_style as ls
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        result = create_print_layout("Field report: North", template="field_report", body_text="North field, wheat, sown in March",
                                     key_figures_from={"layer_name": "fields", "label_field": "name", "value_field": "mean_ndvi", "top_n": 2}, sources=["Earth Search Sentinel-2 L2A"])
        body = self._body(result)
        self.assertEqual(result["template"], "field_report")
        self.assertTrue(body.startswith("FIELD\nNorth field, wheat"), body)
        for expected in ("INDEX READINGS", "North: 0.54", "South: 0.41", "HOW TO READ THIS MAP\n" + ls.FIELD_REPORT_GUIDE, "SOURCES\nEarth Search Sentinel-2 L2A", "NOTE\n" + ls.FIELD_REPORT_NOTE):
            self.assertIn(expected, body)
        for absent in ("SITUATION", "KEY FIGURES", "HANDLING", ls.UNVERIFIED_FIGURE_MARK):
            self.assertNotIn(absent, body)

    def test_a_typed_figure_that_is_not_in_the_data_is_marked_in_a_field_report(self):
        from cartogen_ai.core.agent.tools import layout_style as ls
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        result = create_print_layout("Field", template="field_report", body_text="North", key_figures=[{"label": "Mean NDVI", "value": "0.99", "source": "memory"}])
        self.assertIn("Mean NDVI: 0.99 (memory) " + ls.UNVERIFIED_FIGURE_MARK, self._body(result))
        self.assertIn("Mean NDVI", result["sitrep_warning"])

    def test_an_epi_bulletin_leaves_out_a_typed_figure_that_is_not_in_the_data(self):
        """LR-3, row C25 of the 2026-11-20 live run: a top-3 of 20 and 18 cases was printed against a maximum of 15. A bulletin carries no unverified number."""
        from cartogen_ai.core.agent.tools import layout_style as ls
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        result = create_print_layout("Epidemic bulletin", template="epi_bulletin", body_text="Cases reported to 2026-11-08",
                                     key_figures=[{"label": "Worst district", "value": "99"}, {"label": "Lost area", "value": "30"}])
        body = self._body(result)
        self.assertNotIn("Worst district", body)
        self.assertNotIn("99", body)
        self.assertIn("Lost area: 30", body)               # 30 is the real largest value of lost_ha in the fixture layer
        self.assertNotIn(ls.UNVERIFIED_FIGURE_MARK, body)
        self.assertIn("LEFT OUT", result["sitrep_warning"])
        self.assertIn("Worst district", result["sitrep_warning"])

    def test_an_identifier_column_does_not_ground_a_typed_figure(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=fid:integer&field=cases:integer", "ids", "memory")
        feats = []
        for i in range(1, 51):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({i} 0, {i + 0.5} 0, {i + 0.5} 0.5, {i} 0.5, {i} 0))"))
            f.setAttributes([i, i % 4])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        result = create_print_layout("Bulletin", template="epi_bulletin", body_text="x", key_figures=[{"label": "Impossible", "value": "47"}])
        self.assertNotIn("Impossible", self._body(result))      # 47 is a fid but no field measures it

    def test_a_change_report_has_its_headings_and_the_screening_note(self):
        from cartogen_ai.core.agent.tools import layout_style as ls
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        result = create_print_layout("Change 2020 to 2021", template="change_report", body_text="Cropland lost to built-up",
                                     key_figures_from={"layer_name": "fields", "label_field": "name", "value_field": "lost_ha", "top_n": 2}, sources=["ESA WorldCover 2020 and 2021"])
        body = self._body(result)
        self.assertEqual(result["template"], "change_report")
        self.assertTrue(body.startswith("CHANGE\nCropland lost"), body)
        for expected in ("CHANGE FIGURES", "South: 30", "North: 12", "HOW TO READ THIS MAP\n" + ls.CHANGE_REPORT_GUIDE_UNCOLOURED, "NOTE\n" + ls.CHANGE_REPORT_NOTE):
            self.assertIn(expected, body)             # the change look was not applied to any visible layer, so the page must not name colours
        self.assertNotIn("Orange marks loss", body)
        self.assertNotIn("HANDLING", body)

    def test_the_change_colour_sentence_appears_only_when_the_change_look_is_on_a_visible_layer(self):
        """2026-11-20 live run, row C20: the page named orange, grey and purple over a plain grey map."""
        from qgis.core import QgsProject
        from cartogen_ai.core.agent.tools import layout_style as ls
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        QgsProject.instance().mapLayersByName("fields")[0].setCustomProperty("cartogen_look", "change_classes")      # what apply_land_cover_look sets
        result = create_print_layout("Change coloured", template="change_report", body_text="Cropland lost to built-up",
                                     key_figures_from={"layer_name": "fields", "label_field": "name", "value_field": "lost_ha", "top_n": 2}, sources=["ESA WorldCover 2020 and 2021"])
        self.assertIn("HOW TO READ THIS MAP\n" + ls.CHANGE_REPORT_GUIDE, self._body(result))

    def test_an_epi_bulletin_has_its_headings_the_figures_from_the_layer_and_the_method_and_limits_box(self):
        from cartogen_ai.core.agent.tools import layout_style as ls
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        result = create_print_layout("Epidemic bulletin", template="epi_bulletin", body_text="Cases reported to 2026-11-08",
                                     key_figures_from={"layer_name": "fields", "label_field": "name", "value_field": "lost_ha", "top_n": 2}, sources=["District health office line list"])
        body = self._body(result)
        self.assertEqual(result["template"], "epi_bulletin")
        self.assertIs(result["exported"], False)                       # LR-3: no output_path means no file, and the reply must say so
        self.assertIn("No file was written", result["export_note"])
        self.assertTrue(body.startswith("SUMMARY\nCases reported to 2026-11-08"), body)
        for expected in ("CASES AND RATES", "South: 30", "North: 12", "HOW TO READ THIS MAP\n" + ls.EPI_BULLETIN_GUIDE, "SOURCES\nDistrict health office line list", "METHOD AND LIMITS\n" + ls.EPI_BULLETIN_NOTE):
            self.assertIn(expected, body)
        for absent in ("SITUATION", "HANDLING", ls.UNVERIFIED_FIGURE_MARK):
            self.assertNotIn(absent, body)

    def test_sitrep_is_unchanged_and_an_unknown_template_is_the_standard_layout(self):
        from cartogen_ai.core.agent.tools import layout_style as ls
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        sitrep = create_print_layout("Sitrep", template="sitrep", body_text="Floods")
        self.assertIn("HANDLING\n" + ls.SITREP_HANDLING, self._body(sitrep))
        other = create_print_layout("Other", template="made_up", body_text="plain text")
        self.assertTrue(other.get("success"), other)
        self.assertEqual(other["template"], "standard")


if __name__ == "__main__":
    unittest.main()
