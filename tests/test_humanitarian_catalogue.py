# -*- coding: utf-8 -*-
"""docs/HUMANITARIAN_TOOLS_CATALOGUE.md must only name tools that exist, and must list every tool added for the humanitarian workflows."""
import os
import re
import unittest

from cartogen_ai.core.agent.tools import TOOL_REGISTRY

DOC = os.path.join(os.path.dirname(__file__), "..", "docs", "HUMANITARIAN_TOOLS_CATALOGUE.md")
REQUIRED = {"apply_network_barriers", "generate_mapping_task_grid", "design_sampling_frame", "evaluate_forecast_trigger",
            "calculate_mcda_ranking", "aggregate_survey_indicator", "calculate_service_area", "classify_facilities_by_access",
            "calculate_severity_index", "calculate_presence_gap", "fetch_gdacs_disaster_alerts"}


class TestCatalogue(unittest.TestCase):
    def setUp(self):
        with open(DOC, encoding="utf-8") as fh:
            self.text = fh.read()

    def test_every_backticked_tool_name_exists(self):
        names = set(re.findall(r"`([a-z]+(?:_[a-z0-9]+)+)`", self.text))
        # words in backticks that are arguments or fields, not tools
        arguments = {"speed_field", "output_field", "buffer_m", "extent_layer", "pcode_field", "weight_field", "positive_values",
                     "plan_only", "source_layers", "invert_indicators", "top_k", "min_n", "rows_skipped", "unit_field",
                     "event_type", "date_field", "lead_days", "design_effect", "cell_size", "invert", "task_id", "area_km2", "pop_sum",
                     "pop_sum_", "alert_level", "access_class", "map_look", "people_in_need", "presence_gap", "output_layer_name", "pop_estimate", "key_figures", "body_text", "min_lon", "min_lat", "max_lon", "max_lat", "output_prefix"}
        unknown = sorted(n for n in names if n not in TOOL_REGISTRY and n not in arguments
                         and not n.startswith(("tests_", "test_", "src_", "docs_")) and "." not in n)
        # allow field/argument-like names that carry a placeholder or suffix
        unknown = [n for n in unknown if not re.search(r"(_score|_rank|_rank_min|_rank_max|_barrier_affected|_field|_layer|_m|_km2)$", n)]
        self.assertEqual(unknown, [], f"names in the catalogue that are not registered tools: {unknown}")

    def test_the_new_and_core_tools_are_listed(self):
        for name in REQUIRED:
            self.assertIn(f"`{name}`", self.text, name)

    def test_every_tool_heading_is_registered(self):
        for heading in re.findall(r"^### (.+)$", self.text, re.M):
            for name in re.findall(r"`([a-z_0-9]+)`", heading):
                self.assertIn(name, TOOL_REGISTRY, heading)


if __name__ == "__main__":
    unittest.main()
