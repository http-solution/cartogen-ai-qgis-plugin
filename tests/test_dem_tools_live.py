# -*- coding: utf-8 -*-
"""Live-QGIS check of fetch_dem against a local HTTP server that serves synthetic COG-named tiles, so the /vsicurl/ + BuildVRT +
windowed Translate path is really executed without depending on the internet. Whether the real AWS bucket answers is checked separately
(see docs/COST_AND_ROUTING_PLAN_2026-10-09.md). Written without hand-testing."""
import functools
import http.server
import os
import tempfile
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import numpy
    from osgeo import gdal, osr
    from qgis.core import QgsProject
    LIVE = True
except ImportError:
    LIVE = False


class _RangeHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler ignores Range, which GDAL's /vsicurl/ requires (like the real bucket, which supports it)."""

    def log_message(self, *a, **k):
        pass

    def do_GET(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().do_GET()
        start, _, end = rng.replace("bytes=", "").partition("-")
        size = os.path.getsize(path)
        start = int(start)
        end = min(int(end) if end else size - 1, size - 1)
        with open(path, "rb") as fh:
            fh.seek(start)
            body = fh.read(end - start + 1)
        self.send_response(206)
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()


def _tile(root, lat, lon):
    from cartogen_ai.core.agent.tools.dem_tools import tile_name
    name = tile_name(lat, lon)
    os.makedirs(os.path.join(root, name))
    n = 360                                               # coarse stand-in for the 3600-cell tile; the geometry rules are the same
    ds = gdal.GetDriverByName("GTiff").Create(os.path.join(root, name, name + ".tif"), n, n, 1, gdal.GDT_Float32)
    ds.SetGeoTransform([lon, 1.0 / n, 0, lat + 1, 0, -1.0 / n])
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    rows = numpy.arange(n, dtype="float32")[:, None] * numpy.ones((1, n), dtype="float32")
    ds.GetRasterBand(1).WriteArray(rows + 100.0 * (lat % 7))
    ds = None


@unittest.skipUnless(LIVE, "requires real QGIS + gdal + numpy")
class TestFetchDemLive(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.root = tempfile.mkdtemp(prefix="dem_tiles_")
        _tile(self.root, 15, 45)
        _tile(self.root, 15, 46)                          # 14/45 and 14/46 are deliberately absent, like open sea
        handler = functools.partial(_RangeHandler, directory=self.root)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        from cartogen_ai.core.agent.tools import dem_tools
        self.mod = dem_tools
        self.old_base = dem_tools.TILE_BASE
        dem_tools.TILE_BASE = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.addCleanup(lambda: setattr(dem_tools, "TILE_BASE", self.old_base))

    def test_window_across_two_tiles_with_a_missing_neighbour(self):
        r = self.mod.fetch_dem(west=45.5, south=14.5, east=46.5, north=15.5)
        self.assertTrue(r.get("success"), r)
        self.assertEqual(len(r["tiles_used"]), 2)
        self.assertEqual(len(r["tiles_absent"]), 2)
        self.assertIn("warning", r)
        layer = QgsProject.instance().mapLayersByName("DEM_Copernicus_GLO30")[0]
        self.assertTrue(layer.isValid())
        ext = layer.extent()
        self.assertAlmostEqual(ext.xMinimum(), 45.5, places=2)
        self.assertAlmostEqual(ext.xMaximum(), 46.5, places=2)
        self.assertIn("Copernicus", layer.customProperty("cartogen/source"))
        self.assertIn("DSM", r["model_type"])

    def test_all_absent_is_a_clear_error(self):
        r = self.mod.fetch_dem(west=10.2, south=10.2, east=10.8, north=10.8)
        self.assertIn("error", r)
        self.assertIn("No elevation tiles", r["error"])

    def test_centre_and_radius(self):
        r = self.mod.fetch_dem(lat=15.5, lon=45.5, radius_km=10)
        self.assertTrue(r.get("success"), r)


if __name__ == "__main__":
    unittest.main()
