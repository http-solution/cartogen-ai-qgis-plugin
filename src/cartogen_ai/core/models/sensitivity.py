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

from ...infrastructure.settings_keys import PROJECT_PROPERTY_SENSITIVITY

SENSITIVITY_PROPERTY_KEY = PROJECT_PROPERTY_SENSITIVITY
SENSITIVITY_LEVELS = ["PUBLIC", "INTERNAL", "RESTRICTED", "SENSITIVE", "HIGHLY_SENSITIVE"]

# Only these levels trigger an export-time advisory warning
_LEVELS_REQUIRING_EXPORT_WARNING = {"RESTRICTED", "SENSITIVE"}


def _default_record() -> dict:
    return {"level": None, "reason": None}


def _unreadable_tag_record(why) -> dict:
    """What a tag that IS stored but cannot be read counts as: SENSITIVE, with a reason that says so. It used to read as untagged, so a corrupted
    SENSITIVE tag unprotected the layer (owner decision 2026-11-22: fail closed). Re-tagging the layer in the Sensitivity dialog replaces it."""
    from ..logger import log_event
    log_event("sensitivity_tag_unreadable", why=why)
    return {"level": "SENSITIVE", "reason": "the stored protection tag could not be read, so the layer is treated as protected"}


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
    except Exception as exc:
        # QGIS refused to answer (a layer whose C++ object is gone, for one), so whether a tag exists is unknown, not "no tag" (DEF-8, owner
        # decision 2026-11-22: protection that cannot be read counts as protected). Not seen on a real layer; offline test only.
        return _unreadable_tag_record("read_failed_" + type(exc).__name__)
    if not isinstance(raw, str) or not raw.strip():
        return _default_record()
    try:
        record = json.loads(raw)
    except Exception:
        return _unreadable_tag_record("invalid_json")
    if not isinstance(record, dict) or record.get("level") not in SENSITIVITY_LEVELS:
        return _unreadable_tag_record("not_a_record_or_unknown_level")
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


def check_export_allowed(layer) -> tuple:
    """
    Evaluates whether raw layer export is permitted under humanitarian data protection policy:
    - PUBLIC: Allowed normally.
    - INTERNAL: Allowed with warning.
    - RESTRICTED: Allowed with advisory warning.
    - HIGHLY_SENSITIVE: Raw export BLOCKED (only sanitized/obfuscated derivatives permitted).
    Returns (allowed: bool, reason_or_message: str).
    """
    record = get_layer_sensitivity(layer)
    level = record.get("level")
    if level == "HIGHLY_SENSITIVE":
        reason = record.get("reason")
        suffix = f" ({reason})" if reason else ""
        return False, (
            f"Export BLOCKED under Do No Harm protection policy: Layer is tagged 'HIGHLY_SENSITIVE'{suffix}. "
            "Raw unmasked export of highly sensitive data (e.g. GBV / named protection cases) is prohibited. "
            "Please create and export an obfuscated or aggregated derivative layer instead."
        )
    return True, ""


def export_warning_for(layer) -> str:
    """Returns an advisory warning string if the layer is tagged RESTRICTED
    or SENSITIVE, else "" (falsy, safe to use directly in an `if`)."""
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
