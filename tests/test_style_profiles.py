"""PLAN-023 R1-7: the persona style registry and the colour rules it must obey. Offline, no QGIS. The colour maths is checked against published known answers; the rules are shown able to fail on synthetic palettes so a check
that passes everything cannot slip through."""
import unittest

from cartogen_ai.core import personas as pp
from cartogen_ai.core.representation import colour_rules as cr
from cartogen_ai.core.representation import style_profiles as sp

MIN_CATEGORICAL = 10.0
MIN_RAMP_STEP = 5.0


class TestColourMathAgainstPublishedAnswers(unittest.TestCase):
    def test_ciede2000_reproduces_the_published_test_pairs(self):
        # Sharma, Wu and Dalal (2005), supplementary test data, pairs 1 to 4
        pairs = [((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425), ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
                 ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412), ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0000)]
        for a, b, expected in pairs:
            self.assertAlmostEqual(cr.delta_e2000(a, b), expected, places=4)
            self.assertAlmostEqual(cr.delta_e2000(b, a), expected, places=4)

    def test_lab_of_black_and_white(self):
        self.assertEqual(cr.rgb_to_lab((0, 0, 0)), (0.0, 0.0, 0.0))
        light, a, b = cr.rgb_to_lab((255, 255, 255))
        self.assertAlmostEqual(light, 100.0, places=3)
        self.assertAlmostEqual(a, 0.0, places=3)
        self.assertAlmostEqual(b, 0.0, places=3)

    def test_a_colour_has_no_difference_from_itself(self):
        for kind in (None, *cr.CVD_MATRICES):
            self.assertAlmostEqual(cr.colour_difference("#0072B2", "#0072B2", kind), 0.0, places=6)

    def test_grey_stays_grey_under_every_simulation(self):
        for kind in cr.CVD_MATRICES:
            r, g, b = cr.simulate((128, 128, 128), kind)
            self.assertAlmostEqual(r, g, delta=1.0)
            self.assertAlmostEqual(g, b, delta=1.0)

    def test_red_and_green_collapse_for_people_without_red_or_green_cones(self):
        normal = cr.colour_difference("#E00000", "#2E8B57")
        for kind in ("deuteranopia", "protanopia"):
            self.assertLess(cr.colour_difference("#E00000", "#2E8B57", kind), normal)

    def test_hex_parsing(self):
        self.assertEqual(cr.hex_to_rgb("#0072B2"), (0, 114, 178))
        with self.assertRaises(ValueError):
            cr.hex_to_rgb("#FFF")


class TestTheRulesCanFail(unittest.TestCase):
    def test_red_beside_green_is_caught(self):
        self.assertEqual(cr.red_beside_green(["#0072B2", "#E00000", "#2E8B57"]), [(1, 2)])
        self.assertEqual(cr.red_beside_green(["#2E8B57", "#E00000"]), [(0, 1)])
        self.assertEqual(cr.red_beside_green(["#E00000", "#0072B2", "#2E8B57"]), [])

    def test_two_colours_that_look_alike_are_caught(self):
        self.assertTrue(cr.weak_neighbours(["#0072B2", "#0073B3"]))

    def test_a_pair_that_differs_normally_but_not_to_a_protanope_is_caught(self):
        problems = cr.weak_neighbours(["#E00000", "#2E8B57"], minimum=60.0)
        self.assertTrue(any(kind == "protanopia" for _i, kind, _d in problems) or any(kind == "deuteranopia" for _i, kind, _d in problems))

    def test_red_and_green_hues_are_recognised_and_greys_are_not(self):
        self.assertTrue(cr.is_red("#CA0020"))
        self.assertTrue(cr.is_green("#31A354"))
        self.assertFalse(cr.is_red("#969696"))
        self.assertFalse(cr.is_green("#969696"))
        self.assertFalse(cr.is_red("#0072B2"))


