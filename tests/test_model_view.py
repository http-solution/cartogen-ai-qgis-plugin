# -*- coding: utf-8 -*-
"""rc7 smoke test F21: field names of a SENSITIVE layer reached the cloud model through get_layers / the map
context, although the egress gate was protecting the layer's data. models/model_view.py is the one rule for it."""
import unittest

from cartogen_ai.core.models import egress_gate as eg
from cartogen_ai.core.models import model_view as mv

ENTRY = {"name": "Health Facilities", "type": "VectorLayer", "crs": "EPSG:4326", "feature_count": 3369,
         "fields": ["fid", "osm_id", "fclass", "name"]}


class TestMasksSchema(unittest.TestCase):
    def setUp(self):
        self.addCleanup(mv.set_policy_provider, None)

    def test_enforce_cloud_protected_is_masked(self):
        for level in ("RESTRICTED", "SENSITIVE"):
            self.assertTrue(mv.masks_schema(level, (eg.MODE_ENFORCE, False, False)), level)

    def test_open_levels_are_never_masked(self):
        for level in ("PUBLIC", "INTERNAL"):
            self.assertFalse(mv.masks_schema(level, (eg.MODE_ENFORCE, False, True)), level)

    def test_untagged_is_masked_only_in_strict_mode(self):
        self.assertFalse(mv.masks_schema(None, (eg.MODE_ENFORCE, False, False)))
        self.assertTrue(mv.masks_schema(None, (eg.MODE_ENFORCE, False, True)))

    def test_a_local_provider_sees_everything(self):
        self.assertFalse(mv.masks_schema("SENSITIVE", (eg.MODE_ENFORCE, True, True)))

    def test_off_and_warn_modes_do_not_mask(self):
        self.assertFalse(mv.masks_schema("SENSITIVE", (eg.MODE_OFF, False, True)))
        self.assertFalse(mv.masks_schema("SENSITIVE", (eg.MODE_WARN, False, True)))

    def test_no_provider_registered_means_no_masking(self):
        mv.set_policy_provider(None)
        self.assertFalse(mv.masks_schema("SENSITIVE"))

    def test_a_failing_policy_provider_hides_rather_than_leaks(self):
        def boom():
            raise RuntimeError("settings unreadable")
        mv.set_policy_provider(boom)
        self.assertTrue(mv.masks_schema("SENSITIVE"))
        self.assertTrue(mv.masks_schema("PUBLIC") is False)      # an open layer stays visible

    def test_the_registered_provider_is_used(self):
        mv.set_policy_provider(lambda: (eg.MODE_ENFORCE, False, False))
        self.assertTrue(mv.masks_schema("SENSITIVE"))
        mv.set_policy_provider(lambda: (eg.MODE_ENFORCE, True, False))
        self.assertFalse(mv.masks_schema("SENSITIVE"))


class TestApplyToLayerEntry(unittest.TestCase):
    POLICY = (eg.MODE_ENFORCE, False, False)

    def test_field_names_are_withheld_but_name_type_crs_and_count_stay(self):
        out = mv.apply_to_layer_entry(ENTRY, "SENSITIVE", self.POLICY)
        self.assertEqual(out["fields"], [])
        self.assertTrue(out["schema_hidden"])
        self.assertEqual(out["name"], "Health Facilities")
        self.assertEqual(out["feature_count"], 3369)
        self.assertEqual(out["crs"], "EPSG:4326")

    def test_the_input_is_not_mutated(self):
        mv.apply_to_layer_entry(ENTRY, "SENSITIVE", self.POLICY)
        self.assertEqual(ENTRY["fields"], ["fid", "osm_id", "fclass", "name"])

    def test_an_open_layer_is_returned_unchanged(self):
        self.assertIs(mv.apply_to_layer_entry(ENTRY, "PUBLIC", self.POLICY), ENTRY)

    def test_a_raster_entry_without_fields_is_still_marked(self):
        out = mv.apply_to_layer_entry({"name": "pop", "type": "RasterLayer"}, "SENSITIVE", self.POLICY)
        self.assertTrue(out["schema_hidden"])
        self.assertNotIn("fields", out)

    def test_a_non_dict_is_passed_through(self):
        self.assertEqual(mv.apply_to_layer_entry("x", "SENSITIVE", self.POLICY), "x")


class TestPromptShowsWithheldFields(unittest.TestCase):
    def test_the_prompt_says_fields_are_withheld_and_lists_no_names(self):
        from cartogen_ai.core.agent import prompts
        ctx = {"project_title": "t", "canvas_crs": "EPSG:4326", "active_layer": "None", "layer_count": 1,
               "layers": [dict(ENTRY, fields=[], schema_hidden=True)], "truncated": False}
        text = prompts._format_map_context(ctx)
        self.assertIn("withheld: protected layer", text)
        self.assertNotIn("osm_id", text)
        self.assertIn("3369 features", text)

    def test_an_open_layer_still_lists_its_fields(self):
        from cartogen_ai.core.agent import prompts
        ctx = {"project_title": "t", "canvas_crs": "EPSG:4326", "active_layer": "None", "layer_count": 1,
               "layers": [ENTRY], "truncated": False}
        self.assertIn("osm_id", prompts._format_map_context(ctx))


if __name__ == "__main__":
    unittest.main()
