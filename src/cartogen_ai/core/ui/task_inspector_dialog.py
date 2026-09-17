# -*- coding: utf-8 -*-
"""Task inspector dialog -- Broadsheet redesign Phase 1. Rehouses the old Activity tab's
always-visible "01 Task Inspector and Preview Safety" box (tasks_tab_widget.py, deleted
in this same change) as a per-task dialog opened from a click on the in-chat plan card's task rows
(chat_tab_widget.py's _on_plan_task_clicked), instead of a box that stayed on screen (mostly empty, "Select a task to inspect details")
even when nothing was selected -- a real 2026-09-16 audit finding about the old tab's
wasted, always-visible chrome.

Confirm/Cancel route through chat_tab_widget.py's _resolve_pending_confirmation -- the
SAME deterministic agent._real_execute_tool(pending_tool, pending_args,
user_confirmed=True) path a plain-text "Confirm" chat reply and the inline safety-gate
card's links already use (see this session's earlier confirmation-gate fix and Phase 2's
render_safety_gate_html). The old tab's _confirm_selected_task/_cancel_selected_task
duplicated that same logic a third time -- reusing the one shared implementation here
retires that duplication rather than adding a fourth copy."""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QApplication,
)


class CartogenAiTaskInspectorDialog(QDialog):
    def __init__(self, dock, task, read_only=False, parent=None):
        super().__init__(parent)
        self._dock = dock
        self._task = task
        self._read_only = read_only
        self.setWindowTitle(f"Task {task.get('id', '?')}")
        self._current_code_snippet = task.get("code_snippet") or ""
        self.init_ui()

    @property
    def _agent_provider(self):
        return self._dock._agent_provider

    def init_ui(self):
        layout = QVBoxLayout(self)
        task = self._task
        status = task.get("status", "TODO")

        desc = QLabel(f"<b>{task.get('description', '')}</b>")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        rat = task.get("rationale") or "(No rationale provided for this step)"
        rationale_label = QLabel(f"<b>Rationale:</b> {rat}")
        rationale_label.setWordWrap(True)
        layout.addWidget(rationale_label)

        snippet = task.get("code_snippet") or "# No code snippet recorded for this step"
        self.code_inspector = QTextBrowser()
        self.code_inspector.setMaximumHeight(120)
        self.code_inspector.setText(f"<code>{snippet}</code>")
        layout.addWidget(self.code_inspector)

        self.copy_snippet_btn = QPushButton("📋 Copy Snippet")
        self.copy_snippet_btn.setObjectName("secondaryButton")
        self.copy_snippet_btn.setEnabled(bool(self._current_code_snippet))
        self.copy_snippet_btn.clicked.connect(self._copy_code_snippet)
        layout.addWidget(self.copy_snippet_btn)

        button_row = QHBoxLayout()
        self.confirm_btn = QPushButton("✅ Confirm and Apply Edit")
        self.confirm_btn.setObjectName("successButton")
        self.confirm_btn.setEnabled(not self._read_only and status == "PREVIEW_READY")
        self.confirm_btn.clicked.connect(self._confirm)

        self.cancel_task_btn = QPushButton("❌ Cancel")
        self.cancel_task_btn.setObjectName("secondaryButton")
        self.cancel_task_btn.setEnabled(not self._read_only and status == "PREVIEW_READY")
        self.cancel_task_btn.clicked.connect(self._cancel)

        self.retry_task_btn = QPushButton("🔁 Retry")
        self.retry_task_btn.setObjectName("secondaryButton")
        self.retry_task_btn.setEnabled(not self._read_only and status == "FAILED")
        self.retry_task_btn.clicked.connect(self._retry)

        self.edit_task_btn = QPushButton("✏️ Edit and Resend")
        self.edit_task_btn.setObjectName("secondaryButton")
        self.edit_task_btn.setEnabled(not self._read_only)
        self.edit_task_btn.clicked.connect(self._edit_and_resend)

        button_row.addWidget(self.retry_task_btn)
        button_row.addWidget(self.edit_task_btn)
        button_row.addWidget(self.cancel_task_btn)
        layout.addLayout(button_row)
        layout.addWidget(self.confirm_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

    def _copy_code_snippet(self):
        if not self._current_code_snippet:
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._current_code_snippet)
            self._dock.statusSignal.emit("Code snippet copied to clipboard.")

    def _confirm(self):
        agent = self._agent_provider() if self._agent_provider else None
        if agent is None or not hasattr(agent, "task_manager"):
            return
        self._dock.chat_tab_widget._resolve_pending_confirmation(agent, self._task, confirmed=True)
        self.accept()

    def _cancel(self):
        agent = self._agent_provider() if self._agent_provider else None
        if agent is None or not hasattr(agent, "task_manager"):
            return
        self._dock.chat_tab_widget._resolve_pending_confirmation(agent, self._task, confirmed=False)
        self.accept()

    def _retry(self):
        task_id = self._task.get("id")
        desc = self._task.get("description", "")
        result = self._task.get("result", "")
        prompt = (
            f"Retry task {task_id}: {desc}. It previously failed with: {result}"
            if result else f"Retry task {task_id}: {desc}."
        )
        chat_tab = self._dock.chat_tab_widget
        chat_tab.input_edit.setPlainText(prompt)
        self.accept()
        chat_tab.send_message()

    def _edit_and_resend(self):
        """Pragmatic version of step-level re-editability: pre-fills the chat box with an
        editable prompt for this task (any status, not just FAILED like Retry) but does NOT
        auto-send -- the user edits the parameters/details themselves, then sends when
        ready. Avoids building per-tool-schema dynamic parameter forms, a much larger UI
        subsystem (same tradeoff the old Activity tab's identical control already made)."""
        task_id = self._task.get("id")
        desc = self._task.get("description", "")
        chat_tab = self._dock.chat_tab_widget
        chat_tab.input_edit.setPlainText(f"Redo task {task_id} ({desc}) but with these changes: ")
        self.accept()
        chat_tab.input_edit.setFocus()
