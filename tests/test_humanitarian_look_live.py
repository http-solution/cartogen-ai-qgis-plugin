# -*- coding: utf-8 -*-
"""HX1 humanitarian looks on result fields, in real QGIS. Written without a local QGIS: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsGeometry, QgsGraduatedSymbolRenderer, QgsProject,
                           QgsVectorLayer)
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

try:
    import numpy as np
    from osgeo import gdal, osr
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _districts(rows):
    """rows: dicts with name, sev (float or None), pin (float or None), gap (str or None), rnk (float or None)."""
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=sev:double&field=pin:double&field=gap:string&field=rnk:double",
                           "districts", "memory")
    feats = []
    for i, r in enumerate(rows):
        f = QgsFeature(layer.fields())
        x = 44.0 + i * 0.1
        f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 15, {x + 0.09} 15, {x + 0.09} 15.09, {x} 15.09, {x} 15))"))
        f.setAttributes([r["name"], r.get("sev"), r.get("pin"), r.get("gap"), r.get("rnk")])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


ROWS = [
    {"name": "A", "sev": 0.05, "pin": 0, "gap": "gap", "rnk": 1},
    {"name": "B", "sev": 0.2, "pin": 150, "gap": "covered", "rnk": 2},
    {"name": "C", "sev": 0.5, "pin": 2400, "gap": "unmatched", "rnk": 3},
    {"name": "D", "sev": 0.85, "pin": 52000, "gap": None, "rnk": 4},
    {"name": "E", "sev": None, "pin": None, "gap": None, "rnk": None},
]


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestApplyHumanitarianLook(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.layer = _districts(ROWS)

    def _look(self, look, field, **kw):
        from cartogen_ai.core.agent.tools.humanitarian_look_tools import apply_humanitarian_look
        return apply_humanitarian_look("districts", look, field, **kw)

    def test_severity_uses_five_classes_and_exact_boundaries_agree_with_the_tool(self):
        res = self._look("severity", "sev")
        self.assertTrue(res.get("success"), res)
        renderer = self.layer.renderer()
        self.assertIsInstance(renderer, QgsGraduatedSymbolRenderer)
        self.assertEqual(len(renderer.ranges()), 5)
        self.assertEqual(renderer.classAttribute(), "sev")
        # 0.2 is class 2 in calculate_severity_index; the second range must contain it and the first must not
        first, second = renderer.ranges()[0], renderer.ranges()[1]
        self.assertFalse(first.lowerValue() <= 0.2 <= first.upperValue())
        self.assertTrue(second.lowerValue() <= 0.2 <= second.upperValue())

    def test_severity_warns_when_the_field_is_not_a_zero_to_one_score(self):
        res = self._look("severity", "pin")
        self.assertTrue(res.get("success"), res)
        self.assertTrue(any("outside 0-1" in n for n in res["notes"]), res)

    def test_people_in_need_gives_graduated_count_classes_with_a_zero_class(self):
        res = self._look("people_in_need", "pin")
        self.assertTrue(res.get("success"), res)
        self.assertIsInstance(self.layer.renderer(), QgsGraduatedSymbolRenderer)
        self.assertIn("0", res["classes"])
        self.assertGreaterEqual(len(res["classes"]), 3)

    def test_presence_gap_is_categorized(self):
        res = self._look("presence_gap", "gap")
        self.assertTrue(res.get("success"), res)
        renderer = self.layer.renderer()
        self.assertIsInstance(renderer, QgsCategorizedSymbolRenderer)
        self.assertEqual({c.value() for c in renderer.categories()}, {"gap", "covered", "unmatched", ""})

    def test_rank_emphasises_the_top_units(self):
        res = self._look("rank", "rnk", top_k=2)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["classes"][0], "Rank 1 to 2")

    def test_errors_change_nothing(self):
        before = type(self.layer.renderer())
        self.assertIn("error", self._look("severity", "no_such_field"))
        self.assertIn("error", self._look("whatever", "sev"))
        self.assertIn("error", self._look("presence_gap", "name"))
        self.assertIs(type(self.layer.renderer()), before)

    def test_the_data_is_never_written(self):
        self._look("severity", "sev")
        self.assertEqual([f["sev"] for f in sorted(self.layer.getFeatures(), key=lambda f: f.id())], [r["sev"] for r in ROWS])


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestLooksForCreatedLayers(unittest.TestCase):
    """HX1b: layers the tools create themselves arrive styled."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _lines(self, values):
        layer = QgsVectorLayer("LineString?crs=EPSG:4326&field=highway:string", "osm_roads", "memory")
        feats = []
        for i, v in enumerate(values):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"LINESTRING({44 + i * 0.01} 15, {44 + i * 0.01} 15.01)"))
            f.setAttributes([v])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_osm_roads_are_graded_by_class_with_a_catch_all(self):
        from cartogen_ai.core.agent.tools.humanitarian_style import style_osm_layer
        layer = self._lines(["primary", "residential", "track", "weird_value"])
        self.assertTrue(style_osm_layer(layer))
        renderer = layer.renderer()
        self.assertEqual(renderer.type(), "RuleRenderer")
        labels = [r.label() for r in renderer.rootRule().children()]
        self.assertEqual(labels, ["Major roads", "Secondary roads", "Local roads", "Tracks and paths", "Other"])

    def test_osm_areas_and_other_lines_get_a_quiet_look(self):
        from cartogen_ai.core.agent.tools.humanitarian_style import style_osm_layer
        poly = _districts(ROWS)
        self.assertTrue(style_osm_layer(poly))
        self.assertEqual(poly.renderer().type(), "singleSymbol")

    def test_footprints_are_a_translucent_reference_layer(self):
        from cartogen_ai.core.agent.tools.humanitarian_style import style_footprints
        layer = _districts(ROWS)
        self.assertTrue(style_footprints(layer))
        self.assertEqual(layer.renderer().type(), "singleSymbol")
        self.assertLess(layer.opacity(), 1.0)

    def test_detected_features_are_banded_by_confidence(self):
        from cartogen_ai.core.agent.tools.humanitarian_style import style_detected_features
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=confidence:double", "det", "memory")
        QgsProject.instance().addMapLayer(layer)
        self.assertTrue(style_detected_features(layer))
        self.assertEqual(len(layer.renderer().ranges()), 3)
        self.assertFalse(style_detected_features(_districts(ROWS)))           # no confidence field: left alone


