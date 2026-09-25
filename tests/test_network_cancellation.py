# -*- coding: utf-8 -*-
"""Stop reaches a running network analysis, and no tool mistakes it for an ordinary failure.

BUG-2026-09-25-2: a routing call over a national road network took 292-572 s on the GUI thread with no
way to stop it. agent.run() only checked should_stop between tool calls. See cancel_signal.py and
tools/_background_processing.py. The real thread/event-loop behaviour is in
tests/test_network_background_live.py (real QGIS); these pin the logic that needs no QGIS."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent import agent_orchestrator as agent_mod
from cartogen_ai.core.agent import cancel_signal
from cartogen_ai.core.agent.tools import _background_processing as bg
from cartogen_ai.core.agent.tools import logistics_tools as lt
from tests.test_logistics_tools import _LineNetworkMixin, _stop_layer

_LT = "cartogen_ai.core.agent.tools.logistics_tools."


class TestCancelSignal(unittest.TestCase):
    def tearDown(self):
        cancel_signal.end()

    def test_not_cancelled_unless_a_request_registered_a_stop_check(self):
        self.assertFalse(cancel_signal.is_cancelled())
        cancel_signal.begin(should_stop=lambda: True)
        self.assertTrue(cancel_signal.is_cancelled())
        cancel_signal.end()
        self.assertFalse(cancel_signal.is_cancelled())

    def test_a_broken_callback_never_breaks_a_tool(self):
        def boom(*a):
            raise RuntimeError("callback bug")
        cancel_signal.begin(should_stop=boom, status=boom)
        self.assertFalse(cancel_signal.is_cancelled())
        cancel_signal.report("still fine")          # must not raise

    def test_report_reaches_the_status_callback(self):
        seen = []
        cancel_signal.begin(status=seen.append)
        cancel_signal.report("Service area: working... 3s")
        self.assertEqual(seen, ["Service area: working... 3s"])
        cancel_signal.end()
        cancel_signal.report("nobody is listening")   # no callback: silently nothing
        self.assertEqual(len(seen), 1)

    def test_a_request_started_inside_another_restores_the_outer_one(self):
        outer = cancel_signal.begin(should_stop=lambda: False)
        inner = cancel_signal.begin(should_stop=lambda: True)
        self.assertTrue(cancel_signal.is_cancelled())
        cancel_signal.end(inner)
        self.assertFalse(cancel_signal.is_cancelled())      # the outer request's check is back
        cancel_signal.end(outer)
        self.assertFalse(cancel_signal.is_cancelled())


class TestRunPublishesAndClearsTheStopCheck(unittest.TestCase):
    def _agent(self, impl):
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent.client = SimpleNamespace(_emit_status=lambda text: self.statuses.append(text))
        agent._run_impl = impl
        return agent

    def setUp(self):
        self.statuses = []
        self.addCleanup(cancel_signal.end)

    def test_a_tool_running_inside_run_can_see_stop_and_report_progress(self):
        seen = {}

        def impl(user_query, map_context, should_stop, tool_step_callback):
            seen["cancelled_before"] = cancel_signal.is_cancelled()
            flag["stop"] = True
            seen["cancelled_after"] = cancel_signal.is_cancelled()
            cancel_signal.report("Service area: working... 3s")
            return "answer"
        flag = {"stop": False}
        out = self._agent(impl).run("q", should_stop=lambda: flag["stop"])
        self.assertEqual(out, "answer")
        self.assertEqual(seen, {"cancelled_before": False, "cancelled_after": True})
        self.assertEqual(self.statuses, ["Service area: working... 3s"])

    def test_the_registration_is_cleared_when_run_finishes_and_when_it_raises(self):
        self._agent(lambda *a: "done").run("q", should_stop=lambda: True)
        self.assertFalse(cancel_signal.is_cancelled())

        def failing(*a):
            raise ValueError("boom")
        with self.assertRaises(ValueError):
            self._agent(failing).run("q", should_stop=lambda: True)
        self.assertFalse(cancel_signal.is_cancelled())

    def test_run_passes_its_arguments_through_unchanged(self):
        got = {}

        def impl(user_query, map_context, should_stop, tool_step_callback):
            got.update(q=user_query, ctx=map_context, stop=should_stop, cb=tool_step_callback)
        stop, cb = (lambda: False), (lambda *a: None)
        self._agent(impl).run("hello", map_context={"x": 1}, should_stop=stop, tool_step_callback=cb)
        self.assertEqual(got, {"q": "hello", "ctx": {"x": 1}, "stop": stop, "cb": cb})


class TestRunNetworkAlgorithmChoosesTheThread(unittest.TestCase):
    def _call(self, network):
        with patch.object(lt._bg, "run_algorithm", return_value={"OUTPUT": "x"}) as run:
            out = lt._run_network_algorithm("native:serviceareafrompoint", {"p": 1}, "ctx", network, "Service area")
        return out, run

    def test_small_networks_stay_synchronous_and_big_ones_go_to_the_worker(self):
        for count, expected in ((10, False), (lt.BACKGROUND_MIN_FEATURES - 1, False),
                                (lt.BACKGROUND_MIN_FEATURES, True), (161041, True)):
            network = MagicMock()
            network.featureCount.return_value = count
            _, run = self._call(network)
            self.assertEqual(run.call_args.kwargs["use_background"], expected, count)
            self.assertEqual(run.call_args.kwargs["label"], "Service area")

    def test_an_unknown_size_is_treated_as_big(self):
        network = MagicMock()
        network.featureCount.side_effect = RuntimeError("provider gone")
        _, run = self._call(network)
        self.assertTrue(run.call_args.kwargs["use_background"])

    def test_the_synchronous_fallback_is_plain_processing_run_with_the_context(self):
        network = MagicMock()
        network.featureCount.return_value = 5
        with patch(_LT + "processing", create=True) as processing:
            processing.run.return_value = {"OUTPUT": "layer"}
            out = lt._run_network_algorithm("native:shortestpathpointtolayer", {"a": 1}, "the-context", network, "x")
        self.assertEqual(out, {"OUTPUT": "layer"})
        processing.run.assert_called_once_with("native:shortestpathpointtolayer", {"a": 1}, context="the-context")

    def test_outside_qgis_the_runner_is_exactly_processing_run(self):
        calls = []

        def fallback(alg, params, context=None):
            calls.append((alg, params, context))
            return {"ok": True}
        self.assertFalse(bg.can_run_in_background())
        self.assertEqual(bg.run_algorithm("native:x", {"p": 1}, "ctx", fallback), {"ok": True})
        self.assertEqual(calls, [("native:x", {"p": 1}, "ctx")])


def _cancel(*a, **k):
    raise bg.AnalysisCancelled("Stopped by the user.")


@patch(_LT + "QGIS_AVAILABLE", True)
@patch(_LT + "QgsProject", create=True)
@patch(_LT + "processing", create=True)
@patch(_LT + "Qgis", create=True)
@patch(_LT + "_find_layer_by_name")
class TestToolsLetStopThrough(_LineNetworkMixin, unittest.TestCase):
    """A Stop must end the request. The tools' generic `except Exception` (one facility failing must
    not abort the batch; one unreachable pair becomes infinity) would otherwise record it as an
    ordinary failure and carry on with the next facility, pair or origin."""

    def test_service_area_stops_and_does_not_report_a_skipped_facility(self, mock_find, mock_qgis, mock_proc, mock_project):
        mock_find.side_effect = lambda n: {"facilities": _stop_layer(["A", "B"]), "roads": MagicMock()}.get(n)
        with patch(_LT + "_run_network_algorithm", side_effect=_cancel) as run:
            res = lt.calculate_service_area("facilities", "roads", 1000)
        self.assertTrue(res.get("cancelled"), res)
        self.assertIn("Stopped", res["error"])
        self.assertNotIn("skipped", res)
        self.assertEqual(run.call_count, 1)                       # did not go on to facility B
        mock_project.instance.return_value.addMapLayer.assert_not_called()

    def test_travel_time_matrix_stops_instead_of_moving_to_the_next_origin(self, mock_find, mock_qgis, mock_proc, mock_project):
        mock_find.side_effect = lambda n: {"origins": _stop_layer(["A", "B"]), "dests": MagicMock(),
                                           "roads": MagicMock()}.get(n)
        with patch(_LT + "_run_network_algorithm", side_effect=_cancel) as run:
            res = lt.travel_time_matrix("origins", "dests", "roads")
        self.assertTrue(res.get("cancelled"), res)
        self.assertEqual(run.call_count, 1)

    def test_delivery_route_stops_during_the_distance_matrix(self, mock_find, mock_qgis, mock_proc, mock_project):
        mock_find.side_effect = lambda n: {"stops": _stop_layer(["a", "b", "c"]), "roads": MagicMock()}.get(n)
        with patch(_LT + "_run_network_algorithm", side_effect=_cancel) as run:
            res = lt.optimize_delivery_route("stops", road_network_layer="roads")
        self.assertTrue(res.get("cancelled"), res)
        self.assertEqual(run.call_count, 1)                       # not 6 pairs, each recorded as "unreachable"

    def test_matrix_and_route_helpers_propagate_a_stop_but_still_absorb_ordinary_failures(self, *mocks):
        geoms = [f.geometry() for f in _stop_layer(["a", "b", "c"]).getFeatures.return_value]
        network = MagicMock()
        with patch(_LT + "_run_network_algorithm", side_effect=_cancel):
            with self.assertRaises(bg.AnalysisCancelled):
                lt._build_network_distance_matrix(network, geoms)
            with self.assertRaises(bg.AnalysisCancelled):
                lt._build_road_snapped_route("stops", network, geoms, [0, 1, 2])
        # control: an ordinary per-pair failure is still infinity / a skipped leg, as before
        with patch(_LT + "_run_network_algorithm", side_effect=RuntimeError("no path")):
            matrix = lt._build_network_distance_matrix(network, geoms)
            self.assertEqual(matrix[0][1], float("inf"))
            self.assertIsNone(lt._build_road_snapped_route("stops", network, geoms, [0, 1, 2]))

    def test_an_ordinary_failure_is_still_a_skipped_facility_not_a_stop(self, mock_find, mock_qgis, mock_proc, mock_project):
        mock_find.side_effect = lambda n: {"facilities": _stop_layer(["A"]), "roads": MagicMock()}.get(n)
        with patch(_LT + "_run_network_algorithm", side_effect=RuntimeError("degenerate network")):
            res = lt.calculate_service_area("facilities", "roads", 1000)
        self.assertNotIn("cancelled", res)
        self.assertIn("error", res)                               # nothing built for the only facility


if __name__ == "__main__":
    unittest.main()
