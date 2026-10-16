"""Live-QGIS tests for package H (new_layer_tools.py). Written without a QGIS install: CI's first run is their first execution.
The point cloud is a tiny LAS 1.2 file written byte by byte, so opening it is really exercised; the tile sources have no sample data
in CI, so those tests check the refusal paths and print what QGIS did with a minimal local source (NEWLAYER lines in the log)."""
import json
import os
import struct
import tempfile
import unittest

try:
    from qgis.core import QgsProject
    LIVE = True
except ImportError:
    LIVE = False


def write_las(path, points):
    """LAS 1.2, point format 0, scale 0.01, one record per (x, y, z)."""
    xs, ys, zs = zip(*points, strict=True)
    header = bytearray(227)
    header[0:4] = b"LASF"
    header[24], header[25] = 1, 2
    struct.pack_into("<H", header, 94, 227)
    struct.pack_into("<I", header, 96, 227)
    struct.pack_into("<I", header, 100, 0)
    header[104] = 0
    struct.pack_into("<H", header, 105, 20)
    struct.pack_into("<I", header, 107, len(points))
    struct.pack_into("<3d", header, 131, 0.01, 0.01, 0.01)
    struct.pack_into("<3d", header, 155, 0.0, 0.0, 0.0)
    struct.pack_into("<6d", header, 179, max(xs), min(xs), max(ys), min(ys), max(zs), min(zs))
    with open(path, "wb") as fh:
        fh.write(bytes(header))
        for x, y, z in points:
            fh.write(struct.pack("<iiiHBBbBH", round(x * 100), round(y * 100), round(z * 100), 100, 0, 1, 0, 0, 1))


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestNewLayerToolsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp()

    def test_point_cloud_las_opens(self):
        from cartogen_ai.core.agent.tools.new_layer_tools import add_point_cloud_layer
        path = os.path.join(self.tmp, "tiny.las")
        write_las(path, [(100.0 + i, 200.0 + i, 5.0 + i) for i in range(50)])
        res = add_point_cloud_layer(path)
        print("NEWLAYER point_cloud", res)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["layer_type"], "point_cloud")
        self.assertEqual(len(QgsProject.instance().mapLayers()), 1)

    def test_point_cloud_refusals(self):
        from cartogen_ai.core.agent.tools.new_layer_tools import add_point_cloud_layer
        self.assertIn("error", add_point_cloud_layer(os.path.join(self.tmp, "missing.las")))
        self.assertIn("error", add_point_cloud_layer(os.path.join(self.tmp, "a.tif")))
        self.assertEqual(len(QgsProject.instance().mapLayers()), 0)

    def test_vector_tile_refusals_and_xyz_source(self):
        from cartogen_ai.core.agent.tools.new_layer_tools import add_vector_tile_layer
        self.assertIn("error", add_vector_tile_layer("http://t.example.org/{z}/{x}/{y}.pbf"))
        self.assertIn("error", add_vector_tile_layer(os.path.join(self.tmp, "missing.mbtiles")))
        res = add_vector_tile_layer("https://tiles.example.org/{z}/{x}/{y}.pbf", "remote tiles")
        print("NEWLAYER vector_tile_xyz", res)
        # An XYZ vector tile layer is valid without the network (nothing is fetched until it draws); if this QGIS build says otherwise
        # the tool must fail cleanly, never raise.
        self.assertTrue(res.get("success") or "error" in res, res)

    def test_3d_tiles_refusals_and_minimal_tileset(self):
        from cartogen_ai.core.agent.tools.new_layer_tools import add_3d_tiles_layer
        self.assertIn("error", add_3d_tiles_layer("http://x.example.org/tileset.json"))
        self.assertIn("error", add_3d_tiles_layer(os.path.join(self.tmp, "missing.json")))
        path = os.path.join(self.tmp, "tileset.json")
        with open(path, "w") as fh:
            json.dump({"asset": {"version": "1.0"}, "geometricError": 100,
                       "root": {"boundingVolume": {"region": [0.0, 0.0, 0.001, 0.001, 0.0, 10.0]}, "geometricError": 10, "refine": "ADD"}}, fh)
        res = add_3d_tiles_layer(path)
        print("NEWLAYER tiled_scene", res)
        self.assertTrue(res.get("success") or "error" in res, res)


if __name__ == "__main__":
    unittest.main()
