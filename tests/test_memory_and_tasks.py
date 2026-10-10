# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
from cartogen_ai.core.agent.memory import SpatialMemoryManager, is_project_memory_persist_enabled
from cartogen_ai.core.agent.task_manager import AgentTaskManager


class TestMemoryAndTasks(unittest.TestCase):
    def test_spatial_memory_manager(self):
        memory = SpatialMemoryManager()

        res1 = memory.store_project_note("study_area", "Damascus Region")
        self.assertTrue(res1["success"])
        self.assertEqual(memory.get_project_notes()["study_area"], "Damascus Region")

        res2 = memory.store_global_note("preferred_unit", "meters")
        self.assertTrue(res2["success"])
        self.assertEqual(memory.get_global_notes()["preferred_unit"], "meters")

        memory.log_spatial_action("buffer_analysis", "distance=500")
        actions = memory.get_action_history()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action"], "buffer_analysis")

        ctx = memory.get_formatted_memory_context()
        self.assertIn("Damascus Region", ctx)
        self.assertIn("preferred_unit", ctx)

    def test_delete_global_note_removes_single_key(self):
        memory = SpatialMemoryManager()
        memory.store_global_note("pref:units", "metric")
        memory.store_global_note("pref:basemap", "osm")

        result = memory.delete_global_note("pref:units")
        self.assertTrue(result["success"])
        self.assertTrue(result["existed"])
        notes = memory.get_global_notes()
        self.assertNotIn("pref:units", notes)
        self.assertIn("pref:basemap", notes)

    def test_delete_global_note_missing_key_reports_not_existed(self):
        memory = SpatialMemoryManager()
        result = memory.delete_global_note("no_such_key")
        self.assertTrue(result["success"])
        self.assertFalse(result["existed"])

    def test_clear_global_notes_removes_everything_across_key_prefixes(self):
        """GDPR review F1 (docs/GDPR_COMPLIANCE_REVIEW.docx, cartogen-ai-community):
        global memory previously had no bulk erasure path. This is the R4 fix --
        clear_global_notes() must remove every global note in one call, regardless
        of which key/prefix wrote it, unlike delete_global_note()'s single-key scope.

        Named distinctly from test_clear_global_notes_removes_everything below --
        both were independently added to close the same GDPR finding on two
        branches and merged into this file together; kept side by side (covering
        different key shapes) rather than deleting either, since the duplicate
        name would otherwise have silently shadowed this one (see BUG_TRACKER)."""
        memory = SpatialMemoryManager()
        memory.store_global_note("pref:units", "metric")
        memory.store_global_note("some_other_note", "written by a different tool")
        self.assertEqual(len(memory.get_global_notes()), 2)

        result = memory.clear_global_notes()
        self.assertTrue(result["success"])
        self.assertEqual(result["scope"], "global")
        self.assertEqual(memory.get_global_notes(), {})

    def test_clear_global_notes_does_not_touch_project_notes_with_prefixed_keys(self):
        """Symmetric guard with test_spatial_memory_manager's project-scope
        assertions -- clearing global memory must not clear project memory,
        mirroring clear_project_notes() not touching global memory. See the
        naming note on test_clear_global_notes_removes_everything_across_key_prefixes
        above -- kept alongside test_clear_global_notes_does_not_touch_project_notes
        rather than deleted."""
        memory = SpatialMemoryManager()
        memory.store_project_note("study_area", "Damascus Region")
        memory.store_global_note("pref:units", "metric")

        memory.clear_global_notes()
        self.assertEqual(memory.get_global_notes(), {})
        self.assertEqual(memory.get_project_notes()["study_area"], "Damascus Region")

    def test_agent_task_manager(self):
        tm = AgentTaskManager()

        plan = tm.create_plan("Flood Risk Assessment", ["Geocode Damascus", "Create 500m Buffer", "Calculate Affected Area"])
        self.assertTrue(plan["success"])
        self.assertEqual(len(tm.tasks), 3)

        p_res = tm.set_task_preview("1", "processing.run('native:buffer')", "Buffer 500m created for safety check", is_destructive=False)
        self.assertTrue(p_res["success"])
        self.assertEqual(tm.tasks[0]["status"], "PREVIEW_READY")
        self.assertEqual(tm.tasks[0]["code_snippet"], "processing.run('native:buffer')")

        u_res = tm.update_task("1", "DONE", "Coordinates (33.51, 36.29)")
        self.assertTrue(u_res["success"])
        self.assertEqual(tm.tasks[0]["status"], "DONE")
        self.assertEqual(tm.tasks[0]["result"], "Coordinates (33.51, 36.29)")

        ctx = tm.get_formatted_task_context()
        self.assertIn("Flood Risk Assessment", ctx)
        self.assertIn("DONE", ctx)

    def test_auto_advance_advances_single_open_task(self):
        tm = AgentTaskManager()
        tm.create_plan("Map Historical Sites", ["Verify coordinates", "Add point layer"])
        tm.update_task("1", "DONE", "Coordinates verified")
        # Exactly one open task (id 2) remains -- unambiguous, should auto-advance
        res = tm.auto_advance_if_unambiguous("add_point_layer succeeded")
        self.assertIsNotNone(res)
        self.assertTrue(res["success"])
        self.assertEqual(tm.tasks[1]["status"], "DONE")
        self.assertEqual(tm.tasks[1]["result"], "add_point_layer succeeded")

    def test_auto_advance_skips_when_multiple_open_tasks(self):
        tm = AgentTaskManager()
        tm.create_plan("Multi-step", ["Step A", "Step B"])
        # Both tasks still open -- ambiguous which one a tool call maps to, must not guess
        res = tm.auto_advance_if_unambiguous("something succeeded")
        self.assertIsNone(res)
        self.assertEqual(tm.tasks[0]["status"], "TODO")
        self.assertEqual(tm.tasks[1]["status"], "TODO")

    def test_auto_advance_no_op_when_no_plan(self):
        tm = AgentTaskManager()
        res = tm.auto_advance_if_unambiguous("something succeeded")
        self.assertIsNone(res)

    def test_auto_advance_stamps_tool_name(self):
        tm = AgentTaskManager()
        tm.create_plan("Map Sites", ["Add point layer"])
        tm.auto_advance_if_unambiguous("add_point_layer succeeded", tool_name="add_point_layer")
        self.assertEqual(tm.tasks[0]["tool_name"], "add_point_layer")

    def test_tasks_have_timestamps(self):
        tm = AgentTaskManager()
        tm.create_plan("Timestamped Plan", ["Step 1"])
        self.assertTrue(tm.tasks[0]["created_at"])
        self.assertTrue(tm.tasks[0]["updated_at"])
        created = tm.tasks[0]["created_at"]
        tm.update_task("1", "DONE", "finished")
        # updated_at must change on update; created_at must not
        self.assertEqual(tm.tasks[0]["created_at"], created)
        self.assertTrue(tm.tasks[0]["updated_at"])

    def test_plan_history_archives_previous_plan_on_new_plan(self):
        tm = AgentTaskManager()
        tm.create_plan("First Plan", ["Step 1"])
        tm.update_task("1", "DONE", "done")
        tm.create_plan("Second Plan", ["Step A"])

        history = tm.get_plan_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["title"], "First Plan")
        self.assertEqual(history[0]["tasks"][0]["status"], "DONE")
        # Current plan is the new one, untouched
        self.assertEqual(tm.title, "Second Plan")

    def test_plan_history_does_not_record_empty_plans(self):
        tm = AgentTaskManager()
        # No plan created yet -- nothing to archive
        tm.create_plan("Only Plan", ["Step 1"])
        self.assertEqual(tm.get_plan_history(), [])

    def test_plan_history_capped(self):
        tm = AgentTaskManager()
        for i in range(8):
            tm.create_plan(f"Plan {i}", ["Step 1"])
        history = tm.get_plan_history()
        self.assertLessEqual(len(history), 5)
        # Most recent archived plan is first
        self.assertEqual(history[0]["title"], "Plan 6")

    def test_clear_plan_archives_before_resetting(self):
        tm = AgentTaskManager()
        tm.create_plan("To Be Cleared", ["Step 1"])
        tm.clear_plan()
        history = tm.get_plan_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["title"], "To Be Cleared")
        self.assertEqual(tm.title, "")
        self.assertEqual(tm.tasks, [])

    def test_clear_project_notes_removes_stored_note(self):
        memory = SpatialMemoryManager()
        memory.store_project_note("study_area", "Damascus Region")
        self.assertIn("study_area", memory.get_project_notes())

        res = memory.clear_project_notes()
        self.assertTrue(res["success"])
        self.assertEqual(memory.get_project_notes(), {})

    def test_clear_global_notes_removes_everything(self):
        """GDPR review F1 (docs/GDPR_COMPLIANCE_REVIEW.docx): global memory needs a bulk
        erasure path, not just per-key overwrite."""
        memory = SpatialMemoryManager()
        memory.store_global_note("preferred_unit", "meters")
        memory.store_global_note("preferred_provider", "gemini")
        self.assertEqual(len(memory.get_global_notes()), 2)

        res = memory.clear_global_notes()
        self.assertTrue(res["success"])
        self.assertEqual(memory.get_global_notes(), {})

    def test_clear_global_notes_does_not_touch_project_notes(self):
        """Symmetric guard with test_spatial_memory_manager's project-scope note:
        clearing global memory must not reach into the project-scoped store."""
        memory = SpatialMemoryManager()
        memory.store_project_note("study_area", "Damascus Region")
        memory.store_global_note("preferred_unit", "meters")

        memory.clear_global_notes()

        self.assertEqual(memory.get_global_notes(), {})
        self.assertIn("study_area", memory.get_project_notes())


