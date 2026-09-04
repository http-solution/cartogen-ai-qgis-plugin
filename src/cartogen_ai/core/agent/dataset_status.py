# -*- coding: utf-8 -*-
"""
Dataset Status / QA-Gate State Machine for Cartogen AI.

Point 2 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md flagged a
REAL GAP: "No dataset-lifecycle state concept exists anywhere -- no status
field, no @dataclass for it, nothing preventing a tool from running on data
that 'failed' an earlier check, because there is no earlier-check result to
consult."

This module is the shared concept that review's own Section C maintenance
note says points 4 (geometry QA), 5 (schema contracts), 6 (P-code depth), 7
(temporal GIS), and 17 (provenance sidecar) need to "hang off of." It
reuses the exact persistence pattern already proven by lineage.py -- a JSON
blob in a QGIS layer custom property -- instead of inventing a second,
parallel state store. Custom properties are serialized into the .qgz/.qgs
project file, so a layer's dataset status survives project save/reload for
free, the same guarantee lineage.py already relies on.

Scope of this first pass (2026-09-04): the ordered state machine, a
sequential advancement gate that refuses to skip states or silently
overwrite a failed check, and exactly ONE real automated check wired in --
geometry validity (via the existing diagnose_topology tool, point 4's
already-PARTIAL work) gating the STAGED -> VALIDATED transition. This
module deliberately does NOT implement schema contracts (point 5), P-code
hierarchy/uniqueness checks (point 6), temporal-validity concepts (point
7), or a provenance JSON sidecar writer (point 17) -- those remain real,
separate pieces of work. Each can now attach its own result to a layer's
"checks" record and gate its own transition (see _AUTOMATED_CHECK_TRANSITIONS
below) instead of needing its own bespoke state-tracking -- but inventing
placeholder checks for them here, before they exist, would be exactly the
kind of "looks validated but isn't" gap point 2 itself describes.
"""

import json
import time

try:
    from qgis.core import QgsProject  # noqa: F401 -- import used only to gate QGIS_AVAILABLE
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

DATASET_STATUS_PROPERTY_KEY = "cartogen_ai/dataset_status"

# Order matters: this list IS the state machine. advance_dataset_status()
# only allows moving to the very next state in this sequence (or re-stating
# the current one, or moving back), never skipping ahead -- that ordering
# check is the actual gate point 2 found missing.
STATUS_ORDER = [
    "INGESTED",
    "STAGED",
    "VALIDATED",
    "ANALYSIS_READY",
    "CARTOGRAPHY_READY",
    "PUBLICATION_READY",
]

# (from_status, to_status) -> check name, for the forward transitions that
# have a real, automated check wired in. Every other forward transition is
# manual-only (requires a `note` justifying it) -- see the module docstring
# for why no automated check is invented for the others yet.
_AUTOMATED_CHECK_TRANSITIONS = {
    ("STAGED", "VALIDATED"): "geometry_validity",
}


# Unlike lineage.py, the functions below don't gate on module-level
# QGIS_AVAILABLE themselves -- they operate on whatever layer object is
# handed to them (duck-typed on customProperty/setCustomProperty/
# getFeatures), which keeps this state machine directly unit-testable
# with a plain fake layer instead of only ever through a live QGIS
# object. In production this is equivalent: dataset_status_tools.py's
# _find_layer_by_name already returns None whenever QGIS_AVAILABLE is
# False, and every function here already treats layer=None as a no-op
# / default-record case.


def _default_record():
    return {"status": None, "history": [], "checks": {}}


def get_dataset_status(layer) -> dict:
    """Reads the current dataset-status record for a layer:
    {"status": <one of STATUS_ORDER, or None>, "history": [...], "checks": {...}}.
    A layer that was never tagged returns the default record with
    status=None -- distinct from guessing it must be INGESTED, which this
    module has no actual basis for."""
    if layer is None:
        return _default_record()
    try:
        raw = layer.customProperty(DATASET_STATUS_PROPERTY_KEY, "")
    except Exception:
        return _default_record()
    if not isinstance(raw, str) or not raw.strip():
        return _default_record()
    try:
        record = json.loads(raw)
    except Exception:
        return _default_record()
    if not isinstance(record, dict) or "status" not in record:
        return _default_record()
    record.setdefault("history", [])
    record.setdefault("checks", {})
    return record


def _write_record(layer, record) -> bool:
    if layer is None:
        return False
    try:
        layer.setCustomProperty(DATASET_STATUS_PROPERTY_KEY, json.dumps(record))
        return True
    except Exception as e:
        print(f"[DatasetStatus] Failed to write dataset status: {e}")
        return False


