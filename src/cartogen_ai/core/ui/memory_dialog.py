# -*- coding: utf-8 -*-
"""Project notes & memory dialog -- Broadsheet redesign Phase 1, mockup state 1o
("Project notes & memory ... editable and exportable", the same "← back" dialog
pattern settings_dialog.py already established for Settings, 1n). Rehouses the old
Activity tab's "02 Project Notes and Memory" and "03 Learned Preferences and Rules"
sections (tasks_tab_widget.py, deleted in this same change) as their own dialog,
opened from a header button, rather than tab content competing for space with the
live plan."""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
    QComboBox, QLineEdit, QMessageBox, QFileDialog,
)

from .chat_formatting import render_markdown
from .theme import theme_colors


class CartogenAiMemoryDialog(QDialog):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self._dock = dock
        self._raw_memory_context = ""
        self._learned_item_keys = []
        self.setWindowTitle("Project Notes & Memory")
        self.resize(420, 520)
        self.init_ui()
        self.refresh()

    @property
    def _agent_provider(self):
        return self._dock._agent_provider

    def init_ui(self):
        layout = QVBoxLayout(self)

        actions_row = QHBoxLayout()
        self.export_data_btn = QPushButton("💾 Export My Data")
        self.export_data_btn.setObjectName("secondaryButton")
        self.export_data_btn.setToolTip(
            "Export everything Cartogen AI has stored for this project and this machine -- project "
            "memory, global memory, and the saved conversation (if saving it is enabled) -- as one "
            "JSON file."
        )
        self.export_data_btn.clicked.connect(self._export_stored_data_clicked)
        self.clear_memory_btn = QPushButton("🗑 Clear Project Memory")
        self.clear_memory_btn.setObjectName("dangerButton")
        self.clear_memory_btn.clicked.connect(self._clear_project_memory_clicked)
        self.clear_global_memory_btn = QPushButton("🗑 Clear Global Memory")
        self.clear_global_memory_btn.setObjectName("dangerButton")
        self.clear_global_memory_btn.clicked.connect(self._clear_global_memory_clicked)
        self.clear_saved_chat_btn = QPushButton("🗑 Clear Saved Chat")
        self.clear_saved_chat_btn.setObjectName("dangerButton")
        self.clear_saved_chat_btn.setToolTip(
            "Delete the conversation saved inside this project's file (the full transcript and the short "
            "summary of older turns). Does not affect the conversation currently on screen, and cannot "
            "reach copies of the project file that were already shared."
        )
        self.clear_saved_chat_btn.clicked.connect(self._clear_saved_chat_clicked)
        actions_row.addWidget(self.export_data_btn)
        actions_row.addWidget(self.clear_memory_btn)
        actions_row.addWidget(self.clear_global_memory_btn)
        actions_row.addWidget(self.clear_saved_chat_btn)
        layout.addLayout(actions_row)

        self.memory_search_edit = QLineEdit()
        self.memory_search_edit.setPlaceholderText("🔎 Filter memory notes...")
        self.memory_search_edit.textChanged.connect(self._on_memory_search_changed)
        layout.addWidget(self.memory_search_edit)

        self.memory_browser = QTextBrowser()
        self.memory_browser.setPlaceholderText("Project Notes and Memory...")
        layout.addWidget(self.memory_browser, stretch=1)

        layout.addWidget(QLabel("<b>Learned Preferences and Rules</b>"))
        forget_row = QHBoxLayout()
        self.learned_items_combo = QComboBox()
        self.learned_items_combo.setPlaceholderText("(no learned preferences or rules yet)")
        self.forget_learned_btn = QPushButton("🗑 Forget Selected")
        self.forget_learned_btn.setObjectName("dangerButton")
        self.forget_learned_btn.clicked.connect(self._forget_selected_learned_item_clicked)
        forget_row.addWidget(self.learned_items_combo, stretch=1)
        forget_row.addWidget(self.forget_learned_btn)
        layout.addLayout(forget_row)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def refresh(self):
        """Builds fresh state from the live agent -- called once on open (matches
        settings_dialog.py's own "read live state when opened" pattern), not kept
        continuously synced while the dialog is up (it's a short-lived modal, not a
        permanently docked panel like the old tab was)."""
        agent = self._agent_provider() if self._agent_provider else None
        if agent is None or not hasattr(agent, "memory_manager"):
            # rc7 smoke test, 2026-09-30 (F24): this used to return silently, so an operator saw an
            # empty dialog while the same session's data export held 3 project and 26 global
            # entries. Say why it is empty instead.
            self._raw_memory_context = ""
            self.memory_browser.setPlainText(
                "Memory is not available yet: the assistant has not started for this project "
                "(or could not start -- check the provider and API key in Settings). Send a message "
                "in the chat, then reopen this window."
            )
            self.learned_items_combo.clear()
            return
        self._raw_memory_context = agent.memory_manager.get_formatted_memory_context()
        self._apply_memory_filter()
        self._refresh_learned_items_combo(agent.memory_manager)

    def _export_stored_data_clicked(self):
        agent = self._agent_provider() if self._agent_provider else None
        if not (agent and hasattr(agent, "memory_manager")):
            return
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Export My Data", "cartogen_data_export.json", "JSON files (*.json)",
        )
        if not output_path:
            return
        try:
            from ..agent import data_export, chat_persistence
            project_notes = agent.memory_manager.get_project_notes()
            global_notes = agent.memory_manager.get_global_notes()
            chat_history = (chat_persistence.load_chat_transcript()
                            or chat_persistence.load_chat_history_with_timestamps())
            from ..agent.agent_orchestrator import MAX_HISTORY_MESSAGES
            document = data_export.build_export_document(
                project_notes, global_notes, chat_history,
                chat_digest=chat_persistence.load_chat_digest(),
                chat_info=chat_persistence.describe_retention(MAX_HISTORY_MESSAGES))
            ok = data_export.write_export_document(document, output_path)
        except Exception as e:
            QMessageBox.warning(self, "Export My Data", f"Export failed: {e}")
            return
        if ok:
            QMessageBox.information(self, "Export My Data", f"Exported to:\n{output_path}")
        else:
            QMessageBox.warning(self, "Export My Data", f"Failed to write export file to:\n{output_path}")

    def _clear_saved_chat_clicked(self):
        from ..agent import chat_persistence
        stored = len(chat_persistence.load_chat_transcript())
        reply = QMessageBox.question(
            self, "Clear Saved Chat",
            ("Permanently delete the conversation saved in this project's file (%d messages)?\n\n"
             "The conversation on screen is not affected, and copies of the project file that were already "
             "shared keep their own copy." % stored),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = chat_persistence.clear_saved_chat_history()
        if result.get("success"):
            QMessageBox.information(
                self, "Clear Saved Chat",
                "Deleted %d saved messages from this project. Save the project to keep the change." % result.get("removed", 0))
        else:
            QMessageBox.warning(self, "Clear Saved Chat", "Could not delete the saved conversation.")

    def _clear_project_memory_clicked(self):
        agent = self._agent_provider() if self._agent_provider else None
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
        agent = self._agent_provider() if self._agent_provider else None
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
        try:
            notes = memory_manager.get_global_notes()
        except Exception as e:
            print(f"[MemoryDialog] Failed to read global notes for learned-items combo: {e}")
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
        agent = self._agent_provider() if self._agent_provider else None
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
        text = self._raw_memory_context
        if query:
            matched = [line for line in text.split("\n") if query in line.lower()]
            text = "\n".join(matched) if matched else "(no matches)"
        self.memory_browser.setHtml(render_markdown(text, theme_colors()))
