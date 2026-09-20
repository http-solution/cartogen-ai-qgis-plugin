# -*- coding: utf-8 -*-
"""
In-chat tool-step and plan-progress rendering for Cartogen AI's chat tab.

Extracted from chat_tab_widget.py (2026-09-20, Phase 11 architecture restructuring --
docs/IMPLEMENTATION_TRACKER.md §4), the one genuinely self-contained rendering subsystem
in that file: collecting a turn's tool-call outcomes into one compact summary block, and
keeping the in-chat plan/progress card's animated spinner and content in sync as the
active task_manager plan changes. Operates entirely on `widget` (the ChatTabWidget
instance passed to __init__) rather than owning its own state -- chat_tab_widget.py's own
__init__ still owns _current_turn_steps/_step_blocks/_step_block_counter/_plan_block/
_plan_spinner_timer, since test_chat_widget_live.py's live Qt tests read several of these
directly off the widget (e.g. `ct._plan_block`) and chat_tab_widget.py's own message-
rendering methods (_add_message, _scroll_to_bottom) need to stay reachable from here too.
This is a real, scoped split (tool-step/plan rendering out of the widget), not a full
view/controller bisection of the whole file -- see chat_tab_widget.py's own module
docstring for why the rest of that file stays composed rather than being forced apart.

Every method kept its old name (minus the leading underscore) so chat_tab_widget.py's
thin delegators (_add_tool_step -> add_tool_step, etc.) read as an obvious 1:1 mapping.
"""

from qgis.PyQt.QtGui import QTextCursor

from .chat_formatting import (
    render_tool_steps_toggle_html, render_tool_steps_failure_details_html,
    render_task_progress_html, friendly_tool_name, PLAN_SPINNER_FRAMES,
)
from .theme import theme_colors


