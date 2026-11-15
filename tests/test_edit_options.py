import unittest

from cartogen_ai.core.agent.tools.edit_options import (convert_value, conversion_kind, describe_transform, filter_violation,
                                                       transform_options)


class FilterTests(unittest.TestCase):
    def test_plain_conditions_pass(self):
        for ok in ('"pop" > 100', "name = 'select'", "\"type\" = 'it''s' AND id < 5", "a IN (1,2,3)"):
            self.assertIsNone(filter_violation(ok), ok)

    def test_dangerous_text_is_refused(self):
        for bad in ("", "  ", "1=1; DROP TABLE x", "a=1 -- c", "a=1 /* c */", "a IN (SELECT 1)", "a=1 UNION select 2",
                    "name = 'abc", "x" * 1001, "pg_sleep(5) > 0", "a=1\\"):
            self.assertIsNotNone(filter_violation(bad), bad)


class TransformTests(unittest.TestCase):
    def test_needs_one_transform(self):
        self.assertIsNotNone(transform_options()[1])
        self.assertEqual(transform_options(move_x="2")[0], {"move_x": 2.0})

    def test_bad_values(self):
        for kwargs in ({"move_x": "abc"}, {"scale_factor": 0}, {"scale_factor": -1}, {"rotate_degrees": float("nan")},
                       {"scale_factor": 1e9}):
            self.assertIsNotNone(transform_options(**kwargs)[1], kwargs)

    def test_describe(self):
        text = describe_transform({"move_x": 1.0, "rotate_degrees": 90.0, "scale_factor": 2.0})
        self.assertIn("move by (1, 0)", text)
        self.assertIn("rotate 90", text)
        self.assertIn("scale by 2", text)


class ConvertTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(conversion_kind("Integer"), "Int")
        self.assertIsNone(conversion_kind("date"))

    def test_values(self):
        self.assertEqual(convert_value("12", "Int"), (12, False))
        self.assertEqual(convert_value(1.5, "Int"), (1, True))
        self.assertEqual(convert_value("abc", "Double"), (None, True))
        self.assertEqual(convert_value(None, "Double"), (None, False))
        self.assertEqual(convert_value(3, "String"), ("3", False))
        self.assertEqual(convert_value(3e10, "Int"), (None, True))


if __name__ == "__main__":
    unittest.main()
