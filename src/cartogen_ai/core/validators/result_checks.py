"""Checks on a result an analysis tool wrote (PLAN-031, step A of the roadmap): pure functions over a plain summary of the layer, so a wrong
answer is reported as wrong even when the model would have accepted it.

Why: the hand runs of 1.18.2 to 1.18.4 found silent wrong answers the model never noticed: a buffer applied in degrees (PLAN-026 class A), a
signed difference ranked as if bigger meant worse (class B), a column left by an earlier run read as this run's result (class C). Each was fixed
one at a time. These checks make the test general: given what a tool wrote, say pass, warn or fail with a plain-words detail.

This module has no QGIS and no Qt import on purpose, so every check is unit-testable. A separate adapter (not in this file) reads a real layer
into the summary. A check needs a summary key to run; a missing key means "not known", which is a skip, never a pass.

summary = {
  "name": str, "crs_authid": str|None, "crs_geographic": bool|None, "feature_count": int, "input_feature_count": int|None,
  "geometry": {"total": int, "invalid": int, "empty": int}|None,
  "fields": {field: {"count": non-null values, "null": nulls, "distinct": int, "min": number|None, "max": number|None,
                     "fingerprint": str|None}}}
context = {"distance_based": bool, "one_to_one": bool, "written_fields": {field: kind}, "previous_fingerprints": {field: str}}
  kind is one of RANGES (below)."""
PASS, WARN, FAIL = "pass", "warn", "fail"

# kind -> (lowest, highest) allowed; None means unbounded on that side. Hours is bounded because a road trip inside one country cannot take
# more than a few days; a value beyond it is a unit mistake (minutes or seconds read as hours), not a long journey.
RANGES = {
    "percent": (0.0, 100.0),
    "fraction": (0.0, 1.0),
    "score_0_1": (0.0, 1.0),
    "count": (0.0, None),
    "distance_m": (0.0, None),
    "area": (0.0, None),
    "hours": (0.0, 100.0),
}
INVALID_GEOMETRY_WARN_SHARE = 0.0     # any invalid or empty geometry is at least a warning
INVALID_GEOMETRY_FAIL_SHARE = 0.05    # more than 5 percent is a failure
CONSTANT_MIN_FEATURES = 3             # fewer features than this and "the same everywhere" means nothing


def _result(check_id, status, detail):
    return {"id": check_id, "status": status, "detail": detail}


def check_crs(summary, context):
    """A distance, buffer or area result computed in a geographic CRS is in degrees, not metres (PLAN-026 class A)."""
    if not context.get("distance_based"):
        return None
    geographic, authid = summary.get("crs_geographic"), summary.get("crs_authid")
    if geographic is None:
        return _result("crs", WARN, "The layer's coordinate system is not known, so whether the distances are metres or degrees cannot be checked.")
    if geographic:
        return _result("crs", FAIL, f"The result was computed in {authid or 'a geographic CRS'}, where distances and areas are in degrees, "
                                    "not metres. Reproject to a projected CRS (for example the local UTM zone) and run it again.")
    return _result("crs", PASS, f"Computed in a projected CRS ({authid or 'projected'}).")


def check_geometry(summary, context):
    """Share of invalid or empty geometries in the output."""
    geometry = summary.get("geometry")
    if not geometry or not geometry.get("total"):
        return None
    bad = geometry.get("invalid", 0) + geometry.get("empty", 0)
    share = bad / geometry["total"]
    if bad == 0:
        return _result("geometry", PASS, f"All {geometry['total']} geometries are valid and non-empty.")
    status = FAIL if share > INVALID_GEOMETRY_FAIL_SHARE else WARN
    return _result("geometry", status, f"{bad} of {geometry['total']} geometries ({share:.0%}) are invalid or empty.")


