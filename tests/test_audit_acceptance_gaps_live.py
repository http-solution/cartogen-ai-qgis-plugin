# -*- coding: utf-8 -*-
"""Acceptance lines of audit issues #139, #140, #141, #142 and #146 that the first live tests did not cover (null geometries; layer ids,
selected features and filtered sources; US-survey-foot and geographic units; dateline, pole and foot-unit CRSs; geometry, schema and
count edits after an isolated script). Written without a local QGIS: CI's first run is its first execution, and a failure here is a
finding about the code, not about the test, unless it shows a wrong expectation."""
import os
import shutil
import tempfile
import unittest

try:
    from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsPointXY,
                           QgsProcessingContext, QgsProcessingFeatureSourceDefinition, QgsProcessingFeedback, QgsProject,
                           QgsVectorLayer)
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

_KEEP_ALIVE = []


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _layer(kind, crs, wkts, name, fields="field=name:string"):
    layer = QgsVectorLayer(f"{kind}?crs={crs}&{fields}", name, "memory")
    feats = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(layer.fields())
        if wkt is not None:
            f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([f"{name}{i}"] + [0] * (layer.fields().count() - 1))
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


def _run(alg, params):
    context = QgsProcessingContext()
    _KEEP_ALIVE.append(context)
    context.setProject(QgsProject.instance())
    alg.initAlgorithm({})
    results, ok = alg.run(params, context, QgsProcessingFeedback())
    return results, ok, context


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class _Base(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)


class TestHubSitingAcceptance(_Base):
    """#139 and #142."""

    def _hub(self, cands, demand, **extra):
        from cartogen_ai.processing.provider import OptimalHubSitingAlgorithm
        params = {"INPUT_CANDIDATES": cands, "INPUT_DEMAND": demand, "OUTPUT": "memory:"}
        params.update(extra)
        results, ok, context = _run(OptimalHubSitingAlgorithm(), params)
        return ok, (context.getMapLayer(results["OUTPUT"]) if ok else None)

    def test_a_candidate_and_a_demand_point_without_geometry_do_not_crash(self):
        cands = _layer("Point", "EPSG:4326", ["POINT(0 0)", None], "cand")
        demand = _layer("Point", "EPSG:4326", ["POINT(0.005 0)", None], "dem")
        ok, out = self._hub(cands, demand)
        self.assertTrue(ok)
        self.assertEqual(out.featureCount(), 1)

    def test_an_empty_candidate_set_is_not_a_success(self):
        cands = _layer("Point", "EPSG:4326", [], "cand")
        demand = _layer("Point", "EPSG:4326", ["POINT(0 0)"], "dem")
        ok, out = self._hub(cands, demand)
        self.assertFalse(ok and out is not None and out.featureCount() > 0)

    def test_across_the_dateline_the_distance_is_short_not_the_long_way_round(self):
        # 0.02 degrees of longitude apart at the equator, either side of 180: ~2.2 km, not ~40,000 km.
        cands = _layer("Point", "EPSG:4326", ["POINT(179.99 0)"], "cand")
        demand = _layer("Point", "EPSG:4326", ["POINT(-179.99 0)"], "dem")
        ok, out = self._hub(cands, demand)
        self.assertTrue(ok)
        self.assertAlmostEqual(next(out.getFeatures())["avg_dist_m"], 2224.0, delta=150)

    def test_near_the_pole_the_distance_is_geodesic(self):
        # 180 degrees of longitude apart at 89.99 N: over the pole the two points are about 2 * 0.01 * 111.2 km = 2.2 km apart.
        cands = _layer("Point", "EPSG:4326", ["POINT(0 89.99)"], "cand")
        demand = _layer("Point", "EPSG:4326", ["POINT(180 89.99)"], "dem")
        ok, out = self._hub(cands, demand)
        self.assertTrue(ok)
        self.assertAlmostEqual(next(out.getFeatures())["avg_dist_m"], 2224.0, delta=250)

    def test_demand_in_a_us_survey_foot_crs_is_not_read_as_metres(self):
        ft = QgsCoordinateReferenceSystem("EPSG:2227")      # NAD83 / California zone 3 (ftUS)
        if not ft.isValid():
            self.skipTest("EPSG:2227 is not available")
        origin = QgsPointXY(-122.0, 37.5)
        east = QgsPointXY(-122.0 + 0.005, 37.5)            # about 440 m east
        to_ft = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), ft, QgsProject.instance())
        o, e = to_ft.transform(origin), to_ft.transform(east)
        cands = _layer("Point", "EPSG:4326", [f"POINT({origin.x()} {origin.y()})"], "cand")
        demand = _layer("Point", "EPSG:2227", [f"POINT({e.x()} {e.y()})"], "dem")
        ok, out = self._hub(cands, demand)
        self.assertTrue(ok)
        expected_m = 0.005 * 111320 * 0.7934          # cos(37.5 deg)
        self.assertAlmostEqual(next(out.getFeatures())["avg_dist_m"], expected_m, delta=expected_m * 0.03)
        self.assertGreater(o.x(), 1e6, "the foot-CRS coordinates are in the millions, which is what a metre reading would mangle")


