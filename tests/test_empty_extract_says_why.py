"""An extraction that returns nothing says why (DEF-22).

Why: in the owner's Taiz run (2026-11-01) native:extractbyexpression and native:extractbylocation both returned 0 features and the reply
only said "check the inputs". The log held no arguments, so the real cause is unknown; the reply now shows what the layer holds."""
import unittest

from cartogen_ai.core.agent.tools import processing_allowlist_tools as tools


class TestEmptyExtractSaysWhy(unittest.TestCase):
    def test_an_expression_miss_lists_the_values_the_field_holds(self):
        hint = tools.empty_extract_hint("native:extractbyexpression", {
            "input_name": "yem_adm2", "input_count": 333, "fields": ["ADM1_EN", "ADM2_EN"],
            "values": {"ADM1_EN": ["Aden", "Taizz", "Sana'a"]}, "expression": "\"ADM1_EN\" = 'Taiz'"})
        self.assertIn("none of the 333 features in yem_adm2", hint)
        self.assertIn("'Taizz'", hint)
        self.assertIn("spelling and case", hint)

    def test_a_long_value_list_is_cut(self):
        hint = tools.empty_extract_hint("native:extractbyexpression", {
            "input_count": 50, "values": {"F": [f"v{i}" for i in range(30)]}})
        self.assertIn("'v11'", hint)
        self.assertNotIn("'v12'", hint)
        self.assertIn("...", hint)

    def test_an_empty_input_is_blamed_not_the_filter(self):
        hint = tools.empty_extract_hint("native:extractbyexpression", {"input_name": "taiz", "input_count": 0})
        self.assertIn("input is empty, not the filter", hint)

    def test_a_location_miss_names_different_crs_and_non_overlap(self):
        hint = tools.empty_extract_hint("native:extractbylocation", {
            "input_name": "facilities", "input_count": 900, "other_name": "taiz_districts", "other_count": 23,
            "crs_input": "EPSG:4326", "crs_other": "EPSG:32638"})
        self.assertIn("different coordinate systems (EPSG:4326 and EPSG:32638)", hint)
        far = tools.empty_extract_hint("native:extractbylocation", {
            "input_count": 5, "other_count": 3, "extents_intersect": False})
        self.assertIn("extents do not overlap", far)

    def test_an_empty_comparison_layer_is_named(self):
        hint = tools.empty_extract_hint("native:extractbylocation", {
            "input_name": "facilities", "input_count": 900, "other_name": "taiz_clean", "other_count": 0})
        self.assertIn("taiz_clean is empty", hint)

    def test_other_algorithms_get_no_hint(self):
        self.assertEqual(tools.empty_extract_hint("native:buffer", {"input_count": 3}), "")
        self.assertNotIn("native:buffer", tools._EMPTY_HINT_ALGORITHM_IDS)

    def test_output_report_adds_why_empty_only_for_a_zero_feature_extraction(self):
        class Layer:
            def featureCount(self):
                return 0
        plain = tools._output_report(Layer(), "native:buffer", {})
        self.assertNotIn("why_empty", plain)
        self.assertIn("warning", plain)


if __name__ == "__main__":
    unittest.main()