@unittest.skipUnless(QGIS_LIVE_AVAILABLE and GDAL_AVAILABLE, "requires real QGIS and GDAL")
class TestExposureOutputLayer(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, "pop.tif")
        arr = np.full((10, 40), 10.0, dtype="float32")
        ds = gdal.GetDriverByName("GTiff").Create(path, 40, 10, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((44.0, 0.01, 0, 15.1, 0, -0.01))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        ds.GetRasterBand(1).WriteArray(arr)
        ds.FlushCache()
        ds = None
        from qgis.core import QgsRasterLayer
        QgsProject.instance().addMapLayer(QgsRasterLayer(path, "pop"))
        self.zones = _districts([{"name": "A"}, {"name": "B"}])

    def test_a_styled_result_layer_is_added_and_the_area_layer_is_untouched(self):
        from cartogen_ai.core.agent.tools.raster_tools import estimate_population_exposure
        fields_before = [f.name() for f in self.zones.fields()]
        res = estimate_population_exposure("pop", "districts", output_layer_name="Exposure by district")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["output_layer"], "Exposure by district")
        layer = QgsProject.instance().mapLayersByName("Exposure by district")[0]
        self.assertEqual([f.name() for f in layer.fields()], ["zone", "feature_id", "pop_estimate"])
        self.assertEqual(layer.featureCount(), 2)
        self.assertIsInstance(layer.renderer(), QgsGraduatedSymbolRenderer)
        self.assertEqual([f.name() for f in self.zones.fields()], fields_before)

    def test_a_rerun_replaces_its_own_layer_but_never_a_users_layer(self):
        from cartogen_ai.core.agent.tools.raster_tools import estimate_population_exposure
        estimate_population_exposure("pop", "districts", output_layer_name="Exposure")
        estimate_population_exposure("pop", "districts", output_layer_name="Exposure")
        self.assertEqual(len(QgsProject.instance().mapLayersByName("Exposure")), 1)
        user = QgsVectorLayer("Point?crs=EPSG:4326", "Mine", "memory")
        QgsProject.instance().addMapLayer(user)
        res = estimate_population_exposure("pop", "districts", output_layer_name="Mine")
        self.assertEqual(res["output_layer"], "Mine (2)")
        self.assertEqual(len(QgsProject.instance().mapLayersByName("Mine")), 1)


if __name__ == "__main__":
    unittest.main()