def set_initial_status(layer, status="INGESTED", note=None) -> dict:
    """Tags a layer with a starting status. For a layer with no tracked
    record yet only -- refuses to overwrite an existing record so a stray
    call can't quietly wipe out real QA history back to INGESTED. Use
    advance_dataset_status for anything already tracked."""
    if status not in STATUS_ORDER:
        return {"error": f"Unknown status '{status}'. Must be one of: {', '.join(STATUS_ORDER)}."}
    existing = get_dataset_status(layer)
    if existing["status"] is not None:
        return {
            "error": f"Layer already has a tracked status ('{existing['status']}'). "
                     f"Use advance_dataset_status to change it, not set_initial_status."
        }
    record = {
        "status": status,
        "history": [{
            "status": status,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": note,
            "check": None,
        }],
        "checks": {},
    }
    if not _write_record(layer, record):
        return {"error": "Failed to write dataset status to layer."}
    return {"success": True, "status": status}


def _run_automated_check(check_name, layer):
    """Runs one of the real, wired-in automated checks. Returns
    (passed: bool, detail: dict). The only one implemented so far is
    geometry_validity, via the existing diagnose_topology tool (point 4) --
    reusing that check rather than re-implementing geometry validation
    here. Duck-types on getFeatures() rather than a QGIS layer-type enum
    (matching this codebase's own convention, e.g. get_layers()'s
    hasattr(layer, "fields") check) so a raster layer gets an honest
    "not applicable" instead of diagnose_topology crashing on it."""
    if check_name == "geometry_validity":
        if not hasattr(layer, "getFeatures"):
            return False, {"error": "geometry_validity only applies to vector layers."}
        from .tools.vector_tools import diagnose_topology
        result = diagnose_topology(layer.name())
        if "error" in result:
            return False, result
        passed = result.get("invalid_geometries", 1) == 0
        return passed, result
    return False, {"error": f"No automated check implemented for '{check_name}'."}


def advance_dataset_status(layer, target_status, note=None, override=False) -> dict:
    """The actual QA gate. Moves a layer's tracked status by exactly one
    step in STATUS_ORDER (or re-states the current one). Refuses to:
      - advance a layer with no starting status yet (call set_initial_status first)
      - skip ahead (e.g. STAGED -> ANALYSIS_READY directly)
      - move forward across a transition with a wired-in automated check
        (see _AUTOMATED_CHECK_TRANSITIONS) unless that check actually
        passes -- override=True bypasses this, but only with a mandatory
        note explaining why, recorded in history so the bypass is
        auditable rather than silent
      - move forward across a transition with NO automated check yet,
        without a note justifying the manual advance (this module never
        pretends a check ran when none exists)
      - move backward (e.g. VALIDATED -> STAGED, marking a regression)
        without a note explaining why
    """
    if target_status not in STATUS_ORDER:
        return {"error": f"Unknown status '{target_status}'. Must be one of: {', '.join(STATUS_ORDER)}."}

    record = get_dataset_status(layer)
    current = record["status"]
    if current is None:
        return {"error": "Layer has no tracked dataset status yet. Call set_initial_status first."}

    current_idx = STATUS_ORDER.index(current)
    target_idx = STATUS_ORDER.index(target_status)

    is_forward_step = target_idx == current_idx + 1
    is_backward = target_idx < current_idx
    is_restate = target_idx == current_idx

    if not (is_forward_step or is_backward or is_restate):
        skipped = STATUS_ORDER[current_idx + 1:target_idx]
        return {
            "error": f"Cannot advance '{current}' directly to '{target_status}' -- "
                     f"skips {skipped}. Advance one step at a time."
        }

    if is_backward and not note:
        return {"error": f"Moving backward ('{current}' -> '{target_status}') requires a note explaining why."}

    check_detail = None
    if is_forward_step:
        check_name = _AUTOMATED_CHECK_TRANSITIONS.get((current, target_status))
        if check_name:
            passed, check_detail = _run_automated_check(check_name, layer)
            if not passed and not override:
                return {
                    "error": f"Automated check '{check_name}' did not pass for "
                             f"'{current}' -> '{target_status}'.",
                    "check_result": check_detail,
                    "hint": "Fix the underlying issue, or call again with override=True "
                            "and a note explaining why the advance is justified anyway.",
                }
            if override and not note:
                return {"error": "override=True requires a note explaining the bypass."}
        elif not note:
            return {
                "error": f"'{current}' -> '{target_status}' has no automated check yet -- "
                         f"pass a note explaining the manual advance."
            }

    record["status"] = target_status
    record["history"].append({
        "status": target_status,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": note,
        "check": check_detail,
        "override": bool(override and check_detail is not None),
    })
    if check_detail is not None:
        record["checks"][target_status] = check_detail

    if not _write_record(layer, record):
        return {"error": "Failed to write dataset status to layer."}

    result = {"success": True, "previous_status": current, "status": target_status}
    if check_detail is not None:
        result["check_result"] = check_detail
    return result
