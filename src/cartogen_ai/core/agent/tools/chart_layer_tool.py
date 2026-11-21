"""chart_field_by_category (LR-24): a bar, pie or line chart of a layer's field by category in ONE call, the numbers aggregated in code.

Why: in the 2026-11-20 live run (row C16) "make a bar chart of smoke_zones by name" took 22 tool calls and left four report tables in the project.
generate_chart needs typed labels and values, so the model first had to compute them: it listed unique values, added geometry columns, ran
statistics by category and basic statistics, then typed the results into generate_chart. Every typed number is a number that can drift from the
data. This tool reads the layer, counts or sums per category and draws the chart, and returns exactly what was plotted.

generate_chart itself stays off the main thread (it never touches QGIS objects, see NETWORK_ONLY_TOOLS); this tool reads a layer, so it runs on the main
thread and only then calls generate_chart's drawing code. Written without a QGIS install: tests/test_chart_layer_tool_live.py is its first execution in CI."""
from .registry import register_tool

try:
    from qgis.core import QgsProject, QgsVectorLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

MAX_FEATURES = 200_000
DEFAULT_TOP_N = 20
NO_VALUE_LABEL = "(no value)"
_AGGREGATES = ("count", "sum", "mean", "min", "max")
_ADDITIVE = ("count", "sum")        # the leftover categories can be added into one "Other" bar only for these


def aggregate_by_category(pairs, how="count"):
    """([(label, value)], skipped): `pairs` is [(category, number or None)]. A missing category becomes '(no value)'. `how` is count, sum, mean, min or max;
    count ignores the numbers, the others skip a pair whose number is missing (counted in `skipped`). Largest value first, ties by label. Pure."""
    groups = {}
    skipped = 0
    for category, number in pairs:
        label = NO_VALUE_LABEL if category is None or str(category).strip() == "" or str(category) == "NULL" else str(category)
        if how == "count":
            groups[label] = groups.get(label, 0) + 1
            continue
        if not isinstance(number, (int, float)) or isinstance(number, bool) or number != number:
            skipped += 1
            continue
        groups.setdefault(label, []).append(float(number))
    if how != "count":
        reduce = {"sum": sum, "mean": lambda xs: sum(xs) / len(xs), "min": min, "max": max}[how]
        groups = {label: reduce(values) for label, values in groups.items()}
    rows = sorted(groups.items(), key=lambda lv: (-lv[1], lv[0]))
    return rows, skipped


def cap_categories(rows, how, top_n=DEFAULT_TOP_N):
    """(rows, note or None): at most `top_n` bars. For count and sum the leftover categories are added into one 'Other' bar; for mean, min and max
    (which cannot be added) they are left out and the note says how many. Pure."""
    if top_n < 1 or len(rows) <= top_n:
        return rows, None
    if how in _ADDITIVE:
        kept, rest = rows[:top_n - 1], rows[top_n - 1:]
        return [*kept, ("Other", sum(v for _l, v in rest))], f"{len(rest)} smallest categories are combined into 'Other' (the chart shows at most {top_n} bars)."
    return rows[:top_n], f"{len(rows) - top_n} categories with a lower {how} are left out (the chart shows at most {top_n} bars)."


def _numeric_field_names(layer):
    return [f.name() for f in layer.fields() if f.isNumeric()]


