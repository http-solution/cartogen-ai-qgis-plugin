# -*- coding: utf-8 -*-
"""H5 calculate_mcda_ranking: scaling, ranking, weight-stability and validation are pure; layer work is in test_mcda_tools_live.py."""
import unittest

from cartogen_ai.core.agent.tools import mcda_tools as m


def crit(*pairs):
    return [{"field": f, "weight": w, "direction": d} for f, w, d in pairs]


class TestNormalise(unittest.TestCase):
    def test_higher_and_lower(self):
        self.assertEqual(m.normalise([0, 5, 10], "higher"), ([0.0, 0.5, 1.0], True))
        self.assertEqual(m.normalise([0, 5, 10], "lower"), ([1.0, 0.5, 0.0], True))

    def test_no_variation_is_flagged_and_neutral(self):
        self.assertEqual(m.normalise([4, 4, 4], "lower"), ([0.0, 0.0, 0.0], False))


class TestRank(unittest.TestCase):
    def test_competition_ranking_with_ties(self):
        self.assertEqual(m.rank([3, 1, 3, 2]), [1, 4, 1, 3])

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(m.normalise_weights([2, 3, 5])), 1.0)


class TestValidate(unittest.TestCase):
    def test_ok(self):
        self.assertIsNone(m.validate_criteria(crit(("a", 1, "higher"), ("b", 2, "lower"))))

    def test_problems(self):
        for bad in (None, [], [{"field": "a"}], crit(("a", 1, "higher"), ("a", 1, "higher")),
                    crit(("a", 0, "higher"), ("b", 1, "higher")), crit(("a", "x", "higher"), ("b", 1, "higher")),
                    crit(("a", 1, "up"), ("b", 1, "higher")), [{"field": ""}, {"field": "b"}]):
            self.assertIsNotNone(m.validate_criteria(bad), bad)

    def test_direction_defaults_to_higher(self):
        self.assertIsNone(m.validate_criteria([{"field": "a"}, {"field": "b"}]))


def rows():
    return [{"id": 1, "label": "A", "need": 90, "access": 10},
            {"id": 2, "label": "B", "need": 50, "access": 50},
            {"id": 3, "label": "C", "need": 10, "access": 90},
            {"id": 4, "label": "D", "need": None, "access": 20}]


class TestEvaluate(unittest.TestCase):
    def test_direction_decides_which_end_is_priority(self):
        out = m.evaluate(rows(), crit(("need", 1, "higher"), ("access", 1, "lower")), trials=50, seed=1)
        self.assertEqual([r["unit"] for r in out["results"]], ["A", "B", "C"])
        self.assertEqual(out["results"][0]["score"], 1.0)
        self.assertEqual(out["excluded"], ["D"])           # missing a value: excluded, never imputed

    def test_opposite_direction_reverses_the_ranking(self):
        out = m.evaluate(rows(), crit(("need", 1, "lower"), ("access", 1, "higher")), trials=50, seed=1)
        self.assertEqual([r["unit"] for r in out["results"]], ["C", "B", "A"])

    def test_weights_change_the_winner(self):
        a = m.evaluate(rows()[:3], crit(("need", 9, "higher"), ("access", 1, "higher")), trials=10, seed=1)
        self.assertEqual(a["results"][0]["unit"], "A")
        b = m.evaluate(rows()[:3], crit(("need", 1, "higher"), ("access", 9, "higher")), trials=10, seed=1)
        self.assertEqual(b["results"][0]["unit"], "C")
        self.assertEqual(a["weights"], {"need": 0.9, "access": 0.1})

    def test_fewer_than_two_complete_units_is_an_error(self):
        out = m.evaluate(rows()[2:], crit(("need", 1, "higher"), ("access", 1, "higher")))
        self.assertIn("error", out)

    def test_a_criterion_without_variation_is_reported(self):
        r = [{"id": i, "label": str(i), "a": i, "b": 5} for i in range(4)]
        self.assertEqual(m.evaluate(r, crit(("a", 1, "higher"), ("b", 1, "higher")), trials=5)["no_variation"], ["b"])


class TestStability(unittest.TestCase):
    def test_reproducible_for_a_seed(self):
        cols = [[0.0, 0.5, 1.0, 0.4], [1.0, 0.2, 0.3, 0.9]]
        a = m.stability(cols, [0.5, 0.5], trials=200, perturbation=0.3, seed=9, top_k=2)
        self.assertEqual(a, m.stability(cols, [0.5, 0.5], trials=200, perturbation=0.3, seed=9, top_k=2))

    def test_zero_perturbation_never_moves_a_rank(self):
        cols = [[0.0, 0.5, 1.0], [0.2, 0.9, 0.4]]
        for s in m.stability(cols, [0.5, 0.5], trials=20, perturbation=0.0, seed=1):
            self.assertEqual(s["rank_min"], s["rank_max"])

    def test_a_dominant_unit_stays_first_and_a_close_pair_swaps(self):
        cols = [[1.0, 0.0, 0.52, 0.5], [1.0, 0.0, 0.48, 0.5]]
        s = m.stability(cols, [0.5, 0.5], trials=300, perturbation=0.9, seed=3, top_k=1)
        self.assertEqual((s[0]["rank_min"], s[0]["rank_max"]), (1, 1))
        self.assertEqual(s[0]["top_k_share"], 1.0)
        self.assertTrue(s[2]["rank_max"] > s[2]["rank_min"] or s[3]["rank_max"] > s[3]["rank_min"])

    def test_top_k_share_is_none_without_top_k(self):
        self.assertIsNone(m.stability([[0.0, 1.0], [1.0, 0.0]], [0.5, 0.5], trials=5)[0]["top_k_share"])


class TestTool(unittest.TestCase):
    def test_wired_as_modify(self):
        from cartogen_ai.core.agent import tool_operations
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        self.assertIn("calculate_mcda_ranking", TOOL_REGISTRY)
        self.assertEqual(tool_operations.get_tool_operation_type("calculate_mcda_ranking"), tool_operations.MODIFY)

    def test_bad_arguments_are_refused_before_qgis(self):
        c = crit(("a", 1, "higher"), ("b", 1, "higher"))
        self.assertIn("criteria", m.calculate_mcda_ranking("l", [{"field": "a"}])["error"])
        self.assertIn("perturbation", m.calculate_mcda_ranking("l", c, perturbation=2)["error"])
        self.assertIn("trials", m.calculate_mcda_ranking("l", c, trials=0)["error"])
        self.assertIn("top_k", m.calculate_mcda_ranking("l", c, top_k=0)["error"])


if __name__ == "__main__":
    unittest.main()
