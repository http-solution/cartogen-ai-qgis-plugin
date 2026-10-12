"""INVESTIGATION (2026-10-12), second step: the isolated probe (tests/test_gdal_thread_probe_live.py) could NOT reproduce the PR #249/#251 crash of gdal:slope
on a worker thread in 8 variants x 4 fresh processes. The earlier crash was inside the full live suite, so this runs the same call IN the suite's own
process, after hundreds of other live tests, with faulthandler on: a crash would kill the job and print the Python stack of the crashing thread.
Informational; remove when the finding is recorded."""
import faulthandler
import os
import sys
import tempfile
import unittest

try:
    from qgis.core import QgsApplication, QgsProcessingContext, QgsProject
    LIVE = True
except ImportError:
    LIVE = False

faulthandler.enable(all_threads=True)


def _processing_available():
    for cand in ("/usr/share/qgis/python/plugins",):
        if os.path.isdir(os.path.join(cand, "processing")) and cand not in sys.path:
            sys.path.append(cand)
    try:
        from processing.core.Processing import Processing
        Processing.initialize()
        return True
    except Exception as e:
        print("INPROCESS PROBE: processing unavailable:", e, flush=True)
        return False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestGdalSlopeInTheSuiteProcess(unittest.TestCase):
    def test_slope_through_the_background_runner_many_times(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        if not _processing_available():
            self.skipTest("processing module not importable")
        import numpy
        from osgeo import gdal, osr
        import processing
        from cartogen_ai.core.agent.tools import _background_processing as bg
        tmp = tempfile.mkdtemp(prefix="gdalinproc_")
        dem = os.path.join(tmp, "dem.tif")
        n = 400
        ds = gdal.GetDriverByName("GTiff").Create(dem, n, n, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((500000.0, 30.0, 0.0, 1700000.0, 0.0, -30.0))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32638)
        ds.SetProjection(srs.ExportToWkt())
        xs = numpy.linspace(0, 12, n)
        ds.GetRasterBand(1).WriteArray((numpy.sin(xs)[None, :] * 80 + numpy.cos(xs)[:, None] * 60 + 500).astype("float32"))
        ds.FlushCache()
        ds = None
        print("INPROCESS PROBE can_run_in_background:", bg.can_run_in_background(), flush=True)
        ok = 0
        for i in range(12):
            ctx = QgsProcessingContext()
            ctx.setProject(QgsProject.instance())
            params = {"INPUT": dem, "BAND": 1, "SCALE": 1.0, "AS_PERCENT": False, "COMPUTE_EDGES": False, "ZEVENBERG": False, "TRIG": False,
                      "OUTPUT": os.path.join(tmp, f"slope_{i}.tif")}
            res = bg.run_algorithm("gdal:slope", params, ctx, fallback=lambda a, p, context=None: processing.run(a, p, context=context))
            ok += os.path.exists(res["OUTPUT"])
            print(f"INPROCESS PROBE iteration {i} ok", flush=True)
        print(f"INPROCESS PROBE finished: {ok} of 12 outputs written, no crash", flush=True)
        self.assertEqual(ok, 12)


if __name__ == "__main__":
    unittest.main()
