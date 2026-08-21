# -*- coding: utf-8 -*-
"""Tests for agent/scheduler.py and agent/tools/monitoring_tools.py -- the
recurring-monitoring feature (session-scoped QTimer schedules re-running a
saved analysis workflow and diffing per-unit results over time). Follows the
QGIS_AVAILABLE=False degrade-path convention used throughout the suite --
the QTimer/QgsSettings-backed paths can't be exercised outside real QGIS,
same as every other QGIS-facing module here."""
import unittest
from agent.scheduler import get_scheduler, WorkflowScheduler
from agent.tools.monitoring_tools import (
    _find_unit_list, _diff_unit_results, _summarize_diffs,
    run_monitoring_workflow, schedule_recurring_workflow, stop_recurring_workflow,
    list_scheduled_workflows, _ALLOWED_WORKFLOW_TOOLS,
)


class TestFindUnitList(unittest.TestCase):
    def test_finds_list_of_dicts_with_unit_key(self):
        result = {"scored_units": 2, "results": [{"unit": "A", "x": 1}, {"unit": "B", "x": 2}]}
        found = _find_unit_list(result)
        self.assertEqual(found, result["results"])

    def test_returns_none_when_no_unit_list_present(self):
        self.assertIsNone(_find_unit_list({"observed_points": 5, "projections": [1, 2, 3]}))

    def test_returns_none_for_non_dict_input(self):
        self.assertIsNone(_find_unit_list(["not", "a", "dict"]))

    def test_returns_none_for_empty_list(self):
        self.assertIsNone(_find_unit_list({"results": []}))


class TestDiffUnitResults(unittest.TestCase):
    def test_detects_appeared_disappeared_and_changed(self):
        old = {"results": [
            {"unit": "A", "severity_class": 3, "severity_score": 0.5},
            {"unit": "B", "severity_class": 2, "severity_score": 0.3},
        ]}
        new = {"results": [
            {"unit": "A", "severity_class": 5, "severity_score": 0.9},
            {"unit": "C", "severity_class": 4, "severity_score": 0.7},
        ]}
        diff = _diff_unit_results(old, new)
        self.assertEqual(diff["units_appeared"], ["C"])
        self.assertEqual(diff["units_disappeared"], ["B"])
        self.assertEqual(len(diff["units_changed"]), 1)
        self.assertEqual(diff["units_changed"][0]["unit"], "A")
        self.assertEqual(diff["units_changed"][0]["changes"]["severity_class"], {"before": 3, "after": 5})

    def test_identical_results_report_no_changes(self):
        result = {"results": [{"unit": "A", "severity_class": 3}]}
        diff = _diff_unit_results(result, result)
        self.assertEqual(diff, {"units_appeared": [], "units_disappeared": [], "units_changed": []})

    def test_returns_none_when_either_side_has_no_unit_list(self):
        self.assertIsNone(_diff_unit_results({"observed_points": 5}, {"results": [{"unit": "A"}]}))
        self.assertIsNone(_diff_unit_results({"results": [{"unit": "A"}]}, {"observed_points": 5}))

    def test_unit_field_itself_never_reported_as_a_change(self):
        old = {"results": [{"unit": "A", "x": 1}]}
        new = {"results": [{"unit": "A", "x": 1}]}
        diff = _diff_unit_results(old, new)
        self.assertEqual(diff["units_changed"], [])


class TestSummarizeDiffs(unittest.TestCase):
    def test_first_run_has_no_comparison(self):
        summary = _summarize_diffs("weekly_check", {"previous_run_at": None, "diffs_since_last_run": []})
        self.assertIn("first time", summary)

    def test_no_changes_since_last_run(self):
        summary = _summarize_diffs("weekly_check", {"previous_run_at": "2026-01-01", "diffs_since_last_run": []})
        self.assertIn("no changes", summary)

    def test_reports_counts_of_changed_appeared_disappeared(self):
        result = {
            "previous_run_at": "2026-01-01",
            "diffs_since_last_run": [{
                "units_changed": [{"unit": "A", "changes": {}}, {"unit": "B", "changes": {}}],
                "units_appeared": ["C"],
                "units_disappeared": [],
            }],
        }
        summary = _summarize_diffs("weekly_check", result)
        self.assertIn("2 unit(s) changed", summary)
        self.assertIn("1 new unit(s)", summary)
        self.assertNotIn("dropped out", summary)


