"""run_algorithm_in_place (PLAN-023 R11-3): an approved Processing algorithm applied directly to the user's own vector layer, as one undoable edit.

Only algorithms QGIS itself flags as able to edit in place (supportInPlaceEdit for this very layer) are accepted, and only if they are on the approved list; the same parameter and expression
screens as a normal run apply (processing_allowlist_tools / _processing_allowlist). The work is done by QGIS's own in-place executor (processing.gui.AlgorithmExecutor.execute_in_place), which
writes into the layer's edit buffer inside one edit command, so undo_manual_edit steps it back. The layer is left in edit mode with the change UNSAVED (set_layer_editing saves or discards),
and the user's selection is put back as it was. A confirmation card with the exact feature count is shown first. Written without a QGIS install; tests/test_in_place_tool_live.py compares the
result with the normal (new-layer) run of the same algorithm and is its first execution in CI. Stop cannot reach the run: it is synchronous, like run_processing_model."""
from . import in_place_ops as ipo
from ._processing_allowlist import parameter_violation
from .attribute_edit_tools import _layer, preview
from .processing_allowlist_tools import _not_approved_error
from .registry import register_tool

try:
    from qgis.core import QgsApplication, QgsProcessingContext, QgsProcessingFeedback
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _algorithm(algorithm_id, layer):
    """(algorithm, error): the registered algorithm if it can edit this layer in place. Needs QGIS."""
    alg = QgsApplication.processingRegistry().algorithmById(algorithm_id)
    if alg is None:
        return None, f"'{algorithm_id}' is not registered in this QGIS."
    if not alg.supportInPlaceEdit(layer):
        return None, (f"'{algorithm_id}' cannot edit '{layer.name()}' in place (QGIS allows it only for some algorithms and some geometry types). "
                      "run_allowlisted_processing_algorithm makes a new layer instead.")
    return alg, None


@register_tool(
    "run_algorithm_in_place",
    "Apply an approved Processing algorithm that supports editing in place (for example native:smoothgeometry, native:translategeometry, native:simplifygeometries) DIRECTLY to a vector layer "
    "instead of making a new layer. selected_only true changes only the selected features, false changes every feature. `parameters` are the algorithm's settings (not the input or output). "
    "Changes your data: a preview with the exact feature count is shown first, the change is ONE undoable step (undo_manual_edit) and stays UNSAVED in the layer's edit session until "
    "you save it (set_layer_editing). Your selection is put back afterwards.",
    {"type": "object", "properties": {
        "algorithm_id": {"type": "string", "description": "An approved algorithm id that supports in-place editing, e.g. native:smoothgeometry."},
        "layer_name": {"type": "string", "description": "The vector layer to change."},
        "selected_only": {"type": "boolean", "description": "true: only the selected features; false: every feature."},
        "parameters": {"type": "object", "description": "The algorithm's settings, for example {\"ITERATIONS\": 2}."}},
     "required": ["algorithm_id", "layer_name", "selected_only"]},
    keywords=["in place", "edit in place", "smooth the selected features", "change the layer itself", "apply it to the layer itself", "modify the layer in place", "smooth in place",
              "translate in place", "simplify in place", "without making a new layer"],
)
def run_algorithm_in_place(algorithm_id, layer_name, selected_only, parameters=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = ipo.check_request(algorithm_id, layer_name, selected_only, parameters)
    if problem:
        return {"error": problem}
    refusal = _not_approved_error(algorithm_id)
    if refusal:
        return refusal
    violation = parameter_violation(algorithm_id, parameters or {})
    if violation:
        return {"error": violation}
    layer, err = _layer(layer_name)
    if err:
        return err
    alg, problem = _algorithm(algorithm_id, layer)
    if problem:
        return {"error": problem}
    chosen_ids = list(layer.selectedFeatureIds())
    if selected_only and not chosen_ids:
        return {"error": f"selected_only is true but nothing is selected in '{layer_name}'. Select features first, or use selected_only false for every feature."}
    count = len(chosen_ids) if selected_only else layer.featureCount()
    if count == 0:
        return {"error": f"'{layer_name}' has no features to change."}
    if not confirmed:
        arguments = {"algorithm_id": algorithm_id, "layer_name": layer_name, "selected_only": selected_only, "parameters": parameters or {}}
        return preview("run_algorithm_in_place", arguments, ipo.describe(alg.displayName(), layer_name, count, selected_only),
                       "# QGIS's own in-place executor\nfrom processing.gui.AlgorithmExecutor import execute_in_place\nexecute_in_place(alg, {'INPUT': layer, **settings})")
    try:
        from processing.gui.AlgorithmExecutor import execute_in_place
    except ImportError:
        return {"error": "QGIS's Processing plugin is not loaded in this session, so the in-place executor is not available. Nothing was changed."}
    previous = chosen_ids
    was_editable = layer.isEditable()
    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    if not selected_only:
        layer.selectAll()
    try:
        ok, results = execute_in_place(alg, {**(parameters or {}), "INPUT": layer}, context, feedback)
    except Exception as e:
        return {"error": f"'{algorithm_id}' failed: {e}. The layer's edit history was not extended by this tool."}
    finally:
        layer.selectByIds(previous)
    if not ok:
        return {"error": f"'{algorithm_id}' did not change the layer" + (f": {results}" if isinstance(results, str) and results else ".")}
    out = {"success": True, "algorithm": algorithm_id, "layer_name": layer_name, "features_changed": count, "changed_existing_layer": True,
           "undo": "undo_manual_edit steps it back while the layer is in edit mode.",
           "note": "The change is in the layer's edit session and is NOT saved: set_layer_editing saves or discards it."}
    if not was_editable:
        out["note"] = "The layer was switched to edit mode for this; " + out["note"]
    return out
