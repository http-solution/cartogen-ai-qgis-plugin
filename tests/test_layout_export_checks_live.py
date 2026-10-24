"""PLAN-011 phase A, real QGIS (run by the qgis-live-tests CI job; written without a QGIS install, so CI's first run is its first execution):
export_layout on a real layout reports the protected layer its map draws and the mandatory elements it lacks."""
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

    def _export(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        return export_layout("phase_a", os.path.join(self.tmp.name, "out.png"), dpi=60)

    def test_a_tagged_layer_and_the_missing_elements_are_reported(self):
        from cartogen_ai.core.models import sensitivity
        self.assertTrue(sensitivity.set_layer_sensitivity(self.layer, "SENSITIVE", "test"))
        result = self._export()
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["protected_layers"], [{"layer": "incidents", "level": "SENSITIVE"}], result)
        self.assertEqual(result["missing_elements"], ["title", "legend", "scale bar", "north arrow"], result)
        self.assertTrue(any("incidents" in w for w in result["export_warnings"]), result)

    def test_an_untagged_layer_adds_no_protected_note(self):
        result = self._export()
        self.assertTrue(result.get("success"), result)
        self.assertNotIn("protected_layers", result)
        self.assertIn("missing_elements", result)


if __name__ == "__main__":
    unittest.main()