class TestEveryPalette(unittest.TestCase):
    def test_every_palette_has_valid_hex_colours_and_a_known_kind(self):
        for name, palette in sp.PALETTES.items():
            self.assertIn(palette["kind"], ("categorical", "sequential", "diverging"), name)
            self.assertGreaterEqual(len(palette["colours"]), 5 if palette["kind"] != "categorical" else 6, name)
            self.assertEqual(len(set(palette["colours"])), len(palette["colours"]), name)
            for colour in palette["colours"]:
                cr.hex_to_rgb(colour)

    def test_no_palette_puts_red_beside_green(self):
        for name, palette in sp.PALETTES.items():
            self.assertEqual(cr.red_beside_green(palette["colours"]), [], name)

    def test_categorical_neighbours_stay_apart_in_normal_vision_and_all_three_simulations(self):
        for name, palette in sp.PALETTES.items():
            if palette["kind"] == "categorical":
                self.assertEqual(cr.weak_neighbours(palette["colours"], MIN_CATEGORICAL), [], name)

    def test_ramp_steps_stay_distinguishable(self):
        for name, palette in sp.PALETTES.items():
            if palette["kind"] != "categorical":
                self.assertEqual(cr.weak_neighbours(palette["colours"], MIN_RAMP_STEP), [], name)

    def test_a_diverging_ramp_has_a_light_neutral_middle(self):
        for name, palette in sp.PALETTES.items():
            if palette["kind"] == "diverging":
                middle = cr.rgb_to_lab(cr.hex_to_rgb(palette["colours"][len(palette["colours"]) // 2]))
                self.assertGreater(middle[0], 90, name)
                self.assertLess(abs(middle[1]) + abs(middle[2]), 8, name)

    def test_the_utility_colour_code_names_one_utility_per_colour(self):
        palette = sp.PALETTES["utility_colour_code"]
        self.assertEqual(len(palette["labels"]), len(palette["colours"]))
        self.assertIn("water", palette["labels"])


class TestRegistry(unittest.TestCase):
    def test_every_persona_names_a_registered_style_profile(self):
        for pid in pp.ids():
            self.assertIn(pp.get(pid)["style_profile"], sp.PROFILES, pid)

    def test_no_profile_is_unused(self):
        used = {pp.get(pid)["style_profile"] for pid in pp.ids()}
        self.assertEqual(sorted(set(sp.PROFILES) - used), [])

    def test_every_profile_has_every_role_with_a_matching_palette_kind(self):
        for profile_id, roles in sp.PROFILES.items():
            self.assertEqual(sorted(roles), sorted(sp.ROLES), profile_id)
            for role, spec in roles.items():
                palette = sp.PALETTES[spec["palette"]]
                self.assertEqual(palette["kind"], sp.ROLE_KIND[role], f"{profile_id}/{role}")
                self.assertGreaterEqual(spec["classes"], 3, f"{profile_id}/{role}")
                self.assertLessEqual(spec["classes"], len(palette["colours"]), f"{profile_id}/{role}")

    def test_a_placeholder_says_why(self):
        placeholders = [(p, r) for p, roles in sp.PROFILES.items() for r, spec in roles.items() if spec["status"] == "placeholder"]
        self.assertTrue(placeholders)
        for profile_id, role in placeholders:
            self.assertGreater(len(sp.PROFILES[profile_id][role]["reason"]), 20, f"{profile_id}/{role}")
        for profile_id, roles in sp.PROFILES.items():
            for role, spec in roles.items():
                self.assertIn(spec["status"], ("chosen", "placeholder"), f"{profile_id}/{role}")

    def test_the_two_conventions_the_plan_names_are_present(self):
        self.assertEqual(sp.spec("utilities", "categorical")["palette"], "utility_colour_code")
        self.assertEqual(sp.spec("public_health", "intensity")["palette"], "Blues")
        self.assertEqual(sp.spec("research", "intensity")["palette"], "Greys")

    def test_nothing_in_a_diverging_role_is_red_and_green(self):
        for profile_id, roles in sp.PROFILES.items():
            palette = sp.PALETTES[roles["difference"]["palette"]]["colours"]
            self.assertFalse(any(cr.is_red(c) for c in palette) and any(cr.is_green(c) for c in palette), profile_id)

    def test_an_unknown_profile_reads_as_general_and_an_unknown_role_raises(self):
        self.assertEqual(sp.spec("nonsense", "intensity"), sp.spec("general", "intensity"))
        self.assertEqual(sp.spec(None, "categorical"), sp.spec("general", "categorical"))
        with self.assertRaises(ValueError):
            sp.spec("general", "mood")

    def test_spec_returns_a_copy_the_caller_cannot_use_to_change_the_registry(self):
        spec = sp.spec("general", "intensity")
        spec["palette"] = "Hacked"
        self.assertEqual(sp.spec("general", "intensity")["palette"], "Blues")

    def test_colours_returns_a_copy_and_rejects_unknown_names(self):
        first = sp.colours("Blues")
        first.append("#000000")
        self.assertEqual(len(sp.colours("Blues")), 5)
        with self.assertRaises(ValueError):
            sp.colours("Rainbow")

    def test_the_persona_checker_flags_an_unregistered_style_profile(self):
        persona = dict(pp.get("general"), style_profile="not_a_profile")
        problems = pp.validate(persona, style_profile_ids=set(sp.PROFILES))
        self.assertEqual(len(problems), 1)
        self.assertIn("style profile registry", problems[0])
        self.assertEqual(pp.validate(pp.get("general"), style_profile_ids=set(sp.PROFILES)), [])


if __name__ == "__main__":
    unittest.main()