def check_fields_written(summary, context):
    """Each field the run says it wrote must hold values and must not be one value everywhere (a score that is the same for every district)."""
    results = []
    fields = summary.get("fields") or {}
    count = summary.get("feature_count") or 0
    for name in (context.get("written_fields") or {}):
        stats = fields.get(name)
        if stats is None:
            results.append(_result(f"field:{name}", FAIL, f"The field '{name}' is not on the output layer."))
        elif count and stats.get("count", 0) == 0:
            results.append(_result(f"field:{name}", FAIL, f"The field '{name}' is empty (null for all {count} features)."))
        elif count >= CONSTANT_MIN_FEATURES and stats.get("distinct") == 1:
            results.append(_result(f"field:{name}", FAIL, f"The field '{name}' has the same value for all {count} features, so it ranks nothing."))
        elif stats.get("null", 0):
            results.append(_result(f"field:{name}", WARN, f"The field '{name}' is null for {stats['null']} of {count} features."))
        else:
            results.append(_result(f"field:{name}", PASS, f"The field '{name}' has values for all {count} features."))
    return results


def _allowed(low, high):
    if low is not None and high is not None:
        return f"{low:g} to {high:g}"
    return f"at least {low:g}" if low is not None else f"at most {high:g}"


def check_value_range(summary, context):
    """A value outside what its stated unit allows: a percent of 140, a 0-to-1 score below zero (a signed difference read as a score, class B)."""
    results = []
    fields = summary.get("fields") or {}
    for name, kind in (context.get("written_fields") or {}).items():
        bounds, stats = RANGES.get(kind), fields.get(name)
        if bounds is None or not stats or stats.get("min") is None or stats.get("max") is None:
            continue
        low, high = bounds
        lowest, highest = stats["min"], stats["max"]
        if (low is not None and lowest < low - 1e-9) or (high is not None and highest > high + 1e-9):
            allowed = _allowed(low, high)
            results.append(_result(f"range:{name}", FAIL, f"The field '{name}' ({kind}) runs from {lowest:g} to {highest:g}, outside what a {kind} "
                                                          f"can be ({allowed})."))
        else:
            results.append(_result(f"range:{name}", PASS, f"The field '{name}' stays within the range of a {kind}."))
    return results


def check_not_stale(summary, context):
    """A field the run claims to have written must not be byte-identical to what it held before (class C: an old column read as the result)."""
    results = []
    previous = context.get("previous_fingerprints") or {}
    fields = summary.get("fields") or {}
    for name in (context.get("written_fields") or {}):
        before, now = previous.get(name), (fields.get(name) or {}).get("fingerprint")
        if before is None or now is None:
            continue
        if before == now:
            results.append(_result(f"stale:{name}", FAIL, f"The field '{name}' is identical to what it held before this run, so it was not recomputed."))
        else:
            results.append(_result(f"stale:{name}", PASS, f"The field '{name}' changed in this run."))
    return results


def check_feature_count(summary, context):
    """The output is not empty and, for a one-to-one tool, has as many features as the input."""
    count, source = summary.get("feature_count"), summary.get("input_feature_count")
    if count is None:
        return None
    if count == 0:
        return _result("feature_count", FAIL, "The output has 0 features.")
    if context.get("one_to_one") and source is not None and count != source:
        return _result("feature_count", FAIL, f"The output has {count} features but the input had {source}; this tool should return one per input feature.")
    return _result("feature_count", PASS, f"The output has {count} features.")


def run_checks(summary, context=None):
    """Every applicable check, in a fixed order. A check that cannot run (its inputs are not in the summary) is left out, not passed."""
    context = context or {}
    out = []
    for single in (check_feature_count, check_crs, check_geometry):
        found = single(summary, context)
        if found:
            out.append(found)
    for many in (check_fields_written, check_value_range, check_not_stale):
        out.extend(many(summary, context))
    return out


def summarize(checks):
    """('2 passed, 1 warning, 1 failed: crs; field:sev', failed ids). Plain words for the tool result; the reply must not leave a failure out."""
    failed = [c["id"] for c in checks if c["status"] == FAIL]
    warned = [c["id"] for c in checks if c["status"] == WARN]
    passed = len(checks) - len(failed) - len(warned)
    text = f"{passed} passed, {len(warned)} warning{'s' if len(warned) != 1 else ''}, {len(failed)} failed"
    if failed:
        text += ": " + "; ".join(failed)
    return text, failed
