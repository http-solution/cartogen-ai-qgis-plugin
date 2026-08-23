# -*- coding: utf-8 -*-
"""
Dock Widget UI for Cartogen AI.
Provides dual-tab interface (Chat and Tasks/Notes Plan)
with non-blocking execution threads and file attachment handling.

CartogenAiDockWidget is the outer QDockWidget: it owns the cross-tab signals, the
agent_provider callable, and the header (title/provider switcher/settings button).
The three tabs (Chat, Tasks & Notes, Help) are separate QWidget classes in
chat_tab_widget.py / tasks_tab_widget.py / help_tab_widget.py --
docs/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md has the full rationale for the split and
what still needs verifying in a real QGIS session (this file cannot be imported or
run outside one -- no QGIS_AVAILABLE fallback -- so nothing here has run since the
split; see docs/RELEASE_SMOKE_TEST.md before shipping)."""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QComboBox, QScrollArea,
)
from qgis.core import QgsSettings

from .chat_formatting import build_dock_stylesheet
from .theme import extract_theme_palette
from .dock_constants import PROVIDER_CHOICES
from .chat_tab_widget import ChatTabWidget
from .tasks_tab_widget import TasksTabWidget
from .help_tab_widget import HelpTabWidget


class CartogenAiDockWidget(QDockWidget):
    receiveMessageSignal = pyqtSignal(str, str)
    statusSignal = pyqtSignal(str)
    usageSignal = pyqtSignal(str)
    planUpdatedSignal = pyqtSignal(dict)
    toolStepSignal = pyqtSignal(str, str, str)
    # The refinement call hits the network -- must never block the UI thread,
    # same reasoning as settings_dialog.py's modelsFetchedSignal/_fetch_models.
    # Emitted from the background worker thread in ChatTabWidget._start_refinement();
    # Qt auto-queues delivery to ChatTabWidget._on_refinement_fetched on the main
    # thread since this widget lives there. Payload is (original_text, result_dict),
    # where result_dict is either a valid parsed refinement dict or {"error": ...}.
    refinementFetchedSignal = pyqtSignal(str, dict)

    def __init__(self, agent_provider=None, parent=None):
        super().__init__("Cartogen AI", parent)
        self.setObjectName("CartogenAiDockWidget")
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self._agent_provider = agent_provider

        self.init_ui()

        # Connected after init_ui() so chat_tab_widget/tasks_tab_widget exist.
        self.receiveMessageSignal.connect(self.chat_tab_widget._add_message)
        self.statusSignal.connect(self.chat_tab_widget._set_status)
        self.usageSignal.connect(self.chat_tab_widget._set_usage_label)
        self.toolStepSignal.connect(self.chat_tab_widget._add_tool_step)
        self.refinementFetchedSignal.connect(self.chat_tab_widget._on_refinement_fetched)
        self.planUpdatedSignal.connect(self.tasks_tab_widget._render_plan)

        from ..agent.scheduler import get_scheduler
        get_scheduler().workflow_tick_completed.connect(self.chat_tab_widget._on_scheduled_workflow_tick)

    def init_ui(self):
        container = QWidget(self)
        self.setWidget(container)
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("<b>🗺️ Cartogen AI</b>")

        # Quick provider switcher — lets you jump providers (e.g. after hitting a rate
        # limit) without opening the full Settings dialog each time.
        self.provider_combo = QComboBox()
        for label, value in PROVIDER_CHOICES:
            self.provider_combo.addItem(label, value)
        current_provider = QgsSettings().value("cartogen_ai/provider", "openrouter")
        idx = self.provider_combo.findData(current_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_switch)

        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.setObjectName("secondaryButton")
        self.settings_btn.clicked.connect(self.open_settings)
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.provider_combo)
        header_layout.addWidget(self.settings_btn)
        main_layout.addLayout(header_layout)

        # Main Tab Widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self.chat_tab_widget = ChatTabWidget(dock=self)
        self.tab_widget.addTab(self.chat_tab_widget, "💬 Chat")

        # Tasks & Help are wrapped in a QScrollArea rather than added to tab_widget
        # directly: QTabWidget/QStackedWidget sizes the WHOLE dock to its tallest
        # tab's natural size hint, not just the currently visible tab. With the
        # Tasks tab's substantial content (progress bar, history, task list,
        # inspector, memory panel) sized directly, that was forcing the entire QGIS
        # window taller than the screen regardless of which tab was actually
        # showing -- including the unrelated Chat tab. A QScrollArea decouples the
        # tab's reported size from its content's full size; content that doesn't
        # fit scrolls instead of forcing growth.
        self.tasks_tab_widget = TasksTabWidget(dock=self)
        tasks_scroll = QScrollArea()
        tasks_scroll.setWidgetResizable(True)
        tasks_scroll.setFrameShape(QScrollArea.NoFrame)
        tasks_scroll.setWidget(self.tasks_tab_widget)
        self.tab_widget.addTab(tasks_scroll, "📋 Tasks & Notes")

        self.help_tab_widget = HelpTabWidget()
        help_scroll = QScrollArea()
        help_scroll.setWidgetResizable(True)
        help_scroll.setFrameShape(QScrollArea.NoFrame)
        help_scroll.setWidget(self.help_tab_widget)
        self.tab_widget.addTab(help_scroll, "❓ Help")

        # Modern, theme-adaptive QSS pass over every widget in this dock --
        # see chat_formatting.build_dock_stylesheet for the actual rules and
        # why it's built from the live palette instead of hardcoded colors.
        # A handful of buttons keep meaning-carrying colors (success green on
        # Confirm, danger red on the two Clear buttons) via objectName
        # variants defined in that same stylesheet, set on each button above.
        container.setStyleSheet(build_dock_stylesheet(extract_theme_palette()))

    def refresh_chat_for_project_change(self):
        """Called by CartogenAi (see plugin_main.py) when QgsProject fires
        readProject/cleared -- the dock and its cached agent instance persist
        across project switches, so the visible chat log needs to be reloaded
        to match the newly-active project's saved history instead of showing
        the previous project's conversation."""
        self.chat_tab_widget.refresh_chat_for_project_change()

    def _on_provider_switch(self, index):
        provider_value = self.provider_combo.currentData()
        provider_label = self.provider_combo.currentText()
        if not provider_value:
            return
        QgsSettings().setValue("cartogen_ai/provider", provider_value)
        if self._agent_provider:
            try:
                self._agent_provider()
            except Exception as e:
                print(f"[DockWidget] Agent refresh after provider switch failed: {e}")
        self.receiveMessageSignal.emit("ai", f"🔀 Switched active provider to **{provider_label}**.")

    def open_settings(self):
        from .settings_dialog import CartogenAiSettingsDialog
        dialog = CartogenAiSettingsDialog(self)
        if dialog.exec_():
            self.statusSignal.emit("Settings saved")
            # Keep the quick-switch dropdown in sync without re-triggering _on_provider_switch.
            provider_value = QgsSettings().value("cartogen_ai/provider", "openrouter")
            idx = self.provider_combo.findData(provider_value)
            if idx >= 0:
                self.provider_combo.blockSignals(True)
                self.provider_combo.setCurrentIndex(idx)
                self.provider_combo.blockSignals(False)
            if hasattr(self, '_agent_provider'):
                try:
                    self._agent_provider()
                except Exception as e:
                    print(f"[DockWidget] Agent refresh after settings save failed: {e}")