class TestServiceAreaInputKinds(_Base):
    """#140: the algorithm is given a layer id, selected features and a filtered source, the way the dialog and a model give them."""

    def _run_alg(self, facilities, network):
        from cartogen_ai.processing.provider import CalculateServiceAreaAlgorithm
        params = {"INPUT_FACILITIES": facilities, "INPUT_NETWORK": network, "TRAVEL_COST": 500.0, "STRATEGY": 0,
                  "DEFAULT_SPEED": 50.0, "OUTPUT_LINES": "memory:"}
        results, ok, context = _run(CalculateServiceAreaAlgorithm(), params)
        return ok, (context.getMapLayer(results["OUTPUT_LINES"]) if ok else None)

    def _fixture(self):
        roads = _layer("LineString", "EPSG:4326", ["LINESTRING(0 0, 0.01 0)", "LINESTRING(1 1, 1.01 1)"], "roads")
        fac = _layer("Point", "EPSG:4326", ["POINT(0 0)", "POINT(1 1)"], "fac")
        QgsProject.instance().addMapLayers([roads, fac])
        return roads, fac

    def test_layer_ids_as_inputs(self):
        roads, fac = self._fixture()
        ok, out = self._run_alg(fac.id(), roads.id())
        self.assertTrue(ok)
        self.assertGreater(out.featureCount(), 0)

    def test_selected_features_only(self):
        roads, fac = self._fixture()
        fac.selectByIds([next(fac.getFeatures()).id()])        # the facility at the first road only
        source = QgsProcessingFeatureSourceDefinition(fac.id(), selectedFeaturesOnly=True)
        ok, out = self._run_alg(source, roads)
        self.assertTrue(ok)
        xs = [g.boundingBox().xMinimum() for g in (f.geometry() for f in out.getFeatures())]
        self.assertTrue(xs and max(xs) < 0.5, "only the first road should be reached when only the first facility is selected")

    def test_a_filtered_source(self):
        roads, fac = self._fixture()
        if not fac.setSubsetString('"name" = \'fac1\''):
            self.skipTest("the memory provider here does not support subset strings")
        ok, out = self._run_alg(fac, roads)
        self.assertTrue(ok)
        xs = [f.geometry().boundingBox().xMinimum() for f in out.getFeatures()]
        self.assertTrue(xs and min(xs) > 0.5, "only the second road should be reached when the layer is filtered to the second facility")


