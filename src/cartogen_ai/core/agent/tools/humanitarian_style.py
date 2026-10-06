# -*- coding: utf-8 -*-
"""
Map looks for the humanitarian tools' outputs (styling review, docs/HUMANITARIAN_TOOLS_CATALOGUE.md section "Map styling review").

The review found tools whose result arrived in QGIS's raw defaults -- a random single colour, or an unstretched grey raster --
although what the tool computed has an obvious visual meaning: the mapping-task grid's priority, the road segments a barrier
affects, the survey sample points per stratum, a GDACS alert level, a before/after difference. This module gives those layers a
look that carries that meaning. The palettes and the ordering rules are pure and unit tested offline; the QGIS half is covered by
tests/test_humanitarian_style_live.py, written without a local QGIS (its first execution is CI). Everything is best-effort
cosmetics: a styling failure returns False and never turns a successful analysis into an error, and a user's own layers are not
restyled (only layers these tools create).
"""
import math

try:
    from qgis.core import (QgsCategorizedSymbolRenderer, QgsColorRampShader, QgsFillSymbol, QgsGraduatedSymbolRenderer, QgsLineSymbol,
                           QgsMarkerSymbol, QgsRasterShader, QgsRendererCategory, QgsRendererRange, QgsRuleBasedRenderer,
                           QgsSingleBandPseudoColorRenderer, QgsSingleSymbolRenderer, QgsWkbTypes)
    from qgis.PyQt.QtGui import QColor
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# Priority runs dark (map first) to pale; an unranked task is a neutral grey outline.
PRIORITY_COLORS = {"High": "#b2182b", "Medium": "#ef8a62", "Low": "#fddbc7"}
UNRANKED_COLOR = "#d9d9d9"
# GDACS's own Green / Orange / Red alert levels.
ALERT_COLORS = {"Red": "#d7191c", "Orange": "#fdae61", "Green": "#1a9641"}
BARRIER_COLORS = {"block": "#d7191c", "penalise": "#f58231"}
# Qualitative palette for strata / event categories (colour-blind-aware ordering, cycled).
QUALITATIVE = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d", "#1f78b4", "#666666", "#b15928"]
FIRE_COLOR = "#e8590c"
LABEL_TASK_LIMIT = 150            # above this the task-id labels are a cloud


# ---------------------------------------------------------------- pure --

def qualitative_colors(values):
    """{value: colour} for the distinct values, in sorted order, cycling the palette. Pure and deterministic, so a re-run gives the
    same colours."""
    distinct = sorted({str(v) for v in values if v is not None and str(v) != ""})
    return {v: QUALITATIVE[i % len(QUALITATIVE)] for i, v in enumerate(distinct)}


def priority_categories(values):
    """[(value, colour, label)] for the priority values present, High -> Low, then 'unranked'. Pure."""
    present = {v for v in values if v in PRIORITY_COLORS}
    out = [(k, PRIORITY_COLORS[k], k) for k in ("High", "Medium", "Low") if k in present]
    if any(v is None or str(v) == "" for v in values):
        out.append(("", UNRANKED_COLOR, "unranked"))
    return out


def alert_categories(values):
    """[(value, colour, label)] for GDACS alert levels present, Red -> Green; unknown levels fall to grey. Pure."""
    present = {str(v) for v in values if v is not None and str(v) != ""}
    out = [(k, ALERT_COLORS[k], k) for k in ("Red", "Orange", "Green") if k in present]
    out += [(v, "#808080", v) for v in sorted(present - set(ALERT_COLORS))]
    return out


def diverging_stops(vmin, vmax):
    """[(value, (r,g,b,a), label)] for a before/after difference: symmetric about zero so equal gains and losses get equal
    colour strength, blue = decrease, red = increase, zero fully transparent. Pure. A flat or non-numeric range falls back to
    +/-1."""
    try:
        m = max(abs(float(vmin)), abs(float(vmax)))
    except (TypeError, ValueError):
        m = 0.0
    if not m > 0:
        m = 1.0
    colours = [(-1.0, (33, 102, 172, 255)), (-0.5, (146, 197, 222, 235)), (-0.02, (247, 247, 247, 120)),
               (0.0, (247, 247, 247, 0)), (0.02, (247, 247, 247, 120)), (0.5, (244, 165, 130, 235)), (1.0, (178, 24, 43, 255))]
    return [(f * m, rgba, f"{f * m:+.3g}" if f else "0") for f, rgba in colours]



