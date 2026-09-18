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

Scope as of this update (2026-09-04): the ordered state machine, a
sequential advancement gate that refuses to skip states or silently
overwrite a failed check, and THREE real automated checks now wired in --
P-code depth (uniqueness + parent/child hierarchy prefix-match, point 6's
work, via pcode_validation.py) gating INGESTED -> STAGED; geometry validity
(via the existing diagnose_topology tool, point 4's work) gating
STAGED -> VALIDATED; and schema-contract validation (point 5's work, via
schema_contracts.py) gating VALIDATED -> ANALYSIS_READY when a
contract_name is supplied. This module deliberately does NOT implement
temporal-validity concepts (point 7) or a provenance JSON sidecar writer
(point 17) -- those remain real, separate pieces of work. Each can now
attach its own result to a layer's "checks" record and gate its own
transition (see _AUTOMATED_CHECK_TRANSITIONS below) instead of needing its
own bespoke state-tracking -- but inventing placeholder checks for them
here, before they exist, would be exactly the kind of "looks validated but
isn't" gap point 2 itself describes.
"""

import json
import time

try:
    from qgis.core import QgsProject  # noqa: F401 -- import used only to gate QGIS_AVAILABLE
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

from ...infrastructure.settings_keys import PROJECT_PROPERTY_DATASET_STATUS

DATASET_STATUS_PROPERTY_KEY = PROJECT_PROPERTY_DATASET_STATUS

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
    # pcode_depth (point 6) gates INGESTED -> STAGED: P-code uniqueness and
    # parent/child hierarchy are properties of the raw ingested data itself
    # (is this dataset's identity/joinability sound before it's even
    # staged for further QA), unlike geometry_validity and schema_contract
    # below, which are about the data's shape and structure. Unlike
    # schema_contract, this one needs no caller-supplied parameter to be
    # "opt-in" -- it auto-detects applicability from the layer's own
    # fields (see _run_automated_check) and reports itself not applicable,
    # not failing, on a layer with no P-code-shaped fields at all.
    ("INGESTED", "STAGED"): "pcode_depth",
    ("STAGED", "VALIDATED"): "geometry_validity",
    # Opt-in, not automatic: this only actually runs when the caller passes
    # a contract_name to advance_dataset_status (see that function and
    # _run_automated_check below) -- not every dataset has a schema
    # contract yet (agent/contracts/ currently has two: health_facilities,
    # admin2), so a layer with no matching contract still falls through to
    # the ordinary "no automated check, note required" path rather than
    # being blocked by a check that has nothing to check against.
    ("VALIDATED", "ANALYSIS_READY"): "schema_contract",
    # v1.8.0 workstream 3: opt-in exactly like schema_contract above -- only
    # actually runs when the caller passes a layout_name to
    # advance_dataset_status. This is the real slot the external
    # "QGIS Cartographic Intelligence Standard" document's blocking quality
    # gates belong in: a genuine automated check gating the one transition
    # (CARTOGRAPHY_READY -> PUBLICATION_READY) that had zero automated
    # checks of any kind before this, rather than a parallel gate system.
    ("CARTOGRAPHY_READY", "PUBLICATION_READY"): "map_qa",
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


def _run_automated_check(check_name, layer, contract_name=None, layout_name=None):
    """Runs one of the real, wired-in automated checks. Returns
    (passed: bool, detail: dict).

    geometry_validity, via the existing diagnose_topology tool (point 4) --
    reusing that check rather than re-implementing geometry validation
    here. Duck-types on getFeatures() rather than a QGIS layer-type enum
    (matching this codebase's own convention, e.g. get_layers()'s
    hasattr(layer, "fields") check) so a raster layer gets an honest
    "not applicable" instead of diagnose_topology crashing on it.

    diagnose_topology was extended (2026-09-04) to also report
    duplicate_geometries and, for polygon layers, overlapping_feature_pairs
    -- both are checked here too, not just invalid_geometries, so this gate
    actually strengthens when that check does, with no state-machine change
    needed (exactly what point 2's own cross-reference note in the review
    doc says should happen). .get(..., 0) defaults on the two newer keys so
    a caller-supplied diagnose_topology result predating this extension
    (e.g. a test double) isn't treated as failing on keys it never claimed
    to report; invalid_geometries keeps its original fail-closed .get(..., 1)
    default.

    schema_contract, via agent/schema_contracts.py (point 5) -- requires a
    contract_name (advance_dataset_status only sets check_name to
    "schema_contract" at all when one was actually supplied; see that
    function). Duck-types on hasattr(layer, "fields") for the same reason
    geometry_validity duck-types on getFeatures().

    map_qa, via agent/tools/qa_checklist_tools.py's
    generate_map_product_qa_checklist (point 26, extended for v1.8.0
    workstream 3) -- requires a layout_name for the same opt-in reason
    schema_contract requires a contract_name. Fails the transition when
    either a mandatory print-layout element (MAP_MAIN/TITLE/LEGEND/
    SCALEBAR/NORTH_ARROW) is missing, or the layer is tagged RESTRICTED/
    SENSITIVE -- both real, reused signals the checklist already computes,
    not a new judgment call invented here. A SENSITIVE layer isn't
    permanently blocked: the same override=True + mandatory-note path
    every other failing check here already uses covers "yes, this
    disclosure is genuinely intended," recorded in history so the bypass
    is auditable, matching this module's own existing design rather than
    a bespoke sensitivity-specific override flow."""
    if check_name == "geometry_validity":
        if not hasattr(layer, "getFeatures"):
            return False, {"error": "geometry_validity only applies to vector layers."}
        from .tools.vector_tools import diagnose_topology
        result = diagnose_topology(layer.name())
        if "error" in result:
            return False, result
        passed = (
            result.get("invalid_geometries", 1) == 0
            and result.get("duplicate_geometries", 0) == 0
            and result.get("overlapping_feature_pairs", 0) == 0
        )
        return passed, result
    if check_name == "schema_contract":
        if contract_name is None:
            return False, {"error": "schema_contract check requires a contract_name."}
        if not hasattr(layer, "fields"):
            return False, {"error": "schema_contract only applies to vector layers with fields()."}
        from .schema_contracts import validate_layer_schema
        result = validate_layer_schema(layer, contract_name)
        if "error" in result:
            return False, result
        return result.get("passed", False), result
    if check_name == "pcode_depth":
        if not hasattr(layer, "fields"):
            # Not a vector layer with fields() at all (e.g. a raster, or a
            # minimal test double) -- pcode depth simply isn't applicable,
            # same as a vector layer with no P-code-shaped fields below.
            # This check should never be what blocks a non-admin-boundary
            # layer from reaching STAGED.
            return True, {"applicable": False, "reason": "Layer has no fields() -- not a P-code-bearing vector layer."}
        from .pcode_validation import check_pcode_uniqueness, check_pcode_hierarchy
        uniqueness = check_pcode_uniqueness(layer)
        has_uniqueness_field = "error" not in uniqueness
        hierarchy = check_pcode_hierarchy(layer)
        has_hierarchy_fields = "error" not in hierarchy
        if not has_uniqueness_field and not has_hierarchy_fields:
            # No P-code-shaped fields at all -- this layer was never
            # claiming to be a P-code dataset, so "not applicable" passes
            # rather than blocking every non-admin-boundary layer from
            # ever reaching STAGED.
            return True, {"applicable": False, "reason": "No P-code fields found on this layer."}
        detail = {"applicable": True}
        passed = True
        if has_uniqueness_field:
            detail["uniqueness"] = uniqueness
            passed = passed and uniqueness.get("passed", False)
        if has_hierarchy_fields:
            detail["hierarchy"] = hierarchy
            passed = passed and hierarchy.get("passed", False)
        return passed, detail
    if check_name == "map_qa":
        if layout_name is None:
            return False, {"error": "map_qa check requires a layout_name."}
        from .tools.qa_checklist_tools import generate_map_product_qa_checklist
        result = generate_map_product_qa_checklist(layer.name(), layout_name=layout_name)
        if "error" in result:
            return False, result
        categories = result.get("categories", {})
        cartography = categories.get("cartography", {})
        missing = cartography.get("mandatory_elements_missing", [])
        disclosure = categories.get("disclosure", {})
        sensitivity_blocked = disclosure.get("level") in ("RESTRICTED", "SENSITIVE")
        passed = not missing and not sensitivity_blocked
        return passed, {
            "layout_name": layout_name,
            "mandatory_elements_missing": missing,
            "sensitivity_level": disclosure.get("level"),
            "sensitivity_blocked": sensitivity_blocked,
        }
    return False, {"error": f"No automated check implemented for '{check_name}'."}


def advance_dataset_status(layer, target_status, note=None, override=False, contract_name=None, layout_name=None) -> dict:
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

    contract_name is specific to the VALIDATED -> ANALYSIS_READY transition
    (see _AUTOMATED_CHECK_TRANSITIONS): the schema_contract check registered
    there only actually runs when contract_name is supplied here. Not every
    dataset has a contract yet (see agent/contracts/), so omitting it simply
    falls through to the ordinary unchecked-transition path (a note is
    required instead) rather than failing a check that has nothing to check
    against.

    layout_name is the same opt-in shape for CARTOGRAPHY_READY ->
    PUBLICATION_READY's map_qa check (v1.8.0 workstream 3): only supplied
    when this map product actually has a print layout to check, otherwise
    this transition falls through to the ordinary note-required path
    exactly like every other unchecked transition.
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
        if check_name == "schema_contract" and contract_name is None:
            # Opt-in: no contract was specified for this call, so this
            # transition is treated the same as one with no automated check
            # at all (falls through to the "note required" branch below)
            # rather than failing a check with nothing to check against.
            check_name = None
        if check_name == "map_qa" and layout_name is None:
            # Same opt-in shape as schema_contract above.
            check_name = None
        if check_name:
            passed, check_detail = _run_automated_check(
                check_name, layer, contract_name=contract_name, layout_name=layout_name,
            )
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
