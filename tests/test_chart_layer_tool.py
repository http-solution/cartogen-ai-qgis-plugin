"""chart_field_by_category (LR-24): the pure aggregation and the routing; the QGIS half is in test_chart_layer_tool_live.py."""
import unittest
from typing import ClassVar

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import chart_layer_tool as clt
from cartogen_ai.core.services.tool_router import ToolRouter


class TestAggregate(unittest.TestCase):
    def test_counts_per_category_largest_first_ties_by_label(self):
        rows, skipped = clt.aggregate_by_category([("b", None), ("a", None), ("b", None), ("c", None), ("a", None)], "count")
        self.assertEqual(rows, [("a", 2), ("b", 2), ("c", 1)])
        self.assertEqual(skipped, 0)

    def test_a_missing_category_is_named_not_dropped(self):
        rows, _ = clt.aggregate_by_category([(None, None), ("", None), ("NULL", None), ("x", None)], "count")
        self.assertEqual(rows, [(clt.NO_VALUE_LABEL, 3), ("x", 1)])

    def test_sum_mean_min_max_skip_numbers_that_are_missing_and_say_how_many(self):
        pairs = [("a", 10), ("a", 20), ("b", 5), ("b", None), ("c", "n/a"), ("c", True)]
        self.assertEqual(clt.aggregate_by_category(pairs, "sum"), ([("a", 30.0), ("b", 5.0)], 3))
        self.assertEqual(clt.aggregate_by_category(pairs, "mean")[0], [("a", 15.0), ("b", 5.0)])
        self.assertEqual(clt.aggregate_by_category(pairs, "min")[0], [("a", 10.0), ("b", 5.0)])
        self.assertEqual(clt.aggregate_by_category(pairs, "max")[0], [("a", 20.0), ("b", 5.0)])

    def test_the_figures_are_the_data_not_a_model_typed_number(self):
        # the 2026-11-20 run charted 3.001 / 3.001 / 3.001 typed by the model; here a count can only be the number of features
        rows, _ = clt.aggregate_by_category([("urban", None)] * 3 + [("open", None)] * 2 + [("mixed", None)], "count")
        self.assertEqual(dict(rows), {"urban": 3, "open": 2, "mixed": 1})


class TestCap(unittest.TestCase):
    ROWS: ClassVar[list] = [("a", 9), ("b", 8), ("c", 7), ("d", 1), ("e", 1)]

    def test_within_the_cap_nothing_changes(self):
        self.assertEqual(clt.cap_categories(self.ROWS, "count", 5), (self.ROWS, None))
        self.assertEqual(clt.cap_categories(self.ROWS, "count", 0), (self.ROWS, None))

    def test_counts_and_sums_combine_the_rest_into_other(self):
        rows, note = clt.cap_categories(self.ROWS, "count", 3)
        self.assertEqual(rows, [("a", 9), ("b", 8), ("Other", 9)])      # the chart has top_n bars: two kept plus Other (7 + 1 + 1)
        self.assertEqual(sum(v for _l, v in rows), sum(v for _l, v in self.ROWS))      # nothing is lost
        self.assertIn("3 smallest categories", note)

    def test_a_mean_cannot_be_added_so_the_rest_are_left_out_and_said(self):
        rows, note = clt.cap_categories(self.ROWS, "mean", 3)
        self.assertEqual(rows, [("a", 9), ("b", 8), ("c", 7)])
        self.assertIn("2 categories with a lower mean are left out", note)


class TestRoutingAndRegistration(unittest.TestCase):
    def test_a_chart_request_is_offered_the_one_call_tool(self):
        router = ToolRouter(TOOLS_SCHEMA)
        for query in ("make a bar chart of smoke_zones by zone_type", "pie chart of cases per district", "bar chart of the number of features per category in roads"):
            names = [t["function"]["name"] for t in router.filter_relevant_tools(query)]
            self.assertIn("chart_field_by_category", names, query)
            self.assertIn("generate_chart", names, query)         # still there for data that is not in a layer

    def test_it_is_registered_with_a_required_layer_and_field_and_an_operation_type(self):
        from cartogen_ai.core import tool_operations
        spec = next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "chart_field_by_category")
        self.assertEqual(spec["parameters"]["required"], ["layer_name", "category_field"])
        self.assertEqual(tool_operations.get_tool_operation_type("chart_field_by_category"), tool_operations.get_tool_operation_type("generate_chart"))
        self.assertIn("ONE call", spec["description"])
