# -*- coding: utf-8 -*-
import unittest
from cartogen_ai.core.agent.memory import SpatialMemoryManager
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

    def test_clear_global_notes_removes_everything(self):
        """GDPR review F1 (docs/GDPR_COMPLIANCE_REVIEW.docx, cartogen-ai-community):
        global memory previously had no bulk erasure path. This is the R4 fix --
        clear_global_notes() must remove every global note in one call, regardless
        of which key/prefix wrote it, unlike delete_global_note()'s single-key scope."""
        memory = SpatialMemoryManager()
        memory.store_global_note("pref:units", "metric")
        memory.store_global_note("some_other_note", "written by a different tool")
        self.assertEqual(len(memory.get_global_notes()), 2)

        result = memory.clear_global_notes()
        self.assertTrue(result["success"])
        self.assertEqual(result["scope"], "global")
        self.assertEqual(memory.get_global_notes(), {})

    def test_clear_global_notes_does_not_touch_project_notes(self):
        """Symmetric guard with test_spatial_memory_manager's project-scope
        assertions -- clearing global memory must not clear project memory,
        mirroring clear_project_notes() not touching global memory."""
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


if __name__ == "__main__":
    unittest.main()
