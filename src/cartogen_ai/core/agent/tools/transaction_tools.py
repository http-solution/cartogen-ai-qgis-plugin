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
from ._snapshot_registry import get_restore_fn

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
    "Reverse the most recent undoable tool call made THIS turn (see get_turn_transaction_log to "
    "check what qualifies first). Covers: a call that added a new layer (removes it); "
    "remove_layer (restores the removed layer and its data); field_calculator/calculate_area/"
    "calculate_length (restores the field's prior values, or deletes it if it didn't exist "
    "before); apply_categorized_style/apply_graduated_style/apply_graduated_symbol_style "
    "(restores the prior style); set_dataset_status/set_layer_sensitivity/set_layer_confidence/"
    "run_query (restores the prior value). It cannot undo load_project or any other in-place "
    "edit not in that list -- a real, separate, still-open gap, not something this tool silently "
    "skips without saying so. Destructive action requiring UI confirmation.",
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

    undo = entry["undo"]
    kind = undo.get("kind")

    if kind == "remove_layers":
        return _undo_remove_layers(entry, undo, confirmed)
    return _undo_via_snapshot(entry, undo, confirmed)


def _undo_remove_layers(entry, undo, confirmed):
    layer_ids = undo["layer_ids"]
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


def _undo_via_snapshot(entry, undo, confirmed):
    """v1.7.0: the priority-subset MODIFY/DELETE undo kinds
    (_snapshot_registry.py -- restore_layer/restore_field/restore_style/
    restore_property), all sharing this same preview/confirm/restore
    shape, unlike remove_layers' layer-id-list-specific one above."""
    kind = undo.get("kind", "change")
    label = kind.replace("restore_", "") if kind else "change"
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "undo_last_operation",
            "arguments": {"confirmed": True},
            "rationale": f"Undo '{entry['name']}': reverse its {label} from this turn.",
            "message": f"Confirmation required before undoing '{entry['name']}'.",
        }

    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    restore_fn = get_restore_fn(kind, undo.get("tool_name"))
    if restore_fn is None:
        return {"error": f"No restore mechanism available for '{entry['name']}'."}

    if not restore_fn(undo):
        return {"error": f"Failed to undo '{entry['name']}' -- the layer or field may no longer exist."}

    _TRANSACTION_LOG.mark_undone(entry["index"])
    return {
        "success": True,
        "undone_tool": entry["name"],
        "message": f"Undid '{entry['name']}'.",
    }
