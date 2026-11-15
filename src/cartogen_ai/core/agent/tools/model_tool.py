"""run_processing_model (PLAN-023 R11-1): run a graphical-modeler model (.model3) from the project folder, only if every step of it is approved.

A model is a program, so it gets the same rule as a single Processing algorithm, applied to EVERY step before anything runs (model_ops.py holds the pure checks and their known answers):
every algorithm id must be on the approved list (a nested model and a Python script never are), an algorithm that changes the user's own layer is refused, every parameter goes through
parameter_violation and every expression through the expression screen. The ids are checked twice, once from this module's own parse of the file and once from QGIS's parse of the same file;
the model is refused if QGIS sees an algorithm the first parse did not. The refusal names the step and the algorithm.

Where the file may be: inside the project folder (the project must be saved), a .model3 file of at most 1 MB; a path that leaves the folder is refused. Outputs are forced to temporary layers
(`memory:` for a vector sink, a temporary file for a raster or a vector file destination); a model with a folder, file or any other destination is refused because it would write where it is told.
The run is synchronous with the window kept painting (like the GRASS and GDAL algorithms), so Stop cannot reach it; the description says so. Results are added to the project as new layers; nothing
the model does can change an existing layer. Written without a QGIS install; tests/test_model_tool_live.py is its first execution in CI."""
import contextlib
import os

from ... import _background_processing as _bg
from . import model_ops as mo
from .registry import register_tool

try:
    from qgis.core import QgsProcessingContext, QgsProcessingModelAlgorithm, QgsProject, QgsRasterLayer, QgsVectorLayer
    import processing
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

TEMPORARY_SINKS = {"sink": "memory:", "vectorDestination": "TEMPORARY_OUTPUT", "rasterDestination": "TEMPORARY_OUTPUT"}
MAX_LAYERS = 10


def _model_path(model_file):
    """(absolute path, error text): the model file resolved inside the project folder. Needs QGIS."""
    home = QgsProject.instance().homePath()
    if not home:
        return None, "Save the project first: models are read from the project folder, and this project has none yet."
    if not isinstance(model_file, str) or not model_file.strip():
        return None, "model_file must be the name of a .model3 file in the project folder."
    root = os.path.realpath(home)
    path = os.path.realpath(model_file if os.path.isabs(model_file) else os.path.join(root, model_file))
    try:
        inside = os.path.commonpath([root, path]) == root
    except ValueError:                                  # a path on another drive (Windows) has no common path with the project folder
        inside = False
    if not inside:
        return None, "The model file must be inside the project folder."
    if not path.lower().endswith(".model3"):
        return None, "A model file ends in .model3."
    if not os.path.isfile(path):
        return None, f"No model file '{os.path.basename(path)}' in the project folder."
    if os.path.getsize(path) > mo.MAX_BYTES:
        return None, f"The model file is larger than {mo.MAX_BYTES // 1000} KB, which is more than a model made in the modeler needs."
    return path, None


def _second_opinion(model, parsed):
    """The refusal text when QGIS's own reading of the model finds an algorithm the first parse missed or one that is not approved, else None. Needs QGIS."""
    qgis_ids = {child.algorithmId() for child in model.childAlgorithms().values()}
    unseen = sorted(qgis_ids - set(parsed["algorithm_ids"]))
    if unseen:
        return f"Model refused: QGIS reads an algorithm ({unseen[0]}) that the file check did not see, so the file is not trusted."
    bad = mo.not_approved(qgis_ids)
    return f"Model refused: {bad[1]}" if bad else None


def _plain_inputs(model, inputs):
    """(params dict, error): the caller's inputs with layer names resolved to layers; only the model's own input names are accepted. Needs QGIS."""
    names = [p.name() for p in model.parameterDefinitions() if not p.isDestination()]
    if not isinstance(inputs, dict):
        return None, "inputs must be an object {input name: value}."
    unknown = sorted(set(inputs) - set(names))
    if unknown:
        return None, f"The model has no input(s) {unknown}. Its inputs are: {mo.input_help(names)}."
    params = {}
    for key, value in inputs.items():
        if isinstance(value, dict):
            return None, f"Input '{key}' must be a plain value or a list of plain values, not an object."
        params[key] = _resolve(value)
    return params, None


def _resolve(value):
    """A string that names a loaded layer becomes that layer (as the single-algorithm tool does); lists likewise; everything else is unchanged. Needs QGIS."""
    if isinstance(value, str):
        matches = QgsProject.instance().mapLayersByName(value)
        return matches[0] if matches else value
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    return value


def _destinations(model):
    """({name: temporary value}, error text): every destination of the model forced to a temporary sink; a model that writes a folder, a file or anything else is refused. Needs QGIS."""
    forced = {}
    for definition in model.destinationParameterDefinitions():
        value = TEMPORARY_SINKS.get(definition.type())
        if value is None:
            return None, (f"Model refused: its output '{definition.name()}' is a {definition.type()}, which would write to a place the model names. "
                          "Only layer outputs are run here (they become temporary layers).")
        forced[definition.name()] = value
    return forced, None


