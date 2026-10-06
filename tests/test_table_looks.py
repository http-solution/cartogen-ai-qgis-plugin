"""Looks for imported tables and generic measured values (IPC, INFORM, UNOSAT damage, measure) and the hints that point at them."""
import unittest

from cartogen_ai.core.agent.tools import humanitarian_style as hs


class TestTableLooks(unittest.TestCase):
    def test_ipc_phases_are_one_to_five_with_a_not_analysed_catch_all(self):
        rules = hs.phase_rules("ipc_phase", hs.IPC_PHASES, hs.IPC_NOT_ANALYSED)
        self.assertEqual([r[0] for r in rules[:5]], ["1 Minimal", "2 Stressed", "3 Crisis", "4 Emergency", "5 Famine"])
        self.assertEqual((rules[-1][0], rules[-1][1]), ("Not analysed", "ELSE"))

    def test_inform_classes_cover_zero_to_ten_without_gaps_or_overlap(self):
        ranges = hs.inform_ranges()
        self.assertEqual(len(ranges), 5)
        self.assertEqual(ranges[0][0], 0.0)
        self.assertGreaterEqual(ranges[-1][1], 10.0)
        for (_l1, h1, *_a), (l2, _h2, *_b) in zip(ranges, ranges[1:]):
            self.assertLess(h1, l2)           # a value on a class start belongs to the higher class only
            self.assertLess(l2 - h1, 1e-6)    # and nothing falls between two classes

    def test_damage_rules_match_the_file_wording_not_only_the_normalised_names(self):
        rules = hs.damage_rules("main_damage_site_class", ["Destroyed", "Severe Damage", "severely damaged", "No Visible Damage", None, "???"])
        self.assertEqual([r[0] for r in rules], ["Destroyed", "Severe damage", "No visible damage", "Other / not classified"])
        severe = next(r for r in rules if r[0] == "Severe damage")
        self.assertIn("'severe damage'", severe[1])
        self.assertIn("'severely damaged'", severe[1])
        self.assertEqual(rules[-1][1], "ELSE")
        self.assertEqual(hs.damage_rules("f", ["x", None]), [])

    def test_table_hints(self):
        hints = hs.table_look_hints("admin", ["ipc_phase", "ipc_pop", "ipc_p3plus", "inf_risk", "jp_health", "js_wash", "other"])
        got = {h["args"]["field"]: h["args"]["look"] for h in hints}
        self.assertEqual(got, {"ipc_phase": "ipc_phase", "ipc_p3plus": "people_in_need", "inf_risk": "inform_risk",
                               "jp_health": "people_in_need", "js_wash": "jiaf_severity"})

    def test_measure_hint_says_what_the_number_is(self):
        h = hs.measure_hint("roads", "assumed_speed_kmh", "The assumed speed per road")
        self.assertEqual(h["args"], {"layer_name": "roads", "look": "measure", "field": "assumed_speed_kmh"})
        self.assertIn("assumed speed per road", h["note"])
        self.assertIsNone(hs.measure_hint("", "f", "x"))

    def test_class_colours_are_distinct_for_up_to_ten_classes(self):
        self.assertEqual(len(set(hs.class_colors(10))), 10)
        self.assertEqual(len(hs.class_colors(12)), 12)


if __name__ == "__main__":
    unittest.main()