# --- looks for analysis results written into a layer's fields (HX1) -----------------------------------------------------------
# Severity runs yellow -> dark red (one hue family, light to dark = low to high need). The classes are the ones calculate_severity_index
# uses (equal intervals of the 0-1 score), so a unit's colour and its reported class always agree. People-in-need and exposure are counts:
# different hues (purple, brown) so they are never read as severity.
SEVERITY_COLORS = ["#ffffb2", "#fecc5c", "#fd8d3c", "#e31a1c", "#800026"]
PIN_COLORS = ["#f2f0f7", "#cbc9e2", "#9e9ac8", "#756bb1", "#54278f"]
EXPOSURE_COLORS = ["#feedde", "#fdbe85", "#fd8d3c", "#d94701", "#7f2704"]
GAP_COLORS = {"gap": "#b2182b", "covered": "#2166ac", "unmatched": "#969696"}
GAP_LABELS = {"gap": "Gap: high need, low presence", "covered": "Covered", "unmatched": "Unmatched (no presence data)"}
NOT_ASSESSED_COLOR = "#f0f0f0"
RANK_COLORS = ["#7f0000", "#fc8d59", "#fee8c8"]
ALLOCATION_COLORS = ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"]       # green: an amount of money, not a level of need
LOOKS = ("severity", "people_in_need", "exposure", "allocation", "presence_gap", "rank",
         "jiaf_severity", "jiaf_review_pin", "jiaf_review_severity", "jiaf_count")

# JIAF 2 looks. Severity is a PHASE 1-5 (not the 0-1 score of the severity look), and a unit with no phase must stay visible as
# "not assessed" -- a gap in the map would read as "fine". Review status says which units still wait for the group's decision.
JIAF_PHASES = [(1, "#ffffb2", "1 None / minimal"), (2, "#fecc5c", "2 Stress"), (3, "#fd8d3c", "3 Severe"), (4, "#e31a1c", "4 Extreme"),
               (5, "#800026", "5 Catastrophic")]
JIAF_NOT_ASSESSED = ("#d9d9d9", "No severity (not assessed or incomplete sector coverage)")
JIAF_REVIEW = {
    "jiaf_review_pin": [(0, "#9ecae1", "No flag"), (1, "#c7e9c0", "Flags closed in bulk"), (2, "#31a354", "Decided by the group"),
                        (3, "#d7191c", "Pending: flagged, needs the group")],
    "jiaf_review_severity": [(0, "#d9d9d9", "No severity data"), (1, "#9ecae1", "Preliminary accepted"), (2, "#31a354", "Decided by the group"),
                             (3, "#d7191c", "Pending: flagged, needs the group"), (4, "#969696", "Incomplete sector coverage")],
}
# The result field each JIAF tool writes -> the look that draws it.
JIAF_FIELD_LOOKS = {
    "jf_pre_pin": "people_in_need", "jf_fin_pin": "people_in_need", "jf_pre_sev": "jiaf_severity", "jf_fin_sev": "jiaf_severity",
    "jf_npinfl": "jiaf_count", "jf_nsevfl": "jiaf_count", "jf_nsec40": "jiaf_count", "jf_nsev45": "jiaf_count",
    "jf_pin_st": "jiaf_review_pin", "jf_sev_st": "jiaf_review_severity",
}


def _quoted(field):
    return '"' + str(field).replace('"', '""') + '"'


def jiaf_phase_rules(field):
    """[(label, filter expression, colour)] for severity phases 1-5 of a numeric field, then the not-assessed catch-all (expression 'ELSE'). Pure.
    Phases are integers stored as doubles, so each rule covers phase +-0.5."""
    q = _quoted(field)
    rules = [(label, f"{q} >= {n - 0.5} AND {q} < {n + 0.5}", colour) for n, colour, label in JIAF_PHASES]
    rules.append((JIAF_NOT_ASSESSED[1], "ELSE", JIAF_NOT_ASSESSED[0]))
    return rules


