"""PLAN-023 R3-6: the agriculture and environment looks. Offline, no QGIS. Known answers are hand-computed or taken from the published legend; the renderer side (a tool applying a look to a real layer) is tested in tests/test_land_cover_look_live.py."""
import re
import unittest

from cartogen_ai.core.representation import colour_rules as cr
from cartogen_ai.core.representation import style_looks as sl
from cartogen_ai.core.representation import style_profiles as sp

# ESA WorldCover legend, class code -> (name, RGB) as published in the product's user manual
PUBLISHED_WORLDCOVER = {10: ("Tree cover", (0, 100, 0)), 20: ("Shrubland", (255, 187, 34)), 30: ("Grassland", (255, 255, 76)), 40: ("Cropland", (240, 150, 255)), 50: ("Built-up", (250, 0, 0)),
                        60: ("Bare / sparse vegetation", (180, 180, 180)), 70: ("Snow and ice", (240, 240, 240)), 80: ("Permanent water bodies", (0, 100, 200)), 90: ("Herbaceous wetland", (0, 150, 160)),
                        95: ("Mangroves", (0, 207, 117)), 100: ("Moss and lichen", (250, 230, 160))}


class TestWorldCover(unittest.TestCase):
    def test_the_eleven_classes_equal_the_published_legend(self):
        entries = sl.worldcover_entries()
        self.assertEqual(len(entries), 11)
        for entry in entries:
            name, rgb = PUBLISHED_WORLDCOVER[entry["code"]]
            self.assertEqual(entry["label"], name)
            self.assertEqual(cr.hex_to_rgb(entry["colour"]), rgb, name)

    def test_lookup_by_code_text_code_float_and_name_in_any_case(self):
        for value in (10, "10", 10.0, "Tree cover", "tree COVER", " 10 "):
            self.assertEqual(sl.worldcover_lookup(value)["code"], 10, repr(value))
        self.assertEqual(sl.worldcover_lookup(95)["label"], "Mangroves")

    def test_lookup_refuses_what_is_not_a_class(self):
        for value in (None, "", 11, 0, "forest", True, 10.5, "tree"):
            self.assertIsNone(sl.worldcover_lookup(value), repr(value))

    def test_the_legend_text_always_carries_the_name_and_the_code(self):
        labels = sl.legend_labels(sl.worldcover_entries())
        self.assertEqual(labels[0], "Tree cover (10)")
        self.assertEqual(labels[-1], "Moss and lichen (100)")
        self.assertEqual(len(set(labels)), 11)


class TestChangeClasses(unittest.TestCase):
    def test_loss_stable_gain_are_minus_one_zero_one_and_not_red_or_green(self):
        entries = sl.change_entries()
        self.assertEqual([(e["code"], e["label"]) for e in entries], [(-1, "loss"), (0, "stable"), (1, "gain")])
        self.assertEqual(cr.red_beside_green([e["colour"] for e in entries]), [])
        self.assertFalse(any(cr.is_red(e["colour"]) or cr.is_green(e["colour"]) for e in entries))

    def test_lookup_by_number_text_or_name(self):
        for value, label in ((-1, "loss"), ("-1", "loss"), ("Loss", "loss"), (0, "stable"), ("0", "stable"), (1, "gain"), ("GAIN", "gain")):
            self.assertEqual(sl.change_lookup(value)["label"], label, repr(value))
        for value in (2, "decrease", None, ""):
            self.assertIsNone(sl.change_lookup(value), repr(value))


