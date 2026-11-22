"""PLAN-011 phase A, no QGIS needed: the missing-element rule and the wording of the export report."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools import layout_export_checks as checks
from cartogen_ai.core.agent.tools.layout_export_checks import MANDATORY_LAYOUT_ELEMENTS, export_report, missing_elements


def _layer(name):
    layer = MagicMock()
    layer.name.return_value = name
    return layer


class TestMissingElements(unittest.TestCase):
    def test_all_present_reports_nothing(self):
        self.assertEqual(missing_elements(list(MANDATORY_LAYOUT_ELEMENTS)), [])

    def test_names_what_is_absent_in_a_fixed_order(self):
        self.assertEqual(missing_elements(["MAP_MAIN", "TITLE"]), ["legend", "scale bar", "north arrow"])

    def test_empty_layout_misses_everything(self):
        self.assertEqual(len(missing_elements([])), len(MANDATORY_LAYOUT_ELEMENTS))


_ALL = list(MANDATORY_LAYOUT_ELEMENTS)


class TestExportReport(unittest.TestCase):
    def test_clean_layout_with_public_layers_says_nothing(self):
        with patch("cartogen_ai.core.models.sensitivity.get_layer_sensitivity", return_value={"level": "PUBLIC"}):
            self.assertEqual(export_report([_layer("roads")], _ALL), {})

    def test_a_sensitive_layer_is_named_with_its_level(self):
        record = {"level": "SENSITIVE", "reason": "GBV cases"}
        with patch("cartogen_ai.core.models.sensitivity.get_layer_sensitivity", return_value=record):
            report = export_report([_layer("incidents")], _ALL)
        self.assertEqual(report["protected_layers"], [{"layer": "incidents", "level": "SENSITIVE"}])
        self.assertIn("'incidents' is tagged SENSITIVE (GBV cases)", report["export_warnings"][0])
        self.assertNotIn("missing_elements", report)

    def test_missing_elements_are_a_warning_and_the_file_is_not_blocked(self):
        with patch("cartogen_ai.core.models.sensitivity.get_layer_sensitivity", return_value={"level": "PUBLIC"}):
            report = export_report([_layer("roads")], ["MAP_MAIN"])
        self.assertEqual(report["missing_elements"], ["title", "legend", "scale bar", "north arrow"])
        self.assertIn("The file was written as it is", report["export_warnings"][-1])

    def test_no_layers_and_all_elements_is_empty(self):
        self.assertEqual(export_report([], _ALL), {})


def _layout(ids):
    layout = MagicMock()
    layout.customProperty.return_value = ""         # what QGIS returns for a property the layout does not have (no profile stored)
    items = []
    for item_id in ids:
        item = MagicMock()
        item.id.return_value = item_id
        items.append(item)
    layout.items.return_value = items
    return layout


_SENS = [{"layer": "incidents", "level": "SENSITIVE", "reason": "GBV"}]
_ARGS = {"layout_name": "L", "output_path": "o.pdf"}


class TestGate(unittest.TestCase):
    def _gate(self, ids, protected, purpose=None, reason=None, confirmed=False):
        with patch.object(checks, "layers_drawn", return_value=[]), patch.object(checks, "protected_in", return_value=protected):
            return checks.gate_export(_layout(ids), "export_layout", dict(_ARGS), purpose, reason, confirmed, False)

    def test_complete_layout_with_no_protected_layer_goes_ahead(self):
        self.assertIsNone(self._gate(_ALL, []))

    def test_a_protected_layer_gives_a_confirm_card_whose_apply_sets_confirmed(self):
        card = self._gate(_ALL, _SENS)
        self.assertEqual(card["status"], "PREVIEW_REQUIRED")
        self.assertTrue(card["arguments"]["confirmed"])
        self.assertIn("incidents", card["rationale"])

    def test_confirmed_skips_the_card(self):
        self.assertIsNone(self._gate(_ALL, _SENS, confirmed=True))

    def test_publication_with_problems_and_no_reason_is_refused_and_lists_them(self):
        result = self._gate(["MAP_MAIN"], _SENS, purpose="publication")
        self.assertIn("error", result)
        self.assertIn("missing title", result["error"])
        self.assertIn("incidents", result["error"])
        self.assertEqual(len(result["problems"]), 2)

    def test_a_blank_reason_does_not_count(self):
        self.assertIn("error", self._gate(["MAP_MAIN"], [], purpose="publication", reason="   "))

    def test_publication_with_a_reason_gives_a_card_that_shows_the_reason(self):
        card = self._gate(["MAP_MAIN"], [], purpose="publication", reason="internal copy")
        self.assertEqual(card["status"], "PREVIEW_REQUIRED")
        self.assertIn("internal copy", card["rationale"])
        self.assertIn("missing", card["rationale"])

    def test_publication_of_a_clean_layout_needs_nothing(self):
        self.assertIsNone(self._gate(_ALL, [], purpose="publication"))

    def test_a_draft_with_missing_elements_is_not_gated(self):
        self.assertIsNone(self._gate(["MAP_MAIN"], []))


def _fake_layer(name, ident):
    layer = _layer(name)
    layer.id.return_value = ident
    return layer


_ATLAS_ARGS = {"layout_name": "L", "coverage_layer_name": "districts"}


class TestAtlasGate(unittest.TestCase):
    def test_a_protected_coverage_layer_gives_a_card_naming_it(self):
        coverage = _fake_layer("districts", "d1")
        with patch.object(checks, "layers_drawn", return_value=[]), \
                patch.object(checks, "protected_in", side_effect=lambda layers: [{"layer": layer.name(), "level": "SENSITIVE", "reason": None} for layer in layers]):
            card = checks.atlas_gate(_layout(_ALL), coverage, dict(_ATLAS_ARGS), False)
        self.assertEqual(card["tool_name"], "export_layout_atlas")
        self.assertTrue(card["arguments"]["confirmed"])
        self.assertIn("districts", card["rationale"])

    def test_confirmed_or_nothing_protected_goes_ahead(self):
        coverage = _fake_layer("districts", "d1")
        with patch.object(checks, "layers_drawn", return_value=[]), patch.object(checks, "protected_in", return_value=[]):
            self.assertIsNone(checks.atlas_gate(_layout(_ALL), coverage, dict(_ATLAS_ARGS), False))
        with patch.object(checks, "layers_drawn", return_value=[]), patch.object(checks, "protected_in", return_value=_SENS):
            self.assertIsNone(checks.atlas_gate(_layout(_ALL), coverage, dict(_ATLAS_ARGS), True))

    def test_the_coverage_layer_is_not_counted_twice(self):
        both = _fake_layer("districts", "d1")
        seen = []
        with patch.object(checks, "layers_drawn", return_value=[both]), patch.object(checks, "protected_in", side_effect=lambda layers: seen.append(layers) or []):
            checks.atlas_gate(_layout(_ALL), both, dict(_ATLAS_ARGS), False)
        self.assertEqual(len(seen[0]), 1)


class TestPublicationRecordAndBuildTimePreview(unittest.TestCase):
    def test_record_is_written_beside_the_file(self):
        import json
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "map.pdf")
            path = checks.write_publication_record(target, "L", ["missing legend"], "review copy")
            self.assertEqual(path, target + ".publication.json")
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        self.assertEqual((data["reason_given"], data["problems_at_export"]), ("review copy", ["missing legend"]))

    def test_unwritable_location_returns_none_instead_of_raising(self):
        self.assertIsNone(checks.write_publication_record("/nonexistent_dir_xyz/map.pdf", "L", [], "r"))

    def test_no_output_path_means_no_card(self):
        self.assertIsNone(checks.build_time_preview("create_print_layout", {}, ""))

    def test_protected_layer_ticked_gives_a_card_only_when_a_file_is_to_be_written(self):
        with patch.object(checks, "checked_project_layers", return_value=[]), patch.object(checks, "protected_in", return_value=_SENS):
            self.assertEqual(checks.build_time_preview("create_print_layout", {"title": "t"}, "o.pdf")["status"], "PREVIEW_REQUIRED")
            self.assertIsNone(checks.build_time_preview("create_print_layout", {"title": "t"}, ""))


class TestExportStatus(unittest.TestCase):
    """LR-3 (2026-11-20 live run, rows C25 and C26): a request for a PDF ended with a layout in the project and a reply with no word about the missing file."""

    def test_no_output_path_says_that_no_file_was_written_and_how_to_get_one(self):
        from cartogen_ai.core.agent.tools.layout_tools import export_status
        for empty in ("", None):
            status = export_status(empty)
            self.assertIs(status["exported"], False)
            self.assertIn("No file was written", status["export_note"])
            self.assertIn("output_path", status["export_note"])

    def test_an_output_path_is_reported_as_exported_with_no_note(self):
        from cartogen_ai.core.agent.tools.layout_tools import export_status
        self.assertEqual(export_status("C:/out/bulletin.pdf"), {"exported": True})


class TestProtectionControlsFailClosed(unittest.TestCase):
    """Owner decision 2026-11-22 (DEF-8 review): when a protection lookup FAILS, the control applies instead of silently not applying. Each failure
    is also logged, with the error class only."""

    def test_a_sensitivity_that_cannot_be_read_counts_as_protected_and_is_logged(self):
        layer = _layer("clinics")
        with patch("cartogen_ai.core.agent.protection.effective_sensitivity", side_effect=RuntimeError("boom")), \
                patch.object(checks, "log_event") as log:
            found = checks.protected_in([layer], all_layers=[])
        self.assertEqual([(f["layer"], f["level"]) for f in found], [("clinics", "SENSITIVE")])
        self.assertIn("could not be read", found[0]["reason"])
        self.assertEqual(log.call_args.args[0], "sensitivity_read_failed")
        self.assertEqual(log.call_args.kwargs["error_class"], "RuntimeError")

    def test_a_layer_that_reads_fine_is_still_judged_by_its_own_tag(self):
        layer = _layer("clinics")
        with patch("cartogen_ai.core.agent.protection.effective_sensitivity", return_value={"level": "PUBLIC"}):
            self.assertEqual(checks.protected_in([layer], all_layers=[]), [])

    def test_a_stored_profile_that_cannot_be_read_is_marked_not_treated_as_no_profile(self):
        broken = MagicMock()
        broken.customProperty.side_effect = RuntimeError("boom")
        notjson = MagicMock()
        notjson.customProperty.return_value = "{not json"
        notobject = MagicMock()
        notobject.customProperty.return_value = "[1, 2]"
        for layout in (broken, notjson, notobject):
            with patch.object(checks, "log_event") as log:
                self.assertEqual(checks.profile_of(layout), {checks.PROFILE_UNREADABLE: True})
            self.assertEqual(log.call_args.args[0], "profile_read_failed")

    def test_a_layout_with_no_profile_is_still_no_profile(self):
        layout = MagicMock()
        layout.customProperty.return_value = ""
        self.assertEqual(checks.profile_of(layout), {})

    def test_an_unreadable_profile_blocks_publication_until_the_user_gives_a_reason(self):
        layout = _layout(_ALL)
        layout.customProperty.return_value = "{not json"
        with patch.object(checks, "protected_in", return_value=[]), patch.object(checks, "log_event"):
            refused = checks.gate_export(layout, "export_layout", dict(_ARGS), "publication", None, False, False)
            card = checks.gate_export(layout, "export_layout", dict(_ARGS), "publication", "the user said go", False, False)
        self.assertIn("could not be read", refused["error"])
        self.assertEqual(card["status"], "PREVIEW_REQUIRED")          # with a user-given reason it goes to the confirm card, like any other problem

    def test_an_unreadable_profile_does_not_stop_an_ordinary_export(self):
        layout = _layout(_ALL)
        layout.customProperty.return_value = "{not json"
        with patch.object(checks, "protected_in", return_value=[]), patch.object(checks, "log_event"):
            self.assertIsNone(checks.gate_export(layout, "export_layout", dict(_ARGS), None, None, False, False))

    def test_a_failed_model_view_lookup_withholds_the_field_names_and_is_logged(self):
        from cartogen_ai.core.agent.tools import vector_tools
        entry = {"name": "clinics", "fields": ["name", "patient_id"], "feature_count": 7}
        with patch("cartogen_ai.core.models.model_view.apply_to_layer_entry", side_effect=RuntimeError("boom")), \
                patch.object(vector_tools, "log_event") as log:
            seen = vector_tools._model_view_entry(entry, MagicMock())
        self.assertEqual(seen["fields"], [])
        self.assertIs(seen["schema_hidden"], True)
        self.assertIn("could not be read", seen["schema_note"])
        self.assertEqual(seen["name"], "clinics")                    # only the schema is withheld
        self.assertEqual(entry["fields"], ["name", "patient_id"])    # the caller's own entry is not modified
        self.assertEqual(log.call_args.kwargs["tool"], "model_view_entry")

    def test_a_model_view_entry_that_is_not_a_dict_comes_back_as_it_was(self):
        from cartogen_ai.core.agent.tools import vector_tools
        self.assertEqual(vector_tools._entry_with_schema_withheld("text"), "text")

    def test_the_log_carries_the_error_class_only(self):
        layout = MagicMock()
        layout.customProperty.side_effect = RuntimeError("secret path C:/Users/x")
        with patch.object(checks, "log_event") as log:
            checks.profile_of(layout)
        self.assertNotIn("secret", repr(log.call_args))


if __name__ == "__main__":
    unittest.main()
