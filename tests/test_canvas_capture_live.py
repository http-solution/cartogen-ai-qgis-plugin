"""PLAN-032: the off-screen canvas render on real QGIS: a PNG that is not blank, within the size cap, with the layers and legend as text.

Written without a QGIS install: CI's first run is its first execution. What this does NOT show: that any provider's model can read the picture."""
import base64
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    from qgis.gui import QgsMapCanvas
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestCanvasCaptureLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _canvas(self, width=3000, height=1200):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string", "districts", "memory")
        feats = []
        for i in range(3):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({i} 0,{i + 0.9} 0,{i + 0.9} 1,{i} 1,{i} 0))"))
            f.setAttributes([f"D{i}"])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        canvas = QgsMapCanvas()
        canvas.resize(width, height)
        canvas.setDestinationCrs(layer.crs())
        canvas.setLayers([layer])
        canvas.setExtent(layer.extent())
        return canvas, layer

    def test_the_render_is_capped_not_blank_and_described(self):
        from cartogen_ai.core.agent.tools import multimodal_remote_sensing as mrs
        canvas, _layer = self._canvas()
        out = mrs._render_capped(canvas)
        self.assertLessEqual(max(out["width"], out["height"]), 1280)
        self.assertFalse(out["blank"], "three filled polygons must not render blank")
        png = base64.b64decode(out["image_b64"])
        self.assertTrue(png.startswith(b"\x89PNG"), png[:8])
        self.assertIn("districts", out["layers_text"])
        self.assertIn("districts", out["legend_text"])

    def test_an_empty_extent_renders_blank(self):
        from qgis.core import QgsRectangle
        from cartogen_ai.core.agent.tools import multimodal_remote_sensing as mrs
        canvas, _layer = self._canvas(400, 300)
        canvas.setExtent(QgsRectangle(100, 50, 101, 51))
        self.assertTrue(mrs._render_capped(canvas)["blank"])

    def test_the_extent_layer_shows_that_layer_without_moving_the_canvas(self):
        from cartogen_ai.core.agent.tools import multimodal_remote_sensing as mrs
        canvas, layer = self._canvas(400, 300)
        canvas.setExtent(layer.extent().buffered(50))
        before = canvas.extent().toString()
        out = mrs._render_capped(canvas, extent_layer="districts")
        self.assertFalse(out["blank"])
        self.assertEqual(canvas.extent().toString(), before)

    def test_an_unknown_extent_layer_is_reported(self):
        from cartogen_ai.core.agent.tools import multimodal_remote_sensing as mrs
        canvas, _layer = self._canvas(400, 300)
        with self.assertRaises(ValueError):
            mrs._render_capped(canvas, extent_layer="no_such_layer")


if __name__ == "__main__":
    unittest.main()
