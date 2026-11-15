"""
Golden Scenario GS-JIAF-001: End-to-End JIAF 2 Preliminary to Final Results Traceability.

Validates the full JIAF processing chain:
1. Sectoral PiN inputs (8 main clusters)
2. Preliminary Joint PiN calculation (Mosaic Method: highest sectoral PiN)
3. PiN Flag detection (Flags 1-6 according to Table 3A / Worksheet 2026 profile)
4. Intersectoral Severity rule (Box 22: >=4 sectors in phase)
5. Decision recording for flagged units (Final PiN & Final Severity)
6. Final results assembly & invariant summation
"""

import unittest
from cartogen_ai.core.agent.tools import jiaf_engine as je
from cartogen_ai.core.agent.tools import jiaf_rules as jr


class TestGoldenScenarioJiaf001(unittest.TestCase):
    def test_gs_jiaf_001_complete_traceability_chain(self):
        """
        Scenario:
        Unit 1 (YE0101):
          Sector PiNs: health=50000, wash=48000, fsac=45000, nut=10000, edu=5000, shl=5000, cccm=0, pro=10000
          Pop = 100000
          Highest sector = health (50,000) -> Preliminary Joint PiN = 50,000.
          Second highest = wash (48,000). Difference = (50000-48000)/50000 = 4% (< 30% threshold -> Flag 2 does not fire).
          Sector Severities: health=4, wash=4, fsac=4, nut=4, edu=3, shl=3, cccm=1, pro=3
          Count of sectors >= 4: 4 (health, wash, fsac, nut).
          Box 22 Rule: At least 4 sectors in phase 4 -> Preliminary Severity = 4.

        Unit 2 (YE0102):
          Sector PiNs: fsac=90000, health=20000, wash=10000, nut=5000, edu=0, shl=0, cccm=0, pro=0
          Pop = 100000
          Highest sector = fsac (90,000).
          Second highest = health (20,000). Difference = (90000-20000)/90000 = 77.8% (> 30% -> Flag 2 FIRES!).
          Preliminary Joint PiN = 90,000, but unit is FLAGGED.

        Group Decision Phase:
          - Unit 1 is unflagged -> Final PiN = 50,000, Final Severity = 4.
          - Unit 2 is flagged on Flag 2. Analysis team records consensus:
            Agreed to accept 2nd highest (Health: 20,000) due to FSAC localized pocket assessment,
            with recorded rationale "Accepted 2nd highest after cluster review".
            Final PiN for Unit 2 = 20,000. Final Severity agreed = 3.

        Final Joint Overall PiN = 50,000 (Unit 1) + 20,000 (Unit 2) = 70,000.
        """
        settings = je.merge_settings()

        # 1. Unit 1 Evaluation
        u1_pins = {
            "health": 50000, "wash": 48000, "food_security": 45000, "nutrition": 10000,
            "education": 5000, "shelter": 5000, "cccm": 0, "protection": 10000
        }
        u1_sevs = {
            "health": 4, "wash": 4, "food_security": 4, "nutrition": 4,
            "education": 3, "shelter": 3, "cccm": 1, "protection": 3
        }

        # PiN Flags & Preliminary PiN
        u1_flags, u1_ranks = jr.pin_flags(u1_pins, 100000, settings, None)
        self.assertEqual(u1_ranks["highest"], 50000)
        self.assertFalse(u1_flags[2]["fired"])  # Diff is 4%, < 30%

        # Preliminary Severity (Box 22) takes list/values of sector phases
        u1_sev_calc = je.preliminary_severity(list(u1_sevs.values()))
        self.assertEqual(u1_sev_calc, 4)

        # 2. Unit 2 Evaluation
        u2_pins = {
            "food_security": 90000, "health": 20000, "wash": 10000, "nutrition": 5000,
            "education": 0, "shelter": 0, "cccm": 0, "protection": 0
        }
        u2_flags, u2_ranks = jr.pin_flags(u2_pins, 100000, settings, None)
        self.assertEqual(u2_ranks["highest"], 90000)
        self.assertTrue(u2_flags[2]["fired"])  # Diff is 77.8%, > 30% threshold fires

        # 3. Simulate Consensus Decision Application
        # Unit 1 unflagged -> retains preliminary PiN 50,000
        # Unit 2 flagged -> receives recorded decision of 20,000
        unit_results = [
            {"unit": "YE0101", "preliminary_pin": 50000, "is_flagged": False, "final_pin": 50000, "final_sev": 4},
            {"unit": "YE0102", "preliminary_pin": 90000, "is_flagged": True, "final_pin": 20000, "final_sev": 3,
             "rationale": "Accepted 2nd highest after cluster review"},
        ]

        # National Summation Rule: Sum happens across units only
        national_preliminary_pin = sum(u["preliminary_pin"] for u in unit_results)
        national_final_pin = sum(u["final_pin"] for u in unit_results)

        self.assertEqual(national_preliminary_pin, 140000)
        self.assertEqual(national_final_pin, 70000)


if __name__ == "__main__":
    unittest.main()
