"""The synthetic fixture docs/release_smoke_assets/inputs/smoke_network.gpkg opens in real QGIS, and the two changes it was built to exercise
work on it: optimize_delivery_route(additional_stops_layers=...) (rc40) and the analysis output-field writes through the edit session (#293).

Needs real qgis.core + the Processing plugin (skipped otherwise). Written without a QGIS install; its first execution is CI."""
import os
import shutil
import tempfile
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes

INPUTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "release_smoke_assets", "inputs")
NETWORK = os.path.join(INPUTS, "smoke_network.gpkg")
DATA = os.path.join(INPUTS, "smoke_data.gpkg")

EXPECTED = {   # layer -> (features, geometry type name, EPSG)
    "smoke_roads": (24, "Line", "EPSG:32636"),
    "smoke_facilities": (8, "Point", "EPSG:32636"),
    "smoke_admin_dup": (4, "Polygon", "EPSG:32636"),
    "smoke_points_4326": (5, "Point", "EPSG:4326"),
    "smoke_hubs_4326": (3, "Point", "EPSG:4326"),
    "smoke_ubend_road": (1, "Line", "EPSG:32636"),
    "smoke_ubend_facilities": (2, "Point", "EPSG:32636"),
}


def _add(path, layer, name=None):
    vl = QgsVectorLayer(f"{path}|layername={layer}", name or layer, "ogr")
    assert vl.isValid(), f"{layer} did not open from {path}"
    QgsProject.instance().addMapLayer(vl)
    return vl


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings -- run from an OSGeo4W/QGIS Python")
class TestSmokeNetworkFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_every_layer_opens_with_the_documented_shape(self):
        for name, (count, geom, crs) in EXPECTED.items():
            vl = _add(NETWORK, name)
            self.assertEqual(vl.featureCount(), count, name)
            self.assertEqual(QgsWkbTypes.geometryDisplayString(vl.geometryType()), geom, name)
            self.assertEqual(vl.crs().authid(), crs, name)

    def test_the_road_layer_carries_geofabrik_style_oneway_values_and_missing_speeds(self):
        roads = _add(NETWORK, "smoke_roads")
        values = {f["oneway"] for f in roads.getFeatures()} - {None, "", "NULL"}
        self.assertEqual({str(v) for v in values}, {"B", "F", "T"})
        self.assertTrue(any(f["speed_kmh"] is None or f["speed_kmh"] == "" or str(f["speed_kmh"]) == "NULL" for f in roads.getFeatures()))

    def test_duplicate_and_empty_names_are_really_there(self):
        admin = _add(NETWORK, "smoke_admin_dup")
        names = [f["admin_name"] for f in admin.getFeatures()]
        self.assertEqual(names.count("Al-Dhale"), 2)
        self.assertEqual(sum(1 for n in names if n is None or str(n) in ("", "NULL")), 1)

    def test_the_4326_copies_sit_where_the_projected_originals_are(self):
        original = _add(DATA, "smoke_points")
        moved = _add(NETWORK, "smoke_points_4326")
        self.assertEqual({f["name"] for f in original.getFeatures()}, {f["name"] for f in moved.getFeatures()})
        box = moved.extent()
        self.assertTrue(35.9 < box.xMinimum() < box.xMaximum() < 35.96 and 31.9 < box.yMinimum() < box.yMaximum() < 32.0, box.toString())


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings -- run from an OSGeo4W/QGIS Python")
class TestToolsOnTheFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)
        from cartogen_ai.core.agent.tools import analysis_tools, logistics_tools
        cls.lt, cls.at = logistics_tools, analysis_tools

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        # The tools that write a field change the file; work on a copy so the checked-in fixture is never touched.
        self.scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.scratch, True)
        self.network = os.path.join(self.scratch, "smoke_network.gpkg")
        shutil.copy(NETWORK, self.network)
        self.addCleanup(QgsProject.instance().clear)

    def test_a_depot_in_another_layer_is_merged_into_the_route(self):
        _add(DATA, "smoke_points")
        _add(DATA, "smoke_hubs")
        res = self.lt.optimize_delivery_route("smoke_points", start_stop_name="Hub_A", additional_stops_layers=["smoke_hubs"])
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["stop_count"], 8)
        self.assertEqual(res["route_order"][0], "Hub_A")
        self.assertEqual(set(res["route_order"]), {"North", "Central", "East", "West", "South", "Hub_A", "Hub_B", "Hub_C"})
        self.assertEqual(res["additional_stops_layers"], ["smoke_hubs"])

    def test_a_depot_layer_in_another_crs_gives_the_same_route_length(self):
        _add(DATA, "smoke_points")
        _add(DATA, "smoke_hubs")
        same = self.lt.optimize_delivery_route("smoke_points", start_stop_name="Hub_A", additional_stops_layers=["smoke_hubs"])
        QgsProject.instance().removeMapLayer(QgsProject.instance().mapLayersByName("smoke_hubs")[0].id())
        _add(self.network, "smoke_hubs_4326", "smoke_hubs")
        other = self.lt.optimize_delivery_route("smoke_points", start_stop_name="Hub_A", additional_stops_layers=["smoke_hubs"])
        self.assertTrue(same.get("success") and other.get("success"), (same, other))
        self.assertEqual(same["route_order"], other["route_order"])
        self.assertAlmostEqual(same["total_distance"], other["total_distance"], delta=2.0)

    def test_score_fields_are_written_through_the_edit_session_by_feature_id(self):
        admin = _add(self.network, "smoke_admin_dup")
        res = self.at.calculate_severity_index("smoke_admin_dup", ["population", "need"], "admin_name", output_field="severity_test", confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertNotIn("output_field_warning", res, res)
        self.assertFalse(admin.isEditable(), "the tool must not leave the layer in edit mode when it started the session")
        self.assertGreaterEqual(admin.fields().indexOf("severity_test"), 0)
        by_fid = {f.id(): f["severity_test"] for f in admin.getFeatures()}
        self.assertEqual(len(by_fid), 4)
        self.assertTrue(all(v is not None and str(v) != "NULL" for v in by_fid.values()), by_fid)
        twins = [f["severity_test"] for f in admin.getFeatures() if f["admin_name"] == "Al-Dhale"]
        self.assertEqual(len(twins), 2)
        self.assertNotEqual(twins[0], twins[1], "two units that share a name must keep their own scores")

    def test_a_layer_the_user_is_editing_keeps_its_session_and_gets_the_values_in_the_buffer(self):
        admin = _add(self.network, "smoke_admin_dup")
        self.assertTrue(admin.startEditing())
        self.addCleanup(lambda: admin.rollBack() if admin.isEditable() else None)
        res = self.at.calculate_severity_index("smoke_admin_dup", ["population", "need"], "admin_name", output_field="severity_user", confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(admin.isEditable(), "the user's edit session must be left alone")
        self.assertTrue(admin.isModified(), "the new field and values wait in the user's buffer to be saved or discarded")


if __name__ == "__main__":
    unittest.main()
