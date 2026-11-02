"""export_workflow_file: write a shareable workflow file from the recorded history of one or more result layers (PLAN-048 stage 2).

The model can call it; it never writes without a person's yes. The first call returns the whole file as a preview (the usual PREVIEW_REQUIRED card);
only the person's Confirm runs it again with `confirmed` and writes. There is deliberately NO tool that opens or runs a workflow file: that is the
person's own action (stage 3), so a document the model reads cannot load one.

Building the document is pure and lives in core/agent/workflow_export.py; this module only reads the project, picks a path and writes.
Unverified by hand; the live test is CI only."""
import json
import os

from ... import tool_operations
from .. import workflow_export, workflow_file
from .registry import TOOLS_SCHEMA, register_tool
from . import export_tools as _ex
from ._paths import resolve_output_path

try:
    from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

EXTENSION = ".cgworkflow.json"
_PREVIEW_CHARS = 8000


def _lookup(name):
    layers = QgsProject.instance().mapLayersByName(name) if QGIS_AVAILABLE else []
    return layers[0] if layers else None


def _layer_info(name):
    """{"kind", "geometry", "fields"} of a loaded layer, for the role description. Field NAMES only, never values."""
    layer = _lookup(name)
    if layer is None:
        return None
    if not isinstance(layer, QgsVectorLayer):
        return {"kind": "raster"}
    geometry = {QgsWkbTypes.PointGeometry: "point", QgsWkbTypes.LineGeometry: "line", QgsWkbTypes.PolygonGeometry: "polygon"}.get(layer.geometryType())
    return {"kind": "vector", "geometry": geometry, "fields": list(layer.fields().names())}


def layer_info(name):
    """Public form of _layer_info for the import dialog: {"kind", "geometry", "fields"} of a loaded layer, or None."""
    return _layer_info(name)


def project_layers():
    """[(layer name, info)] for every layer in the open project, in name order. MAIN THREAD."""
    if not QGIS_AVAILABLE:
        return []
    names = sorted({layer.name() for layer in QgsProject.instance().mapLayers().values()})
    return [(n, _layer_info(n) or {}) for n in names]


def _target_path(output_path, document):
    path = resolve_output_path(output_path)
    if not path:
        path = os.path.join(_ex._default_export_dir("exports/workflows"), _ex._sanitize_filename(document["name"]) + EXTENSION)
    lower = path.lower()
    if not lower.endswith(EXTENSION):
        base = path[:-5] if lower.endswith(".json") else path
        path = (base[:-len(".cgworkflow")] if base.lower().endswith(".cgworkflow") else base) + EXTENSION
    return path


def file_text(document):
    """The exact text written to disk. Pure."""
    return json.dumps(document, indent=1, ensure_ascii=False) + "\n"


@register_tool(
    "export_workflow_file",
    "Save the steps that made one or more result layers as a shareable workflow file (.cgworkflow.json) that a colleague can open, read and run on "
    "their own layers. Built only from the recorded history of the named layers: the tools used, their arguments, and the data sources. Layers the "
    "analysis started from become named roles that the colleague maps to their own layers; no data, file paths or credentials are written. A step "
    "that cannot be shared (a tool not on the shareable list, or an argument that looks like a file path) is left out and reported. The user sees "
    "the whole file and confirms before anything is written. output_path is optional: omit it to save under the project's exports/workflows folder.",
    {"type": "object", "properties": {
        "layer_names": {"type": "array", "items": {"type": "string"}, "description": "The result layer(s) whose history to export."},
        "name": {"type": "string", "description": "A short title for the workflow."},
        "description": {"type": "string", "description": "One or two sentences on what it does."},
        "output_path": {"type": "string"}}, "required": ["layer_names"]},
    keywords=["export this workflow", "export the workflow", "save the workflow as a file", "share this workflow", "share the workflow", "workflow file",
              "save these steps", "send the steps to a colleague", "share the method as a file"],
)
def export_workflow_file(layer_names, name=None, description=None, output_path=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    names = [n for n in (layer_names or []) if isinstance(n, str) and n.strip()]
    if not names:
        return {"error": "Give at least one layer name."}
    schemas = workflow_file.schemas_from(TOOLS_SCHEMA)
    title = (name or "").strip() or f"Workflow for {names[0]}"
    built = workflow_export.export_from_layers(names, _lookup, schemas, tool_operations.get_tool_operation_type, title, description or "", _layer_info)
    if built["document"] is None:
        return {"error": " ".join(built["problems"]), "skipped_steps": built["skipped"]}
    document = built["document"]
    path = _target_path(output_path, document)
    text = file_text(document)
    if not confirmed:
        shown = text if len(text) <= _PREVIEW_CHARS else text[:_PREVIEW_CHARS] + f"\n... ({len(text) - _PREVIEW_CHARS} more characters not shown)"
        replaces = _ex.overwrite_preview("export_workflow_file", {"layer_names": names, "name": title, "description": description or "", "output_path": path}, path)
        return {
            "status": "PREVIEW_REQUIRED", "requires_confirmation": True, "is_destructive": bool(replaces),
            "tool_name": "export_workflow_file",
            "arguments": {"layer_names": names, "name": title, "description": description or "", "output_path": path, "confirmed": True},
            "code_snippet": shown,
            "rationale": (f"Workflow File Preview: {len(document['steps'])} step(s), {len(document['roles'])} layer role(s), written to {path}"
                          + (" (REPLACES an existing file)" if replaces else "") + ". No data, file paths or credentials are in it."
                          + (f" {len(built['skipped'])} recorded step(s) are left out." if built["skipped"] else "")),
            "message": f"Confirmation required before writing the workflow file '{path}'.",
            "skipped_steps": built["skipped"], "warnings": built["warnings"],
        }
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as e:
        return {"error": f"Could not write the workflow file: {e}"}
    _ex.remember_written(path)
    return {"success": True, "output_path": path, "steps": len(document["steps"]), "roles": built["roles"], "fingerprint": built["fingerprint"],
            "skipped_steps": built["skipped"], "warnings": built["warnings"],
            "note": "Roles are filled in by whoever opens the file. The steps were not run again from the file."}
