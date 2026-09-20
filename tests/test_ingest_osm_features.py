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


if __name__ == "__main__":
    unittest.main()
