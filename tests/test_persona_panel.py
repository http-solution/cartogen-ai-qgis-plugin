"""PLAN-023 R1-3: the readiness panel text. Offline, no QGIS. The panel is generated from the persona files, so these tests pin its shape and check that it never says more than the files do."""
import unittest

from cartogen_ai.core import personas as pp
from cartogen_ai.core.personas import panel


class TestSections(unittest.TestCase):
    def test_headings_come_in_a_fixed_order_and_empty_ones_are_left_out(self):
        persona = pp.get("public_health")
        headings = [h for h, _ in panel.sections(persona)]
        self.assertEqual(headings, ["Available (checked by automatic tests)", "Not built yet"])
        self.assertNotIn("Built and seen working", headings)

    def test_not_built_lines_name_the_release_and_out_of_scope_lines_name_the_reason(self):
        text = panel.panel_text("public_health")
        self.assertIn("Moran's I and Getis-Ord Gi* tests - due in R2 (1.20.0)", text)
        self.assertIn("DHIS2 connector - due in R7 (1.25.0) (needs the owner's credentials)", text)
        text = panel.panel_text("utilities")
        self.assertIn("SCADA and live meters - live telemetry is outside what the plugin connects to", text)

    def test_available_lines_name_the_tool(self):
        self.assertIn("density surface of cases [hotspot_analysis]", panel.panel_text("public_health"))

    def test_the_agreed_example_primary_public_health_secondary_logistics(self):
        text = panel.panel_text("public_health", "logistics")
        self.assertIn("Primary: Public Health / Epidemiology", text)
        self.assertIn("Secondary: Logistics / Supply Chain", text)
        self.assertLess(text.index("Primary:"), text.index("Secondary:"))
        self.assertIn("Kulldorff spatial scan with Monte Carlo", text)                     # a not-built item of the primary
        self.assertIn("vehicle routing with capacity and time windows - due in R5 (1.23.0)", text)   # a not-built item of the secondary
        self.assertIn("hub siting and location-allocation [optimal_hub_siting]", text)       # an available item of the secondary

    def test_the_same_persona_twice_is_shown_once_and_an_unknown_id_is_ignored(self):
        self.assertNotIn("Secondary:", panel.panel_text("logistics", "logistics"))
        self.assertEqual(panel.panel_text("nonsense"), "")
        self.assertNotIn("Secondary:", panel.panel_text("logistics", "nonsense"))

    def test_the_text_says_no_tool_is_hidden(self):
        self.assertIn("Every tool stays available", panel.panel_text("general"))

    def test_nothing_is_called_built_unless_a_file_says_built(self):
        for pid in pp.ids():
            persona = pp.get(pid)
            has_built = any(i["state"] == "built" for i in persona["readiness"])
            self.assertEqual("Built and seen working" in panel.panel_text(pid), has_built, pid)

    def test_every_capability_of_every_persona_appears_in_its_panel(self):
        for pid in pp.ids():
            text = panel.panel_text(pid)
            for item in pp.get(pid)["readiness"]:
                self.assertIn(item["capability"], text, f"{pid}: {item['capability']}")

    def test_persona_fifteen_shows_the_agreed_sentence(self):
        self.assertIn("Not built as written. Open-source conflict and access analysis is available under Humanitarian and Public Safety. Classified data must never be used with this plugin.", panel.panel_text("defense_intel"))


if __name__ == "__main__":
    unittest.main()
