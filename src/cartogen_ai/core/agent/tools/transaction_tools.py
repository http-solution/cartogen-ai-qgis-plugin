# -*- coding: utf-8 -*-
"""
Agent-facing view onto agent/transactions.py's TurnTransactionLog -- see
that module's docstring for exactly what is and isn't tracked/undoable.
Follows the same module-level bind pattern task_tools.py already uses for
TaskManager/MemoryManager (bind_agent_context): agent.py calls
bind_transaction_log() once per CartogenAi instance so these free
functions can reach the live, per-turn log without every tool call having
to thread an agent reference through TOOL_REGISTRY's plain
name-to-function dispatch.
"""

from .registry import register_tool

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_TRANSACTION_LOG = None


def bind_transaction_log(transaction_log):
    """Binds the active CartogenAi instance's TurnTransactionLog to the tool
    handlers below."""
    global _TRANSACTION_LOG
    _TRANSACTION_LOG = transaction_log


@register_tool(
    "get_turn_transaction_log",
    "List every tool call made so far during THIS turn (this one user request), each tagged "
    "with its operation type and, when it added a new layer, whether it can be undone with "
    "undo_last_operation. Use this before undo_last_operation to see what's actually available "
    "to undo -- it does not reach back into earlier turns/messages, only the current one.",
    {"type": "object", "properties": {}, "required": []},
)
def get_turn_transaction_log():
    if _TRANSACTION_LOG is None:
        return {"error": "Transaction log not initialized."}
    entries = _TRANSACTION_LOG.summary()
    return {
        "entries": entries,
        "undo_available": any(e.get("undo") and not e.get("undone") for e in entries),
    }


@register_tool(
    "undo_last_operation",
    "Reverse the most recent undoable tool call made THIS turn -- currently, this only ever "
    "means removing a layer that a call added (see get_turn_transaction_log to check what "
    "qualifies first). It cannot undo an in-place edit (e.g. field_calculator, a style change, "
    "run_query's filter) or a previous removal/project load -- those are a real, separate, "
    "still-open gap, not something this tool silently skips without saying so. "
    "Destructive action requiring UI confirmation.",
    {
        "type": "object",
        "properties": {
            "confirmed": {"type": "boolean", "description": "Set true only after the user has confirmed the undo."},
        },
        "required": [],
    },
)
def undo_last_operation(confirmed: bool = False):
    if _TRANSACTION_LOG is None:
        return {"error": "Transaction log not initialized."}

    entry = _TRANSACTION_LOG.last_undoable()
    if entry is None:
        return {
            "success": False,
            "message": "Nothing undoable in this turn -- either nothing has been done yet, "
                       "everything undoable already was, or the only calls made were "
                       "reads/in-place edits this mechanism can't reverse (see "
                       "get_turn_transaction_log).",
        }

    layer_ids = entry["undo"]["layer_ids"]
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "undo_last_operation",
            "arguments": {"confirmed": True},
            "code_snippet": "\n".join(f"QgsProject.instance().removeMapLayer('{lid}')" for lid in layer_ids),
            "rationale": f"Undo '{entry['name']}': remove {len(layer_ids)} layer(s) it added this turn.",
            "message": f"Confirmation required before undoing '{entry['name']}' "
                       f"(removes {len(layer_ids)} layer(s) it created).",
        }

    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    project = QgsProject.instance()
    removed, missing = [], []
    for lid in layer_ids:
        if project.mapLayer(lid) is not None:
            project.removeMapLayer(lid)
            removed.append(lid)
        else:
            missing.append(lid)

    _TRANSACTION_LOG.mark_undone(entry["index"])
    result = {
        "success": True,
        "undone_tool": entry["name"],
        "removed_layer_ids": removed,
        "message": f"Undid '{entry['name']}': removed {len(removed)} layer(s) it added.",
    }
    if missing:
        result["warning"] = (
            f"{len(missing)} layer(s) it added were already gone from the project "
            "(removed some other way since) -- nothing to undo for those."
        )
    return result
