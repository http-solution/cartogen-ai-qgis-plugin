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

from ...logger import log_event
from ...models.sensitivity import get_layer_sensitivity
from ._sensitivity_notes import protected_layer_notes
from .map_profiles import sign_off_missing

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


# labels for the extra elements a profile may require (PLAN-014 phase 2b); the five above are the default requirement
ELEMENT_LABELS = {**MANDATORY_LAYOUT_ELEMENTS, "MAP_INFO": "map information line", "FOOTER": "footer", "BODY_TEXT": "summary text",
                  "INSET_MAP": "locator map"}
PROFILE_PROPERTY = "cartogen_ai/profile_json"
PROFILE_NAME_PROPERTY = "cartogen_ai/profile_name"


def missing_elements(ids_present, required=None):
    """Labels of the required layout elements whose ids are not in `ids_present`, in the order required. `required` is a list of item ids (a
    profile's required_elements); the default is the five mandatory ones. Pure."""
    present = set(ids_present or ())
    wanted = list(required) if required else list(MANDATORY_LAYOUT_ELEMENTS)
    return [ELEMENT_LABELS.get(item_id, item_id) for item_id in wanted if item_id not in present]


def profile_of(layout):
    """The profile stored on a layout by create_print_layout(profile=...), or {}. Never raises."""
    try:
        import json
        raw = layout.customProperty(PROFILE_PROPERTY)
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def merge_current_profile(stored, loaded):
    """The profile an export is judged by: the CURRENT file's requirements (required_elements, require_sign_off, export preset, file name pattern,
    COD flag) with the sign-off the layout was BUILT with. The sign-off line is printed in the footer when the layout is made, so whether the
    map shows a review is a fact about the layout, not about the file today; a review added to the file later needs the layout rebuilt. Pure."""
    merged = dict(loaded)
    merged.pop("sign_off", None)
    if (stored or {}).get("sign_off"):
        merged["sign_off"] = stored["sign_off"]
    return merged


def current_profile(layout):
    """(profile, note): the profile to judge `layout` by at export time (PLAN-016 item 1). A layout built with a named profile re-reads that file
    now, so a requirement added after the layout was made (A29 in the rc50 hand run: require_sign_off) applies. If the file is gone or no
    longer valid, the copy stored on the layout is used and `note` says why. A layout without a profile name keeps its stored copy. Never raises."""
    stored = profile_of(layout)
    try:
        name = layout.customProperty(PROFILE_NAME_PROPERTY)
    except Exception:
        name = None
    if not name:
        return stored, None
    from .map_profiles import load_profile
    loaded, problem = load_profile(name)
    if loaded is None:
        return stored, f"profile '{name}' could not be re-read ({problem}); the copy stored on the layout was used"
    return merge_current_profile(stored, loaded), None


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


def publication_problems(missing, protected, sign_off_missing=False):
    """The reasons a layout is not ready to publish: missing mandatory elements, protected layers it draws and (when its profile requires it)
    a missing reviewer sign-off. [] means ready. Pure."""
    problems = []
    if sign_off_missing:
        problems.append("reviewer sign-off missing (the profile requires a named, dated review with status Reviewed or Approved)")
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


def export_report(layers_drawn, ids_present, layout_problems=(), required=None, pcode_checks=()):
    """The fields an export result should carry: {} when there is nothing to say. Pure apart from reading each layer's sensitivity tag."""
    notes = protected_layer_notes(layers_drawn, "it is drawn on this exported map -- confirm the file is meant to be shared before distributing it.")
    missing = missing_elements(ids_present, required)
    report = {}
    if notes:
        report["protected_layers"] = [{"layer": p["layer"], "level": p["level"]} for p in protected_in(layers_drawn)]
    if missing:
        notes.append("This layout is missing: " + ", ".join(missing) + ". The file was written as it is.")
        report["missing_elements"] = missing
    if layout_problems:
        # PLAN-014 phase 1: geometry problems found from the item rectangles (layout_geometry_checks). Warnings only, like the rest.
        notes.append("Layout check: " + "; ".join(layout_problems) + ". The file was written as it is.")
        report["layout_problems"] = list(layout_problems)
    pcode_warning_notes, pcode_findings = pcode_notes(pcode_checks)
    if pcode_findings:
        notes.extend(pcode_warning_notes)
        report["pcode_findings"] = pcode_findings
    if notes:
        report["export_warnings"] = notes
    return report


PCODE_FIELD_ALIASES = ("admin3_pcode", "adm3_pcode", "admin2_pcode", "adm2_pcode", "admin1_pcode", "adm1_pcode")


def pcode_field_of(field_names):
    """The first admin P-code field among `field_names` (finest level first, case-insensitive), or None. Pure."""
    lowered = {str(n).lower(): n for n in field_names}
    return next((lowered[a] for a in PCODE_FIELD_ALIASES if a in lowered), None)


def pcode_notes(results):
    """(notes, findings) from [{layer, field, duplicates}] P-code checks: one note per layer with duplicate codes. Pure."""
    findings = [{"layer": r["layer"], "field": r["field"], "duplicates": r["duplicates"]} for r in results if r.get("duplicates")]
    notes = [f"COD check: '{f['layer']}' has {f['duplicates']} duplicated value(s) in {f['field']}; a join on it will be wrong." for f in findings]
    return notes, findings


def pcode_results(layers):
    """[{layer, field, duplicates}] for the drawn vector layers that have an admin P-code field. A layer that cannot be read is left out
    (advisory, never raises)."""
    from ...validators import pcode_validation
    out = []
    for layer in layers or []:
        try:
            if not hasattr(layer, "fields"):
                continue
            field = pcode_field_of(layer.fields().names())
            if field is None:
                continue
            result = pcode_validation.check_pcode_uniqueness(layer, pcode_field=field)
            if result.get("success"):
                out.append({"layer": layer.name(), "field": field, "duplicates": len(result.get("duplicate_pcodes", {}))})
        except Exception as exc:
            log_event("pcode_check_failed", error_class=type(exc).__name__)
    return out


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
    profile, _ = current_profile(layout)
    problems = (publication_problems(missing_elements(ids, profile.get("required_elements")), protected, sign_off_missing(profile))
                if publishing else [])
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
        from .layout_geometry_checks import layout_geometry_problems
        profile, _ = current_profile(layout)
        drawn = _with_extra(layers_drawn(layout), extra_layers)
        return export_report(drawn, ids, layout_geometry_problems(layout), profile.get("required_elements"),
                             pcode_results(drawn) if profile.get("cod_boundaries") else ())
    except Exception:
        return {}


def atlas_gate(layout, coverage_layer, arguments, confirmed):
    """None when an atlas export may go ahead, else the confirm card. An atlas writes one file per coverage feature, so the coverage layer counts
    as drawn as well as the layers on the map (PLAN-011 phase D: export_layout_atlas was the one layout export without the phase B gate)."""
    if confirmed:
        return None
    protected = protected_in(_with_extra(layers_drawn(layout), [coverage_layer]))
    return protected_preview("export_layout_atlas", arguments, protected) if protected else None