def _layers_from(output, model):
    """[(output key, layer)] for the layers a finished model returned, in the model's order. Needs QGIS."""
    kinds = {d.name(): d.type() for d in model.destinationParameterDefinitions()}
    found = []
    for key in [d.name() for d in model.destinationParameterDefinitions() if d.name() in output] + [k for k in output if k not in kinds]:
        value = output[key]
        if isinstance(value, str) and value and kinds.get(key) in ("rasterDestination", "vectorDestination"):
            value = QgsRasterLayer(value, key) if kinds[key] == "rasterDestination" else QgsVectorLayer(value, key, "ogr")
            value = value if value.isValid() else None
        if value is not None and hasattr(value, "setName"):
            found.append((key, value))
    return found


@register_tool(
    "run_processing_model",
    "Run a model made in QGIS's graphical modeler (a .model3 file in the project folder, so save the project first). It is run ONLY if every step is an approved algorithm: a model that "
    "contains a Python script, another model, an unapproved algorithm, one that changes your own layers, or an expression that calls a denied function is REFUSED and the reply names the step "
    "and the algorithm. `inputs` gives the model's inputs ({input name: layer name or value}); outputs always become temporary new layers in the project, and a model that writes a folder or "
    "file is refused. The run keeps the window painting but cannot be stopped with Stop.",
    {"type": "object", "properties": {
        "model_file": {"type": "string", "description": "Name of the .model3 file in the project folder (or a path inside it)."},
        "inputs": {"type": "object", "description": "{input name: layer name or plain value} for the model's inputs."},
        "output_name": {"type": "string", "description": "Name for the result layer(s) (default: the model's name)."}},
     "required": ["model_file"]},
    keywords=["run a model", "run the model", "run my model", "processing model", "graphical model", "graphical modeler", "run the graphical model", "model3", "run a saved model"],
)
def run_processing_model(model_file, inputs=None, output_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    path, problem = _model_path(model_file)
    if problem:
        return {"error": problem}
    with open(path, encoding="utf-8", errors="replace") as fh:
        parsed, problem = mo.parse_model(fh.read())
    if problem:
        return {"error": problem}
    refusal = mo.check_model(parsed)
    if refusal:
        return {"error": refusal, "refused_before_running": True}
    model = QgsProcessingModelAlgorithm()
    if not model.fromFile(path):
        return {"error": "QGIS could not read this model file."}
    refusal = _second_opinion(model, parsed)
    if refusal:
        return {"error": refusal, "refused_before_running": True}
    runnable, reason = model.canExecute()
    if not runnable:
        return {"error": f"QGIS says this model cannot run here: {reason}"}
    params, problem = _plain_inputs(model, inputs or {})
    if problem:
        return {"error": problem}
    forced, problem = _destinations(model)
    if problem:
        return {"error": problem, "refused_before_running": True}
    params.update(forced)
    context = QgsProcessingContext()
    context.setProject(QgsProject.instance())
    valid, message = model.checkParameterValues(params, context)
    if not valid:
        inputs_needed = [p.name() for p in model.parameterDefinitions() if not p.isDestination()]
        return {"error": f"The model's inputs are not complete: {message} Its inputs are: {mo.input_help(inputs_needed)}."}
    label = f"model:{parsed['name'] or os.path.basename(path)}"
    try:
        output = _bg.run_synchronously_with_repaint(label, lambda feedback: processing.run(model, params) if feedback is None else processing.run(model, params, feedback=feedback))
    except _bg.AnalysisCancelledError:
        return {"error": "The model run was stopped. Nothing was added to the project.", "cancelled": True}
    except Exception as e:
        return {"error": f"The model failed: {e}"}
    layers = _layers_from(output if isinstance(output, dict) else {}, model)[:MAX_LAYERS]
    base = (output_name or "").strip() or parsed["name"] or os.path.splitext(os.path.basename(path))[0]
    project = QgsProject.instance()
    added = []
    for key, layer in layers:
        layer.setName(base if len(layers) == 1 else f"{base}_{key}")
        project.addMapLayer(layer)
        with contextlib.suppress(AttributeError, RuntimeError):
            added.append({"output": key, "layer_name": layer.name(), "features": layer.featureCount()} if hasattr(layer, "featureCount") else {"output": key, "layer_name": layer.name()})
    return {"success": True, "model": parsed["name"] or os.path.basename(path), "steps": len(parsed["children"]), "algorithms": parsed["algorithm_ids"], "layers": added,
            "temporary": True, "note": "The results are temporary layers: they are not saved with the project until you export them. No existing layer was changed."}
