import unittest

from cartogen_ai.core.agent.tools.new_layer_options import point_cloud_provider, tiled_scene_source, vector_tile_uri, zoom_violation


class TestNewLayerOptions(unittest.TestCase):
    def test_point_cloud_provider_by_name(self):
        self.assertEqual(point_cloud_provider("/d/a.copc.laz"), ("copc", None))
        self.assertEqual(point_cloud_provider("/d/ept.json"), ("ept", None))
        self.assertEqual(point_cloud_provider("/d/a.LAS"), ("pdal", None))
        self.assertEqual(point_cloud_provider("/d/a.laz"), ("pdal", None))
        self.assertIsNone(point_cloud_provider("/d/a.tif")[0])

    def test_zoom_range(self):
        self.assertIsNone(zoom_violation(0, 14))
        self.assertTrue(zoom_violation(5, 2))
        self.assertTrue(zoom_violation(0, 99))
        self.assertTrue(zoom_violation("x", 3))

    def test_vector_tile_uri(self):
        uri, err = vector_tile_uri("https://tiles.example.org/{z}/{x}/{y}.pbf", 0, 12)
        self.assertIsNone(err)
        self.assertTrue(uri.startswith("type=xyz&url=https://tiles.example.org/{z}/{x}/{y}.pbf"))
        self.assertIn("zmax=12", uri)
        self.assertEqual(vector_tile_uri("/d/a.mbtiles")[0], "type=mbtiles&url=/d/a.mbtiles")
        self.assertEqual(vector_tile_uri("/d/a.vtpk")[0], "type=vtpk&url=/d/a.vtpk")

    def test_vector_tile_refusals(self):
        for bad in ("http://t.example.org/{z}/{x}/{y}", "https://t.example.org/tiles", "https://localhost/{z}/{x}/{y}",
                    "https://u:p@t.example.org/{z}/{x}/{y}", "/d/a.shp", ""):
            self.assertIsNone(vector_tile_uri(bad)[0], bad)

    def test_tiled_scene_source(self):
        self.assertEqual(tiled_scene_source("/d/tileset.json"), ("/d/tileset.json", None))
        self.assertIsNone(tiled_scene_source("https://x.example.org/t/tileset.json")[1])
        for bad in ("http://x.example.org/tileset.json", "https://x.example.org/model.glb", "/d/model.obj", "https://192.168.1.2/t.json"):
            self.assertIsNone(tiled_scene_source(bad)[0], bad)


if __name__ == "__main__":
    unittest.main()
