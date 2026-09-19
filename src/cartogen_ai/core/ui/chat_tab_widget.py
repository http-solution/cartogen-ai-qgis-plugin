# -*- coding: utf-8 -*-
"""Chat tab, extracted from dock_widget.py's CartogenAiDockWidget
(docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md). Owns the chat log, input row,
quick-suggestion chips, prompt-refinement panel, and file-attachment analysis. The old
separate Activity tab (tasks_tab_widget.py) is deleted; its Task Inspector moved to
task_inspector_dialog.py (opened per-task, see below) and its Project Notes/Memory
section moved to memory_dialog.py (opened from a header button in dock_widget.py).

Task/plan progress (2026-09-17, second redesign pass): plan_strip_widget.py's
always-docked strip above the chat -- itself the Broadsheet Phase 1 replacement for the
old Activity tab -- was live-user-rejected in turn: a separately pinned panel with its
own animation read as a debug overlay sitting on top of the conversation, not part of
it. Task progress now renders as an ordinary block INSIDE the chat log itself
(render_task_progress_html, see _on_live_plan_updated/_tick_plan_spinner below), updated
in place while its plan is the active one via the same tracked-cursor-span technique
_on_step_anchor_clicked already uses for the tool-steps toggle -- no separate widget, no
plan-history dropdown (scrollback already IS the history), and plan_strip_widget.py is
no longer imported anywhere in this file. The current task carries a small animated
spinner glyph (QTimer-driven), the only "motion" this in-chat card has -- deliberately
quieter than a docked progress bar, matching the direct instruction to keep it "elegant
but professional," not gimmicky.

Signals (receiveMessageSignal/statusSignal/usageSignal/toolStepSignal/
refinementFetchedSignal) stay defined on the parent CartogenAiDockWidget, not here
-- per the split plan's recommendation, since statusSignal/usageSignal are also
emitted from dock-header code (open_settings) and the two dialogs above. This widget
reaches them via self._dock, the same pattern those dialogs use too."""

import threading
import traceback
import os

from qgis.PyQt.QtCore import Qt, pyqtSignal, QSize, QTimer
from qgis.PyQt.QtGui import QTextCursor
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QTextBrowser,
    QPushButton, QTextEdit, QGroupBox,
)
from qgis.core import QgsSettings
from ..logger import log_warning
from ...infrastructure.settings_keys import SETTINGS_PROVIDER


from .chat_formatting import (
    render_markdown, _relative_time, now_iso, escape_plain_text, render_tool_step_html,
    render_tool_steps_toggle_html, render_tool_steps_failure_details_html, friendly_tool_name,
    format_send_error, render_task_progress_html, PLAN_SPINNER_FRAMES,
)
from .attachments import read_attached_file as _read_attached_file
# API-007, 2026-09-14 audit: reused rather than duplicated -- settings_dialog.py's PROVIDERS
# is already the single source of truth for each provider's display name.
from .settings_dialog import PROVIDERS as _PROVIDERS
from .theme import theme_colors, extract_theme_palette
from .icons import themed_icon

# _ask_preview_in_chat's reply interpretation (2026-09-15 boxed-panel-to-in-chat conversion):
# the old "Send this / Send as typed instead / Cancel" 3-way button choice now resolves from
# free text. Deliberately generous but not fuzzy-matched -- an unrecognized reply always falls
# through to the "send as typed" edit path (see send_message()), never silently ignored or
# misread as a confirmation it wasn't.
_PREVIEW_CONFIRM_REPLIES = {
    "yes", "y", "yeah", "yep", "ok", "okay", "sure", "go", "go ahead",
    "send", "send this", "confirm", "proceed", "do it",
}
_PREVIEW_CANCEL_REPLIES = {
    "no", "n", "nope", "cancel", "stop", "abort", "never mind", "nevermind", "nvm",
}


def _normalize_preview_reply(text):
    return text.strip().lower().rstrip("!.?")


class ChatInputEdit(QTextEdit):
    """Multi-line input that sends on Enter and inserts a newline on Shift+Enter."""
    sendRequested = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.sendRequested.emit()
            return
        super().keyPressEvent(event)


