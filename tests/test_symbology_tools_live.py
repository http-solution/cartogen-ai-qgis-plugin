"""Live run of set_layer_symbol, set_label_style and set_raster_style: each setting is read back from the real QGIS objects.
Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import (QgsFeature, QgsGeometry, QgsPalettedRasterRenderer, QgsProject, QgsRasterLayer, QgsSimpleFillSymbolLayer,
                           QgsSimpleLineSymbolLayer, QgsSimpleMarkerSymbolLayer, QgsVectorLayer)
    from qgis.PyQt.QtCore import Qt
    LIVE = True
except ImportError:
    LIVE = False

try:
    from osgeo import gdal, osr
    import numpy
    HAVE_GDAL = True
except ImportError:
    HAVE_GDAL = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


def _layer(kind, name, wkts):
    layer = QgsVectorLayer(f"{kind}?crs=EPSG:4326&field=name:string", name, "memory")
    feats = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([f"n{i}"])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestSymbolTool(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_polygon_outline_pattern_and_hatch(self):
        from cartogen_ai.core.agent.tools.symbology_tools import set_layer_symbol
        layer = _layer("Polygon", "zones", ["POLYGON((0 0,1 0,1 1,0 1,0 0))"])
        result = set_layer_symbol("zones", fill_color="pale yellow", outline_color="dark red", outline_width_mm=0.8, line_style="dashed",
                                  fill_style="hatch_forward", opacity_percent=60)
        self.assertTrue(result.get("success"), result)
        sl = layer.renderer().symbol().symbolLayer(0)
        self.assertIsInstance(sl, QgsSimpleFillSymbolLayer)
        self.assertAlmostEqual(sl.strokeWidth(), 0.8)
        self.assertEqual(sl.strokeStyle(), Qt.PenStyle.DashLine)
        self.assertEqual(sl.brushStyle(), Qt.BrushStyle.BDiagPattern)
        self.assertTrue(sl.strokeColor().red() > sl.strokeColor().green())
        self.assertAlmostEqual(layer.opacity(), 0.6)

    def test_point_shape_and_size_and_line_pattern(self):
        from cartogen_ai.core.agent.tools.symbology_tools import set_layer_symbol
        pts = _layer("Point", "pts", ["POINT(0 0)", "POINT(1 1)"])
        result = set_layer_symbol("pts", marker_shape="star", marker_size_mm=6, fill_color="#00ff00", outline_color="black")
        self.assertTrue(result.get("success"), result)
        sl = pts.renderer().symbol().symbolLayer(0)
        self.assertIsInstance(sl, QgsSimpleMarkerSymbolLayer)
        self.assertAlmostEqual(sl.size(), 6)
        self.assertEqual(sl.color().name(), "#00ff00")
        lines = _layer("LineString", "roads", ["LINESTRING(0 0,1 1)"])
        result = set_layer_symbol("roads", line_style="dotted", outline_width_mm=1.2, outline_color="#0000ff")
        self.assertTrue(result.get("success"), result)
        sl = lines.renderer().symbol().symbolLayer(0)
        self.assertIsInstance(sl, QgsSimpleLineSymbolLayer)
        self.assertEqual(sl.penStyle(), Qt.PenStyle.DotLine)
        self.assertAlmostEqual(sl.width(), 1.2)

    def test_categorized_layer_keeps_its_classes(self):
        from cartogen_ai.core.agent.tools.styling_tools import apply_categorized_style
        from cartogen_ai.core.agent.tools.symbology_tools import set_layer_symbol
        layer = _layer("Polygon", "cat", ["POLYGON((0 0,1 0,1 1,0 1,0 0))", "POLYGON((2 0,3 0,3 1,2 1,2 0))"])
        self.assertTrue(apply_categorized_style("cat", "name").get("success"))
        refused = set_layer_symbol("cat", fill_color="red")
        self.assertIn("error", refused)
        ok = set_layer_symbol("cat", outline_width_mm=0.1)
        self.assertTrue(ok.get("success"), ok)
        self.assertEqual(layer.renderer().type(), "categorizedSymbol")
        self.assertEqual(len(layer.renderer().categories()), 2)

    def test_bad_input_changes_nothing(self):
        from cartogen_ai.core.agent.tools.symbology_tools import set_layer_symbol
        layer = _layer("Polygon", "z", ["POLYGON((0 0,1 0,1 1,0 1,0 0))"])
        before = layer.renderer().symbol().symbolLayer(0).strokeWidth()
        for kwargs in ({"line_style": "wavy"}, {"outline_width_mm": 99}, {"outline_color": "not-a-colour"}, {}):
            self.assertIn("error", set_layer_symbol("z", **kwargs), kwargs)
        self.assertIn("error", set_layer_symbol("missing", outline_width_mm=1))
        self.assertEqual(layer.renderer().symbol().symbolLayer(0).strokeWidth(), before)


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestLabelTool(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_style_existing_labels(self):
        from cartogen_ai.core.agent.tools.symbology_tools import set_label_style
        from cartogen_ai.core.agent.tools.vector_tools import apply_labels
        layer = _layer("Point", "towns", ["POINT(0 0)"])
        self.assertIn("error", set_label_style("towns", font_size=12))     # no labels yet
        self.assertTrue(apply_labels("towns", target_field="name").get("success"))
        result = set_label_style("towns", font_color="dark blue", font_size=14, bold=True, halo_color="white", halo_size_mm=1.5,
                                 placement="over_point", visible_zoomed_out_to=250000, visible_zoomed_in_to=5000)
        self.assertTrue(result.get("success"), result)
        settings = layer.labeling().settings()
        fmt = settings.format()
        self.assertAlmostEqual(fmt.size(), 14)
        self.assertTrue(fmt.font().bold())
        self.assertTrue(fmt.buffer().enabled())
        self.assertAlmostEqual(fmt.buffer().size(), 1.5)
        self.assertTrue(settings.scaleVisibility)
        self.assertAlmostEqual(settings.minimumScale, 250000)
        self.assertAlmostEqual(settings.maximumScale, 5000)

    def test_switch_off_and_validation(self):
        from cartogen_ai.core.agent.tools.symbology_tools import set_label_style
        from cartogen_ai.core.agent.tools.vector_tools import apply_labels
        layer = _layer("Point", "p", ["POINT(0 0)"])
        apply_labels("p", target_field="name")
        self.assertTrue(set_label_style("p", show_labels=False).get("success"))
        self.assertFalse(layer.labelsEnabled())
        self.assertIn("error", set_label_style("p", placement="sideways"))
        self.assertIn("error", set_label_style("p"))


@unittest.skipUnless(LIVE and HAVE_GDAL, "requires real QGIS + gdal + numpy")
class TestRasterTool(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp(prefix="cartogen_ss_")

    def _add(self, name, array):
        path = os.path.join(self.tmp, name + ".tif")
        rows, cols = array.shape
        ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, 1, gdal.GDT_Int16)
        ds.SetGeoTransform((44.0, 0.001, 0, 15.0, 0, -0.001))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        ds.GetRasterBand(1).WriteArray(array.astype("int16"))
        ds.FlushCache()
        ds = None
        layer = QgsRasterLayer(path, name)
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_unique_values_opacity_nodata(self):
        from cartogen_ai.core.agent.tools.symbology_tools import set_raster_style
        layer = self._add("lc", numpy.array([[1, 1, 2], [3, 3, 2], [0, 1, 2]]))
        result = set_raster_style("lc", mode="unique_values", opacity_percent=70, nodata_min=0)
        self.assertTrue(result.get("success"), result)
        self.assertIsInstance(layer.renderer(), QgsPalettedRasterRenderer)
        self.assertEqual(result["classes"], len(layer.renderer().classes()))
        self.assertAlmostEqual(layer.renderer().opacity(), 0.7)
        self.assertTrue(layer.dataProvider().userNoDataValues(1))
        cleared = set_raster_style("lc", clear_nodata=True)
        self.assertTrue(cleared.get("success"), cleared)
        self.assertFalse(layer.dataProvider().userNoDataValues(1))

    def test_resampling_and_refusals(self):
        from cartogen_ai.core.agent.tools.symbology_tools import set_raster_style
        self._add("r", numpy.arange(9).reshape(3, 3))
        for method in ("bilinear", "cubic", "nearest"):
            result = set_raster_style("r", resampling=method)
            self.assertTrue(result.get("success"), (method, result))
        self.assertIn("error", set_raster_style("r", resampling="smooth"))
        self.assertIn("error", set_raster_style("missing", opacity_percent=50))
        _layer("Point", "v", ["POINT(0 0)"])
        self.assertIn("error", set_raster_style("v", opacity_percent=50))

    def test_too_many_distinct_values_is_refused(self):
        from cartogen_ai.core.agent.tools.symbology_tools import set_raster_style
        layer = self._add("many", numpy.arange(400).reshape(20, 20))
        before = type(layer.renderer())
        result = set_raster_style("many", mode="unique_values")
        self.assertIn("error", result)
        self.assertIs(type(layer.renderer()), before)


if __name__ == "__main__":
    unittest.main()
