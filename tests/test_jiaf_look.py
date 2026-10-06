"""JIAF 2 map looks: the pure rules (phase classes, review status, hints) and that the look list stays consistent."""
import unittest

from cartogen_ai.core.agent.tools import humanitarian_style as hs
from cartogen_ai.core.agent.tools.humanitarian_look_tools import LOOK_DESCRIPTIONS


class TestJiafLookRules(unittest.TestCase):
    def test_every_look_is_described_for_the_model(self):
        self.assertEqual(set(hs.LOOKS), set(LOOK_DESCRIPTIONS))

    def test_phase_rules_cover_phases_one_to_five_and_a_not_assessed_catch_all(self):
        rules = hs.jiaf_phase_rules("jf_fin_sev")
        self.assertEqual([r[0] for r in rules[:5]], ["1 None / minimal", "2 Stress", "3 Severe", "4 Extreme", "5 Catastrophic"])
        self.assertEqual(rules[-1][1], "ELSE")
        self.assertIn("not assessed", rules[-1][0])
        self.assertEqual(len({r[2] for r in rules}), 6)

    def test_phase_filters_use_half_open_bands_so_a_phase_stored_as_a_double_matches_once(self):
        rules = hs.jiaf_phase_rules("jf_pre_sev")
        self.assertEqual(rules[2][1], '"jf_pre_sev" >= 2.5 AND "jf_pre_sev" < 3.5')

    def test_a_field_name_with_a_quote_is_escaped(self):
        self.assertIn('"a""b"', hs.jiaf_phase_rules('a"b')[0][1])

    def test_review_rules_name_the_units_still_waiting_for_the_group(self):
        labels = [r[0] for r in hs.jiaf_review_rules("jiaf_review_severity", "jf_sev_st")]
        self.assertIn("Pending: flagged, needs the group", labels)
        self.assertIn("Incomplete sector coverage", labels)
        self.assertEqual(hs.jiaf_review_rules("jiaf_review_pin", "jf_pin_st")[-1][1], "ELSE")

    def test_review_codes_match_the_codes_the_tools_write(self):
        from cartogen_ai.core.agent.tools.jiaf_review import PIN_STATUS_CODE, SEV_STATUS_CODE
        self.assertEqual({n for n, _c, _l in hs.JIAF_REVIEW["jiaf_review_pin"]}, set(PIN_STATUS_CODE.values()))
        self.assertEqual({n for n, _c, _l in hs.JIAF_REVIEW["jiaf_review_severity"]}, set(SEV_STATUS_CODE.values()))

    def test_hints_exist_for_every_field_the_jiaf_tools_write(self):
        written = ["jf_pre_pin", "jf_pre_sev", "jf_npinfl", "jf_nsevfl", "jf_fin_pin", "jf_fin_sev", "jf_pin_rk", "jf_pin_st", "jf_sev_st",
                   "jf_nsec40", "jf_nsev45"]
        hints = hs.jiaf_look_hints("districts", written)
        by_field = {h["args"]["field"]: h["args"]["look"] for h in hints}
        self.assertEqual(by_field["jf_pre_sev"], "jiaf_severity")
        self.assertEqual(by_field["jf_fin_pin"], "people_in_need")
        self.assertEqual(by_field["jf_sev_st"], "jiaf_review_severity")
        self.assertNotIn("jf_pin_rk", by_field)  # a rank code, not a map message
        self.assertTrue(all(h["tool"] == "apply_humanitarian_look" and h["args"]["layer_name"] == "districts" for h in hints))
        self.assertEqual(hs.jiaf_look_hints(None, written), [])


class TestSmokeFixtureNumbers(unittest.TestCase):
    """The figures printed in docs/SMOKE_RUN_SHEET_rc18 for docs/release_smoke_assets/inputs/smoke_jiaf_hxl.csv. They are what this
    code computes (a regression pin), not an independent check of the JIAF rules."""
    PATH = None

    @classmethod
    def setUpClass(cls):
        import os
        cls.PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "release_smoke_assets", "inputs",
                                "smoke_jiaf_hxl.csv")

    def test_preliminary_figures(self):
        from cartogen_ai.core.agent.tools.jiaf_engine import compute_jiaf_preliminary
        out = compute_jiaf_preliminary(self.PATH)
        self.assertTrue(out["success"], out)
        rows = {u["admin2_code"]: u for u in out["most_flagged_units"]}
        self.assertEqual((rows["District_1"]["preliminary_pin"], rows["District_1"]["preliminary_severity"]), (500.0, 3))
        self.assertEqual((rows["District_2"]["preliminary_pin"], rows["District_2"]["preliminary_severity"]), (1800.0, 5))
        self.assertEqual(rows["District_3"]["preliminary_pin"], 600.0)
        self.assertIsNone(rows["District_3"]["preliminary_severity"])
        self.assertEqual(out["national_preliminary_pin"], 3020.0)
        self.assertEqual(out["worksheet_preliminary_pin"]["national"], 2300.0)

    def test_final_figures_with_no_decision_recorded(self):
        from cartogen_ai.core.agent.tools.jiaf_review import finalize_jiaf_results
        out = finalize_jiaf_results(self.PATH)
        self.assertTrue(out["success"], out)
        self.assertEqual(out["final_pin_total"], 2900.0)
        self.assertTrue(out["provisional"])
        self.assertEqual({u["unit"] for u in out["pending_units_shown"]}, {"District_2", "District_3"})


if __name__ == "__main__":
    unittest.main()
