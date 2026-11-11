"""calculate_health_rates (PLAN-023 R2-4): rates per 100,000, relative risk, standardised ratios and smoothed rates for areas, with a small-number flag.

The arithmetic (crude rate, Byar interval, SMR from caller-supplied expected counts, Marshall's global empirical-Bayes smoothing, the small-number rule) is the pure, hand-checked _health_rates.py; this module reads the layer
and writes a NEW layer. It never edits the input layer, never invents expected counts, and never shows a figure the small-number rule flags in `value_shown` (the field a map should use).

Written without a QGIS install; tests/test_health_rates_tool_live.py is its first execution in CI."""
from . import _health_rates as hr
from ._layer_checks import require_valid_layer
from .registry import register_tool

try:
    from qgis.core import QgsFeature, QgsProject, QgsVectorLayer, QgsWkbTypes
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

MAX_FEATURES = 50_000
NOTE = ("These are crude figures for areas, not adjusted for age or sex, and they say nothing about individuals. Rates for areas with few cases are unstable: `value_shown` is left empty where cases are below "
        "the threshold (or the population is below min_population), so a map built on it does not show them. Smoothed rates pull small areas toward the overall rate and are for mapping, not for reporting an area's true rate.")


def _find_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _read(layer, case_field, population_field, expected_field):
    """(ids, cases, populations, expected or None, problem): refuses, with counts, any feature whose figures cannot be used."""
    ids, cases, pops, expected = [], [], [], []
    bad_cases = bad_pop = bad_expected = 0
    for feature in layer.getFeatures():
        c, p = feature[case_field], feature[population_field]
        if c is None or isinstance(c, bool) or not isinstance(c, (int, float)) or c != c or c < 0 or c != int(c):
            bad_cases += 1
            continue
        if p is None or isinstance(p, bool) or not isinstance(p, (int, float)) or p != p or p <= 0:
            bad_pop += 1
            continue
        if expected_field:
            e = feature[expected_field]
            if e is None or isinstance(e, bool) or not isinstance(e, (int, float)) or e != e or e <= 0:
                bad_expected += 1
                continue
            expected.append(float(e))
        if len(ids) >= MAX_FEATURES:
            return None, None, None, None, f"The layer has more than {MAX_FEATURES:,} features; this tool stops there so QGIS stays responsive. Aggregate it first."
        ids.append(feature.id())
        cases.append(int(c))
        pops.append(float(p))
    problems = []
    if bad_cases:
        problems.append(f"{bad_cases} feature(s) have no whole-number case count in '{case_field}'")
    if bad_pop:
        problems.append(f"{bad_pop} feature(s) have no population above zero in '{population_field}'")
    if bad_expected:
        problems.append(f"{bad_expected} feature(s) have no expected count above zero in '{expected_field}'")
    if problems:
        return None, None, None, None, "; ".join(problems) + ". Fix or remove them first: this tool does not guess a missing figure."
    return ids, cases, pops, (expected if expected_field else None), None