@register_tool(
    "chart_field_by_category",
    "Draw a bar, pie or line chart of a layer's field by category in ONE call, with the numbers counted or summed from the layer itself: 'bar chart of "
    "smoke_zones by zone_type', 'pie chart of cases per district', 'chart of population by region'. Give category_field (the field whose values are the bars) "
    "and, to total a number, value_field with aggregate sum, mean, min or max; with no value_field it counts features per category. Returns the PNG path "
    "and the exact figures plotted, so report those and never type numbers by hand. Prefer this to listing unique values, running statistics algorithms "
    "and then generate_chart: those take many calls and leave extra tables in the project. Use generate_chart only when the labels and values are not in a layer.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "The vector layer (or table) to chart."},
            "category_field": {"type": "string", "description": "The field whose distinct values become the bars, slices or points."},
            "value_field": {"type": "string", "description": "Optional numeric field to total per category. Omit to count the features per category."},
            "aggregate": {"type": "string", "description": "count, sum, mean, min or max. Default: count without value_field, sum with it."},
            "chart_type": {"type": "string", "description": "'bar' (default), 'pie' or 'line'."},
            "title": {"type": "string", "description": "Chart title. Default names the layer, the field and the aggregate."},
            "top_n": {"type": "integer", "description": f"At most this many bars (default {DEFAULT_TOP_N}); the rest are combined into 'Other' for counts and sums."},
            "output_path": {"type": "string", "description": "Where to save the PNG. Defaults to a temporary file."},
        },
        "required": ["layer_name", "category_field"],
    },
    keywords=["bar chart", "pie chart", "chart by", "graph of", "count per", "number of features per", "frequency chart", "chart of"],
)
def chart_field_by_category(layer_name, category_field, value_field=None, aggregate=None, chart_type="bar", title=None, top_n=DEFAULT_TOP_N, output_path=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layers = QgsProject.instance().mapLayersByName(layer_name)
    layer = layers[0] if layers else None
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not isinstance(layer, QgsVectorLayer):
        return {"error": f"'{layer_name}' is not a vector layer or table."}
    names = [f.name() for f in layer.fields()]
    if category_field not in names:
        return {"error": f"Field '{category_field}' not found on '{layer_name}'. Fields: {', '.join(names)}."}
    how = (aggregate or ("sum" if value_field else "count")).lower()
    if how not in _AGGREGATES:
        return {"error": f"aggregate must be one of {list(_AGGREGATES)}."}
    if how != "count" and not value_field:
        return {"error": f"aggregate '{how}' needs value_field, the numeric field to {how}. Numeric fields: {_numeric_field_names(layer)}."}
    if value_field and how != "count" and value_field not in _numeric_field_names(layer):
        return {"error": f"value_field '{value_field}' is not a numeric field of '{layer_name}'. Numeric fields: {_numeric_field_names(layer)}."}
    try:
        top_n = int(top_n)
    except (TypeError, ValueError):
        return {"error": "top_n must be a whole number."}

    pairs, read, truncated = [], 0, False
    for feature in layer.getFeatures():
        if read >= MAX_FEATURES:
            truncated = True
            break
        read += 1
        pairs.append((feature[category_field], feature[value_field] if value_field and how != "count" else None))
    rows, skipped = aggregate_by_category(pairs, how)
    if not rows:
        return {"error": f"'{layer_name}' has no usable values to chart (field '{category_field}'" + (f", value field '{value_field}'" if value_field else "") + ")."}
    rows, cap_note = cap_categories(rows, how, top_n)

    from .reporting_tools import generate_chart
    unit = {"count": "Number of features", "sum": f"Sum of {value_field}", "mean": f"Mean of {value_field}",
            "min": f"Minimum of {value_field}", "max": f"Maximum of {value_field}"}[how]
    chart = generate_chart(chart_type or "bar", title or f"{unit} by {category_field} ({layer_name})", [label for label, _v in rows], [value for _l, value in rows],
                           x_label=category_field, y_label=unit, output_path=output_path)
    if "error" in chart:
        return chart
    result = {**chart, "layer_name": layer_name, "category_field": category_field, "aggregate": how, "value_field": value_field,
              "features_read": read, "plotted": [{"label": label, "value": round(value, 6)} for label, value in rows]}
    notes = [n for n in (cap_note,
                         f"{skipped} feature(s) had no number in '{value_field}' and are not in the totals." if skipped else None,
                         f"Only the first {MAX_FEATURES:,} features were read." if truncated else None) if n]
    if notes:
        result["notes"] = notes
    return result