class ChatTabWidget(QWidget):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self._dock = dock
        self._active_highlights = []  # keeps QgsHighlight objects alive until their timer fires
        self._active_task = None  # the running QgsTask, if any -- lets _stop_current_task cancel it
        self._pending_refinement_cards = None  # recommendations list while in-chat cards are showing
        self._pending_restore_ts = None  # ISO ts for the message _add_message is about
        # to render, set only while _populate_initial_chat is replaying restored history
        self._pending_analysis_text = None
        self._pending_analysis = None
        # True while a requirement question (see _ask_requirement_in_chat) is
        # sitting in the chat log awaiting the user's reply -- the next plain
        # message they send is treated as the answer, not a new unrelated
        # request. Replaces a separate always-shown QGroupBox panel with two
        # buttons (2026-09-13, direct user feedback: "i dont like the style
        # of the feedback from cartogen AI make it more in the chat and get
        # user response interactive chat") -- the question itself now reads
        # as a normal Cartogen chat message, and answering it is just typing
        # a reply and hitting Send like any other turn.
        self._awaiting_requirement_reply = False
        # True while the "Prompt that will be sent" preview (see _ask_preview_in_chat) is
        # sitting in the chat log awaiting the user's reply -- same conversion, same reasoning
        # as _awaiting_requirement_reply above, applied 2026-09-15 to the second and last
        # remaining boxed panel (direct feedback, repeated: "i prefer everything to be in the
        # chat"). Unlike the requirement gate, the reply here is genuinely 3-way (send the
        # composed prompt / send as typed instead / cancel), so it needs real interpretation --
        # see send_message()'s _awaiting_preview_reply branch and _PREVIEW_CONFIRM_REPLIES/
        # _PREVIEW_CANCEL_REPLIES below.
        self._awaiting_preview_reply = False
        # Files the user attached since the last send. attach_file() still
        # analyses each one immediately (unchanged); this list is what lets the
        # NEXT message know those files exist, so a sitrep PDF or a damage
        # photo becomes part of the task rather than a separate side errand.
        self._attached_paths = []
        # Design proposal, 2026-09-16 (Dateline Dock artifact, adapted from Cartogen
        # Panel.pdf's option 1B): example requests shown as clickable links in the welcome
        # message (_populate_initial_chat) -- index here is what a cartogen://starter/{i}
        # anchor resolves against (_on_starter_prompt_clicked). Each one maps to a real,
        # already-shipped tool (buffer_analysis, estimate_population_exposure,
        # calculate_service_area -- see docs/TOOLS_REFERENCE.md), not an aspirational example.
        self._starter_prompts = [
            "Buffer 5 km around active GDACS alerts",
            "Population within the flood extent",
            "Health facilities beyond one hour's travel",
        ]
        # Tool names that ran during the turn in flight -- the evidence
        # agent/output_router.py checks the output contract against.
        self._executed_tools = []
        # Terminal-status (done/failed) step records for the turn in flight, flushed as one
        # compact summary block by _flush_tool_steps_summary() once the turn completes -- see
        # _add_tool_step. "running" status never lands here, it goes straight to status_label.
        self._current_turn_steps = []
        # block_id -> {"steps", "expanded", "start", "end"} for every tool-steps summary block
        # rendered so far this session, keyed by a monotonic counter (_step_block_counter) baked
        # into each block's toggle-anchor href. start/end are QTextCursor character positions
        # bounding exactly the collapsible portion of that block -- valid for the block's whole
        # lifetime since chat_browser is strictly append-only (nothing is ever inserted before
        # an existing block), so a position recorded once stays correct until THIS code replaces
        # it (and immediately re-records the fresh end position after doing so).
        self._step_blocks = {}
        self._step_block_counter = 0
        # The in-chat plan/progress card's tracked span (see render_task_progress_html and
        # _on_live_plan_updated) -- None until the first plan of the session starts. Unlike
        # _step_blocks above, only ONE entry is ever tracked at a time: once a plan's title
        # changes (a new plan started), the old card's HTML is left exactly as it last
        # rendered and this dict is replaced wholesale to point at the new one -- the old
        # card becomes an ordinary frozen part of scrollback, not something later code can
        # or should still edit in place.
        self._plan_block = None  # {"title", "start", "end", "spinner_frame"}
        self._connected_task_manager = None
        self._plan_spinner_timer = QTimer(self)
        self._plan_spinner_timer.setInterval(400)
        self._plan_spinner_timer.timeout.connect(self._tick_plan_spinner)
        self._pending_contract = None
        self._contract_followup_used = False
        # task_manager task ids whose inline safety-gate card (_show_safety_gate_in_chat,
        # Broadsheet redesign Phase 2) has already been posted to this chat log -- a
        # PREVIEW_READY task stays PREVIEW_READY across every turn until it's actually
        # confirmed/cancelled, so without this the same card would be re-posted after
        # every unrelated message sent while it's still pending. Cleared per task id once
        # _resolve_pending_confirmation moves that task off PREVIEW_READY, so a LATER
        # destructive action reusing the same numeric id (a fresh plan/task_manager
        # instance) still gets its own card shown.
        self._posted_safety_gate_task_ids = set()
        # Broadsheet redesign Phase 3 (mockup 1l, layer context picker): {layer_name:
        # bool}, empty until the user opens layer_context_btn at least once -- see
        # map_context.filter_layers_by_selection's docstring for why an empty dict here
        # means "send every loaded layer's schema" (today's unchanged behavior), not
        # "send nothing".
        self._layer_context_selection = {}

        from ..agent.deps import get_dependency_warning_message
        self._dep_warning = get_dependency_warning_message()

        self.init_ui()

    @property
    def _agent_provider(self):
        return self._dock._agent_provider

    def _pending_confirmation_task(self, agent):
        """The most recently updated task still awaiting a destructive-action confirmation
        gate (agent.py's _real_execute_tool PREVIEW_REQUIRED handling), or None. Only tasks
        carrying pending_tool are eligible -- a PREVIEW_READY task with no pending_tool has
        nothing to directly re-execute. See send_message()'s call site for why this exists."""
        if agent is None or not hasattr(agent, "task_manager"):
            return None
        candidates = [t for t in agent.task_manager.tasks
                      if t.get("status") == "PREVIEW_READY" and t.get("pending_tool")]
        if not candidates:
            return None
        return max(candidates, key=lambda t: t.get("updated_at", ""))

    def _resolve_pending_confirmation(self, agent, task, confirmed):
        """Executes or cancels a pending destructive-action gate directly, with no model
        turn involved -- mirrors tasks_tab_widget.py's _confirm_selected_task/
        _cancel_selected_task exactly, so a chat-typed reply, the inline safety-gate card's
        links, and the Activity tab's own buttons are all the same code path and can never
        disagree about what "Confirm" does."""
        task_id = task.get("id")
        self._posted_safety_gate_task_ids.discard(task_id)
        if confirmed:
            pending_tool = task.get("pending_tool")
            pending_args = task.get("pending_args", {})
            exec_res = agent._real_execute_tool(pending_tool, pending_args, user_confirmed=True)
            msg = f"Executed `{pending_tool}`: {exec_res}"
            agent.task_manager.update_task(task_id, "DONE", msg)
            self._dock.receiveMessageSignal.emit(
                "ai", f"✅ **Confirmed & Executed Task {task_id}:** {msg}")
        else:
            agent.task_manager.update_task(task_id, "FAILED", "Cancelled by User")
            self._dock.receiveMessageSignal.emit(
                "ai", f"❌ **Cancelled Task {task_id}:** {task.get('description')}")

    def _show_safety_gate_in_chat(self, agent):
        """Posts the inline destructive-action confirmation card (render_safety_gate_html,
        Broadsheet redesign Phase 2, mockup state 1f) for the current pending task, if any
        and if it hasn't already been posted. Called from _dispatch_message's on_complete
        after every successful turn -- cheap no-op when there's nothing pending, and
        _posted_safety_gate_task_ids stops the same still-open gate from being reposted
        after every unrelated message sent while it waits (see that set's own docstring in
        __init__)."""
        task = self._pending_confirmation_task(agent)
        if task is None:
            return
        task_id = task.get("id")
        if task_id in self._posted_safety_gate_task_ids:
            return
        self._posted_safety_gate_task_ids.add(task_id)
        from .chat_formatting import render_safety_gate_html
        html = render_safety_gate_html(task, theme_colors())
        self._add_message("ai", "", _raw_html=html)

    def _on_safety_gate_link_clicked(self, url):
        """A cartogen://confirm/{task_id} or cartogen://cancel/{task_id} link, from
        _show_safety_gate_in_chat's card. Resolves the SAME task_manager task a plain-text
        "Confirm"/"cancel" chat reply already resolves (see send_message()'s
        _pending_confirmation_task check) -- this is a second, clickable entry point onto
        the identical _resolve_pending_confirmation path, not a new confirmation mechanism.
        Silently no-ops if the agent or the task is gone (e.g. the task was cleared/the
        plan reset since the card was shown) rather than erroring on a stale click."""
        agent = self._agent_provider() if self._agent_provider else None
        if agent is None or not hasattr(agent, "task_manager"):
            return
        parts = [p for p in url.path().split("/") if p]
        task_id = parts[-1] if parts else None
        if not task_id:
            return
        task = next((t for t in agent.task_manager.tasks if t.get("id") == task_id), None)
        if task is None:
            return
        self._resolve_pending_confirmation(agent, task, confirmed=(url.host() == "confirm"))

    def _open_layer_context_picker(self):
        """Opens layer_context_picker_dialog.py's checklist against the CURRENT live
        layer list, and replaces self._layer_context_selection wholesale with whatever
        was checked on accept. A cancelled dialog leaves the prior selection untouched."""
        from ..agent.map_context import get_map_context_summary
        map_ctx = get_map_context_summary()
        layers = map_ctx.get("layers") or []
        if not layers:
            self._dock.statusSignal.emit("No layers loaded to choose from.")
            return
        from .layer_context_picker_dialog import LayerContextPickerDialog
        dialog = LayerContextPickerDialog(layers, self._layer_context_selection, parent=self)
        if dialog.exec():
            self._layer_context_selection = dialog.result_selection()

    def init_ui(self):
        chat_layout = QVBoxLayout(self)
        chat_layout.setContentsMargins(4, 4, 4, 4)

        self.chat_browser = QTextBrowser()
        # openExternalLinks=False is REQUIRED so Qt's anchorClicked signal fires for custom
        # schemes like cartogen:// (Qt specification: openExternalLinks=True suppresses anchorClicked
        # for non-empty schemes and hands them to QDesktopServices). Real http(s) and file links
        # are forwarded to QDesktopServices inside _on_step_anchor_clicked.
        self.chat_browser.setOpenExternalLinks(False)
        self.chat_browser.setOpenLinks(False)
        self.chat_browser.anchorClicked.connect(self._on_step_anchor_clicked)
        # Keep chat scrolled to bottom as asynchronous document layout updates geometry
        sb = self.chat_browser.verticalScrollBar()
        if sb:
            sb.rangeChanged.connect(self._on_scrollbar_range_changed)
        chat_layout.addWidget(self.chat_browser)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        chat_layout.addWidget(self.status_label)

        # Session token usage indicator (docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md
        # SS3.2, docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md's sibling task). Deliberately
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
            "Not shown for providers/models that don't report usage. \"Served from cache\" "
            "(2026-09-13) is how many of those tokens were a provider-side prompt-cache hit -- "
            "billed at a steep discount rather than full price. Claude sends explicit cache "
            "breakpoints; Gemini 2.5+/3.x models cache repeated content automatically, no setup "
            "needed, as long as the request stays above the model's own minimum cacheable size. "
            "No dollar-cost estimate is shown -- accurate per-model pricing across 5 providers "
            "isn't something this plugin can keep reliably current."
        )
        chat_layout.addWidget(self.usage_label)

        # Quick-suggestion chips used to sit here, always visible above the input row.
        # Removed per a 2026-09-12 real-session user report ("remove the buttons in the
        # bottom... irrelevant") -- QUICK_SUGGESTION_CHIPS (dock_constants.py) still backs
        # help_tab_widget.py's own example-prompts list, which is now their only home now
        # that Help is a deliberate, opt-in destination (Plugins menu) rather than
        # always-visible chrome.

        # Prompt Refinement recommendations -- design proposal, 2026-09-16 (Dateline Dock
        # artifact), real live report: "the recommendation text as button style like the
        # welcome message". Previously a separate boxed QGroupBox panel above the input row
        # (docs/archive/PROMPT_REFINEMENT_LAYER_SPEC.md §6/§11.1's original decision) -- now
        # shown in-chat instead, as clickable bordered cards via render_refinement_html, the
        # same technique the welcome message's starter prompts use. The spec's actual
        # underlying reason for a separate panel (these are ephemeral UI suggestions, never
        # persisted into conversation_history/chat_persistence.py as real turns) still holds:
        # _add_message only ever touches the visible chat_browser log, never
        # agent.conversation_history -- exactly like the welcome message and the preview card,
        # neither of which are persisted turns either. See _show_refinement_in_chat/
        # _on_refinement_card_clicked below.

        # Local task-register requirement gate (a genuinely unanswerable slot, e.g. hazard
        # type, with no safe default -- see analyze_request's "blocking" flag). Used to be a
        # separate always-boxed QGroupBox panel with its own "Proceed with stated defaults" /
        # "Edit request" buttons, shown ABOVE the input row with the box locked read-only.
        # Replaced 2026-09-13 (direct user feedback, real screenshot: "i dont like the style
        # of the feedback from cartogen AI make it more in the chat and get user response
        # interactive chat" -- the boxed panel read as a foreign popup, not part of the
        # conversation) with _ask_requirement_in_chat(): the question is posted as a normal
        # Cartogen chat message, and the user answers it by just typing a reply and hitting
        # Send like any other turn -- see send_message()'s _awaiting_requirement_reply branch.
        # "Proceed with stated defaults" was also confirmed dead in practice while removing
        # this: _show_requirement_panel (now _ask_requirement_in_chat) was only ever called
        # from the one `if analysis.get("blocking"):` branch below, and that button was always
        # `setEnabled(not analysis.get("blocking"))` -- i.e. always disabled on every real call.

        # Prompt preview used to be a separate always-boxed QGroupBox panel here too (Send
        # this / Send as typed instead / Cancel), shown ABOVE the input row. Replaced
        # 2026-09-15 with _ask_preview_in_chat() for the same reason _ask_requirement_in_chat
        # replaced the requirement-gate panel above: direct, repeated user feedback ("i prefer
        # everything to be in the chat"). The reasoning + composed prompt now post as a normal
        # chat message; the user answers by typing a reply -- see send_message()'s
        # _awaiting_preview_reply branch and _PREVIEW_CONFIRM_REPLIES/_PREVIEW_CANCEL_REPLIES.

        # Input Area
        # Icon color for the 3 buttons below: they're all styled #iconButton, which falls back
        # to the generic QPushButton rule's accent-filled background (build_dock_stylesheet),
        # so the icon itself needs to contrast against THAT fill -- highlighted_text (the
        # palette's own "text that sits on the accent color" role), not the page's normal text
        # color. UI/chat redesign workstream, 2026-09-12: these were plain Unicode emoji before
        # (📎 ➤ ⏹), replaced with theme-reactive SVGs (ui/icons.py) per the observed QGIS
        # plugin-ecosystem convention (custom SVG icons tinted from the live palette at render
        # time, not an icon font or fixed-color assets).
        _palette = extract_theme_palette()
        _icon_fg = (_palette or {}).get("highlighted_text", "#ffffff")

        input_layout = QHBoxLayout()
        # Broadsheet redesign Phase 3 (mockup 1l): explicit, per-question control over
        # which loaded layers' schema reaches the model -- opt-out, not opt-in (see
        # map_context.py's filter_layers_by_selection), so this button is silently a
        # no-op on every send until the user actually opens it once.
        self.layer_context_btn = QPushButton()
        self.layer_context_btn.setIcon(themed_icon("layers", _icon_fg))
        self.layer_context_btn.setIconSize(QSize(16, 16))
        self.layer_context_btn.setObjectName("iconButton")
        self.layer_context_btn.setFixedSize(30, 30)
        self.layer_context_btn.setToolTip("Choose which layers' schema Cartogen can see for this question")
        self.layer_context_btn.clicked.connect(self._open_layer_context_picker)

        self.attach_btn = QPushButton()
        self.attach_btn.setIcon(themed_icon("attach", _icon_fg))
        self.attach_btn.setIconSize(QSize(16, 16))
        self.attach_btn.setObjectName("iconButton")
        self.attach_btn.setFixedSize(30, 30)
        self.attach_btn.setToolTip("Attach a file (PDF, Word, image, CSV, or Excel)")
        self.attach_btn.clicked.connect(self.attach_file)

        self.input_edit = ChatInputEdit()
        self.input_edit.setFixedHeight(55)
        # Saved so _ask_requirement_in_chat can swap in a reply-specific hint
        # and restore this exact wording afterward.
        self._default_input_placeholder = "Ask me anything about your layers... (Enter to send, Shift+Enter for new line)"
        self.input_edit.setPlaceholderText(self._default_input_placeholder)
        self.input_edit.sendRequested.connect(self.send_message)

        self.send_btn = QPushButton()
        self.send_btn.setIcon(themed_icon("send", _icon_fg))
        self.send_btn.setIconSize(QSize(16, 16))
        self.send_btn.setObjectName("iconButton")
        self.send_btn.setFixedSize(30, 30)
        self.send_btn.setToolTip("Send (Enter)")
        self.send_btn.clicked.connect(self.send_message)

        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(themed_icon("stop", _icon_fg))
        self.stop_btn.setIconSize(QSize(16, 16))
        self.stop_btn.setObjectName("iconButton")
        self.stop_btn.setFixedSize(30, 30)
        self.stop_btn.setToolTip("Stop the current request")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_current_task)

        input_layout.addWidget(self.layer_context_btn)
        input_layout.addWidget(self.attach_btn)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(self.send_btn)
        input_layout.addWidget(self.stop_btn)
        chat_layout.addLayout(input_layout)

        # NOT called here anymore -- see CartogenAiDockWidget.__init__ (dock_widget.py) for why:
        # this method emits receiveMessageSignal before the dock has connected it to
        # _add_message, which used to silently drop the welcome/restored-history message every
        # time. The dock now calls _populate_initial_chat() itself, once its signals are wired.

    def _populate_initial_chat(self):
        """Shows the welcome message, or restores this project's saved conversation
        (agent/chat_persistence.py) if one exists. Called on first load, and again
        by refresh_chat_for_project_change() whenever the active QGIS project changes.

        Reads load_chat_history_with_timestamps() directly rather than
        agent.conversation_history (which deliberately has no timestamps -- see
        chat_persistence.py's module docstring) so each restored bubble can carry
        its real relative age via _add_message's self._pending_restore_ts, instead
        of every restored message rendering as "just now" -- see that function's
        comment for the live bug this fixes."""
        restored = False
        agent = None
        if self._agent_provider:
            try:
                agent = self._agent_provider()
                if agent is not None:
                    from ..agent.chat_persistence import load_chat_history_with_timestamps
                    history = load_chat_history_with_timestamps()
                    for entry in history:
                        role = entry.get("role")
                        content = entry.get("content")
                        if not content or role not in ("user", "assistant") or not isinstance(content, str):
                            continue
                        self._pending_restore_ts = entry.get("ts")
                        self._dock.receiveMessageSignal.emit("user" if role == "user" else "ai", content)
                        restored = True
            except Exception as e:
                log_warning(f"Failed to restore chat history: {e}", tag="ChatTabWidget")

        if restored:
            self._dock.receiveMessageSignal.emit("ai", "_(Restored previous conversation for this project.)_")
        else:
            # Design proposal, 2026-09-16 (Dateline Dock artifact): the plain welcome
            # paragraph gains a numbered capability index (adapted from Cartogen Panel.pdf's
            # option 1B, "The spatial desk") and clickable starter prompts (see
            # self._starter_prompts / _on_starter_prompt_clicked). Real live feedback on the
            # first pass ("its not following the design notes"): going through plain markdown
            # (a numbered list + bullet links) lost the mockup's actual visual treatment -- a
            # big teal numeral beside each capability, and each starter as its own bordered
            # card, not inline text. render_welcome_html builds that directly; called through
            # _add_message's _raw_html path, not the receiveMessageSignal emit every other
            # message uses, since this is the one message that needs to bypass render_markdown.
            from .chat_formatting import render_welcome_html
            welcome_html = render_welcome_html(
                intro="Your spatial analysis assistant for humanitarian GIS 🗺️. What are we working on?",
                capabilities=[
                    ("Monitor", "Real-time GDACS alerts, flood extents, earthquake footprints."),
                    ("Ingest", "HDX/OCHA boundaries, OSM infrastructure, satellite basemaps."),
                    ("Analyse", "Population exposure, facility accessibility, buffer zones."),
                    ("Publish", "Thematic maps, hi-res layouts, cluster summary reports."),
                ],
                starters=self._starter_prompts,
                colors=theme_colors(),
            )
            self._add_message("ai", "", _raw_html=welcome_html)

        from ..agent.auth import CredentialManager
        missing_key_msg = CredentialManager.missing_credential_message(
            client=getattr(agent, "client", None) if agent is not None else None)
        if missing_key_msg:
            self._dock.receiveMessageSignal.emit("ai", missing_key_msg)

        if self._dep_warning:
            self._dock.receiveMessageSignal.emit("ai", self._dep_warning)

    def refresh_chat_for_project_change(self):
        """Called by CartogenAi (see plugin_main.py) via the dock when QgsProject fires
        readProject/cleared -- the dock and its cached agent instance persist across
        project switches, so the visible chat log needs to be reloaded to match the
        newly-active project's saved history instead of showing the previous project's
        conversation."""
        self.chat_browser.clear()
        # A pending requirement question's chat bubble is about to be wiped by the clear()
        # above -- without resetting this too, a message typed after switching projects would
        # be silently merged into a now-invisible original request instead of treated as its
        # own new message.
        self._awaiting_requirement_reply = False
        self._awaiting_preview_reply = False
        self._populate_initial_chat()

    def _add_message(self, role, text, _raw_html=None):
        # _raw_html: pre-built HTML body to use verbatim instead of running `text` through
        # render_markdown -- only the welcome message (_populate_initial_chat, via
        # chat_formatting.render_welcome_html) uses this, to get the design proposal's actual
        # numeral-led capability rows and bordered starter cards instead of what render_
        # markdown's plain bullet/numbered-list output can produce. Not part of
        # receiveMessageSignal's (str, str) signature -- called directly (this method is a
        # normal Python method beneath the signal-connected slot of the same name), never via
        # emit(), so no signal-signature change was needed.
        # Theme-aware colors (see chat_formatting.derive_bubble_colors) so bubbles
        # read correctly in both light and dark QGIS themes instead of a hardcoded
        # light-blue/light-grey pair. timestamp is "now" at render time for a live
        # message; a restored message instead uses the real timestamp
        # _populate_initial_chat stashed in self._pending_restore_ts right before
        # this call, so a leftover bubble from an earlier session shows its actual
        # age (e.g. "2h ago") instead of falsely claiming to have just happened --
        # this was a real, live-reported bug (a stale Ollama-provider error looked
        # like it had just occurred next to a brand-new reply from a different
        # provider). See chat_persistence.py's _attach_timestamps for where the ts
        # comes from.
        colors = theme_colors()
        restore_ts = getattr(self, "_pending_restore_ts", None)
        self._pending_restore_ts = None
        timestamp = _relative_time(restore_ts) if restore_ts else _relative_time(now_iso())
        # Table-based alignment, not a floated div -- Qt's rich-text engine
        # supports table cell alignment reliably; float-based layout is flaky.
        if role == "user":
            body = escape_plain_text(text)
            label, align = "You", "right"
            bg = colors["user_bg"]
            accent_border = colors["accent"]  # the one place this UI spends its brand-color boldness
        else:
            body = _raw_html if _raw_html is not None else render_markdown(text, colors)
            label, align = "🗺️ Cartogen", "left"
            bg = colors["agent_bg"]
            accent_border = colors["border"]  # stays quiet -- no accent on the agent's own side

        # border="0" cellspacing="0" cellpadding="0" on the OUTER (alignment-only) table --
        # real bug, found from a live user report with screenshots (UI real-session-feedback
        # fixes, 2026-09-12): without this, Qt's rich-text engine drew its own default table
        # border around the outer table, stacking visibly with the inner table's real
        # border:1px below it -- a "double border" around every message. border-radius:8px
        # (previously on the inner table) is REMOVED, not just left as dead weight: Qt's
        # rich-text engine is a limited CSS 2.1-ish subset with no border-radius support at
        # all, so it was always silently ignored -- every message has always rendered as a
        # sharp rectangle in real QGIS, never actually rounded despite the code claiming to.
        #
        # The accent stripe went through a second, real bug the first time around: a single
        # cell styled with both "border:1px solid X" and "border-left:3px solid Y" silently
        # drops the border-left override entirely -- confirmed by rendering an unmistakable
        # magenta border-left in isolation and finding it never appeared in the output at all,
        # only the uniform 1px border color on every side, live user report 2026-09-12 (the
        # first fix looked right on inspection but was never actually visually confirmed
        # pixel-by-pixel, only via a color existing somewhere in the wider screenshot -- see
        # feedback_synthetic_screenshots_have_limits memory). Qt's table CSS DOES reliably
        # support per-cell background-color and a uniform border shorthand -- just not both
        # border shorthand and a conflicting border-left on the same cell. Fixed by using two
        # cells instead of one CSS trick: a dedicated 3px-wide stripe cell with only a
        # background-color (no border at all), directly beside the actual content cell, which
        # keeps its border but only on 3 sides (top/right/bottom -- no border-left, so it sits
        # flush against the stripe with no gap or double edge).
        html = f"""
        <table border="0" cellspacing="0" cellpadding="0" width="100%" style="margin:6px 0;"><tr><td align="{align}">
        <table border="0" cellspacing="0" cellpadding="0" align="{align}" style="max-width:85%;"><tr>
        <td width="3" style="background-color:{accent_border};"></td>
        <td style="background-color:{bg};padding:8px 12px;
            border-top:1px solid {colors['border']};border-right:1px solid {colors['border']};
            border-bottom:1px solid {colors['border']};">
        <div style="font-size:11px;font-weight:bold;color:{colors['text']};margin-bottom:3px;">
            {label} <span style="font-weight:normal;color:{colors['subtle']};">&middot; {timestamp}</span>
        </div>
        <div style="color:{colors['text']};font-size:13px;">{body}</div>
        </td></tr></table>
        </td></tr></table>
        """

        self.chat_browser.append(html)
        self._scroll_to_bottom()
        self.input_edit.clear()
        self.send_btn.setEnabled(True)
        self.status_label.setText("")

    def _scroll_to_bottom(self):
        """Scrolls to the bottom reliably, scheduling layout-settling checks."""
        from qgis.PyQt.QtCore import QTimer
        from qgis.PyQt.QtGui import QTextCursor

        def _do_scroll():
            self.chat_browser.moveCursor(QTextCursor.MoveOperation.End)
            sb = self.chat_browser.verticalScrollBar()
            if sb:
                sb.setValue(sb.maximum())

        _do_scroll()
        QTimer.singleShot(50, _do_scroll)
        QTimer.singleShot(150, _do_scroll)

    def _on_scrollbar_range_changed(self, min_val, max_val):
        """When document geometry changes asynchronously, follow to bottom if user was near bottom."""
        sb = self.chat_browser.verticalScrollBar()
        if sb and (max_val - sb.value() < 160):
            sb.setValue(max_val)

    def _set_status(self, text):
        self.status_label.setText(text)

    def _set_usage_label(self, text):
        self.usage_label.setText(text)

    def _add_tool_step(self, name, status, error):
        """Live per-tool-call progress signal, fired twice per tool call (once starting, once
        finishing) -- see agent.py's run() tool_step_callback. Previously every one of those
        events appended its own line directly into the chat scrollback; real user feedback
        (2026-09-12) called that too much visual space/raw detail/noise for a multi-tool-call
        turn. Redesigned: "running" is transient, live-progress-only -- it now updates
        status_label in place (the same label already used for "Thinking...") instead of adding
        a permanent scrollback line. Terminal statuses ("done"/"failed") are collected into
        self._current_turn_steps instead of rendered immediately; _flush_tool_steps_summary()
        (called once, from _dispatch_message's on_complete when the whole turn finishes) turns
        the collected list into ONE compact summary block."""
        status_lower = (status or "").lower()
        if status_lower == "running":
            self.status_label.setText(f"⚙️ {friendly_tool_name(name)}…")
            return
        colors = theme_colors()
        # Also the record agent/output_router.py checks the output contract
        # against. Only completed steps count -- a tool that started and failed
        # did not produce the deliverable.
        if name and status_lower in ("done", "ok", "finished", "completed", "success"):
            self._executed_tools.append(name)
        self._current_turn_steps.append({
            "name": name,
            "status": "failed" if status_lower == "failed" else "done",
            "error": error or None,
        })

    def _flush_tool_steps_summary(self):
        """Renders self._current_turn_steps (accumulated by _add_tool_step above) as one
        compact summary block, then clears the list. Called once per turn, from
        _dispatch_message's on_complete() -- which already runs on the main GUI thread (it
        calls receiveMessageSignal.emit directly with no extra thread-marshalling), so this is
        safe to call directly without another signal hop. A no-op when no tools ran this turn
        (a plain conversational reply with no tool calls) -- nothing is appended at all."""
        steps = self._current_turn_steps
        self._current_turn_steps = []
        if not steps:
            return
        colors = theme_colors()
        self._step_block_counter += 1
        block_id = self._step_block_counter

        cursor = QTextCursor(self.chat_browser.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()  # a fresh paragraph, matching .append()'s own behavior elsewhere
        start_pos = cursor.position()
        cursor.insertHtml(render_tool_steps_toggle_html(steps, block_id, colors, expanded=False))
        end_pos = cursor.position()
        self._step_blocks[block_id] = {
            "steps": steps, "expanded": False, "start": start_pos, "end": end_pos,
        }

        failure_html = render_tool_steps_failure_details_html(steps, colors)
        if failure_html:
            # Outside the tracked start/end span on purpose -- always visible, never part of
            # what the toggle above collapses/expands (see render_tool_steps_failure_details_
            # html's docstring: failures are load-bearing, not opt-in detail).
            self.chat_browser.append(failure_html)

        self._scroll_to_bottom()

    def _on_live_plan_updated(self, plan_data):
        """Renders/updates the in-chat plan-progress card -- connected to task_manager's
        plan_updated signal in send_message() above. A plan with no title and no tasks
        means "nothing active right now": the timer stops but any existing card is left
        untouched in scrollback (it's a real record of a past plan, not a placeholder to
        blank out). A DIFFERENT title than the currently-tracked card means a new plan
        started -- appends a fresh block rather than overwriting the old one, so plan
        history is just "scroll up" (see this file's module docstring)."""
        title = plan_data.get("title", "")
        tasks = plan_data.get("tasks", [])
        colors = theme_colors()

        if not title and not tasks:
            self._plan_spinner_timer.stop()
            return

        is_new_plan = self._plan_block is None or self._plan_block["title"] != title
        spinner_frame = 0 if is_new_plan else self._plan_block["spinner_frame"]
        html = render_task_progress_html(plan_data, colors, spinner_frame=spinner_frame)

        if is_new_plan:
            cursor = QTextCursor(self.chat_browser.document())
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertBlock()
            start_pos = cursor.position()
            cursor.insertHtml(html)
            end_pos = cursor.position()
            self._plan_block = {
                "title": title, "start": start_pos, "end": end_pos,
                "spinner_frame": spinner_frame, "plan_data": plan_data,
            }
            # Same force-scroll fix as _flush_tool_steps_summary above, for the same reason
            # (a fresh QTextCursor insert bypasses append()'s own scroll heuristic) -- only
            # for a genuinely NEW card, not every in-place update below: forcing this on
            # every _tick_plan_spinner tick (every 400ms while a task runs) would yank the
            # view back to the bottom several times a second, making scrollback unreadable
            # during a long-running turn.
            self._scroll_to_bottom()
        else:
            self._plan_block["plan_data"] = plan_data
            self._replace_tracked_block(self._plan_block, html)

        has_running = any(t.get("status") == "IN_PROGRESS" for t in tasks)
        if has_running and not self._plan_spinner_timer.isActive():
            self._plan_spinner_timer.start()
        elif not has_running:
            self._plan_spinner_timer.stop()

    def _tick_plan_spinner(self):
        """Advances the current plan card's spinner glyph one frame -- the only animation
        this in-chat card has, deliberately quiet (a single cycling braille dot, not a
        moving progress bar or bouncing icon) per the direct instruction that replaced
        plan_strip_widget.py's docked-panel-with-animation with this in-chat design."""
        if self._plan_block is None:
            self._plan_spinner_timer.stop()
            return
        self._plan_block["spinner_frame"] = (self._plan_block["spinner_frame"] + 1) % len(PLAN_SPINNER_FRAMES)
        colors = theme_colors()
        html = render_task_progress_html(
            self._plan_block["plan_data"], colors, spinner_frame=self._plan_block["spinner_frame"],
        )
        self._replace_tracked_block(self._plan_block, html)

    def _replace_tracked_block(self, block, new_html):
        """Shared in-place-edit primitive for any tracked chat_browser span (currently the
        plan card and the tool-steps toggle in _on_step_anchor_clicked below): replaces the
        HTML between block['start']/['end'], then shifts every OTHER tracked block (both
        _step_blocks and, if it isn't the one being edited, _plan_block) whose span starts
        after the edited one's old end -- the collapsed/expanded or spinner-frame HTML
        rarely renders to the same character count, so every later block's stored position
        would silently go stale without this, exactly the bug _on_step_anchor_clicked's own
        original delta-shift comment already documents for the tool-steps case."""
        old_end = block["end"]
        cursor = QTextCursor(self.chat_browser.document())
        cursor.setPosition(block["start"])
        cursor.setPosition(old_end, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertHtml(new_html)
        new_end = cursor.position()
        block["end"] = new_end

        delta = new_end - old_end
        if not delta:
            return
        for other_block in self._step_blocks.values():
            if other_block is not block and other_block["start"] > old_end:
                other_block["start"] += delta
                other_block["end"] += delta
        if self._plan_block is not None and self._plan_block is not block and self._plan_block["start"] > old_end:
            self._plan_block["start"] += delta
            self._plan_block["end"] += delta

    def _clear_plan(self):
        if not self._agent_provider:
            return
        agent = self._agent_provider()
        if not (agent and hasattr(agent, "task_manager")) or not agent.task_manager.tasks:
            return
        from qgis.PyQt.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Clear Plan", "Archive the current plan and reset the tracker?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            agent.task_manager.clear_plan()

    def _on_step_anchor_clicked(self, url):
        """Handles clicks on this app's own internal "cartogen://" anchors -- the
        Details/Hide-details toggle a tool-steps summary block renders (render_tool_steps_
        toggle_html), a welcome-message starter prompt (cartogen://starter/{index}, see
        _populate_initial_chat), a prompt-refinement recommendation (cartogen://refine/
        {index}, see _show_refinement_in_chat), the inline safety-gate card's Apply
        edit/Cancel links (cartogen://confirm/{task_id} / cartogen://cancel/{task_id}, see
        _show_safety_gate_in_chat -- Broadsheet redesign Phase 2), and the in-chat plan
        card's row/footer links (cartogen://task/{task_id}, cartogen://clearplan -- see
        render_task_progress_html/_on_live_plan_updated). Dispatches on url.host() since
        all share the scheme. Ignores anything that isn't "cartogen", so real markdown
        links in AI responses (opened via setOpenExternalLinks(True), untouched by this
        handler) are unaffected."""
        # Handle standard external schemes via QDesktopServices
        if url.scheme() in ("http", "https", "file"):
            from qgis.PyQt.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)
            return
        if url.scheme() != "cartogen":
            return
        if url.host() == "starter":
            self._on_starter_prompt_clicked(url)
            return
        if url.host() == "refine":
            self._on_refinement_card_clicked(url)
            return
        if url.host() in ("confirm", "cancel"):
            self._on_safety_gate_link_clicked(url)
            return
        if url.host() == "clearplan":
            self._clear_plan()
            return
        if url.host() == "task":
            self._on_plan_task_clicked(url)
            return
        if url.host() == "action":
            self._on_chat_action_clicked(url)
            return
        if url.host() == "export":
            self._on_export_action_clicked(url)
            return
        if url.host() == "prompt":
            import urllib.parse
            prompt_text = urllib.parse.unquote(url.path().lstrip("/"))
            if not prompt_text and url.hasQuery():
                prompt_text = urllib.parse.unquote(url.query())
            if prompt_text:
                self.input_edit.setPlainText(prompt_text)
                self.input_edit.setFocus()
            return
        if url.host() == "zoom":
            parts = [p for p in url.path().split("/") if p]
            layer_name = parts[-1] if parts else None
            from ..agent.tools.map_tools import zoom_to_layer
            if layer_name and layer_name != "zoom":
                zoom_to_layer(layer_name)
            else:
                try:
                    from qgis.utils import iface
                    from qgis.core import QgsProject
                    layers = list(QgsProject.instance().mapLayers().values())
                    if iface and iface.activeLayer():
                        zoom_to_layer(iface.activeLayer().name())
                    elif layers:
                        zoom_to_layer(layers[0].name())
                    elif iface and iface.mapCanvas():
                        iface.mapCanvas().zoomToFullExtent()
                except Exception:
                    pass
            return

        parts = [p for p in url.path().split("/") if p]
        if not parts and url.host():
            parts = [url.host()]
        try:
            block_id = int(parts[-1]) if parts else int(url.host())
        except (ValueError, IndexError):
            return
        block = self._step_blocks.get(block_id)
        if block is None:
            return

        colors = theme_colors()
        block["expanded"] = not block["expanded"]
        new_html = render_tool_steps_toggle_html(
            block["steps"], block_id, colors, expanded=block["expanded"]
        )
        self._replace_tracked_block(block, new_html)

    def _on_plan_task_clicked(self, url):
        """cartogen://task/{task_id} from the in-chat plan card -- opens the same Task
        Inspector dialog the old plan_strip_widget.py's list rows opened on click, looked
        up fresh from the live agent's task_manager rather than the (possibly stale, if
        this is an older frozen plan card in scrollback) snapshot the card was rendered
        from. A task no longer present (plan since cleared) is a silent no-op."""
        parts = [p for p in url.path().split("/") if p]
        if not parts:
            return
        agent = self._agent_provider() if self._agent_provider else None
        if not (agent and hasattr(agent, "task_manager")):
            return
        task_id = parts[-1]
        task = next(
            (t for t in agent.task_manager.get_plan().get("tasks", []) if str(t.get("id")) == task_id),
            None,
        )
        if task is None:
            return
        from .task_inspector_dialog import CartogenAiTaskInspectorDialog
        dialog = CartogenAiTaskInspectorDialog(self._dock, task, read_only=False, parent=self)
        dialog.exec()

    def _on_chat_action_clicked(self, url):
        """Resolves and dispatches a typed ChatAction from ChatActionRegistry."""
        parts = [p for p in url.path().split("/") if p]
        act_id = parts[-1] if parts else None
        if not act_id:
            return
        from ..agent.map_intelligence import ChatActionRegistry
        action = ChatActionRegistry.get(act_id)
        if action is None:
            # Fallback for dynamic action URLs like cartogen://action/zoom/Layer or cartogen://action/export/Layer
            action_parts = [p for p in url.path().split("/") if p]
            if len(action_parts) >= 2 and action_parts[0] == "zoom":
                from ..agent.tools.map_tools import zoom_to_layer
                zoom_to_layer(action_parts[1])
                return
            if len(action_parts) >= 2 and action_parts[0] == "export":
                from qgis.PyQt.QtCore import QUrl
                self._on_export_action_clicked(QUrl(f"cartogen://export/{action_parts[1]}"))
                return
            clean_text = " ".join(action_parts).replace("_", " ")
            if clean_text and not clean_text.startswith("act_"):
                self.input_edit.setPlainText(clean_text)
                self.input_edit.setFocus()
                return
            self._dock.receiveMessageSignal.emit(
                "ai", "_This action is no longer available (session expired or project changed)._"
            )
            return

        kind = action.kind
        payload = action.payload or {}
        layer_name = payload.get("layer_name")

        if kind == "export":
            from ..agent.tools.export_tools import export_to_csv
            res = export_to_csv(layer_name, only_selected=payload.get("only_selected"))
            if res.get("cancelled"):
                self._dock.statusSignal.emit("Export cancelled.")
            elif res.get("success"):
                cnt = res.get("feature_count", "all")
                path = res.get("output_path", "")
                self._dock.receiveMessageSignal.emit(
                    "ai", f"✅ **Exported {layer_name}:** Saved {cnt} feature(s) to `{path}`"
                )
            else:
                err = res.get("error", "Export failed")
                self._dock.receiveMessageSignal.emit("ai", f"❌ **Export Error:** {err}")
            return

        if kind == "zoom":
            from ..agent.tools.map_tools import zoom_to_layer
            res = zoom_to_layer(layer_name)
            if res.get("success"):
                self._dock.statusSignal.emit(f"Zoomed to {layer_name}")
            return

        if kind == "apply_style":
            from ..agent.tools.representation_tools import apply_recommended_representation
            rep_id = payload.get("representation_id", "")
            target_field = payload.get("target_field")
            res = apply_recommended_representation(layer_name, rep_id, target_field)
            if res.get("success"):
                self._dock.statusSignal.emit(f"Applied {rep_id} to {layer_name}")
                self._dock.receiveMessageSignal.emit(
                    "ai", f"🎨 **Applied Representation:** Configured `{rep_id}` on `{layer_name}`."
                )
                try:
                    from qgis.utils import iface
                    if iface and iface.mapCanvas():
                        iface.mapCanvas().refresh()
                except Exception:
                    pass
            else:
                err = res.get("error", "Failed to apply representation")
                self._dock.receiveMessageSignal.emit("ai", f"❌ **Style Error:** {err}")
            return

        if kind == "prompt":
            prompt_text = payload.get("text", "")
            if prompt_text:
                self.input_edit.setPlainText(prompt_text)
                self.input_edit.setFocus()
            return

    def _on_export_action_clicked(self, url):
        """cartogen://export/{layer_name} direct export action with Save As dialog."""
        parts = [p for p in url.path().split("/") if p]
        layer_name = parts[-1] if parts else None
        if not layer_name:
            return
        from ..agent.tools.export_tools import export_to_csv
        # only_selected=None allows export_to_csv to export selection if active, or all features if no selection
        res = export_to_csv(layer_name, only_selected=None)
        if res.get("cancelled"):
            self._dock.statusSignal.emit("Export cancelled.")
        elif res.get("success"):
            cnt = res.get("feature_count", "all")
            path = res.get("output_path", "")
            self._dock.receiveMessageSignal.emit(
                "ai", f"✅ **Exported {layer_name}:** Saved {cnt} feature(s) to `{path}`"
            )
        else:
            err = res.get("error", "Export failed")
            self._dock.receiveMessageSignal.emit("ai", f"❌ **Export Error:** {err}")

    def _on_starter_prompt_clicked(self, url):
        """A cartogen://starter/{index} link, from the welcome message's example-prompt list
        (_populate_initial_chat) -- fills the input box with that example rather than sending
        it, matching the design proposal's "clicking one fills the input box (not auto-sends)"
        call, the same one-click-to-edit pattern "Edit & Resend" already uses in the Tasks tab.
        Real product decision documented in the Dateline Dock design proposal, 2026-09-16."""
        parts = [p for p in url.path().split("/") if p]
        try:
            index = int(parts[-1]) if parts else -1
        except (ValueError, IndexError):
            return
        if not (0 <= index < len(self._starter_prompts)):
            return
        self.input_edit.setPlainText(self._starter_prompts[index])
        self.input_edit.setFocus()

    def send_message(self):
        if not self.send_btn.isEnabled():
            # A request is already in flight. send_btn.setEnabled(False) blocks
            # a second click, but ChatInputEdit.keyPressEvent emits
            # sendRequested on Enter unconditionally -- without this check,
            # Enter could still start a second, overlapping turn.
            return
        text = self.input_edit.toPlainText().strip()
        if not text:
            return

        # A requirement question is outstanding (see _ask_requirement_in_chat) -- this
        # message IS the answer to it, not a new unrelated request. Real-session report,
        # 2026-09-13: "some of my text i sent in the chat is not showing" -- the reply
        # itself was never echoed into the chat log at all before being folded into the
        # pending request, so a multi-round clarification (a second still-missing slot
        # asking again) made every reply in between silently vanish from what the user
        # could see. Echoing it here, unconditionally, as its own message is what makes
        # this feel like an actual chat rather than a black box -- the eventual composed
        # request (original + "Details: ...") still shows too, once dispatch/preview
        # actually happens, exactly like any other task-matched message already does.
        if self._awaiting_requirement_reply:
            self._dock.receiveMessageSignal.emit("user", text)
            text = f"{self._pending_analysis_text}\n\nDetails: {text}"
            self._awaiting_requirement_reply = False
            self.input_edit.setPlaceholderText(self._default_input_placeholder)

        # Answering the in-chat preview question (see _ask_preview_in_chat) -- this reply
        # resolves the pending 3-way choice the old boxed panel used to offer as buttons:
        # an affirmative reply sends the composed prompt, a cancel reply abandons it, and
        # anything else is sent exactly as typed with no enrichment (the free-text
        # equivalent of "Send as typed instead" -- confirmed with the user as the intended
        # design, 2026-09-15). Fully resolves the turn itself, unlike the requirement-reply
        # branch above (which merges and falls through) -- returns immediately either way.
        if self._awaiting_preview_reply:
            self._awaiting_preview_reply = False
            original_text, pending_analysis = self._pending_analysis_text, self._pending_analysis
            self._pending_analysis_text = None
            self._pending_analysis = None
            self.input_edit.setPlaceholderText(self._default_input_placeholder)
            reply_key = _normalize_preview_reply(text)
            if reply_key in _PREVIEW_CONFIRM_REPLIES:
                self._dock.receiveMessageSignal.emit("user", text)
                # already_echoed=True: original_text was already shown as its own bubble
                # by _ask_preview_in_chat when the question was first asked -- see that
                # method's docstring.
                self._dispatch_message(original_text, pending_analysis, already_echoed=True)
            elif reply_key in _PREVIEW_CANCEL_REPLIES:
                self._dock.receiveMessageSignal.emit("user", text)
                self._dock.receiveMessageSignal.emit(
                    "ai", "Okay, cancelled -- send a new message whenever you're ready.")
            else:
                # Edit fallback: exactly _send_preview_original's old behavior -- no manual
                # echo here, _dispatch_message already echoes `text` itself.
                self._dispatch_message(text, None)
            return

        # A destructive-action confirmation gate (field_calculator etc. -- see agent.py's
        # _real_execute_tool PREVIEW_REQUIRED handling) may be pending. A short, unambiguous
        # confirm/cancel reply here must resolve it through the exact same deterministic path
        # the Activity tab's own Confirm/Cancel buttons use (tasks_tab_widget.py's
        # _confirm_selected_task/_cancel_selected_task), not the free-form LLM loop.
        #
        # Real live report, 2026-09-16: a user typed "Confirm" in chat to approve a
        # field_calculator preview. That reply re-entered the normal tool-calling turn with
        # no structured awareness of what was pending (get_formatted_task_context() didn't
        # even mention pending_tool/pending_args at the time), and the model fabricated a
        # "Confirmed" narrative without ever calling field_calculator -- the approved edit
        # silently never happened.
        #
        # Deliberately narrow: only intercepts when (a) a task is actually PREVIEW_READY
        # with a pending_tool attached, AND (b) the typed reply exactly matches one of the
        # same keyword sets _awaiting_preview_reply already uses above -- so a longer,
        # unrelated message is never mistaken for a yes/no answer to a stale gate, and this
        # never fires unless there is something real to confirm or cancel. Checked after the
        # two local UI-flag branches above so a still-open requirement/preview question (a
        # more specific, just-asked exchange) always takes priority over an older pending
        # gate.
        agent = self._agent_provider() if self._agent_provider else None
        pending_task = self._pending_confirmation_task(agent)
        if pending_task is not None:
            reply_key = _normalize_preview_reply(text)
            if reply_key in _PREVIEW_CONFIRM_REPLIES or reply_key in _PREVIEW_CANCEL_REPLIES:
                self._dock.receiveMessageSignal.emit("user", text)
                self._resolve_pending_confirmation(
                    agent, pending_task, confirmed=(reply_key in _PREVIEW_CONFIRM_REPLIES))
                return

        # A fresh send attempt abandons any still-pending refinement cards from a previous
        # message -- the practical equivalent of spec §7's "user closes the card without
        # choosing". No explicit hide needed now that the cards render in-chat (they're just
        # scrollback, not a widget that stays visible) -- only the pending-selection state
        # needs clearing, so a stale click on an old card's link can't resurrect it.
        self._pending_refinement_cards = None

        from ..agent.prompt_refiner import (
            analyze_request, should_refine, is_refinement_enabled, is_prompt_preview_enabled,
        )
        try:
            from ..agent.map_context import get_map_context_summary
            request_context = get_map_context_summary()
        except Exception:
            request_context = {}
        analysis = analyze_request(text, request_context, self._attached_paths)

        # Order matters. A genuinely unanswerable gap is asked about FIRST:
        # previewing a prompt that is about to guess the hazard type would be
        # showing the user a decision instead of asking them for it.
        #
        # Only `blocking` stops the send, not every missing slot. A slot with a
        # safe default (area of interest, admin level, period) is filled in and
        # STATED in the preview below, where the user can see and correct it --
        # that is the register's "ask once, then default" policy. Stopping for
        # every missing slot would interrupt roughly nine messages in ten, and
        # a prompt that interrupts constantly gets clicked through unread,
        # which defeats the disclosure it exists for.
        if analysis.get("blocking"):
            self._ask_requirement_in_chat(text, analysis)
            return
        self._pending_analysis_text = text
        self._pending_analysis = analysis

        if analysis.get("task") is not None and is_prompt_preview_enabled():
            self._ask_preview_in_chat(text, analysis)
            return

        agent = self._agent_provider() if self._agent_provider else None
        client = getattr(agent, "client", None) if agent is not None else None

        # docs/archive/PROMPT_REFINEMENT_LAYER_SPEC.md: an optional, opt-in step that
        # rewrites this text into two better-specified candidates before it
        # reaches _dispatch_message()/agent.run(). Every failure mode here
        # (disabled, too-short message, no client available) falls straight
        # through to the exact same dispatch a message would get today.
        if client is not None and should_refine(text, is_refinement_enabled()):
            self._start_refinement(text, client)
            return

        self._dispatch_message(text, analysis)

    def _ask_requirement_in_chat(self, original_text, analysis):
        """Asks a genuinely unanswerable requirement gap (e.g. hazard type --
        no safe default exists, guessing one risks confidently wrong
        humanitarian output) as a normal chat message instead of a separate
        boxed panel. See _awaiting_requirement_reply's docstring in __init__
        for why: a real user screenshot showed the old panel reading as a
        foreign popup, disconnected from the conversation above it. The input
        box stays fully live -- answering is just typing a reply and hitting
        Send, handled by send_message()'s _awaiting_requirement_reply branch,
        which merges that reply into `original_text` and re-runs it through
        the exact same pipeline (so a second still-missing slot asks again
        the same way, rather than needing a different mechanism).

        Echoes original_text as its own "You" bubble first -- real live report,
        2026-09-15: "the first message i sent on the chat was not showing in the
        chat box". Confirmed live: the triggering message was never shown as a
        distinct bubble at all before this fix, only ever quoted back secondhand
        once a later step happened to reference it -- from the user's side, it
        looked like their own message had vanished."""
        self._dock.receiveMessageSignal.emit("user", original_text)
        self._pending_analysis_text = original_text
        self._pending_analysis = analysis
        self._awaiting_requirement_reply = True
        self.input_edit.clear()
        self.input_edit.setPlaceholderText("Type your answer... (Enter to send)")
        self.input_edit.setFocus()
        question = analysis.get("question") or "Could you tell me a bit more about what you need?"
        self._dock.receiveMessageSignal.emit("ai", question)

    # ------------------------------------------------------ prompt preview --

    def _ask_preview_in_chat(self, original_text, analysis):
        """Shows the exact prompt and the reasoning behind it as a normal chat message,
        then waits for a typed reply -- same conversion, same rationale as
        _ask_requirement_in_chat above (2026-09-15, direct repeated feedback: "i prefer
        everything to be in the chat"). Unlike that gate's free-form merge, the reply here
        resolves a genuine 3-way choice (send the composed prompt / send as typed instead /
        cancel) -- see send_message()'s _awaiting_preview_reply branch for the interpretation.

        Echoes original_text as its own "You" bubble first -- see _ask_requirement_in_chat's
        identical fix above for the real live report this addresses. Confirmed live: without
        this, the only place the user's own message appeared was quoted secondhand inside the
        AI's own "Message sent as you: ..." text -- never as a message actually attributed to
        the user. send_message()'s confirm branch passes already_echoed=True to _dispatch_message
        so this doesn't show a third time, identical text, once dispatch actually happens."""
        self._dock.receiveMessageSignal.emit("user", original_text)
        self._pending_analysis_text = original_text
        self._pending_analysis = analysis
        self._awaiting_preview_reply = True
        from ..agent import output_router

        lines = list(analysis.get("reasoning") or [])
        contract_line = output_router.describe_contract(analysis.get("contract"))
        if contract_line:
            lines.append(contract_line)
        composed_prompt = analysis.get("optimum_prompt") or original_text
        # Design proposal, 2026-09-16 (Dateline Dock artifact): matches render_welcome_html's
        # visual treatment (real live report: this card still looked like plain text next to
        # the now-styled welcome message) -- a teal heading, muted reasoning bullets, and the
        # composed prompt in a bordered card instead of a markdown code fence. Bypasses
        # render_markdown via _add_message's _raw_html param, same as the welcome message.
        from .chat_formatting import render_preview_html
        preview_html = render_preview_html(lines, composed_prompt, theme_colors())
        self.input_edit.clear()
        self.input_edit.setPlaceholderText("Reply to confirm, or type what to change... (Enter to send)")
        self.input_edit.setFocus()
        self._add_message("ai", "", _raw_html=preview_html)

    def _start_refinement(self, text, client):
        """Runs the refinement API call on a background thread -- it's a
        real network call and must never block the UI thread, same reasoning
        as settings_dialog.py's modelsFetchedSignal/_fetch_models. Delivers
        the result back via refinementFetchedSignal, which Qt auto-queues
        onto the main thread for _on_refinement_fetched."""
        import threading
        from ..agent.prompt_refiner import refine, get_user_profile

        self._dock.statusSignal.emit("Refining prompt...")
        # Blocks a second Send/Enter from starting a second refine() call
        # while this network round-trip is in flight. Previously unguarded --
        # a fast double-send could race two refine() calls, and whichever
        # response landed last would silently overwrite
        # _pending_refinement_text (and the panel's cards), possibly for the
        # wrong prompt. _on_refinement_fetched (both branches) re-enables
        # send_btn once this settles. stop_btn is deliberately left alone --
        # there is no cancellation wired for this background thread, and a
        # Stop button that looks actionable but does nothing would be its
        # own bug.
        self.send_btn.setEnabled(False)
        profile = get_user_profile()

        def worker():
            result = refine(text, profile, client)
            try:
                self._dock.refinementFetchedSignal.emit(text, result)
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
        self._dock.statusSignal.emit("")
        if not isinstance(result, dict) or "error" in result or "recommendations" not in result:
            self._dispatch_message(original_text, self._pending_analysis)
            return
        # _dispatch_message (the other branch above) re-enables send_btn itself
        # via _add_message; this branch doesn't reach _dispatch_message, so it
        # must undo _start_refinement's send_btn.setEnabled(False) here.
        self.send_btn.setEnabled(True)
        self._show_refinement_in_chat(result["recommendations"])

    def _show_refinement_in_chat(self, recommendations):
        """Design proposal, 2026-09-16 (Dateline Dock artifact): the 'Suggested rewordings'
        cards render in-chat now, same as the welcome message's starter prompts -- see
        render_refinement_html and this file's own comment where the old boxed panel used to
        be constructed. self.input_edit is left exactly as the user typed it (never made
        read-only) -- unlike the old panel, "send as typed instead" needs no dedicated
        button/branch: the user's own text is already sitting in the box, so hitting Send
        again just sends it, same as ignoring a starter prompt."""
        from .chat_formatting import render_refinement_html
        self._pending_refinement_cards = recommendations
        html = render_refinement_html(recommendations, theme_colors())
        self._add_message("ai", "", _raw_html=html)

    def _on_refinement_card_clicked(self, url):
        """A cartogen://refine/{index} link, from _show_refinement_in_chat -- fills the input
        box with that recommendation's refined prompt rather than sending it (spec §6: never
        auto-send a rewritten prompt the user hasn't seen), the same one-click-to-edit pattern
        _on_starter_prompt_clicked already uses."""
        parts = [p for p in url.path().split("/") if p]
        try:
            index = int(parts[-1]) if parts else -1
        except (ValueError, IndexError):
            return
        cards = self._pending_refinement_cards
        if not cards or not (0 <= index < len(cards)):
            return
        refined_prompt = cards[index].get("refined_prompt", "")
        if refined_prompt:
            self.input_edit.setPlainText(refined_prompt)
            self.input_edit.setFocus()

    def _dispatch_message(self, text, analysis=None, already_echoed=False):
        """The actual send path -- unchanged from send_message()'s original
        body. Shared by the refinement skip-path (send_message() calls this
        directly) and the post-choice path (a card's 'Use this', 'Send as
        typed instead', or the plain non-refined flow all funnel here with
        one final chosen_text string). conversation_history sees only this
        text -- no trace of a refinement step survives downstream, per spec
        §3/§11.2's decision.

        already_echoed=True (only the preview-confirm branch in send_message() passes this):
        skips the "user" bubble below because _ask_preview_in_chat already showed this exact
        text as its own message when the preview question was first asked -- without this,
        confirming would show the same original message a second time, verbatim, as if the
        user had just retyped it."""
        # receiveMessageSignal is a direct (same-thread) connection, so this emit
        # runs _add_message synchronously right here -- and _add_message always
        # re-enables send_btn (it's also used for messages that aren't part of a
        # running task). So the "disable while a task is in flight" state has to
        # be set AFTER this emit, not before, or it gets immediately clobbered.
        if not already_echoed:
            self._dock.receiveMessageSignal.emit("user", text)
        self._dock.statusSignal.emit("Thinking...")
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        agent = None
        if self._agent_provider:
            agent = self._agent_provider()

        # Checked before scheduling a background task: without this, a missing
        # key reached the provider's HTTP API and came back as a raw 401 (see
        # chat_formatting.format_send_error for the general case below) --
        # this specific, extremely common first-run scenario gets a direct
        # answer instead of a round trip that was always going to fail.
        from ..agent.auth import CredentialManager
        no_agent_msg = "**Agent could not be initialized.** Check the QGIS Python console for details."
        block_msg = no_agent_msg if agent is None else \
            CredentialManager.missing_credential_message(client=getattr(agent, "client", None))
        if block_msg:
            self._dock.receiveMessageSignal.emit("ai", block_msg)
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._dock.statusSignal.emit("")
            return

        # Connects the live task_manager.plan_updated signal once per agent instance (not
        # once per message -- a Qt-signal-connected-N-times bug already fixed once for the
        # old Activity tab, see that method's own history in git blame) and renders
        # whatever plan is currently live into the in-chat card. The memory-panel half of
        # the old TasksTabWidget.sync_with_agent moved to memory_dialog.py, which reads
        # live state fresh on open instead of needing an eager per-send sync (it's a
        # short-lived modal now, not a permanently docked tab).
        if agent is not None and hasattr(agent, "task_manager"):
            if self._connected_task_manager is not agent.task_manager:
                try:
                    agent.task_manager.plan_updated.connect(self._on_live_plan_updated)
                    self._connected_task_manager = agent.task_manager
                except Exception as e:
                    print(f"[ChatTabWidget] Failed to connect plan_updated signal: {e}")
            self._on_live_plan_updated(agent.task_manager.get_plan())

        from ..agent.task_runner import run_agent_task
        from ..agent.map_context import get_map_context_summary, filter_layers_by_selection

        # Gathered here, on the main thread, before the background QgsTask
        # starts -- QgsProject/layers aren't thread-safe to touch from run().
        map_ctx = get_map_context_summary()
        # Broadsheet redesign Phase 3 (mockup 1l, layer context picker): a no-op filter
        # (returns map_ctx unchanged) unless the user has actually opened
        # layer_context_btn at least once this session and unchecked something.
        map_ctx = filter_layers_by_selection(map_ctx, self._layer_context_selection)
        # analysis=None is meaningful, not "not supplied" -- it is exactly
        # what send_message()'s _awaiting_preview_reply edit-fallback branch passes to mean
        # "skip the register's enrichment entirely" (the escape hatch for when the matched
        # task is simply wrong). Every call site above passes its own analysis (or
        # explicitly None) already, so there is no caller left that needs a
        # self._pending_analysis fallback here -- and a fallback used to sit
        # here, which silently undid "Send as typed instead": clicking it
        # looked like it worked, then this line re-applied the very
        # enrichment, and the very output contract, the user had just opted
        # out of. Found by a real click on a real button in a headless
        # QGIS session (tests/test_chat_widget_live.py); no unit test on the
        # pure logic could have caught it, because the pure logic was never
        # wrong -- only this one call site's default was.
        analysis_directive = analysis.get("directive", "") if isinstance(analysis, dict) else ""
        if analysis_directive:
            map_ctx = dict(map_ctx or {})
            map_ctx["task_directive"] = analysis_directive

        # What actually goes over the wire. Identical to the text shown in the
        # preview panel -- the preview is a disclosure, not a mock-up, so the
        # two must come from the same value.
        sent_text = text
        if isinstance(analysis, dict) and analysis.get("user_message"):
            sent_text = analysis["user_message"]

        new_contract = analysis.get("contract") if isinstance(analysis, dict) else None
        if new_contract is not self._pending_contract:
            # A genuinely new request, not the contract follow-up re-entering.
            self._contract_followup_used = False
        self._pending_contract = new_contract
        self._executed_tools = []
        self._current_turn_steps = []
        self._attached_paths = []
        self._pending_analysis = None
        self._pending_analysis_text = None

        def on_complete(response, err):
            self._active_task = None
            self.stop_btn.setEnabled(False)
            # Runs on the main GUI thread already (this function directly calls
            # receiveMessageSignal.emit below with no extra thread-marshalling), so touching
            # chat_browser here directly is safe. Flushed before the turn's own response bubble
            # so the summary block reads in chronological order: user message, tool-call
            # summary, then the answer.
            self._flush_tool_steps_summary()
            if err:
                self._dock.receiveMessageSignal.emit("ai", format_send_error(err))
                # A multi-tool-call turn can accumulate usage on earlier,
                # successful client.complete() calls before a later one in the
                # same turn errors out -- refresh here too so that usage isn't
                # silently dropped from the displayed total just because the
                # turn as a whole ended in an error.
                self._refresh_usage_label(agent)
            else:
                self._dock.receiveMessageSignal.emit("ai", response if response else "_(empty response)_")
                self._after_successful_response(agent, response)
                self._enforce_output_contract(sent_text)
                self._show_safety_gate_in_chat(agent)

        def on_status(msg):
            self._dock.statusSignal.emit(msg)

        def on_tool_step(name, status, error):
            # Called from the background task thread -- emit() is thread-safe;
            # Qt queues the connected slot (_add_tool_step) onto this widget's
            # own (main GUI) thread automatically, same as statusSignal/
            # receiveMessageSignal already rely on.
            self._dock.toolStepSignal.emit(name, status, error or "")

        # Keep a strong reference to the running task on self — QgsApplication.taskManager()
        # does not guarantee the Python-side wrapper survives otherwise, which can cause the
        # task to silently never execute or never report completion.
        self._active_task = run_agent_task(
            agent=agent,
            user_text=sent_text,
            description="Cartogen AI Analysis",
            on_complete=on_complete,
            on_status=on_status,
            map_context=map_ctx,
            on_tool_step=on_tool_step,
        )

    def _enforce_output_contract(self, sent_text):
        """After a turn: did the answer actually come back in the promised form?

        The contract said, before the call, what the user would get. If the
        tool that writes it never ran, one -- and only one -- follow-up turn is
        sent asking for it, with the reason stated in the chat so the extra
        call is never silent. See agent/output_router.py for why the renderer
        is not simply called directly from here.
        """
        contract = self._pending_contract
        if not contract:
            return
        from ..agent import output_router

        executed = list(self._executed_tools)
        if output_router.satisfied(contract, executed):
            self._pending_contract = None
            self._contract_followup_used = False
            return

        has_layers = None
        try:
            from qgis.core import QgsProject
            has_layers = bool(QgsProject.instance().mapLayers())
        except Exception:
            pass

        instruction = output_router.followup_instruction(
            contract, executed, already_retried=self._contract_followup_used,
            has_layers=has_layers)
        if instruction is None:
            # Already retried once. Say so plainly rather than trying again.
            self._dock.receiveMessageSignal.emit(
                "ai", "_%s_" % output_router.delivery_note(contract, executed))
            self._pending_contract = None
            self._contract_followup_used = False
            return

        self._contract_followup_used = True
        self._dock.receiveMessageSignal.emit(
            "ai", "_%s Asking for it now._" % output_router.delivery_note(contract, executed))
        # Re-enter dispatch with the contract preserved, so the follow-up turn
        # is checked the same way -- and _contract_followup_used stops it there.
        followup_analysis = {"contract": contract, "user_message": instruction, "directive": ""}
        self._dispatch_message(instruction, followup_analysis)

    def cancel_active_task(self):
        """Cancels the in-flight request, if any -- the cancel-only core of
        _stop_current_task below, exposed separately so plugin_main.py's unload() can call
        it too (QGIS-002, 2026-09-13 audit): unloading/reloading the plugin while a request
        was in flight used to leave a background QgsTask running against a dock widget
        about to be deleted -- the direct trigger for QGIS-001's finished()-callback crash
        (now also fixed with its own try/except, but stopping the task from ever running
        against a doomed widget in the first place is the better fix). Deliberately does
        NOT touch stop_btn/statusSignal -- those are chat-tab UI feedback that doesn't
        apply (and could itself raise on a widget mid-teardown) when called from unload()."""
        if self._active_task is None:
            return
        try:
            self._active_task.cancel()
        except Exception as e:
            print(f"[ChatTabWidget] Failed to cancel task: {e}")

    def _stop_current_task(self):
        """Cancels the in-flight request. This is cooperative, not instant --
        it sets QgsTask's isCanceled() flag, which agent.run()'s tool-calling
        loop checks both once per LLM round AND once per individual tool call
        within a multi-tool-call batch (QGIS-003, 2026-09-13 audit -- a batch
        used to only be checked between rounds, so it couldn't be interrupted
        mid-batch; see agent/agent.py's should_stop param for both check
        sites), so it stops before the NEXT LLM call or the NEXT tool step,
        whichever comes first, rather than interrupting whichever call is
        already in flight. stop_btn stays disabled until on_complete
        actually fires so the UI doesn't claim it's stopped before it
        really has."""
        if self._active_task is None:
            return
        self.cancel_active_task()
        self.stop_btn.setEnabled(False)
        self._dock.statusSignal.emit("Stopping...")

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
        self._dock.usageSignal.emit(text or "")

    def _after_successful_response(self, agent, response_text):
        """Runs on the main thread (called from on_complete, itself invoked
        from AgentQgsTask.finished()). Persists chat history and flashes any
        layer the reply mentions on the canvas."""
        if agent is None:
            return

        self._refresh_usage_label(agent)

        try:
            from ..agent.chat_persistence import save_chat_history
            history = agent._read_history_snapshot() if hasattr(agent, "_read_history_snapshot") else getattr(agent, "conversation_history", [])
            save_chat_history(history)
        except Exception as e:
            print(f"[ChatTabWidget] Failed to save chat history: {e}")

        try:
            from qgis.core import QgsProject
            from qgis.utils import iface
            from .canvas_highlight import flash_layer_extent, find_mentioned_layers, zoom_to_layers

            layers = list(QgsProject.instance().mapLayers().values())
            matched = find_mentioned_layers(response_text or "", layers)

            # Real user report: after the agent creates/modifies layers, the
            # canvas view keeps whatever extent it already had -- the result
            # is never actually visible without the user manually zooming.
            # Runs once per turn (not once per tool call) against the same
            # layers already resolved for the highlight flash below, so
            # "what the canvas shows" and "what got highlighted" always
            # agree with each other.
            zoom_to_layers(iface, matched)

            def _on_expired(highlight):
                if highlight in self._active_highlights:
                    self._active_highlights.remove(highlight)

            for layer in matched:
                highlight = flash_layer_extent(iface, layer, on_expired=_on_expired)
                if highlight is not None:
                    self._active_highlights.append(highlight)
        except Exception as e:
            print(f"[ChatTabWidget] Canvas highlight failed: {e}")

    @staticmethod
    def _attachment_disclosure_note():
        """API-007, 2026-09-14 audit: no inline notice existed at the moment of file
        attachment telling the user that its content (including image bytes, for an
        image attachment) is about to be sent to whichever AI provider is currently
        configured -- the general privacy posture is documented in SECURITY.md/the
        provider settings dialog's own key_tooltip text, but nothing surfaced it at the
        specific moment it becomes true for THIS file. Ollama is local -- nothing leaves
        the machine -- so it gets a different, accurate note rather than a generic
        third-party-sending warning that would be false for it."""
        provider_value = QgsSettings().value(SETTINGS_PROVIDER, "openrouter")
        if provider_value == "ollama":

            return "This file's content stays local (Ollama) -- nothing is sent to a third party."
        label = next(
            (p["provider_label"] for p in _PROVIDERS if p["value"] == provider_value),
            provider_value,
        )
        return f"This file's content will be sent to {label} for analysis."

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
        disclosure = self._attachment_disclosure_note()
        self._dock.receiveMessageSignal.emit(
            "ai", f"📎 **Attaching:** {name}\n\n_{disclosure}_\n\nReading...")
        self._dock.statusSignal.emit("Reading file...")

        agent = None
        if self._agent_provider:
            agent = self._agent_provider()

        thread = threading.Thread(
            target=self._read_and_analyze_file, args=(agent, name, path), daemon=True
        )
        thread.start()

    def _read_and_analyze_file(self, agent, name, path):
        """PERF-005, 2026-09-13 audit: read_attached_file (pypdf/docx/pandas parsing) used
        to run synchronously on the Qt main thread inside attach_file(), before the
        background analysis thread below was even started -- a large PDF/DOCX/table-heavy
        file could freeze the whole GUI while it parsed. read_attached_file has zero Qt/QGIS
        dependency (see its own docstring), so it's safe to run here instead, on the same
        background thread that was already doing the LLM analysis. Logic below is otherwise
        unchanged from what attach_file() used to do synchronously."""
        data, err = _read_attached_file(path)
        if err is not None:
            self._dock.receiveMessageSignal.emit("ai", f"Error reading {name}: {err}")
            return

        # Remembered for the next chat message so the file becomes part of the
        # task, not just a one-off analysis -- see analyze_request(attachments=).
        if path not in self._attached_paths:
            self._attached_paths.append(path)

        from ..agent import file_io
        kind = file_io.classify(path)
        carried = (" It will also be used with your next message as a %s input."
                   % kind) if kind else ""
        self._dock.receiveMessageSignal.emit(
            "ai", f"📎 **File attached:** {name}{carried}\n\nAnalyzing...")
        self._dock.statusSignal.emit("Analyzing...")

        self._analyze_file(agent, name, path, data)

    def _analyze_file(self, agent, name, path, data):
        try:
            from ..agent.auth import CredentialManager
            no_agent_msg = "**Agent could not be initialized.** Check the QGIS Python console for details."
            block_msg = no_agent_msg if agent is None else \
                CredentialManager.missing_credential_message(client=getattr(agent, "client", None))
            if block_msg:
                self._dock.receiveMessageSignal.emit("ai", block_msg)
                return

            client = getattr(agent, "client", None)
            if client is not None and hasattr(client, "set_status_callback"):
                client.set_status_callback(lambda msg: self._dock.statusSignal.emit(msg))

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

            self._dock.receiveMessageSignal.emit("ai", response if response else "_(empty response)_")
        except Exception as e:
            traceback.print_exc()
            self._dock.receiveMessageSignal.emit("ai", f"**Error analyzing file:** {e}")
        finally:
            self._dock.statusSignal.emit("")
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
        # Reads via the same lock-protected snapshot run() itself uses (see agent.py's
        # _history_lock) when the real agent provides it -- this vision-analysis call runs
        # on the main Qt thread while a normal chat turn could be mid-flight on the
        # background QgsTask thread, appending to this same list concurrently. Falls back
        # to the raw attribute for a test double that doesn't implement the method.
        if hasattr(agent, "_read_history_snapshot"):
            messages.extend(agent._read_history_snapshot())
        else:
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
        message = result.get("message")
        if not isinstance(message, dict):
            message = {}
        content = message.get("content")
        if not content:
            return (
                "The current model did not return any analysis. "
                "Vision support depends on the model; try a vision-capable model in Settings."
            )
        try:
            user_entry = {"role": "user", "content": f"[Attached image: {name}]"}
            assistant_entry = {"role": "assistant", "content": content}
            if hasattr(agent, "_append_history"):
                agent._append_history(user_entry, assistant_entry)
            else:
                agent.conversation_history.append(user_entry)
                agent.conversation_history.append(assistant_entry)
                if hasattr(agent, "_trim_history"):
                    agent._trim_history()
        except Exception:
            pass
        return content