@register_tool(
    "calculate_health_rates",
    "Compute disease or incident RATES for areas from a case count and a population: the crude rate per 100,000 (or per), its 95% interval, the RELATIVE RISK (area rate over the overall rate), the indirectly standardised "
    "ratio SMR (observed over expected, ONLY when you supply an expected-count field: this tool never invents expected counts, so age or sex adjustment must come from you), and a global empirical-Bayes SMOOTHED rate "
    "that steadies small areas. method chooses the headline `value` ('crude', 'smr' or 'eb'). Every area with cases below 5 (min_cases) or a population below min_population gets a small-number flag and an EMPTY "
    "`value_shown`, so a map made from value_shown never shows an unstable figure. Writes a NEW layer; the input is never changed. Needs a whole-number case field and a population field above zero on every area.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"},
        "case_field": {"type": "string", "description": "Whole-number case counts per area."},
        "population_field": {"type": "string", "description": "Population at risk per area (above zero)."},
        "method": {"type": "string", "enum": list(hr.METHODS), "description": "crude (default), smr (needs expected_field) or eb (smoothed)."},
        "expected_field": {"type": "string", "description": "Expected case counts you computed (for example by age and sex standardisation). Required for method='smr'."},
        "per": {"type": "number", "description": "Rate denominator (default 100000)."},
        "min_population": {"type": "number", "description": "Flag areas with a smaller population (default: no population floor)."},
        "min_cases": {"type": "integer", "description": "Flag areas with fewer cases than this (default 5)."},
        "output_layer_name": {"type": "string", "description": "Name of the new layer (default '<layer>_rates')."},
    }, "required": ["layer_name", "case_field", "population_field"]},
    keywords=["rate per 100000", "rate per 100,000", "incidence rate", "disease rate", "crude rate", "relative risk", "standardised mortality ratio", "standardized mortality ratio", "smr", "smoothed rate",
              "empirical bayes", "age standardised", "small number suppression", "cases per population", "attack rate", "mortality rate"],
)
def calculate_health_rates(layer_name, case_field, population_field, method="crude", expected_field=None, per=hr.DEFAULT_PER, min_population=None, min_cases=hr.DEFAULT_MIN_CASES, output_layer_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    method = str(method or "crude").strip().lower()
    if method not in hr.METHODS:
        return {"error": f"Unknown method '{method}'. Choose one of: {', '.join(hr.METHODS)}."}
    if method == "smr" and not expected_field:
        return {"error": "method 'smr' needs expected_field: a field of expected case counts that you computed (for example by age and sex). This tool does not invent expected counts."}
    layer = _find_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not isinstance(layer, QgsVectorLayer):
        return {"error": f"'{layer_name}' is not a vector layer."}
    for label, name in (("case", case_field), ("population", population_field), ("expected", expected_field)):
        if label == "expected" and not expected_field:
            continue
        index = layer.fields().indexOf(name)
        if index < 0:
            return {"error": f"The {label} field '{name}' was not found in '{layer_name}'. Fields: {', '.join(f.name() for f in layer.fields())}."}
        if not layer.fields().at(index).isNumeric():
            return {"error": f"The {label} field '{name}' is not numeric."}
    ids, cases, pops, expected, problem = _read(layer, case_field, population_field, expected_field)
    if problem:
        return {"error": problem}
    try:
        result = hr.analyse(cases, pops, method, expected, per, min_population, min_cases)
    except ValueError as e:
        return {"error": f"calculate_health_rates: {e}"}
    except Exception as e:
        return {"error": f"The rates could not be computed: {e}"}
    name = (output_layer_name or "").strip() or f"{layer_name}_rates"
    written = _write_layer(layer, ids, cases, pops, result, name)
    if isinstance(written, str):
        return {"error": written}
    shown = len(ids) - result["flagged"]
    out = {"success": True, "layer_name": layer_name, "output_layer": written.name(), "method": method, "areas": len(ids), "per": per, "overall_rate": round(result["overall_rate"], 3), "total_cases": sum(cases),
           "total_population": sum(pops), "flagged_small_numbers": result["flagged"], "shown": shown,
           "summary": f"Overall rate {result['overall_rate']:.1f} per {per:g}; {result['flagged']} of {len(ids)} area(s) flagged for small numbers and left out of value_shown.", "notes": [NOTE]}
    if method == "eb":
        out["smoothing"] = "Global empirical Bayes (Marshall 1991)." + (" The areas differ no more than chance explains, so every smoothed rate equals the overall rate." if result["between_variance"] <= 0 else "")
    return out


def _write_layer(layer, ids, cases, pops, result, name):
    """A new memory layer with the source geometry (when there is one) and the rate fields. Returns the layer, or a refusal string."""
    if QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.GeometryType.NullGeometry:
        head = "None?"                                  # a plain table: the memory provider's own spelling, no CRS
    else:
        head = f"{QgsWkbTypes.displayString(layer.wkbType())}?crs={layer.crs().authid()}&"
    out = QgsVectorLayer(f"{head}field=src_id:integer&field=cases:integer&field=population:double&field=rate:double&field=rate_lo:double&field=rate_hi:double"
                         "&field=rel_risk:double&field=expected:double&field=smr:double&field=smr_lo:double&field=smr_hi:double&field=eb_rate:double&field=value:double&field=value_shown:double"
                         "&field=small_number:string", name, "memory")
    try:
        require_valid_layer(out)
    except ValueError as e:
        return str(e)
    by_id = {f.id(): f for f in layer.getFeatures()}

    def rounded(value, places=4):
        return None if value is None else round(value, places)
    feats = []
    for fid, c, p, a in zip(ids, cases, pops, result["areas"], strict=True):
        f = QgsFeature(out.fields())
        geometry = by_id[fid].geometry()
        if geometry is not None and not geometry.isNull():
            f.setGeometry(geometry)
        value = rounded(a["value"])
        f.setAttributes([int(fid), c, p, rounded(a["rate"]), rounded(a["rate_lo"]), rounded(a["rate_hi"]), rounded(a["rel_risk"]), rounded(a["expected"]), rounded(a["smr"]), rounded(a["smr_lo"]),
                         rounded(a["smr_hi"]), rounded(a["eb_rate"]), value, None if a["flag"] else value, a["flag"]])
        feats.append(f)
    out.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(out)
    return out