class TestSiUnitsOtherUnits(_Base):
    """#141: area/length in the SI-named fields whatever the layer's CRS units and the project's units are."""

    def test_area_of_a_us_survey_foot_layer_in_square_metres_with_the_project_in_square_feet(self):
        from cartogen_ai.core.agent.tools.vector_tools import calculate_area
        ft = QgsCoordinateReferenceSystem("EPSG:2227")
        if not ft.isValid():
            self.skipTest("EPSG:2227 is not available")
        project = QgsProject.instance()
        project.setAreaUnits(Qgis.AreaUnit.SquareFeet)
        layer = _layer("Polygon", "EPSG:2227", ["POLYGON((6000000 2000000, 6001000 2000000, 6001000 2001000, 6000000 2001000, 6000000 2000000))"],
                       "ft", fields="field=name:string&field=keep:integer")
        project.addMapLayer(layer)
        res = calculate_area("ft", confirmed=True)
        self.assertTrue(res.get("success"), res)
        value = next(layer.getFeatures())["area_sqm"]
        self.assertAlmostEqual(value / 92903.4, 1.0, delta=0.02)      # 1,000,000 ftUS2 is about 92,903 m2

    def test_length_of_a_geographic_layer_in_metres_with_the_project_in_miles(self):
        from cartogen_ai.core.agent.tools.vector_tools import calculate_length
        project = QgsProject.instance()
        project.setDistanceUnits(Qgis.DistanceUnit.Miles)
        layer = _layer("LineString", "EPSG:4326", ["LINESTRING(0 0, 0.01 0)"], "ln", fields="field=name:string&field=keep:integer")
        project.addMapLayer(layer)
        res = calculate_length("ln", confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertAlmostEqual(next(layer.getFeatures())["length_m"], 1113.2, delta=15)


class TestReconcileOtherEdits(_Base):
    """#146: geometry, schema and count changes made by an isolated script either reach the live layer or come back as explicit problems,
    and never leave the live layer damaged."""

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.mkdtemp(prefix="cartogen_reconcile_gaps_")
        self.addCleanup(shutil.rmtree, self.tempdir, True)
        self.live = _layer("Point", "EPSG:4326", ["POINT(0 0)", "POINT(1 1)"], "mem", fields="field=name:string&field=v:integer")
        QgsProject.instance().addMapLayer(self.live)
        self.pre_ids = set(QgsProject.instance().mapLayers().keys())

    def _reconcile(self, change):
        from cartogen_ai.core.agent.services import script_isolation as si
        scratch, memory_ids = si._build_scratch_project(self.tempdir)
        result = QgsProject()
        result.read(scratch)
        change(result.mapLayersByName("mem")[0])
        path = os.path.join(self.tempdir, "result.qgz")
        result.write(path)
        return si._reconcile_results(path, self.pre_ids, memory_ids)

    def _assert_reconciled_or_explicit(self, outcome, reconciled):
        _new, updated, problems = outcome
        self.assertTrue(updated == ["mem"] and reconciled() or bool(problems), f"silently ignored: updated={updated} problems={problems}")
        self.assertEqual(self.live.featureCount() > 0, True, "the live layer must not be emptied")
        self.assertTrue(self.live.isValid())

    def test_a_geometry_edit_with_the_same_feature_count(self):
        def change(layer):
            layer.startEditing()
            fid = next(layer.getFeatures()).id()
            layer.changeGeometry(fid, QgsGeometry.fromWkt("POINT(5 5)"))
            self.assertTrue(layer.commitChanges())
        outcome = self._reconcile(change)
        self._assert_reconciled_or_explicit(outcome, lambda: any(abs(f.geometry().asPoint().x() - 5) < 1e-9 for f in self.live.getFeatures()))

    def test_a_new_field(self):
        from qgis.PyQt.QtCore import QVariant
        from qgis.core import QgsField

        def change(layer):
            layer.startEditing()
            layer.addAttribute(QgsField("extra", QVariant.Int))
            self.assertTrue(layer.commitChanges())
        outcome = self._reconcile(change)
        self._assert_reconciled_or_explicit(outcome, lambda: self.live.fields().indexOf("extra") >= 0)

    def test_a_deleted_feature(self):
        def change(layer):
            layer.startEditing()
            layer.deleteFeature(next(layer.getFeatures()).id())
            self.assertTrue(layer.commitChanges())
        outcome = self._reconcile(change)
        self._assert_reconciled_or_explicit(outcome, lambda: self.live.featureCount() == 1)


if __name__ == "__main__":
    unittest.main()