class TestProjectMemoryPersistenceOptIn(unittest.TestCase):
    """GDPR review finding F6 (docs/GDPR_COMPLIANCE_REVIEW.docx): project-scoped
    memory notes used to be written unconditionally to two persistent, shareable
    locations (sidecar SQLite file, QgsProject custom property) with no opt-in,
    unlike chat_persistence.py's already-opt-in chat history. Mirrors
    tests/test_chat_persistence.py's own convention for is_persist_enabled()."""

    def test_is_project_memory_persist_enabled_false_outside_qgis(self):
        self.assertFalse(is_project_memory_persist_enabled())

    @patch("cartogen_ai.core.agent.memory.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.memory.QgsSettings", create=True)
    def test_is_project_memory_persist_enabled_reads_setting(self, mock_settings_cls):
        mock_settings_cls.return_value.value.return_value = True
        self.assertTrue(is_project_memory_persist_enabled())

    @patch("cartogen_ai.core.agent.memory.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.memory.QgsSettings", create=True)
    def test_is_project_memory_persist_enabled_defaults_false(self, mock_settings_cls):
        mock_settings_cls.return_value.value.return_value = False
        self.assertFalse(is_project_memory_persist_enabled())

    @patch("cartogen_ai.core.agent.memory.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.memory.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.memory.QgsSettings", create=True)
    def test_store_project_note_skips_disk_writes_when_persist_disabled(self, mock_settings_cls, mock_project_cls):
        mock_settings_cls.return_value.value.return_value = False
        mock_project_cls.instance.return_value.fileName.return_value = ""

        memory = SpatialMemoryManager()
        result = memory.store_project_note("study_area", "Damascus Region")

        self.assertTrue(result["success"])
        self.assertFalse(result["persisted"])
        # Still readable from the in-memory cache regardless of the setting.
        self.assertEqual(memory.get_project_notes()["study_area"], "Damascus Region")
        # The persistent QgsProject custom-property write must NOT have happened.
        mock_project_cls.instance.return_value.setCustomProperty.assert_not_called()

    @patch("cartogen_ai.core.agent.memory.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.memory.set_project_custom_property", create=True)
    @patch("cartogen_ai.core.agent.memory.get_project_custom_property", create=True)
    @patch("cartogen_ai.core.agent.memory.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.memory.QgsSettings", create=True)
    def test_store_project_note_writes_property_when_persist_enabled(
        self, mock_settings_cls, mock_project_cls, mock_get_prop, mock_set_prop
    ):
        mock_settings_cls.return_value.value.return_value = True
        mock_project_cls.instance.return_value.fileName.return_value = ""
        mock_get_prop.return_value = "{}"

        memory = SpatialMemoryManager()
        result = memory.store_project_note("study_area", "Damascus Region")

        self.assertTrue(result["success"])
        self.assertTrue(result["persisted"])
        mock_set_prop.assert_called_once()

    @patch("cartogen_ai.core.agent.memory.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.memory.get_project_custom_property", create=True)
    @patch("cartogen_ai.core.agent.memory.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.memory.QgsSettings", create=True)
    def test_get_project_notes_does_not_read_property_when_persist_disabled(
        self, mock_settings_cls, mock_project_cls, mock_get_prop
    ):
        mock_settings_cls.return_value.value.return_value = False
        mock_project_cls.instance.return_value.fileName.return_value = ""

        memory = SpatialMemoryManager()
        memory.get_project_notes()

        mock_get_prop.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class TestMemoryContextForModel(unittest.TestCase):
    """2026-10-10 captured prompts: usage counters and learned-preference counts changed on almost every run and meant nothing to the
    model; they broke prompt-prefix caching. The Memory panel still shows them (for_model=False)."""

    def _memory(self):
        from cartogen_ai.core.agent.memory import SpatialMemoryManager
        m = SpatialMemoryManager()
        m.store_global_note("pref:preferred_provider", "gemini (used in 36/37 recent sessions)")
        m.store_global_note("usage:tool:update_task", "68")
        m.store_global_note("rule:1", "Never use red for water.")
        m.log_spatial_action("buffer_analysis", "{'output_name': 'b', 'distance': 500, 'layer_name': 'p'}")
        return m

    def test_the_memory_panel_still_shows_counters(self):
        ctx = self._memory().get_formatted_memory_context()
        self.assertIn("Usage Patterns", ctx)
        self.assertIn("Learned Preferences", ctx)

    def test_the_model_prompt_leaves_counters_out_but_keeps_rules_and_operations(self):
        ctx = self._memory().get_formatted_memory_context(for_model=True)
        self.assertNotIn("Usage Patterns", ctx)
        self.assertNotIn("Learned Preferences", ctx)
        self.assertNotIn("recent sessions", ctx)
        self.assertIn("Never use red for water.", ctx)
        self.assertIn("buffer_analysis", ctx)

    def test_operation_arguments_render_the_same_whatever_their_key_order(self):
        from cartogen_ai.core.agent.memory import _stable_details
        a = _stable_details("{'output_name': 'b', 'distance': 500, 'layer_name': 'p'}")
        b = _stable_details("{'layer_name': 'p', 'distance': 500, 'output_name': 'b'}")
        self.assertEqual(a, b)
        self.assertEqual(_stable_details("not a dict"), "not a dict")


