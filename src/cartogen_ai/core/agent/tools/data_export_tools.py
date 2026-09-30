# -*- coding: utf-8 -*-
"""
Registered tool surface for agent/data_export.py -- GDPR review findings
F7/F8 (docs/GDPR_COMPLIANCE_REVIEW.docx). See that module's own docstring
for the full design.
"""

from .registry import register_tool
from .task_tools import get_memory_manager
from .. import data_export as _export
from .. import chat_persistence as _chat_persistence


def _max_history_messages():
    try:
        from ..agent_orchestrator import MAX_HISTORY_MESSAGES
        return MAX_HISTORY_MESSAGES
    except Exception:
        return None


@register_tool(
    "export_stored_data",
    "Exports everything Cartogen AI has stored for this project and this machine -- project "
    "memory notes, global memory notes/preferences, and chat history (if chat history saving is "
    "enabled in Settings) -- into one structured JSON file. Use this when the user asks what data "
    "the plugin has stored, wants a copy of their conversation/notes, or needs a data-portability "
    "export. Chat history is included only if the user has opted into 'Save chat history in the "
    "project file' -- this tool does not change that setting or read history that was never saved. "
    "The chat history it exports is only a rolling window of the most recent messages plus a short digest of "
    "older ones (see chat_history_info in the file), never a full transcript; say so when reporting it.",
    {
        "type": "object",
        "properties": {
            "output_path": {
                "type": "string",
                "description": "Full file path to write the JSON export to, e.g. 'C:/Users/me/Desktop/cartogen_data_export.json'.",
            },
        },
        "required": ["output_path"],
    },
)
def export_stored_data(output_path):
    memory_manager = get_memory_manager()
    if memory_manager is None:
        return {"error": "Memory manager not initialized."}

    try:
        project_notes = memory_manager.get_project_notes()
        global_notes = memory_manager.get_global_notes()
    except Exception as e:
        return {"error": f"Failed to read stored memory: {e}"}

    try:
        chat_history = _chat_persistence.load_chat_history_with_timestamps()
    except Exception:
        chat_history = []

    try:
        chat_digest = _chat_persistence.load_chat_digest()
        chat_info = _chat_persistence.describe_retention(_max_history_messages())
    except Exception:
        chat_digest, chat_info = [], {}

    document = _export.build_export_document(
        project_notes, global_notes, chat_history, chat_digest=chat_digest, chat_info=chat_info)
    if not _export.write_export_document(document, output_path):
        return {"error": f"Failed to write export file to '{output_path}'."}

    return {
        "success": True,
        "output_path": output_path,
        "project_memory_count": len(document["project_memory"]),
        "global_memory_count": len(document["global_memory"]),
        "chat_history_count": len(document["chat_history"]),
        "chat_history_note": (document.get("chat_history_info") or {}).get("note"),
    }
