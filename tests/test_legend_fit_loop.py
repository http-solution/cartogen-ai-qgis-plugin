"""The legend fit loop of layout_style._fit_legend, offline with a fake legend whose measured height follows a simple model (self-audit 2026-11-06, DEF-27):
height = layers x 100 mm x scale / columns, width = columns x 30 mm. Frame 100 x 50 mm."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools import layout_style as ls


class _Node:
    def __init__(self, layer_id):
        self._id = layer_id

    def layerId(self):
        return self._id


class _Root:
    def __init__(self, count):
        self.nodes = [_Node(f"l{i}") for i in range(count)]

    def findLayers(self):
        return list(self.nodes)

    def removeChildNode(self, node):
        self.nodes.remove(node)


class _Model:
    def __init__(self, root):
        self._root = root

    def rootGroup(self):
        return self._root


class _Rect:
    def __init__(self, w, h):
        self._w, self._h = w, h

    def width(self):
        return self._w

    def height(self):
        return self._h


class FakeLegend:
    def __init__(self, layers, frame=(100.0, 50.0)):
        self.root, self.frame = _Root(layers), frame
        self.columns, self.symbol, self.title, self.split, self.resized = 1, 4.0, "Legend", False, None

    def rect(self):
        return _Rect(*self.frame)

    def symbolHeight(self):
        return self.symbol

    def setSymbolHeight(self, value):
        self.symbol = value

    def setColumnCount(self, value):
        self.columns = value

    def setSplitLayer(self, value):
        self.split = value

    def model(self):
        return _Model(self.root)

    def setTitle(self, value):
        self.title = value

    def attemptResize(self, size):
        self.resized = size


class FakeLayout:
    def __init__(self, leg):
        self.leg = leg

    def itemById(self, item_id):
        return self.leg if item_id == "LEGEND" else None


def fake_measure(leg, _layout):
    return leg.columns * 30.0, len(leg.root.nodes) * 100.0 * (leg.symbol / 4.0) / leg.columns


def run(leg, measure=fake_measure):
    report, chosen = {}, {"ids": [n.layerId() for n in leg.root.nodes]}
    with patch.object(ls, "measure_legend_size", measure), patch.object(ls, "_style_legend_fonts", lambda *_a, **_k: None), \
            patch.object(ls, "QgsLayoutSize", lambda *a: a, create=True):
        warnings = ls._fit_legend(FakeLayout(leg), "mm", chosen, report)
    return report, warnings, chosen


class TestTheFitLoop(unittest.TestCase):
    def test_one_tall_layer_is_split_into_columns_not_dropped(self):
        leg = FakeLegend(1)
        report, warnings, _chosen = run(leg)
        self.assertEqual((report["columns"], report["dropped"], report["fits"], report["measured"]), (2, 0, True, True))
        self.assertEqual((leg.columns, leg.split, leg.title, warnings), (2, True, "Legend", []))

    def test_a_short_legend_stays_in_one_column_at_full_size(self):
        leg = FakeLegend(1, frame=(100.0, 120.0))
        report, _w, _c = run(leg)
        self.assertEqual((report["columns"], report["scale"], report["dropped"], leg.split), (1, 1.0, 0, False))

    def test_many_layers_drop_the_last_ones_and_the_title_says_how_many(self):
        leg = FakeLegend(7)
        report, warnings, chosen = run(leg)
        self.assertEqual((report["columns"], report["dropped"], report["fits"]), (3, 5, True))     # 4 columns would be 120 mm wide in a 100 mm frame
        self.assertEqual(len(leg.root.nodes), 2)
        self.assertEqual(chosen["ids"], ["l0", "l1"])
        self.assertIn("5 more layers", leg.title)
        self.assertTrue(warnings)

    def test_an_answer_equal_to_the_frame_is_not_reported_as_fitting(self):
        leg = FakeLegend(1)
        report, _w, _c = run(leg, measure=lambda _leg, _layout: (30.0, 50.0))
        self.assertFalse(report["measured"])
        self.assertFalse(report["fits"])


class TestWhenToDropAnotherLayer(unittest.TestCase):
    def test_an_unmeasurable_arrangement_does_not_fit(self):
        self.assertTrue(ls.legend_needs_dropping(None, 50.0))

    def test_taller_than_the_frame_drops_and_within_the_slack_does_not(self):
        self.assertTrue(ls.legend_needs_dropping(51.0, 50.0))
        self.assertFalse(ls.legend_needs_dropping(50.4, 50.0))


if __name__ == "__main__":
    unittest.main()
