# -*- coding: utf-8 -*-
"""
File-attachment reading, analysis, and disclosure for Cartogen AI's chat tab.

Extracted from chat_tab_widget.py (2026-09-20, Phase 11 architecture restructuring --
docs/IMPLEMENTATION_TRACKER.md §4), the other genuinely self-contained subsystem in that
file (alongside chat_view_presenter.py's tool-step/plan rendering): reading an attached
file off disk, running it (or an attached image) through the agent's client, and folding
the result back into the chat log and session usage total. Operates on `widget` (the
ChatTabWidget instance passed to __init__) the same way chat_view_presenter.py does, for
the same reason -- widget.py owns the actual QFileDialog/thread-launch entry point
(attach_btn.clicked connects straight to this class's attach_file), and
test_chat_widget_live.py calls read_and_analyze_file/attachment_disclosure_note directly
by name (via chat_tab_widget.py's thin delegators), so those two stay reachable there.
"""

import os
import threading
import traceback

from qgis.core import QgsSettings

from .attachments import read_attached_file as _read_attached_file
from .settings_dialog import PROVIDERS as _PROVIDERS
from ...infrastructure.settings_keys import SETTINGS_PROVIDER


class ChatInputController:
    def __init__(self, widget):
        self.widget = widget

    @staticmethod
    def attachment_disclosure_note():
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
        from qgis.PyQt.QtWidgets import QFileDialog

        w = self.widget
        filters = (
            "Supported files (*.pdf *.docx *.png *.jpg *.jpeg *.csv *.xlsx);;"
            "PDF (*.pdf);;Word (*.docx);;Images (*.png *.jpg *.jpeg);;"
            "CSV (*.csv);;Excel (*.xlsx);;All files (*)"
        )
        path, _ = QFileDialog.getOpenFileName(w, "Attach file", "", filters)
        if not path:
            return

        name = os.path.basename(path)
        disclosure = self.attachment_disclosure_note()
        w._dock.receiveMessageSignal.emit(
            "ai", f"📎 **Attaching:** {name}\n\n_{disclosure}_\n\nReading...")
        w._dock.statusSignal.emit("Reading file...")

        agent = None
        if w._agent_provider:
            agent = w._agent_provider()

        thread = threading.Thread(
            target=self.read_and_analyze_file, args=(agent, name, path), daemon=True
        )
        thread.start()

    def read_and_analyze_file(self, agent, name, path):
        """PERF-005, 2026-09-13 audit: read_attached_file (pypdf/docx/pandas parsing) used
        to run synchronously on the Qt main thread inside attach_file(), before the
        background analysis thread below was even started -- a large PDF/DOCX/table-heavy
        file could freeze the whole GUI while it parsed. read_attached_file has zero Qt/QGIS
        dependency (see its own docstring), so it's safe to run here instead, on the same
        background thread that was already doing the LLM analysis."""
        w = self.widget
        data, err = _read_attached_file(path)
        if err is not None:
            w._dock.receiveMessageSignal.emit("ai", f"Error reading {name}: {err}")
            return

        # Remembered for the next chat message so the file becomes part of the
        # task, not just a one-off analysis -- see analyze_request(attachments=).
        if path not in w._attached_paths:
            w._attached_paths.append(path)

        from ..agent import file_io
        kind = file_io.classify(path)
        carried = (" It will also be used with your next message as a %s input."
                   % kind) if kind else ""
        w._dock.receiveMessageSignal.emit(
            "ai", f"📎 **File attached:** {name}{carried}\n\nAnalyzing...")
        w._dock.statusSignal.emit("Analyzing...")

        self.analyze_file(agent, name, path, data)

    def analyze_file(self, agent, name, path, data):
        w = self.widget
        try:
            from ...infrastructure.auth import CredentialManager
            no_agent_msg = "**Agent could not be initialized.** Check the QGIS Python console for details."
            block_msg = no_agent_msg if agent is None else \
                CredentialManager.missing_credential_message(client=getattr(agent, "client", None))
            if block_msg:
                w._dock.receiveMessageSignal.emit("ai", block_msg)
                return

            client = getattr(agent, "client", None)
            if client is not None and hasattr(client, "set_status_callback"):
                client.set_status_callback(lambda msg: w._dock.statusSignal.emit(msg))

            if data.get("is_image"):
                response = self.analyze_image(agent, name, data)
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

            w._dock.receiveMessageSignal.emit("ai", response if response else "_(empty response)_")
        except Exception as e:
            traceback.print_exc()
            w._dock.receiveMessageSignal.emit("ai", f"**Error analyzing file:** {e}")
        finally:
            w._dock.statusSignal.emit("")
            # Covers both branches above: the non-image path's agent.run(prompt)
            # already accumulated usage internally, and analyze_image's direct
            # client.complete() call accumulates it itself (see that method) --
            # this is just the one place that refreshes what the label shows
            # after either one, same as _after_successful_response does for the
            # main chat send path.
            w._refresh_usage_label(agent)

    def analyze_image(self, agent, name, data):
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
        # Reads via the same lock-protected snapshot run() itself uses (see
        # agent_orchestrator.py's HistoryManager) when the real agent provides it -- this
        # vision-analysis call runs on the main Qt thread while a normal chat turn could be
        # mid-flight on the background QgsTask thread, appending to this same list
        # concurrently. Falls back to the raw attribute for a test double that doesn't
        # implement the method.
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
