# -*- coding: utf-8 -*-
"""
P-code depth validation for Cartogen AI.

Point 6 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md flagged
a REAL GAP, extending an already-partially-logged item:
HUMANITARIAN_CARTOGRAPHY_STANDARDS.md Section I already logs basic P-code
*usage* as substantially met, but flags "no check against reusing a
retired P-code." Going further, fetch_hdx_admin_boundaries only detects
WHICH field is the P-code field -- it validates neither uniqueness, nor
the admin2-pcode-prefix-matches-parent-admin1-pcode hierarchy, nor any
temporal-validity concept.

This module closes the first two of those three:
  - UNIQUENESS: no P-code value repeated across features in a layer.
  - HIERARCHY: a child admin unit's P-code is prefixed by its own parent
    P-code, on the SAME row -- the real OCHA/HDX COD-AB convention (e.g.
    admin2 'YE1201' under admin1 'YE12'). This is a pure string-prefix
    check on two sibling attributes, not a spatial one: real COD-AB
    admin2 layers already carry their parent's P-code denormalized onto
    every row (see validators/contracts/admin2.json, which requires both
    admin2_pcode and admin1_pcode on one layer) -- so this needs no
    second "parent layer" argument or spatial join at all. The SEPARATE
    question of whether an admin2 polygon spatially sits inside its
    claimed admin1 parent's geometry is the semantic topology check
    point 4 already named and explicitly left unbuilt -- a genuinely
    different (and harder to verify without a live QGIS install) check
    from this one.

Deliberately NOT addressed here:
  - Temporal validity (a P-code valid at one date, retired/reissued at
    another) -- that's point 7's territory (temporal GIS fields), which
    doesn't exist in this codebase yet either; a P-code validity date
    range has nothing to check itself against without it.
  - "No check against reusing a retired P-code" specifically -- that
    needs a persistent historical registry of P-codes seen across
    sessions/projects, not a single-layer, single-point-in-time check.
    Real, separate future work; not implemented here.

Field matching reuses the same alias-list, case-insensitive approach as
schema_contracts.py (admin2_pcode/adm2_pcode/ADM2_PCODE all acceptable),
for the same reason: this codebase already treats admin/pcode field
names as varying by source, not fixed (calculate_severity_index's
unit_name_field, etc.).
"""

_ADMIN2_PCODE_ALIASES = ["admin2_pcode", "adm2_pcode", "ADM2_PCODE"]
_ADMIN1_PCODE_ALIASES = ["admin1_pcode", "adm1_pcode", "ADM1_PCODE"]


def _match_field(field_names_lower_map, aliases):
    """Case-insensitive match of any alias against a layer's real field
    names. Returns the layer's actual field name (real casing) or None."""
    for alias in aliases:
        match = field_names_lower_map.get(alias.lower())
        if match:
            return match
    return None


def check_pcode_uniqueness(layer, pcode_field=None):
    """Checks that every non-null, non-empty value in the P-code field is
    unique across the layer's features. pcode_field can be given
    explicitly (any real field name on the layer); if omitted, tries the
    admin2 P-code alias list first, since that's this codebase's most
    common P-code field. Returns a structured report; never raises."""
    if layer is None or not hasattr(layer, "fields"):
        return {"error": "check_pcode_uniqueness requires a vector layer with fields()."}

    field_names_lower_map = {n.lower(): n for n in layer.fields().names()}
    if pcode_field is None:
        pcode_field = _match_field(field_names_lower_map, _ADMIN2_PCODE_ALIASES)
        if pcode_field is None:
            return {"error": f"No P-code field found or specified. Tried aliases: {_ADMIN2_PCODE_ALIASES}"}
    else:
        matched = field_names_lower_map.get(pcode_field.lower())
        if matched is None:
            return {"error": f"Field '{pcode_field}' not found on this layer."}
        pcode_field = matched

    seen_at = {}
    duplicates = {}
    null_or_empty_count = 0
    total = 0
    for feature in layer.getFeatures():
        total += 1
        value = feature.attribute(pcode_field)
        if value is None or value == "":
            null_or_empty_count += 1
            continue
        fid = feature.id() if hasattr(feature, "id") else None
        if value in seen_at:
            duplicates.setdefault(value, [seen_at[value]])
            duplicates[value].append(fid)
        else:
            seen_at[value] = fid

    passed = not duplicates
    return {
        "success": True,
        "pcode_field": pcode_field,
        "total_features": total,
        "unique_pcodes": len(seen_at),
        "null_or_empty_pcodes": null_or_empty_count,
        "duplicate_pcodes": {str(k): v for k, v in duplicates.items()},
        "passed": passed,
    }


def check_pcode_hierarchy(layer, child_pcode_field=None, parent_pcode_field=None):
    """Checks that each feature's child P-code (e.g. admin2_pcode) is
    prefixed by its own parent P-code (e.g. admin1_pcode) on the SAME
    row. Skips (does not count as a mismatch) any feature missing either
    value -- a hierarchy check has nothing to compare there. Returns a
    structured report; never raises."""
    if layer is None or not hasattr(layer, "fields"):
        return {"error": "check_pcode_hierarchy requires a vector layer with fields()."}

    field_names_lower_map = {n.lower(): n for n in layer.fields().names()}
    if child_pcode_field is None:
        child_pcode_field = _match_field(field_names_lower_map, _ADMIN2_PCODE_ALIASES)
    else:
        child_pcode_field = field_names_lower_map.get(child_pcode_field.lower())
    if parent_pcode_field is None:
        parent_pcode_field = _match_field(field_names_lower_map, _ADMIN1_PCODE_ALIASES)
    else:
        parent_pcode_field = field_names_lower_map.get(parent_pcode_field.lower())

    if child_pcode_field is None or parent_pcode_field is None:
        return {
            "error": "Could not find both a child and parent P-code field on this layer.",
            "child_pcode_field": child_pcode_field,
            "parent_pcode_field": parent_pcode_field,
        }

    mismatches = []
    total = 0
    checked = 0
    for feature in layer.getFeatures():
        total += 1
        child_value = feature.attribute(child_pcode_field)
        parent_value = feature.attribute(parent_pcode_field)
        if not child_value or not parent_value:
            continue
        checked += 1
        if not str(child_value).startswith(str(parent_value)):
            mismatches.append({
                "feature_id": feature.id() if hasattr(feature, "id") else None,
                "child_pcode": child_value,
                "parent_pcode": parent_value,
            })

    passed = not mismatches
    return {
        "success": True,
        "child_pcode_field": child_pcode_field,
        "parent_pcode_field": parent_pcode_field,
        "total_features": total,
        "checked_features": checked,
        "skipped_missing_values": total - checked,
        "mismatches": mismatches,
        "passed": passed,
    }
