# -*- coding: utf-8 -*-
"""
Dock Widget UI for Cartogen AI.
Provides dual-tab interface (Chat and Tasks/Notes Plan)
with non-blocking execution threads and file attachment handling.

CartogenAiDockWidget is the outer QDockWidget: it owns the cross-tab signals, the
agent_provider callable, and the header (title/provider switcher/settings button).
The two tabs (Chat, Activity) are separate QWidget classes in chat_tab_widget.py /
tasks_tab_widget.py -- Help moved out of the dock's own tabs and into the QGIS
Plugins menu (see plugin_main.py) per a 2026-09-12 real-session user report; its
HelpTabWidget class (help_tab_widget.py) is unchanged, just no longer permanently
embedded here.
docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md has the full rationale for the split and
what still needs verifying in a real QGIS session (this file cannot be imported or
run outside one -- no QGIS_AVAILABLE fallback -- so nothing here has run since the
split; see docs/RELEASE_SMOKE_TEST.md before shipping)."""

from qgis.PyQt.QtCore import Qt, pyqtSignal, QSize
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QComboBox, QScrollArea,
)
from qgis.core import QgsSettings

from .chat_formatting import build_dock_stylesheet
from .theme import extract_theme_palette
from .dock_constants import PROVIDER_CHOICES
from .icons import themed_icon
from .chat_tab_widget import ChatTabWidget
from .tasks_tab_widget import TasksTabWidget


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
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
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

        # Run only after the connect() calls above, not from ChatTabWidget.__init__ itself
        # (where it used to live) -- real live report, 2026-09-15, confirmed via a Python
        # Console screenshot showing an entirely empty chat log right after dock creation:
        # the automatic welcome message never appeared at all, first use, every time.
        # Root cause: _populate_initial_chat() emits receiveMessageSignal to show the
        # welcome/restored-history message, but when it ran inside init_ui() (called from
        # ChatTabWidget's own __init__, several lines above receiveMessageSignal.connect()
        # here), that signal had zero slots connected yet -- connect() can't happen until
        # self.chat_tab_widget exists, which requires ChatTabWidget.__init__ to have already
        # returned. A Qt signal emitted with no connected slots is just silently dropped, so
        # the welcome message vanished into nothing, every single time, while every later
        # emit (sent after this constructor fully returns) worked correctly -- exactly the
        # "only ever missing at first use" pattern reported.
        self.chat_tab_widget._populate_initial_chat()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._clamp_to_screen_if_floating()

    def _clamp_to_screen_if_floating(self):
        """Defensive guard against a floating dock ending up taller/wider than the available
        screen, or partly off-screen (real-session report, 2026-09-12: a long chat response
        left the input row not visible -- extensive headless testing across several hypotheses
        (small windows, bloated Activity-tab content, the exact reported multi-tool-call
        scenario) never reproduced a layout defect; the input row was always correctly present
        and positioned in every test. A floating window that's grown or drifted past the
        available screen height is a known Qt/Windows failure mode that produces exactly this
        symptom -- the input row is still there in the layout, just rendered below the visible
        screen area, invisible and unreachable without a manual resize this guard makes
        unnecessary). Only acts while floating -- a docked panel is already bounded by the main
        QGIS window's own geometry -- and only changes geometry that genuinely doesn't fit;
        idempotent, so this is safe to call from every resizeEvent without risk of runaway
        recursion (a window already inside the available geometry computes no change here)."""
        if not self.isFloating():
            return
        screen = self.screen() if hasattr(self, "screen") else None
        if screen is None:
            from qgis.PyQt.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        geo = self.geometry()
        new_width = min(geo.width(), available.width())
        new_height = min(geo.height(), available.height())
        new_x = max(available.left(), min(geo.x(), available.right() - new_width))
        new_y = max(available.top(), min(geo.y(), available.bottom() - new_height))
        if (new_width, new_height, new_x, new_y) != (geo.width(), geo.height(), geo.x(), geo.y()):
            self.setGeometry(new_x, new_y, new_width, new_height)

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

        # secondaryButton is outlined/transparent (build_dock_stylesheet), not accent-filled
        # like the input row's iconButton trio -- so this icon takes the palette's normal text
        # color, not highlighted_text. UI/chat redesign workstream, 2026-09-12: replaces the
        # plain "⚙" emoji with the same theme-reactive SVG convention as chat_tab_widget.py's
        # icons (ui/icons.py).
        _header_palette = extract_theme_palette()
        _settings_icon_fg = (_header_palette or {}).get("text", "#000000")
        self.settings_btn = QPushButton(" Settings")
        self.settings_btn.setIcon(themed_icon("settings", _settings_icon_fg))
        self.settings_btn.setIconSize(QSize(14, 14))
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

        # Wrapped in a QScrollArea rather than added to tab_widget directly:
        # QTabWidget/QStackedWidget sizes the WHOLE dock to its tallest tab's natural size
        # hint, not just the currently visible tab. With this tab's substantial content
        # (progress bar, history, task list, inspector, memory panel) sized directly, that
        # was forcing the entire QGIS window taller than the screen regardless of which tab
        # was actually showing -- including the unrelated Chat tab. A QScrollArea decouples
        # the tab's reported size from its content's full size; content that doesn't fit
        # scrolls VERTICALLY instead of forcing growth. Horizontal scrolling is explicitly
        # turned off below -- a real user report (screenshots, UI real-session-feedback
        # fixes, 2026-09-12) showed both scrollbars appearing at once, which reads as
        # cluttered/broken; content should wrap within the available width, never need
        # horizontal scroll, so this makes that structurally impossible rather than tuning
        # around one window size.
        self.tasks_tab_widget = TasksTabWidget(dock=self)
        tasks_scroll = QScrollArea()
        tasks_scroll.setWidgetResizable(True)
        tasks_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        tasks_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tasks_scroll.setWidget(self.tasks_tab_widget)
        # "Activity" -- renamed from "Tasks & Notes" (real bug, found from the same user
        # report: Qt treats a bare "&" followed by a space as a mnemonic it can't resolve,
        # rendering as a stray underscore, e.g. "Tasks _Notes" -- visible in the screenshots).
        # The new name sidesteps the ampersand entirely rather than just escaping it, and per
        # the user's own choice among the options offered, reads better than spelling out
        # "Tasks and Notes" for what's really one activity feed (live plan + stored memory).
        self.tab_widget.addTab(tasks_scroll, "📋 Activity")

        # Help used to be a permanent 3rd tab here (HelpTabWidget still exists as a class --
        # see plugin_main.py's show_help(), which now opens it in a QDialog from the QGIS
        # Plugins menu instead). Per the same user report: a reference document doesn't need
        # to occupy dock space at all times, and moving it to the menu also gave a natural
        # home for a plugin-version entry (see plugin_main.py).

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
        if dialog.exec():
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