class TestWorkflowScheduler(unittest.TestCase):
    def test_start_degrades_gracefully_outside_qgis(self):
        scheduler = WorkflowScheduler()
        res = scheduler.start("preset", 5, lambda name: None)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_rejects_interval_below_one_minute(self):
        # Security review finding (docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md
        # A.1): interval_minutes <= 0 was the only guard, so e.g. 0.001
        # became a ~60ms QTimer hammering the main Qt thread. Validation
        # runs before the QGIS-availability check, so this is testable
        # without a real QGIS environment.
        scheduler = WorkflowScheduler()
        res = scheduler.start("preset", 0.001, lambda name: None)
        self.assertIn("error", res)
        self.assertIn("at least 1", res["error"])

    def test_accepts_interval_at_the_floor(self):
        scheduler = WorkflowScheduler()
        res = scheduler.start("preset", 1, lambda name: None)
        # Passes interval validation and the (empty) concurrency check, so
        # the only thing left to fail on outside real QGIS is availability.
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_rejects_new_schedule_past_concurrency_cap(self):
        # Same review finding: no cap meant an unbounded number of
        # independent QTimers could be spun up. Simulate 5 already-active
        # schedules directly (start() always fails at the QGIS-availability
        # gate outside real QGIS, so it can never actually populate
        # _timers in this environment).
        scheduler = WorkflowScheduler()
        for i in range(5):
            scheduler._timers[f"preset_{i}"] = object()
        res = scheduler.start("preset_new", 5, lambda name: None)
        self.assertIn("error", res)
        self.assertIn("limit of 5", res["error"])

    def test_replacing_an_existing_schedule_is_exempt_from_the_cap(self):
        scheduler = WorkflowScheduler()
        for i in range(5):
            scheduler._timers[f"preset_{i}"] = object()
        res = scheduler.start("preset_0", 5, lambda name: None)
        # Same preset_name as an already-active schedule -- replacing it
        # doesn't grow the count, so it should reach the QGIS-availability
        # check instead of the concurrency error.
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_stop_on_unknown_preset_returns_false(self):
        scheduler = WorkflowScheduler()
        self.assertFalse(scheduler.stop("never_started"))

    def test_list_active_empty_by_default(self):
        scheduler = WorkflowScheduler()
        self.assertEqual(scheduler.list_active(), [])

    def test_get_scheduler_returns_same_instance(self):
        self.assertIs(get_scheduler(), get_scheduler())


class TestAllowedWorkflowTools(unittest.TestCase):
    def test_only_read_only_analysis_tools_allowed(self):
        # Guards against a destructive/geometry-editing tool being added to
        # the allowlist without deliberate review -- an unattended recurring
        # job must never be able to silently repeat such an operation.
        destructive_markers = ("delete", "remove", "clip", "overwrite", "write", "export", "save_project")
        for name in _ALLOWED_WORKFLOW_TOOLS:
            for marker in destructive_markers:
                self.assertNotIn(marker, name, f"'{name}' looks destructive, should not be in the recurring-workflow allowlist")


class TestMonitoringToolsDegradeOutsideQgis(unittest.TestCase):
    def test_run_monitoring_workflow(self):
        res = run_monitoring_workflow("weekly_check")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_schedule_recurring_workflow(self):
        res = schedule_recurring_workflow("weekly_check", 60)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_stop_recurring_workflow(self):
        res = stop_recurring_workflow("weekly_check")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_list_scheduled_workflows(self):
        res = list_scheduled_workflows()
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


if __name__ == "__main__":
    unittest.main()
