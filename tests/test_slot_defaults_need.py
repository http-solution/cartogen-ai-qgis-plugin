"""#304 (rc40 hand test): a default is injected as "Given: slot = value" only for a task whose tools can use that slot."""
import unittest

from cartogen_ai.core.agent import task_matcher as tm


class TestDefaultsOnlyWhereUsed(unittest.TestCase):
    def test_threshold_is_not_injected_for_a_ranking_chain(self):
        entry = {"tools": ["optimal_hub_siting", "apply_categorized_style"]}
        self.assertEqual(tm.defaults(["threshold"], entry), {})

    def test_threshold_is_injected_for_a_service_area_chain(self):
        entry = {"tools": ["calculate_service_area"]}
        self.assertEqual(tm.defaults(["threshold"], entry), {"threshold": "5 km"})

    def test_imagery_is_not_injected_for_classifying_a_loaded_raster(self):
        entry = {"tools": ["unsupervised_classification"]}
        self.assertEqual(tm.defaults(["imagery"], entry), {})

    def test_imagery_is_injected_when_the_chain_fetches_imagery(self):
        entry = {"tools": ["search_stac_satellite_imagery", "calculate_ndvi"]}
        self.assertIn("imagery", tm.defaults(["imagery"], entry))

    def test_other_slots_and_the_no_entry_call_keep_the_old_behaviour(self):
        self.assertEqual(tm.defaults(["admin_level"], {"tools": ["x"]}), {"admin_level": "admin2"})
        self.assertIn("threshold", tm.defaults(["threshold"]))


if __name__ == "__main__":
    unittest.main()
