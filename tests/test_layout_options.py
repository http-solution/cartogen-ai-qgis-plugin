import unittest

from cartogen_ai.core.agent.tools import layout_options as lo


class TestGeometry(unittest.TestCase):
    def test_new_items_need_all_four(self):
        self.assertIn("width_mm is required", lo.validate_geometry(10, 10, None, 20, need_all=True)[1])
        out, err = lo.validate_geometry(10, "20", 50, 30.5, need_all=True)
        self.assertIsNone(err)
        self.assertEqual(out, {"x_mm": 10.0, "y_mm": 20.0, "width_mm": 50.0, "height_mm": 30.5})

    def test_partial_for_edits_and_limits(self):
        self.assertEqual(lo.validate_geometry(x_mm=5)[0], {"x_mm": 5.0})
        self.assertIn("at least 1.0", lo.validate_geometry(width_mm=0)[1])
        self.assertIn("at most", lo.validate_geometry(width_mm=99999)[1])
        self.assertIn("must be a number", lo.validate_geometry(x_mm="left")[1])


class TestItems(unittest.TestCase):
    def test_refused_kinds_say_why(self):
        self.assertIn("web content", lo.validate_new_item("html")[1])
        self.assertIn("not offered yet", lo.validate_new_item("chart")[1])
        self.assertIn("Choose one of", lo.validate_new_item("hologram")[1])

    def test_label(self):
        self.assertEqual(lo.validate_new_item("label", text="Hi", font_size=12)[0], {"kind": "label", "text": "Hi", "font_size": 12.0})
        self.assertIn("needs text", lo.validate_new_item("label", text="  ")[1])
        self.assertIn("font_size", lo.validate_new_item("label", text="x", font_size=999)[1])

    def test_picture_is_local_only(self):
        self.assertIn("local files", lo.validate_new_item("picture", picture_path="https://x.org/a.png")[1])
        self.assertIn("local files", lo.validate_new_item("picture", picture_path="file:///etc/a.png")[1])
        self.assertIn("Pictures can be", lo.validate_new_item("picture", picture_path="/tmp/a.exe")[1])
        self.assertIn("needs picture_path", lo.validate_new_item("picture")[1])
        self.assertEqual(lo.validate_new_item("picture", picture_path="C:/maps/logo.PNG")[0]["picture_path"], "C:/maps/logo.PNG")

    def test_shape_arrow_table(self):
        self.assertEqual(lo.validate_new_item("shape")[0]["shape"], "rectangle")
        self.assertIn("shape must be", lo.validate_new_item("shape", shape="star")[1])
        ok = lo.validate_new_item("arrow", from_x_mm=10, from_y_mm=10, to_x_mm=50, to_y_mm=30)[0]
        self.assertEqual(ok["to_x_mm"], 50.0)
        self.assertIn("needs from_x_mm", lo.validate_new_item("arrow", from_x_mm=1)[1])
        self.assertIn("must differ", lo.validate_new_item("arrow", from_x_mm=1, from_y_mm=1, to_x_mm=1, to_y_mm=1)[1])
        self.assertEqual(lo.validate_new_item("table", layer_name="roads", fields=["name"])[0]["max_rows"], 10)
        self.assertIn("at most", lo.validate_new_item("table", layer_name="roads", max_rows=5000)[1])
        self.assertIn("non-empty list", lo.validate_new_item("table", layer_name="r", fields=[])[1])
        self.assertIn("needs layer_name", lo.validate_new_item("table")[1])

    def test_item_ids(self):
        self.assertTrue(lo.valid_item_id("MAP_2"))
        self.assertFalse(lo.valid_item_id(""))
        self.assertFalse(lo.valid_item_id("a<b"))


class TestPagesAndPaths(unittest.TestCase):
    def test_page_sizes(self):
        self.assertEqual(lo.page_size_mm("A4", "landscape")[0], (297, 210))
        self.assertEqual(lo.page_size_mm("a3", "portrait")[0], (297, 420))
        self.assertEqual(lo.page_size_mm("Letter", "Portrait")[0], (215.9, 279.4))
        self.assertIn("not a known page size", lo.page_size_mm("A9")[1])
        self.assertIn("orientation", lo.page_size_mm("A4", "tilted")[1])

    def test_export_and_template_paths(self):
        self.assertEqual(lo.validate_export_path("/x/map.SVG")[0], "svg")
        self.assertEqual(lo.validate_export_path("map.png")[0], "image")
        self.assertIn("Unsupported", lo.validate_export_path("map.docx")[1])
        self.assertIsNone(lo.validate_template_path("a.qpt", must_exist=False))
        self.assertIn(".qpt", lo.validate_template_path("a.txt", must_exist=False))
        self.assertIn("local files", lo.validate_template_path("http://x/a.qpt", must_exist=False))
        self.assertIn("not found", lo.validate_template_path("/nope/a.qpt", must_exist=True))


class TestMapOptions(unittest.TestCase):
    def test_valid_and_invalid(self):
        out, err = lo.validate_map_options(scale="250000", bbox=[35, 31, 36, 32], lock_layers=True)
        self.assertIsNone(err)
        self.assertEqual(out["scale"], 250000.0)
        self.assertEqual(out["bbox"], [35.0, 31.0, 36.0, 32.0])
        self.assertIn("Nothing to change", lo.validate_map_options()[1])
        self.assertIn("not both", lo.validate_map_options(bbox=[1, 1, 2, 2], extent_layer="x")[1])
        self.assertIn("min below max", lo.validate_map_options(bbox=[5, 1, 2, 2])[1])
        self.assertIn("denominator", lo.validate_map_options(scale=0)[1])
        self.assertIn("true or false", lo.validate_map_options(lock_layers="yes")[1])


if __name__ == "__main__":
    unittest.main()
