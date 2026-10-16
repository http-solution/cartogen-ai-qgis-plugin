import unittest

from cartogen_ai.core.agent.tools import symbology_options as so


class TestKeys(unittest.TestCase):
    def test_everyday_words_reach_their_key(self):
        self.assertEqual(so.line_style_key("Dashed"), "dashed")
        self.assertEqual(so.line_style_key("dash-dot"), "dash_dot")
        self.assertEqual(so.line_style_key("no outline"), "none")
        self.assertEqual(so.fill_style_key("hatched"), "hatch_forward")
        self.assertEqual(so.fill_style_key("cross hatch"), "diagonal_cross")
        self.assertEqual(so.fill_style_key("no fill"), "none")
        self.assertEqual(so.marker_shape_key("Star"), "star")
        self.assertEqual(so.marker_shape_key("round"), "circle")
        self.assertEqual(so.placement_key("centered"), "over_point")
        self.assertEqual(so.placement_key("follow line"), "curved")

    def test_unknown_words_return_none(self):
        for fn in (so.line_style_key, so.fill_style_key, so.marker_shape_key, so.placement_key):
            self.assertIsNone(fn("zigzag-wibble"))
            self.assertIsNone(fn(None))

    def test_every_alias_points_at_a_real_key(self):
        for aliases, table in ((so._LINE_ALIASES, so.LINE_STYLES), (so._FILL_ALIASES, so.FILL_STYLES),
                               (so._SHAPE_ALIASES, so.MARKER_SHAPES), (so._PLACEMENT_ALIASES, so.LABEL_PLACEMENTS)):
            for alias, target in aliases.items():
                self.assertIn(target, table, alias)


class TestSymbolOptions(unittest.TestCase):
    def test_nothing_to_change_is_an_error(self):
        self.assertIn("Nothing to change", so.validate_symbol_options()[1])

    def test_normalises_and_omits_unset_keys(self):
        out, err = so.validate_symbol_options(outline_color="dark red", outline_width_mm="0.5", line_style="dashed", marker_shape="Star")
        self.assertIsNone(err)
        self.assertEqual(out, {"outline_color": "dark red", "outline_width_mm": 0.5, "line_style": "dashed", "marker_shape": "star"})

    def test_ranges_and_choices(self):
        self.assertIn("between 0 and 20", so.validate_symbol_options(outline_width_mm=50)[1])
        self.assertIn("between 0 and 100", so.validate_symbol_options(opacity_percent=120)[1])
        self.assertIn("must be a number", so.validate_symbol_options(marker_size_mm="big")[1])
        self.assertIn("Choose one of", so.validate_symbol_options(line_style="wavy")[1])
        self.assertIn("is empty", so.validate_symbol_options(fill_color="  ")[1])


class TestLabelOptions(unittest.TestCase):
    def test_valid_set(self):
        out, err = so.validate_label_options(font_size=12, bold=True, halo=False, placement="centered", visible_zoomed_out_to=250000,
                                             visible_zoomed_in_to=5000)
        self.assertIsNone(err)
        self.assertEqual(out["placement"], "over_point")
        self.assertEqual(out["visible_zoomed_out_to"], 250000.0)

    def test_scale_order_and_types(self):
        self.assertIn("must not be below", so.validate_label_options(visible_zoomed_out_to=1000, visible_zoomed_in_to=5000)[1])
        self.assertIn("true or false", so.validate_label_options(bold="yes")[1])
        self.assertIn("scale denominator", so.validate_label_options(visible_zoomed_out_to="far")[1])
        self.assertIn("Nothing to change", so.validate_label_options()[1])
        self.assertIn("between 1 and 120", so.validate_label_options(font_size=500)[1])


class TestRasterOptions(unittest.TestCase):
    def test_modes_and_nodata(self):
        out, err = so.validate_raster_options(mode="paletted", resampling="Bilinear", nodata_min=0)
        self.assertIsNone(err)
        self.assertEqual(out, {"mode": "unique_values", "resampling": "bilinear", "nodata_min": 0.0, "nodata_max": 0.0})

    def test_errors(self):
        self.assertIn("Nothing to change", so.validate_raster_options()[1])
        self.assertIn("mode must be", so.validate_raster_options(mode="rainbow")[1])
        self.assertIn("Choose one of", so.validate_raster_options(resampling="smooth")[1])
        self.assertIn("must not be above", so.validate_raster_options(nodata_min=5, nodata_max=1)[1])
        self.assertIn("not both", so.validate_raster_options(nodata_min=1, clear_nodata=True)[1])
        self.assertIn("between 0 and 100", so.validate_raster_options(opacity_percent=-1)[1])


if __name__ == "__main__":
    unittest.main()
