"""In-place Processing helpers (PLAN-023 R11-3): the request check and the plain-language card text, pure Python (no QGIS).

run_algorithm_in_place (in_place_tool.py) runs an approved Processing algorithm that supports QGIS's "edit features in place" mode (smooth, translate, simplify ...) directly on the
user's own layer, instead of making a new layer. That changes the user's data, so: the algorithm must be on the approved list; the input and output settings are never passed in
(the layer is the input, the result goes back into the layer); the same parameter and expression screens as a normal run apply; a confirmation card with the exact feature count comes first;
and the change lands in the layer's edit buffer as ONE undoable step (undo_manual_edit), unsaved until the user saves. Known answers (the tests): `selected_only` true with nothing selected is
refused, an INPUT or OUTPUT key in `parameters` is refused, 1 feature reads '1 feature' and 3 read '3 features'."""
import re

_ID = re.compile(r"^[a-z0-9_]+:[A-Za-z0-9_]+$")


def check_request(algorithm_id, layer_name, selected_only, parameters):
    """Error text for a request that cannot be run, else None. Pure."""
    if not isinstance(algorithm_id, str) or not _ID.match(algorithm_id) or len(algorithm_id) > 100:
        return "algorithm_id must be an approved algorithm id such as native:smoothgeometry (find_processing_algorithm lists them)."
    if not isinstance(layer_name, str) or not layer_name.strip():
        return "layer_name must be the name of a vector layer."
    if not isinstance(selected_only, bool):
        return "selected_only must be true (only the selected features) or false (every feature)."
    if parameters is not None and not isinstance(parameters, dict):
        return "parameters must be an object of the algorithm's settings."
    for key, value in (parameters or {}).items():
        if str(key).upper() in ("INPUT", "OUTPUT") or str(key).lower().startswith("output"):
            return f"parameters must not contain '{key}': the layer is the input and the result goes back into it."
        if isinstance(value, dict):
            return f"parameter '{key}' must be a plain value, not an object."
    return None


def count_text(count):
    """'1 feature' / '3 features'. Pure."""
    return f"{count} feature" + ("" if count == 1 else "s")


def describe(algorithm_name, layer_name, count, selected_only):
    """The confirmation sentence. Pure."""
    scope = "the selected" if selected_only else "every"
    return f"Run '{algorithm_name}' IN PLACE on {scope} feature(s) of '{layer_name}' ({count_text(count)}); the layer's own geometry or values change (one undoable step)."
