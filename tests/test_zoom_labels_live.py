"""GitHub #127, rc48 OI-127: an admin layer too big to label at country scale gets names that appear when zoomed in. Written without a QGIS
install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestZoomLabels(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _districts(self, count):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=adm2_name:string&field=adm2_pcode:string", "YEM_ADM2_boundary_hdx", "memory")
        feats = []
        for i in range(count):
            x, y = (i % 20) * 0.1, (i // 20) * 0.1
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} {y},{x + .09} {y},{x + .09} {y + .09},{x} {y + .09},{x} {y}))"))
            f.setAttributes([f"District {i}", f"YE{i:04d}"])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_a_330_district_layer_gets_labels_that_show_only_when_zoomed_in(self):
        from cartogen_ai.core.agent.tools.output_style import style_auto_labels, style_zoom_labels
        layer = self._districts(330)
        self.assertIsNone(style_auto_labels(layer), "the always-on rule must still skip a layer this big")
        self.assertEqual(style_zoom_labels(layer), "adm2_name")
        self.assertTrue(layer.labelsEnabled())
        settings = layer.labeling().settings()
        print(f"ZOOMLABELS scaleVisibility={settings.scaleVisibility} minimumScale={settings.minimumScale} maximumScale={settings.maximumScale}")
        self.assertTrue(settings.scaleVisibility)
        self.assertEqual(settings.minimumScale, 1_000_000.0)

    def test_a_layer_without_a_name_field_is_left_alone(self):
        from cartogen_ai.core.agent.tools.output_style import style_zoom_labels
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=code:string", "plain", "memory")
        QgsProject.instance().addMapLayer(layer)
        self.assertIsNone(style_zoom_labels(layer))


if __name__ == "__main__":
    unittest.main()