def jiaf_review_rules(look, field):
    """[(label, filter expression, colour)] for a review-status field, then an 'ELSE' for a unit with no status. Pure."""
    q = _quoted(field)
    rules = [(label, f"{q} >= {n - 0.5} AND {q} < {n + 0.5}", colour) for n, colour, label in JIAF_REVIEW[look]]
    rules.append(("Not assessed", "ELSE", "#f0f0f0"))
    return rules


def jiaf_look_hints(layer_name, fields_written):
    """The apply_humanitarian_look calls that draw the JIAF fields a tool just wrote (one per field with a look). Pure."""
    out = []
    for f in fields_written or []:
        look = JIAF_FIELD_LOOKS.get(f)
        hint = look_hint(layer_name, look, f) if look else None
        if hint:
            out.append(hint)
    return out


def look_hint(layer_name, look, field, **extra):
    """The apply_humanitarian_look call an analysis result suggests for the field it just wrote, or None when there is no field. Pure.
    The tools never restyle a layer they did not create; they hand the model this instead, to offer or to run when asked."""
    if not layer_name or not field:
        return None
    args = {"layer_name": layer_name, "look": look, "field": field}
    args.update({k: v for k, v in extra.items() if v is not None})
    return {"tool": "apply_humanitarian_look", "args": args,
            "note": "The result field is written but the layer is still in default colours. Offer to show it on the map by calling this tool "
                    "with these arguments, or call it if the user asked to see the result on the map."}


def severity_ranges():
    """[(low, high, colour, label)] for the five equal-interval severity classes of a 0-1 composite score. Pure."""
    edges = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    labels = ["1 (score < 0.2)", "2 (0.2 to < 0.4)", "3 (0.4 to < 0.6)", "4 (0.6 to < 0.8)", "5 (0.8 or more)"]
    out = []
    for i, colour in enumerate(SEVERITY_COLORS):
        # QGIS ranges include both ends, so an exact 0.2 would land in class 1 while calculate_severity_index calls it class 2
        # (int(score * 5) + 1). The upper end of every class but the last is the float just below the next class's start.
        high = math.nextafter(edges[i + 1], 0.0) if i < 4 else 1.0000001
        out.append((edges[i], high, colour, labels[i]))
    return out


def _nice(x):
    """x rounded to two significant digits, so class limits read as 1,200 and not 1,187. Pure."""
    if x == 0:
        return 0
    from math import floor, log10
    digits = 1 - int(floor(log10(abs(x))))
    return round(x, digits) if digits > 0 else int(round(x, digits))


def count_ranges(values, colours, classes=5):
    """[(low, high, colour, label)] for a count field (people, exposed population). Pure.

    Classes are quantile-based on the positive values, with limits rounded to two significant digits, because counts are heavy-tailed and
    equal intervals would put almost every unit in the first class. Zero (or no positive value) gets its own palest class so a real zero
    is not confused with a missing value; missing values are not drawn. Returns [] when there are no numeric values."""
    nums = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f and f >= 0:
            nums.append(f)
    if not nums:
        return []
    positives = sorted(x for x in nums if x > 0)
    out = []
    if len(positives) < len(nums):
        out.append((0.0, 0.0, "#ffffff", "0"))
    if not positives:
        return out
    k = max(1, min(classes, len(set(positives))))
    cuts = [positives[0]]
    for i in range(1, k):
        cuts.append(_nice(positives[min(len(positives) - 1, int(len(positives) * i / k))]))
    cuts.append(positives[-1])
    # strictly increasing limits only
    edges = [cuts[0]]
    for c in cuts[1:]:
        if c > edges[-1]:
            edges.append(c)
    if len(edges) < 2:
        edges.append(edges[0] + 1)
    n = len(edges) - 1
    palette = [colours[-1]] if n == 1 else [colours[round(i * (len(colours) - 1) / (n - 1))] for i in range(n)]
    for i in range(len(edges) - 1):
        low, high = edges[i], edges[i + 1]
        last = i == len(edges) - 2
        label = f"{low:,.0f} to {high:,.0f}" if last else f"{low:,.0f} to < {high:,.0f}"
        out.append((low, high + (0.5 if last else 0.0), palette[i], label))
    return out


