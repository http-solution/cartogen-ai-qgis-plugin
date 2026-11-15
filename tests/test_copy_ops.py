"""PLAN-023 R9-4: the pure field mapping and value conversion for copy_features_between_layers, with the plan's example as the known answer. No QGIS and no numpy needed."""
import unittest

from cartogen_ai.core.agent.tools import copy_ops as co


class TestMapping(unittest.TestCase):
    def test_explicit_and_same_name_pairs_and_the_field_left_empty(self):
        pairs, empty, unused, err = co.resolve_mapping(["name", "pop"], ["title", "pop", "note"], {"title": "name"})
        self.assertIsNone(err)
        self.assertEqual(sorted(pairs), [("name", "title"), ("pop", "pop")])
        self.assertEqual((empty, unused), (["note"], []))

    def test_names_match_without_regard_to_case_and_unused_source_fields_are_listed(self):
        pairs, empty, unused, _ = co.resolve_mapping(["NAME", "extra"], ["name"])
        self.assertEqual((pairs, empty, unused), ([("NAME", "name")], [], ["extra"]))

    def test_fid_is_not_filled_by_name_but_can_be_on_purpose(self):
        self.assertEqual(co.resolve_mapping(["fid", "a"], ["fid", "a"])[0], [("a", "a")])
        self.assertEqual(co.resolve_mapping(["fid", "a"], ["fid", "a"], {"fid": "fid"})[0], [("fid", "fid"), ("a", "a")])

    def test_a_field_that_does_not_exist_is_an_error_not_a_skip(self):
        self.assertIn("no field 'zzz'", co.resolve_mapping(["a"], ["a"], {"zzz": "a"})[3])
        self.assertIn("no field 'zzz'", co.resolve_mapping(["a"], ["a"], {"a": "zzz"})[3])


class TestConvert(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(co.convert_value("12", "Int"), (12, None))
        self.assertEqual(co.convert_value(3.0, "LongLong"), (3, None))
        self.assertEqual(co.convert_value("2.5", "Double"), (2.5, None))
        self.assertEqual(co.convert_value(7, "String"), ("7", None))
        self.assertEqual(co.convert_value(None, "Int"), (None, None))
        self.assertEqual(co.convert_value("2020-01-01", "Other"), ("2020-01-01", None))

    def test_what_cannot_be_converted_is_an_error(self):
        for value, kind in (("abc", "Int"), (2.5, "Int"), ("x", "Double"), (float("nan"), "Double"), (float("inf"), "Int")):
            self.assertIsNotNone(co.convert_value(value, kind)[1], (value, kind))

    def test_type_names(self):
        for name, kind in (("integer", "Int"), ("Integer64", "LongLong"), ("double", "Double"), ("real", "Double"), ("string", "String"), ("text", "String"),
                           ("varchar(20)", "String"), ("date", "Other"), (None, "Other")):
            self.assertEqual(co.kind_from_type_name(name), kind, name)


class TestRequest(unittest.TestCase):
    def test_checks(self):
        self.assertIsNone(co.check_request("a", "b"))
        self.assertIsNone(co.check_request("a", "b", {"x": "y"}, None, True))
        for args in (("", "b"), ("a", "a"), ("a", "b", ["x"]), ("a", "b", {"x": 1}), ("a", "b", None, "1=1", True)):
            self.assertIsNotNone(co.check_request(*args), args)

    def test_words(self):
        self.assertEqual(co.describe_scope("selected", 3, 5), "the 3 selected feature(s) (of 5)")
        self.assertEqual(co.describe_scope("filter", 2, 5), "2 of 5 feature(s) that match the filter")
        self.assertEqual(co.describe_scope("all", 5, 5), "all 5 feature(s)")
        self.assertEqual(co.list_some(list("abcdefg")), "a, b, c, d, e ... (2 more)")


if __name__ == "__main__":
    unittest.main()
