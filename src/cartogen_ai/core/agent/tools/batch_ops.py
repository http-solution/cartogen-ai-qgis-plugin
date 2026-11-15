"""Batch Processing helpers (PLAN-023 R11-2): the request check and the way results are summed up, pure Python (no QGIS, no numpy).

run_processing_batch (batch_tool.py) runs ONE approved algorithm over several layers, one run per layer, and groups the results. Every run goes through run_allowlisted_processing_algorithm,
so each one gets exactly the checks a single run gets (approved list, parameter screen, temporary output); what is added here is the request check below and the summary.
Rules: 1 to MAX_LAYERS layers (20), each named once; `parameters` are the settings shared by all runs (plain values, never the input or an output); an algorithm that changes the user's own
layer (a selection) is refused because a batch would change many layers at once; a run that fails does not stop the others, and the reply lists which failed and why; Stop ends the batch and the
reply says how far it got. Known answers (the tests): 21 layers are refused, a repeated layer name is refused, 3 successes and 1 failure sum up as partial with the failure named."""
import re

MAX_LAYERS = 20
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def short_name(algorithm_id):
    """The part after the colon: 'native:buffer' -> 'buffer'. Pure."""
    return str(algorithm_id).split(":")[-1]


def check_request(algorithm_id, layers, parameters=None, input_parameter="INPUT"):
    """Error text for a batch request that cannot be run, else None. Pure."""
    if not isinstance(algorithm_id, str) or ":" not in algorithm_id or len(algorithm_id) > 100:
        return "algorithm_id must be an approved algorithm id such as native:buffer (find_processing_algorithm lists them)."
    if not isinstance(layers, list) or not 1 <= len(layers) <= MAX_LAYERS:
        return f"layers must be a list of 1 to {MAX_LAYERS} layer names (a batch of more is split by the caller)."
    if any(not isinstance(n, str) or not n.strip() for n in layers):
        return "every entry of layers must be a layer name."
    names = [n.strip() for n in layers]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        return f"Layer(s) {repeated} are listed more than once."
    if not isinstance(input_parameter, str) or not _NAME.match(input_parameter):
        return "input_parameter must be the algorithm's input parameter name, for example INPUT."
    if parameters is not None and not isinstance(parameters, dict):
        return "parameters must be an object of settings shared by all the runs."
    for key, value in (parameters or {}).items():
        if key == input_parameter:
            return f"parameters must not contain '{input_parameter}': that is filled in with each layer in turn."
        if key.lower().startswith("output") or key.lower().endswith("_output"):
            return f"parameters must not contain '{key}': the outputs of a batch are always temporary layers."
        if isinstance(value, dict):
            return f"parameter '{key}' must be a plain value or a list of plain values, not an object."
    return None


def summarise(results):
    """{'requested', 'succeeded', 'failed', 'partial', 'stopped_after'} from [(layer, ok, detail, cancelled)] in run order. Pure."""
    failed = [{"layer": layer, "error": detail} for layer, ok, detail, _c in results if not ok]
    stopped = next((i for i, row in enumerate(results) if row[3]), None)
    succeeded = sum(1 for _l, ok, _d, _c in results if ok)
    return {"ran": len(results), "succeeded": succeeded, "failed": failed, "partial": bool(failed) and succeeded > 0,
            "stopped_after": None if stopped is None else stopped}
