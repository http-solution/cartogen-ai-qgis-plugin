# -*- coding: utf-8 -*-
"""
Tests for ingest_osm_features two-phase vector ingestion.
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools.humanitarian_tools import (
    ingest_osm_features_network_phase,
    add_osm_layer_main_thread_phase,
    ingest_osm_features,
)
from cartogen_ai.core.agent.tools import TOOL_REGISTRY, TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter


class TestIngestOsmFeatures(unittest.TestCase):

    def test_registered_in_registry_and_schema(self):
        self.assertIn("ingest_osm_features", TOOL_REGISTRY)
        schema_names = [t["function"]["name"] for t in TOOLS_SCHEMA]
        self.assertIn("ingest_osm_features", schema_names)

    def test_network_phase_validation_missing_key_value(self):
        res = ingest_osm_features_network_phase(key="", value="hospital")
        self.assertIn("error", res)
        res = ingest_osm_features_network_phase(key="amenity", value="")
        self.assertIn("error", res)

    def test_network_phase_validation_missing_coordinates(self):
        res = ingest_osm_features_network_phase(key="amenity", value="hospital")
        self.assertIn("error", res)
        self.assertIn("Either 'bbox' ([south, west, north, east]) or ('center_lat', 'center_lon')", res["error"])

    def test_network_phase_validation_invalid_bbox(self):
        res = ingest_osm_features_network_phase(
            key="amenity", value="hospital", bbox=[35.0, 36.0, 31.0, 32.0]
        )
        self.assertIn("error", res)
        self.assertIn("Invalid bounding box", res["error"])

    @patch("urllib.request.urlopen")
    def test_network_phase_success_with_center_and_radius(self, mock_urlopen):
        mock_response_data = {
            "elements": [
                {
                    "type": "node",
                    "id": 1001,
                    "lat": 31.8995,
                    "lon": 35.8725,
                    "tags": {
                        "amenity": "hospital",
                        "name": "Al-Bashir Hospital",
                        "name:en": "Al-Bashir Hospital",
                        "beds": "500",
                    },
                },
                {
                    "type": "way",
                    "id": 2002,
                    "center": {"lat": 31.9010, "lon": 35.8740},
                    "tags": {
                        "amenity": "hospital",
                        "name": "Jordan University Hospital",
                        "emergency": "yes",
                    },
                },
            ]
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm
        mock_urlopen.return_value = mock_cm

        res = ingest_osm_features_network_phase(
            key="amenity",
            value="hospital",
            center_lat=31.89925,
            center_lon=35.87223,
            radius_km=5.0,
        )

        self.assertTrue(res.get("success"))
        self.assertEqual(res["feature_count"], 2)
        self.assertEqual(len(res["sample_names"]), 2)
        self.assertIn("Al-Bashir Hospital", res["sample_names"])
        self.assertIn("Jordan University Hospital", res["sample_names"])
        self.assertTrue(os.path.exists(res["local_path"]))

        # Verify GeoJSON content
        with open(res["local_path"], "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["type"], "FeatureCollection")
            self.assertEqual(len(data["features"]), 2)
            f0 = data["features"][0]
            self.assertEqual(f0["geometry"]["type"], "Point")
            self.assertEqual(f0["geometry"]["coordinates"], [35.8725, 31.8995])
            self.assertEqual(f0["properties"]["name"], "Al-Bashir Hospital")
            self.assertEqual(f0["properties"]["amenity"], "hospital")
            self.assertEqual(f0["properties"]["beds"], "500")

            f1 = data["features"][1]
            self.assertEqual(f1["geometry"]["type"], "Point")
            self.assertEqual(f1["geometry"]["coordinates"], [35.8740, 31.9010])
            self.assertEqual(f1["properties"]["name"], "Jordan University Hospital")

        # Cleanup
        os.remove(res["local_path"])

    @patch("urllib.request.urlopen")
    def test_network_phase_keeps_features_exactly_on_equator_or_prime_meridian(self, mock_urlopen):
        # Real bug found in a code-review pass (2026-09-20): `elem.get("lat") or
        # elem.get("center", {}).get("lat")` treats a genuine lat/lon of 0.0 as falsy,
        # falling through to the (nonexistent, for a plain node) "center" lookup and
        # silently dropping the feature -- relevant for real humanitarian mapping near the
        # equator/prime meridian (e.g. Ghana, Togo).
        mock_response_data = {
            "elements": [
                {
                    "type": "node", "id": 3003, "lat": 0.0, "lon": 35.0,
                    "tags": {"amenity": "hospital", "name": "Equator Clinic"},
                },
                {
                    "type": "node", "id": 3004, "lat": 6.0, "lon": 0.0,
                    "tags": {"amenity": "hospital", "name": "Prime Meridian Clinic"},
                },
            ]
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm
        mock_urlopen.return_value = mock_cm

        res = ingest_osm_features_network_phase(
            key="amenity", value="hospital",
            center_lat=3.0, center_lon=17.5, radius_km=2000.0,
        )

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["feature_count"], 2)
        with open(res["local_path"], "r", encoding="utf-8") as f:
            data = json.load(f)
        coords = [tuple(f["geometry"]["coordinates"]) for f in data["features"]]
        self.assertIn((35.0, 0.0), coords)
        self.assertIn((0.0, 6.0), coords)
        os.remove(res["local_path"])

    @patch("urllib.request.urlopen")
    def test_network_phase_no_features_found(self, mock_urlopen):
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps({"elements": []}).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm
        mock_urlopen.return_value = mock_cm

        res = ingest_osm_features_network_phase(
            key="amenity",
            value="hospital",
            bbox=[31.0, 35.0, 32.0, 36.0],
        )
        self.assertIn("error", res)
        self.assertIn("No OSM features found", res["error"])

    def test_main_thread_phase_error_passthrough(self):
        err_res = {"error": "Previous phase failed"}
        res = add_osm_layer_main_thread_phase(err_res)
        self.assertEqual(res, err_res)

    def test_main_thread_phase_outside_qgis(self):
        # Outside QGIS, QGIS_AVAILABLE is False, returns result dict without local_path
        fetch_res = {
            "success": True,
            "key": "amenity",
            "value": "hospital",
            "local_path": "/fake/path/file.geojson",
            "layer_name": "TestLayer",
        }
        res = add_osm_layer_main_thread_phase(fetch_res)
        self.assertTrue(res.get("success"))
        self.assertNotIn("local_path", res)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.ingest_osm_features_network_phase")
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.add_osm_layer_main_thread_phase")
    def test_standalone_ingest_cleans_up_temp_file(self, mock_main_phase, mock_net_phase):
        import tempfile
        fd, tmp_file = tempfile.mkstemp(suffix=".geojson")
        os.close(fd)

        mock_net_phase.return_value = {
            "success": True,
            "local_path": tmp_file,
            "layer_name": "OSM_amenity_hospital",
        }
        mock_main_phase.return_value = {
            "success": True,
            "layer_name": "OSM_amenity_hospital",
        }

        res = ingest_osm_features(
            key="amenity",
            value="hospital",
            bbox=[31.0, 35.0, 32.0, 36.0],
        )
        self.assertTrue(res["success"])
        # Should have cleaned up the file
        self.assertFalse(os.path.exists(tmp_file))

    def test_tool_router_aliases_include_ingest_osm_features(self):
        router = ToolRouter(TOOLS_SCHEMA)
        filtered = router.filter_relevant_tools("Health facilities beyond one hour's travel 31.89925,35.87223")
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("ingest_osm_features", names)

        filtered_osm = router.filter_relevant_tools("download osm data for hospitals and road network")
        names_osm = [t.get("function", {}).get("name") for t in filtered_osm]
        self.assertIn("ingest_osm_features", names_osm)


class TestOsmWayGeometry(unittest.TestCase):
    """Live-reported 2026-09-24: the query's `>; out skel qt;` returns every node that makes up a
    matched way, untagged. Each of those used to become its own point feature: building-outline
    corners became fake hospitals, and a road network came out as vertex points with no lines.
    The responses below have the shape Overpass really returns: tagged ways with a `nodes` list,
    then the untagged vertex nodes."""

    def _run(self, key, value, elements):
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps({"elements": elements}).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm
        with patch("urllib.request.urlopen", return_value=mock_cm):
            res = ingest_osm_features_network_phase(key=key, value=value, center_lat=31.95,
                                                    center_lon=35.90, radius_km=2)
        self.assertTrue(res.get("success"), res)
        with open(res["local_path"], encoding="utf-8") as f:
            data = json.load(f)
        os.remove(res["local_path"])
        return res, data["features"]

    def test_roads_become_lines_built_from_their_vertex_nodes(self):
        res, feats = self._run("highway", "primary|secondary", [
            {"type": "way", "id": 10, "nodes": [1, 2, 3], "center": {"lat": 31.951, "lon": 35.901},
             "tags": {"highway": "primary", "name": "Zahran St"}},
            {"type": "way", "id": 11, "nodes": [3, 4], "center": {"lat": 31.953, "lon": 35.903},
             "tags": {"highway": "secondary"}},
            {"type": "node", "id": 1, "lat": 31.950, "lon": 35.900},
            {"type": "node", "id": 2, "lat": 31.951, "lon": 35.901},
            {"type": "node", "id": 3, "lat": 31.952, "lon": 35.902},
            {"type": "node", "id": 4, "lat": 31.954, "lon": 35.904},
        ])
        self.assertEqual(res["feature_count"], 2)  # the 4 vertex nodes are not features
        self.assertEqual(res["geometry_type"], "LineString")
        self.assertEqual({f["geometry"]["type"] for f in feats}, {"LineString"})
        zahran = next(f for f in feats if f["properties"]["name"] == "Zahran St")
        self.assertEqual(zahran["geometry"]["coordinates"],
                         [[35.900, 31.950], [35.901, 31.951], [35.902, 31.952]])
        self.assertEqual(zahran["properties"]["highway"], "primary")

    def test_facility_outline_corners_are_not_extra_facilities(self):
        res, feats = self._run("amenity", "hospital", [
            {"type": "node", "id": 1, "lat": 31.95, "lon": 35.90,
             "tags": {"amenity": "hospital", "name": "Clinic A"}},
            {"type": "way", "id": 20, "nodes": [5, 6, 7, 5], "center": {"lat": 31.96, "lon": 35.91},
             "tags": {"amenity": "hospital", "name": "Hospital B"}},
            {"type": "node", "id": 5, "lat": 31.959, "lon": 35.909},
            {"type": "node", "id": 6, "lat": 31.961, "lon": 35.909},
            {"type": "node", "id": 7, "lat": 31.961, "lon": 35.911},
        ])
        self.assertEqual(res["feature_count"], 2)  # was 5: the 3 outline corners counted as hospitals
        self.assertEqual(res["geometry_type"], "Point")
        self.assertEqual(sorted(f["properties"]["name"] for f in feats), ["Clinic A", "Hospital B"])
        b = next(f for f in feats if f["properties"]["name"] == "Hospital B")
        self.assertEqual(b["geometry"]["coordinates"], [35.91, 31.96])  # the way's centre, as before

    def test_linear_key_with_only_nodes_stays_a_point_layer(self):
        # e.g. highway=bus_stop is mapped as nodes; there are no ways to draw lines from.
        res, feats = self._run("highway", "bus_stop", [
            {"type": "node", "id": 1, "lat": 31.95, "lon": 35.90,
             "tags": {"highway": "bus_stop", "name": "Stop 1"}},
        ])
        self.assertEqual(res["geometry_type"], "Point")
        self.assertEqual(len(feats), 1)


class TestOverpassResilience(unittest.TestCase):
    """Live-reported 2026-09-24: four back-to-back ingest_osm_features calls all got 504, and the
    model then burned its 20-call budget geocoding facilities one by one. Measured that evening,
    only 5 of 12 spaced requests to overpass-api.de succeeded, with failures scattered."""

    OK_BODY = {"elements": [{"type": "node", "id": 1, "lat": 31.95, "lon": 35.90,
                             "tags": {"amenity": "hospital", "name": "Clinic A"}}]}

    def _ok(self):
        cm = MagicMock()
        cm.read.return_value = json.dumps(self.OK_BODY).encode("utf-8")
        cm.__enter__.return_value = cm
        return cm

    @staticmethod
    def _http(code):
        import urllib.error
        return urllib.error.HTTPError("https://overpass-api.de/api/interpreter", code, "x", {}, None)

    def _run(self, side_effect, key="amenity", value="hospital"):
        with patch("urllib.request.urlopen", side_effect=side_effect) as mock_open,              patch("cartogen_ai.core.agent.tools._urllib_retry.time.sleep") as mock_sleep:
            res = ingest_osm_features_network_phase(key=key, value=value, center_lat=31.95,
                                                    center_lon=35.90, radius_km=2)
        if res.get("local_path"):
            os.remove(res["local_path"])
        return res, mock_open, mock_sleep

    def test_transient_504s_are_retried_inside_the_tool(self):
        res, mock_open, mock_sleep = self._run([self._http(504), self._http(429), self._http(504), self._ok()])
        self.assertTrue(res.get("success"), res)
        self.assertEqual(mock_open.call_count, 4)
        self.assertEqual([c.args[0] for c in mock_sleep.call_args_list], [3.0, 6.0, 9.0])

    def test_persistent_overload_tells_the_model_to_stop(self):
        res, mock_open, _ = self._run([self._http(504)] * 4)
        self.assertEqual(mock_open.call_count, 4)
        self.assertTrue(res.get("retryable_later"))
        self.assertIn("Don't call ingest_osm_features again in this turn", res["error"])
        self.assertIn("geocoding", res["error"])

    def test_a_bad_query_is_not_retried_or_called_overload(self):
        res, mock_open, _ = self._run([self._http(400)])
        self.assertEqual(mock_open.call_count, 1)
        self.assertNotIn("retryable_later", res)
        self.assertIn("Overpass API request failed", res["error"])

    def test_point_keys_skip_the_vertex_recursion(self):
        # Outline corners are only needed to draw lines; for points they just made the response
        # ~4x larger (live: 100 elements vs 24 for the same hospitals).
        _, mock_open, _ = self._run([self._ok()])
        self.assertNotIn(b"out skel", mock_open.call_args.args[0].data)
        _, mock_open, _ = self._run([self._ok()], key="highway", value="primary")
        self.assertIn(b"out skel", mock_open.call_args.args[0].data)


if __name__ == "__main__":
    unittest.main()
