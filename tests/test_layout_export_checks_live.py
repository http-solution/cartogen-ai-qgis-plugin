"""PLAN-011 phase A, real QGIS (run by the qgis-live-tests CI job; written without a QGIS install, so CI's first run is its first execution):
export_layout on a real layout reports the protected layer its map draws and the mandatory elements it lacks."""
import json
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsLayoutItemMap, QgsLayoutPoint, QgsLayoutSize, QgsPrintLayout, QgsProject, QgsRectangle, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestExportLayoutReport(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        project = QgsProject.instance()
        project.clear()
        self.addCleanup(project.clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", "incidents", "memory")
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POINT(44 15)"))
        feature.setAttributes([1])
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()
        project.addMapLayer(layer)
        self.layer = layer
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName("phase_a")
        map_item = QgsLayoutItemMap(layout)
        map_item.setId("MAP_MAIN")
        layout.addLayoutItem(map_item)
        map_item.attemptMove(QgsLayoutPoint(10, 10))
        map_item.attemptResize(QgsLayoutSize(100, 100))
        map_item.setExtent(QgsRectangle(43, 14, 45, 16))
        project.layoutManager().addLayout(layout)

    def _export(self, **kw):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        return export_layout("phase_a", os.path.join(self.tmp.name, "out.png"), dpi=60, **kw)

    def test_a_tagged_layer_and_the_missing_elements_are_reported(self):
        from cartogen_ai.core.models import sensitivity
        self.assertTrue(sensitivity.set_layer_sensitivity(self.layer, "SENSITIVE", "test"))
        result = self._export(confirmed=True)        # phase B: the user's Apply button; without it the export waits (tests below)
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["protected_layers"], [{"layer": "incidents", "level": "SENSITIVE"}], result)
        self.assertEqual(result["missing_elements"], ["title", "legend", "scale bar", "north arrow"], result)
        self.assertTrue(any("incidents" in w for w in result["export_warnings"]), result)

    def test_an_untagged_layer_adds_no_protected_note(self):
        result = self._export()
        self.assertTrue(result.get("success"), result)
        self.assertNotIn("protected_layers", result)
        self.assertIn("missing_elements", result)


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestExportGate(TestExportLayoutReport):
    """PLAN-011 phase B on a real layout."""

    def _tag(self):
        from cartogen_ai.core.models import sensitivity
        self.assertTrue(sensitivity.set_layer_sensitivity(self.layer, "SENSITIVE", "test"))

    def _out(self):
        return os.path.join(self.tmp.name, "out.png")

    def test_a_protected_layer_waits_for_the_confirm_card_and_writes_nothing(self):
        self._tag()
        result = self._export()
        self.assertEqual(result.get("status"), "PREVIEW_REQUIRED", result)
        self.assertTrue(result["arguments"]["confirmed"])
        self.assertIn("incidents", result["rationale"])
        self.assertFalse(os.path.exists(self._out()), "the file was written before the user confirmed")

    def test_confirming_writes_the_file(self):
        self._tag()
        self.assertTrue(self._export(confirmed=True).get("success"))
        self.assertTrue(os.path.isfile(self._out()))

    def test_an_untagged_layer_exports_without_a_card(self):
        self.assertTrue(self._export().get("success"))

    def test_publication_is_refused_without_a_reason_and_lists_the_problems(self):
        result = self._export(purpose="publication")
        self.assertIn("error", result, result)
        self.assertIn("missing", result["error"])
        self.assertFalse(os.path.exists(self._out()))

    def test_publication_with_a_reason_asks_then_records_the_reason_beside_the_file(self):
        card = self._export(purpose="publication", override_reason="internal review copy")
        self.assertEqual(card.get("status"), "PREVIEW_REQUIRED", card)
        self.assertIn("internal review copy", card["rationale"])
        done = self._export(purpose="publication", override_reason="internal review copy", confirmed=True)
        self.assertTrue(done.get("success"), done)
        record = done.get("publication_record")
        self.assertTrue(record and os.path.isfile(record), done)
        with open(record, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["reason_given"], "internal review copy")

    def test_create_print_layout_waits_too_when_it_would_write_a_protected_map(self):
        self._tag()
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        result = create_print_layout("Gate check", output_path=self._out())
        self.assertEqual(result.get("status"), "PREVIEW_REQUIRED", result)
        self.assertFalse(os.path.exists(self._out()))
        self.assertEqual(QgsProject.instance().layoutManager().printLayouts(), [], "a layout was built before the user confirmed")


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestFooterSourcesAndDisclaimer(unittest.TestCase):
    """PLAN-011 phase C on a real layout built by create_print_layout."""

    def setUp(self):
        from qgis.core import QgsSettings
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        project = QgsProject.instance()
        project.clear()
        self.addCleanup(project.clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", "clinics", "memory")
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POINT(44 15)"))
        feature.setAttributes([1])
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()
        project.addMapLayer(layer)
        settings = QgsSettings()
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_LAYOUT_DISCLAIMER_ENABLED, SETTINGS_LAYOUT_DISCLAIMER_TEXT
        for key in (SETTINGS_LAYOUT_DISCLAIMER_ENABLED, SETTINGS_LAYOUT_DISCLAIMER_TEXT):
            self.addCleanup(settings.remove, key)
            settings.remove(key)
        self.settings, self.enabled_key, self.text_key = settings, SETTINGS_LAYOUT_DISCLAIMER_ENABLED, SETTINGS_LAYOUT_DISCLAIMER_TEXT

    def _layout(self, orientation="Landscape", **kw):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("Footer check", page_orientation=orientation, confirmed=True, **kw)
        self.assertTrue(res.get("success"), res)
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        self.assertIsNotNone(layout, res)
        return res, layout

    def test_default_footer_names_the_layer_source_and_carries_the_neutral_disclaimer(self):
        from cartogen_ai.core.agent.tools.layout_style import DEFAULT_DISCLAIMER, NOT_RECORDED
        _, layout = self._layout()
        text = layout.itemById("FOOTER").text()
        self.assertIn("AI-generated", text)
        self.assertIn(f"Sources: clinics ({NOT_RECORDED})", text)
        self.assertIn(DEFAULT_DISCLAIMER, text)

    def test_the_organisations_wording_replaces_the_default_and_off_removes_it(self):
        self.settings.setValue(self.text_key, "Our boundary wording.")
        _, layout = self._layout()
        self.assertIn("Our boundary wording.", layout.itemById("FOOTER").text())
        self.settings.setValue(self.enabled_key, False)
        _, layout = self._layout()
        self.assertNotIn("Our boundary wording.", layout.itemById("FOOTER").text())
        self.assertIn("Sources:", layout.itemById("FOOTER").text())

    def test_explicit_sources_replace_the_derived_ones(self):
        _, layout = self._layout(sources=["OCHA COD-AB 2024"])
        text = layout.itemById("FOOTER").text()
        self.assertIn("Sources: OCHA COD-AB 2024", text)
        self.assertNotIn("clinics (", text)

    def test_the_grown_footer_stays_on_the_page_and_clear_of_the_other_items(self):
        for orientation in ("Landscape", "Portrait"):
            with self.subTest(orientation=orientation):
                _, layout = self._layout(orientation, body_text="Finding one\nFinding two\nFinding three")
                footer = layout.itemById("FOOTER")
                page = layout.pageCollection().page(0).pageSize()
                self.assertGreaterEqual(footer.y(), 0)
                self.assertLessEqual(footer.y() + footer.rect().height(), page.height() + 0.01)
                for other in layout.items():
                    if other is footer or not (hasattr(other, "id") and other.id()):
                        continue
                    apart = (other.y() + other.rect().height() <= footer.y() + 0.01 or other.y() >= footer.y() + footer.rect().height() - 0.01
                             or other.x() + other.rect().width() <= footer.x() + 0.01 or other.x() >= footer.x() + footer.rect().width() - 0.01)
                    self.assertTrue(apart, f"{other.id()} overlaps the footer in {orientation}")


if __name__ == "__main__":
    unittest.main()
