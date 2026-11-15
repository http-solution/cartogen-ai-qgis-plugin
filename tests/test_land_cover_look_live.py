"""Live run of apply_land_cover_look (PLAN-023 R3-6): every colour, label and the hatch is read back from the real QGIS renderer. Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsGeometry, QgsPalettedRasterRenderer, QgsProject, QgsRasterLayer,
                           QgsSimpleFillSymbolLayer, QgsSingleSymbolRenderer, QgsVectorLayer)
    from qgis.PyQt.QtCore import Qt
    LIVE = True
except ImportError:
    LIVE = False

try:
    import numpy
    from osgeo import gdal, osr
    HAVE_GDAL = True
except ImportError:
    HAVE_GDAL = False

WORLDCOVER = {10: ("Tree cover", "#006400"), 20: ("Shrubland", "#ffbb22"), 40: ("Cropland", "#f096ff"), 80: ("Permanent water bodies", "#0064c8"), 95: ("Mangroves", "#00cf75")}


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


def _polygons(name, values, field="lc", kind="string"):
    layer = QgsVectorLayer(f"Polygon?crs=EPSG:4326&field={field}:{kind}", name, "memory")
    feats = []
    for i, value in enumerate(values):
        f = QgsFeature(layer.fields())
        x = float(i)
        f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 0,{x + 0.9} 0,{x + 0.9} 0.9,{x} 0.9,{x} 0))"))
        f.setAttributes([value])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    return layer


def _by_label(renderer):
    return {c.label(): c.symbol().color().name().lower() for c in renderer.categories()}


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestVectorLooks(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_worldcover_by_code_text_code_and_name_gives_the_official_colours_with_names_in_the_legend(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        layer = _polygons("cover", ["10", "20", "Cropland", "95"])
        result = apply_land_cover_look("cover", "esa_worldcover", field="lc")
        self.assertTrue(result.get("success"), result)
        self.assertTrue(result["legend_names_included"])
        renderer = layer.renderer()
        self.assertIsInstance(renderer, QgsCategorizedSymbolRenderer)
        self.assertEqual(renderer.classAttribute(), "lc")
        got = _by_label(renderer)
        for code in (10, 20, 40, 95):
            name, colour = WORLDCOVER[code]
            self.assertEqual(got[f"{name} ({code})"], colour)
        self.assertEqual(len(renderer.categories()), 4)
        self.assertEqual(result["unmatched_values"], [])

    def test_a_value_that_is_not_a_class_is_grey_named_and_reported(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        layer = _polygons("odd", ["10", "11", "forest"])
        result = apply_land_cover_look("odd", "esa_worldcover", field="lc")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(sorted(result["unmatched_values"]), ["11", "forest"])
        got = _by_label(layer.renderer())
        self.assertEqual(got["11 (not in the ESA WorldCover legend)"], "#bdbdbd")
        self.assertEqual(got["forest (not in the ESA WorldCover legend)"], "#bdbdbd")
        self.assertEqual(got["Tree cover (10)"], "#006400")

    def test_nothing_matching_changes_nothing_and_says_so(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        layer = _polygons("none", ["a", "b"])
        before = layer.renderer().type()
        result = apply_land_cover_look("none", "esa_worldcover", field="lc")
        self.assertIn("No value of 'lc' is in the ESA WorldCover legend", result["error"])
        self.assertEqual(layer.renderer().type(), before)

    def test_change_classes_in_orange_grey_purple_by_number_and_by_word(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        numbers = _polygons("chg_n", [-1, 0, 1, 2], field="chg", kind="integer")
        result = apply_land_cover_look("chg_n", "change_classes", field="chg")
        self.assertTrue(result.get("success"), result)
        got = _by_label(numbers.renderer())
        self.assertEqual(got["loss (-1)"], "#e66101")
        self.assertEqual(got["stable (0)"], "#cccccc")
        self.assertEqual(got["gain (1)"], "#5e3c99")
        self.assertEqual(got["2 (not in the loss / stable / gain classes)"], "#bdbdbd")
        self.assertEqual(result["unmatched_values"], ["2"])
        words = _polygons("chg_w", ["loss", "Stable", "GAIN"], field="chg")
        self.assertTrue(apply_land_cover_look("chg_w", "change_classes", field="chg").get("success"))
        self.assertEqual(sorted(_by_label(words.renderer())), ["gain (1)", "loss (-1)", "stable (0)"])

    def test_refusals(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        _polygons("cover", ["10"])
        self.assertIn("not found", apply_land_cover_look("missing", "esa_worldcover", field="lc")["error"])
        self.assertIn("Unknown scheme", apply_land_cover_look("cover", "rainbow", field="lc")["error"])
        self.assertIn("say which field", apply_land_cover_look("cover", "esa_worldcover")["error"])
        self.assertIn("Field 'nope' not found", apply_land_cover_look("cover", "esa_worldcover", field="nope")["error"])

    def test_the_protected_area_hatch_is_a_diagonal_brush_with_an_outline(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        layer = _polygons("pa", ["Reserve"], field="name")
        result = apply_land_cover_look("pa", "protected_area_hatch")
        self.assertTrue(result.get("success"), result)
        self.assertFalse(result["legend_names_included"])
        renderer = layer.renderer()
        self.assertIsInstance(renderer, QgsSingleSymbolRenderer)
        sl = renderer.symbol().symbolLayer(0)
        self.assertIsInstance(sl, QgsSimpleFillSymbolLayer)
        self.assertEqual(sl.brushStyle(), Qt.BrushStyle.BDiagPattern)
        self.assertEqual(sl.fillColor().name().lower(), "#404040")
        self.assertEqual(sl.strokeColor().name().lower(), "#404040")
        self.assertAlmostEqual(sl.strokeWidth(), 0.3)

    def test_the_hatch_is_refused_on_a_layer_that_is_not_a_polygon_layer(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        points = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "pts", "memory")
        QgsProject.instance().addMapLayer(points)
        self.assertIn("not a polygon layer", apply_land_cover_look("pts", "protected_area_hatch")["error"])


@unittest.skipUnless(LIVE and HAVE_GDAL, "requires real QGIS + gdal + numpy")
class TestRasterLooks(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp(prefix="cartogen_lc_")

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

    def test_a_classified_raster_gets_the_official_colours_and_named_classes(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        layer = self._add("wc", numpy.array([[10, 10, 20], [40, 80, 80], [95, 10, 20]]))
        result = apply_land_cover_look("wc", "esa_worldcover")
        self.assertTrue(result.get("success"), result)
        renderer = layer.renderer()
        self.assertIsInstance(renderer, QgsPalettedRasterRenderer)
        classes = {int(c.value): (c.label, c.color.name().lower()) for c in renderer.classes()}
        self.assertEqual(sorted(classes), [10, 20, 40, 80, 95])
        for code, (name, colour) in WORLDCOVER.items():
            self.assertEqual(classes[code], (f"{name} ({code})", colour))
        self.assertEqual(result["unmatched_values"], [])

    def test_a_cell_value_that_is_not_a_class_is_grey_and_reported(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        layer = self._add("wc2", numpy.array([[10, 10, 11], [10, 11, 10]]))
        result = apply_land_cover_look("wc2", "esa_worldcover")
        self.assertTrue(result.get("success"), result)
        classes = {int(c.value): (c.label, c.color.name().lower()) for c in layer.renderer().classes()}
        self.assertEqual(classes[11], ("11 (not in the ESA WorldCover legend)", "#bdbdbd"))
        self.assertEqual(result["unmatched_values"], ["11"])

    def test_change_classes_on_a_raster_of_minus_one_zero_one(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        layer = self._add("chg", numpy.array([[-1, 0, 1], [1, 0, -1]]))
        result = apply_land_cover_look("chg", "change_classes")
        self.assertTrue(result.get("success"), result)
        classes = {int(c.value): c.color.name().lower() for c in layer.renderer().classes()}
        self.assertEqual(classes, {-1: "#e66101", 0: "#cccccc", 1: "#5e3c99"})

    def test_a_raster_with_no_class_values_is_left_alone(self):
        from cartogen_ai.core.agent.tools.land_cover_look_tool import apply_land_cover_look
        layer = self._add("plain", numpy.array([[1, 2], [3, 4]]))
        before = layer.renderer().type()
        result = apply_land_cover_look("plain", "esa_worldcover")
        self.assertIn("No cell value is in the ESA WorldCover legend", result["error"])
        self.assertEqual(layer.renderer().type(), before)


if __name__ == "__main__":
    unittest.main()
