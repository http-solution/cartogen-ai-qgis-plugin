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

import os
import threading

from qgis.PyQt.QtCore import Qt, pyqtSignal, QSize, QTimer
from qgis.PyQt.QtGui import QTextCursor
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QPushButton, QTextEdit,
)
from ..logger import log_warning


from . import reply_vocab
from .chat_formatting import (
    render_markdown, _clock_time, now_iso, escape_plain_text, summarize_tool_result, render_tool_steps_toggle_html,
    format_send_error,
)
from .theme import theme_colors, extract_theme_palette
from .icons import themed_icon
from .chat_view_presenter import ChatViewPresenter
from .chat_input_controller import ChatInputController

# _ask_preview_in_chat's reply interpretation (2026-09-15 boxed-panel-to-in-chat conversion):
# the old "Send this / Send as typed instead / Cancel" 3-way button choice now resolves from
# free text. Deliberately generous but not fuzzy-matched -- an unrecognized reply always falls
# through to the "send as typed" edit path (see send_message()), never silently ignored or
# misread as a confirmation it wasn't.
# Router-card replies (casual "yes" is fine there). A pending DESTRUCTIVE gate uses the stricter
# reply_vocab.gate_reply -- see reply_vocab.py and rc7 smoke test finding F16.
_PREVIEW_CONFIRM_REPLIES = reply_vocab.ROUTER_CONFIRM
_PREVIEW_CANCEL_REPLIES = reply_vocab.CANCEL


def _normalize_preview_reply(text):
    return reply_vocab.normalize_reply(text)


