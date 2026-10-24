"""PLAN-011 phase A: what a layout export tells the user about the map it just wrote.

export_layout and create_print_layout's export used to say nothing about WHAT was drawn: a layout showing a layer tagged RESTRICTED or
SENSITIVE left as a PDF with no note (the data exports already add one), and a layout stripped of its legend or scale bar exported without
a word. This reports both, as warnings only -- nothing is blocked here (the confirm-card gate is phase B, docs/plans/PLAN-011).

The element rule and the wording are pure so they run without QGIS; `layers_drawn` needs a real layout and is covered by
tests/test_layout_export_checks_live.py in CI."""
from ...models.sensitivity import get_layer_sensitivity
from ._sensitivity_notes import protected_layer_notes

try:
    from qgis.core import QgsLayoutItemMap, QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# Same five ids qa_checklist_tools checks (docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md section VII); create_print_layout sets every one.
MANDATORY_LAYOUT_ELEMENTS = {
    "MAP_MAIN": "map",
    "TITLE": "title",
    "LEGEND": "legend",
    "SCALEBAR": "scale bar",
    "NORTH_ARROW": "north arrow",
}


def missing_elements(ids_present):
    """Labels of the mandatory layout elements whose ids are not in `ids_present`, in a fixed order. Pure."""
    present = set(ids_present or ())
    return [label for item_id, label in MANDATORY_LAYOUT_ELEMENTS.items() if item_id not in present]


def export_report(layers_drawn, ids_present):
    """The fields an export result should carry: {} when there is nothing to say. Pure apart from reading each layer's sensitivity tag."""
    notes = protected_layer_notes(layers_drawn, "it is drawn on this exported map -- confirm the file is meant to be shared before distributing it.")
    missing = missing_elements(ids_present)
    report = {}
    if notes:
        protected = []
        for layer in layers_drawn:
            try:
                level = get_layer_sensitivity(layer).get("level")
            except Exception:
                level = None
            if level in ("RESTRICTED", "SENSITIVE"):
                protected.append({"layer": layer.name(), "level": level})
        report["protected_layers"] = protected
    if missing:
        notes.append("This layout is missing: " + ", ".join(missing) + ". The file was written as it is.")
        report["missing_elements"] = missing
    if notes:
        report["export_warnings"] = notes
    return report


def layers_drawn(layout):
    """The layers the layout's map items draw: each map's own locked layer set, else its map theme, else the layers ticked in the project. Never raises."""
    if not QGIS_AVAILABLE:
        return []
    project = QgsProject.instance()
    seen, out = set(), []

    def add(layer):
        if layer is not None and layer.id() not in seen:
            seen.add(layer.id())
            out.append(layer)

    try:
        for item in layout.items():
            if not isinstance(item, QgsLayoutItemMap):
                continue
            chosen = None
            if item.keepLayerSet():
                chosen = item.layers()
            elif item.followVisibilityPreset() and item.followVisibilityPresetName():
                names = project.mapThemeCollection().mapThemeVisibleLayers(item.followVisibilityPresetName())
                chosen = [project.mapLayer(n) if isinstance(n, str) else n for n in names]
            if chosen is None:
                chosen = project.layerTreeRoot().checkedLayers()
            for layer in chosen:
                add(layer)
    except Exception:
        return out
    return out


def layout_export_report(layout):
    """export_report() for a real layout. Never raises: a note that cannot be built is left out, the export result stays as it was."""
    try:
        ids = [i.id() for i in layout.items() if hasattr(i, "id") and i.id()]
        return export_report(layers_drawn(layout), ids)
    except Exception:
        return {}
