# -*- coding: utf-8 -*-
"""Tests for agent/tools/processing_allowlist_tools.py -- the Tier 2
allow-listed Processing algorithm runner, point 19's "larger question"
(docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md). Follows this
suite's established QGIS_AVAILABLE/QgsProject/processing patch convention
(e.g. tests/test_logistics_tools.py)."""
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS


class TestDegradesGracefullyOutsideQgis(unittest.TestCase):
    def test_degrades(self):
        result = run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "x"})
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])


class TestAllowListEnforcement(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_rejects_unlisted_algorithm_without_calling_processing_run(self, mock_processing):
        result = run_allowlisted_processing_algorithm("native:reallynotarealalg", {"INPUT": "x"})
        self.assertIn("error", result)
        self.assertIn("not on the allowed algorithm list", result["error"])
        mock_processing.run.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    def test_rejects_non_dict_params(self):
        result = run_allowlisted_processing_algorithm("native:buffer", "not a dict")
        self.assertIn("error", result)
        self.assertIn("params must be", result["error"])

    def test_allow_list_is_non_empty_and_all_native_or_known_provider_prefixed(self):
        self.assertGreater(len(ALLOWED_ALGORITHM_IDS), 20)
        for alg_id in ALLOWED_ALGORITHM_IDS:
            self.assertIn(":", alg_id)


class TestSuccessfulRun(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_registers_new_layer_and_reports_feature_count(self, mock_processing, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        new_layer = MagicMock()
        new_layer.featureCount.return_value = 3
        mock_processing.run.return_value = {"OUTPUT": new_layer}

        result = run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "roads", "DISTANCE": 500})

        self.assertTrue(result["success"])
        self.assertEqual(result["feature_count"], 3)
        self.assertNotIn("warning", result)
        new_layer.setName.assert_called_once_with("buffer_output")
        mock_project.instance.return_value.addMapLayer.assert_called_once_with(new_layer)

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_custom_layer_name_is_used_when_given(self, mock_processing, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        new_layer = MagicMock()
        new_layer.featureCount.return_value = 1
        mock_processing.run.return_value = {"OUTPUT": new_layer}

        run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "roads"}, new_layer_name="my_buffer")

        new_layer.setName.assert_called_once_with("my_buffer")

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_zero_feature_result_warns(self, mock_processing, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        new_layer = MagicMock()
        new_layer.featureCount.return_value = 0
        mock_processing.run.return_value = {"OUTPUT": new_layer}

        result = run_allowlisted_processing_algorithm("native:intersection", {"INPUT": "a", "OVERLAY": "b"})

        self.assertTrue(result["success"])
        self.assertEqual(result["feature_count"], 0)
        self.assertIn("warning", result)

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_no_output_layer_still_reports_success(self, mock_processing, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        mock_processing.run.return_value = {}

        result = run_allowlisted_processing_algorithm("native:selectbylocation", {"INPUT": "a", "INTERSECT": "b"})

        self.assertTrue(result["success"])
        mock_project.instance.return_value.addMapLayer.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_processing_run_exception_is_reported_not_raised(self, mock_processing, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        mock_processing.run.side_effect = RuntimeError("boom")

        result = run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "roads"})

        self.assertIn("error", result)
        self.assertIn("boom", result["error"])


class TestParamResolution(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_string_matching_loaded_layer_is_resolved_to_the_layer_object(self, mock_processing, mock_project):
        real_layer = MagicMock()

        def mapLayersByName(name):
            return [real_layer] if name == "roads" else []
        mock_project.instance.return_value.mapLayersByName.side_effect = mapLayersByName
        mock_processing.run.return_value = {}

        run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "roads", "DISTANCE": 500})

        called_alg, called_params = mock_processing.run.call_args[0]
        self.assertIs(called_params["INPUT"], real_layer)
        self.assertEqual(called_params["DISTANCE"], 500)

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_string_not_matching_any_layer_passes_through_literally(self, mock_processing, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        mock_processing.run.return_value = {}

        run_allowlisted_processing_algorithm("native:reprojectlayer", {"INPUT": "roads", "TARGET_CRS": "EPSG:4326"})

        _, called_params = mock_processing.run.call_args[0]
        self.assertEqual(called_params["TARGET_CRS"], "EPSG:4326")

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_output_key_is_always_forced_to_memory_regardless_of_input(self, mock_processing, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        mock_processing.run.return_value = {}

        run_allowlisted_processing_algorithm(
            "native:buffer", {"INPUT": "roads", "OUTPUT": "C:/Users/attacker/exfil.gpkg"},
        )

        _, called_params = mock_processing.run.call_args[0]
        self.assertEqual(called_params["OUTPUT"], "memory:")

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_output_key_is_injected_when_omitted_entirely(self, mock_processing, mock_project):
        """Live-confirmed against QGIS 4.2.2: processing.run() does NOT
        default a missing OUTPUT parameter itself -- it fails outright
        ('no value specified for parameter OUTPUT'). A caller omitting
        OUTPUT/OUTPUT_LINES entirely must still get a working call."""
        mock_project.instance.return_value.mapLayersByName.return_value = []
        mock_processing.run.return_value = {}

        run_allowlisted_processing_algorithm("native:centroids", {"INPUT": "roads"})

        _, called_params = mock_processing.run.call_args[0]
        self.assertEqual(called_params["OUTPUT"], "memory:")

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_output_lines_key_is_also_forced_to_memory(self, mock_processing, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        mock_processing.run.return_value = {}

        run_allowlisted_processing_algorithm(
            "native:serviceareafrompoint",
            {"INPUT": "roads", "OUTPUT_LINES": "/tmp/somewhere.gpkg"},
        )

        _, called_params = mock_processing.run.call_args[0]
        self.assertEqual(called_params["OUTPUT_LINES"], "memory:")

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_non_string_values_pass_through_unchanged(self, mock_processing, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        mock_processing.run.return_value = {}

        run_allowlisted_processing_algorithm(
            "native:buffer", {"INPUT": "roads", "DISTANCE": 500.5, "SEGMENTS": 8, "DISSOLVE": True},
        )

        _, called_params = mock_processing.run.call_args[0]
        self.assertEqual(called_params["DISTANCE"], 500.5)
        self.assertEqual(called_params["SEGMENTS"], 8)
        self.assertIs(called_params["DISSOLVE"], True)


if __name__ == "__main__":
    unittest.main()
