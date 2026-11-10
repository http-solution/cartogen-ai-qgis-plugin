"""PLAN-023 R10-1: the pure request checks for virtual fields, constraints and defaults, and the violation summary. No QGIS and no numpy needed."""
import unittest

from cartogen_ai.core.agent.tools import field_rules as fr


class TestVirtual(unittest.TestCase):
    def test_valid_and_invalid_requests(self):
        self.assertIsNone(fr.check_virtual("density", "double", '"pop" / "area"'))
        self.assertIsNone(fr.check_virtual("label", None, "'x'"))
        for args in (("a:b", "double", "1"), ("", "double", "1"), ("1x", "double", "1"), ("d", "blob", "1"), ("d", "double", ""), ("d", "double", None), ("d", "double", "1" * 2001)):
            self.assertIsNotNone(fr.check_virtual(*args), args)


class TestConstraint(unittest.TestCase):
    def test_valid_requests(self):
        self.assertIsNone(fr.check_constraint(not_null=True))
        self.assertIsNone(fr.check_constraint(unique=False, strength="soft"))
        self.assertIsNone(fr.check_constraint(expression='"pop" >= 0', description="must not be negative"))
        self.assertIsNone(fr.check_constraint(expression=""))                         # removes the rule

    def test_invalid_requests(self):
        for kwargs in ({}, {"not_null": "yes"}, {"unique": 1}, {"expression": 5}, {"not_null": True, "strength": "firm"}, {"not_null": True, "description": "x"},
                       {"expression": "1", "description": 5}):
            self.assertIsNotNone(fr.check_constraint(**kwargs), kwargs)


class TestDefault(unittest.TestCase):
    def test_checks(self):
        self.assertIsNone(fr.check_default("now()"))
        self.assertIsNone(fr.check_default("", False))
        self.assertIsNone(fr.check_default("@user_account_name", True))
        for args in ((None,), (5,), ("1", "yes"), ("", True), ("1" * 2001,)):
            self.assertIsNotNone(fr.check_default(*args), args)


class TestSummary(unittest.TestCase):
    def test_twelve_violations_are_counted_and_the_first_ten_listed(self):
        rows = [(i, [f"bad {i % 2}"]) for i in range(12)]
        out = fr.summarise_violations(rows, 100)
        self.assertEqual((out["checked"], out["violations"], out["feature_ids"]), (100, 12, list(range(10))))
        self.assertEqual(out["examples"], ["bad 0", "bad 1"])

    def test_none(self):
        self.assertEqual(fr.summarise_violations([], 5), {"checked": 5, "violations": 0, "feature_ids": [], "examples": []})


if __name__ == "__main__":
    unittest.main()
