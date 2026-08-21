# -*- coding: utf-8 -*-
"""
Dock Widget UI for Cartogen AI.
Provides dual-tab interface (Chat and Tasks/Memory Plan)
with non-blocking execution threads and file attachment handling.
"""

import threading
import traceback
import os

from qgis.PyQt.QtCore import Qt, pyqtSignal, pyqtSlot
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFileDialog, QTextBrowser, QPushButton, QTextEdit, QTabWidget,
    QListWidget, QListWidgetItem, QGroupBox, QSplitter, QComboBox,
    QProgressBar, QLineEdit, QMessageBox, QApplication, QScrollArea
)
from qgis.core import QgsSettings

from .chat_formatting import (
    render_markdown, _relative_time, derive_bubble_colors, now_iso, escape_plain_text,
    render_tool_step_html, build_dock_stylesheet,
)
from .attachments import read_attached_file as _read_attached_file

PROVIDER_CHOICES = [
    ("OpenRouter", "openrouter"),
    ("Gemini", "gemini"),
    ("Ollama", "ollama"),
    ("OpenAI", "openai"),
    ("Claude", "claude"),
]

# Module-level (not a local in init_ui) so the Help tab can list the same example prompts as
# the quick suggestion chips without a second, driftable copy of the text.
QUICK_SUGGESTION_CHIPS = [
    ("💡 List layers", "List all layers in the project."),
    ("💡 Calculate area", "Calculate the area for the active layer."),
    ("💡 Style by attribute", "Suggest and apply a colorblind-safe style for the active layer based on its attributes."),
    ("💡 Style raster layer", "Apply a color ramp or contrast stretch to the active raster layer so it isn't flat/unstretched."),
    ("💡 Export to GeoJSON", "Export the active layer to GeoJSON."),
]


def _extract_theme_palette():
    """Reads the live QGIS application's actual palette so chat bubble colors
    follow whatever theme QGIS is really running (OS dark mode, a QGIS theme,
    a custom stylesheet) instead of a guessed static light/dark split. Thin
    and QGIS-dependent on purpose -- see chat_formatting.derive_bubble_colors
    for the pure-Python color logic this feeds, which is what's unit tested
    (this function can't be, since dock_widget.py isn't importable outside a
    real QGIS process at all -- see the qgis.PyQt import at the top of this
    file, which has no QGIS_AVAILABLE-style fallback)."""
    from qgis.PyQt.QtGui import QPalette
    app = QApplication.instance()
    if app is None:
        return None
    p = app.palette()
    return {
        "window": p.color(QPalette.Window).name(),
        "alt_base": p.color(QPalette.AlternateBase).name(),
        "base": p.color(QPalette.Base).name(),
        "text": p.color(QPalette.WindowText).name(),
        "highlight": p.color(QPalette.Highlight).name(),
        "highlighted_text": p.color(QPalette.HighlightedText).name(),
        "muted_text": p.color(QPalette.Disabled, QPalette.WindowText).name(),
        "mid": p.color(QPalette.Mid).name(),
    }


def _theme_colors():
    return derive_bubble_colors(_extract_theme_palette())


class ChatInputEdit(QTextEdit):
    """Multi-line input that sends on Enter and inserts a newline on Shift+Enter."""
    sendRequested = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self.sendRequested.emit()
            return
        super().keyPressEvent(event)


