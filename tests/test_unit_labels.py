"""#159: duplicate and NULL unit names must not share one result."""
import unittest

from cartogen_ai.core.agent.tools import analysis_tools as at
from cartogen_ai.core.agent.tools.raster_tools import unique_zone_keys


class _Feat:
    def __init__(self, fid, name):
        self._fid, self._name = fid, name

    def id(self):
        return self._fid

    def __getitem__(self, key):
        return self._name


class _Layer:
    def __init__(self, names):
        self._feats = [_Feat(i + 1, n) for i, n in enumerate(names)]

    def getFeatures(self):
        return iter(self._feats)


class TestUnitLabels(unittest.TestCase):
    def test_unique_names_are_untouched(self):
        labels, changed = at._unit_labels(_Layer(["A", "B", "C"]), "name")
        self.assertEqual((labels, changed), ({1: "A", 2: "B", 3: "C"}, 0))
        self.assertIsNone(at._label_note(changed))

    def test_repeated_and_empty_names_get_distinct_labels(self):
        labels, changed = at._unit_labels(_Layer(["Al Qafr", "Yarim", "Al Qafr", None, "", "  "]), "name")
        self.assertEqual(labels[1], "Al Qafr [#1]")
        self.assertEqual(labels[3], "Al Qafr [#3]")
        self.assertEqual(labels[2], "Yarim")
        self.assertEqual({labels[4], labels[5], labels[6]}, {"feature 4", "feature 5", "feature 6"})
        self.assertEqual(len(set(labels.values())), 6)
        self.assertEqual(changed, 5)
        self.assertIn("5 unit(s)", at._label_note(changed))

    def test_severity_scores_for_same_named_units_are_kept_apart(self):
        labels, _ = at._unit_labels(_Layer(["X", "X"]), "name")
        rows = [{"unit": labels[1], "__fid__": 1, "a": 1.0}, {"unit": labels[2], "__fid__": 2, "a": 9.0}]
        out = at._compute_severity_index(rows, ["a"])
        self.assertEqual(len(out["results"]), 2)
        by_unit = {r["unit"]: r["severity_score"] for r in out["results"]}
        self.assertNotEqual(by_unit["X [#1]"], by_unit["X [#2]"])

    def test_the_shared_rule_is_the_population_tools_rule(self):
        self.assertEqual(unique_zone_keys([(1, "A"), (2, "A"), (3, None)]), {1: "A [#1]", 2: "A [#2]", 3: "feature 3"})


if __name__ == "__main__":
    unittest.main()
