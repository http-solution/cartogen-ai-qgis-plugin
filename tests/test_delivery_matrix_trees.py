"""Master list HU-3: optimize_delivery_route built its stop-to-stop distance matrix with one native:shortestpathpointtopoint call per stop pair, and every call rebuilds the whole road
graph (about 3 minutes each on 140,000 roads, rc11 smoke C1; 45 builds for a 10-stop route even after the undirected halving). The single-tree routine travel_time_matrix already uses
(checked against the native tool in CI) builds the graph once per ORIGIN. The matrix is now assembled from one tree per origin (n-1 for a two-way network, n with one-way streets), and falls
back to the native per-pair call for an origin whose tree cannot be built. Offline: the assembly and the wiring, with fakes. That the costs equal the native ones is checked live
(tests/test_delivery_matrix_live.py, CI only)."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core import _background_processing as bg
from cartogen_ai.core.agent.tools import logistics_tools as lt

INF = float("inf")


def fake_tree(distances, calls):
    """tree_costs(i, dest_indices) -> costs from a symmetric table; records each call."""
    def tree_costs(i, dests):
        calls.append((i, tuple(dests)))
        return [distances[i][j] for j in dests]
    return tree_costs


TABLE = [[0, 5, 9, 4], [5, 0, 3, 8], [9, 3, 0, 6], [4, 8, 6, 0]]


class TestAssembly(unittest.TestCase):
    def test_a_two_way_network_needs_one_tree_per_origin_except_the_last(self):
        calls = []
        matrix = lt._matrix_from_trees(4, True, fake_tree(TABLE, calls), lambda i, j: 999, lambda: False)
        self.assertEqual(calls, [(0, (1, 2, 3)), (1, (2, 3)), (2, (3,))])
        self.assertEqual(matrix, [[0.0 if i == j else float(TABLE[i][j]) for j in range(4)] for i in range(4)])

    def test_one_way_streets_keep_every_direction_so_every_origin_gets_a_tree(self):
        asym = [[0, 5, 9], [50, 0, 3], [90, 30, 0]]
        calls = []
        matrix = lt._matrix_from_trees(3, False, fake_tree(asym, calls), lambda i, j: 999, lambda: False)
        self.assertEqual([c[0] for c in calls], [0, 1, 2])
        self.assertEqual(matrix[1][0], 50.0)
        self.assertEqual(matrix[0][1], 5.0)

    def test_the_graph_builds_for_ten_stops_drop_from_45_to_9(self):
        calls = []
        n = 10
        table = [[abs(i - j) for j in range(n)] for i in range(n)]
        lt._matrix_from_trees(n, True, fake_tree(table, calls), lambda i, j: 0, lambda: False)
        self.assertEqual(len(calls), n - 1)
        self.assertLess(len(calls), n * (n - 1) // 2)

    def test_an_unreachable_stop_is_infinite_so_the_route_goes_around_it(self):
        def tree_costs(i, dests):
            return [None if j == 2 else 1.0 for j in dests]
        matrix = lt._matrix_from_trees(3, True, tree_costs, lambda i, j: 0, lambda: False)
        self.assertEqual(matrix[0][2], INF)
        self.assertEqual(matrix[2][0], INF)
        self.assertEqual(matrix[0][1], 1.0)

    def test_an_origin_whose_tree_cannot_be_built_falls_back_to_the_native_pair_call_for_its_row(self):
        def tree_costs(i, dests):
            if i == 0:
                raise RuntimeError("the origin could not be tied into the road network")
            return [7.0 for _ in dests]
        pairs = []

        def pair_cost(i, j):
            pairs.append((i, j))
            return 11.0
        matrix = lt._matrix_from_trees(3, True, tree_costs, pair_cost, lambda: False)
        self.assertEqual(pairs, [(0, 1), (0, 2)])
        self.assertEqual(matrix[0][1], 11.0)
        self.assertEqual(matrix[1][2], 7.0)

    def test_stop_is_honoured_between_origins(self):
        calls = []
        stop = {"now": False}

        def tree_costs(i, dests):
            calls.append(i)
            stop["now"] = True
            return [1.0 for _ in dests]
        with self.assertRaises(bg.AnalysisCancelledError):
            lt._matrix_from_trees(5, True, tree_costs, lambda i, j: 0, lambda: stop["now"])
        self.assertEqual(calls, [0])


def _geoms(n):
    out = []
    for i in range(n):
        g = MagicMock()
        g.asPoint.return_value = f"pt{i}"
        out.append(g)
    return out


class TestTheMatrixBuilder(unittest.TestCase):
    def _build(self, n, available, extra=None, fastest=False):
        trees, natives = [], []

        def single(network, origin_xy, dest_xys, strategy, default_speed, speed_field, direction_field, vf, vb, vboth, ellipsoid):
            trees.append((origin_xy, len(dest_xys), strategy, speed_field, direction_field, vf, vb, vboth))
            return [100.0 + k for k in range(len(dest_xys))]

        def native(alg, params, context, network, label):
            natives.append((params["START_POINT"], params["END_POINT"]))
            layer = MagicMock()
            layer.getFeatures.return_value = [{"cost": 42.0}]
            return {"OUTPUT": layer}

        context = MagicMock()
        with patch.object(lt, "single_tree_costs_available", return_value=available), patch.object(lt, "_single_tree_costs", single), \
                patch.object(lt, "_run_network_algorithm", native), patch.object(lt, "_network_context", return_value=context), \
                patch.object(lt, "_point_xy_in_network_crs", side_effect=lambda p, crs, net: f"xy:{p}"), \
                patch.object(lt, "_point_for_network", side_effect=lambda p, crs, net: f"native:{p}"):
            matrix = lt._build_network_distance_matrix("net", _geoms(n), extra, source_crs="crs", fastest=fastest, default_speed=40)
        return matrix, trees, natives

    def test_with_the_tree_routine_available_no_pair_call_is_made(self):
        matrix, trees, natives = self._build(4, True)
        self.assertEqual(len(trees), 3)
        self.assertEqual(natives, [])
        self.assertEqual(matrix[0][3], matrix[3][0])

    def test_without_it_the_native_pair_calls_are_used_exactly_as_before(self):
        _matrix, trees, natives = self._build(4, False)
        self.assertEqual(trees, [])
        self.assertEqual(len(natives), 6)               # n(n-1)/2 with the undirected halving, as before

    def test_the_speed_and_direction_settings_reach_the_tree(self):
        extra = {"SPEED_FIELD": "maxspeed", "DIRECTION_FIELD": "oneway", "VALUE_FORWARD": "yes", "VALUE_BACKWARD": "-1", "VALUE_BOTH": "no", "DEFAULT_DIRECTION": 2}
        _matrix, trees, _natives = self._build(3, True, extra=extra, fastest=True)
        _origin_xy, _dests, strategy, speed_field, direction_field, vf, vb, vboth = trees[0]
        self.assertEqual((strategy, speed_field, direction_field, vf, vb, vboth), ("fastest", "maxspeed", "oneway", "yes", "-1", "no"))
        self.assertEqual(len(trees), 3)                  # a direction field makes the network directed: every origin gets a tree

    def test_without_a_direction_field_the_strategy_is_shortest(self):
        _matrix, trees, _natives = self._build(3, True)
        self.assertEqual(trees[0][2], "shortest")


if __name__ == "__main__":
    unittest.main()
