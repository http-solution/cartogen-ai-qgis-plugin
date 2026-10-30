"""
run_allowlisted_processing_algorithm -- a Tier 2 slice of the tiered
allow-list model point 19's "larger question" describes
(docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md), sitting between
this codebase's ~150 declarative tools (Tier 1) and execute_pyqgis_script's
denylist sandbox (Tier 4, "LAST RESORT ONLY" per point 1's routing fix).
Runs exactly one Processing algorithm from a hard-coded allow-list
(_processing_allowlist.py, derived from this codebase's own existing
processing.run() call sites) with a caller-supplied flat params dict --
never executes Python code at all, so it has none of execute_pyqgis_script's
attack surface (no eval/exec, no denylist to bypass) while covering the
common "I need one Processing algorithm not wrapped by a dedicated tool"
case that would otherwise reach for raw script execution.

Deliberately does NOT touch or loosen execute_pyqgis_script's existing
sandbox in any way -- this is a new, narrower, safer path offered as a
preference, not a replacement.
"""

import contextlib
from .registry import register_tool
from ... import _background_processing as _bg
from ._processing_allowlist import (ALLOWED_ALGORITHM_IDS, FILE_VECTOR_ALGORITHM_IDS, GRASS_ALGORITHM_IDS, MUTATES_INPUT_ALGORITHM_IDS,
                                    RASTER_OUTPUT_ALGORITHM_IDS, parameter_violation)

try:
    from qgis.core import QgsApplication, QgsMeshLayer, QgsProcessingContext, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes  # noqa: F401 -- QgsMeshLayer is looked up by name in layer_kind_violation
    import processing
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# Any params key matching one of these (case-insensitive) is forced to an
# in-memory/temporary sink regardless of what value is supplied -- this
# tool's whole point is a bounded, in-memory Processing call, not a way to
# write to an arbitrary file path the way a dedicated, audited export tool
# (export_layer, write_provenance_sidecar) already does deliberately and
# visibly. Matches the exact "OUTPUT": "memory:" convention every existing
# processing.run() call in this codebase already uses.
_OUTPUT_KEY_SUFFIXES = ("output", "output_lines")
_SAFE_OUTPUT_VALUE = "memory:"
_SAFE_RASTER_OUTPUT_VALUE = "TEMPORARY_OUTPUT"   # a temporary file: rasters cannot go to "memory:"
MEMORY_COPY_LIMIT = 50000      # PLAN-005 rule R1: a file-backed vector result up to this many features is copied into a memory layer
MAX_STATISTICS = 40            # PLAN-005 rule R3: at most this many plain values from a result dictionary reach the model
MAX_STATISTIC_TEXT = 200


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def unknown_parameters(supplied_keys, defined_names):
    """Sorted parameter names the caller supplied that the algorithm does not define (case-sensitive, as Processing is). Pure.
    GitHub #163 (audit F27): these used to be passed straight through, so a typo was either silently ignored or surfaced as an
    unrelated Processing error."""
    defined = set(defined_names)
    return sorted(k for k in supplied_keys if k not in defined)


def _algorithm_definition(alg_id):
    """(parameter names, destination parameter names, raster destination names, output definitions) of the algorithm in the
    running registry, or None when it cannot be asked (no registry, unknown id). Callers fall back to the old behaviour then."""
    try:
        algorithm = QgsApplication.processingRegistry().algorithmById(alg_id)
        if algorithm is None:
            return None
        params = list(algorithm.parameterDefinitions())
        names = {p.name() for p in params}
        destinations = {p.name() for p in params if p.isDestination()}
        raster_destinations = {p.name() for p in params if p.isDestination() and "raster" in str(p.type()).lower()}
        layer_lists = {p.name() for p in params if str(p.type()) == "multilayer"}
        # a report (HTML) destination is a FILE, not a sink: "memory:" is not valid for it (PLAN-005 wave E1)
        file_destinations = {p.name() for p in params if p.isDestination() and str(p.type()) == "fileDestination"}
        return names, destinations, raster_destinations, list(algorithm.outputDefinitions()), layer_lists, _expected_layer_kinds(params), file_destinations
    except Exception:
        return None


def harvest_outputs(output, definition=None, path_outputs=False):
    """[(key, value)] for every output of a finished algorithm that is a layer or a raster file path, in algorithm order. Pure
    given plain values: a value is a layer when it has setName(), or a raster path when the output is declared a raster. GitHub #163:
    only the key 'OUTPUT' used to be looked at, so multi-output algorithms lost their other results."""
    if not isinstance(output, dict):
        return []
    raster_keys = set()
    vector_keys = set()
    order = list(output.keys())
    if definition is not None:
        raster_keys = {d.name() for d in definition[3] if "raster" in str(d.type()).lower()}
        vector_keys = {d.name() for d in definition[3] if "vector" in str(d.type()).lower()} if path_outputs else set()
        declared = [d.name() for d in definition[3]]
        order = [k for k in declared if k in output] + [k for k in output if k not in declared]
    found = []
    for key in order:
        value = output[key]
        if hasattr(value, "setName") or (isinstance(value, str) and (key in raster_keys or key in vector_keys or (definition is None and key == "OUTPUT")) and value):
            found.append((key, value))
    return found


def scalar_results(output, skip_keys=()):
    """{key: value} for the plain numbers and short texts in an algorithm's result dictionary, in dictionary order. Pure.

    PLAN-005 rule R3: this is all the model learns from a statistics algorithm. A layer, a file path (the keys in `skip_keys`), a list, a dict
    or a long text is never passed on, and at most MAX_STATISTICS values are. The numbers are the algorithm's own (MEAN, COUNT, VOLUME ...)."""
    if not isinstance(output, dict):
        return {}
    found = {}
    for key, value in output.items():
        if key in skip_keys or hasattr(value, "setName") or isinstance(value, (list, tuple, dict, set, bytes)):
            continue
        if isinstance(value, (int, float)) or (isinstance(value, str) and 0 < len(value) <= MAX_STATISTIC_TEXT):   # a bool is an int
            found[str(key)] = value
        if len(found) >= MAX_STATISTICS:
            break
    return found


