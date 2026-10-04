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
    def test_unnamed_output_is_hidden_from_the_layer_tree(self, mock_processing, mock_project):
        """IMPLEMENTATION_TRACKER.md SS1.9, option 1: an unnamed output is treated as an
        internal scratch step (the caller didn't bother naming a real deliverable), so its
        layer-tree checkbox is unchecked rather than left cluttering the visible map."""
        mock_project.instance.return_value.mapLayersByName.return_value = []
        new_layer = MagicMock()
        new_layer.featureCount.return_value = 3
        new_layer.id.return_value = "layer123"
        mock_processing.run.return_value = {"OUTPUT": new_layer}
        layer_node = MagicMock()
        mock_project.instance.return_value.layerTreeRoot.return_value.findLayer.return_value = layer_node

        result = run_allowlisted_processing_algorithm("native:reprojectlayer", {"INPUT": "roads"})

        mock_project.instance.return_value.layerTreeRoot.return_value.findLayer.assert_called_once_with("layer123")
        layer_node.setItemVisibilityChecked.assert_called_once_with(False)
        self.assertFalse(result["visible"])

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_named_output_stays_visible(self, mock_processing, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        new_layer = MagicMock()
        new_layer.featureCount.return_value = 3
        mock_processing.run.return_value = {"OUTPUT": new_layer}

        result = run_allowlisted_processing_algorithm(
            "native:buffer", {"INPUT": "roads"}, new_layer_name="my_buffer",
        )

        mock_project.instance.return_value.layerTreeRoot.assert_not_called()
        self.assertTrue(result["visible"])

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


class TestNoFreeFormCodeSurface(unittest.TestCase):
    """GitHub #137 (audit F01): gdal:rastercalculator's FORMULA is evaluated with Python eval() by gdal_calc."""

    def test_the_gdal_raster_calculator_is_not_offered_by_the_generic_tool(self):
        from cartogen_ai.core.agent.tools._processing_allowlist import RASTER_OUTPUT_ALGORITHM_IDS
        self.assertNotIn("gdal:rastercalculator", ALLOWED_ALGORITHM_IDS)
        self.assertNotIn("gdal:rastercalculator", RASTER_OUTPUT_ALGORITHM_IDS)

    def test_no_allowlisted_id_is_a_raster_calculator_of_any_provider_that_takes_a_formula_string(self):
        for alg_id in ALLOWED_ALGORITHM_IDS:
            self.assertNotIn("rastercalc", alg_id.lower(), alg_id)

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_the_calculator_is_rejected_before_processing_runs(self, mock_processing):
        result = run_allowlisted_processing_algorithm("gdal:rastercalculator", {"FORMULA": "__import__('os').getcwd()"})
        self.assertIn("not on the allowed algorithm list", result["error"])
        mock_processing.run.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_formula_and_extra_parameters_are_rejected_for_every_algorithm_in_any_case(self, mock_processing):
        for key in ("FORMULA", "formula", "EXTRA", "Extra"):
            result = run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "x", key: "anything"})
            self.assertIn("error", result, key)
            self.assertIn("not accepted", result["error"], key)
        mock_processing.run.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_nested_objects_are_rejected(self, mock_processing):
        result = run_allowlisted_processing_algorithm("native:buffer", {"INPUT": {"nested": "x"}})
        self.assertIn("plain value", result["error"])
        mock_processing.run.assert_not_called()

    def test_ordinary_parameters_pass_the_check(self):
        from cartogen_ai.core.agent.tools._processing_allowlist import parameter_violation
        self.assertIsNone(parameter_violation("native:buffer", {"INPUT": "roads", "DISTANCE": 500, "LAYERS": ["a", "b"]}))
        self.assertIsNone(parameter_violation("native:buffer", None))

    def test_the_tool_description_no_longer_claims_there_is_no_code_execution_surface(self):
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY, TOOLS_SCHEMA
        self.assertIn("run_allowlisted_processing_algorithm", TOOL_REGISTRY)
        text = next(t["function"]["description"] for t in TOOLS_SCHEMA
                    if t["function"]["name"] == "run_allowlisted_processing_algorithm")
        self.assertNotIn("no code-execution surface", text)
        self.assertIn("FORMULA", text)


