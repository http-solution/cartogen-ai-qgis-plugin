# -*- coding: utf-8 -*-
"""Consolidated data export for Cartogen AI -- GDPR review findings F7 (no
structured data export/portability) and F8 (no consolidated "what do you
know about me" view), docs/GDPR_COMPLIANCE_REVIEW.docx. Deliberately
Qt-free and qgis-free (pure Python/JSON), matching ui/chat_formatting.py's
own established pattern for logic that should stay unit-testable without a
real QGIS session -- this module only assembles and serializes data that
memory.py's/chat_persistence.py's own accessors already return; it never
reads from QgsProject/QgsSettings itself.

F7 and F8 are closed together, per the review's own recommendation, since
both touch the same three data sources (project memory, global memory,
chat history) and both are already JSON-serializable internally: F7 wants
a structured export the data subject (or the org, on their behalf) can
receive; F8 wants one consolidated view instead of three separate UI
surfaces (the memory browser panel, twice, plus the Chat tab) -- the same
assembled document serves both."""

import json
import datetime


def build_export_document(project_notes, global_notes, chat_history, chat_digest=None, chat_info=None):
    """Pure assembly -- no I/O. project_notes/global_notes are the dicts
    memory.py's get_project_notes()/get_global_notes() already return;
    chat_history is the list chat_persistence.py's
    load_chat_history_with_timestamps() already returns (empty if the user
    hasn't opted into chat history persistence -- see
    chat_persistence.is_persist_enabled(), this function doesn't decide
    that, just serializes whatever it's given). Wrapped with an export
    timestamp and a version tag so the JSON is self-describing if read back
    later without this codebase for context."""
    return {
        "export_format_version": 1,
        "exported_at": datetime.datetime.now().isoformat(),
        "project_memory": dict(project_notes or {}),
        "global_memory": dict(global_notes or {}),
        "chat_history": list(chat_history or []),
        # F25: the stored digest of older, trimmed messages, and a statement of what chat_history is
        # (a rolling window, not a transcript; empty when saving is off).
        "chat_history_digest": list(chat_digest or []),
        "chat_history_info": dict(chat_info or {}),
    }


def write_export_document(document, output_path):
    """Writes the assembled document to output_path as pretty-printed
    JSON. Returns True on success, False on any write failure -- caller
    reports the error, this doesn't raise, matching this codebase's tool
    convention of returning a result rather than propagating exceptions up
    to the UI/agent dispatch layer."""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(document, f, indent=2, ensure_ascii=False, default=str)
        return True
    except Exception:
        return False