def _resolve_params(params, raster_output=False, destination_keys=None, raster_keys=None, layer_list_keys=None, temp_file_vectors=False,
                    file_keys=None):
    """Any string value that matches a layer currently loaded in the
    project is resolved to that QgsMapLayer object -- the same shape every
    existing processing.run() call in this codebase already uses
    ("INPUT": a_real_layer_object, not a name string). A string that
    doesn't match a loaded layer is passed through literally (e.g. a
    genuine text param, or "memory:"/"TEMPORARY_OUTPUT" for an output
    key). Non-string values (numbers, bools, lists) pass through
    unchanged -- this tool never accepts nested objects or code, only
    JSON-primitive params, so there's nothing here to execute.

    Confirmed live against QGIS 4.2.2: unlike this codebase's other
    processing.run() call sites, which always build their own OUTPUT key
    explicitly, a caller here may omit it entirely -- and Processing does
    NOT default it, it fails outright ("no value specified for parameter
    OUTPUT"). If the caller's params has neither OUTPUT nor OUTPUT_LINES
    at all, one is added ("OUTPUT": "memory:") -- every allow-listed
    algorithm's real call site (see _processing_allowlist.py) uses one of
    these two keys for its sink, so this default covers the whole list."""
    resolved = {}
    has_output_key = False
    for key, value in params.items():
        key_lower = key.lower()
        if destination_keys is not None:
            is_destination = key in destination_keys
        else:
            is_destination = any(key_lower == suffix or key_lower.endswith("_" + suffix) for suffix in _OUTPUT_KEY_SUFFIXES)
        if is_destination:
            as_raster = (key in raster_keys) if raster_keys is not None else raster_output
            as_file = bool(file_keys) and key in file_keys
            resolved[key] = _SAFE_RASTER_OUTPUT_VALUE if (as_raster or as_file or temp_file_vectors) else _SAFE_OUTPUT_VALUE
            has_output_key = True
            continue
        if isinstance(value, str):
            layer = _find_layer_by_name(value)
            resolved[key] = layer if layer is not None else value
        elif isinstance(value, list) and layer_list_keys and key in layer_list_keys:
            # a multiple-layer parameter (stack of rasters, layers to merge): each name that is a loaded layer becomes that layer. Only
            # for parameters the algorithm declares as layer lists, so a list of FIELD names is never mistaken for layer names.
            resolved[key] = [(_find_layer_by_name(v) or v) if isinstance(v, str) else v for v in value]
        else:
            resolved[key] = value
    if destination_keys is not None:
        # every destination the algorithm defines gets a safe sink, whether or not the caller named it (a second output such as
        # OUTPUT_LINES used to be left unset, so Processing failed or wrote to its own default)
        for key in destination_keys:
            if key not in resolved:
                as_raster = (key in raster_keys) if raster_keys is not None else raster_output
                as_file = bool(file_keys) and key in file_keys
                resolved[key] = _SAFE_RASTER_OUTPUT_VALUE if (as_raster or as_file or temp_file_vectors) else _SAFE_OUTPUT_VALUE
    elif not has_output_key:
        resolved["OUTPUT"] = _SAFE_RASTER_OUTPUT_VALUE if raster_output else _SAFE_OUTPUT_VALUE
    return resolved


def _expected_layer_kinds(parameters):
    """{parameter name: "raster" | "vector" | "mesh"} for the layer parameters whose kind the algorithm fixes. A single-layer parameter says so
    by its type; a layer-list parameter by its layer type. Anything that accepts any layer is left out."""
    kinds = {}
    for p in parameters:
        if p.isDestination():
            continue
        kind = str(p.type())
        if kind == "raster":
            kinds[p.name()] = "raster"
        elif kind in ("source", "vector"):
            kinds[p.name()] = "vector"
        elif kind == "mesh":
            kinds[p.name()] = "mesh"
        elif kind == "multilayer":
            text = str(getattr(p, "layerType", lambda: "")()).lower()
            for word in ("raster", "mesh", "vector"):
                if word in text:
                    kinds[p.name()] = word
                    break
    return kinds


def layer_kind_violation(alg_id, resolved_params, kinds):
    """A message when a parameter that needs one kind of layer was given another (a raster where a table is needed, a vector in a stack of
    rasters), else None. Pure given the layer classes.

    rc45 smoke run: native:reclassifybylayer was given a raster as its reclassification TABLE and native:cellstackpercentile and
    cellstackpercentrankfromvalue ran for 3 to 10 minutes until Stop; CI had already found that vector layers handed to the cell-stack tools
    crash QGIS. Processing's own parameter check lets a wrongly-typed layer through to code that assumes the right type, so the kind is checked
    here before anything runs, for every algorithm and every layer parameter, not only raster stacks."""
    if not kinds:
        return None
    classes = {"raster": globals().get("QgsRasterLayer"), "vector": globals().get("QgsVectorLayer"), "mesh": globals().get("QgsMeshLayer")}
    for key, kind in sorted(kinds.items()):
        value = resolved_params.get(key)
        wanted = classes.get(kind)
        if value is None or wanted is None:
            continue
        for item in (value if isinstance(value, list) else [value]):
            if isinstance(item, (str, wanted)):
                continue                      # an unresolved name or path is Processing's to judge; a layer of the right kind is fine
            other = next((k for k, c in classes.items() if c is not None and k != kind and isinstance(item, c)), None)
            if other and hasattr(item, "name"):
                return (f"parameter '{key}' of '{alg_id}' needs a {kind} layer, but '{item.name()}' is a {other} layer. "
                        "Nothing was run; choose a layer of the right kind.")
    return None


