"""PLAN-023 R1-2: one persona list and the migration of what users already have stored. Offline, no QGIS: the settings store is a plain fake."""
import unittest

from cartogen_ai.core import personas as pp
from cartogen_ai.core.agent.onboarding_profile import ROLE_CHOICES
from cartogen_ai.core.personas import selection as sel
from cartogen_ai.core.services.prompt_refiner import PROFILE_GUIDANCE, PROFILE_LABELS

OLD_FIFTEEN = ("general", "humanitarian", "engineering", "urban_planning", "logistics", "agriculture", "environment", "public_health", "disaster_risk", "utilities", "transport", "public_safety",
               "research", "real_estate", "defense_intel")


class FakeSettings:
    def __init__(self, **stored):
        self.data = {f"cartogen_ai/{k}": v for k, v in stored.items()}
        self.writes = []

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.writes.append(key)
        self.data[key] = value


class BrokenSettings:
    def value(self, key, default=None):
        raise RuntimeError("store unavailable")

    def setValue(self, key, value):
        raise RuntimeError("store unavailable")


class TestOneList(unittest.TestCase):
    def test_the_refiners_two_dicts_are_views_of_the_persona_files(self):
        self.assertEqual(tuple(PROFILE_LABELS), OLD_FIFTEEN)
        self.assertEqual(tuple(PROFILE_GUIDANCE), OLD_FIFTEEN)
        for pid in OLD_FIFTEEN:
            self.assertEqual(PROFILE_LABELS[pid], pp.get(pid)["label"])
            self.assertEqual(PROFILE_GUIDANCE[pid], pp.get(pid)["guidance"])

    def test_the_labels_shown_in_settings_are_unchanged(self):
        self.assertEqual(PROFILE_LABELS["general"], "GIS Generalist")
        self.assertEqual(PROFILE_LABELS["public_health"], "Public Health / Epidemiology")
        self.assertEqual(PROFILE_LABELS["defense_intel"], "Defense / Intelligence")


class TestRoleMapping(unittest.TestCase):
    def test_every_onboarding_role_maps_to_a_persona_and_nothing_else_is_mapped(self):
        self.assertEqual(set(sel.ROLE_TO_PERSONA), set(ROLE_CHOICES))
        for role, persona in sel.ROLE_TO_PERSONA.items():
            self.assertIn(persona, pp.ids(), role)

    def test_the_agreed_mapping(self):
        self.assertEqual(sel.ROLE_TO_PERSONA, {"humanitarian_analyst": "humanitarian", "urban_planner": "urban_planning", "researcher": "research", "emergency_responder": "humanitarian",
                                               "cartographer": "general", "gis_student": "general", "other": "general"})


class TestResolve(unittest.TestCase):
    def test_each_of_the_fifteen_old_stored_values_becomes_the_same_primary(self):
        for old in OLD_FIFTEEN:
            self.assertEqual(sel.resolve_selection(legacy_profile=old), (old, "", True), old)

    def test_a_stored_primary_wins_over_the_old_value_and_the_role(self):
        self.assertEqual(sel.resolve_selection(primary="agriculture", legacy_profile="engineering", role="humanitarian_analyst"), ("agriculture", "", False))

    def test_an_unknown_stored_primary_is_replaced_not_trusted(self):
        self.assertEqual(sel.resolve_selection(primary="astronaut", legacy_profile="logistics"), ("logistics", "", True))
        self.assertEqual(sel.resolve_selection(primary="astronaut"), ("general", "", True))
        self.assertEqual(sel.resolve_selection(primary=7), ("general", "", True))

    def test_with_no_old_value_a_finished_onboarding_role_chooses_the_default(self):
        self.assertEqual(sel.resolve_selection(role="humanitarian_analyst")[0], "humanitarian")
        self.assertEqual(sel.resolve_selection(role="urban_planner")[0], "urban_planning")
        self.assertEqual(sel.resolve_selection(role="researcher")[0], "research")
        self.assertEqual(sel.resolve_selection(role="gis_student")[0], "general")
        self.assertEqual(sel.resolve_selection(role="not a role")[0], "general")

    def test_an_explicit_old_general_is_a_choice_and_beats_the_role_but_an_unset_one_is_not(self):
        self.assertEqual(sel.resolve_selection(legacy_profile="general", role="humanitarian_analyst")[0], "general")
        self.assertEqual(sel.resolve_selection(legacy_profile=None, role="humanitarian_analyst")[0], "humanitarian")

    def test_the_secondary_is_kept_only_when_valid_and_different_and_is_never_guessed(self):
        self.assertEqual(sel.resolve_selection(primary="engineering", secondary="logistics"), ("engineering", "logistics", False))
        self.assertEqual(sel.resolve_selection(primary="engineering", secondary="engineering")[1], "")
        self.assertEqual(sel.resolve_selection(primary="engineering", secondary="nonsense")[1], "")
        self.assertEqual(sel.resolve_selection(legacy_profile="engineering", role="humanitarian_analyst")[1], "")


class TestReadAndWrite(unittest.TestCase):
    def test_the_first_read_migrates_once_and_writes_all_three_keys(self):
        store = FakeSettings(user_profile="transport")
        self.assertEqual(sel.read_selection(store), ("transport", ""))
        self.assertEqual(store.data["cartogen_ai/persona_primary"], "transport")
        self.assertEqual(store.data["cartogen_ai/persona_secondary"], "")
        self.assertEqual(store.data["cartogen_ai/user_profile"], "transport")
        writes = len(store.writes)
        self.assertEqual(sel.read_selection(store), ("transport", ""))
        self.assertEqual(len(store.writes), writes, "the second read must not write again")

    def test_a_fresh_install_with_a_finished_onboarding_gets_the_role_persona(self):
        store = FakeSettings()
        self.assertEqual(sel.read_selection(store, role="researcher"), ("research", ""))
        self.assertEqual(store.data["cartogen_ai/persona_primary"], "research")

    def test_a_fresh_install_with_nothing_is_the_generalist(self):
        self.assertEqual(sel.read_selection(FakeSettings()), ("general", ""))

    def test_a_broken_store_reads_as_the_defaults_and_never_raises(self):
        self.assertEqual(sel.read_selection(BrokenSettings()), ("general", ""))

    def test_write_mirrors_the_primary_into_the_old_key_and_cleans_bad_input(self):
        store = FakeSettings()
        self.assertEqual(sel.write_selection(store, "public_safety", "logistics"), ("public_safety", "logistics"))
        self.assertEqual(store.data["cartogen_ai/user_profile"], "public_safety")
        self.assertEqual(sel.write_selection(store, "nonsense", "also nonsense"), ("general", ""))
        self.assertEqual(store.data["cartogen_ai/persona_primary"], "general")

    def test_a_change_made_in_settings_is_not_undone_by_the_next_read(self):
        store = FakeSettings(user_profile="transport")
        sel.read_selection(store)
        sel.write_selection(store, "agriculture", "")
        self.assertEqual(sel.read_selection(store), ("agriculture", ""))


if __name__ == "__main__":
    unittest.main()