class ChatInputEdit(QTextEdit):
    """Multi-line input that sends on Enter and inserts a newline on Shift+Enter."""
    sendRequested = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Part B §9 UX verification, 2026-09-20: live-tested (QTest.keyClick against a
        # real widget, not just read) that Tab pressed while focus was in this box did
        # nothing but insert a literal tab character -- QTextEdit's own default, since
        # multi-line editors generally want Tab available for indentation. This input
        # has no such use for it (Shift+Enter already covers "insert a newline"; there
        # is no code/indentation content a user would ever type here), and the effect
        # was a real keyboard-navigation dead end: nothing after this widget (send_btn,
        # stop_btn) was reachable by Tab at all. setTabChangesFocus is Qt's own built-in
        # switch for exactly this case -- no custom key handling needed.
        self.setTabChangesFocus(True)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.sendRequested.emit()
            return
        # Same verification pass: Escape did nothing at all (confirmed live -- typed
        # text survived an Escape press unchanged). Clearing the box on Escape is the
        # ordinary convention for a single-purpose text input (most chat/search boxes),
        # and deliberately narrow -- it only clears whatever's currently typed, it does
        # NOT cancel an in-flight request (that's the Stop button's own, separate job,
        # already reachable via Tab once this fix is in) and does NOT touch any pending
        # requirement/preview-reply state (chat_tab_widget.py's own _awaiting_* flags),
        # since guessing at "cancel the whole pending flow" from one ambiguous key is a
        # bigger, real product decision this fix isn't making unilaterally.
        if event.key() == Qt.Key.Key_Escape and self.toPlainText():
            self.clear()
            return
        super().keyPressEvent(event)


class ChatTabWidget(QWidget):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self._dock = dock
        # Composed rather than inlined (2026-09-20, Phase 11 architecture restructuring --
        # docs/IMPLEMENTATION_TRACKER.md §4): chat_view_presenter.py owns tool-step/plan-
        # progress rendering, chat_input_controller.py owns file-attachment analysis -- the
        # two genuinely self-contained subsystems this file's own module docstring flags.
        # Both operate on `self` (this widget) directly rather than owning separate state,
        # since test_chat_widget_live.py's live Qt tests and dock_widget.py's signal wiring
        # both reach several of these methods/attributes by their original widget-level
        # names -- see each class's own module docstring.
        self.presenter = ChatViewPresenter(self)
        self.input_controller = ChatInputController(self)
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
        # The "download local data, or fetch online?" question (see _ask_local_data_in_chat and
        # agent/local_data_sources.py). _local_data_pending holds the request it's about:
        # {"text", "analysis", "themes", "stage": "offer"|"confirm_size", "region"}.
        self._awaiting_local_data_reply = False
        self._local_data_pending = None
        # "online" is remembered for the session, so the same question isn't asked on every
        # request after the user has already said no.
        self._local_data_declined = False
        # Set when a request resumes after the local-data question: skip the offer this once and
        # don't echo the user's message again (it was shown when the question was asked).
        self._resume_after_local_data = False
        self._original_already_shown = False
        # Several separate requests pasted as one message run as a queue, one at a time (agent/job_queue.py).
        self._job_queue = None
        self._awaiting_job_queue_reply = False
        self._job_queue_running = False
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
        # True once the user pressed Stop for the turn in flight (see _stop_current_task and on_complete).
        self._turn_stopped = False
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

        from ...infrastructure.deps import get_dependency_warning_message
        self._dep_warning = get_dependency_warning_message()

        self.init_ui()

    @property
    def _agent_provider(self):
        return self._dock._agent_provider

    def _pending_confirmation_task(self, agent):
        """The most recently updated task still awaiting a destructive-action confirmation
        gate (agent_orchestrator.py's _real_execute_tool PREVIEW_REQUIRED handling), or None. Only tasks
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
            # A readable line, not the raw dict (rc11 smoke test, #124). The full result stays in the task record.
            readable = summarize_tool_result(exec_res)
            failed = isinstance(exec_res, dict) and bool(exec_res.get("error"))
            agent.task_manager.update_task(task_id, "FAILED" if failed else "DONE",
                                           f"Executed `{pending_tool}`: {exec_res}")
            self._dock.receiveMessageSignal.emit(
                "ai", f"{'⚠️ **Confirmed, but it failed' if failed else '✅ **Confirmed & executed'}"
                      f" (Task {task_id}, `{pending_tool}`):** {readable}")
            self._continue_request_after_confirmation(failed, pending_tool, readable, task.get("origin_request"))
        else:
            agent.task_manager.update_task(task_id, "FAILED", "Cancelled by User")
            self._dock.receiveMessageSignal.emit(
                "ai", f"❌ **Cancelled Task {task_id}:** {task.get('description')}")

    def _continue_request_after_confirmation(self, failed, tool_name, summary, original=None):
        """After a confirmed step succeeded, resumes the user's original request once if it asked for more than that step.

        The confirm button runs the tool directly, with no model turn (see _resolve_pending_confirmation), so a request such as
        "write the score to a field, then style the layer" ended at the write (rc15/rc17 hand tests, D05). At most
        reply_vocab.MAX_CONTINUATIONS follow-up turns per original request, so a chain of confirmations cannot loop."""
        if failed or not original or not reply_vocab.has_followup_steps(original, tool_name):
            return
        if getattr(self, "_continuation_count", 0) >= reply_vocab.MAX_CONTINUATIONS:
            return
        self._dock.receiveMessageSignal.emit("ai", "Continuing with the rest of your request...")
        self._dispatch_message(reply_vocab.continuation_prompt(original, tool_name, summary), None, already_echoed=True)

    def _expire_pending_previews(self, agent):
        """Closes every pending confirmation after an unrelated message was sent (F16 step 3, #125)."""
        if agent is None or not hasattr(agent, "task_manager"):
            return
        for task in list(agent.task_manager.tasks):
            if task.get("status") == "PREVIEW_READY" and task.get("pending_tool"):
                self._posted_safety_gate_task_ids.discard(task.get("id"))
                agent.task_manager.update_task(task["id"], "FAILED", "Expired: a new request was sent")

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
        # The request that produced THIS card, kept on the task so a continuation after Apply never uses a later, unrelated message.
        task.setdefault("origin_request", getattr(self, "_last_user_request", None))
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
        self._follow_bottom = True
        if sb:
            sb.rangeChanged.connect(self._on_scrollbar_range_changed)
            sb.actionTriggered.connect(self._on_user_scroll_action)
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

        from ...infrastructure.auth import CredentialManager
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
        self._awaiting_local_data_reply = False
        self._local_data_pending = None
        # #147: tool steps collected for a turn of the previous project must not be summarised into the next turn's reply.
        self._current_turn_steps = []
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
        # time (a clock time such as "23:41", not a relative label that would never update) instead of falsely claiming to have just happened --
        # this was a real, live-reported bug (a stale Ollama-provider error looked
        # like it had just occurred next to a brand-new reply from a different
        # provider). See chat_persistence.py's _attach_timestamps for where the ts
        # comes from.
        colors = theme_colors()
        restore_ts = getattr(self, "_pending_restore_ts", None)
        self._pending_restore_ts = None
        timestamp = _clock_time(restore_ts) if restore_ts else _clock_time(now_iso())
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

        def _do_scroll():
            # The two delayed calls below can fire after the dock (and so the browser) was destroyed -- on QGIS shutdown,
            # plugin unload, or in CI when a test tears its window down. An uncaught RuntimeError inside a Qt slot aborts the
            # whole process under PyQt6 (seen: "Aborted (core dumped)" in the live job once the panel opened at startup).
            try:
                self.chat_browser.moveCursor(QTextCursor.MoveOperation.End)
                sb = self.chat_browser.verticalScrollBar()
                if sb:
                    sb.setValue(sb.maximum())
            except RuntimeError:
                pass

        self._follow_bottom = True        # a new message was added: show it, and keep following until the user scrolls up
        _do_scroll()
        QTimer.singleShot(50, _do_scroll)
        QTimer.singleShot(150, _do_scroll)

    def _on_user_scroll_action(self, _action):
        """Wheel, drag and key scrolling only (QAbstractSlider.actionTriggered is not emitted for setValue()).
        Records whether the user left the bottom, so later layout changes stop pulling the view back.
        rc11 smoke test: the view stayed at the top of a tall confirm card and did not follow later messages. Likely cause
        (unverified in a real QGIS session): the card's layout settles after the forced scroll, so the range grows by more
        than the old 160 px 'near the bottom' window and the follow rule gave up. The rule is now 'follow until the user
        scrolls up'."""
        from qgis.PyQt.QtCore import QTimer

        def _update():
            try:
                sb = self.chat_browser.verticalScrollBar()
                if sb:
                    self._follow_bottom = (sb.maximum() - sb.value()) < 24
            except RuntimeError:
                pass
        QTimer.singleShot(0, _update)     # the slider moves after the signal, so read its position afterwards

    def _on_scrollbar_range_changed(self, min_val, max_val):
        """When document geometry changes asynchronously, follow to bottom unless the user scrolled up."""
        sb = self.chat_browser.verticalScrollBar()
        if sb and self._follow_bottom:
            sb.setValue(max_val)

    def _set_status(self, text):
        self.status_label.setText(text)

    def _set_usage_label(self, text):
        self.usage_label.setText(text)

    def _add_tool_step(self, name, status, error):
        """See chat_view_presenter.ChatViewPresenter.add_tool_step for the real logic and
        its full rationale. Thin delegator, kept under its original name since dock_widget.py
        connects toolStepSignal straight to it."""
        self.presenter.add_tool_step(name, status, error)

    def _flush_tool_steps_summary(self):
        """See chat_view_presenter.ChatViewPresenter.flush_tool_steps_summary."""
        self.presenter.flush_tool_steps_summary()

    def _on_live_plan_updated(self, plan_data):
        """See chat_view_presenter.ChatViewPresenter.on_live_plan_updated. Thin delegator,
        kept under its original name since dock_widget.py connects planUpdatedSignal (and
        _dispatch_message connects task_manager.plan_updated) straight to it, and
        test_chat_widget_live.py calls it directly."""
        self.presenter.on_live_plan_updated(plan_data)

    def _tick_plan_spinner(self):
        """See chat_view_presenter.ChatViewPresenter.tick_plan_spinner."""
        self.presenter.tick_plan_spinner()

    def _replace_tracked_block(self, block, new_html):
        """See chat_view_presenter.ChatViewPresenter.replace_tracked_block. Kept as a thin
        delegator since _on_step_anchor_clicked below (the tool-steps toggle click handler)
        calls it by this name."""
        self.presenter.replace_tracked_block(block, new_html)

    def _clear_plan(self):
        """See chat_view_presenter.ChatViewPresenter.clear_plan."""
        self.presenter.clear_plan()

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
        host = url.host()
        path = url.path()
        if not host and path:
            path_parts = [p for p in path.split("/") if p]
            if path_parts:
                host = path_parts[0]
                path = "/" + "/".join(path_parts[1:])

        if host == "starter":
            self._on_starter_prompt_clicked(url)
            return
        if host == "refine":
            self._on_refinement_card_clicked(url)
            return
        if host in ("confirm", "cancel"):
            self._on_safety_gate_link_clicked(url)
            return
        if host == "clearplan":
            self._clear_plan()
            return
        if host == "task":
            self._on_plan_task_clicked(url)
            return
        if host == "action":
            self._on_chat_action_clicked(url)
            return
        if host == "export":
            self._on_export_action_clicked(url)
            return
        if host == "prompt":
            import urllib.parse
            prompt_text = urllib.parse.unquote(path.lstrip("/"))
            if not prompt_text and url.hasQuery():
                from qgis.PyQt.QtCore import QUrlQuery
                q = QUrlQuery(url)
                prompt_text = q.queryItemValue("text") or urllib.parse.unquote(url.query())
            if prompt_text:
                self.input_edit.setPlainText(prompt_text)
                from qgis.PyQt.QtGui import QTextCursor
                cursor = self.input_edit.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.input_edit.setTextCursor(cursor)
                self.input_edit.setFocus()
                if self._dock:
                    self._dock.statusSignal.emit("Staged prompt in chat input.")
            return
        if host == "zoom":
            parts = [p for p in path.split("/") if p]
            layer_name = parts[-1] if parts else None
            from ..agent.tools.vector_tools import zoom_to_layer
            if layer_name and layer_name != "zoom":
                res = zoom_to_layer(layer_name)
                if self._dock and res.get("success"):
                    self._dock.statusSignal.emit(f"Zoomed to {layer_name}")
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
                from ..agent.tools.vector_tools import zoom_to_layer
                res = zoom_to_layer(action_parts[1])
                if self._dock and res.get("success"):
                    self._dock.statusSignal.emit(f"Zoomed to {action_parts[1]}")
                return
            if len(action_parts) >= 2 and action_parts[0] == "export":
                from qgis.PyQt.QtCore import QUrl
                self._on_export_action_clicked(QUrl(f"cartogen://export/{action_parts[1]}"))
                return
            clean_text = " ".join(action_parts).replace("_", " ")
            if clean_text and not clean_text.startswith("act_"):
                self.input_edit.setPlainText(clean_text)
                from qgis.PyQt.QtGui import QTextCursor
                cursor = self.input_edit.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.input_edit.setTextCursor(cursor)
                self.input_edit.setFocus()
                return
            self._dock.receiveMessageSignal.emit(
                "ai", "_This action is no longer available (session expired or project changed)._"
            )
            return

        kind = action.kind
        payload = action.payload or {}
        layer_name = payload.get("layer_name")

        if kind == "local_data_choice":
            # Clickable-chip half of the local-data download/online choice (see
            # _offer_local_data_choice, chat_tab_widget.py) -- reuses the exact same
            # _on_local_data_reply a typed "download"/"online" reply already resolves through,
            # so both affordances stay in sync with a single implementation.
            self._awaiting_local_data_reply = False
            self.input_edit.setPlaceholderText(self._default_input_placeholder)
            self._on_local_data_reply(payload.get("choice"))
            return

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
            from ..agent.tools.vector_tools import zoom_to_layer
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

        if self._job_queue_gate(text):
            return

        # The local-data question (see _ask_local_data_in_chat) is outstanding. A recognised
        # answer resolves it; anything else is treated as a new request and the question is
        # dropped, the same way an unrecognised preview reply is "send as typed".
        if self._awaiting_local_data_reply:
            self._awaiting_local_data_reply = False
            self.input_edit.setPlaceholderText(self._default_input_placeholder)
            from ..agent import local_data_sources
            choice = local_data_sources.parse_reply(text)
            if choice is not None:
                self._dock.receiveMessageSignal.emit("user", text)
                self.input_edit.clear()
                self._on_local_data_reply(choice)
                return
            self._local_data_pending = None

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
        if self._awaiting_requirement_reply and reply_vocab.is_new_request(text):
            # A whole new request typed instead of an answer abandons the open question; it is NOT pasted under the old request.
            self._awaiting_requirement_reply = False
            self._pending_analysis_text = None
            self._pending_analysis = None
            self.input_edit.setPlaceholderText(self._default_input_placeholder)
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

        # A destructive-action confirmation gate (field_calculator etc. -- see agent_orchestrator.py's
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
            # Only an explicit word confirms a destructive action -- a casual "yes"/"ok" typed to
            # answer something else must never (F16) -- and only while the preview is recent.
            decision = reply_vocab.gate_reply(text)
            if decision == "confirm" and pending_task.get("egress_override"):
                # A decision to let protected data leave the machine is made on the card, not with a typed word
                # (rc11 smoke test, #125: a typed "confirm" approved a cloud override the user was never shown).
                self._dock.receiveMessageSignal.emit("user", text)
                self._dock.receiveMessageSignal.emit(
                    "ai", "Sending protected data to a cloud provider can only be approved with the **Send to cloud once** "
                          "button on its card. Typing a word does not approve it. Say **cancel** to drop it.")
                return
            if decision is None and reply_vocab.router_reply(text) == "confirm":
                # "yes" / "ok" / "sure" / "go" never confirm a destructive action, and must not be passed to the model
                # either: it answered by retrying the same action through another tool (rc11 smoke test, #125).
                self._dock.receiveMessageSignal.emit("user", text)
                self._dock.receiveMessageSignal.emit(
                    "ai", "That is not enough to confirm a change that cannot be undone. Click the button on the card, "
                          "or type **Confirm** to go ahead, or **Cancel** to drop it.")
                return
            if decision is None:
                # An unrelated message: the preview is not consent for anything the user types later (F16 step 3).
                self._expire_pending_previews(agent)
                pending_task = None
            if pending_task is not None and decision == "confirm" and not reply_vocab.preview_is_fresh(pending_task.get("updated_at")):
                self._dock.receiveMessageSignal.emit("user", text)
                self._dock.receiveMessageSignal.emit(
                    "ai",
                    "That confirmation request is more than "
                    f"{reply_vocab.PREVIEW_MAX_AGE_SECONDS // 60} minutes old, so typing Confirm no longer "
                    "applies it. Use the Confirm button in the Activity tab, or ask again.")
                return
            if pending_task is not None and decision is not None:
                self._dock.receiveMessageSignal.emit("user", text)
                self._resolve_pending_confirmation(agent, pending_task, confirmed=(decision == "confirm"))
                return

        # A fresh send attempt abandons any still-pending refinement cards from a previous
        # message -- the practical equivalent of spec §7's "user closes the card without
        # choosing". No explicit hide needed now that the cards render in-chat (they're just
        # scrollback, not a widget that stays visible) -- only the pending-selection state
        # needs clearing, so a stale click on an old card's link can't resurrect it.
        self._pending_refinement_cards = None

        from ..services.prompt_refiner import (
            analyze_request, should_refine, is_refinement_enabled, is_prompt_preview_enabled,
        )
        try:
            from ..agent.map_context import get_map_context_summary
            request_context = get_map_context_summary()
        except Exception:
            request_context = {}
        analysis = analyze_request(text, request_context, self._attached_paths)

        # Asked before anything else: whether the data this request needs should be downloaded
        # locally first changes what every later step (preview, tool choice) should do.
        if self._resume_after_local_data:
            self._resume_after_local_data = False
        else:
            self._original_already_shown = False
            if self._maybe_ask_local_data(text, analysis):
                return

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
        # At most TWO rounds of questions (the first, and one follow-up for a slot the first reply left open -- see
        # test_multi_round_clarification_shows_every_reply_in_chat). Each answered round is appended as "\n\nDetails:", so
        # the count says how many have happened. rc10 smoke test: the same "Which facility or service type?" came back
        # three times and each repeated reply grew the request ("Details: ... Details: ...") without satisfying it.
        # After the second round the register's "ask once, then default" policy applies: go on to the preview.
        if analysis.get("blocking") and text.count("\n\nDetails:") < 2:
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
        self._echo_original(original_text)
        self._pending_analysis_text = original_text
        self._pending_analysis = analysis
        self._awaiting_requirement_reply = True
        self.input_edit.clear()
        self.input_edit.setPlaceholderText("Type your answer... (Enter to send)")
        self.input_edit.setFocus()
        question = analysis.get("question") or "Could you tell me a bit more about what you need?"
        self._dock.receiveMessageSignal.emit("ai", question)

    # ------------------------------------------------------ job queue --

    def _job_queue_gate(self, text):
        """True when this message was consumed by the job-queue flow (proposed a split, or answered the proposal).

        2026-10-09 cost investigation: five unrelated analyses pasted as one message ran as one turn and spent the whole round budget.
        When the message holds several whole requests (agent/job_queue.split_jobs: numbered or blank-line-separated, never a sentence
        count), this shows the split and asks first; confirmed jobs then run one at a time, each its own turn with its own budget."""
        from ..agent import job_queue
        if self._awaiting_job_queue_reply:
            self._awaiting_job_queue_reply = False
            self.input_edit.setPlaceholderText(self._default_input_placeholder)
            lowered = text.lower().strip().rstrip("!.?")
            if lowered in ("first", "only first", "just the first", "first one"):
                self._dock.receiveMessageSignal.emit("user", text)
                self.input_edit.clear()
                self._job_queue.keep_only_first()
                self._start_next_job()
                return True
            choice = reply_vocab.router_reply(text) or ("confirm" if lowered in ("run", "run all", "run them", "start", "go") else None)
            if choice == "confirm":
                self._dock.receiveMessageSignal.emit("user", text)
                self.input_edit.clear()
                self._start_next_job()
                return True
            if choice == "cancel":
                self._dock.receiveMessageSignal.emit("user", text)
                self.input_edit.clear()
                self._job_queue = None
                self._dock.receiveMessageSignal.emit("ai", "Cancelled; nothing was run. Send the requests one at a time when you are ready.")
                return True
            self._job_queue = None            # something else was typed: it is a new message, the proposal is dropped
            return False
        if self._job_queue_running or self._awaiting_requirement_reply or self._awaiting_preview_reply or self._awaiting_local_data_reply:
            return False
        jobs = job_queue.split_jobs(text)
        if not jobs:
            return False
        self._dock.receiveMessageSignal.emit("user", text)
        self.input_edit.clear()
        self._job_queue = job_queue.JobQueue(jobs)
        self._awaiting_job_queue_reply = True
        self.input_edit.setPlaceholderText("Reply run, first, or cancel")
        self._dock.receiveMessageSignal.emit("ai", (
            f"**This looks like {len(jobs)} separate requests.** Running them as one message makes the assistant try all of them in "
            f"one turn, which is slow and uses a lot of your API credit. I can run them one at a time, each with its own budget "
            f"and its own result:\n\n{job_queue.preview_text(jobs)}\n\n"
            f"Reply **run** to start with job 1, **first** to run only job 1, or **cancel**. (If this is really one analysis, "
            f"cancel and send it again as a single numbered list of short steps.)"))
        return True

    def _start_next_job(self):
        """Sends the next pending job through the normal send path; sets the running flag so a job is never split again."""
        queue = self._job_queue
        item = queue.next_pending() if queue is not None else None
        if item is None:
            self._finish_job_queue()
            return
        index, job = item
        self._job_queue_running = True
        self._dock.receiveMessageSignal.emit("ai", f"**Job {index + 1} of {len(queue)}**")
        self.input_edit.setPlainText(job)
        self.send_message()

    def _finish_job_queue(self):
        queue = self._job_queue
        if queue is not None and len(queue) > 1:
            self._dock.receiveMessageSignal.emit("ai", f"_All jobs finished: {queue.summary()}._")
        self._job_queue = None
        self._job_queue_running = False

    def _advance_job_queue(self, ok):
        """Called when a turn ends. Records the job's outcome and starts the next one, or pauses after a failure or a Stop."""
        queue = self._job_queue
        if queue is None or not self._job_queue_running:
            return
        if self._awaiting_preview_reply or self._awaiting_requirement_reply or self._awaiting_local_data_reply:
            return          # the job is waiting for the user's answer; its turn will end again after that
        queue.finish_current(ok)
        if not ok:
            self._job_queue_running = False
            left = queue.pending_count()
            self._awaiting_job_queue_reply = left > 0
            if left:
                self.input_edit.setPlaceholderText("Reply run to continue with the rest, or cancel")
                self._dock.receiveMessageSignal.emit("ai", (
                    f"**Paused: job {max(i for i, state in enumerate(queue.status) if state == 'failed') + 1} did not complete.** "
                    f"{queue.summary()}. Reply **run** to continue with the {left} remaining, or **cancel**."))
            else:
                self._finish_job_queue()
            return
        if queue.pending_count():
            QTimer.singleShot(400, self._start_next_job)
        else:
            self._finish_job_queue()

    def _echo_original(self, text):
        """Shows the user's message as their own bubble, unless it was already shown when the
        local-data question was asked about it (then the resumed request mustn't repeat it)."""
        if self._original_already_shown:
            self._original_already_shown = False
            return
        self._dock.receiveMessageSignal.emit("user", text)

    # ---------------------------------------------------------- local data --

    def _maybe_ask_local_data(self, text, analysis):
        """Silently decides whether this request should use local data, resolving the choice
        in the background rather than interrupting with a free-text question. True if the
        request is paused pending that background work.

        Live-reported 2026-09-24/25: the same travel-time request failed twice because every
        run fetched roads and facilities live from Overpass (see agent/local_data_sources.py).
        The original fix asked "download or online?" before every single eligible request --
        live-reported again, 2026-09-28: "download / online is just used for critical actions
        not a routine task". Replaced with a silent smart default: a background probe checks
        connectivity and resolves the Geofabrik region size; if the connection is good and the
        extract isn't unusually large, the download just happens (an informational note, not a
        question -- see _start_local_download). The chat only interrupts -- via clickable chips
        (see _offer_local_data_choice), not free text -- for the two cases that actually
        warrant an active choice: an unusually large/unknown-size download, or a slow/offline
        connection. That last case matters specifically for field/humanitarian use on a poor
        connection: guessing either way risks a silent multi-second stall or wasted data, so
        the user gets an explicit choice instead of either guess.

        Only triggered when the matched task needs a road network (and the project has no line
        layer that looks like one), at most once per request, and never again this session
        after the user picks online (`_local_data_declined`)."""
        from ..agent import local_data_sources, local_data_loader
        try:
            themes = local_data_sources.should_offer(
                analysis.get("task"), text, local_data_loader.project_layer_facts(),
                declined=self._local_data_declined)
        except Exception as e:  # never let the offer check break sending a message
            log_warning("ChatTab", "local-data offer check failed: %s" % e)
            return False
        if not themes:
            return False
        # Prefer the coordinate the request itself named (live-reported, 2026-09-28: using
        # the canvas's current view centre instead named the wrong region -- a neighboring
        # country, or a meaningless "(0.000, 0.000)" -- whenever the canvas hadn't been
        # panned to the request's actual area yet). Falls back to the canvas centre for a
        # request that names no coordinate at all (e.g. "buffer 5km around active GDACS
        # alerts"). No center at all -- nothing to resolve a region for -- falls straight
        # through to online with no interruption, same as before.
        center = local_data_loader.query_point_wgs84(text) or self._canvas_center()
        if center is None:
            return False

        self._dock.receiveMessageSignal.emit("user", text)
        self._local_data_pending = {"text": text, "analysis": analysis, "themes": themes,
                                    "stage": "probing", "region": None, "center": center}
        self._set_local_data_busy(True)
        self.input_edit.clear()
        from ..services.task_runner import run_background_call
        lon, lat = center
        cache_dir = local_data_loader.data_dir()
        self._active_task = run_background_call(
            "Cartogen AI: check connection and find OSM extract",
            lambda _cancelled: local_data_loader.resolve_region_with_connectivity(lon, lat, cache_dir),
            self._on_connectivity_and_region_resolved)
        return True

    def _canvas_center(self):
        try:
            from qgis.utils import iface
            from ..agent import local_data_loader
            return local_data_loader.canvas_center_wgs84(iface.mapCanvas() if iface else None)
        except Exception:
            return None

    def _on_connectivity_and_region_resolved(self, result, error):
        """Callback for _maybe_ask_local_data's background probe. Applies the smart-default
        policy: download silently when the connection is good and the extract is a known,
        reasonable size; otherwise offer the choice as clickable chips."""
        self._set_local_data_busy(False)
        pending = self._local_data_pending
        if pending is None or self._stopped_by_user(error):
            return
        if error is not None:
            # Couldn't even run the probe -- treat it like a bad connection rather than
            # silently guessing either way.
            self._offer_local_data_choice(online_ok=False, region=None)
            return
        online_ok = (result or {}).get("online_ok", False)
        region = (result or {}).get("region")
        if not region or "error" in (region or {}):
            # No Geofabrik coverage for this location -- continue online exactly as before,
            # no interruption; the online tools' own errors, if any, surface normally.
            self._resume_local_data_request()
            return
        pending["region"] = region
        from ..agent import local_data_loader
        try:
            cached = local_data_loader.extract_is_cached(region, local_data_loader.data_dir())
        except Exception:
            cached = False
        if local_data_loader.should_ask_before_download(
                region, online_ok, cached, local_data_loader.ask_threshold_bytes(),
                metered=local_data_loader.is_metered_connection()):
            self._offer_local_data_choice(online_ok, region)
            return
        self._start_local_download(region)

    def _offer_local_data_choice(self, online_ok, region):
        """Shows the download/online choice as clickable chips, not a free-text 'reply
        download or online' prompt -- only reached for the two cases that actually warrant an
        active choice (see _maybe_ask_local_data's docstring). Typing "download"/"online" as a
        reply still works too (send_message()'s _awaiting_local_data_reply branch, unchanged),
        for anyone who prefers typing over clicking."""
        from ..agent.map_intelligence import ChatActionRegistry
        pending = self._local_data_pending
        pending["stage"] = "confirm_size"  # _on_local_data_reply's existing "ready to act" stage
        download_id = ChatActionRegistry.register(
            "local_data_choice", "Download local data", {"choice": "download"})
        online_id = ChatActionRegistry.register(
            "local_data_choice", "Continue online", {"choice": "online"})
        lines = []
        if not online_ok:
            lines.append(
                "The connection looks slow or unavailable right now. I can try to download "
                "the OpenStreetMap extract anyway (it'll keep retrying in the background), or "
                "continue online, which may also be slow or fail."
            )
        if region:
            size = region.get("size_bytes") or 0
            size_text = "%d MB" % round(size / 1e6) if size else "of unknown size"
            lines.append("The OpenStreetMap extract for **%s** is **%s**." % (region["name"], size_text))
        lines.append(
            "[\U0001F4E5 Download local data](cartogen://action/%s)  "
            "[\U0001F310 Continue online](cartogen://action/%s)" % (download_id, online_id)
        )
        self._awaiting_local_data_reply = True
        self.input_edit.setPlaceholderText("Reply download or online, or use the buttons above...")
        self._dock.receiveMessageSignal.emit("ai", "\n\n".join(lines))

    def _on_local_data_reply(self, choice):
        pending = self._local_data_pending
        if pending is None:
            return
        if choice == "online":
            self._local_data_declined = True
            self._dock.receiveMessageSignal.emit(
                "ai", "Okay, continuing with online data. I won't ask again this session.")
            self._resume_local_data_request()
            return
        self._start_local_download(pending["region"])

    def _stopped_by_user(self, error):
        """Stop pressed during the lookup or download: end the request, don't carry on online
        -- Stop means stop, not "skip this step"."""
        if not isinstance(error, InterruptedError):
            return False
        self._local_data_pending = None
        self._dock.receiveMessageSignal.emit("ai", "Stopped. Nothing was added to the project.")
        self._dock.statusSignal.emit("")
        return True

    def _start_local_download(self, region):
        from ..agent import local_data_loader
        from ..services.task_runner import run_background_call
        dest = local_data_loader.data_dir()
        self._dock.receiveMessageSignal.emit(
            "ai", "Downloading the OpenStreetMap extract for **%s** (%s) from Geofabrik. This "
                  "runs in the background; press Stop to cancel." % (
                      region["name"],
                      "%d MB" % round(region["size_bytes"] / 1e6) if region.get("size_bytes") else "size unknown"))
        self._set_local_data_busy(True)

        def work(is_cancelled):
            return local_data_loader.download_and_extract(region, dest, is_cancelled=is_cancelled)
        self._active_task = run_background_call(
            "Cartogen AI: download %s" % region["name"], work, self._on_local_download_done)

    def _on_local_download_done(self, result, error):
        self._set_local_data_busy(False)
        pending = self._local_data_pending
        if pending is None or self._stopped_by_user(error):
            return
        if error is not None:
            self._dock.receiveMessageSignal.emit(
                "ai", "The download didn't finish (%s). Continuing with online data." % error)
            self._resume_local_data_request()
            return
        from ..agent import local_data_loader
        try:
            loaded = local_data_loader.load_layers(result, pending["themes"])
        except Exception as e:
            loaded = {"layers": [], "errors": [str(e)]}
        lines = ["Added to the project from Geofabrik (OpenStreetMap, ODbL):"]
        lines += ["- **%s**: %s features%s" % (lyr["name"], format(lyr["count"], ","),
                                              " (%s)" % lyr["note"] if lyr.get("note") else "")
                  for lyr in loaded["layers"]]
        lines += ["- %s" % err for err in loaded["errors"]]
        lines.append("Saved in `%s`, so it's reused next time. Continuing with your request."
                     % os.path.dirname(result["zip_path"]))
        self._dock.receiveMessageSignal.emit("ai", "\n".join(lines))
        self._resume_local_data_request()

    def _set_local_data_busy(self, busy):
        self.send_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        if not busy:
            self._active_task = None

    def _resume_local_data_request(self):
        """Sends the original request on through the normal pipeline (preview etc.), now that
        the local-data question is settled."""
        pending, self._local_data_pending = self._local_data_pending, None
        self._awaiting_local_data_reply = False
        self.input_edit.setPlaceholderText(self._default_input_placeholder)
        if not pending:
            return
        self._resume_after_local_data = True
        self._original_already_shown = True
        self.input_edit.setPlainText(pending["text"])
        self.send_message()

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
        self._echo_original(original_text)
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
        from ..services.prompt_refiner import refine, get_user_profile

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
        if text.startswith(reply_vocab.CONTINUATION_MARKER):
            self._continuation_count = getattr(self, "_continuation_count", 0) + 1
        else:
            self._last_user_request = text
            self._continuation_count = 0
        if not already_echoed:
            self._echo_original(text)
        self._turn_sent_iso = now_iso()     # F25: stamped on the stored user message at save time
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
        from ...infrastructure.auth import CredentialManager
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

        from ..services.task_runner import run_agent_task
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
        self._turn_stopped = False
        failed_steps = []

        from ..agent import project_session
        turn_session = project_session.current()

        def on_complete(response, err):
            self._active_task = None
            self.stop_btn.setEnabled(False)
            if project_session.is_stale(turn_session):
                # #147: the project was cleared or replaced while this request ran; its reply belongs to the old project and
                # the chat has already been reloaded for the new one.
                return
            # Runs on the main GUI thread already (this function directly calls
            # receiveMessageSignal.emit below with no extra thread-marshalling), so touching
            # chat_browser here directly is safe. Flushed before the turn's own response bubble
            # so the summary block reads in chronological order: user message, tool-call
            # summary, then the answer.
            self._flush_tool_steps_summary()
            if err:
                self._advance_job_queue(False)
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
                # a tool that failed and was recovered from does not pause the queue; a Stop or a guard/budget stop does
                self._advance_job_queue(not (self._turn_stopped or str(response or "").startswith("[Agent stopped]")))
                # rc18 hand test R3 (2026-10-06): after the user pressed Stop on a run whose imagery tool had already failed, the
                # contract check asked the model for a report nobody wanted ("Do not redo the analysis ... call generate_spatial_report").
                # A deliverable is only owed for a turn that ran to its end: not one the user stopped, and not one where a tool failed
                # and the answer says so.
                if self._turn_stopped or failed_steps or str(response or "").startswith("[Agent stopped]"):
                    self._pending_contract = None
                    self._contract_followup_used = False
                else:
                    self._enforce_output_contract(sent_text)
                self._show_safety_gate_in_chat(agent)

        def on_status(msg):
            self._dock.statusSignal.emit(msg)

        def on_tool_step(name, status, error):
            # Called from the background task thread -- emit() is thread-safe;
            # Qt queues the connected slot (_add_tool_step) onto this widget's
            # own (main GUI) thread automatically, same as statusSignal/
            # receiveMessageSignal already rely on.
            if str(status).lower() == "failed":
                failed_steps.append(name)
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
        mid-batch; see agent/agent_orchestrator.py's should_stop param for both check
        sites), so it stops before the NEXT LLM call or the NEXT tool step,
        whichever comes first, rather than interrupting whichever call is
        already in flight. stop_btn stays disabled until on_complete
        actually fires so the UI doesn't claim it's stopped before it
        really has."""
        if self._active_task is None:
            return
        self._turn_stopped = True
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
        try:
            turn = agent.get_turn_usage_text() if hasattr(agent, "get_turn_usage_text") else None
        except Exception:
            turn = None
        try:     # observed, provider-reported breakdown (fresh vs cached input, output, last call) when the provider reports it
            detail = agent.get_turn_usage_detail_text() if hasattr(agent, "get_turn_usage_detail_text") else None
        except Exception:
            detail = None
        lead = detail or turn          # the observed breakdown replaces the older one-number turn text, never duplicates it
        if text and lead:
            text = f"{lead} \u00b7 {text}"
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
            save_chat_history(history, user_ts=getattr(self, "_turn_sent_iso", None))
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
        """See chat_input_controller.ChatInputController.attachment_disclosure_note."""
        return ChatInputController.attachment_disclosure_note()

    def attach_file(self):
        """See chat_input_controller.ChatInputController.attach_file."""
        self.input_controller.attach_file()

    def _read_and_analyze_file(self, agent, name, path):
        """See chat_input_controller.ChatInputController.read_and_analyze_file. Thin
        delegator, kept under its original name since test_chat_widget_live.py calls it
        directly to drive the attachment flow without a real QFileDialog."""
        self.input_controller.read_and_analyze_file(agent, name, path)

    def _analyze_file(self, agent, name, path, data):
        """See chat_input_controller.ChatInputController.analyze_file."""
        self.input_controller.analyze_file(agent, name, path, data)

    def _analyze_image(self, agent, name, data):
        """See chat_input_controller.ChatInputController.analyze_image."""
        return self.input_controller.analyze_image(agent, name, data)
