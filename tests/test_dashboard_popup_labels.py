"""Round-2 live run 2026-11-05, row C1 (evidence t12): generate_situation_dashboard returned "generate_html_dashboard failed: 'list' object has no attribute 'get'".
Cause (read from the code, reproduced here): it passed popup_labels as a LIST aligned with popup_fields, and _resolve_popup_kwargs calls popup_labels.get(field).
Offline: folium is replaced by a recorder."""
import types
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools import export_tools, hazard_monitoring_tools

FEATURES = [{"properties": {"name": "a", "alert_level": "Red", "description": "d", "country": "YE"}}]


def fake_folium():
    seen = {}

    def popup(fields, aliases):
        seen["fields"], seen["aliases"] = fields, aliases
        return "popup"
    return types.SimpleNamespace(GeoJsonPopup=popup), seen


class TestPopupLabelsAsAList(unittest.TestCase):
    def resolve(self, fields, labels):
        module, seen = fake_folium()
        warnings = []
        popup = export_tools._resolve_popup_kwargs(module, "layer", FEATURES, fields, labels, warnings)
        return popup, seen

    def test_a_list_aligned_with_the_fields_gives_each_field_its_label(self):
        popup, seen = self.resolve(["name", "alert_level", "description", "country"], ["Event", "Alert Level", "Description", "Country"])
        self.assertEqual(popup, "popup")
        self.assertEqual(seen["aliases"], ["Event", "Alert Level", "Description", "Country"])

    def test_a_list_is_matched_by_position_even_when_a_field_is_dropped_for_being_absent(self):
        _popup, seen = self.resolve(["name", "missing", "country"], ["Event", "Gone", "Country"])
        self.assertEqual(seen["fields"], ["name", "country"])
        self.assertEqual(seen["aliases"], ["Event", "Country"])

    def test_a_short_list_labels_what_it_covers_and_humanises_the_rest(self):
        _popup, seen = self.resolve(["name", "alert_level"], ["Event"])
        self.assertEqual(seen["aliases"], ["Event", "Alert Level"])

    def test_a_dict_still_works(self):
        _popup, seen = self.resolve(["name", "country"], {"name": "Event"})
        self.assertEqual(seen["aliases"], ["Event", "Country"])

    def test_something_else_is_ignored_not_a_crash(self):
        _popup, seen = self.resolve(["name"], "Event")
        self.assertEqual(seen["aliases"], ["Name"])


class TestTheSituationDashboardPassesLabelsTheDashboardReads(unittest.TestCase):
    def test_every_layer_config_it_builds_has_dict_labels(self):
        ok = {"layer_name": "L", "detection_count": 1, "event_count": 1, "alert_count": 1}
        captured = {}

        def fake_dashboard(layers_config, **_kwargs):
            captured["layers"] = layers_config
            return {"success": True}
        with patch.object(hazard_monitoring_tools, "fetch_nasa_active_fires", return_value=dict(ok)), \
                patch.object(hazard_monitoring_tools, "fetch_nasa_eonet_events", return_value=dict(ok)), \
                patch.object(hazard_monitoring_tools, "fetch_gdacs_disaster_alerts", return_value=dict(ok)), \
                patch.object(export_tools, "generate_html_dashboard", fake_dashboard):
            hazard_monitoring_tools.generate_situation_dashboard([-20, -35, 60, 40], title="t")
        self.assertEqual(len(captured["layers"]), 3)
        for config in captured["layers"]:
            self.assertIsInstance(config["popup_labels"], dict, config["layer_name"])
            self.assertEqual(set(config["popup_labels"]), set(config["popup_fields"]))


if __name__ == "__main__":
    unittest.main()