def _raster_list_violation(alg_id, resolved_params, layer_list_keys):
    """A message when a raster-family algorithm is given a layer list that holds something other than raster layers, else None.

    CI run 38883595535 (package D/E probe): handing vector layers to native:cellstackpercentile, cellstackpercentrankfromrasterlayer and
    cellstackpercentrankfromvalue crashed the QGIS process (SIGSEGV) and hung native:rasterrank. Processing's own parameter check lets such a
    list through, and a crash would take the user's whole QGIS session with it, so the list is checked here. Every layer-list parameter in
    the raster family is a stack of rasters."""
    from ._processing_allowlist import RASTER_ALGORITHM_IDS
    # GRASS raster (r.*) and imagery (i.*) algorithms take stacks of rasters too; the vector ones (v.*) take vector lists and are not checked
    raster_stack = alg_id in RASTER_ALGORITHM_IDS or alg_id.startswith(("grass:r.", "grass:i."))
    if not raster_stack or not layer_list_keys:
        return None
    for key in layer_list_keys:
        values = resolved_params.get(key)
        if isinstance(values, list):
            bad = [v if isinstance(v, str) else getattr(v, "name", lambda: "a layer")() for v in values if not isinstance(v, QgsRasterLayer)]
            if bad:
                return (f"parameter '{key}' of '{alg_id}' must list raster layers only; these are not rasters or not loaded: "
                        f"{', '.join(map(str, bad))}.")
    return None


def _check_raster_lists(alg_id, resolved_params, layer_list_keys, kinds=None):
    """Raises ValueError (reported as "'<alg>' failed: ...") when a layer list or a single layer is of the wrong kind; the algorithm is not run."""
    problem = (_raster_list_violation(alg_id, resolved_params, layer_list_keys) or layer_kind_violation(alg_id, resolved_params, kinds)
               or geometry_violation(alg_id, resolved_params, _geometry_limits(alg_id)))
    if problem:
        raise ValueError(problem)


_GEOMETRY_WORDS = {"vectorpoint": "Point", "vectorline": "Line", "vectorpolygon": "Polygon"}
_GEOMETRY_CODES = {0: "Point", 1: "Line", 2: "Polygon"}      # QgsProcessing::SourceType: TypeVectorPoint, TypeVectorLine, TypeVectorPolygon


def _source_geometry(data_type):
    """"Point", "Line" or "Polygon" for one declared source type, or None for anything else (any geometry, a table, a raster). QGIS 4.2.2 CI
    returned plain integers from dataTypes() (1 for lines), so integers are read as well as named enums."""
    name = getattr(data_type, "name", None)
    if isinstance(name, str):
        return _GEOMETRY_WORDS.get(name.lower().replace("_", ""))
    with contextlib.suppress(TypeError, ValueError):
        return _GEOMETRY_CODES.get(int(data_type))
    return None


def _geometry_limits(alg_id):
    """{parameter name: {"Point"/"Line"/"Polygon"}} for the source parameters that accept only some geometry types, else {}. A parameter that
    also accepts any geometry or a table is left out."""
    limits = {}
    if not alg_id.startswith("qgis:"):
        # CI run 40045990390: with every id checked, the all-algorithms probes failed for 11 GRASS and 3 native algorithms that ran fine on
        # other geometry types (GRASS imports any vector, and these native ones convert). Only the Python-implemented qgis: algorithms were seen
        # to die on the wrong type (rc48 B3), so only those are checked.
        return limits
    with contextlib.suppress(Exception):
        algorithm = QgsApplication.processingRegistry().algorithmById(alg_id)
        for p in algorithm.parameterDefinitions():
            if p.isDestination() or str(p.type()) != "source":
                continue
            kinds = [_source_geometry(t) for t in p.dataTypes()]
            if kinds and all(kinds):
                limits[p.name()] = set(kinds)
    return limits


def geometry_violation(alg_id, resolved_params, limits):
    """A message when a layer parameter that takes only some geometry types was given another (a polygon layer where lines are needed), else
    None. rc48 B3: qgis:linestopolygons run on a polygon layer died with a raw "setExteriorRing unexpected type QgsPolygon" TypeError, and the
    model then spent 28 calls trying other algorithms; a clear refusal on the first call lets it pick the right one. Pure given the layers."""
    if not limits:
        return None
    for key, allowed in sorted(limits.items()):
        value = resolved_params.get(key)
        if not hasattr(value, "geometryType") or not hasattr(value, "name"):
            continue                               # a name or path is Processing's to judge
        actual = None
        with contextlib.suppress(Exception):
            actual = QgsWkbTypes.geometryDisplayString(value.geometryType())
        if actual in ("Point", "Line", "Polygon") and actual not in allowed:
            wanted = " or ".join(sorted(a.lower() for a in allowed))
            return (f"parameter '{key}' of '{alg_id}' needs a {wanted} layer, but '{value.name()}' is a {actual.lower()} layer. Nothing was run; "
                    f"choose a {wanted} layer, or another algorithm for a {actual.lower()} layer.")
    return None


# rc45 smoke run: five native algorithms sat at "working on the road network" for 3 to 10 minutes on tiny test data before the tester pressed
# Stop. A run that long on a person's data is a hang, not an analysis; this bounds the wait. Large real analyses that need longer can use a
# dedicated tool (network analysis has no limit).
MAX_RUNTIME_S = 300.0

# Free-form-expression algorithms are not approved (they evaluate text as code); each has a dedicated, screened tool.
_DEDICATED_INSTEAD = {"gdal:rastercalculator": "raster_calculator", "qgis:rastercalc": "raster_calculator", "native:rastercalc": "raster_calculator",
                      "native:rastercalculator": "raster_calculator"}