class ChatViewPresenter:
    def __init__(self, widget):
        self.widget = widget

    def add_tool_step(self, name, status, error):
        """Live per-tool-call progress signal, fired twice per tool call (once starting, once
        finishing) -- see agent_orchestrator.py's run() tool_step_callback. "running" is
        transient, live-progress-only -- it updates status_label in place (the same label
        already used for "Thinking...") instead of adding a permanent scrollback line.
        Terminal statuses ("done"/"failed") are collected into widget._current_turn_steps
        instead of rendered immediately; flush_tool_steps_summary() (called once, from
        _dispatch_message's on_complete when the whole turn finishes) turns the collected
        list into ONE compact summary block."""
        w = self.widget
        status_lower = (status or "").lower()
        if status_lower == "running":
            w.status_label.setText(f"⚙️ {friendly_tool_name(name)}…")
            return
        # Also the record agent/output_router.py checks the output contract
        # against. Only completed steps count -- a tool that started and failed
        # did not produce the deliverable.
        if name and status_lower in ("done", "ok", "finished", "completed", "success"):
            w._executed_tools.append(name)
        w._current_turn_steps.append({
            "name": name,
            "status": "failed" if status_lower == "failed" else "done",
            "error": error or None,
        })

    def flush_tool_steps_summary(self):
        """Renders widget._current_turn_steps (accumulated by add_tool_step above) as one
        compact summary block, then clears the list. Called once per turn, from
        _dispatch_message's on_complete() -- which already runs on the main GUI thread, so
        this is safe to call directly without another signal hop. A no-op when no tools ran
        this turn (a plain conversational reply with no tool calls) -- nothing is appended
        at all."""
        w = self.widget
        steps = w._current_turn_steps
        w._current_turn_steps = []
        if not steps:
            return
        colors = theme_colors()
        w._step_block_counter += 1
        block_id = w._step_block_counter

        cursor = QTextCursor(w.chat_browser.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()  # a fresh paragraph, matching .append()'s own behavior elsewhere
        start_pos = cursor.position()
        cursor.insertHtml(render_tool_steps_toggle_html(steps, block_id, colors, expanded=False))
        end_pos = cursor.position()
        w._step_blocks[block_id] = {
            "steps": steps, "expanded": False, "start": start_pos, "end": end_pos,
        }

        failure_html = render_tool_steps_failure_details_html(steps, colors)
        if failure_html:
            # Outside the tracked start/end span on purpose -- always visible, never part of
            # what the toggle above collapses/expands (see render_tool_steps_failure_details_
            # html's docstring: failures are load-bearing, not opt-in detail).
            w.chat_browser.append(failure_html)

        w._scroll_to_bottom()

    def on_live_plan_updated(self, plan_data):
        """Renders/updates the in-chat plan-progress card -- connected to task_manager's
        plan_updated signal in _dispatch_message. A plan with no title and no tasks means
        "nothing active right now": the timer stops but any existing card is left untouched
        in scrollback (it's a real record of a past plan, not a placeholder to blank out). A
        DIFFERENT title than the currently-tracked card means a new plan started -- appends
        a fresh block rather than overwriting the old one, so plan history is just "scroll
        up" (see chat_tab_widget.py's module docstring)."""
        w = self.widget
        title = plan_data.get("title", "")
        tasks = plan_data.get("tasks", [])
        colors = theme_colors()

        if not title and not tasks:
            w._plan_spinner_timer.stop()
            return

        is_new_plan = w._plan_block is None or w._plan_block["title"] != title
        spinner_frame = 0 if is_new_plan else w._plan_block["spinner_frame"]
        html = render_task_progress_html(plan_data, colors, spinner_frame=spinner_frame)

        if is_new_plan:
            cursor = QTextCursor(w.chat_browser.document())
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertBlock()
            start_pos = cursor.position()
            cursor.insertHtml(html)
            end_pos = cursor.position()
            w._plan_block = {
                "title": title, "start": start_pos, "end": end_pos,
                "spinner_frame": spinner_frame, "plan_data": plan_data,
            }
            # Same force-scroll fix as flush_tool_steps_summary above, for the same reason
            # (a fresh QTextCursor insert bypasses append()'s own scroll heuristic) -- only
            # for a genuinely NEW card, not every in-place update below: forcing this on
            # every tick_plan_spinner tick (every 400ms while a task runs) would yank the
            # view back to the bottom several times a second, making scrollback unreadable
            # during a long-running turn.
            w._scroll_to_bottom()
        else:
            w._plan_block["plan_data"] = plan_data
            self.replace_tracked_block(w._plan_block, html)

        has_running = any(t.get("status") == "IN_PROGRESS" for t in tasks)
        if has_running and not w._plan_spinner_timer.isActive():
            w._plan_spinner_timer.start()
        elif not has_running:
            w._plan_spinner_timer.stop()

    def tick_plan_spinner(self):
        """Advances the current plan card's spinner glyph one frame -- the only animation
        this in-chat card has, deliberately quiet (a single cycling braille dot, not a
        moving progress bar or bouncing icon) per the direct instruction that replaced
        plan_strip_widget.py's docked-panel-with-animation with this in-chat design."""
        w = self.widget
        if w._plan_block is None:
            w._plan_spinner_timer.stop()
            return
        w._plan_block["spinner_frame"] = (w._plan_block["spinner_frame"] + 1) % len(PLAN_SPINNER_FRAMES)
        colors = theme_colors()
        html = render_task_progress_html(
            w._plan_block["plan_data"], colors, spinner_frame=w._plan_block["spinner_frame"],
        )
        self.replace_tracked_block(w._plan_block, html)

    def replace_tracked_block(self, block, new_html):
        """Shared in-place-edit primitive for any tracked chat_browser span (currently the
        plan card and the tool-steps toggle in chat_tab_widget.py's _on_step_anchor_clicked):
        replaces the HTML between block['start']/['end'], then shifts every OTHER tracked
        block (both widget._step_blocks and, if it isn't the one being edited,
        widget._plan_block) whose span starts after the edited one's old end -- the
        collapsed/expanded or spinner-frame HTML rarely renders to the same character count,
        so every later block's stored position would silently go stale without this."""
        w = self.widget
        old_end = block["end"]
        cursor = QTextCursor(w.chat_browser.document())
        cursor.setPosition(block["start"])
        cursor.setPosition(old_end, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertHtml(new_html)
        new_end = cursor.position()
        block["end"] = new_end

        delta = new_end - old_end
        if not delta:
            return
        for other_block in w._step_blocks.values():
            if other_block is not block and other_block["start"] > old_end:
                other_block["start"] += delta
                other_block["end"] += delta
        if w._plan_block is not None and w._plan_block is not block and w._plan_block["start"] > old_end:
            w._plan_block["start"] += delta
            w._plan_block["end"] += delta

    def clear_plan(self):
        w = self.widget
        if not w._agent_provider:
            return
        agent = w._agent_provider()
        if not (agent and hasattr(agent, "task_manager")) or not agent.task_manager.tasks:
            return
        from qgis.PyQt.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            w, "Clear Plan", "Archive the current plan and reset the tracker?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            agent.task_manager.clear_plan()