def presence_gap_categories(values):
    """[(value, colour, label)] for presence-gap status values present, gap first, plus 'not assessed' for empties. Pure."""
    present = {v for v in values if v in GAP_COLORS}
    out = [(k, GAP_COLORS[k], GAP_LABELS[k]) for k in ("gap", "covered", "unmatched") if k in present]
    if any(v is None or str(v) == "" for v in values):
        out.append(("", NOT_ASSESSED_COLOR, "Not assessed (below the high-severity classes)"))
    return out


def rank_ranges(max_rank, top_k):
    """[(low, high, colour, label)] for a rank field (1 = highest priority): the top_k units dark, the next top_k mid, the rest pale. Pure.
    Boundaries sit between integers so tied (shared) ranks stay in the class of their rank."""
    try:
        k = max(1, int(top_k))
    except (TypeError, ValueError):
        k = 10
    try:
        top = max(float(max_rank), 1.0)
    except (TypeError, ValueError):
        top = float(k)
    out = [(0.5, k + 0.5, RANK_COLORS[0], f"Rank 1 to {k}")]
    if top > k:
        out.append((k + 0.5, 2 * k + 0.5, RANK_COLORS[1], f"Rank {k + 1} to {2 * k}"))
    if top > 2 * k:
        out.append((2 * k + 0.5, top + 0.5, RANK_COLORS[2], f"Rank {2 * k + 1} and below"))
    return out


# --- looks for layers the tools create themselves (HX1b) ------------------------------------------------------------------------
# Reference layers (buildings, roads) are drawn quiet so the analysis on top of them is what the eye finds.
FOOTPRINT_STYLE = {"color": "#8d99ae", "outline": "#4a4e69", "outline_width": "0.12", "opacity": 0.7}
DETECTION_CONFIDENCE_COLORS = ["#a8dadc", "#457b9d", "#1d3557"]
DETECTION_CONFIDENCE_EDGES = [0.0, 0.6, 0.8, 1.0]
# OSM highway class -> (group, colour, width in mm). Dark and thick = through roads; pale and thin = local access.
ROAD_GROUPS = [
    ("Major roads", "#343a40", 1.4, ("motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link")),
    ("Secondary roads", "#6c757d", 0.9, ("secondary", "tertiary", "secondary_link", "tertiary_link")),
    ("Local roads", "#adb5bd", 0.5, ("residential", "unclassified", "living_street", "service", "road")),
    ("Tracks and paths", "#ced4da", 0.4, ("track", "path", "footway", "cycleway", "bridleway", "steps", "pedestrian")),
]


def road_rules(highway_field="highway"):
    """[(label, filter expression, colour, width_mm)] for an OSM road layer, one rule per group plus a catch-all 'Other'. Pure."""
    rules = []
    for label, colour, width, values in ROAD_GROUPS:
        quoted = ", ".join("'" + v + "'" for v in values)
        rules.append((label, f'"{highway_field}" IN ({quoted})', colour, width))
    return rules


def detection_ranges():
    """[(low, high, colour, label)] for model-confidence bands of detected features. Pure. Confidence is a score from the model, not a
    probability that the object is real; the labels say 'confidence' and nothing stronger."""
    edges = DETECTION_CONFIDENCE_EDGES
    labels = ["Confidence below 0.6", "Confidence 0.6 to < 0.8", "Confidence 0.8 or more"]
    out = []
    for i, colour in enumerate(DETECTION_CONFIDENCE_COLORS):
        high = math.nextafter(edges[i + 1], 0.0) if i < 2 else 1.0000001
        out.append((edges[i], high, colour, labels[i]))
    return out

# ---------------------------------------------------------------- QGIS --

def _categorized(layer, field, categories, symbol_factory, default_colour=None):
    """Categorized renderer; with default_colour an 'other' category catches values that appear later (a hazard layer is
    refreshed in place, so a new alert level or event category must not vanish from the map)."""
    cats = [QgsRendererCategory(value, symbol_factory(colour), label) for value, colour, label in categories]
    if default_colour:
        cats.append(QgsRendererCategory("", symbol_factory(default_colour), "other"))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, cats))
    layer.triggerRepaint()
    return True


