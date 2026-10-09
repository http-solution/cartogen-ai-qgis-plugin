# -*- coding: utf-8 -*-
"""Runs each pre-built chain end to end in real QGIS with its slots filled, calling the real tool functions through the same
reference resolution run_steps uses. fetch_dem reads synthetic tiles from a local range-capable server (the real bucket is not used in
CI). Proves tool order, argument names and result fields; says nothing about whether a model follows the skeleton."""
import copy
import functools
import http.server
import os
import tempfile
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import numpy  # noqa: F401
    from osgeo import gdal  # noqa: F401
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def fill(value, slots):
    if isinstance(value, str) and value.startswith("<") and value.endswith(">"):
        return slots[value[1:-1]]
    if isinstance(value, dict):
        return {k: fill(v, slots) for k, v in value.items()}
    return value


@unittest.skipUnless(LIVE, "requires real QGIS + gdal + numpy")
class TestChainsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        try:
            from processing.core.Processing import Processing
            Processing.initialize()
        except Exception:
            pass
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        import cartogen_ai.core.agent.tools  # noqa: F401  (registers every tool)
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        self.tools = TOOL_REGISTRY

    def run_chain(self, chain_id, slots):
        from cartogen_ai.core.agent import chains, step_runner
        chain = next(c for c in chains.CHAINS if c["id"] == chain_id)
        self.assertEqual(set(slots), set(chain["slots"]))
        results = []
        for step in copy.deepcopy(chain["steps"]):
            args, err = step_runner.resolve_arguments(fill(step["arguments"], slots), results)
            self.assertIsNone(err, err)
            result = self.tools[step["tool"]](**args)
            self.assertNotIn("error", result, (step["tool"], result))
            results.append(result)
        return results

    def _vector(self, geom, name, crs="EPSG:4326"):
        kind = {"Point": "Point", "LineString": "LineString", "Polygon": "Polygon"}[geom.split("(")[0].strip()]
        layer = QgsVectorLayer(f"{kind}?crs={crs}&field=id:integer", name, "memory")
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(geom))
        f.setAttributes([1])
        layer.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_exclusion_zone_split(self):
        self._vector("Point(44.5 15.5)", "chk")
        self._vector("LineString(44.3 15.5,44.7 15.5)", "hwy")
        results = self.run_chain("exclusion_zone_split", {"points": "chk", "utm": "EPSG:32638", "metres": 5000, "zones": "chk_zones",
                                                          "line": "hwy"})
        self.assertEqual(results[1]["layer_name"], "chk_zones")
        self.assertNotIn("warning", results[1])            # buffered in metres, not degrees
        out = results[2]
        self.assertTrue(out.get("success"), out)
        text = str(out)
        self.assertIn("compromised", text)

    def test_buffer_then_clip(self):
        self._vector("Point(44.5 15.5)", "src")
        self._vector("LineString(44.3 15.5,44.7 15.5)", "tgt")
        results = self.run_chain("buffer_then_clip", {"source": "src", "utm": "EPSG:32638", "metres": 5000, "target": "tgt"})
        self.assertNotIn("warning", results[1])
        self.assertGreater(results[2]["feature_count"], 0)

    def _dem_server(self):
        from tests.test_dem_tools_live import _RangeHandler, _tile
        root = tempfile.mkdtemp(prefix="chain_tiles_")
        _tile(root, 15, 45)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_RangeHandler, directory=root))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        from cartogen_ai.core.agent.tools import dem_tools
        old = dem_tools.TILE_BASE
        dem_tools.TILE_BASE = "http://127.0.0.1:%d" % server.server_address[1]
        self.addCleanup(lambda: setattr(dem_tools, "TILE_BASE", old))
        self._vector("Polygon((45.2 15.2,45.6 15.2,45.6 15.6,45.2 15.6,45.2 15.2))", "aoi")

    def test_terrain_contours(self):
        self._dem_server()
        results = self.run_chain("terrain_contours", {"aoi": "aoi", "interval": 20})
        self.assertGreater(results[1]["contour_count"], 0)

    def test_terrain_slope(self):
        self._dem_server()
        results = self.run_chain("terrain_slope", {"aoi": "aoi"})
        self.assertTrue(results[1].get("success"), results[1])


if __name__ == "__main__":
    unittest.main()
