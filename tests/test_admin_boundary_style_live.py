"""Live QGIS: a boundary layer keeps visible borders between its areas, also after a recolour with opacity (owner report 2026-10-26, Yemen
ADM1: the model recoloured the layer to 25 percent opacity, which faded the outline and the borders between provinces vanished).
Written without a local QGIS: CI's first run is its first execution."""
import json
import os
import tempfile
import unittest

try:
    from qgis.core import QgsProject
    LIVE = True
except ImportError:
    LIVE = False

GEOJSON = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"shapeName": "A"}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}},
    {"type": "Feature", "properties": {"shapeName": "B"}, "geometry": {"type": "Polygon", "coordinates": [[[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]]}},
]}


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestAdminBoundaryBorders(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        fd, self.path = tempfile.mkstemp(suffix=".geojson")
        with os.fdopen(fd, "w") as fh:
            json.dump(GEOJSON, fh)
        self.addCleanup(os.remove, self.path)

    def _add(self):
        from cartogen_ai.core.agent.tools.humanitarian_tools import add_geoboundaries_layer_main_thread_phase
        res = add_geoboundaries_layer_main_thread_phase({"success": True, "local_path": self.path, "iso3": "TST", "admin_level": "ADM1", "boundary": "t"})
        self.assertTrue(res.get("success"), res)
        return QgsProject.instance().mapLayersByName("TST_ADM1_boundary")[0]

    def test_default_style_has_a_white_opaque_border_on_a_grey_fill(self):
        sl = self._add().renderer().symbol().symbolLayer(0)
        self.assertEqual(sl.strokeColor().name(), "#ffffff")
        self.assertEqual(sl.strokeColor().alpha(), 255)
        self.assertGreaterEqual(sl.strokeWidth(), 0.25)
        self.assertEqual(sl.fillColor().name(), "#c8c8c8")
        self.assertLess(sl.fillColor().alpha(), 150)         # stays a backdrop: translucent, as tests/test_hdx_admin_live.py requires

    def test_recolour_with_opacity_fades_the_fill_not_the_border(self):
        from cartogen_ai.core.agent.tools.styling_tools import change_layer_color
        layer = self._add()
        res = change_layer_color("TST_ADM1_boundary", "#2b5c8f", opacity=25)
        self.assertTrue(res.get("success"), res)
        sl = layer.renderer().symbol().symbolLayer(0)
        self.assertEqual(layer.opacity(), 1.0)
        self.assertAlmostEqual(sl.fillColor().alphaF(), 0.25, places=1)
        self.assertEqual(sl.strokeColor().alpha(), 255)

    def test_set_layer_transparency_keeps_the_border_too(self):
        from cartogen_ai.core.agent.tools.styling_tools import set_layer_transparency
        layer = self._add()
        self.assertTrue(set_layer_transparency("TST_ADM1_boundary", 40).get("success"))
        sl = layer.renderer().symbol().symbolLayer(0)
        self.assertEqual(sl.strokeColor().alpha(), 255)
        self.assertEqual(layer.opacity(), 1.0)


if __name__ == "__main__":
    unittest.main()
