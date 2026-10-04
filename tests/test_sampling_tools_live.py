# -*- coding: utf-8 -*-
"""Live-QGIS tests for H3 design_sampling_frame. Written without a QGIS install: CI's first run is their first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _strata():
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=hh:integer", "strata", "memory")
    rows = [("North", 400, "POLYGON((44.0 15.1, 44.1 15.1, 44.1 15.2, 44.0 15.2, 44.0 15.1))"),
            ("South", 60, "POLYGON((44.0 15.0, 44.1 15.0, 44.1 15.1, 44.0 15.1, 44.0 15.0))")]
    feats = []
    for name, hh, wkt in rows:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([name, hh])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


def _units(n_north, n_south):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=n:integer", "households", "memory")
    feats = []
    for i in range(n_north):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({44.001 + i * 0.0002} 15.15)"))
        f.setAttributes([i])
        feats.append(f)
    for i in range(n_south):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({44.001 + i * 0.0002} 15.05)"))
        f.setAttributes([i])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestDesignSamplingFrame(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        QgsProject.instance().addMapLayer(_strata())

    def _run(self, **kw):
        from cartogen_ai.core.agent.tools.sampling_tools import design_sampling_frame
        return design_sampling_frame("strata", stratum_field="name", **kw)

    def test_plan_only_uses_the_population_field_and_creates_no_layer(self):
        res = self._run(population_attribute="hh", plan_only=True, seed=1)
        self.assertTrue(res.get("success"), res)
        by = {r["stratum"]: r for r in res["strata"]}
        self.assertEqual(by["North"]["sample_required"], 197)     # n0 384.16, N = 400
        self.assertEqual(by["South"]["sample_required"], 53)      # N = 60
        self.assertEqual(res["total_required"], 250)
        self.assertEqual(QgsProject.instance().mapLayersByName("survey_sample"), [])

    def test_random_points_land_inside_their_stratum_and_the_seed_repeats(self):
        a = self._run(population_attribute="hh", seed=5)
        self.assertTrue(a.get("success"), a)
        self.assertEqual(a["total_drawn"], a["total_required"])
        layer = QgsProject.instance().mapLayersByName("survey_sample")[0]
        first = sorted((f["sample_id"], round(f.geometry().asPoint().x(), 9)) for f in layer.getFeatures())
        for f in layer.getFeatures():
            if f["stratum"] == "South":
                self.assertLess(f.geometry().asPoint().y(), 15.1)
            else:
                self.assertGreaterEqual(f.geometry().asPoint().y(), 15.1)
        QgsProject.instance().removeMapLayer(layer.id())
        self._run(population_attribute="hh", seed=5)
        again = QgsProject.instance().mapLayersByName("survey_sample")[0]
        self.assertEqual(first, sorted((f["sample_id"], round(f.geometry().asPoint().x(), 9)) for f in again.getFeatures()))
        self.assertIn("warnings", a)      # the random-points caveat

    def test_candidate_units_are_sampled_and_a_short_stratum_is_flagged(self):
        QgsProject.instance().addMapLayer(_units(300, 20))
        res = self._run(units_layer="households", seed=3)
        self.assertTrue(res.get("success"), res)
        by = {r["stratum"]: r for r in res["strata"]}
        self.assertEqual(by["South"]["population"], 20)
        self.assertEqual(by["South"]["sample_drawn"], by["South"]["sample_required"])
        self.assertLessEqual(by["South"]["sample_drawn"], 20)
        layer = QgsProject.instance().mapLayersByName("survey_sample")[0]
        ids = [f["sample_id"] for f in layer.getFeatures()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_bad_inputs_are_errors(self):
        from cartogen_ai.core.agent.tools.sampling_tools import design_sampling_frame
        self.assertIn("error", design_sampling_frame("ghost"))
        self.assertIn("error", design_sampling_frame("strata", stratum_field="nope"))
        self.assertIn("error", design_sampling_frame("strata", margin_of_error=0))


if __name__ == "__main__":
    unittest.main()
