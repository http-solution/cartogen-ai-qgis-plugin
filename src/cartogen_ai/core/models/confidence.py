# -*- coding: utf-8 -*-
"""Confidence/uncertainty classification for Cartogen AI layers -- point 23
of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.

Same shape as sensitivity.py (point 24), deliberately: a layer gets tagged
with an epistemic-status level -- OBSERVED/DERIVED/MODELED/INFERRED/UNKNOWN,
the reviewer's own stated taxonomy -- via set_layer_confidence, and
get_layer_confidence reads it back. No automated classification exists: a
layer is only ever as confident as whoever calls set_layer_confidence says
it is, matching this project's own restraint on point 24 (no heuristic
guessing from field names or tool provenance). Genuinely automating this --
e.g. having every analytical tool self-report its own output's confidence
level -- would need per-tool epistemic judgment calls (is a buffer's output
DERIVED or MODELED? is a join OBSERVED if both inputs were?) this module
does not make unilaterally; tagging stays a deliberate, explicit action.

Same durable-storage pattern as sensitivity.py/dataset_status.py/lineage.py:
a JSON blob in a layer custom property, survives project save/reload for
free."""

import json

from ...infrastructure.settings_keys import PROJECT_PROPERTY_CONFIDENCE

CONFIDENCE_PROPERTY_KEY = PROJECT_PROPERTY_CONFIDENCE
CONFIDENCE_LEVELS = ["OBSERVED", "DERIVED", "MODELED", "INFERRED", "UNKNOWN"]


def _default_record() -> dict:
    return {"level": None, "reason": None}


def get_layer_confidence(layer) -> dict:
    """Reads a layer's current confidence record: {"level": <one of
    CONFIDENCE_LEVELS, or None>, "reason": <str or None>}. A layer that was
    never tagged returns level=None -- distinct from UNKNOWN, which is an
    explicit classification (someone looked and couldn't determine
    provenance), not a default guessed on the caller's behalf."""
    if layer is None:
        return _default_record()
    try:
        raw = layer.customProperty(CONFIDENCE_PROPERTY_KEY, "")
    except Exception:
        return _default_record()
    if not isinstance(raw, str) or not raw.strip():
        return _default_record()
    try:
        record = json.loads(raw)
    except Exception:
        return _default_record()
    if not isinstance(record, dict) or record.get("level") not in CONFIDENCE_LEVELS:
        return _default_record()
    record.setdefault("reason", None)
    return record


def set_layer_confidence(layer, level, reason=None) -> bool:
    if layer is None or level not in CONFIDENCE_LEVELS:
        return False
    try:
        layer.setCustomProperty(CONFIDENCE_PROPERTY_KEY, json.dumps({"level": level, "reason": reason}))
        return True
    except Exception:
        return False
