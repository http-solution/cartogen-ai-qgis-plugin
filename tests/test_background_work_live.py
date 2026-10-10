# -*- coding: utf-8 -*-
"""Live-QGIS tests for audit A14: zonal_statistics runs through the background runner and still writes the zs_ fields, and
run_callable keeps the GUI loop alive, returns results, re-raises errors and honours Stop. Written without hand-testing; the
Docker QGIS run is the only execution evidence."""
import os
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import numpy
    from osgeo import gdal, osr
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()
    try:
        from processing.core.Processing import Processing
        Processing.initialize()
    except Exception:
        pass


@unittest.skipUnless(LIVE, "requires real QGIS + gdal + numpy")
class TestBackgroundWork(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _raster(self):
        path = os.path.join(tempfile.mkdtemp(prefix="cartogen_zs_"), "r.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 10, 10, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((0.0, 1.0, 0, 10.0, 0, -1.0))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        data = numpy.zeros((10, 10), dtype="float32")
        data[:, 5:] = 10.0                        # left half 0, right half 10
        ds.GetRasterBand(1).WriteArray(data)
        ds.FlushCache()
        ds = None
        layer = QgsRasterLayer(path, "r")
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)

    def _zones(self, count):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string", "zones", "memory")
        feats = []
        for i in range(count):
            f = QgsFeature(layer.fields())
            x0 = 0 if i % 2 == 0 else 5
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x0} 0,{x0 + 5} 0,{x0 + 5} 10,{x0} 10,{x0} 0))"))
            f.setAttributes([f"z{i}"])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _check(self, count):
        from cartogen_ai.core.agent.tools.raster_tools import zonal_statistics
        self._raster()
        zones = self._zones(count)
        res = zonal_statistics("r", "zones")
        self.assertTrue(res.get("success"), res)
        self.assertGreaterEqual(zones.fields().indexOf("zs_mean"), 0)
        self.assertGreaterEqual(zones.fields().indexOf("zs_median"), 0)
        self.assertGreaterEqual(zones.fields().indexOf("zs_stdev"), 0)
        means = sorted({round(f["zs_mean"], 3) for f in zones.getFeatures()})
        self.assertEqual(means, [0.0, 10.0])
        by_name = {f["name"]: f["zs_mean"] for f in zones.getFeatures()}
        self.assertAlmostEqual(by_name["z0"], 0.0, places=3)      # polygon order is preserved through the copy
        self.assertAlmostEqual(by_name["z1"], 10.0, places=3)

    def test_zonal_statistics_small_layer_synchronous_path(self):
        self._check(4)

    def test_zonal_statistics_large_layer_background_path(self):
        self._check(250)

    def test_generic_raster_operation_goes_through_the_background_runner(self):
        """#221: _run_raster_and_add used to call processing.run on the GUI thread; it now uses the task runner."""
        from unittest import mock
        from cartogen_ai.core.agent.tools import _background_processing as bg
        from cartogen_ai.core.agent.tools import raster_tools
        self._raster()
        src = QgsProject.instance().mapLayersByName("r")[0].source()
        real = bg.run_algorithm
        with mock.patch.object(bg, "run_algorithm", wraps=real) as spy:
            res = raster_tools._run_raster_and_add("gdal:slope", {"INPUT": src, "BAND": 1, "SCALE": 1, "AS_PERCENT": False,
                                                                   "COMPUTE_EDGES": False, "ZEVENBERGEN": False}, "slope_bg")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(spy.call_count, 1)
        self.assertTrue(QgsProject.instance().mapLayersByName("slope_bg"))

    def test_allowlisted_algorithm_goes_through_the_background_runner_and_returns_a_layer(self):
        from unittest import mock
        from cartogen_ai.core.agent.tools import _background_processing as bg
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        zones = self._zones(4)
        real = bg.run_algorithm
        with mock.patch.object(bg, "run_algorithm", wraps=real) as spy:
            res = run_allowlisted_processing_algorithm(
                "native:buffer", {"INPUT": zones.name(), "DISTANCE": 0.5, "SEGMENTS": 5, "END_CAP_STYLE": 0, "JOIN_STYLE": 0,
                                  "MITER_LIMIT": 2, "DISSOLVE": False}, "buffered_bg")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(spy.call_count, 1)

    def test_a_selection_algorithm_stays_synchronous(self):
        from unittest import mock
        from cartogen_ai.core.agent.tools import _background_processing as bg
        from cartogen_ai.core.agent.tools import processing_allowlist_tools as pat
        from cartogen_ai.core.agent.tools._processing_allowlist import MUTATES_INPUT_ALGORITHM_IDS
        alg = sorted(MUTATES_INPUT_ALGORITHM_IDS)[0]
        with mock.patch.object(bg, "run_algorithm") as spy, mock.patch.object(pat.processing, "run", return_value={}) as plain:
            pat._run_allowlisted(alg, {})
        spy.assert_not_called()
        plain.assert_called_once()

    def test_run_callable_returns_the_result_and_keeps_the_event_loop_alive(self):
        from qgis.PyQt.QtCore import QTimer
        from cartogen_ai.core.agent.tools import _background_processing as bg
        ticks = []
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        self.addCleanup(timer.stop)
        self.assertEqual(bg.run_callable(lambda: (time.sleep(0.6), 42)[1], label="t"), 42)
        self.assertGreater(len(ticks), 5)           # the GUI thread kept processing events while the worker slept

    def test_run_callable_reraises_the_workers_exception(self):
        from cartogen_ai.core.agent.tools import _background_processing as bg

        def boom():
            raise ValueError("bad input")
        with self.assertRaisesRegex(ValueError, "bad input"):
            bg.run_callable(boom, label="t")

    def test_run_callable_stops_on_cancel(self):
        from cartogen_ai.core.agent import cancel_signal
        from cartogen_ai.core.agent.tools import _background_processing as bg
        token = cancel_signal.begin(should_stop=lambda: True)
        try:
            with self.assertRaises(bg.AnalysisCancelled):
                bg.run_callable(lambda: time.sleep(3), label="t")
        finally:
            cancel_signal.end(token)


if __name__ == "__main__":
    unittest.main()