def _values(layer, field):
    return [f[field] for f in layer.getFeatures()]


def style_task_grid(layer):
    """Mapping-task polygons coloured by priority (High dark -> Low pale) with task ids as labels on small grids. Returns True when
    applied. Without any priority values the tasks get one neutral outline so an unranked grid does not look ranked."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        def fill(colour):
            return QgsFillSymbol.createSimple({"color": colour, "outline_color": "#ffffff", "outline_width": "0.3"})
        cats = priority_categories(_values(layer, "priority"))
        if not any(c[0] for c in cats):
            layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
                {"color": "255,255,255,0", "outline_color": "#555555", "outline_width": "0.4"})))
            layer.triggerRepaint()
        else:
            _categorized(layer, "priority", cats, fill)
        if layer.featureCount() <= LABEL_TASK_LIMIT:
            from .vector_tools import apply_labels
            apply_labels(layer.name(), target_field="task_id", font_size=8)
        return True
    except Exception:
        return False


def style_barrier_segments(layer, mode="block"):
    """Road segments a barrier affects: thick red (blocked) or orange (slowed) line. Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        symbol = QgsLineSymbol.createSimple({"color": BARRIER_COLORS.get(mode, BARRIER_COLORS["block"]), "width": "1.0",
                                              "capstyle": "round", "joinstyle": "round"})
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()
        return True
    except Exception:
        return False


def style_sample_points(layer, field="stratum"):
    """Survey sample points: small circles, one colour per stratum. Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        colours = qualitative_colors(_values(layer, field))

        def marker(colour):
            return QgsMarkerSymbol.createSimple({"name": "circle", "color": colour, "outline_color": "#ffffff",
                                                  "outline_width": "0.3", "size": "2.2"})
        return _categorized(layer, field, [(v, c, v) for v, c in colours.items()], marker)
    except Exception:
        return False


def style_hazard_layer(layer, kind):
    """kind 'gdacs' (by alert level), 'eonet' (by event category) or 'fires' (one small orange dot). Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        def marker(colour, size="3.2"):
            return QgsMarkerSymbol.createSimple({"name": "circle", "color": colour, "outline_color": "#333333",
                                                  "outline_width": "0.3", "size": size})
        if kind == "gdacs":
            fixed = [(k, c, k) for k, c in ALERT_COLORS.items()]       # always all three, so a later Red alert is not invisible
            return _categorized(layer, "alert_level", fixed, lambda c: marker(c, "4.2"), default_colour="#808080")
        if kind == "eonet":
            colours = qualitative_colors(_values(layer, "category"))
            return _categorized(layer, "category", [(v, c, v) for v, c in colours.items()], marker, default_colour="#808080")
        if kind == "fires":
            layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": FIRE_COLOR + "cc", "outline_color": "#7f2704", "outline_width": "0.2", "size": "2.0"})))
            layer.triggerRepaint()
            return True
        return False
    except Exception:
        return False


