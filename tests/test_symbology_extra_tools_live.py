"""Live run of the package F symbology tools: each setting is read back from the real QGIS objects. Written without a QGIS install: CI's
first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import (QgsFeature, QgsFontMarkerSymbolLayer, QgsGeometry, QgsProject, QgsRasterLayer, QgsSvgMarkerSymbolLayer,
                           QgsVectorLayer)
    LIVE = True
except ImportError:
    LIVE = False

try:
    import numpy
    from osgeo import gdal, osr
    HAVE_GDAL = True
except ImportError:
    HAVE_GDAL = False

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="8" fill="red"/></svg>'


def _points(name="camps"):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer&field=men:integer&field=women:integer", name, "memory")
    for i, (n, pop) in enumerate((("a", 50), ("b", 5000), ("c", 90000))):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({i} {i})"))
        f.setAttributes([n, pop, pop // 2, pop // 3])
        layer.dataProvider().addFeatures([f])
    QgsProject.instance().addMapLayer(layer)
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestSymbologyExtraLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp()

    def test_rule_based_labels(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import set_rule_based_labels
        layer = _points()
        res = set_rule_based_labels("camps", [{"field": "name", "filter": '"pop" > 1000', "font_size": 12, "font_color": "dark red"},
                                              {"field": "pop", "filter": '"pop" <= 1000', "font_size": 8, "max_scale": 25000}])
        self.assertTrue(res.get("success"), res)
        labeling = layer.labeling()
        self.assertEqual(labeling.type(), "rule-based")
        rules = labeling.rootRule().children()
        self.assertEqual([r.filterExpression() for r in rules], ['"pop" > 1000', '"pop" <= 1000'])
        self.assertEqual(rules[0].settings().fieldName, "name")
        self.assertAlmostEqual(rules[0].settings().format().size(), 12)
        self.assertTrue(layer.labelsEnabled())

    def test_rule_based_labels_refuse_bad_input(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import set_rule_based_labels
        _points()
        self.assertIn("not found", set_rule_based_labels("camps", [{"field": "nope"}])["error"])
        self.assertIn("env()", set_rule_based_labels("camps", [{"field": "name", "filter": "env('HOME') = 'x'"}])["error"])
        self.assertIn("invalid filter", set_rule_based_labels("camps", [{"field": "name", "filter": '"pop" >>> 1'}])["error"])
        self.assertIn("error", set_rule_based_labels("camps", []))

    def test_callout_and_mask(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import set_label_callout
        from cartogen_ai.core.agent.tools.vector_tools import apply_labels
        layer = _points()
        self.assertTrue(apply_labels("camps", target_field="name").get("success"))
        res = set_label_callout("camps", enabled=True, style="simple", color="grey", width_mm=0.3, mask=True, mask_size_mm=1.2)
        self.assertTrue(res.get("success"), res)
        settings = layer.labeling().settings()
        self.assertTrue(settings.callout().enabled())
        self.assertTrue(settings.format().mask().enabled())
        self.assertAlmostEqual(settings.format().mask().size(), 1.2)
        self.assertIn("error", set_label_callout("camps", style="wavy"))

    def test_svg_and_font_markers(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import set_point_marker
        layer = _points()
        path = os.path.join(self.tmp, "icon.svg")
        with open(path, "w") as fh:
            fh.write(SVG)
        res = set_point_marker("camps", "svg", svg_path=path, size_mm=7)
        self.assertTrue(res.get("success"), res)
        sl = layer.renderer().symbol().symbolLayer(0)
        self.assertIsInstance(sl, QgsSvgMarkerSymbolLayer)
        self.assertTrue(sl.path().endswith("icon.svg"))
        self.assertAlmostEqual(sl.size(), 7)
        res = set_point_marker("camps", "font", font_family="Arial", character="A", size_mm=5, color="blue")
        self.assertTrue(res.get("success"), res)
        sl = layer.renderer().symbol().symbolLayer(0)
        self.assertIsInstance(sl, QgsFontMarkerSymbolLayer)
        self.assertEqual(sl.character(), "A")
        self.assertIn("error", set_point_marker("camps", "svg", svg_path="http://x/a.svg"))
        self.assertIn("not found", set_point_marker("camps", "svg", svg_path=os.path.join(self.tmp, "missing.svg"))["error"])

    def test_marker_refuses_a_polygon_layer(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import set_point_marker
        poly = QgsVectorLayer("Polygon?crs=EPSG:4326", "zones", "memory")
        QgsProject.instance().addMapLayer(poly)
        self.assertIn("not a point layer", set_point_marker("zones", "font", font_family="Arial", character="A")["error"])

    def test_diagrams(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import set_layer_diagram
        layer = _points()
        res = set_layer_diagram("camps", "pie", ["men", "women"], size_mm=12, colors=["blue", "red"])
        self.assertTrue(res.get("success"), res)
        renderer = layer.diagramRenderer()
        self.assertIsNotNone(renderer)
        settings = renderer.diagramSettings()[0]
        self.assertEqual(list(settings.categoryAttributes), ["men", "women"])
        self.assertAlmostEqual(settings.size.width(), 12)
        self.assertIn("not numeric", set_layer_diagram("camps", "bar", ["name"])["error"])
        self.assertIn("not found", set_layer_diagram("camps", "bar", ["nope"])["error"])
        self.assertTrue(set_layer_diagram("camps", clear=True)["success"])
        self.assertIsNone(layer.diagramRenderer())

    @unittest.skipUnless(HAVE_GDAL, "needs osgeo.gdal and numpy")
    def test_hillshade_and_contour_renderers(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import set_raster_relief
        path = os.path.join(self.tmp, "dem.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 30, 30, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((44.0, 0.001, 0, 15.0, 0, -0.001))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        ds.GetRasterBand(1).WriteArray(numpy.add.outer(numpy.arange(30), numpy.arange(30)).astype("float32") * 5)
        ds.FlushCache()
        ds = None
        layer = QgsRasterLayer(path, "dem")
        QgsProject.instance().addMapLayer(layer)
        res = set_raster_relief("dem", "hillshade", azimuth=270, altitude=30, z_factor=2)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(layer.renderer().type(), "hillshade")
        self.assertAlmostEqual(layer.renderer().azimuth(), 270)
        self.assertAlmostEqual(layer.renderer().zFactor(), 2)
        res = set_raster_relief("dem", "contour", interval=20, index_interval=100)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(layer.renderer().type(), "contour")
        self.assertAlmostEqual(layer.renderer().contourInterval(), 20)
        self.assertIn("band 2", set_raster_relief("dem", "hillshade", band=2)["error"])
        self.assertIn("interval", set_raster_relief("dem", "contour")["error"])

    def test_symbol_library_round_trip(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import apply_saved_symbol, list_saved_symbols, save_symbol_to_library
        from cartogen_ai.core.agent.tools.symbology_tools import set_layer_symbol
        source = _points("source")
        set_layer_symbol("source", fill_color="red", marker_size_mm=8)
        name = "cartogen ci symbol"
        res = save_symbol_to_library("source", name, tags=["ci"])
        self.assertTrue(res.get("success"), res)
        self.assertEqual(save_symbol_to_library("source", name)["status"], "PREVIEW_REQUIRED")
        self.assertTrue(save_symbol_to_library("source", name, confirmed=True)["success"])
        self.assertIn(name, [s["name"] for s in list_saved_symbols()["symbols"]])
        target = _points("target")
        res = apply_saved_symbol("target", name)
        self.assertTrue(res.get("success"), res)
        self.assertAlmostEqual(target.renderer().symbol().size(), source.renderer().symbol().size())
        poly = QgsVectorLayer("Polygon?crs=EPSG:4326", "zones", "memory")
        QgsProject.instance().addMapLayer(poly)
        self.assertIn("marker symbol", apply_saved_symbol("zones", name)["error"])
        self.assertIn("No symbol called", apply_saved_symbol("target", "nope nope")["error"])


if __name__ == "__main__":
    unittest.main()
