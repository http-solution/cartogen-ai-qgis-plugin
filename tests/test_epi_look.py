"""PLAN-023 R2-5: the public-health look, pure rules. Offline, no QGIS: the real renderers are read back in tests/test_public_health_look_live.py (CI's QGIS job)."""
import unittest

from cartogen_ai.core.representation import colour_rules, epi_look, style_profiles


class TestLegendAndClasses(unittest.TestCase):
    def test_the_legend_sentence_is_exactly_the_plans(self):
        self.assertEqual(epi_look.legend_title(), "Rate per 100,000; suppressed where n < 5")
        self.assertEqual(epi_look.legend_title(per=1000, min_cases=10), "Rate per 1,000; suppressed where n < 10")

    def test_quantiles_of_1_to_100_break_at_the_hand_computed_points(self):
        # type-7 quantile: position (n-1) q = 99 q; q = 0.2 -> 19.8 -> 1 + 19.8 = 20.8; 0.4 -> 40.6; 0.6 -> 60.4; 0.8 -> 80.2
        classes = epi_look.rate_classes(range(1, 101))["classes"]
        edges = [classes[0]["lo"]] + [c["hi"] for c in classes]
        for got, expected in zip(edges, (1.0, 20.8, 40.6, 60.4, 80.2, 100.0), strict=True):
            self.assertAlmostEqual(got, expected, places=9)
        self.assertEqual(len(classes), 5)

    def test_five_classes_use_the_public_health_ramp_in_order_and_one_hue(self):
        spec = style_profiles.spec("public_health", "intensity")
        classes = epi_look.rate_classes(range(1, 101))["classes"]
        self.assertEqual([c["colour"] for c in classes], style_profiles.colours(spec["palette"]))
        self.assertEqual(spec["palette"], "Blues")
        self.assertEqual(spec["classes"], 5)

    def test_every_shown_figure_falls_in_exactly_one_class_and_suppressed_ones_in_none(self):
        values = [2, 5, 9, 14, 20, 33, 47, 60, 75, 91, 100]
        classes = epi_look.rate_classes(values)["classes"]
        for v in values:
            hits = [c for c in classes if c["lo"] <= v < c["hi"] or (c is classes[-1] and v == c["hi"])]     # the half-open rule, the top class includes its top
            self.assertEqual(len(hits), 1, v)
            self.assertIs(epi_look.class_for(v, classes), hits[0])
        self.assertIsNone(epi_look.class_for(None, classes))
        self.assertIsNone(epi_look.class_for(float("nan"), classes))

    def test_repeated_figures_never_make_empty_or_duplicate_classes(self):
        result = epi_look.rate_classes([1, 1, 1, 1, 5])
        self.assertEqual(len(result["classes"]), 2)
        self.assertEqual(result["dropped"], 3)
        edges = [result["classes"][0]["lo"]] + [c["hi"] for c in result["classes"]]
        self.assertEqual(edges, sorted(set(edges)))

    def test_all_figures_equal_is_one_class(self):
        result = epi_look.rate_classes([3, 3, 3])
        self.assertEqual(len(result["classes"]), 1)
        self.assertIs(epi_look.class_for(3, result["classes"]), result["classes"][0])

    def test_suppressed_figures_are_ignored_when_classing(self):
        with_suppressed = epi_look.rate_classes([None, float("nan"), *range(1, 101)])
        self.assertEqual(with_suppressed["shown"], 100)
        self.assertEqual(with_suppressed["classes"], epi_look.rate_classes(range(1, 101))["classes"])

    def test_nothing_shown_and_bad_class_counts_are_refused(self):
        with self.assertRaises(ValueError):
            epi_look.rate_classes([None, None])
        for bad in (1, 6, True, 2.5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                epi_look.rate_classes([1, 2, 3], bad)

    def test_labels_read_as_plain_ranges(self):
        classes = epi_look.rate_classes([10, 1200, 3400, 56000])["classes"]
        self.assertTrue(all(" to " in c["label"] for c in classes))
        self.assertIn("1,", " ".join(c["label"] for c in classes))


class TestColourRules(unittest.TestCase):
    def test_nothing_in_the_look_is_red(self):
        self.assertEqual(epi_look.any_red(epi_look.all_colours()), [])

    def test_cluster_outline_is_a_black_line_under_a_narrower_white_line(self):
        black, white = epi_look.CLUSTER_STROKES
        self.assertEqual((black["colour"], white["colour"]), ("#000000", "#FFFFFF"))
        self.assertGreater(black["width_mm"], white["width_mm"])
        self.assertFalse(any(colour_rules.is_red(s["colour"]) for s in epi_look.CLUSTER_STROKES))

    def test_no_red_beside_green_in_any_class_table_and_the_rate_ramp(self):
        for table in (epi_look.LISA_CLASSES, epi_look.HOTSPOT_CLASSES):
            self.assertEqual(colour_rules.red_beside_green([c for _v, c, _l in table]), [])
        self.assertEqual(colour_rules.red_beside_green([c["colour"] for c in epi_look.rate_classes(range(1, 101))["classes"]]), [])

    def test_class_neighbours_stay_distinguishable_in_every_vision_type(self):
        for table in (epi_look.LISA_CLASSES, epi_look.HOTSPOT_CLASSES):
            self.assertEqual(colour_rules.weak_neighbours([c for _v, c, _l in table]), [], table[0][0])

    def test_the_rate_ramp_neighbours_pass_the_ramp_floor_of_5(self):
        self.assertEqual(colour_rules.weak_neighbours([c["colour"] for c in epi_look.rate_classes(range(1, 101))["classes"]], minimum=5.0), [])


class TestCategories(unittest.TestCase):
    def test_lisa_classes_are_the_names_the_moran_tool_writes(self):
        self.assertEqual([v for v, _c, _l in epi_look.category_entries("lisa")], ["HH", "HL", "LH", "LL", "not significant", "no neighbours"])

    def test_hotspot_classes_are_the_names_the_gi_star_tool_writes(self):
        from cartogen_ai.core.agent.tools import _spatial_stats as ss
        written = {ss.hot_cold_class(z, p, 0.10) for z, p in ((3, 0.001), (2, 0.04), (1.7, 0.09), (-3, 0.001), (-2, 0.04), (-1.7, 0.09), (0, 1))}
        self.assertLessEqual(written, {v for v, _c, _l in epi_look.category_entries("hotspot")})

    def test_other_looks_have_no_table(self):
        with self.assertRaises(ValueError):
            epi_look.category_entries("rate")

    def test_the_registry_still_names_a_single_hue_rate_ramp_per_100000(self):
        spec = style_profiles.spec("public_health", "intensity")
        self.assertEqual(spec["label_units"], "per 100,000")
        self.assertIn("hatched", spec["convention"])


if __name__ == "__main__":
    unittest.main()
