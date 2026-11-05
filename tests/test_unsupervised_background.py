"""Master list AR-4 (audit A14): unsupervised_classification reads, clusters and writes a raster of up to 400 million cells, and until now did it on QGIS's GUI thread, so
QGIS showed "Not Responding" and Stop did nothing. The chunked k-means itself shipped on 2026-10-11 (#222); what was left is running it through
_background_processing.run_callable (a worker thread for work that touches no QGIS object, GUI kept alive, Stop honoured). Offline: the tool's wiring, with mocks.
That the window really stays responsive is only provable in a real QGIS window (a live run); CI cannot show it."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core import _background_processing as bg
from cartogen_ai.core.agent.tools import raster_numpy
from cartogen_ai.core.agent.tools import raster_tools as rt


def _raster(width, height, source="C:/data/image.tif"):
    ras = MagicMock()
    ras.width.return_value, ras.height.return_value = width, height
    ras.source.return_value = source
    return ras


def _run(ras, run_callable=None, classify=None):
    classify = classify or MagicMock(return_value=("C:/tmp/out.tif", {"bands_used": [1, 2]}, 1234))
    run_callable = run_callable or MagicMock(side_effect=lambda fn, **kw: fn())
    new_layer = MagicMock()
    new_layer.isValid.return_value = True
    with patch.object(rt, "QGIS_AVAILABLE", True), patch.object(rt, "_find_layer_by_name", return_value=ras), \
            patch.object(rt, "QgsRasterLayer", MagicMock(return_value=new_layer), create=True), patch.object(rt, "QgsProject", MagicMock(), create=True), \
            patch.object(raster_numpy, "classify_raster_file", classify), patch.object(bg, "run_callable", run_callable), \
            patch("cartogen_ai.core.agent.tools.humanitarian_style.style_classified_raster", return_value=True, create=True):
        return rt.unsupervised_classification("image", 4, seed=3), run_callable, classify


class TestBackgroundWiring(unittest.TestCase):
    def test_a_large_raster_goes_through_the_background_runner(self):
        res, run_callable, classify = _run(_raster(20000, 20000))
        self.assertTrue(res.get("success"), res)
        run_callable.assert_called_once()
        self.assertTrue(run_callable.call_args.kwargs["use_background"])
        self.assertIn("classification", run_callable.call_args.kwargs["label"].lower())
        classify.assert_called_once_with("C:/data/image.tif", 4, seed=3)

    def test_a_small_raster_is_not_given_a_worker_thread(self):
        _res, run_callable, _classify = _run(_raster(200, 200))
        self.assertFalse(run_callable.call_args.kwargs["use_background"])

    def test_stop_gives_a_plain_stopped_result_not_a_failure_trace(self):
        cancelled = MagicMock(side_effect=bg.AnalysisCancelledError("Stopped by the user."))
        res, _rc, _classify = _run(_raster(20000, 20000), run_callable=cancelled)
        self.assertTrue(res.get("cancelled"))
        self.assertIn("Stopped", res["error"])

    def test_the_worker_callable_touches_no_qgis_object(self):
        """run_callable is only for work that touches NO QGIS object: the callable must run on plain values (the source path), not the layer."""
        ras = _raster(20000, 20000)
        captured = {}

        def capture(fn, **kwargs):
            captured["fn"] = fn
            return ("C:/tmp/out.tif", {"bands_used": [1]}, 10)

        _run(ras, run_callable=MagicMock(side_effect=capture))
        for name in ("source", "width", "height", "extent", "crs"):
            getattr(ras, name).side_effect = AssertionError(f"the worker touched the layer ({name})")
        classify = MagicMock(return_value=("p", {}, 1))
        with patch.object(raster_numpy, "classify_raster_file", classify):
            captured["fn"]()
        classify.assert_called_once_with("C:/data/image.tif", 4, seed=3)

    def test_a_value_error_from_the_classifier_still_reads_as_before(self):
        classify = MagicMock(side_effect=ValueError("the raster has 500,000,000 cells, above the 400,000,000 limit; clip it first."))
        res, _rc, _c = _run(_raster(20000, 20000), classify=classify)
        self.assertIn("clip it first", res["error"])

    def test_the_tool_description_says_it_keeps_qgis_responsive(self):
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        desc = next(t["function"]["description"] for t in TOOLS_SCHEMA if t["function"]["name"] == "unsupervised_classification")
        self.assertIn("responsive", desc)


if __name__ == "__main__":
    unittest.main()
