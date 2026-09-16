# -*- coding: utf-8 -*-
"""Tests for agent/task_manager.py -- the Activity tab's plan/task state.

No QGIS needed: AgentTaskManager degrades to plain Python when qgis.PyQt isn't
importable (QT_AVAILABLE guard just skips signal emits)."""
import unittest

from cartogen_ai.core.agent.task_manager import AgentTaskManager


class TestAddTask(unittest.TestCase):
    """2026-09-16 live bug: agent.py's PREVIEW_REQUIRED handling used to only start a
    fresh plan when the task list was completely empty, otherwise reusing tasks[0] of
    whatever plan was already active -- silently overwriting an unrelated task. add_task()
    is the fix's building block: append one task without touching what's already there."""

    def test_appends_without_archiving_the_existing_plan(self):
        tm = AgentTaskManager()
        tm.create_plan("Health facilities", ["Compile facilities", "Style layer"])
        tm.update_task("1", "DONE", "Facilities compiled.")

        res = tm.add_task("Preview field_calculator operation")

        self.assertTrue(res["success"])
        self.assertEqual(tm.title, "Health facilities", "the original plan must be untouched")
        self.assertEqual(len(tm.tasks), 3)
        self.assertEqual(tm.tasks[0]["status"], "DONE")
        self.assertEqual(tm.tasks[0]["result"], "Facilities compiled.",
                          "the original, already-DONE task must not be overwritten")
        self.assertEqual(tm.plan_history, [], "add_task must not archive anything")

    def test_new_task_gets_the_next_sequential_id(self):
        tm = AgentTaskManager()
        tm.create_plan("Plan", ["First", "Second"])
        res = tm.add_task("Third")
        self.assertEqual(res["task"]["id"], "3")

    def test_works_on_a_completely_empty_task_manager(self):
        tm = AgentTaskManager()
        res = tm.add_task("Solo task")
        self.assertTrue(res["success"])
        self.assertEqual(len(tm.tasks), 1)
        self.assertEqual(res["task"]["id"], "1")

    def test_returned_task_is_the_same_object_stored_in_tasks(self):
        # agent.py's PREVIEW_REQUIRED handling mutates the dict add_task() returns
        # (setting pending_tool/pending_args) and expects that to be reflected in
        # tm.tasks -- this must be a reference, not a copy.
        tm = AgentTaskManager()
        res = tm.add_task("Preview op")
        res["task"]["pending_tool"] = "field_calculator"
        self.assertEqual(tm.tasks[0]["pending_tool"], "field_calculator")


class TestFormattedTaskContextSurfacesPendingConfirmation(unittest.TestCase):
    """2026-09-16 live bug: a user confirmed a destructive-action gate by replying
    "Confirm" in chat; the model had no structured way to know which tool+arguments
    that confirmation was for (pending_tool/pending_args lived on the task dict but
    were never included in the prompt context), and fabricated a "confirmed" narrative
    without ever re-calling the tool. This is the defense-in-depth backstop."""

    def test_a_task_with_no_pending_tool_gets_no_extra_line(self):
        tm = AgentTaskManager()
        tm.create_plan("Plan", ["Ordinary task"])
        ctx = tm.get_formatted_task_context()
        self.assertNotIn("Awaiting confirmation", ctx)

    def test_a_task_with_a_pending_tool_names_it_and_its_arguments(self):
        tm = AgentTaskManager()
        tm.create_plan("Plan", ["Preview field_calculator operation"])
        tm.tasks[0]["pending_tool"] = "field_calculator"
        tm.tasks[0]["pending_args"] = {"layer_name": "GDACS Disaster Alerts - Yemen",
                                        "new_field": "severity"}
        ctx = tm.get_formatted_task_context()
        self.assertIn("Awaiting confirmation", ctx)
        self.assertIn("field_calculator", ctx)
        self.assertIn("GDACS Disaster Alerts - Yemen", ctx)
        self.assertIn("do not describe it as done without actually calling it", ctx)


if __name__ == "__main__":
    unittest.main()
