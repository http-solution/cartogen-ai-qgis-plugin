# -*- coding: utf-8 -*-
"""Requests answered from the open project with no model call (2026-10-10 hand test: 'List the layers' took 13 API calls)."""
import unittest

from cartogen_ai.core.ui import local_answers as la


class TestIsListLayersRequest(unittest.TestCase):
    def test_plain_list_requests_match(self):
        for text in ("List the layers in the project.", "list layers", "Show me the layers", "what layers are loaded",
                     "Please list all the layers in this project?", "show the loaded layers", "What layers are in the project",
                     "layers", "List my layers"):
            self.assertTrue(la.is_list_layers_request(text), text)

    def test_anything_with_more_to_do_goes_to_the_model(self):
        for text in ("List the layers and buffer the roads", "Show the layers that are polygons", "list the layers with more than 5 features",
                     "Remove the layers", "style the layers", "list the layer fields of smoke_admin", "", None, "x" * 200):
            self.assertFalse(la.is_list_layers_request(text), text)


class TestFormatLayerList(unittest.TestCase):
    SUMMARY = {"project_title": "Smoke", "canvas_crs": "EPSG:32636", "active_layer": "smoke_zones", "layer_count": 2, "truncated": False,
               "layers": [{"name": "smoke_admin", "type": "Vector", "crs": "EPSG:32636", "feature_count": 3, "fields": ["fid", "admin_name"]},
                          {"name": "smoke_dem", "type": "Raster", "crs": "EPSG:32636", "feature_count": None, "fields": []}]}

    def test_lists_every_layer_with_its_details_and_says_no_model_was_called(self):
        out = la.format_layer_list(self.SUMMARY)
        self.assertIn("2 layers", out)
        self.assertIn("| `smoke_admin` | Vector | EPSG:32636 | 3 | fid, admin_name |", out)
        self.assertIn("| `smoke_dem` | Raster | EPSG:32636 | - | - |", out)
        self.assertIn("No model was called", out)

    def test_an_empty_project_says_so(self):
        self.assertIn("no layers", la.format_layer_list({}).lower())

    def test_a_protected_layer_shows_no_fields_and_a_truncated_list_says_so(self):
        summary = dict(self.SUMMARY, truncated=True, layer_count=20)
        summary["layers"] = [dict(self.SUMMARY["layers"][0], schema_hidden=True, fields=[])]
        out = la.format_layer_list(summary)
        self.assertIn("withheld", out)
        self.assertIn("first 1 of 20", out)


if __name__ == "__main__":
    unittest.main()
