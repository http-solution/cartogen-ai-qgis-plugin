"""Fixes found on 2026-10-16 by checking calls against the QGIS 4.2 API reference: zoom_history used canvas methods that do not exist."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools import project_ops_tools as p


class _Extent:
    def __init__(self, x0, y0, x1, y1):
        self._v = (x0, y0, x1, y1)

    def xMinimum(self): return self._v[0]
    def yMinimum(self): return self._v[1]
    def xMaximum(self): return self._v[2]
    def yMaximum(self): return self._v[3]


class TestExtentChanged(unittest.TestCase):
    def test_same_and_different(self):
        self.assertFalse(p.extent_changed(_Extent(0, 0, 1, 1), _Extent(0, 0, 1, 1)))
        self.assertTrue(p.extent_changed(_Extent(0, 0, 1, 1), _Extent(0, 0, 1, 2)))


class TestZoomHistory(unittest.TestCase):
    def _canvas(self, extents):
        canvas = MagicMock(spec=["extent", "zoomToPreviousExtent", "zoomToNextExtent", "refresh", "scale"])   # spec: a missing method raises
        canvas.extent.side_effect = list(extents)
        canvas.scale.return_value = 1234.56
        return canvas

    def _run(self, direction, canvas):
        iface = MagicMock()
        iface.mapCanvas.return_value = canvas
        with patch.object(p, "QGIS_AVAILABLE", True), patch.object(p, "iface", iface):
            return p.zoom_history(direction)

    def test_a_step_that_moved_the_extent_succeeds_without_the_nonexistent_methods(self):
        canvas = self._canvas([_Extent(0, 0, 1, 1), _Extent(0, 0, 2, 2)])
        res = self._run("previous", canvas)
        self.assertEqual(res["success"], True, res)
        canvas.zoomToPreviousExtent.assert_called_once()

    def test_an_unchanged_extent_means_there_was_nothing_to_go_back_to(self):
        canvas = self._canvas([_Extent(0, 0, 1, 1), _Extent(0, 0, 1, 1)])
        res = self._run("next", canvas)
        self.assertIn("no later", res["error"])
        canvas.zoomToNextExtent.assert_called_once()


if __name__ == "__main__":
    unittest.main()
