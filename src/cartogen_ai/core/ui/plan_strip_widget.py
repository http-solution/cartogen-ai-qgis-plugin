# -*- coding: utf-8 -*-
"""Sticky plan strip -- Broadsheet redesign Phase 1 (mockup state 1k, "no tabs, one
scroll"). Replaces the live-plan half of the old Activity tab (tasks_tab_widget.py,
deleted in this same change): a compact progress bar + task list sitting above the chat
thread in chat_tab_widget.py, instead of a full tab of its own.

2026-09-16 Activity-tab audit finding this directly fixes: the one task genuinely
needing the user's decision used to scroll out of view inside the old tab's
240px-capped list, competing for space with a Task Inspector box beneath it that stayed
visible (mostly empty) even when nothing was selected. There is no separate tab to
scroll past here, and clicking a task now opens task_inspector_dialog.py's dialog
instead of eating always-visible space in this widget -- the list is the only thing in
this widget besides the header/progress bar, so a pending task has far less to compete
with for the user's attention."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QProgressBar,
    QListWidget, QListWidgetItem, QMessageBox,
)

from .chat_formatting import _relative_time

_STATUS_STYLES = {
    "TODO": ("⚪", "#666666", "#f1f3f6"),
    "IN_PROGRESS": ("🟡", "#8a6d00", "#fff8e1"),
    "PREVIEW_READY": ("🔍", "#01579b", "#e3f0ff"),
    "CONFIRMED": ("🔷", "#01579b", "#e3f0ff"),
    "DONE": ("🟢", "#1b5e20", "#e8f5e9"),
    "FAILED": ("🔴", "#b71c1c", "#fdecea"),
}


class PlanStripWidget(QWidget):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self._dock = dock
        self._viewing_history = False
        self._last_seen_plan_title = None
        self._connected_task_manager = None
        self.init_ui()

    @property
    def _agent_provider(self):
        return self._dock._agent_provider

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)

        header_row = QHBoxLayout()
        self.plan_title_label = QLabel("<b>📭 No active plan yet</b>")
        header_row.addWidget(self.plan_title_label, stretch=1)

        self.plan_history_combo = QComboBox()
        self.plan_history_combo.addItem("Current Plan")
        self.plan_history_combo.setToolTip("Browse past plans from this session")
        self.plan_history_combo.currentIndexChanged.connect(self._on_plan_history_selected)
        header_row.addWidget(self.plan_history_combo)

        self.clear_plan_btn = QPushButton("✕")
        self.clear_plan_btn.setObjectName("dangerButton")
        self.clear_plan_btn.setToolTip("Archive the current plan and reset the tracker")
        self.clear_plan_btn.setFixedWidth(28)
        self.clear_plan_btn.clicked.connect(self._clear_plan_clicked)
        header_row.addWidget(self.clear_plan_btn)
        layout.addLayout(header_row)

        self.plan_progress_bar = QProgressBar()
        self.plan_progress_bar.setTextVisible(True)
        self.plan_progress_bar.setRange(0, 1)
        self.plan_progress_bar.setValue(0)
        self.plan_progress_bar.setFormat("No active plan yet -- ask me something multi-step")
        self.plan_progress_bar.setFixedHeight(18)
        layout.addWidget(self.plan_progress_bar)

        # No fixed max-height cap here (unlike the old Activity tab's task_list_widget) --
        # this widget no longer shares vertical space with an always-visible Task
        # Inspector box below it (that content moved to task_inspector_dialog.py, opened
        # per-task on click), so there's nothing else in this widget competing for room.
        # Still bounded loosely so a very long plan doesn't dominate the whole dock --
        # scrolls internally past that, same mechanism the old tab used.
        self.task_list_widget = QListWidget()
        self.task_list_widget.setMaximumHeight(180)
        self.task_list_widget.itemClicked.connect(self._on_task_item_clicked)
        layout.addWidget(self.task_list_widget)
        self.task_list_widget.setVisible(False)
        self.plan_history_combo.setVisible(False)
        self.clear_plan_btn.setVisible(False)

    def sync_with_agent(self, agent):
        """Called by chat_tab_widget.py's _dispatch_message right before every send, same
        call-site timing tasks_tab_widget.py's old sync_with_agent had -- connects the live
        task_manager.plan_updated signal once per instance (not once per message; a
        Qt-signal-connected-N-times bug already fixed once for the old tab, see that
        method's own historical docstring in git blame) and renders the current plan."""
        self._viewing_history = False
        self.plan_history_combo.blockSignals(True)
        self.plan_history_combo.setCurrentIndex(0)
        self.plan_history_combo.blockSignals(False)

        if agent is not None and hasattr(agent, "task_manager"):
            if getattr(self, "_connected_task_manager", None) is not agent.task_manager:
                try:
                    agent.task_manager.plan_updated.connect(self._on_live_plan_updated)
                    self._connected_task_manager = agent.task_manager
                except Exception as e:
                    print(f"[PlanStripWidget] Failed to connect plan_updated signal: {e}")
            self._on_live_plan_updated(agent.task_manager.get_plan())

    def _build_task_item_widget(self, task):
        status = task.get("status", "TODO")
        icon, text_color, bg_color = _STATUS_STYLES.get(status, _STATUS_STYLES["TODO"])
        desc = task.get("description", "")
        task_id = task.get("id", "?")
        result = task.get("result", "")
        tool_name = task.get("tool_name", "")
        when = _relative_time(task.get("updated_at", ""))
        pending = task.get("pending_tool")

        chips = ""
        if pending:
            chips += (
                '<span style="background-color:#fce4ec;color:#a3255a;border-radius:3px;'
                'padding:1px 5px;font-size:10px;margin-left:4px;font-weight:bold;">'
                'needs you</span>'
            )
        if tool_name:
            chips += (
                f'<span style="background-color:#dde3ea;border-radius:3px;padding:1px 5px;'
                f'font-size:10px;margin-left:4px;">{tool_name}</span>'
            )
        if when:
            chips += f'<span style="color:#888;font-size:10px;margin-left:4px;">{when}</span>'

        result_html = f"<br><span style='color:#555;font-size:11px;'>→ {result}</span>" if result else ""

        html = (
            f'<div style="background-color:{bg_color}; border-radius:6px; padding:6px 8px; margin:2px 0;">'
            f'<span style="color:{text_color}; font-weight:bold;">{icon} Task {task_id}: {desc}</span>'
            f'{chips}{result_html}'
            f'</div>'
        )
        label = QLabel(html)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        return label

    def _render_plan(self, plan_data):
        """Draws the given plan snapshot into the task list/progress bar. Used for both the
        live plan and read-only history snapshots selected from plan_history_combo."""
        title = plan_data.get("title", "")
        tasks = plan_data.get("tasks", [])

        has_plan = bool(title or tasks)
        self.task_list_widget.setVisible(has_plan)
        self.plan_history_combo.setVisible(has_plan)
        self.clear_plan_btn.setVisible(has_plan)

        if title:
            self.plan_title_label.setText(f"<b>📋 Plan: {title}</b>")
        else:
            self.plan_title_label.setText("<b>📭 No active plan yet</b>")

        total = len(tasks)
        done = sum(1 for t in tasks if t.get("status") == "DONE")
        pending_count = sum(1 for t in tasks if t.get("pending_tool"))
        if total == 0:
            self.plan_progress_bar.setRange(0, 1)
            self.plan_progress_bar.setValue(0)
            self.plan_progress_bar.setFormat("No active plan yet -- ask me something multi-step")
        else:
            self.plan_progress_bar.setRange(0, total)
            self.plan_progress_bar.setValue(done)
            fmt = "%v/%m steps complete"
            if pending_count:
                fmt += f" -- {pending_count} needs you"
            self.plan_progress_bar.setFormat(fmt)

        self.task_list_widget.clear()
        for task in tasks:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, task)
            widget = self._build_task_item_widget(task)
            item.setSizeHint(widget.sizeHint())
            self.task_list_widget.addItem(item)
            self.task_list_widget.setItemWidget(item, widget)

    def _refresh_plan_history_combo(self):
        agent = self._agent_provider() if self._agent_provider else None
        history = agent.task_manager.get_plan_history() if agent and hasattr(agent, "task_manager") else []
        self.plan_history_combo.blockSignals(True)
        self.plan_history_combo.clear()
        self.plan_history_combo.addItem("Current Plan")
        for entry in history:
            self.plan_history_combo.addItem(entry.get("title") or "(untitled plan)")
        self.plan_history_combo.setCurrentIndex(0)
        self.plan_history_combo.blockSignals(False)

    def _on_live_plan_updated(self, plan_data):
        title = plan_data.get("title", "")
        if title != self._last_seen_plan_title:
            self._last_seen_plan_title = title
            self._refresh_plan_history_combo()
        if not self._viewing_history:
            self._render_plan(plan_data)

    def _on_plan_history_selected(self, index):
        agent = self._agent_provider() if self._agent_provider else None
        if index <= 0:
            self._viewing_history = False
            if agent and hasattr(agent, "task_manager"):
                self._render_plan(agent.task_manager.get_plan())
            return
        if not (agent and hasattr(agent, "task_manager")):
            return
        history = agent.task_manager.get_plan_history()
        hist_idx = index - 1
        if 0 <= hist_idx < len(history):
            self._viewing_history = True
            self._render_plan(history[hist_idx])

    def _on_task_item_clicked(self, item):
        """Opens the task inspector dialog for the clicked task -- the old Activity tab's
        always-visible Task Inspector box moved here, per-task, rather than staying
        permanently docked (and mostly empty) below the list. A history snapshot is
        read-only (matches the old tab's identical restriction)."""
        task = item.data(Qt.ItemDataRole.UserRole) or {}
        from .task_inspector_dialog import CartogenAiTaskInspectorDialog
        dialog = CartogenAiTaskInspectorDialog(
            self._dock, task, read_only=self._viewing_history, parent=self)
        dialog.exec()

    def _clear_plan_clicked(self):
        if not self._agent_provider:
            return
        agent = self._agent_provider()
        if not (agent and hasattr(agent, "task_manager")) or not agent.task_manager.tasks:
            return
        reply = QMessageBox.question(
            self, "Clear Plan", "Archive the current plan and reset the tracker?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            agent.task_manager.clear_plan()
