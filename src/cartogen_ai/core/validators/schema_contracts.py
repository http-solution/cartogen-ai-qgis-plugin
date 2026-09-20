# -*- coding: utf-8 -*-
"""
Machine-readable dataset schema contracts for Cartogen AI.

Point 5 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md flagged a
REAL GAP: "No YAML/JSON schema files, no foreign_key/required_fields/
validate_schema symbol anywhere in src/. The only 'schema' hits are the LLM
function-calling JSON schema and runtime QgsFields objects -- column
meaning is inferred by the model at call time, not pre-validated against a
contract." That review's own maintenance note suggested starting with just
health_facilities and admin2 -- schema_contracts/health_facilities.json and
contracts/admin2.json do exactly that, as real JSON files (not
inline Python dicts), so a non-developer can add or edit a contract without
touching code.

Contract JSON shape:
{
  "dataset": "<name>",
  "description": "<what this dataset represents>",
  "required_fields": [
    {
      "aliases": ["<name1>", "<name2>", ...],
      "type": "<QVariant type name, e.g. String/LongLong/Double/DateTime/Bool>",
      "allowed_values": [...],   # optional -- a controlled-vocabulary/domain check
      "description": "..."
    }
  ]
}

"aliases" (always a list, even for a single acceptable name) exists because
this codebase already treats admin/pcode field names as NOT standardized
across sources -- calculate_severity_index/calculate_presence_gap take
unit_name_field/presence_admin_field as caller-supplied PARAMETERS rather
than assuming a fixed name, precisely because real admin-boundary field
names vary by country/provider (ADM2_PCODE vs. admin2_pcode vs. adm2_pcode,
etc.). A contract that required one exact name would be less useful than
this codebase's own existing tools for the same data. Matching is
case-insensitive, mirroring fetch_hdx_admin_boundaries_network_phase's own
pcode-field detection (`k.lower() == f"adm{level_num}_pcode"`).

Field type checking compares against QVariant.<type name> -- the exact
enum vocabulary already used elsewhere in this codebase
(_qvariant_type_for_dtype in tools/vector_tools.py maps pandas dtypes to
QVariant.Bool/LongLong/Double/DateTime/String) -- rather than a
provider-dependent field.typeName() string, which varies by data source
(shapefile vs. memory vs. GeoPackage) in ways this project has no live
QGIS install to verify against.

This module is a validator, not an enforcer: nothing here blocks a tool
from running on non-conforming data by itself. models/dataset_status.py's
QA gate is what actually gates a transition (VALIDATED -> ANALYSIS_READY)
on a schema-contract result, and only when a contract_name is explicitly
supplied -- not every dataset has a contract yet, so this is opt-in per
call, never inferred.
"""

import json
import pathlib

_CONTRACTS_DIR = pathlib.Path(__file__).parent / "contracts"

try:
    from qgis.PyQt.QtCore import QVariant
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    QVariant = None


def list_contracts():
    """Names of all available schema contracts (JSON filenames, without
    extension, in the contracts/ directory next to this module)."""
    if not _CONTRACTS_DIR.is_dir():
        return []
    return sorted(p.stem for p in _CONTRACTS_DIR.glob("*.json"))


def _load_contract(contract_name):
    path = _CONTRACTS_DIR / f"{contract_name}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"_load_error": str(e)}


def _match_field(field_names_lower_map, aliases):
    """Case-insensitive match of any alias against the layer's real field
    names. Returns the layer's actual field name (real casing) or None."""
    for alias in aliases:
        match = field_names_lower_map.get(alias.lower())
        if match:
            return match
    return None


def validate_layer_schema(layer, contract_name):
    """Checks a QGIS vector layer's fields (presence, type, and optional
    controlled-vocabulary values) against a named contract. Never raises on
    a non-conforming layer -- always returns a structured report with
    missing_fields / type_mismatches / value_violations and an overall
    passed bool."""
    contract = _load_contract(contract_name)
    if contract is None:
        return {"error": f"No schema contract named '{contract_name}'. Available: {list_contracts()}"}
    if "_load_error" in contract:
        return {"error": f"Contract '{contract_name}' is not valid JSON: {contract['_load_error']}"}

    if layer is None or not hasattr(layer, "fields"):
        return {"error": "validate_layer_schema requires a vector layer with fields()."}

    field_names_lower_map = {n.lower(): n for n in layer.fields().names()}
    missing_fields = []
    type_mismatches = []
    value_violations = []

    for spec in contract.get("required_fields", []):
        aliases = spec.get("aliases") or []
        if not aliases:
            continue
        matched_name = _match_field(field_names_lower_map, aliases)
        if matched_name is None:
            missing_fields.append(aliases[0])
            continue

        expected_type_name = spec.get("type")
        if expected_type_name and QGIS_AVAILABLE:
            expected = getattr(QVariant, expected_type_name, None)
            # An unrecognized type name in the contract is left unchecked
            # rather than silently reported as a mismatch -- a typo in the
            # contract JSON shouldn't masquerade as a real data problem.
            if expected is not None:
                idx = layer.fields().indexFromName(matched_name)
                actual_field = layer.fields().field(idx)
                if actual_field.type() != expected:
                    type_mismatches.append({
                        "field": matched_name,
                        "expected_type": expected_type_name,
                        "actual_type": actual_field.typeName(),
                    })

        allowed_values = spec.get("allowed_values")
        if allowed_values:
            allowed_set = set(allowed_values)
            bad_values = set()
            bad_count = 0
            for feature in layer.getFeatures():
                value = feature.attribute(matched_name)
                if value is not None and value not in allowed_set:
                    bad_values.add(value)
                    bad_count += 1
            if bad_count > 0:
                value_violations.append({
                    "field": matched_name,
                    "bad_count": bad_count,
                    "example_values": sorted(str(v) for v in bad_values)[:5],
                })

    passed = not missing_fields and not type_mismatches and not value_violations
    return {
        "success": True,
        "contract": contract_name,
        "dataset": contract.get("dataset", contract_name),
        "missing_fields": missing_fields,
        "type_mismatches": type_mismatches,
        "value_violations": value_violations,
        "passed": passed,
    }
