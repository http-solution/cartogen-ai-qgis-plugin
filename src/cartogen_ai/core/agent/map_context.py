# -*- coding: utf-8 -*-
"""
Proactive Map Context Summary for Cartogen AI.
Builds a lightweight snapshot of the current project/canvas so the agent has
baseline spatial awareness without needing a get_layers() tool round-trip on
every request. Must only be called from the main Qt thread -- QgsProject and
iface are not thread-safe.
"""

MAX_LAYERS = 15
MAX_FIELDS_PER_LAYER = 8

try:
    from qgis.core import QgsProject
    from qgis.utils import iface
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    iface = None


def get_map_context_summary() -> dict:
    """Returns a capped, lightweight summary of loaded layers, CRS, and the
    active layer. Returns {} if QGIS isn't available or nothing is loaded."""
    if not QGIS_AVAILABLE:
        return {}

    try:
        project = QgsProject.instance()
        all_layers = list(project.mapLayers().values())
        if not all_layers:
            return {}

        layers = []
        for layer in all_layers[:MAX_LAYERS]:
            if not layer.isValid():
                continue
            fields = []
            if hasattr(layer, "fields"):
                try:
                    fields = [f.name() for f in layer.fields()][:MAX_FIELDS_PER_LAYER]
                except Exception:
                    fields = []
            feature_count = None
            if hasattr(layer, "featureCount"):
                try:
                    feature_count = layer.featureCount()
                except Exception:
                    feature_count = None
            layer_type = layer.type()
            entry = {
                "name": layer.name(),
                "type": layer_type.name if hasattr(layer_type, "name") else str(layer_type),
                "crs": layer.crs().authid() if layer.crs() else "",
                "feature_count": feature_count,
                "fields": fields,
            }
            try:
                # F21: one rule for what the cloud model may see about a layer (models/model_view.py).
                from ..models import model_view, sensitivity
                entry = model_view.apply_to_layer_entry(entry, sensitivity.get_layer_sensitivity(layer).get("level"))
            except Exception:
                pass
            layers.append(entry)

        active_layer = iface.activeLayer() if iface else None
        canvas = iface.mapCanvas() if iface else None

        return {
            "project_title": project.title() or "Untitled Project",
            "canvas_crs": canvas.mapSettings().destinationCrs().authid() if canvas else "",
            "active_layer": active_layer.name() if active_layer else "None",
            "layer_count": len(all_layers),
            "layers": layers,
            "truncated": len(all_layers) > MAX_LAYERS,
        }
    except Exception as e:
        print(f"[MapContext] Failed to build map context summary: {e}")
        return {}


# Broadsheet redesign Phase 3 (mockup state 1l, "layer context picker"): explicit,
# per-question control over which loaded layers' schema actually reaches the model,
# instead of every loaded layer's schema always being sent unconditionally. Pure Python
# below -- no QGIS import -- so it's testable without a live QGIS process, matching this
# package's existing split convention (ui/chat_formatting.py, ui/icons.py's path data).

# Rough, honest estimate only -- this app talks to 5 different provider APIs, each with
# its own real tokenizer, and none of them are worth vendoring here just to show one
# approximate number next to a checkbox list. ~4 chars/token is the commonly cited
# English-text average (OpenAI's own docs use the same rule of thumb) -- close enough to
# be useful for "is this picker selection roughly small or large," not a billing figure.
_CHARS_PER_TOKEN_ESTIMATE = 4


def estimate_layer_context_tokens(layers):
    """A rough token-count estimate for a list of layer summary dicts (the same shape
    get_map_context_summary()["layers"] returns) -- for the picker's "~N tokens" label,
    not a precise or provider-specific count."""
    if not layers:
        return 0
    chars = 0
    for layer in layers:
        chars += len(str(layer.get("name", "")))
        chars += len(str(layer.get("type", "")))
        chars += len(str(layer.get("crs", "")))
        chars += sum(len(str(f)) for f in (layer.get("fields") or []))
        chars += 20  # rough allowance for the surrounding formatted-line punctuation/labels
    return max(1, chars // _CHARS_PER_TOKEN_ESTIMATE)


def filter_layers_by_selection(map_ctx, selection):
    """Returns a COPY of map_ctx with "layers" filtered down to the layer names present
    (and truthy) in `selection` -- never mutates the original dict or list, since
    get_map_context_summary()'s own return value must keep reflecting the project's real
    state regardless of what a user has unchecked in the picker for this one question.

    `selection` is {layer_name: bool}. A layer with no entry in `selection` at all (the
    common case -- the user never opened the picker) is KEPT, not dropped: the picker is
    opt-out, not opt-in, so a user who never touches it gets today's unchanged behavior
    of sending every loaded layer's schema. Only a layer explicitly set to False is
    excluded."""
    if not map_ctx or not selection:
        return map_ctx
    layers = map_ctx.get("layers") or []
    kept = [layer for layer in layers if selection.get(layer.get("name")) is not False]
    if len(kept) == len(layers):
        return map_ctx
    filtered = dict(map_ctx)
    filtered["layers"] = kept
    filtered["layer_count"] = len(kept)
    return filtered