class TestIndexClasses(unittest.TestCase):
    def test_known_breaks(self):
        self.assertEqual(sl.index_breaks("NDVI"), [0.2, 0.4, 0.6, 0.8])
        self.assertEqual(sl.index_breaks("ndwi"), [-0.6, -0.2, 0.2, 0.6])
        self.assertEqual(sl.index_breaks("NDVI", 3), [0.33, 0.67])

    def test_labels_are_ranges_only(self):
        self.assertEqual(sl.index_class_labels("NDVI"), ["below 0.2", "0.2 to 0.4", "0.4 to 0.6", "0.6 to 0.8", "0.8 and above"])
        self.assertEqual(sl.index_class_labels("NDWI")[0], "below -0.6")
        self.assertEqual(sl.index_class_labels("NDVI", [0.1, 0.5]), ["below 0.1", "0.1 to 0.5", "0.5 and above"])

    def test_no_label_claims_a_meaning(self):
        words = set(re.findall(r"[a-z]+", " ".join([*sl.index_class_labels("NDVI"), sl.index_look("NDVI")["title"]]).lower()))
        for banned in ("stress", "stressed", "healthy", "poor", "good", "low", "high", "yield", "bare", "dense"):
            self.assertNotIn(banned, words)

    def test_the_look_carries_the_index_name_and_its_units_and_one_colour_per_class(self):
        look = sl.index_look("ndvi")
        self.assertEqual(look["title"], "NDVI (index value, unitless)")
        self.assertEqual(len(look["classes"]), 5)
        self.assertEqual(len({c["colour"] for c in look["classes"]}), 5)
        self.assertEqual([c["colour"] for c in look["classes"]], sp.colours("Greens"))
        self.assertEqual(sl.index_look("NDWI")["classes"][0]["colour"], sp.colours("Blues")[0])

    def test_bad_input_is_refused(self):
        with self.assertRaises(ValueError):
            sl.index_breaks("EVI")
        with self.assertRaises(ValueError):
            sl.index_breaks("NDVI", 2)
        with self.assertRaises(ValueError):
            sl.index_breaks("NDVI", 8)
        with self.assertRaises(ValueError):
            sl.index_class_labels("NDVI", [0.5, 0.4])
        with self.assertRaises(ValueError):
            sl.index_look("NDVI", 6)


class TestManagementZones(unittest.TestCase):
    def test_zones_run_light_to_dark_with_the_mean_and_nothing_else(self):
        zones = sl.zone_look("NDVI", [0.5, 0.31, 0.72])
        self.assertEqual([z["label"] for z in zones], ["Zone 1: mean NDVI 0.31", "Zone 2: mean NDVI 0.50", "Zone 3: mean NDVI 0.72"])
        self.assertEqual([z["colour"] for z in zones], ["#EDF8E9", "#74C476", "#006D2C"])

    def test_three_to_five_zones_only(self):
        for n in (3, 4, 5):
            self.assertEqual(len(sl.zone_look("NDRE", [i / 10 for i in range(1, n + 1)])), n)
        for n in (0, 1, 2, 6):
            with self.assertRaises(ValueError):
                sl.zone_look("NDVI", [i / 10 for i in range(n)])

    def test_a_zone_label_never_states_a_rate_or_a_yield(self):
        words = set(re.findall(r"[a-z]+", " ".join(z["label"] for z in sl.zone_look("NDVI", [0.2, 0.4, 0.6, 0.8, 0.9])).lower()))
        for banned in ("kg", "ha", "rate", "yield", "apply", "recommend", "fertiliser", "fertilizer"):
            self.assertNotIn(banned, words)

    def test_unknown_index_is_refused(self):
        with self.assertRaises(ValueError):
            sl.zone_look("EVI", [0.1, 0.2, 0.3])


class TestRampsAndHatch(unittest.TestCase):
    def test_ramp_steps_include_both_ends_and_refuse_bad_counts(self):
        self.assertEqual(sl.ramp_steps("Greens", 2), [sp.colours("Greens")[0], sp.colours("Greens")[-1]])
        self.assertEqual(sl.ramp_steps("Greens", 5), sp.colours("Greens"))
        for n in (1, 6):
            with self.assertRaises(ValueError):
                sl.ramp_steps("Greens", n)

    def test_the_protected_area_hatch_is_a_brush_pattern_with_an_outline(self):
        hatch = sl.HATCHES["protected_area"]
        self.assertEqual(hatch["kind"], "brush_pattern")
        self.assertEqual(hatch["brush"], "BDiagPattern")
        for key in ("colour", "outline_colour"):
            cr.hex_to_rgb(hatch[key])
        self.assertGreater(hatch["outline_width_mm"], 0)

    def test_every_look_names_things_that_exist(self):
        for profile, looks in sl.LOOKS.items():
            self.assertIn(profile, sp.PROFILES)
            for spec in looks.values():
                if "palette" in spec:
                    self.assertIn(spec["palette"], sp.PALETTES)
                if "hatch" in spec:
                    self.assertIn(spec["hatch"], sl.HATCHES)
                for index in spec.get("indices", []):
                    self.assertIn(index, sl.INDEX_DISPLAY)

    def test_each_index_palette_is_sequential_and_passes_the_ramp_rule(self):
        for index, (palette, low, high, units) in sl.INDEX_DISPLAY.items():
            self.assertEqual(sp.PALETTES[palette]["kind"], "sequential", index)
            self.assertLess(low, high)
            self.assertTrue(units)
            self.assertEqual(cr.weak_neighbours(sp.colours(palette), 5.0), [], index)


if __name__ == "__main__":
    unittest.main()
