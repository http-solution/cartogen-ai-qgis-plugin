# -*- coding: utf-8 -*-
"""Sensitivity/disclosure classification for Cartogen AI layers -- point 24
of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.

Deliberately advisory, not enforcing: this tags a layer with a sensitivity
level (PUBLIC/INTERNAL/RESTRICTED/SENSITIVE) and lets export_layer/
export_to_csv (agent/tools/export_tools.py) add a warning when exporting a
RESTRICTED/SENSITIVE layer -- but never blocks the export. Matching this
project's own established restraint on advisory-vs-blocking checks (point 3's
CRS warning, point 22's zero-result warning): a hard export-blocking gate is
a real product decision (what happens when a legitimate, authorized export
of sensitive data is needed -- an override flow, a different confirmation
UI, who can lift it) this module doesn't decide unilaterally. No automated
classification exists either -- a layer is only ever as sensitive as
whoever calls set_layer_sensitivity says it is; there's no heuristic here
guessing from field names or content.

Same durable-storage pattern as dataset_status.py/lineage.py: a JSON blob
in a layer custom property, survives project save/reload for free."""

import json

SENSITIVITY_PROPERTY_KEY = "cartogen_ai/sensitivity"
SENSITIVITY_LEVELS = ["PUBLIC", "INTERNAL", "RESTRICTED", "SENSITIVE"]

# Only these two levels trigger an export-time advisory warning -- PUBLIC/
# INTERNAL are the common case and shouldn't add friction to routine exports.
_LEVELS_REQUIRING_EXPORT_WARNING = {"RESTRICTED", "SENSITIVE"}


def _default_record() -> dict:
    return {"level": None, "reason": None}


def get_layer_sensitivity(layer) -> dict:
    """Reads a layer's current sensitivity record: {"level": <one of
    SENSITIVITY_LEVELS, or None>, "reason": <str or None>}. A layer that
    was never tagged returns level=None -- distinct from PUBLIC, which is
    an explicit classification, not a default guessed on the caller's
    behalf."""
    if layer is None:
        return _default_record()
    try:
        raw = layer.customProperty(SENSITIVITY_PROPERTY_KEY, "")
    except Exception:
        return _default_record()
    if not isinstance(raw, str) or not raw.strip():
        return _default_record()
    try:
        record = json.loads(raw)
    except Exception:
        return _default_record()
    if not isinstance(record, dict) or record.get("level") not in SENSITIVITY_LEVELS:
        return _default_record()
    record.setdefault("reason", None)
    return record


def set_layer_sensitivity(layer, level, reason=None) -> bool:
    if layer is None or level not in SENSITIVITY_LEVELS:
        return False
    try:
        layer.setCustomProperty(SENSITIVITY_PROPERTY_KEY, json.dumps({"level": level, "reason": reason}))
        return True
    except Exception:
        return False


def export_warning_for(layer) -> str:
    """Returns an advisory warning string if the layer is tagged RESTRICTED
    or SENSITIVE, else "" (falsy, safe to use directly in an `if`). Never
    blocks the export this is called from -- see module docstring."""
    record = get_layer_sensitivity(layer)
    level = record.get("level")
    if level not in _LEVELS_REQUIRING_EXPORT_WARNING:
        return ""
    reason = record.get("reason")
    suffix = f" ({reason})" if reason else ""
    return (
        f"This layer is tagged '{level}'{suffix} -- confirm this export is intended and "
        "appropriately shared before distributing it. Advisory only: the export already "
        "completed, nothing was blocked."
    )
