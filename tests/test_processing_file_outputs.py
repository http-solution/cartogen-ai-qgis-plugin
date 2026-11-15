"""PLAN-005 wave E1: the file-writing algorithms of the statistics and GDAL-vector families. Offline parts (the QGIS parts are in
tests/test_processing_file_output_family_live.py, which runs in CI): what is allow-listed and refused, how file destinations are resolved, what a
statistics result passes on to the model, and that the cloud-data gate still sees a sensitive layer named in the parameters."""
import unittest

from cartogen_ai.core.agent.tools import _processing_allowlist as allow
from cartogen_ai.core.agent.tools import processing_allowlist_tools as tools

REPORTS = {"native:basicstatisticsforfields", "native:listuniquevalues", "native:nearestneighbouranalysis", "native:rasterlayerstatistics",
           "native:rasterlayeruniquevaluesreport", "native:rastersurfacevolume"}
FILE_VECTORS = {"gdal:polygonize", "gdal:contour_polygon"}
TWINS = {"gdal:buffervectors", "gdal:clipvectorbyextent", "gdal:clipvectorbypolygon", "gdal:dissolve", "gdal:offsetcurve", "gdal:onesidebuffer",
         "gdal:pointsalonglines", "gdal:contour"}


class TestFamilies(unittest.TestCase):
    def test_the_eight_are_approved_and_named(self):
        self.assertEqual(set(allow.REPORT_ALGORITHM_IDS), REPORTS)
        self.assertEqual(set(allow.FILE_VECTOR_ALGORITHM_IDS), FILE_VECTORS)
        for alg_id in REPORTS | FILE_VECTORS:
            self.assertIn(alg_id, allow.ALLOWED_ALGORITHM_IDS)
            self.assertIn(alg_id, allow.FAMILY_NAMES)

    def test_the_twins_of_approved_algorithms_were_not_added(self):
        # owner decision 2026-10-23: a second route to the same result only adds ambiguity and tokens
        self.assertEqual(sorted(TWINS & set(allow.ALLOWED_ALGORITHM_IDS)), [])

    def test_raw_argument_parameters_stay_refused_for_the_new_gdal_ids(self):
        for alg_id in FILE_VECTORS:
            self.assertIn("EXTRA", tools.parameter_violation(alg_id, {"INPUT": "dem", "EXTRA": "-x"}) or "")
            self.assertIn("OPTIONS", tools.parameter_violation(alg_id, {"INPUT": "dem", "OPTIONS": "COMPRESS=LZW"}) or "")


class TestFileDestinations(unittest.TestCase):
    def test_a_report_file_destination_becomes_a_temporary_file_and_a_sink_stays_in_memory(self):
        resolved = tools._resolve_params(
            {"INPUT": "towns", "FIELD_NAME": "pop", "OUTPUT_HTML_FILE": "/home/user/secret.html"},
            destination_keys={"OUTPUT_HTML_FILE", "OUTPUT"}, raster_keys=set(), file_keys={"OUTPUT_HTML_FILE"})
        self.assertEqual(resolved["OUTPUT_HTML_FILE"], "TEMPORARY_OUTPUT")      # the path the caller supplied is ignored (rule R1)
        self.assertEqual(resolved["OUTPUT"], "memory:")

    def test_without_a_file_key_nothing_changes(self):
        resolved = tools._resolve_params({"INPUT": "towns", "OUTPUT": "/tmp/x.gpkg"}, destination_keys={"OUTPUT"}, raster_keys=set())
        self.assertEqual(resolved["OUTPUT"], "memory:")

    def test_file_vector_results_get_a_temporary_file(self):
        resolved = tools._resolve_params({"INPUT": "dem", "OUTPUT": "/tmp/x.gpkg"}, destination_keys={"OUTPUT"}, raster_keys=set(),
                                         temp_file_vectors=True)
        self.assertEqual(resolved["OUTPUT"], "TEMPORARY_OUTPUT")


class TestStatisticsReachTheModelBounded(unittest.TestCase):
    def test_numbers_and_short_text_pass_layers_paths_and_collections_do_not(self):
        class Layer:
            def setName(self, name):
                pass
        out = {"MEAN": 12.5, "COUNT": 40, "OK": True, "NOTE": "fine", "OUTPUT_HTML_FILE": "/tmp/report.html", "OUTPUT": Layer(),
               "LIST": [1, 2], "NESTED": {"a": 1}, "LONG": "x" * 500, "EMPTY": ""}
        found = tools.scalar_results(out, skip_keys={"OUTPUT_HTML_FILE"})
        self.assertEqual(found, {"MEAN": 12.5, "COUNT": 40, "OK": True, "NOTE": "fine"})

    def test_at_most_forty_values_are_passed_on(self):
        found = tools.scalar_results({f"K{i}": i for i in range(100)})
        self.assertEqual(len(found), tools.MAX_STATISTICS)

    def test_a_result_that_is_not_a_dict_gives_nothing(self):
        self.assertEqual(tools.scalar_results(None), {})

    def test_report_fields_are_added_to_a_result(self):
        result = tools._with_report_fields({"success": True, "alg_id": "native:rasterlayerstatistics", "message": "m"}, {"MEAN": 3.0},
                                           {"OUTPUT_HTML_FILE": "/tmp/r.html"})
        self.assertEqual(result["statistics"], {"MEAN": 3.0})
        self.assertIn("'statistics'", result["message"])
        self.assertEqual(result["report_files"], {"OUTPUT_HTML_FILE": "/tmp/r.html"})
        self.assertIn("temporary", result["report_note"])

    def test_a_layer_result_keeps_its_own_message(self):
        result = tools._with_report_fields({"success": True, "alg_id": "native:listuniquevalues", "layer_name": "uniq", "message": "m"},
                                           {"TOTAL_VALUES": 9}, {})
        self.assertEqual(result["message"], "m")
        self.assertEqual(result["statistics"], {"TOTAL_VALUES": 9})


class TestSensitiveLayersStayGated(unittest.TestCase):
    """PLAN-005 rule R3: statistics computed from a sensitive layer must not slip past the cloud-data gate. The gate reads the layer names out of
    the tool's arguments, including the nested params, so a statistics call naming a protected layer is stopped like any other call."""

    def test_a_statistics_call_naming_a_protected_layer_is_blocked(self):
        from cartogen_ai.core.models import egress_gate
        for alg_id in sorted(REPORTS):
            decision = egress_gate.evaluate(
                mode=egress_gate.MODE_ENFORCE, provider_is_local=False, tool_name="run_allowlisted_processing_algorithm",
                arguments={"alg_id": alg_id, "params": {"INPUT": "beneficiaries", "FIELD_NAME": "pop"}},
                project_layer_names=["beneficiaries", "districts"],
                get_level=lambda name: "SENSITIVE" if name == "beneficiaries" else "PUBLIC",
                get_sources=lambda name: [], strict=False)
            self.assertEqual(decision["action"], "block", alg_id)


if __name__ == "__main__":
    unittest.main()