def style_diverging_raster(layer, band=1):
    """Before/after difference raster: blue (decrease) - transparent zero - red (increase), symmetric about zero. Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        from .raster_tools import _COLOR_RAMP_SHADER_ITEM, _RAMP_INTERPOLATED
        if _COLOR_RAMP_SHADER_ITEM is None or _RAMP_INTERPOLATED is None:
            return False
        provider = layer.dataProvider()
        stats = provider.bandStatistics(band)
        stops = diverging_stops(stats.minimumValue, stats.maximumValue)
        shader = QgsColorRampShader(stops[0][0], stops[-1][0])
        shader.setColorRampType(_RAMP_INTERPOLATED)
        shader.setColorRampItemList([_COLOR_RAMP_SHADER_ITEM(v, QColor(*rgba), label) for v, rgba, label in stops])
        from .output_style import _set_unit_legend
        _set_unit_legend(shader, {"min": "decrease", "max": "increase"})
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(shader)
        renderer = QgsSingleBandPseudoColorRenderer(provider, band, raster_shader)
        from .output_style import set_renderer_range
        set_renderer_range(renderer, stops[0][0], stops[-1][0])
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        from .output_style import send_under_vectors
        send_under_vectors(layer)
        return True
    except Exception:
        return False


# --- QGIS: looks for result fields (HX1) ---------------------------------------------------------------------------------------

def _symbol(layer, colour):
    kind = layer.geometryType()
    if kind == QgsWkbTypes.GeometryType.PolygonGeometry:
        return QgsFillSymbol.createSimple({"color": colour, "outline_color": "#ffffff", "outline_width": "0.26"})
    if kind == QgsWkbTypes.GeometryType.LineGeometry:
        return QgsLineSymbol.createSimple({"color": colour, "width": "0.9", "capstyle": "round"})
    return QgsMarkerSymbol.createSimple({"name": "circle", "color": colour, "outline_color": "#333333", "outline_width": "0.3", "size": "3.2"})


def _graduated(layer, field, ranges):
    items = [QgsRendererRange(low, high, _symbol(layer, colour), label) for low, high, colour, label in ranges]
    layer.setRenderer(QgsGraduatedSymbolRenderer(field, items))
    layer.setCustomProperty("cartogen_look", field)
    layer.triggerRepaint()
    return [label for _l, _h, _c, label in ranges]


def _rule_based(layer, rules):
    """Rule-based renderer from [(label, expression, colour)]; an 'ELSE' expression becomes the catch-all so units with no value stay drawn."""
    first = rules[0]
    renderer = QgsRuleBasedRenderer(_symbol(layer, first[2]))
    root = renderer.rootRule()
    first_rule = root.children()[0]
    first_rule.setFilterExpression(first[1])
    first_rule.setLabel(first[0])
    for label, expression, colour in rules[1:]:
        rule = first_rule.clone()
        rule.setSymbol(_symbol(layer, colour))
        rule.setFilterExpression(expression)
        rule.setLabel(label)
        if expression == "ELSE":
            rule.setIsElse(True)
        root.appendChild(rule)
    layer.setRenderer(renderer)
    layer.triggerRepaint()
    return [label for label, _e, _c in rules]


def style_result_field(layer, look, field, top_k=None):
    """Apply one of LOOKS to `field` of `layer`. Returns {"classes": [labels], "notes": [..]} on success or {"error": text}. Only the
    renderer changes; nothing is written to the layer. Called by apply_humanitarian_look when the user asks for it."""
    if not QGIS_AVAILABLE or layer is None:
        return {"error": "QGIS not available"}
    if look not in LOOKS:
        return {"error": f"look must be one of {list(LOOKS)}."}
    if layer.fields().indexOf(field) < 0:
        return {"error": f"Field '{field}' not found on '{layer.name()}'."}
    try:
        values = _values(layer, field)
        notes = []
        if look == "presence_gap":
            cats = presence_gap_categories(values)
            if not cats:
                return {"error": f"'{field}' holds no presence-gap status values (gap / covered / unmatched)."}

            def symbol(colour):
                return _symbol(layer, colour)
            _categorized(layer, field, cats, symbol)
            layer.setCustomProperty("cartogen_look", look)
            return {"classes": [label for _v, _c, label in cats], "notes": notes}
        if look in ("jiaf_severity", "jiaf_review_pin", "jiaf_review_severity"):
            nums = [float(v) for v in values if isinstance(v, (int, float))]
            if not nums:
                return {"error": f"'{field}' holds no numeric values."}
            rules = jiaf_phase_rules(field) if look == "jiaf_severity" else jiaf_review_rules(look, field)
            if look == "jiaf_severity" and (max(nums) > 5.5 or min(nums) < 0.5):
                notes.append(f"'{field}' has values outside phases 1-5 ({min(nums):g} to {max(nums):g}); those units are drawn as not assessed.")
            classes = _rule_based(layer, rules)
            layer.setCustomProperty("cartogen_look", look)
            notes.append("Units with no value are drawn grey as not assessed, never as a low phase.")
            return {"classes": classes, "notes": notes}
        if look == "severity":
            nums = [float(v) for v in values if isinstance(v, (int, float))]
            if not nums:
                return {"error": f"'{field}' holds no numeric values."}
            if max(nums) > 1.0 + 1e-9 or min(nums) < -1e-9:
                notes.append(f"'{field}' has values outside 0-1 ({min(nums):g} to {max(nums):g}); this look expects the 0-1 composite "
                             "score, so those units fall outside the five classes and are not drawn.")
            ranges = severity_ranges()
        elif look in ("people_in_need", "exposure", "allocation", "jiaf_count"):
            palette = {"people_in_need": PIN_COLORS, "exposure": EXPOSURE_COLORS, "allocation": ALLOCATION_COLORS,
                       "jiaf_count": EXPOSURE_COLORS}[look]
            ranges = count_ranges(values, palette)
            if not ranges:
                return {"error": f"'{field}' holds no numeric values."}
        else:  # rank
            nums = [float(v) for v in values if isinstance(v, (int, float))]
            if not nums:
                return {"error": f"'{field}' holds no numeric values."}
            ranges = rank_ranges(max(nums), top_k if top_k else 10)
        notes.append("Units with no value in the field are not drawn.")
        classes = _graduated(layer, field, ranges)
        layer.setCustomProperty("cartogen_look", look)
        return {"classes": classes, "notes": notes}
    except Exception as e:
        return {"error": f"Could not apply the {look} look: {e}"}


# --- QGIS: looks for layers the tools create (HX1b) ----------------------------------------------------------------------------

def style_footprints(layer):
    """Building footprints: a quiet grey translucent fill with a thin dark edge, so they sit behind an analysis. True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
            {"color": FOOTPRINT_STYLE["color"], "outline_color": FOOTPRINT_STYLE["outline"],
             "outline_width": FOOTPRINT_STYLE["outline_width"]})))
        layer.setOpacity(FOOTPRINT_STYLE["opacity"])
        layer.triggerRepaint()
        return True
    except Exception:
        return False


