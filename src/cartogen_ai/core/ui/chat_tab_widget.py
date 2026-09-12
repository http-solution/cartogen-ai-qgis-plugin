# -*- coding: utf-8 -*-
"""Chat tab, extracted from dock_widget.py's CartogenAiDockWidget
(docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md). Owns the chat log, input row,
quick-suggestion chips, prompt-refinement panel, and file-attachment analysis.

Signals (receiveMessageSignal/statusSignal/usageSignal/toolStepSignal/
refinementFetchedSignal) stay defined on the parent CartogenAiDockWidget, not here
-- per the split plan's recommendation, since statusSignal/usageSignal are also
emitted from Tasks-tab and dock-header code (_copy_code_snippet, open_settings).
This widget reaches them via self._dock, the same pattern used for
self._dock.tasks_tab_widget below."""

import threading
import traceback
import os

from qgis.PyQt.QtCore import Qt, pyqtSignal, QSize
from qgis.PyQt.QtGui import QTextCursor
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QTextBrowser,
    QPushButton, QTextEdit, QGroupBox,
)

from .chat_formatting import (
    render_markdown, _relative_time, now_iso, escape_plain_text, render_tool_step_html,
    render_tool_steps_toggle_html, render_tool_steps_failure_details_html, friendly_tool_name,
    format_send_error,
)
from .attachments import read_attached_file as _read_attached_file
from .theme import theme_colors, extract_theme_palette
from .icons import themed_icon


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
        self._pending_refinement_text = None  # original text while the refinement panel is shown
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
        # Files the user attached since the last send. attach_file() still
        # analyses each one immediately (unchanged); this list is what lets the
        # NEXT message know those files exist, so a sitrep PDF or a damage
        # photo becomes part of the task rather than a separate side errand.
        self._attached_paths = []
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
        self._pending_contract = None
        self._contract_followup_used = False

        from ..agent.deps import get_dependency_warning_message
        self._dep_warning = get_dependency_warning_message()

        self.init_ui()

    @property
    def _agent_provider(self):
        return self._dock._agent_provider

    def init_ui(self):
        chat_layout = QVBoxLayout(self)
        chat_layout.setContentsMargins(4, 4, 4, 4)

        self.chat_browser = QTextBrowser()
        self.chat_browser.setOpenExternalLinks(True)
        # openLinks=False so a real (internal-looking) anchor doesn't trigger QTextBrowser's own
        # page-navigation via setSource() -- independent of openExternalLinks above, which still
        # opens genuine http(s) links from markdown responses via QDesktopServices exactly as
        # before. anchorClicked fires either way; this just intercepts the one internal scheme
        # (cartogen://) this codebase's first-ever clickable in-chat control uses (the tool-steps
        # Details toggle, added 2026-09-12 -- see _flush_tool_steps_summary/render_tool_steps_
        # toggle_html) without letting Qt try to "navigate" to it as if it were a real page.
        self.chat_browser.setOpenLinks(False)
        self.chat_browser.anchorClicked.connect(self._on_step_anchor_clicked)
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

        # Prompt Refinement panel -- separate widget above the input row
        # (docs/archive/PROMPT_REFINEMENT_LAYER_SPEC.md §6/§11.1: decided as a
        # separate panel rather than inline chat bubbles, so these cards
        # never touch conversation_history or chat_persistence.py at all --
        # they're not chat messages). Hidden by default; shown only once
        # send_message() decides a message should be refined and a valid
        # response comes back. Modeled on the confirm_btn/PREVIEW_READY
        # gate's explicit-button, nothing-auto-proceeds interaction language.
        self.refinement_panel = QGroupBox("Suggested rewordings")
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
            edit_btn = QPushButton("Edit request")
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

        # Prompt preview. The user asked to be shown the prompt that will be
        # sent, as reasoning, before it is sent -- so this shows the literal
        # text (agent/prompt_refiner.compose_optimum_prompt returns both halves
        # verbatim), not a paraphrase of it. Nothing is sent while this panel
        # is open.
        self.preview_panel = QGroupBox("Prompt that will be sent")
        self.preview_panel.setVisible(False)
        preview_layout = QVBoxLayout(self.preview_panel)
        self.preview_reasoning = QLabel()
        self.preview_reasoning.setWordWrap(True)
        self.preview_reasoning.setTextFormat(Qt.TextFormat.RichText)
        preview_layout.addWidget(self.preview_reasoning)
        self.preview_prompt = QTextEdit()
        self.preview_prompt.setReadOnly(True)
        self.preview_prompt.setFixedHeight(120)
        preview_layout.addWidget(self.preview_prompt)
        preview_buttons = QHBoxLayout()
        self.preview_send_btn = QPushButton("Send this")
        # Deliberately the default (accent) button style, not "successButton" --
        # that green is reserved for the Activity tab's destructive-action confirm
        # gate ("Confirm and Apply Edit"). Reusing it here made the same color mean
        # both "send a low-stakes composed prompt" and "apply an edit/delete",
        # collapsing a meaning-carrying color -- found in the UX audit dated
        # 2026-08-31.
        self.preview_send_btn.clicked.connect(self._send_previewed_prompt)
        # "Send as typed instead" matches the Refinement panel's identical bypass-send button
        # exactly (:161) -- was "Send my wording only" here, a second phrasing of the same
        # action across the two gate panels. UI/chat redesign workstream, 2026-09-12.
        self.preview_original_btn = QPushButton("Send as typed instead")
        self.preview_original_btn.clicked.connect(self._send_preview_original)
        self.preview_cancel_btn = QPushButton("Cancel")
        self.preview_cancel_btn.clicked.connect(self._cancel_preview)
        preview_buttons.addWidget(self.preview_send_btn)
        preview_buttons.addWidget(self.preview_original_btn)
        preview_buttons.addWidget(self.preview_cancel_btn)
        preview_layout.addLayout(preview_buttons)
        chat_layout.addWidget(self.preview_panel)

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

        input_layout.addWidget(self.attach_btn)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(self.send_btn)
        input_layout.addWidget(self.stop_btn)
        chat_layout.addLayout(input_layout)

        self._populate_initial_chat()

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
            except Exception:
                pass

        if restored:
            self._dock.receiveMessageSignal.emit("ai", "_(Restored previous conversation for this project.)_")
        else:
            self._dock.receiveMessageSignal.emit(
                "ai",
                "Hello! I'm Cartogen AI 🗺️\n\n"
                "I plan multi-step spatial tasks, call the right tools, and execute real operations "
                "against your open project -- with spatial memory and every step inspectable.\n\n"
                "Ask me to analyze, buffer, style, or process your layers!"
            )

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
        self._populate_initial_chat()

    def _add_message(self, role, text):
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
            body = render_markdown(text, colors)
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
        self.input_edit.clear()
        self.send_btn.setEnabled(True)
        self.status_label.setText("")

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

    def _on_step_anchor_clicked(self, url):
        """Handles clicks on the Details/Hide-details toggle anchor a tool-steps summary block
        renders (render_tool_steps_toggle_html) -- the first internal (non-http) clickable
        control this chat log has ever had. Ignores anything that isn't our own "cartogen://
        steps/{block_id}" scheme, so real markdown links in AI responses (opened via
        setOpenExternalLinks(True), untouched by this handler) are unaffected."""
        if url.scheme() != "cartogen":
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

        old_end = block["end"]
        cursor = QTextCursor(self.chat_browser.document())
        cursor.setPosition(block["start"])
        cursor.setPosition(old_end, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertHtml(new_html)
        new_end = cursor.position()
        block["end"] = new_end

        # The collapsed and expanded HTML render to a different number of characters, so
        # editing THIS block shifts every character position after it -- including any later
        # turn's own step block(s) and their stored start/end, which are plain ints, not live
        # QTextCursor objects Qt would auto-adjust on its own. Shift them by the same delta so a
        # later toggle click still targets the right span instead of a now-stale one.
        delta = new_end - old_end
        if delta:
            for other_id, other_block in self._step_blocks.items():
                if other_id != block_id and other_block["start"] > old_end:
                    other_block["start"] += delta
                    other_block["end"] += delta

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

        # A fresh send attempt abandons any still-open refinement panel from
        # a previous message -- the practical equivalent of spec §7's "user
        # closes the card without choosing" (this UI has no separate close/X
        # affordance; typing something else and hitting Send again is how a
        # user actually walks away from it). Without this, a stale panel and
        # its _pending_refinement_text would linger orphaned.
        if self.refinement_panel.isVisible():
            self._hide_refinement_panel()
        if self.preview_panel.isVisible():
            self._cancel_preview()

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
            self._show_preview_panel(text, analysis)
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
        the same way, rather than needing a different mechanism)."""
        self._pending_analysis_text = original_text
        self._pending_analysis = analysis
        self._awaiting_requirement_reply = True
        self.input_edit.clear()
        self.input_edit.setPlaceholderText("Type your answer... (Enter to send)")
        self.input_edit.setFocus()
        question = analysis.get("question") or "Could you tell me a bit more about what you need?"
        self._dock.receiveMessageSignal.emit("ai", question)

    # ------------------------------------------------------ prompt preview --

    def _show_preview_panel(self, original_text, analysis):
        """Shows the exact prompt and the reasoning behind it, then waits."""
        self._pending_analysis_text = original_text
        self._pending_analysis = analysis
        from ..agent import output_router

        lines = list(analysis.get("reasoning") or [])
        contract_line = output_router.describe_contract(analysis.get("contract"))
        if contract_line:
            lines.append(contract_line)
        self.preview_reasoning.setText(
            "<b>Why this prompt</b><ul>"
            + "".join("<li>%s</li>" % escape_plain_text(l) for l in lines)
            + "</ul>"
        )
        self.preview_prompt.setPlainText(analysis.get("optimum_prompt") or original_text)
        # Read-only while this panel is up: Send this / Send as typed instead
        # both act on the original_text snapshot captured above, not on
        # whatever is in the box right now. Without this, editing the box
        # underneath the open panel and clicking either button silently sent
        # the pre-edit text -- found in the UX audit dated 2026-08-31.
        self.input_edit.setReadOnly(True)
        self.preview_panel.setVisible(True)

    def _hide_preview_panel(self):
        self.preview_panel.setVisible(False)
        self.input_edit.setReadOnly(False)

    def _send_previewed_prompt(self):
        text = self._pending_analysis_text
        analysis = self._pending_analysis
        self._hide_preview_panel()
        if text:
            self._dispatch_message(text, analysis)

    def _send_preview_original(self):
        """Sends the user's own wording with no register enrichment at all --
        the escape hatch for when the matched task is simply wrong."""
        text = self._pending_analysis_text
        self._hide_preview_panel()
        if text:
            self._dispatch_message(text, None)

    def _cancel_preview(self):
        self._hide_preview_panel()
        text = self._pending_analysis_text
        self._pending_analysis = None
        self._pending_analysis_text = None
        if text:
            self.input_edit.setPlainText(text)
            self.input_edit.setFocus()

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
        self.input_edit.setReadOnly(True)
        self.refinement_panel.setVisible(True)

    def _hide_refinement_panel(self):
        self.refinement_panel.setVisible(False)
        self._pending_refinement_text = None
        self.input_edit.setReadOnly(False)

    def _use_refinement_card(self, card_id):
        card = self._refinement_cards.get(card_id)
        chosen_text = card["prompt"].text() if card else ""
        self._hide_refinement_panel()
        if chosen_text:
            self._dispatch_message(chosen_text, self._pending_analysis)

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
            self._dispatch_message(original_text, self._pending_analysis)

    def _dispatch_message(self, text, analysis=None):
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

        # Sending a new message means "back to work" -- hands off to the Tasks tab to
        # snap out of history-browsing mode and refresh the live plan/memory panels
        # while this request runs (docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md: this used
        # to be inline here since both tabs were one class; now Tasks owns its own state).
        self._dock.tasks_tab_widget.sync_with_agent(agent)

        from ..agent.task_runner import run_agent_task
        from ..agent.map_context import get_map_context_summary

        # Gathered here, on the main thread, before the background QgsTask
        # starts -- QgsProject/layers aren't thread-safe to touch from run().
        map_ctx = get_map_context_summary()
        # analysis=None is meaningful, not "not supplied" -- it is exactly
        # what _send_preview_original() passes to mean "skip the register's
        # enrichment entirely" (the escape hatch for when the matched task is
        # simply wrong). Every call site above passes its own analysis (or
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

        instruction = output_router.followup_instruction(
            contract, executed, already_retried=self._contract_followup_used)
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
            print(f"[ChatTabWidget] Failed to cancel task: {e}")
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
            save_chat_history(getattr(agent, "conversation_history", []))
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

        agent = None
        if self._agent_provider:
            agent = self._agent_provider()

        thread = threading.Thread(
            target=self._analyze_file, args=(agent, name, path, data), daemon=True
        )
        thread.start()

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