class TestParameterValidationAndOutputs(unittest.TestCase):
    """#163 (audit F27): unknown parameters are rejected before running; every layer output of an algorithm is returned; an algorithm
    that changes an existing layer is not described as creating a new one."""

    def test_unknown_parameters_are_listed(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import unknown_parameters
        self.assertEqual(unknown_parameters({"INPUT", "DISTANC", "OUTPUT"}, {"INPUT", "DISTANCE", "OUTPUT"}), ["DISTANC"])
        self.assertEqual(unknown_parameters(set(), {"A"}), [])
        self.assertEqual(unknown_parameters({"input"}, {"INPUT"}), ["input"])      # case-sensitive, like Processing

    def _definition(self, outputs=(("OUTPUT", "outputVector"),)):
        def out(name, kind):
            m = MagicMock()
            m.name.return_value = name
            m.type.return_value = kind
            return m
        return ({"INPUT", "DISTANCE", "OUTPUT"}, {"OUTPUT"}, set(), [out(n, k) for n, k in outputs])

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools._algorithm_definition")
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_a_misspelled_parameter_is_rejected_before_the_algorithm_runs(self, mock_processing, mock_def):
        mock_def.return_value = self._definition()
        result = run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "roads", "DISTANC": 5})
        self.assertIn("DISTANC", result["error"])
        self.assertIn("DISTANCE", result["error"])
        mock_processing.run.assert_not_called()

    def test_resolve_params_uses_the_defined_destinations_not_name_suffixes(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import _resolve_params
        with patch("cartogen_ai.core.agent.tools.processing_allowlist_tools._find_layer_by_name", return_value=None):
            out = _resolve_params({"INPUT": "x", "FOO": "/etc/passwd"}, destination_keys={"FOO", "BAR"}, raster_keys=set())
        self.assertEqual(out["FOO"], "memory:")                 # a destination named FOO is forced to memory
        self.assertEqual(out["BAR"], "memory:")                 # a destination the caller omitted is filled in
        self.assertEqual(out["INPUT"], "x")

    def test_resolve_params_keeps_the_old_default_when_the_registry_cannot_be_asked(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import _resolve_params
        with patch("cartogen_ai.core.agent.tools.processing_allowlist_tools._find_layer_by_name", return_value=None):
            self.assertEqual(_resolve_params({"INPUT": "x"})["OUTPUT"], "memory:")

    def test_harvest_returns_every_layer_output_in_declared_order(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import harvest_outputs
        lines, points = MagicMock(), MagicMock()
        out = harvest_outputs({"OUTPUT": points, "OUTPUT_LINES": lines, "COUNT": 3, "NOTE": "text"},
                              self._definition((("OUTPUT_LINES", "outputVector"), ("OUTPUT", "outputVector"))))
        self.assertEqual([k for k, _ in out], ["OUTPUT_LINES", "OUTPUT"])

    def test_harvest_reads_a_raster_path_only_for_a_declared_raster_output(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import harvest_outputs
        definition = self._definition((("OUTPUT", "outputRaster"), ("LOG", "outputString")))
        self.assertEqual(harvest_outputs({"OUTPUT": "/tmp/a.tif", "LOG": "/tmp/log.txt"}, definition), [("OUTPUT", "/tmp/a.tif")])
        self.assertEqual(harvest_outputs("not a dict"), [])

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools._algorithm_definition", return_value=None)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_select_by_location_reports_a_changed_selection_and_never_renames_the_input(self, mock_processing, mock_project, _def):
        users_layer = MagicMock()
        users_layer.name.return_value = "districts"
        users_layer.selectedFeatureCount.return_value = 4
        mock_project.instance.return_value.mapLayersByName.return_value = [users_layer]
        mock_processing.run.return_value = {"OUTPUT": users_layer}
        result = run_allowlisted_processing_algorithm("native:selectbylocation", {"INPUT": "districts", "PREDICATE": [0], "INTERSECT": "x"})
        self.assertTrue(result["changed_existing_layer"])
        self.assertEqual(result["selected_feature_count"], 4)
        self.assertEqual(result["layer_name"], "districts")
        users_layer.setName.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools._algorithm_definition")
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.processing_allowlist_tools.processing", create=True)
    def test_a_second_output_becomes_its_own_layer(self, mock_processing, mock_project, mock_def):
        mock_def.return_value = self._definition((("OUTPUT_LINES", "outputVector"), ("OUTPUT", "outputVector")))
        mock_project.instance.return_value.mapLayersByName.return_value = []
        lines, points = MagicMock(), MagicMock()
        lines.featureCount.return_value = 5
        points.featureCount.return_value = 2
        mock_processing.run.return_value = {"OUTPUT_LINES": lines, "OUTPUT": points}
        result = run_allowlisted_processing_algorithm("native:serviceareafrompoint", {"INPUT": "roads", "DISTANCE": 1}, new_layer_name="reach")
        self.assertEqual(result["layer_name"], "reach")
        lines.setName.assert_called_once_with("reach")
        points.setName.assert_called_once_with("reach_output")
        self.assertEqual(result["additional_outputs"], [{"output": "OUTPUT", "layer_name": "reach_output", "feature_count": 2}])

    def test_zonal_statistics_that_writes_into_its_input_is_no_longer_offered(self):
        self.assertNotIn("qgis:zonalstatistics", ALLOWED_ALGORITHM_IDS)
