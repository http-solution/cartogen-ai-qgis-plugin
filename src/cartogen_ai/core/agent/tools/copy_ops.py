"""Copy features between layers (PLAN-023 R9-4): the field mapping and the value conversion, pure Python (no QGIS, no numpy).

copy_features_between_layers (copy_features_tool.py) reads the features and writes them to the other layer through QGIS; what can be checked offline is here.

Field mapping: `field_mapping` is {target field: source field}. A target field that is not named is matched to the source field with the same name (case-insensitive); a target
field with no match stays empty (NULL) and the preview lists it. The target's `fid` column is never filled automatically (the GeoPackage numbers its own features); name it in
the mapping to fill it on purpose. A name that does not exist is an error, never a silent skip. Values are converted to the target field's type; a value that cannot be
converted ('abc' into an integer field) stops the whole copy before anything is written, and the reply names the first few.
Known answers (the tests): with source fields (name, pop) and target fields (title, pop, note) and the mapping {title: name}, pairs are name to title and pop to pop, and note stays empty."""
import math

MAX_FEATURES = 20000
AUTO_SKIP = ("fid",)
LIST_MAX = 5


def kind_from_type_name(type_name):
    """'Int', 'LongLong', 'Double', 'String' or 'Other' from a QGIS field type name ('integer', 'Integer64', 'double', 'real', 'string', 'text', 'date', ...). Pure."""
    name = str(type_name or "").strip().lower()
    if name in ("integer64", "longlong", "int8", "bigint"):
        return "LongLong"
    if name in ("integer", "int", "int4", "smallint", "int2"):
        return "Int"
    if name in ("double", "real", "float", "numeric", "decimal", "double precision"):
        return "Double"
    if name in ("string", "text", "varchar", "char") or name.startswith(("string", "varchar", "char")):
        return "String"
    return "Other"


def resolve_mapping(source_fields, target_fields, mapping=None):
    """(pairs, empty_targets, unused_sources, error): `pairs` is a list of (source field, target field); `empty_targets` the target fields left empty; `unused_sources` the source
    fields not copied. error is a text when the mapping names a field that does not exist, else None. Pure."""
    source_by_lower = {s.lower(): s for s in source_fields}
    target_by_lower = {t.lower(): t for t in target_fields}
    explicit = {}
    for target, source in (mapping or {}).items():
        t, s = target_by_lower.get(str(target).lower()), source_by_lower.get(str(source).lower())
        if t is None:
            return None, None, None, f"The target layer has no field '{target}'."
        if s is None:
            return None, None, None, f"The source layer has no field '{source}'."
        explicit[t] = s
    pairs = []
    for t in target_fields:
        if t in explicit:
            pairs.append((explicit[t], t))
        elif t.lower() not in AUTO_SKIP and t.lower() in source_by_lower:
            pairs.append((source_by_lower[t.lower()], t))
    used_targets = {t for _s, t in pairs}
    used_sources = {s for s, _t in pairs}
    return pairs, [t for t in target_fields if t not in used_targets], [s for s in source_fields if s not in used_sources], None


def convert_value(value, kind):
    """(value converted for a target field of `kind`, error text or None). None stays None; 'Other' kinds pass unchanged. Whole numbers into integer fields only. Pure."""
    if value is None or kind == "Other":
        return value, None
    try:
        if kind in ("Int", "LongLong"):
            if isinstance(value, bool):
                return int(value), None
            number = float(value)
            if not math.isfinite(number) or number != int(number):
                return None, f"'{value}' is not a whole number."
            return int(number), None
        if kind == "Double":
            number = float(value)
            return (number, None) if math.isfinite(number) else (None, f"'{value}' is not a finite number.")
    except (TypeError, ValueError, OverflowError):
        return None, f"'{value}' is not a number."
    return str(value), None


def check_request(source_layer, target_layer, field_mapping=None, filter_expression=None, only_selected=None):
    """Error text for a copy request that cannot be run, else None. Pure."""
    if not str(source_layer or "").strip() or not str(target_layer or "").strip():
        return "source_layer and target_layer are both needed."
    if str(source_layer).strip() == str(target_layer).strip():
        return "source_layer and target_layer are the same layer; copying inside one layer is not supported."
    if field_mapping is not None and (not isinstance(field_mapping, dict) or any(not isinstance(v, str) for v in field_mapping.values())):
        return "field_mapping must be an object {target field: source field}."
    if filter_expression is not None and only_selected:
        return "give a filter_expression or only_selected, not both."
    return None


def describe_scope(how, count, total):
    """Words for the preview: which features are copied. `how` is 'filter', 'selected' or 'all'. Pure."""
    if how == "filter":
        return f"{count} of {total} feature(s) that match the filter"
    if how == "selected":
        return f"the {count} selected feature(s) (of {total})"
    return f"all {count} feature(s)"


def list_some(names):
    """'a, b, c' for up to LIST_MAX names, then '... (n more)'. Pure."""
    names = list(names)
    text = ", ".join(names[:LIST_MAX])
    return text + (f" ... ({len(names) - LIST_MAX} more)" if len(names) > LIST_MAX else "")