def style_osm_layer(layer):
    """An OSM extract: roads graded by highway class when the layer is lines with a `highway` field, a pale fill for areas, the
    standard point look for points. Other line layers (waterways, rail) get one neutral line. True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        kind = layer.geometryType()
        if kind == QgsWkbTypes.GeometryType.PolygonGeometry:
            layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
                {"color": "#e9ecef", "outline_color": "#868e96", "outline_width": "0.2"})))
        elif kind == QgsWkbTypes.GeometryType.LineGeometry:
            if layer.fields().indexOf("highway") >= 0:
                return _style_roads(layer)
            layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#495057", "width": "0.6"})))
        else:
            from .output_style import style_points_default
            return style_points_default(layer)
        layer.triggerRepaint()
        return True
    except Exception:
        return False


def _style_roads(layer):
    rules = road_rules()

    def line(colour, width):
        return QgsLineSymbol.createSimple({"color": colour, "width": str(width), "capstyle": "round", "joinstyle": "round"})
    first = rules[0]
    renderer = QgsRuleBasedRenderer(line(first[2], first[3]))
    root = renderer.rootRule()
    first_rule = root.children()[0]
    first_rule.setFilterExpression(first[1])
    first_rule.setLabel(first[0])
    for label, expression, colour, width in rules[1:]:
        rule = first_rule.clone()
        rule.setSymbol(line(colour, width))
        rule.setFilterExpression(expression)
        rule.setLabel(label)
        root.appendChild(rule)
    other = first_rule.clone()
    other.setSymbol(line("#ced4da", 0.4))
    other.setFilterExpression("ELSE")
    other.setLabel("Other")
    other.setIsElse(True)
    root.appendChild(other)
    layer.setRenderer(renderer)
    layer.triggerRepaint()
    return True


def style_detected_features(layer, field="confidence"):
    """Imagery-extraction polygons in three model-confidence bands, translucent so the imagery shows through. True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        if layer.fields().indexOf(field) < 0:
            return False
        _graduated(layer, field, detection_ranges())
        layer.setOpacity(0.75)
        layer.triggerRepaint()
        return True
    except Exception:
        return False
