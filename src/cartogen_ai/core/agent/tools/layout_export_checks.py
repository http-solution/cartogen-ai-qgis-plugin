"""PLAN-011 phases A and B: what a layout export tells the user about the map it writes, and when it must ask first.

export_layout and create_print_layout's export used to say nothing about WHAT was drawn: a layout showing a layer tagged RESTRICTED or
SENSITIVE left as a PDF with no note (the data exports already add one), and a layout stripped of its legend or scale bar exported without
a word. Phase A reports both, as warnings. Phase B (owner decisions 2026-10-24, docs/plans/PLAN-011): a layout whose map draws a protected layer waits
for the user's confirm card (never a hard block), and `purpose="publication"` additionally refuses an export with problems unless the user
confirms and a reason is given, which is written beside the file.

The element rule and the wording are pure so they run without QGIS; `layers_drawn` needs a real layout and is covered by
tests/test_layout_export_checks_live.py in CI."""
import json
import time

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


def protected_in(layers):
    """[{layer, level, reason}] for the layers tagged RESTRICTED or SENSITIVE; an unreadable tag counts as no tag (advisory, never raises)."""
    out = []
    for layer in layers or []:
        try:
            record = get_layer_sensitivity(layer)
        except Exception:
            record = {}
        if record.get("level") in ("RESTRICTED", "SENSITIVE"):
            out.append({"layer": layer.name(), "level": record["level"], "reason": record.get("reason")})
    return out


def publication_problems(missing, protected):
    """The reasons a layout is not ready to publish: missing mandatory elements and protected layers it draws. [] means ready. Pure."""
    problems = []
    if missing:
        problems.append("missing " + ", ".join(missing))
    problems.extend(f"draws '{p['layer']}', tagged {p['level']}" + (f" ({p['reason']})" if p.get("reason") else "") for p in protected)
    return problems


def protected_preview(tool_name, arguments, protected, problems=(), reason=None, overwrite_note=""):
    """The PREVIEW_REQUIRED result (the same confirm card an overwrite uses) for an export that draws protected layers or, for a publication
    export, has problems. Pure. `confirmed` is set only by the user's Apply button; the model cannot set it, so it cannot skip this card."""
    parts = []
    if protected:
        parts.append("draws protected layer(s) " + "; ".join(f"'{p['layer']}' ({p['level']})" for p in protected))
    if problems and not protected:
        parts.append("has problems: " + "; ".join(problems))
    what = " and ".join(parts) or "has problems"
    why = f" Reason given for publishing anyway: {reason}." if reason else ""
    extra = f" {overwrite_note}" if overwrite_note else ""
    return {
        "status": "PREVIEW_REQUIRED",
        "requires_confirmation": True,
        "is_destructive": False,
        "tool_name": tool_name,
        "arguments": {**arguments, "confirmed": True},
        "code_snippet": f"# {tool_name} would write a map that {what}",
        "rationale": f"Export Preview: this map {what}. Applying writes a file that can be shared.{why}{extra}",
        "message": f"Confirmation required before exporting a map that {what}.",
    }


def write_publication_record(output_path, layout_name, problems, reason):
    """Writes `<output>.publication.json` beside an export that went out with problems, so the reason travels with the file. Returns the path, or None."""
    path = output_path + ".publication.json"
    record = {"layout": layout_name, "file": output_path, "written": time.strftime("%Y-%m-%d %H:%M:%S"),
              "problems_at_export": problems, "reason_given": reason}
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
    except OSError:
        return None
    return path


def export_report(layers_drawn, ids_present):
    """The fields an export result should carry: {} when there is nothing to say. Pure apart from reading each layer's sensitivity tag."""
    notes = protected_layer_notes(layers_drawn, "it is drawn on this exported map -- confirm the file is meant to be shared before distributing it.")
    missing = missing_elements(ids_present)
    report = {}
    if notes:
        report["protected_layers"] = [{"layer": p["layer"], "level": p["level"]} for p in protected_in(layers_drawn)]
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


def gate_export(layout, tool_name, arguments, purpose, override_reason, confirmed, will_overwrite):
    """None when the export may go ahead; otherwise the result to return instead (a confirm card, or an error asking for a reason).

    - A protected layer drawn on the map: confirm card (owner decision, 2026-10-24: not a hard block). Skipped once `confirmed`.
    - purpose='publication': a missing mandatory element or a protected layer is a problem. Without a user-given `override_reason` the export is
      refused with the problems listed; with one, the confirm card shows the reason. Skipped once `confirmed`.
    `confirmed` comes only from the user's Apply button, so the model cannot skip either step."""
    if confirmed:
        return None
    ids = [i.id() for i in layout.items() if hasattr(i, "id") and i.id()]
    protected = protected_in(layers_drawn(layout))
    publishing = str(purpose or "").lower() == "publication"
    problems = publication_problems(missing_elements(ids), protected) if publishing else []
    if problems and not (override_reason or "").strip():
        return {"error": "Not ready to publish: " + "; ".join(problems) + ". Fix these, or ask the user whether to export anyway and why, "
                         "then call again with their reason as override_reason. The file was not written.",
                "problems": problems}
    if protected or problems:
        note = "The file already exists and will be replaced." if will_overwrite else ""
        return protected_preview(tool_name, arguments, protected, problems, (override_reason or None) if problems else None, note)
    return None


def build_time_preview(tool_name, arguments, output_path):
    """For create_print_layout, which builds and exports in one call: the confirm card when the layers about to be drawn include a protected one
    and a file is to be written; else None. The layout does not exist yet, so the layers ticked in the project stand in for its map."""
    if not output_path:
        return None
    protected = protected_in(checked_project_layers())
    return protected_preview(tool_name, arguments, protected) if protected else None


def checked_project_layers():
    """The layers ticked in the project: what a new standard layout's map will draw. Never raises."""
    if not QGIS_AVAILABLE:
        return []
    try:
        return list(QgsProject.instance().layerTreeRoot().checkedLayers())
    except Exception:
        return []


def _with_extra(layers, extra):
    """`layers` plus `extra`, each layer once (by id)."""
    seen, out = set(), []
    for layer in [*layers, *extra]:
        if layer is not None and layer.id() not in seen:
            seen.add(layer.id())
            out.append(layer)
    return out


def layout_export_report(layout, extra_layers=()):
    """export_report() for a real layout (plus any `extra_layers` the export also uses, such as an atlas coverage layer). Never raises: a note that
    cannot be built is left out, the export result stays as it was."""
    try:
        ids = [i.id() for i in layout.items() if hasattr(i, "id") and i.id()]
        return export_report(_with_extra(layers_drawn(layout), extra_layers), ids)
    except Exception:
        return {}


def atlas_gate(layout, coverage_layer, arguments, confirmed):
    """None when an atlas export may go ahead, else the confirm card. An atlas writes one file per coverage feature, so the coverage layer counts
    as drawn as well as the layers on the map (PLAN-011 phase D: export_layout_atlas was the one layout export without the phase B gate)."""
    if confirmed:
        return None
    protected = protected_in(_with_extra(layers_drawn(layout), [coverage_layer]))
    return protected_preview("export_layout_atlas", arguments, protected) if protected else None