def _not_approved_error(alg_id):
    """The refusal for an id that is not on the approved list, or None when it is approved."""
    if alg_id in ALLOWED_ALGORITHM_IDS:
        return None
    if alg_id in _DEDICATED_INSTEAD:
        # rc45 smoke run: asked for dem > 100 as a new layer, the model tried gdal:rastercalculator, was told it is not approved, and sent the
        # user to the QGIS menu, although the checked raster_calculator tool does exactly this.
        return {"error": f"'{alg_id}' is not approved; use the dedicated tool {_DEDICATED_INSTEAD[alg_id]} instead.",
                "use_tool": _DEDICATED_INSTEAD[alg_id]}
    return {
        "error": f"'{alg_id}' is not on the allowed algorithm list. Call find_processing_algorithm with a few words to search the "
                 f"{len(ALLOWED_ALGORITHM_IDS)} approved algorithms. "
                 "Use execute_pyqgis_script as a last resort if genuinely nothing else covers this."
    }


def _run_allowlisted(alg_id, resolved_params):
    """processing.run(alg_id, params), off the GUI thread when that is safe (rc20 audit A14, #221).

    An algorithm that changes the user's own layer (a selection) stays synchronous: edits to a project layer are only safe on the
    GUI thread, and so do Python-implemented algorithms (gdal:, qgis:), which crashed CI on a worker thread. A native algorithm that
    creates new data goes through QGIS's task runner, so a long one no longer shows "Not Responding" and Stop works. Outside a real GUI thread (tests, the kill-switch setting) this is exactly processing.run."""
    if alg_id in MUTATES_INPUT_ALGORITHM_IDS:
        return processing.run(alg_id, resolved_params)
    if not _bg.is_thread_safe_algorithm(alg_id) or not _bg.can_run_in_background():
        return _bg.run_synchronously_with_repaint(
            alg_id, lambda feedback: processing.run(alg_id, resolved_params) if feedback is None
            else processing.run(alg_id, resolved_params, feedback=feedback))
    context = QgsProcessingContext()
    context.setProject(QgsProject.instance())
    return _bg.run_algorithm(alg_id, resolved_params, context,
                             fallback=lambda a, p, context=None: processing.run(a, p), label=alg_id.split(":")[-1],
                             max_runtime_s=MAX_RUNTIME_S)


# The registration decorator must sit directly on run_allowlisted_processing_algorithm. PR #249 (rc24) put _run_allowlisted between
# the two, so the registry held the helper and every model call failed with "_run_allowlisted() got an unexpected keyword argument
# 'params'" (found in the 2026-10-13 hand test, row RC37-F4); direct calls from tests still worked, which hid it.
def centre_point_of_interest(alg_id, params, extent):
    """(params, note): r.sunmask.datetime's east and north (the point whose sun position is used; both required, no default) put back to the centre of
    the elevation layer when they are missing, not numbers, or outside its extent. rc48 B15 (API trace, 2026-10-23): the model passed east=2.0,
    north=2.0 for a DEM in metres and GRASS answered "Incorrect parameter value for east" on both runs. `extent` is (xmin, ymin, xmax, ymax) or
    None. r.sunmask.position is left alone: its two coordinates are optional there. Pure."""
    if alg_id != "grass:r.sunmask.datetime" or extent is None or not isinstance(params, dict):
        return params, None
    try:
        east, north = float(params.get("east")), float(params.get("north"))
        if extent[0] <= east <= extent[2] and extent[1] <= north <= extent[3]:
            return params, None
    except (TypeError, ValueError):
        pass
    fixed = dict(params)
    fixed["east"] = str(round((extent[0] + extent[2]) / 2, 6))
    fixed["north"] = str(round((extent[1] + extent[3]) / 2, 6))
    return fixed, (f"east and north were missing or outside the elevation layer, so the centre of the layer ({fixed['east']}, {fixed['north']}) "
                   f"was used as the point whose sun position is calculated.")


_RADIUS_HINT = {"grass:r.circle": " r.circle only fills cells between min and max (metres); without max the rings are not drawn, so pass max (and min)."}


def single_value_message(alg_id, value):
    """The warning for a raster whose cells all hold one value. rc48 B7: grass:r.circle without `max` ran fine but wrote a one-value raster, the
    styling tools then failed with "no data range", and the model re-ran the same algorithm until the loop guard stopped it. Saying so in the
    algorithm's own reply sends it back to the parameters instead. Pure."""
    return (f"The output raster holds a single value ({value:g}) in every cell, so it cannot be coloured or classified. Check the inputs and the "
            f"required size or distance parameters before running it again with the same arguments." + _RADIUS_HINT.get(alg_id, ""))


def _output_report(layer, alg_id):
    """feature_count and, for an empty vector or a one-value raster, a warning. The raster check samples the band (not every cell)."""
    if hasattr(layer, "featureCount"):
        count = layer.featureCount()
        out = {"feature_count": count}
        if count == 0:
            out["warning"] = "The output layer has 0 features -- check the inputs before treating this as a real empty result."
        return out
    with contextlib.suppress(Exception):
        from qgis.core import Qgis
        kind = Qgis.RasterBandStatistic
        stats = layer.dataProvider().bandStatistics(1, kind.Min | kind.Max, layer.extent(), 100000)
        if stats.minimumValue == stats.maximumValue:
            return {"warning": single_value_message(alg_id, stats.minimumValue)}
    return {}


def _with_sun_point(alg_id, params):
    """centre_point_of_interest for the elevation layer named in params; (params, None) when the layer cannot be found."""
    with contextlib.suppress(Exception):
        elevation = _find_layer_by_name(params.get("elevation")) if alg_id == "grass:r.sunmask.datetime" else None
        if elevation is not None:
            box = elevation.extent()
            return centre_point_of_interest(alg_id, params, (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()))
    return params, None


