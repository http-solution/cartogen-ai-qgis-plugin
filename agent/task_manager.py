# -*- coding: utf-8 -*-
"""
Agent Task Manager for Cartogen AI.
Handles multi-step spatial workflow planning, task status tracking,
preview-before-apply safety confirmation, and action explainability.
"""

import datetime
from typing import List, Dict, Optional

try:
    from qgis.PyQt.QtCore import QObject, pyqtSignal
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    class QObject:
        pass

MAX_PLAN_HISTORY = 5


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class AgentTaskManager(QObject):
    """Manages active task decomposition, preview safety, and step-by-step progress tracking."""

    if QT_AVAILABLE:
        plan_updated = pyqtSignal(dict)
        task_changed = pyqtSignal(str, str, str)  # task_id, status, result

    def __init__(self):
        if QT_AVAILABLE:
            super().__init__()
        self.title = ""
        self.tasks: List[Dict] = []
        self._next_id = 1
        self.plan_history: List[Dict] = []

    def create_plan(self, title: str, task_descriptions: List[str]) -> dict:
        """Creates a new multi-step execution plan. Archives the previous plan into
        plan_history first (if it had any tasks), so starting a new plan doesn't
        silently erase what the last one accomplished."""
        if self.tasks:
            self.plan_history.insert(0, {
                "title": self.title,
                "tasks": [dict(t) for t in self.tasks],
                "completed_at": _now_iso(),
            })
            self.plan_history = self.plan_history[:MAX_PLAN_HISTORY]

        self.title = title
        self.tasks = []
        self._next_id = 1

        now = _now_iso()
        for desc in task_descriptions:
            task_item = {
                "id": str(self._next_id),
                "description": desc,
                "status": "TODO",  # TODO, IN_PROGRESS, PREVIEW_READY, CONFIRMED, DONE, FAILED
                "result": "",
                "rationale": "",
                "code_snippet": "",
                "is_destructive": False,
                "tool_name": "",
                "created_at": now,
                "updated_at": now,
            }
            self.tasks.append(task_item)
            self._next_id += 1

        plan_data = self.get_plan()
        if QT_AVAILABLE:
            self.plan_updated.emit(plan_data)
        return {"success": True, "title": self.title, "task_count": len(self.tasks), "plan": plan_data}

    def set_task_preview(self, task_id: str, code_snippet: str, rationale: str = "", is_destructive: bool = False) -> dict:
        """Sets preview state for a task requiring user confirmation before destructive execution."""
        for task in self.tasks:
            if task["id"] == str(task_id):
                task["status"] = "PREVIEW_READY"
                task["code_snippet"] = code_snippet
                task["rationale"] = rationale
                task["is_destructive"] = is_destructive
                task["updated_at"] = _now_iso()
                if QT_AVAILABLE:
                    self.task_changed.emit(task["id"], task["status"], "Preview Ready")
                    self.plan_updated.emit(self.get_plan())
                return {"success": True, "task": task}
        return {"error": f"Task ID '{task_id}' not found."}

    def update_task(self, task_id: str, status: str, result: str = "", rationale: str = "", code_snippet: str = "", tool_name: str = "") -> dict:
        """Updates status of a specific task in the plan."""
        status_upper = status.upper()
        valid_statuses = ("TODO", "IN_PROGRESS", "PREVIEW_READY", "CONFIRMED", "DONE", "FAILED")
        if status_upper not in valid_statuses:
            return {"error": f"Invalid status '{status}'. Must be one of {valid_statuses}."}

        for task in self.tasks:
            if task["id"] == str(task_id):
                task["status"] = status_upper
                if result:
                    task["result"] = result
                if rationale:
                    task["rationale"] = rationale
                if code_snippet:
                    task["code_snippet"] = code_snippet
                if tool_name:
                    task["tool_name"] = tool_name
                task["updated_at"] = _now_iso()
                if QT_AVAILABLE:
                    self.task_changed.emit(task["id"], task["status"], task["result"])
                    self.plan_updated.emit(self.get_plan())
                return {"success": True, "task": task}

        return {"error": f"Task ID '{task_id}' not found."}

    def get_plan(self) -> dict:
        """Returns full copy of current plan."""
        return {
            "title": self.title,
            "tasks": [dict(t) for t in self.tasks],
        }

    def get_plan_history(self) -> list:
        """Returns the archived plan snapshots, most recent first."""
        return [dict(p) for p in self.plan_history]

    def auto_advance_if_unambiguous(self, result_summary: str, tool_name: str = "") -> Optional[dict]:
        """Best-effort safety net for when the model creates a plan but then forgets to call
        update_task after actually doing the work (a real, observed failure mode -- a plan can
        sit frozen at TODO forever even though the underlying tool calls genuinely succeeded).
        Only advances a task when there's exactly ONE still-open (TODO/IN_PROGRESS) task, since
        mapping an arbitrary successful tool call to one of several open tasks would often guess
        wrong. Safe to call after every successful tool execution; a no-op most of the time."""
        open_tasks = [t for t in self.tasks if t["status"] in ("TODO", "IN_PROGRESS")]
        if len(open_tasks) != 1:
            return None
        return self.update_task(open_tasks[0]["id"], "DONE", result_summary, tool_name=tool_name)

    def clear_plan(self):
        """Resets active plan (archiving it into plan_history first, same as create_plan)."""
        if self.tasks:
            self.plan_history.insert(0, {
                "title": self.title,
                "tasks": [dict(t) for t in self.tasks],
                "completed_at": _now_iso(),
            })
            self.plan_history = self.plan_history[:MAX_PLAN_HISTORY]
        self.title = ""
        self.tasks = []
        self._next_id = 1
        if QT_AVAILABLE:
            self.plan_updated.emit(self.get_plan())

    def get_formatted_task_context(self) -> str:
        """Formats current task list for system prompt context injection."""
        if not self.tasks:
            return ""

        lines = [f"## 📋 ACTIVE TASK PLAN: {self.title}"]
        for task in self.tasks:
            icon = "⚪"
            if task["status"] == "IN_PROGRESS":
                icon = "🟡"
            elif task["status"] == "PREVIEW_READY":
                icon = "🔍"
            elif task["status"] == "DONE":
                icon = "🟢"
            elif task["status"] == "FAILED":
                icon = "🔴"
            
            res_str = f" → {task['result']}" if task["result"] else ""
            lines.append(f"{task['id']}. [{icon} {task['status']}] {task['description']}{res_str}")

        lines.append("\nRULE: Use `update_task` tool to update status as you execute steps!")
        return "\n".join(lines)