class CartogenAiDockWidget(QDockWidget):
    receiveMessageSignal = pyqtSignal(str, str)
    statusSignal = pyqtSignal(str)
    usageSignal = pyqtSignal(str)
    planUpdatedSignal = pyqtSignal(dict)
    toolStepSignal = pyqtSignal(str, str, str)
    # The refinement call hits the network -- must never block the UI thread,
    # same reasoning as settings_dialog.py's modelsFetchedSignal/_fetch_models.
    # Emitted from the background worker thread in _start_refinement(); Qt
    # auto-queues delivery to _on_refinement_fetched on the main thread since
    # this widget lives there. Payload is (original_text, result_dict), where
    # result_dict is either a valid parsed refinement dict or {"error": ...}.
    refinementFetchedSignal = pyqtSignal(str, dict)

    def __init__(self, agent_provider=None, parent=None):
        super().__init__("Cartogen AI", parent)
        self.setObjectName("CartogenAiDockWidget")
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self._agent_provider = agent_provider
        self._active_highlights = []  # keeps QgsHighlight objects alive until their timer fires
        self._active_task = None  # the running QgsTask, if any -- lets _stop_current_task cancel it
        self._pending_refinement_text = None  # original text while the refinement panel is shown

        self.receiveMessageSignal.connect(self._add_message)
        self.statusSignal.connect(self._set_status)
        self.usageSignal.connect(self._set_usage_label)
        self.planUpdatedSignal.connect(self._render_plan)
        self.toolStepSignal.connect(self._add_tool_step)
        self.refinementFetchedSignal.connect(self._on_refinement_fetched)

        from ..agent.scheduler import get_scheduler
        get_scheduler().workflow_tick_completed.connect(self._on_scheduled_workflow_tick)

        self.init_ui()

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

        # TAB 1: Chat Interface
        self.chat_tab = QWidget()
        chat_layout = QVBoxLayout(self.chat_tab)
        chat_layout.setContentsMargins(4, 4, 4, 4)

        self.chat_browser = QTextBrowser()
        self.chat_browser.setOpenExternalLinks(True)
        chat_layout.addWidget(self.chat_browser)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        chat_layout.addWidget(self.status_label)

        # Session token usage indicator (docs/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md
        # SS3.2, docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md's sibling task). Deliberately
        # separate from status_label (which status_label's own callers clear to "" between
        # turns via statusSignal.emit("")) -- this one should persist and accumulate across
        # the whole session, not blink in and out with each turn's status text. Hidden
        # (empty text) until the first successful response reports usage -- see
        # CartogenAi.get_session_usage_text()'s docstring for why nothing is shown before
        # that instead of a misleading "0 tokens".
        self.usage_label = QLabel("")
        self.usage_label.setStyleSheet("color: gray; font-size: 10px;")
        self.usage_label.setToolTip(
            "Approximate token usage for this session, from provider-reported counts. "
            "Not shown for providers/models that don't report usage. No dollar-cost estimate "
            "is shown -- accurate per-model pricing across 5 providers isn't something this "
            "plugin can keep reliably current."
        )
        chat_layout.addWidget(self.usage_label)

        # Dependency status -- this plugin never runs pip itself (see
        # agent/deps.py docstring); missing optional packages are reported
        # via a message in chat on open, with instructions to install via
        # qpip or manually. Stashed here, shown after the welcome message
        # further down in init_ui() so it doesn't get buried under it.
        from ..agent.deps import get_dependency_warning_message
        self._dep_warning = get_dependency_warning_message()

        # Quick Suggestion Chips
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(4)
        for chip_label, chip_template in QUICK_SUGGESTION_CHIPS:
            chip_btn = QPushButton(chip_label)
            chip_btn.setObjectName("chipButton")
            chip_btn.clicked.connect(lambda checked=False, t=chip_template: self._send_quick_prompt(t))
            chips_layout.addWidget(chip_btn)
        chips_layout.addStretch()
        chat_layout.addLayout(chips_layout)

        # Prompt Refinement panel -- separate widget above the input row
        # (docs/PROMPT_REFINEMENT_LAYER_SPEC.md §6/§11.1: decided as a
        # separate panel rather than inline chat bubbles, so these cards
        # never touch conversation_history or chat_persistence.py at all --
        # they're not chat messages). Hidden by default; shown only once
        # send_message() decides a message should be refined and a valid
        # response comes back. Modeled on the confirm_btn/PREVIEW_READY
        # gate's explicit-button, nothing-auto-proceeds interaction language.
        self.refinement_panel = QGroupBox()
        self.refinement_panel.setVisible(False)
        refinement_layout = QVBoxLayout(self.refinement_panel)

        refinement_hint = QLabel("Refined prompt suggestions -- pick one, edit first, or send as typed:")
        refinement_hint.setStyleSheet("color: gray; font-size: 11px;")
        refinement_layout.addWidget(refinement_hint)

        cards_row = QHBoxLayout()
        self._refinement_cards = {}
        for card_id in ("A", "B"):
            card_box = QGroupBox()
            card_layout = QVBoxLayout(card_box)

            label_lbl = QLabel()
            label_lbl.setStyleSheet("font-weight: bold;")
            card_layout.addWidget(label_lbl)

            prompt_lbl = QLabel()
            prompt_lbl.setWordWrap(True)
            card_layout.addWidget(prompt_lbl)

            rationale_lbl = QLabel()
            rationale_lbl.setWordWrap(True)
            rationale_lbl.setStyleSheet("color: gray; font-size: 11px;")
            card_layout.addWidget(rationale_lbl)

            card_btn_row = QHBoxLayout()
            use_btn = QPushButton("Use this")
            use_btn.clicked.connect(lambda checked=False, cid=card_id: self._use_refinement_card(cid))
            edit_btn = QPushButton("Edit first")
            edit_btn.clicked.connect(lambda checked=False, cid=card_id: self._edit_refinement_card(cid))
            card_btn_row.addWidget(use_btn)
            card_btn_row.addWidget(edit_btn)
            card_layout.addLayout(card_btn_row)

            cards_row.addWidget(card_box)
            self._refinement_cards[card_id] = {"label": label_lbl, "prompt": prompt_lbl, "rationale": rationale_lbl}
        refinement_layout.addLayout(cards_row)

        send_as_typed_btn = QPushButton("Send as typed instead")
        send_as_typed_btn.clicked.connect(self._send_refinement_original)
        refinement_layout.addWidget(send_as_typed_btn)

        chat_layout.addWidget(self.refinement_panel)

        # Input Area
        input_layout = QHBoxLayout()
        self.attach_btn = QPushButton("📎")
        self.attach_btn.setObjectName("iconButton")
        self.attach_btn.setFixedSize(30, 30)
        self.attach_btn.clicked.connect(self.attach_file)

        self.input_edit = ChatInputEdit()
        self.input_edit.setFixedHeight(55)
        self.input_edit.setPlaceholderText("Ask me anything about your layers... (Enter to send, Shift+Enter for new line)")
        self.input_edit.sendRequested.connect(self.send_message)

        self.send_btn = QPushButton("➤")
        self.send_btn.setObjectName("iconButton")
        self.send_btn.setFixedSize(30, 30)
        self.send_btn.clicked.connect(self.send_message)

        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setObjectName("iconButton")
        self.stop_btn.setFixedSize(30, 30)
        self.stop_btn.setToolTip("Stop the current request")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_current_task)

        input_layout.addWidget(self.attach_btn)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(self.send_btn)
        input_layout.addWidget(self.stop_btn)
        chat_layout.addLayout(input_layout)

        self.tab_widget.addTab(self.chat_tab, "💬 Chat")

        # TAB 2: Tasks & Memory Tracker
        # Wrapped in a QScrollArea (see the addTab call below) rather than added to
        # tab_widget directly: QTabWidget/QStackedWidget sizes the WHOLE dock to its
        # tallest tab's natural size hint, not just the currently visible tab. With this
        # tab's now-substantial content (progress bar, history, task list, inspector,
        # memory panel) sized directly, that was forcing the entire QGIS window taller
        # than the screen regardless of which tab was actually showing -- including the
        # unrelated Chat tab. A QScrollArea decouples the tab's reported size from its
        # content's full size; content that doesn't fit scrolls instead of forcing growth.
        self.tasks_tab = QWidget()
        tasks_layout = QVBoxLayout(self.tasks_tab)
        tasks_layout.setContentsMargins(4, 4, 4, 4)

        self._viewing_history = False
        self._last_seen_plan_title = None
        self._current_code_snippet = ""

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
        memory_header.addWidget(QLabel("<b>🧠 Spatial Memory & Notes</b>"))
        self.clear_memory_btn = QPushButton("🗑 Clear Project Memory")
        self.clear_memory_btn.setObjectName("dangerButton")
        self.clear_memory_btn.clicked.connect(self._clear_project_memory_clicked)
        memory_header.addStretch()
        memory_header.addWidget(self.clear_memory_btn)
        tasks_layout.addLayout(memory_header)

        self.memory_search_edit = QLineEdit()
        self.memory_search_edit.setPlaceholderText("🔎 Filter memory notes...")
        self.memory_search_edit.textChanged.connect(self._on_memory_search_changed)
        tasks_layout.addWidget(self.memory_search_edit)

        self.memory_browser = QTextBrowser()
        # Bounded on both ends -- see the comment on task_list_widget's setMaximumHeight
        # above for why an unbounded-growth widget here breaks the whole window's sizing.
        # Bigger than the original 100px cap (that was the "too cramped" complaint this
        # tab was revamped to fix) but still capped -- the QScrollArea wrapper (below) is
        # what actually prevents this from forcing the window taller; this cap just keeps
        # it from dominating this tab's own scrollable area.
        self.memory_browser.setMinimumHeight(120)
        self.memory_browser.setMaximumHeight(220)
        self.memory_browser.setPlaceholderText("Spatial Memory & Project Notes...")
        self._raw_memory_context = ""
        tasks_layout.addWidget(self.memory_browser, stretch=1)

        tasks_scroll = QScrollArea()
        tasks_scroll.setWidgetResizable(True)
        tasks_scroll.setFrameShape(QScrollArea.NoFrame)
        tasks_scroll.setWidget(self.tasks_tab)
        self.tab_widget.addTab(tasks_scroll, "📋 Tasks & Memory")

        # TAB 3: Help -- same QScrollArea wrapping and same reasoning as the Tasks &
        # Memory tab above.
        self.help_tab = QWidget()
        help_layout = QVBoxLayout(self.help_tab)
        help_layout.setContentsMargins(4, 4, 4, 4)
        help_browser = QTextBrowser()
        help_browser.setOpenExternalLinks(True)
        help_browser.setHtml(self._build_help_html())
        help_layout.addWidget(help_browser)

        help_scroll = QScrollArea()
        help_scroll.setWidgetResizable(True)
        help_scroll.setFrameShape(QScrollArea.NoFrame)
        help_scroll.setWidget(self.help_tab)
        self.tab_widget.addTab(help_scroll, "❓ Help")

        # Modern, theme-adaptive QSS pass over every widget in this dock --
        # see chat_formatting.build_dock_stylesheet for the actual rules and
        # why it's built from the live palette instead of hardcoded colors.
        # A handful of buttons keep meaning-carrying colors (success green on
        # Confirm, danger red on the two Clear buttons) via objectName
        # variants defined in that same stylesheet, set on each button above.
        container.setStyleSheet(build_dock_stylesheet(_extract_theme_palette()))

        self._populate_initial_chat()

    def _build_help_html(self):
        """Static help content -- provider list and example prompts are built from the same
        source data as the rest of the UI (PROVIDER_CHOICES, QUICK_SUGGESTION_CHIPS) rather
        than a second, driftable copy of the text."""
        provider_items = "".join(f"<li>{label}</li>" for label, _ in PROVIDER_CHOICES)
        example_items = "".join(
            f"<li>{template}</li>" for _, template in QUICK_SUGGESTION_CHIPS
        )
        return f"""
        <h3>🗺️ Cartogen AI — Help</h3>
        <p>Ask questions or give instructions in plain English in the <b>Chat</b> tab. The assistant
        can inspect your loaded layers, run real PyQGIS/Processing operations, and build maps for
        you — every action it takes is visible in the <b>Tasks &amp; Memory</b> tab.</p>

        <h4>Getting started</h4>
        <ol>
        <li>Open <b>Settings</b> (top-right gear icon) and pick a provider and enter its API key.</li>
        <li>Type a request in the chat box and press Enter (Shift+Enter for a new line).</li>
        <li>For anything that edits or deletes data, you'll be asked to confirm in the
        <b>Tasks &amp; Memory</b> tab before it actually runs.</li>
        </ol>

        <h4>Supported AI providers</h4>
        <ul>{provider_items}</ul>
        <p>OpenRouter (openrouter.ai) offers a genuinely free tier covering many models.
        Ollama runs fully locally, no key needed.</p>

        <h4>Example things to ask</h4>
        <ul>{example_items}
        <li>"Create a buffer 500m around the hospital layer."</li>
        <li>"Map all the foreign embassies in Jordan."</li>
        <li>"Diagnose topology problems in the parcels layer."</li>
        </ul>

        <h4>Safety</h4>
        <p>Destructive actions (removing a layer, changing attribute values) always require an
        explicit click on <b>Confirm &amp; Apply Edit</b> in the Tasks &amp; Memory tab — the AI
        cannot apply them on its own.</p>
        """

    def _populate_initial_chat(self):
        """Shows the welcome message, or restores this project's saved conversation
        (agent/chat_persistence.py) if one exists. Called on first load, and again
        by refresh_chat_for_project_change() whenever the active QGIS project changes."""
        restored = False
        if self._agent_provider:
            try:
                agent = self._agent_provider()
                history = getattr(agent, "conversation_history", []) if agent else []
                for entry in history:
                    role = entry.get("role")
                    content = entry.get("content")
                    if not content or role not in ("user", "assistant") or not isinstance(content, str):
                        continue
                    self.receiveMessageSignal.emit("user" if role == "user" else "ai", content)
                    restored = True
            except Exception:
                pass

        if restored:
            self.receiveMessageSignal.emit("ai", "_(Restored previous conversation for this project.)_")
        else:
            self.receiveMessageSignal.emit(
                "ai",
                "Hello! I'm Cartogen AI 🗺️\n\n"
                "I plan multi-step spatial tasks, call the right tools, and execute real operations "
                "against your open project -- with spatial memory and every step inspectable.\n\n"
                "Ask me to analyze, buffer, style, or process your layers!"
            )

        if self._dep_warning:
            self.receiveMessageSignal.emit("ai", self._dep_warning)

    def refresh_chat_for_project_change(self):
        """Called by CartogenAi (see cartogen_ai.py) when QgsProject fires
        readProject/cleared -- the dock and its cached agent instance persist
        across project switches, so the visible chat log needs to be reloaded
        to match the newly-active project's saved history instead of showing
        the previous project's conversation."""
        self.chat_browser.clear()
        self._populate_initial_chat()

    @pyqtSlot(str, str)
    def _add_message(self, role, text):
        # Theme-aware colors (see chat_formatting.derive_bubble_colors) so bubbles
        # read correctly in both light and dark QGIS themes instead of a hardcoded
        # light-blue/light-grey pair. timestamp is "now" at render time -- accurate
        # for live messages; restored chat history has no stored per-message
        # timestamp to draw on (see agent/chat_persistence.py), so it shows "just
        # now" too rather than a fabricated time, a known, accepted limitation.
        colors = _theme_colors()
        timestamp = _relative_time(now_iso())
        # Table-based alignment, not a floated div -- Qt's rich-text engine
        # supports table cell alignment reliably; float-based layout is flaky.
        if role == "user":
            body = escape_plain_text(text)
            label, align = "You", "right"
            bg = colors["user_bg"]
        else:
            body = render_markdown(text)
            label, align = "🗺️ Cartogen", "left"
            bg = colors["agent_bg"]

        html = f"""
        <table width="100%" style="margin:6px 0;"><tr><td align="{align}">
        <table align="{align}" style="max-width:85%;background-color:{bg};
            border:1px solid {colors['border']};border-radius:8px;"><tr><td style="padding:8px 12px;">
        <div style="font-size:11px;font-weight:bold;color:{colors['text']};margin-bottom:3px;">
            {label} <span style="font-weight:normal;color:{colors['subtle']};">&middot; {timestamp}</span>
        </div>
        <div style="color:{colors['text']};font-size:13px;">{body}</div>
        </td></tr></table>
        </td></tr></table>
        """

        self.chat_browser.append(html)
        self.input_edit.clear()
        self.send_btn.setEnabled(True)
        self.status_label.setText("")

    @pyqtSlot(str)
    def _set_status(self, text):
        self.status_label.setText(text)

    @pyqtSlot(str)
    def _set_usage_label(self, text):
        self.usage_label.setText(text)

    @pyqtSlot(str, str, str)
    def _add_tool_step(self, name, status, error):
        """Live, per-tool-call progress line appended inline in the chat as
        the agent works -- see agent.py's run() tool_step_callback. Previously
        there was zero visibility into a multi-tool-call turn beyond the
        single one-time "Thinking..."/provider status; this fires twice per
        tool call (once when it starts, once when it finishes), giving the
        same kind of live step feedback modern AI chat apps show for tool use.
        Deliberately a small inline div, not a full message bubble via
        _add_message -- a turn with many tool calls shouldn't visually
        compete with the actual conversation."""
        colors = _theme_colors()
        self.chat_browser.append(render_tool_step_html(name, status, error or None, colors))

    _STATUS_STYLES = {
        "TODO": ("⚪", "#666666", "#f1f3f6"),
        "IN_PROGRESS": ("🟡", "#8a6d00", "#fff8e1"),
        "PREVIEW_READY": ("🔍", "#01579b", "#e3f0ff"),
        "CONFIRMED": ("🔷", "#01579b", "#e3f0ff"),
        "DONE": ("🟢", "#1b5e20", "#e8f5e9"),
        "FAILED": ("🔴", "#b71c1c", "#fdecea"),
    }

    def _build_task_item_widget(self, task):
        status = task.get("status", "TODO")
        icon, text_color, bg_color = self._STATUS_STYLES.get(status, self._STATUS_STYLES["TODO"])
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
        label.setTextFormat(Qt.RichText)
        return label

    def _render_plan(self, plan_data):
        """Draws the given plan snapshot into the task list/progress bar. Used for both the
        live plan (gated by _viewing_history in _on_live_plan_updated) and read-only history
        snapshots selected from plan_history_combo."""
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
            item.setData(Qt.UserRole, task)
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

    @pyqtSlot(dict)
    def _on_live_plan_updated(self, plan_data):
        """Connected to task_manager.plan_updated. Refreshes the history dropdown whenever a
        new plan starts (title change), but only re-renders the visible task list if the user
        isn't currently browsing a past plan -- otherwise live updates would yank them back to
        the current plan mid-browse."""
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

        task = items[0].data(Qt.UserRole) or {}
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
            print(f"[DockWidget] Preview highlight failed: {e}")

    def _confirm_selected_task(self):
        items = self.task_list_widget.selectedItems()
        if not items:
            return
        task = items[0].data(Qt.UserRole) or {}
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
                    self.receiveMessageSignal.emit("ai", f"✅ **Confirmed & Executed Task {task_id}:** {msg}")
        self.confirm_btn.setEnabled(False)
        self.retry_task_btn.setEnabled(False)
        self.edit_task_btn.setEnabled(False)
        self.cancel_task_btn.setEnabled(False)

    def _cancel_selected_task(self):
        items = self.task_list_widget.selectedItems()
        if not items:
            return
        task = items[0].data(Qt.UserRole) or {}
        task_id = task.get("id")
        if self._agent_provider:
            agent = self._agent_provider()
            if agent and hasattr(agent, "task_manager"):
                agent.task_manager.update_task(task_id, "FAILED", "Cancelled by User")
                self.receiveMessageSignal.emit("ai", f"❌ **Cancelled Task {task_id}:** {task.get('description')}")
        self.confirm_btn.setEnabled(False)
        self.retry_task_btn.setEnabled(False)
        self.edit_task_btn.setEnabled(False)
        self.cancel_task_btn.setEnabled(False)

    def _retry_selected_task(self):
        items = self.task_list_widget.selectedItems()
        if not items:
            return
        task = items[0].data(Qt.UserRole) or {}
        task_id = task.get("id")
        desc = task.get("description", "")
        result = task.get("result", "")
        prompt = (
            f"Retry task {task_id}: {desc}. It previously failed with: {result}"
            if result else f"Retry task {task_id}: {desc}."
        )
        self.input_edit.setPlainText(prompt)
        self.send_message()

    def _edit_selected_task(self):
        """Pragmatic version of step-level re-editability: pre-fills the chat box with an
        editable prompt for this task (any status, not just FAILED like Retry) but does NOT
        auto-send -- the user edits the parameters/details themselves, then sends when ready.
        Avoids building per-tool-schema dynamic parameter forms, a much larger UI subsystem."""
        items = self.task_list_widget.selectedItems()
        if not items:
            return
        task = items[0].data(Qt.UserRole) or {}
        task_id = task.get("id")
        desc = task.get("description", "")
        self.input_edit.setPlainText(f"Redo task {task_id} ({desc}) but with these changes: ")
        self.input_edit.setFocus()

    def _copy_code_snippet(self):
        if not self._current_code_snippet:
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._current_code_snippet)
            self.statusSignal.emit("Code snippet copied to clipboard.")

    def _clear_plan_clicked(self):
        if not self._agent_provider:
            return
        agent = self._agent_provider()
        if not (agent and hasattr(agent, "task_manager")) or not agent.task_manager.tasks:
            return
        reply = QMessageBox.question(
            self, "Clear Plan", "Archive the current plan and reset the tracker?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            agent.task_manager.clear_plan()

    def _clear_project_memory_clicked(self):
        if not self._agent_provider:
            return
        agent = self._agent_provider()
        if not (agent and hasattr(agent, "memory_manager")):
            return
        reply = QMessageBox.question(
            self, "Clear Project Memory", "Permanently clear all stored project notes for this project?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            agent.memory_manager.clear_project_notes()
            self._raw_memory_context = agent.memory_manager.get_formatted_memory_context()
            self._apply_memory_filter()

    def _on_memory_search_changed(self, _text):
        self._apply_memory_filter()

    def _apply_memory_filter(self):
        query = self.memory_search_edit.text().strip().lower()
        if not query:
            self.memory_browser.setText(self._raw_memory_context)
            return
        matched = [line for line in self._raw_memory_context.split("\n") if query in line.lower()]
        self.memory_browser.setText("\n".join(matched) if matched else "(no matches)")

    def send_message(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return

        # A fresh send attempt abandons any still-open refinement panel from
        # a previous message -- the practical equivalent of spec §7's "user
        # closes the card without choosing" (this UI has no separate close/X
        # affordance; typing something else and hitting Send again is how a
        # user actually walks away from it). Without this, a stale panel and
        # its _pending_refinement_text would linger orphaned.
        if self.refinement_panel.isVisible():
            self._hide_refinement_panel()

        from ..agent.prompt_refiner import should_refine, is_refinement_enabled
        agent = self._agent_provider() if self._agent_provider else None
        client = getattr(agent, "client", None) if agent is not None else None

        # docs/PROMPT_REFINEMENT_LAYER_SPEC.md: an optional, opt-in step that
        # rewrites this text into two better-specified candidates before it
        # reaches _dispatch_message()/agent.run(). Every failure mode here
        # (disabled, too-short message, no client available) falls straight
        # through to the exact same dispatch a message would get today.
        if client is not None and should_refine(text, is_refinement_enabled()):
            self._start_refinement(text, client)
            return

        self._dispatch_message(text)

    def _start_refinement(self, text, client):
        """Runs the refinement API call on a background thread -- it's a
        real network call and must never block the UI thread, same reasoning
        as settings_dialog.py's modelsFetchedSignal/_fetch_models. Delivers
        the result back via refinementFetchedSignal, which Qt auto-queues
        onto the main thread for _on_refinement_fetched."""
        import threading
        from ..agent.prompt_refiner import refine, get_user_profile

        self.statusSignal.emit("Refining prompt...")
        profile = get_user_profile()

        def worker():
            result = refine(text, profile, client)
            try:
                self.refinementFetchedSignal.emit(text, result)
            except RuntimeError:
                pass  # widget was closed/deleted before the call finished

        threading.Thread(target=worker, daemon=True).start()

    def _on_scheduled_workflow_tick(self, preset_name, summary_text):
        """Fires when a background recurring workflow (see
        agent/tools/monitoring_tools.py's schedule_recurring_workflow)
        completes a tick -- posts the change summary into chat like an
        assistant message, without spending a real API call on it."""
        self._add_message("assistant", summary_text)

    def _on_refinement_fetched(self, original_text, result):
        """Every failure (API error, malformed/incomplete JSON) degrades to
        sending the original text unmodified (spec §7) -- never blocks or
        errors the user's turn because this helper call misbehaved."""
        self.statusSignal.emit("")
        if not isinstance(result, dict) or "error" in result or "recommendations" not in result:
            self._dispatch_message(original_text)
            return
        self._show_refinement_panel(original_text, result["recommendations"])

    def _show_refinement_panel(self, original_text, recommendations):
        self._pending_refinement_text = original_text
        for rec in recommendations:
            card = self._refinement_cards.get(rec.get("id"))
            if card is None:
                continue
            card["label"].setText(rec.get("label") or rec.get("id", ""))
            card["prompt"].setText(rec.get("refined_prompt", ""))
            card["rationale"].setText(rec.get("rationale", ""))
        self.refinement_panel.setVisible(True)

    def _hide_refinement_panel(self):
        self.refinement_panel.setVisible(False)
        self._pending_refinement_text = None

    def _use_refinement_card(self, card_id):
        card = self._refinement_cards.get(card_id)
        chosen_text = card["prompt"].text() if card else ""
        self._hide_refinement_panel()
        if chosen_text:
            self._dispatch_message(chosen_text)

    def _edit_refinement_card(self, card_id):
        """Opens the refined text in ChatInputEdit for the user to modify
        before sending -- never auto-sends a rewritten prompt the user
        hasn't seen (spec §6), mirroring the existing pre-fill-without-send
        pattern already used elsewhere in this file (e.g. the Edit & Resend
        task action's setPlainText call, without a following send_message())."""
        card = self._refinement_cards.get(card_id)
        refined_prompt = card["prompt"].text() if card else ""
        self._hide_refinement_panel()
        if refined_prompt:
            self.input_edit.setPlainText(refined_prompt)
            self.input_edit.setFocus()

    def _send_refinement_original(self):
        original_text = self._pending_refinement_text
        self._hide_refinement_panel()
        if original_text:
            self._dispatch_message(original_text)

    def _dispatch_message(self, text):
        """The actual send path -- unchanged from send_message()'s original
        body. Shared by the refinement skip-path (send_message() calls this
        directly) and the post-choice path (a card's 'Use this', 'Send as
        typed instead', or the plain non-refined flow all funnel here with
        one final chosen_text string). conversation_history sees only this
        text -- no trace of a refinement step survives downstream, per spec
        §3/§11.2's decision."""
        # receiveMessageSignal is a direct (same-thread) connection, so this emit
        # runs _add_message synchronously right here -- and _add_message always
        # re-enables send_btn (it's also used for messages that aren't part of a
        # running task). So the "disable while a task is in flight" state has to
        # be set AFTER this emit, not before, or it gets immediately clobbered.
        self.receiveMessageSignal.emit("user", text)
        self.statusSignal.emit("Thinking...")
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        agent = None
        if self._agent_provider:
            agent = self._agent_provider()

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
                    print(f"[DockWidget] Failed to connect plan_updated signal: {e}")
            self._on_live_plan_updated(agent.task_manager.get_plan())
            self._raw_memory_context = agent.memory_manager.get_formatted_memory_context()
            self._apply_memory_filter()

        from ..agent.task_runner import run_agent_task
        from ..agent.map_context import get_map_context_summary

        # Gathered here, on the main thread, before the background QgsTask
        # starts -- QgsProject/layers aren't thread-safe to touch from run().
        map_ctx = get_map_context_summary()

        def on_complete(response, err):
            self._active_task = None
            self.stop_btn.setEnabled(False)
            if err:
                self.receiveMessageSignal.emit("ai", f"**Error:** {err}")
                # A multi-tool-call turn can accumulate usage on earlier,
                # successful client.complete() calls before a later one in the
                # same turn errors out -- refresh here too so that usage isn't
                # silently dropped from the displayed total just because the
                # turn as a whole ended in an error.
                self._refresh_usage_label(agent)
            else:
                self.receiveMessageSignal.emit("ai", response if response else "_(empty response)_")
                self._after_successful_response(agent, response)

        def on_status(msg):
            self.statusSignal.emit(msg)

        def on_tool_step(name, status, error):
            # Called from the background task thread -- emit() is thread-safe;
            # Qt queues the connected slot (_add_tool_step) onto this widget's
            # own (main GUI) thread automatically, same as statusSignal/
            # receiveMessageSignal already rely on.
            self.toolStepSignal.emit(name, status, error or "")

        # Keep a strong reference to the running task on self — QgsApplication.taskManager()
        # does not guarantee the Python-side wrapper survives otherwise, which can cause the
        # task to silently never execute or never report completion.
        self._active_task = run_agent_task(
            agent=agent,
            user_text=text,
            description="Cartogen AI Analysis",
            on_complete=on_complete,
            on_status=on_status,
            map_context=map_ctx,
            on_tool_step=on_tool_step,
        )

    def _stop_current_task(self):
        """Cancels the in-flight request. This is cooperative, not instant --
        it sets QgsTask's isCanceled() flag, which agent.run()'s tool-calling
        loop checks once per iteration (see agent/agent.py's should_stop
        param), so it stops before the NEXT LLM call/tool step rather than
        interrupting whichever one is already in flight. stop_btn stays
        disabled until on_complete actually fires so the UI doesn't claim
        it's stopped before it really has."""
        if self._active_task is None:
            return
        try:
            self._active_task.cancel()
        except Exception as e:
            print(f"[DockWidget] Failed to cancel task: {e}")
        self.stop_btn.setEnabled(False)
        self.statusSignal.emit("Stopping...")

    def _refresh_usage_label(self, agent):
        """Updates the session token-usage indicator from the agent's running
        total. Safe to call from any thread (goes through usageSignal, same
        pattern as statusSignal/_set_status) -- both call sites need this:
        _after_successful_response runs on the main thread, but _analyze_file
        runs on a background threading.Thread. get_session_usage_text()
        returns None until at least one call has actually reported usage, so
        this is a no-op (label stays empty) for the common early case of a
        provider that never reports it, rather than ever showing a fabricated
        count."""
        if agent is None or not hasattr(agent, "get_session_usage_text"):
            return
        try:
            text = agent.get_session_usage_text()
        except Exception:
            return
        self.usageSignal.emit(text or "")

    def _after_successful_response(self, agent, response_text):
        """Runs on the main thread (called from on_complete, itself invoked
        from AgentQgsTask.finished()). Persists chat history and flashes any
        layer the reply mentions on the canvas."""
        if agent is None:
            return

        self._refresh_usage_label(agent)

        try:
            from ..agent.chat_persistence import save_chat_history
            save_chat_history(getattr(agent, "conversation_history", []))
        except Exception as e:
            print(f"[DockWidget] Failed to save chat history: {e}")

        try:
            from qgis.core import QgsProject
            from qgis.utils import iface
            from .canvas_highlight import flash_layer_extent, find_mentioned_layers

            layers = list(QgsProject.instance().mapLayers().values())
            matched = find_mentioned_layers(response_text or "", layers)

            def _on_expired(highlight):
                if highlight in self._active_highlights:
                    self._active_highlights.remove(highlight)

            for layer in matched:
                highlight = flash_layer_extent(iface, layer, on_expired=_on_expired)
                if highlight is not None:
                    self._active_highlights.append(highlight)
        except Exception as e:
            print(f"[DockWidget] Canvas highlight failed: {e}")

    def _send_quick_prompt(self, template):
        """Handler for the suggestion chips -- fills in the active layer's
        name where the template refers to it generically, then sends it."""
        prompt = template
        try:
            from qgis.utils import iface
            active = iface.activeLayer() if iface else None
            if active and "the active layer" in template:
                prompt = template.replace("the active layer", f"the layer '{active.name()}'")
        except Exception:
            pass
        self.input_edit.setPlainText(prompt)
        self.send_message()

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

    def attach_file(self):
        filters = (
            "Supported files (*.pdf *.docx *.png *.jpg *.jpeg *.csv *.xlsx);;"
            "PDF (*.pdf);;Word (*.docx);;Images (*.png *.jpg *.jpeg);;"
            "CSV (*.csv);;Excel (*.xlsx);;All files (*)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "Attach file", "", filters)
        if not path:
            return

        name = os.path.basename(path)
        data, err = _read_attached_file(path)
        if err is not None:
            self.receiveMessageSignal.emit("ai", f"Error reading {name}: {err}")
            return
        
        self.receiveMessageSignal.emit("ai", f"📎 **File attached:** {name}\n\nAnalyzing...")
        self.statusSignal.emit("Analyzing...")
        
        agent = None
        if self._agent_provider:
            agent = self._agent_provider()
            
        thread = threading.Thread(
            target=self._analyze_file, args=(agent, name, path, data), daemon=True
        )
        thread.start()

    def _analyze_file(self, agent, name, path, data):
        try:
            if agent is None:
                self.receiveMessageSignal.emit("ai", "**No API key configured.**")
                return

            client = getattr(agent, "client", None)
            if client is not None and hasattr(client, "set_status_callback"):
                client.set_status_callback(lambda msg: self.statusSignal.emit(msg))

            if data.get("is_image"):
                response = self._analyze_image(agent, name, data)
            else:
                ext = os.path.splitext(path)[1].lower()
                # CSV/Excel previews (see _read_attached_file) are capped to a
                # handful of sample rows to keep the prompt small -- without the
                # real path, the model had no way to act on anything past that
                # preview. Pointing it at load_tabular_data_as_layer (which reads
                # the WHOLE file, not a preview) lets it actually load the full
                # dataset as a layer when that's what the user wants.
                if ext in (".csv", ".xlsx", ".xls"):
                    load_hint = (
                        f"The content below is only a PREVIEW (first few rows) of the attached "
                        f"file -- the full file is saved at: {path}\n"
                        "If the user wants this data actually loaded into the project (not just "
                        "described), call load_tabular_data_as_layer with that exact file_path -- "
                        "it reads the ENTIRE file, not just this preview.\n\n"
                    )
                else:
                    load_hint = f"The full file is saved at: {path}\n\n"
                prompt = (
                    f"I have attached a file: {name}\n\n"
                    f"{load_hint}"
                    f"File content:\n{data.get('text') or ''}\n\n"
                    "Please analyze this file and suggest what can be done with it in QGIS."
                )
                response = agent.run(prompt)

            if client is not None and hasattr(client, "set_status_callback"):
                client.set_status_callback(None)

            self.receiveMessageSignal.emit("ai", response if response else "_(empty response)_")
        except Exception as e:
            traceback.print_exc()
            self.receiveMessageSignal.emit("ai", f"**Error analyzing file:** {e}")
        finally:
            self.statusSignal.emit("")
            # Covers both branches above: the non-image path's agent.run(prompt)
            # already accumulated usage internally, and _analyze_image's direct
            # client.complete() call accumulates it itself (see that method) --
            # this is just the one place that refreshes what the label shows
            # after either one, same as _after_successful_response does for the
            # main chat send path.
            self._refresh_usage_label(agent)

    def _analyze_image(self, agent, name, data):
        b64 = data.get("b64", "")
        mime = data.get("mime", "png")
        data_url = f"data:image/{mime};base64,{b64}"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a QGIS spatial analysis assistant. The user has attached an image; "
                    "describe what it shows and suggest how it could be used inside QGIS."
                ),
            }
        ]
        messages.extend(getattr(agent, "conversation_history", []))
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"I have attached an image: {name}. "
                            "Please analyze it and suggest what can be done with it in QGIS."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        )

        client = getattr(agent, "client", None)
        if client is None:
            return "Agent has no API client configured."

        result = client.complete(messages)
        if not isinstance(result, dict):
            return "[API error] Unexpected response from model client."
        if "error" in result:
            return f"[API error] {result['error']}"
        # This call bypasses agent.run() entirely (image attachments go straight
        # to client.complete()), so it's the one call site outside run() that
        # would otherwise silently miss the session usage total.
        if hasattr(agent, "_accumulate_usage"):
            agent._accumulate_usage(result.get("usage"))
        message = result.get("message") or {}
        content = message.get("content")
        if not content:
            return (
                "The current model did not return any analysis. "
                "Vision support depends on the model; try a vision-capable model in Settings."
            )
        try:
            agent.conversation_history.append(
                {"role": "user", "content": f"[Attached image: {name}]"}
            )
            agent.conversation_history.append({"role": "assistant", "content": content})
            if hasattr(agent, "_trim_history"):
                agent._trim_history()
        except Exception:
            pass
        return content
