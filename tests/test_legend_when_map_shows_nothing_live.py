"""PLAN-058 (DEF-25, row A1), real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): the layout's Legend is not
filtered away when the map has no CRS or shows none of the layers (live run 2026-11-04: pages with only the heading), and is still filtered when the map shows
the data. Uses the plugin's own create_print_layout with a real canvas in place of the QGIS interface."""
import unittest
from unittest.mock import MagicMock, patch

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer
    from qgis.gui import QgsMapCanvas


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestTheLegendIsNotFilteredAway(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.layers = []
        for n in range(3):
            layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=kind:string", f"zones_{n}", "memory")
            feature = QgsFeature(layer.fields())
            x = 43.9 + 0.02 * n
            feature.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 14.9,{x + 0.01} 14.9,{x + 0.01} 15.0,{x} 15.0,{x} 14.9))"))
            feature.setAttributes(["a"])
            layer.dataProvider().addFeatures([feature])
            layer.updateExtents()
            QgsProject.instance().addMapLayer(layer)
            self.layers.append(layer)
        from cartogen_ai.core.agent.tools import layout_tools
        self.layout_tools = layout_tools

    def _make(self, project_crs, view):
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem(project_crs) if project_crs else QgsCoordinateReferenceSystem())
        canvas = QgsMapCanvas()
        canvas.setLayers(self.layers)
        canvas.setExtent(view)
        iface = MagicMock()
        iface.mapCanvas.return_value = canvas
        with patch.object(self.layout_tools, "iface", iface):
            res = self.layout_tools.create_print_layout("Legend test", confirmed=True, body_text="x")
        self.assertTrue(res.get("success"), res)
        legend = QgsProject.instance().layoutManager().layoutByName(res["layout_name"]).itemById("LEGEND")
        return res, legend

    def test_a_project_with_no_crs_keeps_every_layer_in_an_unfiltered_legend_and_says_why(self):
        res, legend = self._make(None, QgsRectangle(43.8, 14.8, 44.1, 15.1))
        self.assertFalse(legend.legendFilterByMapEnabled())
        self.assertEqual(len(legend.model().rootGroup().findLayers()), 3)
        self.assertTrue(any("coordinate system" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))

    def test_a_map_that_shows_none_of_the_layers_keeps_them_all_in_an_unfiltered_legend_and_says_why(self):
        res, legend = self._make("EPSG:4326", QgsRectangle(10.0, 10.0, 11.0, 11.0))
        self.assertFalse(legend.legendFilterByMapEnabled())
        self.assertEqual(len(legend.model().rootGroup().findLayers()), 3)
        self.assertTrue(any("none of the layers" in w for w in res.get("style_warnings", [])), res.get("style_warnings"))

    def test_a_map_that_shows_the_data_still_filters_by_map_and_warns_of_nothing(self):
        res, legend = self._make("EPSG:4326", QgsRectangle(43.8, 14.8, 44.1, 15.1))
        self.assertTrue(legend.legendFilterByMapEnabled())
        self.assertFalse([w for w in res.get("style_warnings", []) if "coordinate system" in w or "none of the layers" in w], res.get("style_warnings"))


if __name__ == "__main__":
    unittest.main()
