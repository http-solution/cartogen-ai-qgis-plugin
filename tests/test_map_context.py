# -*- coding: utf-8 -*-
import unittest
from cartogen_ai.core.agent.map_context import (
    get_map_context_summary, estimate_layer_context_tokens, filter_layers_by_selection,
)
from cartogen_ai.core.agent.prompts import build_system_prompt, _format_map_context


class TestMapContext(unittest.TestCase):
    def test_returns_empty_dict_outside_qgis(self):
        # Test environment has no qgis.core -- QGIS_AVAILABLE is False.
        self.assertEqual(get_map_context_summary(), {})


class TestEstimateLayerContextTokens(unittest.TestCase):
    def test_empty_list_is_zero(self):
        self.assertEqual(estimate_layer_context_tokens([]), 0)
        self.assertEqual(estimate_layer_context_tokens(None), 0)

    def test_more_layers_estimate_more_tokens(self):
        one = [{"name": "A", "type": "Vector", "crs": "EPSG:4326", "fields": ["a", "b"]}]
        two = one + [{"name": "B", "type": "Vector", "crs": "EPSG:4326", "fields": ["a", "b", "c"]}]
        self.assertGreater(estimate_layer_context_tokens(two), estimate_layer_context_tokens(one))

    def test_never_returns_zero_for_a_real_layer(self):
        self.assertGreaterEqual(estimate_layer_context_tokens([{"name": "X"}]), 1)


class TestFilterLayersBySelection(unittest.TestCase):
    """Broadsheet redesign Phase 3 (mockup 1l, layer context picker): the picker is
    opt-out, not opt-in -- a user who never opens it must see today's unchanged
    behavior (every loaded layer's schema sent), and the filter must never mutate
    get_map_context_summary()'s own return value."""

    def _ctx(self):
        return {
            "project_title": "P", "layer_count": 2,
            "layers": [{"name": "Health Facilities"}, {"name": "Beneficiary Registry"}],
        }

    def test_empty_selection_returns_context_unchanged(self):
        ctx = self._ctx()
        result = filter_layers_by_selection(ctx, {})
        self.assertIs(result, ctx)

    def test_none_map_ctx_returns_none(self):
        self.assertIsNone(filter_layers_by_selection(None, {"X": True}))

    def test_a_layer_explicitly_unchecked_is_excluded(self):
        ctx = self._ctx()
        result = filter_layers_by_selection(ctx, {"Beneficiary Registry": False})
        names = [layer["name"] for layer in result["layers"]]
        self.assertEqual(names, ["Health Facilities"])
        self.assertEqual(result["layer_count"], 1)

    def test_a_layer_with_no_entry_at_all_is_kept(self):
        # The picker was opened and ONE layer was explicitly unchecked -- a layer added
        # to the project since (never seen by the picker) has no entry in the selection
        # dict at all, and must still be sent, not silently dropped.
        ctx = self._ctx()
        result = filter_layers_by_selection(ctx, {"Beneficiary Registry": False})
        names = [layer["name"] for layer in result["layers"]]
        self.assertIn("Health Facilities", names)

    def test_original_context_object_is_never_mutated(self):
        ctx = self._ctx()
        original_layers = ctx["layers"]
        filter_layers_by_selection(ctx, {"Beneficiary Registry": False})
        self.assertIs(ctx["layers"], original_layers)
        self.assertEqual(len(ctx["layers"]), 2)

    def test_a_layer_explicitly_checked_true_is_kept(self):
        ctx = self._ctx()
        result = filter_layers_by_selection(ctx, {"Health Facilities": True, "Beneficiary Registry": False})
        self.assertEqual(len(result["layers"]), 1)


class TestFormatMapContext(unittest.TestCase):
    def test_empty_context_produces_no_section(self):
        self.assertEqual(_format_map_context({}), "")
        self.assertEqual(_format_map_context(None), "")

    def test_formats_layers_and_metadata(self):
        ctx = {
            "project_title": "Jordan Analysis",
            "canvas_crs": "EPSG:4326",
            "active_layer": "Jordan_Governorates",
            "layer_count": 1,
            "layers": [
                {"name": "Jordan_Governorates", "type": "VectorLayer", "crs": "EPSG:4326",
                 "feature_count": 12, "fields": ["shapeName", "Population"]},
            ],
            "truncated": False,
        }
        text = _format_map_context(ctx)
        self.assertIn("Jordan Analysis", text)
        self.assertIn("Jordan_Governorates", text)
        self.assertIn("shapeName", text)
        self.assertIn("12 features", text)

    def test_build_system_prompt_includes_map_context_section(self):
        ctx = {"project_title": "Test", "canvas_crs": "EPSG:4326", "active_layer": "None", "layers": []}
        prompt = build_system_prompt(map_context=ctx)
        self.assertIn("CURRENT MAP CONTEXT", prompt)

    def test_build_system_prompt_omits_section_when_no_context(self):
        # Rule #4 in the base prompt references "CURRENT MAP CONTEXT" by name
        # regardless of whether the section is rendered -- check for the
        # actual section header, not just the substring.
        prompt = build_system_prompt()
        self.assertNotIn("## 🗺️ CURRENT MAP CONTEXT", prompt)


if __name__ == "__main__":
    unittest.main()
