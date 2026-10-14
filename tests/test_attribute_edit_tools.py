"""Pure parts of the M3 attribute/feature editing tools (tools/attribute_edit_tools.py) and that each is offered for its plain request.
The tools themselves run in tests/test_attribute_edit_tools_live.py."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import attribute_edit_tools as ae
from cartogen_ai.core.services.tool_router import ToolRouter


class TestCoerceValue(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(ae.coerce_value("5", "Int"), (5, None))
        self.assertEqual(ae.coerce_value("5.0", "Int"), (5, None))
        self.assertEqual(ae.coerce_value("2.5", "Numeric"), (2.5, None))
        self.assertEqual(ae.coerce_value(7, "Double"), (7.0, None))

    def test_a_typo_is_refused_not_turned_into_null(self):
        for bad, kind in (("abc", "Int"), ("2.5", "Int"), ("", "Numeric"), ("1,5", "Numeric")):
            value, err = ae.coerce_value(bad, kind)
            self.assertIsNone(value, bad)
            self.assertTrue(err, bad)

    def test_null_words_clear_the_value_and_text_passes_through(self):
        self.assertEqual(ae.coerce_value("null", "Numeric"), (None, None))
        self.assertEqual(ae.coerce_value(None, "String"), (None, None))
        self.assertEqual(ae.coerce_value("Amman", "String"), ("Amman", None))
        self.assertEqual(ae.coerce_value(12, "String"), ("12", None))


class TestPreview(unittest.TestCase):
    def test_shape_matches_what_the_orchestrator_expects(self):
        res = ae.preview("delete_features", {"layer_name": "a"}, "Delete 3 features.", "code")
        self.assertEqual(res["status"], "PREVIEW_REQUIRED")
        self.assertTrue(res["requires_confirmation"] and res["is_destructive"])
        self.assertEqual(res["arguments"], {"layer_name": "a", "confirmed": True})
        self.assertEqual(res["tool_name"], "delete_features")


class TestFieldTypes(unittest.TestCase):
    def test_words(self):
        self.assertEqual(ae.new_field_type("text"), "String")
        self.assertEqual(ae.new_field_type("bigint"), "LongLong")
        self.assertEqual(ae.new_field_type(None), "String")
        self.assertIsNone(ae.new_field_type("blob"))


class TestToolShapes(unittest.TestCase):
    def test_destructive_tools_take_confirmed_and_it_is_not_in_the_model_schema(self):
        import inspect
        registry = {t["function"]["name"]: t["function"] for t in TOOLS_SCHEMA}
        for name in ("delete_features", "delete_field", "set_attribute_value"):
            self.assertIn("confirmed", inspect.signature(getattr(ae, name)).parameters, name)
            self.assertNotIn("confirmed", registry[name]["parameters"]["properties"], name)

    def test_no_tool_deletes_everything_without_being_told_which(self):
        import inspect
        self.assertNotIn("all", inspect.signature(ae.delete_features).parameters)


class TestOffered(unittest.TestCase):
    ROWS = {  # noqa: RUF012
        "select the schools where population is over 500": "select_by_expression",
        "clear the selection": "clear_selection",
        "select all features in roads": "select_all_features",
        "delete the selected features from roads": "delete_features",
        "delete all features where type is private": "delete_features",
        "change the population of Amman to 4500000": "set_attribute_value",
        "add a column called notes to towns": "add_field",
        "rename the field pop to population": "rename_field",
        "delete the field notes": "delete_field",
        "add a polygon with this WKT POLYGON((0 0,1 0,1 1,0 0)) to parcels": "add_feature_from_wkt",
    }

    def test_each_phrase_is_offered_its_tool(self):
        router = ToolRouter(TOOLS_SCHEMA)
        missing = {q: t for q, t in self.ROWS.items() if t not in {x["function"]["name"] for x in router.filter_relevant_tools(q)}}
        self.assertEqual(missing, {})


if __name__ == "__main__":
    unittest.main()