@register_tool(
    "run_allowlisted_processing_algorithm",
    "Runs one QGIS Processing algorithm from a fixed, pre-approved list -- prefer this over "
    "execute_pyqgis_script when the task is achievable via a single Processing algorithm that "
    "isn't already covered by a dedicated tool. It calls only the named, pre-approved algorithm with "
    "the given parameters and never accepts a FORMULA or EXTRA (raw backend arguments) parameter; "
    "algorithms that evaluate free-form expressions as code (such as the GDAL raster calculator) are "
    "not on the list. Only algorithms already used elsewhere in this codebase "
    "are allowed -- an unlisted algorithm id is rejected outright, not run. Output is always kept "
    "in-memory as a new project layer (auto-named), never written to a file path -- use a "
    "dedicated export tool (export_layer, export_to_csv) afterward if a file is actually needed. "
    "Don't specify the output (destination) parameters yourself -- they are set automatically and any "
    "value you give is ignored. An unknown parameter name is rejected before the algorithm runs, with the list of valid names; an algorithm with several outputs returns each as its own layer (additional_outputs); native:selectbylocation changes the selection of the existing layer instead of creating one. Any string parameter value matching a currently-loaded layer's "
    "name is automatically resolved to that layer; every other value is passed through as-is.",
    {
        "type": "object",
        "properties": {
            "alg_id": {
                "type": "string",
                "description": "Processing algorithm id, e.g. 'native:buffer'. Must be an approved id; call find_processing_algorithm to search the approved list by words and see each algorithm's exact parameter names.",
            },
            "params": {
                "type": "object",
                "description": "Flat dict of algorithm parameters, e.g. {\"INPUT\": \"my_layer\", \"DISTANCE\": 500}. String values matching a loaded layer's name are resolved to that layer automatically.",
            },
            "new_layer_name": {
                "type": "string",
                "description": "Name to give the algorithm's output layer once added to the project. Defaults to '<alg_id>_output' if omitted -- and an omitted name is treated as a signal that this output is an internal/scratch step (e.g. a reprojection before a buffer), so it's added to the project hidden (unchecked in the layer tree) rather than cluttering the visible map. Give this an explicit name whenever the output IS the deliverable you want the user to see.",
            },
        },
        "required": ["alg_id", "params"],
    },
    # QGIS vocabulary audit 2026-10-14 (91 plain menu-style phrases): these were not offered. The Processing tool covers the algorithms in
    # _processing_allowlist.py; phrases are the names users know from the Processing toolbox and the Vector/Raster menus.
    keywords=[
        "mesh edges", "mesh faces", "mesh vertices", "mesh on grid", "mesh contours", "rasterize mesh", "mesh dataset",
        "surface to polygon", "grass", "grass gis", "grass algorithm", "r.watershed", "r.slope.aspect", "r.cost", "r.viewshed",
        "v.buffer", "v.clean", "v.net", "add geometry attributes", "affine transform", "approximate medial axis",
        "bounding box of each", "bounding boxes", "check validity", "collect geometries", "concave hull",
        "convert geometry type", "convert to curved geometries", "convert to multipart", "create wedge buffers", "delete holes",
        "delete the holes", "densify", "densify by count", "densify by interval", "dissolve coverage", "drop m z values",
        "explode lines", "explode the lines", "extend lines", "extract clip by extent", "extract vertices", "extrude",
        "fill gaps between polygons", "fill the holes", "filter vertices by m value", "filter vertices by z value",
        "force polygons", "force polygons clockwise", "force polygons counter clockwise", "force right hand rule",
        "geodesic line split at antimeridian", "interpolate point on line", "keep n biggest parts", "line substring",
        "lines to polygons", "merge lines", "minimum bounding", "minimum bounding geometry", "minimum enclosing circles",
        "multi ring buffer", "offset lines", "offset the lines", "oriented bounding box", "oriented minimum bounding box",
        "orthogonalize", "point on surface", "points along", "points along geometry", "points displacement",
        "pole of inaccessibility", "polygonize", "polygons to lines", "project points", "promote to multi",
        "promote to multipart", "rectangles ovals diamonds", "remove duplicate vertices", "remove null geometries",
        "remove parts by area", "remove parts by length", "reverse line", "reverse line direction", "reverse the line",
        "right hand rule", "rotate the features", "roundness", "segmentize", "segmentize by maximum angle",
        "segmentize by maximum distance", "set m value", "set z value", "simplify coverage", "single sided buffer",
        "smooth the geometr", "smooth the line", "smooth the polygon", "snap geometries to layer", "snap points to grid",
        "snap the points to", "split lines by maximum length", "split with lines", "subdivide the", "swap x and y",
        "swap x and y coordinates", "tapered buffer", "tapered buffers", "boundary of the polygon", "boundary of each polygon",
        "outline of the polygons as lines", "translate the", "validate coverage", "variable width buffer", "wedge buffer",
        "delete duplicate geometries", "drop geometries", "drop the geometries", "extract within distance",
        "filter by geometry type", "drop field", "drop the field", "retain fields", "delete duplicates by attribute",
        "random extract", "random extract within subsets", "join attributes by location summary", "detect dataset changes",
        "detect vector changes", "array of translated features", "array of offset", "check geometry", "check the geometry",
        "geometry check", "small angles", "small polygons", "dangle end", "degenerate polygons", "duplicated geometries",
        "duplicated vertices", "polygons exceeding boundaries", "lines intersecting", "missing vertices along borders",
        "strictly multipart", "sliver polygons", "small segments", "self contacts", "self intersections", "climb along line",
        "distance matrix", "distance to nearest hub", "create layer from extent", "create layer from point", "join by lines",
        "hub lines", "mean coordinate", "shortest line between features", "text to float", "topological coloring",
        "random points in polygons", "random points on lines", "random points along line", "random points in layer bounds",
        "extract by expression", "geometry by expression", "order by expression", "add autoincremental field",
        "random points inside polygons", "autoincrement", "symmetrical difference", "symmetric difference", "k-means", "kmeans",
        "k means cluster", "dbscan", "reclassify", "reclassification", "sample raster", "raster sampling", "raster values at",
        "join by nearest", "join attributes by location", "count points in polygon", "count points in each",
        "points per polygon", "points in each polygon", "cell statistics", "tin interpolation", "idw",
        "statistics by categories", "pansharp", "shortest path", "extract by location", "create grid", "create a grid",
        "make a grid", "fishnet", "regular grid", "native:", "gdal:", "qgis:", "processing algorithm", "processing toolbox",
        "build virtual raster", "clip raster by extent", "fill nodata", "grid with moving average", "grid with data metrics",
        "grid with inverse distance", "grid with nearest neighbor", "grid with linear interpolation", "gdal hillshade",
        "gdal slope", "gdal aspect", "near black", "pct to rgb", "rgb to pct", "raster proximity", "proximity map",
        "distance to the nearest", "rearrange bands", "roughness of the dem", "sieve the raster", "sieve",
        "topographic position index", "terrain ruggedness index", "convert raster format", "warp the raster",
        "reproject the raster", "resample the raster", "cell stack percentile", "cell stack percent rank",
        "create constant raster", "create random raster", "dtm filter", "equal to frequency", "greater than frequency",
        "less than frequency", "highest position in raster stack", "lowest position in raster stack",
        "feature preserving dem smoothing", "gaussian blur", "raster layer properties", "raster layer zonal statistics",
        "raster rank", "ruggedness index", "total curvature", "zonal histogram", "zonal minimum maximum point", "fill sinks",
        "fuzzify raster", "raster boolean and", "raster boolean or", "rescale raster", "round raster", "reclassify by layer",
        "raster minimum maximum", "viewshed", "cell stack", "add unique value index field", "add x y fields to layer",
        "convert spatial bookmarks to layer", "find projection", "assign projection to the layer", "extract by attribute value",
        "rename a table field", "extract selected features to a new layer", "split features by character",
        "create points layer from table", "align points to features", "overlap analysis", "extract network end points",
        "line density", "kernel density heatmap", "raster pixels to points", "raster pixels to polygons",
        "generate points at pixel centroids inside polygons", "regular points", "service area from a layer of facilities",
        "shortest path from a layer to a point", "st-dbscan", "sum line lengths", "validate network", "extract m values",
        "extract z values", "extract specific vertices", "line intersections", "difference of multiple layers",
        "intersection of multiple layers", "union of multiple layers", "set m value from raster", "drape the lines on the dem",
        "extract layer extent as a polygon", "rasterize the vector to a raster", "random points in extent",
        "add field to attributes table",
    ],
)
def run_allowlisted_processing_algorithm(alg_id, params, new_layer_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    refusal = _not_approved_error(alg_id)
    if refusal:
        return refusal
    if not isinstance(params, dict):
        return {"error": "params must be an object/dict of algorithm parameters."}
    violation = parameter_violation(alg_id, params)
    if violation:
        return {"error": violation}

    # GRASS exports its results to files, so a vector destination cannot be 'memory:'; it gets a temporary file like a raster does and
    # the path it returns is loaded as a vector layer below.
    is_grass = alg_id in GRASS_ALGORITHM_IDS
    file_vectors = is_grass or alg_id in FILE_VECTOR_ALGORITHM_IDS     # these return the path of a vector file they wrote
    definition = _algorithm_definition(alg_id)
    destination_keys = raster_keys = layer_list_keys = file_keys = None
    if definition is not None:
        wrong = unknown_parameters(params.keys(), definition[0])
        if wrong:
            return {"error": f"'{alg_id}' has no parameter(s) {wrong}. Its parameters are: {sorted(definition[0])}.",
                    "rejected_before_running": True}
        destination_keys, raster_keys = definition[1], definition[2]
        layer_list_keys = definition[4] if len(definition) > 4 else None
        file_keys = definition[6] if len(definition) > 6 else None

    params, parameter_note = _with_sun_point(alg_id, params)
    try:
        resolved_params = _resolve_params(params, raster_output=alg_id in RASTER_OUTPUT_ALGORITHM_IDS,
                                          destination_keys=destination_keys, raster_keys=raster_keys,
                                          layer_list_keys=layer_list_keys, temp_file_vectors=file_vectors, file_keys=file_keys)
        _check_raster_lists(alg_id, resolved_params, layer_list_keys, definition[5] if definition is not None and len(definition) > 5 else None)
        output = _run_allowlisted(alg_id, resolved_params)
    except _bg.AnalysisCancelledError as e:
        timed_out = isinstance(e, _bg.AnalysisTimedOutError)
        return {"error": str(e) if timed_out else f"Stopped before '{alg_id}' finished. Nothing was added to the project.",
                "cancelled": True, **({"timed_out": True} if timed_out else {})}
    except Exception as e:
        return {"error": f"'{alg_id}' failed: {e}"}

    if alg_id in MUTATES_INPUT_ALGORITHM_IDS:
        # The result IS the user's own layer (for example a changed selection): never rename it or call it new.
        target = resolved_params.get("INPUT")
        result = {"success": True, "alg_id": alg_id, "changed_existing_layer": True,
                  "message": f"'{alg_id}' changed the existing layer rather than creating a new one."}
        if hasattr(target, "name"):
            result["layer_name"] = target.name()
        if hasattr(target, "selectedFeatureCount"):
            result["selected_feature_count"] = target.selectedFeatureCount()
        return result

    harvested = harvest_outputs(output, definition, path_outputs=file_vectors)
    # PLAN-005 wave E1: the plain numbers of a statistics result, and the temporary report file(s) the algorithm wrote
    statistics = scalar_results(output, skip_keys=set(file_keys or ()) | {k for k, _ in harvested})
    report_files = {k: v for k, v in (output.items() if isinstance(output, dict) else []) if file_keys and k in file_keys and isinstance(v, str) and v}
    layers = []
    for key, harvested_value in harvested:
        value = harvested_value
        if isinstance(value, str):                      # a raster algorithm returns the path of the file it wrote
            value = _load_output_path(value, as_vector=file_vectors and key not in (raster_keys or ()))
        if value is not None and hasattr(value, "setName"):
            layers.append((key, value))
    if not layers:
        return _with_report_fields({"success": True, "alg_id": alg_id, "message": f"'{alg_id}' ran successfully with no new layer output."},
                                   statistics, report_files)
    if alg_id in FILE_VECTOR_ALGORITHM_IDS:
        layers = [(key, _small_result_in_memory(layer)) for key, layer in layers]
    primary_key, new_layer = layers[0]

    # IMPLEMENTATION_TRACKER.md §1.9, option 1 (narrow fix, 2026-09-24): a real turn calling this
    # tool 4x to reproject/buffer/intersect its way to one answer left 3 purely-internal scratch
    # layers fully visible and unaccounted-for in the model's own set_layer_order call, cluttering
    # the map. Can't default to always-hidden -- plenty of allowed algorithms (native:buffer for a
    # requested buffer map) ARE the deliverable, and output_router.satisfied()'s `layer` branch
    # relies on seeing them rendered. Betting on an implicit convention instead: if the caller
    # bothered to name the output, treat that as "this is a result I mean to keep visible"; if it
    # fell back to the auto-generated "<alg_id>_output" name, treat it as scratch and hide its
    # checkbox (still added to the project/legend -- inspectable, exportable, just not cluttering
    # the visible map by default). Not a schema change, so no prompt-rule update needed; if this
    # naming-convention bet doesn't hold up in practice, the tracker entry lists the costlier
    # explicit `visible` parameter as the real fix.
    caller_named_it = new_layer_name is not None
    layer_name = new_layer_name or f"{alg_id.split(':')[-1]}_output"
    new_layer.setName(layer_name)
    project = QgsProject.instance()
    project.addMapLayer(new_layer)
    if not caller_named_it:
        layer_node = project.layerTreeRoot().findLayer(new_layer.id())
        if layer_node is not None:
            layer_node.setItemVisibilityChecked(False)

    result = {"success": True, "alg_id": alg_id, "layer_name": layer_name, "visible": caller_named_it}
    if parameter_note:
        result["parameter_note"] = parameter_note
    # a result with the default look beats a failed tool call
    with contextlib.suppress(Exception):
        from .output_style import style_algorithm_output
        styled = style_algorithm_output(new_layer, alg_id)
        if styled:
            result["styled_as"] = styled
    _with_report_fields(result, statistics, report_files)
    if alg_id in FILE_VECTOR_ALGORITHM_IDS:
        result["temporary"] = True
        result["temporary_note"] = ("This result is temporary: it is not saved with the project. Ask to save it (export_layer) to keep it.")
    result.update(_output_report(new_layer, alg_id))

    # GitHub #163: algorithms with several outputs (for example a lines output AND a points output) return all of them, each as its
    # own layer named <layer_name>_<output key>; the first output keeps the plain name above.
    extra = _add_extra_outputs(layers[1:], layer_name, alg_id, caller_named_it, project)
    if extra:
        result["primary_output"] = primary_key
        result["additional_outputs"] = extra
    return result


def _add_extra_outputs(extra_layers, layer_name, alg_id, caller_named_it, project):
    """Adds the second and later outputs of a multi-output algorithm to the project, each named <layer_name>_<output key>, styled by the
    algorithm's kind, and hidden when the caller did not name the result. Returns the per-output summaries."""
    extra = []
    for key, layer in extra_layers:
        extra_name = f"{layer_name}_{key.lower()}"
        layer.setName(extra_name)
        project.addMapLayer(layer)
        node = project.layerTreeRoot().findLayer(layer.id())
        if node is not None and not caller_named_it:
            node.setItemVisibilityChecked(False)
        entry = {"output": key, "layer_name": extra_name}
        if hasattr(layer, "featureCount"):
            entry["feature_count"] = layer.featureCount()
        # rc45 smoke run: grass:r.slope.aspect and the other multi-output algorithms opened plain grey, because only the FIRST output was ever
        # styled. Every output gets the look the algorithm's kind calls for.
        with contextlib.suppress(Exception):
            from .output_style import style_algorithm_output
            styled_extra = style_algorithm_output(layer, alg_id)
            if styled_extra:
                entry["styled_as"] = styled_extra
        extra.append(entry)
    return extra


def _with_report_fields(result, statistics, report_files):
    """Adds a statistics algorithm's numbers and temporary report file(s) to `result` (PLAN-005 wave E1) and returns it."""
    if statistics:
        result["statistics"] = statistics
        if "layer_name" not in result:
            result["message"] = f"'{result['alg_id']}' ran successfully; its numbers are in 'statistics'."
    if report_files:
        result["report_files"] = report_files
        result["report_note"] = "The report is a temporary file; it is not part of the project and is not kept."
    return result


def _small_result_in_memory(layer):
    """PLAN-005 rule R1: a vector result that came back as a temporary file is copied into a memory layer when it is small, so the project does not
    keep pointing at a temporary file that is gone after a restart. A larger result, or one that cannot be copied, stays as the file layer."""
    with contextlib.suppress(Exception):      # a result that cannot be copied is still a usable file layer
        if hasattr(layer, "featureCount") and layer.featureCount() <= MEMORY_COPY_LIMIT and hasattr(layer, "materialize"):
            from qgis.core import QgsFeatureRequest
            copy = layer.materialize(QgsFeatureRequest())
            if copy is not None and copy.isValid():
                return copy
    return layer


def _load_output_path(path, as_vector=False):
    """The layer an algorithm's file output holds, or None when QGIS cannot open it. Rasters are the default; GRASS vector results come
    back as a file path too and are opened as a vector layer."""
    loaded = QgsVectorLayer(path, "grass_output", "ogr") if as_vector else QgsRasterLayer(path, "raster_output")
    return loaded if loaded.isValid() else None


def search_allowed_algorithms(query, names=None, limit=15):
    """[(id, name)] of approved algorithms whose id or display name contains every word of `query`, best first. Pure: `names` maps
    id to display name (ids without one are searched by id only)."""
    from ._processing_allowlist import FAMILY_NAMES
    names = dict(FAMILY_NAMES if names is None else names)
    words = [w for w in str(query or "").lower().replace("_", " ").split() if len(w) > 1]
    scored = []
    for alg_id in sorted(ALLOWED_ALGORITHM_IDS):
        haystack = (alg_id.lower() + " " + str(names.get(alg_id, "")).lower()).replace("_", " ")
        hits = sum(1 for w in words if w in haystack)
        if words and hits == len(words):
            scored.append((-hits, alg_id))
        elif not words:
            scored.append((0, alg_id))
    found = [(alg_id, names.get(alg_id, "")) for _score, alg_id in sorted(scored)[:limit]]
    if words and len(found) < limit:
        # rc46: describe what you want and the topic index finds it ("fill the gaps in my elevation raster" -> r.fillnulls); before this
        # only a query whose every word was inside an algorithm's id or name found anything.
        from ..algorithm_topics import rank
        have = {alg_id for alg_id, _name in found}
        for alg_id, _score, _hits in rank(query, limit=limit):
            if alg_id in ALLOWED_ALGORITHM_IDS and alg_id not in have and len(found) < limit:
                found.append((alg_id, names.get(alg_id, "")))
                have.add(alg_id)
    return found


def _browse_family(family):
    """The approved algorithms of one family as a short list (id, name, what it is for), so a model can pick by meaning when its search words
    did not match any algorithm's name. Pure data: needs no QGIS."""
    from ..algorithm_topics import about, family_ids
    from ._processing_allowlist import FAMILY_NAMES
    ids = family_ids(family)
    if ids is None:
        return {"error": f"Unknown family '{family}'. Use geometry, table, analysis, expression, raster, mixed, grass or mesh."}
    items = []
    for alg_id in ids:
        entry = {"id": alg_id, "name": FAMILY_NAMES.get(alg_id) or alg_id.split(":", 1)[1]}
        phrase = about(alg_id)
        if phrase:
            entry["for"] = phrase
        items.append(entry)
    return {"success": True, "family": family, "count": len(items), "algorithms": items,
            "message": "Pick the one that does what the user wants, then call find_processing_algorithm with its algorithm_id for its parameters."}


@register_tool(
    "find_processing_algorithm",
    "Search the approved QGIS Processing algorithms by a few words (for example 'densify', 'polygons to lines', 'smooth') and get each "
    "match's id, name and exact parameter names with types and defaults, ready for run_allowlisted_processing_algorithm. Read-only. "
    "With algorithm_id set, returns just that algorithm's parameters.",
    {"type": "object", "properties": {"query": {"type": "string"}, "algorithm_id": {"type": "string"},
                                      "family": {"type": "string", "description": "Browse one family instead of searching: geometry, table, analysis, "
                                                 "expression, raster, mixed, grass or mesh. Lists id, name and what each is for."}},
     "required": []},
    # M1 (2026-10-14). inspect_canvas_visually is here because the new basemap/web-layer tools mention "map" and pushed it out of the
    # top 40 for "look at the map" (caught by tests/test_qgis_coverage_ratchet.py): a tool that only matched on a description word
    # loses to any newcomer that uses the same word, so the phrases users actually say are pinned.
    keywords=[
        "which grass", "grass algorithms", "grass commands", "which processing algorithm", "processing algorithm",
        "processing tool for", "is there a tool for", "is there an algorithm", "list the processing", "what algorithms",
        "which algorithm", "available algorithms", "qgis algorithm",
    ],
)
def find_processing_algorithm(query="", algorithm_id=None, family=None):
    if family:
        return _browse_family(family)
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from ._processing_allowlist import FAMILY_NAMES
    if algorithm_id:
        matches = [(algorithm_id, FAMILY_NAMES.get(algorithm_id, ""))] if algorithm_id in ALLOWED_ALGORITHM_IDS else []
        if not matches:
            return {"error": f"'{algorithm_id}' is not on the approved list. Search with a few words instead."}
    else:
        matches = search_allowed_algorithms(query)
    results = []
    for alg_id, name in matches:
        entry = {"id": alg_id, "name": name}
        try:
            algorithm = QgsApplication.processingRegistry().algorithmById(alg_id)
            entry["name"] = name or algorithm.displayName()
            entry["parameters"] = [
                {"name": p.name(), "type": str(p.type()), "default": _plain(p.defaultValue())}
                for p in algorithm.parameterDefinitions() if not p.isDestination()]
            entry["outputs_are_kept_in_memory"] = True
        except Exception:
            entry["parameters"] = "not available in this QGIS session"
        results.append(entry)
    if not results:
        return {"success": True, "matches": [],
                "message": f"No approved algorithm matches '{query}'. Describe the result you want in other words, or browse a family with "
                           "family=geometry, table, analysis, expression, raster, mixed, grass or mesh; or use a dedicated tool."}
    return {"success": True, "matches": results}


def _plain(value):
    return value if isinstance(value, (int, float, str, bool)) or value is None else str(value)
