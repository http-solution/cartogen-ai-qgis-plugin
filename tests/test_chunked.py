"""Cooperative chunking (tools/_chunked.py): slices, Stop, progress, and the work budget. No Qt involved: the clock, pump, cancel check and
report are injected."""
import unittest

from cartogen_ai.core.agent.tools import _chunked as ch
from cartogen_ai.core.agent.tools._background_processing import AnalysisCancelledError


class FakeClock:
    def __init__(self, step=0.001):
        self.t = 0.0
        self.step = step

    def __call__(self):
        self.t += self.step
        return self.t


def _y(**kw):
    log = {"pumps": 0, "reports": []}
    defaults = {"clock": FakeClock(0.001), "pump": lambda: log.__setitem__("pumps", log["pumps"] + 1), "cancelled": lambda: False,
                "report": log["reports"].append, "check_every": 1}
    defaults.update(kw)
    return ch.Yielder("Test", **defaults), log


class TestYielder(unittest.TestCase):
    def test_pumps_about_once_per_slice_not_once_per_item(self):
        y, log = _y(slice_s=0.05)                       # each clock read advances 1 ms, so a slice is ~50 reads
        for _ in range(1000):
            y.tick()
        self.assertTrue(15 <= log["pumps"] <= 25, log["pumps"])
        self.assertEqual(y.count, 1000)

    def test_stop_raises_the_error_every_tool_already_lets_through(self):
        state = {"stop": False}
        y, _log = _y(slice_s=0.01, cancelled=lambda: state["stop"])
        for _ in range(100):
            y.tick()
        state["stop"] = True
        with self.assertRaises(AnalysisCancelledError) as cm:
            for _ in range(1000):
                y.tick()
        self.assertIn("Test: stopped", str(cm.exception))

    def test_progress_is_reported_with_the_total_and_not_every_slice(self):
        y, log = _y(slice_s=0.01, report_s=0.5, total=5000)
        for _ in range(3000):
            y.tick()
        self.assertTrue(2 <= len(log["reports"]) <= 8, len(log["reports"]))
        self.assertIn("of 5,000", log["reports"][0])
        self.assertIn("press Stop", log["reports"][0])

    def test_the_clock_is_read_rarely_for_cheap_items(self):
        reads = []

        def clock():
            reads.append(1)
            return 0.0
        y = ch.Yielder("Test", clock=clock, pump=lambda: None, cancelled=lambda: False, report=lambda t: None, check_every=64)
        reads.clear()
        for _ in range(6400):
            y.tick()
        self.assertEqual(len(reads), 100)

    def test_no_pump_when_slice_has_not_elapsed(self):
        y, log = _y(slice_s=10.0)
        for _ in range(500):
            y.tick()
        self.assertEqual(log["pumps"], 0)


class TestChunkedAndFeatures(unittest.TestCase):
    def test_chunked_yields_every_item_in_order(self):
        self.assertEqual(list(ch.chunked(range(10), "x", clock=FakeClock(), pump=lambda: None, cancelled=lambda: False, report=lambda t: None)),
                         list(range(10)))

    def test_features_is_a_drop_in_for_getfeatures_and_passes_a_request(self):
        class Layer:
            def featureCount(self):
                return 3

            def getFeatures(self, request=None):
                return iter([("a", request), ("b", request), ("c", request)])
        kw = {"clock": FakeClock(), "pump": lambda: None, "cancelled": lambda: False, "report": lambda t: None}
        self.assertEqual([f[0] for f in ch.features(Layer(), "x", **kw)], ["a", "b", "c"])
        self.assertEqual([f[1] for f in ch.features(Layer(), "x", request="REQ", **kw)], ["REQ"] * 3)

    def test_a_layer_without_featurecount_still_iterates(self):
        class Odd:
            def getFeatures(self):
                return iter([1, 2])
        self.assertEqual(list(ch.features(Odd(), "x", clock=FakeClock(), pump=lambda: None, cancelled=lambda: False, report=lambda t: None)), [1, 2])


class TestBudget(unittest.TestCase):
    def test_under_the_limit_passes_and_over_it_says_what_to_do(self):
        ch.ensure_within(10, 10, "pairs")
        with self.assertRaisesRegex(ValueError, "pairs is 11, above the 10 this tool will attempt. Clip"):
            ch.ensure_within(11, 10, "pairs")


if __name__ == "__main__":
    unittest.main()
