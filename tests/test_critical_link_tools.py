"""H9 critical links: the tree-load accumulation and class bounds, offline. The graph work needs QGIS (tests/test_critical_link_tools_live.py)."""
import itertools
import random
import unittest

from cartogen_ai.core.agent.tools import critical_link_tools as cl

INF = 1.0e308


def _brute(parents, costs, weights):
    """Load per edge by walking every destination's path to the root."""
    loads = {}
    for start, w in weights.items():
        if costs[start] >= cl.UNREACHABLE:
            continue
        v = start
        while parents[v] >= 0:
            loads[v] = loads.get(v, 0.0) + w
            v = parents[v]
    return loads


class TestAccumulate(unittest.TestCase):
    def test_chain(self):
        # 0 -> 1 -> 2 -> 3, demand 1 at 3 and 2 at 2
        loads, reached, unreached = cl.accumulate_tree_load([-1, 0, 1, 2], [0, 1, 2, 3], {3: 1.0, 2: 2.0})
        self.assertEqual(loads, {1: 3.0, 2: 3.0, 3: 1.0})
        self.assertEqual((reached, unreached), (3.0, 0.0))

    def test_branch_and_unreachable(self):
        #   0 -> 1 -> 2 ; 1 -> 3 ; vertex 4 unreachable
        loads, reached, unreached = cl.accumulate_tree_load([-1, 0, 1, 1, -1], [0, 1, 2, 2, INF], {2: 1.0, 3: 1.0, 4: 5.0})
        self.assertEqual(loads, {1: 2.0, 2: 1.0, 3: 1.0})
        self.assertEqual((reached, unreached), (2.0, 5.0))

    def test_zero_length_edges_do_not_break_the_order(self):
        loads, _r, _u = cl.accumulate_tree_load([-1, 0, 1], [0, 0, 0], {2: 1.0})
        self.assertEqual(loads, {1: 1.0, 2: 1.0})

    def test_matches_a_path_walk_on_random_trees(self):
        rng = random.Random(7)
        for _ in range(200):
            n = rng.randint(2, 40)
            parents, costs = [-1], [0.0]
            for v in range(1, n):
                if rng.random() < 0.1:
                    parents.append(-1)
                    costs.append(INF)
                else:
                    p = rng.choice([u for u in range(v) if costs[u] < cl.UNREACHABLE])
                    parents.append(p)
                    costs.append(costs[p] + rng.random())
            weights = {v: float(rng.randint(1, 5)) for v in rng.sample(range(n), rng.randint(1, n))}
            got, reached, unreached = cl.accumulate_tree_load(parents, costs, weights)
            want = _brute(parents, costs, weights)
            self.assertEqual({k: round(v, 9) for k, v in got.items() if v}, {k: round(v, 9) for k, v in want.items()})
            self.assertAlmostEqual(reached + unreached, sum(weights.values()))


class TestClasses(unittest.TestCase):
    def test_bounds_increase_and_cover_the_max(self):
        b = cl.classify_loads(list(range(1, 101)))
        self.assertEqual(b, [20, 40, 60, 80, 100])

    def test_few_distinct_values_give_fewer_classes_and_none_for_no_load(self):
        self.assertEqual(cl.classify_loads([3, 3, 3]), [3])
        self.assertEqual(cl.classify_loads([0, 0]), [])
        self.assertTrue(all(b > a for a, b in itertools.pairwise(cl.classify_loads([1, 1, 2, 9, 9, 9, 30]))))

    def test_edge_key_is_undirected(self):
        self.assertEqual(cl.edge_key(5, 2), cl.edge_key(2, 5))


if __name__ == "__main__":
    unittest.main()


class TestReadLimits(unittest.TestCase):
    """LR-21: the numeric limits of analyze_critical_links, split out of the tool."""

    def test_numbers_are_read_and_the_caps_applied(self):
        from cartogen_ai.core.agent.tools import critical_link_tools as clt
        limits, error = clt._read_limits("10", 9999, "500", "30")
        self.assertIsNone(error)
        self.assertEqual(limits, (10, clt._TOP_CAP, 500.0, 30.0))
        limits, _ = clt._read_limits(clt.MAX_ORIGINS + 50, 3, 1, 1)
        self.assertEqual(limits[0], clt.MAX_ORIGINS)

    def test_a_word_or_a_zero_is_refused_with_a_sentence(self):
        from cartogen_ai.core.agent.tools import critical_link_tools as clt
        self.assertIn("must be numbers", clt._read_limits("many", 5, 1, 1)[1])
        for bad in ((0, 5, 1, 1), (5, 5, 0, 1), (5, 5, 1, -2)):
            self.assertIn("above zero", clt._read_limits(*bad)[1])