class TestPlanResultInPrompt(unittest.TestCase):
    def test_a_long_task_result_is_clipped_in_the_prompt_but_kept_on_the_task(self):
        tm = AgentTaskManager()
        tm.create_plan("Plan", ["Step one"])
        task_id = tm.tasks[0]["id"]
        long_result = "x" * 2000
        tm.update_task(task_id, "DONE", long_result)
        prompt = tm.get_formatted_task_context()
        self.assertIn("more characters in the tool result", prompt)
        self.assertLess(len(prompt), 600)
        self.assertEqual(tm.tasks[0]["result"], long_result)

    def test_a_short_result_is_shown_whole(self):
        tm = AgentTaskManager()
        tm.create_plan("Plan", ["Step one"])
        tm.update_task(tm.tasks[0]["id"], "DONE", "3 layers listed")
        self.assertIn("3 layers listed", tm.get_formatted_task_context())


class TestModuleLevelHelpersAreUnconditional(unittest.TestCase):
    """PR #254's first CI run: a helper placed inside the `except ImportError:` fallback of task_manager.py was defined only when QGIS was
    missing, so every real QGIS import failed with a NameError while the offline suite (no QGIS) passed. Names the module needs in both
    environments must be defined at module level, outside any try/except."""

    def test_the_clip_helper_and_its_limit_are_top_level(self):
        import ast
        import inspect
        from cartogen_ai.core.agent import task_manager
        tree = ast.parse(inspect.getsource(task_manager))
        top_level = {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        top_level |= {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        self.assertIn("PLAN_RESULT_PROMPT_CHARS", top_level)
        self.assertIn("_clip_result", top_level)
