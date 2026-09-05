# -*- coding: utf-8 -*-
"""Tasks & Notes tab, extracted from dock_widget.py's CartogenAiDockWidget
(docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md). Owns the live plan/progress display,
plan history browsing, the task inspector (rationale/code snippet/confirm-retry-
edit-cancel), and the spatial memory panel.

statusSignal (used by _copy_code_snippet) stays defined on the parent
CartogenAiDockWidget -- reached via self._dock, same pattern as chat_tab_widget.py."""

from qgis.PyQt.QtCore import Qt, pyqtSlot
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
    QListWidget, QListWidgetItem, QGroupBox, QComboBox, QProgressBar, QLineEdit,
    QMessageBox, QApplication,
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


class TasksTabWidget(QWidget):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self._dock = dock
        self._active_highlights = []  # keeps QgsHighlight objects alive until their timer fires
        self._viewing_history = False
        self._last_seen_plan_title = None
        self._current_code_snippet = ""
        self._connected_task_manager = None
        self._raw_memory_context = ""
        self._learned_item_keys = []  # combo index -> global-note key, kept in sync with the combo

        self.init_ui()

    @property
    def _agent_provider(self):
        return self._dock._agent_provider

    def init_ui(self):
        # Note: this widget is wrapped in a QScrollArea by dock_widget.py, not sized
        # directly into the tab_widget -- see that call site's comment for why
        # (QTabWidget/QStackedWidget sizes the whole dock to its tallest tab's natural
        # size hint, not just the currently visible tab).
        tasks_layout = QVBoxLayout(self)
        tasks_layout.setContentsMargins(4, 4, 4, 4)

        # Header: plan title + progress bar + history dropdown + clear button
        header_row = QHBoxLayout()
        self.plan_title_label = QLabel("<b>📭 No active plan yet</b>")
        header_row.addWidget(self.plan_title_label, stretch=1)

        self.plan_history_combo = QComboBox()
        self.plan_history_combo.addItem("Current Plan")
        self.plan_history_combo.setToolTip("Browse past plans from this session")
        self.plan_history_combo.currentIndexChanged.connect(self._on_plan_history_selected)
        header_row.addWidget(self.plan_history_combo)

        self.clear_plan_btn = QPushButton("✕ Clear Plan")
        self.clear_plan_btn.setObjectName("dangerButton")
        self.clear_plan_btn.setToolTip("Archive the current plan and reset the tracker")
        self.clear_plan_btn.clicked.connect(self._clear_plan_clicked)
        header_row.addWidget(self.clear_plan_btn)
        tasks_layout.addLayout(header_row)

        self.plan_progress_bar = QProgressBar()
        self.plan_progress_bar.setTextVisible(True)
        # min==max==0 would trigger Qt's indeterminate "busy" animation -- use range(0,1)/value(0)
        # for a static empty bar instead (matches the empty-state branch in _render_plan below).
        self.plan_progress_bar.setRange(0, 1)
        self.plan_progress_bar.setValue(0)
        self.plan_progress_bar.setFormat("No active plan yet -- ask me something multi-step")
        tasks_layout.addWidget(self.plan_progress_bar)

        self.task_list_widget = QListWidget()
        # Bounded, not just given a stretch factor: QTabWidget/QStackedWidget sizes the whole
        # dock to its TALLEST tab's natural size hint, not just the currently visible one --
        # an unbounded list here (or memory_browser below) was silently forcing the entire
        # QGIS window taller than the screen, pushing the chat input off-screen under the
        # taskbar. The list still scrolls internally past this height, nothing is hidden.
        self.task_list_widget.setMaximumHeight(240)
        self.task_list_widget.itemSelectionChanged.connect(self._on_task_item_selected)
        tasks_layout.addWidget(self.task_list_widget, stretch=2)

        # Code Inspector & Rationale Panel
        inspector_box = QGroupBox("🔍 Task Inspector & Preview Safety")
        inspector_layout = QVBoxLayout(inspector_box)

        self.rationale_label = QLabel("<b>Rationale:</b> Select a task to inspect details.")
        self.rationale_label.setWordWrap(True)
        inspector_layout.addWidget(self.rationale_label)

        self.code_inspector = QTextBrowser()
        self.code_inspector.setMaximumHeight(80)
        self.code_inspector.setPlaceholderText("PyQGIS / QGIS Expression code executed for selected task...")
        inspector_layout.addWidget(self.code_inspector)

        self.copy_snippet_btn = QPushButton("📋 Copy Snippet")
        self.copy_snippet_btn.setObjectName("secondaryButton")
        self.copy_snippet_btn.setEnabled(False)
        self.copy_snippet_btn.clicked.connect(self._copy_code_snippet)
        inspector_layout.addWidget(self.copy_snippet_btn)

        # Confirm / Retry / Cancel Button Layout
        confirm_layout = QHBoxLayout()
        self.confirm_btn = QPushButton("✅ Confirm & Apply Edit")
        self.confirm_btn.setObjectName("successButton")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._confirm_selected_task)

        self.retry_task_btn = QPushButton("🔁 Retry")
        self.retry_task_btn.setObjectName("secondaryButton")
        self.retry_task_btn.setEnabled(False)
        self.retry_task_btn.setToolTip("Ask the agent to retry this failed step")
        self.retry_task_btn.clicked.connect(self._retry_selected_task)

        self.edit_task_btn = QPushButton("✏️ Edit & Resend")
        self.edit_task_btn.setObjectName("secondaryButton")
        self.edit_task_btn.setEnabled(False)
        self.edit_task_btn.setToolTip("Pre-fill the chat box with an editable version of this step -- change it, then send yourself")
        self.edit_task_btn.clicked.connect(self._edit_selected_task)

        self.cancel_task_btn = QPushButton("❌ Cancel")
        self.cancel_task_btn.setObjectName("secondaryButton")
        self.cancel_task_btn.setEnabled(False)
        self.cancel_task_btn.clicked.connect(self._cancel_selected_task)

        confirm_layout.addWidget(self.confirm_btn)
        confirm_layout.addWidget(self.retry_task_btn)
        confirm_layout.addWidget(self.edit_task_btn)
        confirm_layout.addWidget(self.cancel_task_btn)
        inspector_layout.addLayout(confirm_layout)

        tasks_layout.addWidget(inspector_box)

        # Spatial Memory panel: search box + browser (now actually resizes with the dock) + clear button
        memory_header = QHBoxLayout()
        memory_header.addWidget(QLabel("<b>🧠 Project Notes & Memory</b>"))
        self.clear_memory_btn = QPushButton("🗑 Clear Project Memory")
        self.clear_memory_btn.setObjectName("dangerButton")
        self.clear_memory_btn.clicked.connect(self._clear_project_memory_clicked)
        # GDPR review finding F1 (docs/GDPR_COMPLIANCE_REVIEW.docx, cartogen-ai-community):
        # global memory had no erasure path at all -- this button plus
        # memory_manager.clear_global_notes() closes it, per the review's own R4
        # recommendation ("Add a clear_global_notes() method and wire a 'Clear
        # Global Memory' control next to the existing project-memory button").
        # Deliberately separate from Forget Selected below, which only removes one
        # pref:/rule:/usage: learned-item key at a time -- this clears every global
        # note regardless of who wrote it, matching Clear Project Memory's scope.
        self.clear_global_memory_btn = QPushButton("🗑 Clear Global Memory")
        self.clear_global_memory_btn.setObjectName("dangerButton")
        self.clear_global_memory_btn.clicked.connect(self._clear_global_memory_clicked)
        memory_header.addStretch()
        memory_header.addWidget(self.clear_memory_btn)
        memory_header.addWidget(self.clear_global_memory_btn)
        tasks_layout.addLayout(memory_header)

        self.memory_search_edit = QLineEdit()
        self.memory_search_edit.setPlaceholderText("🔎 Filter memory notes...")
        self.memory_search_edit.textChanged.connect(self._on_memory_search_changed)
        tasks_layout.addWidget(self.memory_search_edit)

        self.memory_browser = QTextBrowser()
        # Bounded on both ends -- see the comment on task_list_widget's setMaximumHeight
        # above for why an unbounded-growth widget here breaks the whole window's sizing.
        # Bigger than the original 100px cap (that was the "too cramped" complaint this
        # tab was revamped to fix) but still capped -- the QScrollArea wrapper (applied by
        # dock_widget.py) is what actually prevents this from forcing the window taller;
        # this cap just keeps it from dominating this tab's own scrollable area.
        self.memory_browser.setMinimumHeight(120)
        self.memory_browser.setMaximumHeight(220)
        self.memory_browser.setPlaceholderText("Project Notes & Memory...")
        tasks_layout.addWidget(self.memory_browser, stretch=1)

        # Learned Preferences & Rules (self-learning mechanism 4, 2026-09-02): the
        # browser above is read-only and shows everything; this row is specifically
        # for un-learning a single wrong pref:*/rule:*/usage:* entry (see
        # agent/learning.py) without wiping all project/global memory via the Clear
        # button above. Kept as a combo + one button rather than per-row buttons in
        # the browser itself -- QTextBrowser doesn't host interactive widgets per
        # line, and a second list widget felt heavier than this tab needed.
        learned_header = QHBoxLayout()
        learned_header.addWidget(QLabel("<b>🎓 Learned Preferences & Rules</b>"))
        learned_header.addStretch()
        tasks_layout.addLayout(learned_header)

        forget_layout = QHBoxLayout()
        self.learned_items_combo = QComboBox()
        self.learned_items_combo.setPlaceholderText("(no learned preferences or rules yet)")
        self.forget_learned_btn = QPushButton("🗑 Forget Selected")
        self.forget_learned_btn.setObjectName("dangerButton")
        self.forget_learned_btn.clicked.connect(self._forget_selected_learned_item_clicked)
        forget_layout.addWidget(self.learned_items_combo, stretch=1)
        forget_layout.addWidget(self.forget_learned_btn)
        tasks_layout.addLayout(forget_layout)

    def sync_with_agent(self, agent):
        """Called by ChatTabWidget._dispatch_message right before a new message is
        sent, so the live plan is what's visible while the request runs. Was inline
        in the old (unsplit) _dispatch_message body -- moved here verbatim (same
        de-dup guard, same exception handling) since all the state it touches
        (plan_history_combo, task_manager.plan_updated connection, memory panel)
        belongs to this tab, not the Chat tab that triggers it."""
        # Sending a new message means "back to work" -- snap out of history-browsing mode
        # so the live plan is what's visible while this request runs.
        self._viewing_history = False
        self.plan_history_combo.blockSignals(True)
        self.plan_history_combo.setCurrentIndex(0)
        self.plan_history_combo.blockSignals(False)

        if agent is not None and hasattr(agent, "task_manager"):
            # Connect once per task_manager instance, not once per message -- re-running
            # .connect() on every send_message() call stacked up a duplicate connection
            # each time, so a single plan_updated.emit() would call _render_plan N times
            # for the Nth message in the session (harmless since _render_plan clears the
            # list first, but wasteful and a sign this was never actually verified live).
            if getattr(self, "_connected_task_manager", None) is not agent.task_manager:
                try:
                    agent.task_manager.plan_updated.connect(self._on_live_plan_updated)
                    self._connected_task_manager = agent.task_manager
                except Exception as e:
                    # Was previously a bare `except: pass` -- a real connection failure
                    # here would silently leave the Tasks panel never updating live,
                    # with no way to tell from the UI. Print so it's visible in the
                    # QGIS Python Console instead of vanishing.
                    print(f"[TasksTabWidget] Failed to connect plan_updated signal: {e}")
            self._on_live_plan_updated(agent.task_manager.get_plan())
            self._raw_memory_context = agent.memory_manager.get_formatted_memory_context()
            self._apply_memory_filter()
            self._refresh_learned_items_combo(agent.memory_manager)

    def _build_task_item_widget(self, task):
        status = task.get("status", "TODO")
        icon, text_color, bg_color = _STATUS_STYLES.get(status, _STATUS_STYLES["TODO"])
        desc = task.get("description", "")
        task_id = task.get("id", "?")
        result = task.get("result", "")
        tool_name = task.get("tool_name", "")
        when = _relative_time(task.get("updated_at", ""))

        chips = ""
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
        live plan (gated by _viewing_history in _on_live_plan_updated) and read-only history
        snapshots selected from plan_history_combo. Also the slot connected to the dock's
        planUpdatedSignal."""
        title = plan_data.get("title", "")
        tasks = plan_data.get("tasks", [])

        if title:
            self.plan_title_label.setText(f"<b>📋 Plan: {title}</b>")
        else:
            self.plan_title_label.setText("<b>📭 No active plan yet</b>")

        total = len(tasks)
        done = sum(1 for t in tasks if t.get("status") == "DONE")
        if total == 0:
            # min==max==0 would trigger Qt's indeterminate "busy" animation, which is not
            # what an empty plan should look like -- use a static empty bar instead.
            self.plan_progress_bar.setRange(0, 1)
            self.plan_progress_bar.setValue(0)
            self.plan_progress_bar.setFormat("No active plan yet -- ask me something multi-step")
        else:
            self.plan_progress_bar.setRange(0, total)
            self.plan_progress_bar.setValue(done)
            self.plan_progress_bar.setFormat("%v/%m steps complete")

        self._active_plan_tasks = tasks
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
        """Connected to task_manager.plan_updated (via sync_with_agent above). Refreshes the
        history dropdown whenever a new plan starts (title change), but only re-renders the
        visible task list if the user isn't currently browsing a past plan -- otherwise live
        updates would yank them back to the current plan mid-browse."""
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

    def _on_task_item_selected(self):
        items = self.task_list_widget.selectedItems()
        if not items or self._viewing_history:
            self.rationale_label.setText(
                "<b>Rationale:</b> Viewing history (read-only) -- switch to Current Plan to act on a task."
                if self._viewing_history else
                "<b>Rationale:</b> Select a task to inspect details."
            )
            self.code_inspector.clear()
            self._current_code_snippet = ""
            self.copy_snippet_btn.setEnabled(False)
            self.confirm_btn.setEnabled(False)
            self.retry_task_btn.setEnabled(False)
            self.edit_task_btn.setEnabled(False)
            self.cancel_task_btn.setEnabled(False)
            return

        task = items[0].data(Qt.ItemDataRole.UserRole) or {}
        rat = task.get("rationale") or "(No rationale provided for this step)"
        snippet = task.get("code_snippet") or "# No code snippet recorded for this step"
        status = task.get("status")

        self.rationale_label.setText(f"<b>Rationale:</b> {rat}")
        self.code_inspector.setText(f"<code>{snippet}</code>")
        self._current_code_snippet = task.get("code_snippet") or ""
        self.copy_snippet_btn.setEnabled(bool(self._current_code_snippet))

        self.confirm_btn.setEnabled(status == "PREVIEW_READY")
        self.cancel_task_btn.setEnabled(status == "PREVIEW_READY")
        self.retry_task_btn.setEnabled(status == "FAILED")
        # Unlike Retry (failed steps only), editing makes sense for any task -- re-run a DONE
        # step with different inputs, or fix up a step before it's even attempted.
        self.edit_task_btn.setEnabled(True)

        if status == "PREVIEW_READY":
            self._flash_preview_layer(task)

    def _flash_preview_layer(self, task):
        """Highlights the layer a pending destructive-edit preview would affect, so the user
        sees *which* layer is about to change before clicking Confirm -- not a full before/after
        geometry diff (that would need running the edit read-only and rendering two geometries,
        a materially bigger change), but a real visual affordance beyond text alone."""
        layer_name = (task.get("pending_args") or {}).get("layer_name")
        if not layer_name:
            return
        try:
            from qgis.core import QgsProject
            from qgis.utils import iface
            from .canvas_highlight import flash_layer_extent

            layers = QgsProject.instance().mapLayersByName(layer_name)
            if not layers:
                return

            def _on_expired(highlight):
                if highlight in self._active_highlights:
                    self._active_highlights.remove(highlight)

            highlight = flash_layer_extent(iface, layers[0], on_expired=_on_expired)
            if highlight is not None:
                self._active_highlights.append(highlight)
        except Exception as e:
            print(f"[TasksTabWidget] Preview highlight failed: {e}")

    def _confirm_selected_task(self):
        items = self.task_list_widget.selectedItems()
        if not items:
            return
        task = items[0].data(Qt.ItemDataRole.UserRole) or {}
        task_id = task.get("id")
        pending_tool = task.get("pending_tool")
        pending_args = task.get("pending_args", {})

        if self._agent_provider:
            agent = self._agent_provider()
            if agent:
                if pending_tool:
                    exec_res = agent._real_execute_tool(pending_tool, pending_args, user_confirmed=True)
                    msg = f"Executed `{pending_tool}`: {exec_res}"
                else:
                    msg = "Confirmed by User"
                if hasattr(agent, "task_manager"):
                    agent.task_manager.update_task(task_id, "DONE", msg)
                    self._dock.receiveMessageSignal.emit("ai", f"✅ **Confirmed & Executed Task {task_id}:** {msg}")
        self.confirm_btn.setEnabled(False)
        self.retry_task_btn.setEnabled(False)
        self.edit_task_btn.setEnabled(False)
        self.cancel_task_btn.setEnabled(False)

    def _cancel_selected_task(self):
        items = self.task_list_widget.selectedItems()
        if not items:
            return
        task = items[0].data(Qt.ItemDataRole.UserRole) or {}
        task_id = task.get("id")
        if self._agent_provider:
            agent = self._agent_provider()
            if agent and hasattr(agent, "task_manager"):
                agent.task_manager.update_task(task_id, "FAILED", "Cancelled by User")
                self._dock.receiveMessageSignal.emit("ai", f"❌ **Cancelled Task {task_id}:** {task.get('description')}")
        self.confirm_btn.setEnabled(False)
        self.retry_task_btn.setEnabled(False)
        self.edit_task_btn.setEnabled(False)
        self.cancel_task_btn.setEnabled(False)

    def _retry_selected_task(self):
        items = self.task_list_widget.selectedItems()
        if not items:
            return
        task = items[0].data(Qt.ItemDataRole.UserRole) or {}
        task_id = task.get("id")
        desc = task.get("description", "")
        result = task.get("result", "")
        prompt = (
            f"Retry task {task_id}: {desc}. It previously failed with: {result}"
            if result else f"Retry task {task_id}: {desc}."
        )
        chat_tab = self._dock.chat_tab_widget
        chat_tab.input_edit.setPlainText(prompt)
        chat_tab.send_message()

    def _edit_selected_task(self):
        """Pragmatic version of step-level re-editability: pre-fills the chat box with an
        editable prompt for this task (any status, not just FAILED like Retry) but does NOT
        auto-send -- the user edits the parameters/details themselves, then sends when ready.
        Avoids building per-tool-schema dynamic parameter forms, a much larger UI subsystem."""
        items = self.task_list_widget.selectedItems()
        if not items:
            return
        task = items[0].data(Qt.ItemDataRole.UserRole) or {}
        task_id = task.get("id")
        desc = task.get("description", "")
        chat_tab = self._dock.chat_tab_widget
        chat_tab.input_edit.setPlainText(f"Redo task {task_id} ({desc}) but with these changes: ")
        chat_tab.input_edit.setFocus()

    def _copy_code_snippet(self):
        if not self._current_code_snippet:
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._current_code_snippet)
            self._dock.statusSignal.emit("Code snippet copied to clipboard.")

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

    def _clear_project_memory_clicked(self):
        if not self._agent_provider:
            return
        agent = self._agent_provider()
        if not (agent and hasattr(agent, "memory_manager")):
            return
        reply = QMessageBox.question(
            self, "Clear Project Memory", "Permanently clear all stored project notes for this project?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            agent.memory_manager.clear_project_notes()
            self._raw_memory_context = agent.memory_manager.get_formatted_memory_context()
            self._apply_memory_filter()

    def _clear_global_memory_clicked(self):
        if not self._agent_provider:
            return
        agent = self._agent_provider()
        if not (agent and hasattr(agent, "memory_manager")):
            return
        reply = QMessageBox.question(
            self, "Clear Global Memory",
            "Permanently clear ALL global memory notes (preferences, rules, and any other "
            "notes remembered across every QGIS project on this machine)?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        agent.memory_manager.clear_global_notes()
        self._raw_memory_context = agent.memory_manager.get_formatted_memory_context()
        self._apply_memory_filter()
        self._refresh_learned_items_combo(agent.memory_manager)

    def _refresh_learned_items_combo(self, memory_manager):
        """Repopulates the Forget-control combo from the memory manager's current
        pref:*/rule:*/usage:* global notes (see agent/learning.py for what writes
        these). Called after every sync_with_agent() and after a successful forget,
        so the list never shows a key that's already been removed."""
        try:
            notes = memory_manager.get_global_notes()
        except Exception as e:
            print(f"[TasksTabWidget] Failed to read global notes for learned-items combo: {e}")
            return
        learned = {
            k: v for k, v in notes.items()
            if k.startswith("pref:") or k.startswith("rule:") or k.startswith("usage:")
        }
        self.learned_items_combo.blockSignals(True)
        self.learned_items_combo.clear()
        self._learned_item_keys = []
        for key in sorted(learned):
            value = learned[key]
            label = f"{key}: {value}"
            if len(label) > 90:
                label = label[:87] + "..."
            self.learned_items_combo.addItem(label)
            self._learned_item_keys.append(key)
        self.learned_items_combo.blockSignals(False)

    def _forget_selected_learned_item_clicked(self):
        idx = self.learned_items_combo.currentIndex()
        if idx < 0 or idx >= len(self._learned_item_keys):
            return
        key = self._learned_item_keys[idx]
        if not self._agent_provider:
            return
        agent = self._agent_provider()
        if not (agent and hasattr(agent, "memory_manager")):
            return
        reply = QMessageBox.question(
            self, "Forget Learned Item", f"Remove this learned item?\n\n{key}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        agent.memory_manager.delete_global_note(key)
        self._raw_memory_context = agent.memory_manager.get_formatted_memory_context()
        self._apply_memory_filter()
        self._refresh_learned_items_combo(agent.memory_manager)

    def _on_memory_search_changed(self, _text):
        self._apply_memory_filter()

    def _apply_memory_filter(self):
        query = self.memory_search_edit.text().strip().lower()
        if not query:
            self.memory_browser.setText(self._raw_memory_context)
            return
        matched = [line for line in self._raw_memory_context.split("\n") if query in line.lower()]
        self.memory_browser.setText("\n".join(matched) if matched else "(no matches)")
