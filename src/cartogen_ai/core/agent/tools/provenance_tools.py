# -*- coding: utf-8 -*-
"""Provenance sidecar tools for Cartogen AI -- the agent-facing surface of
agent/provenance.py (point 17 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: a deterministic,
machine-readable JSON provenance record combining lineage.py's tool-chain
history with dataset_status.py's QA-gate status/history/checks, point 2).
See that module's own docstring for the full design.

get_provenance_record returns the record without touching disk;
write_provenance_sidecar writes it to a real JSON file -- beside the
layer's own on-disk source when one can be resolved, matching the
"sidecar" name, or to Desktop (same fallback convention already used by
export_tools.py's generate_report) when the layer has no real file to sit
beside, e.g. a scratch/memory layer."""

import json
import os

from .registry import register_tool
from .. import provenance as _prov

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


def _sanitize_filename(name):
    safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in str(name)).strip()
    return safe or "layer"


def _derive_sidecar_path(layer, output_path):
    """Returns (path, used_desktop_fallback). An explicit output_path
    always wins. Otherwise, tries to sit the sidecar beside the layer's
    own on-disk source (stripping a QGIS URI suffix like
    "|layername=..." off a GeoPackage/etc. source first) -- only when
    that source actually resolves to a real file, never a guessed path.
    Falls back to Desktop, named after the layer, when it doesn't (a
    scratch/"memory" layer's source has no real file to sit beside)."""
    if output_path:
        return output_path, False

    source = ""
    try:
        source = layer.source() or ""
    except Exception:
        source = ""
    base_path = source.split("|", 1)[0] if source else ""
    if base_path and os.path.isfile(base_path):
        return f"{base_path}.provenance.json", False

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.expanduser("~")
    return os.path.join(desktop, f"{_sanitize_filename(layer.name())}.provenance.json"), True


@register_tool(
    "get_provenance_record",
    "Read a layer's machine-readable provenance record without writing anything to disk: "
    "the QGIS version, its full tool-execution lineage (what tool chain produced/modified it, "
    "see get_layer_lineage-tracked history), and its QA-gate lifecycle status/history/checks "
    "(see get_dataset_status). Use this to inspect provenance in-conversation; use "
    "write_provenance_sidecar instead to save it as a real JSON file.",
    {
        "type": "object",
        "properties": {"layer_name": {"type": "string"}},
        "required": ["layer_name"],
    },
)
def get_provenance_record(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    record = _prov.build_provenance_record(layer)
    if "error" in record:
        return record
    return {"success": True, **record}


@register_tool(
    "write_provenance_sidecar",
    "Write a layer's machine-readable provenance record (QGIS version, tool-execution lineage, "
    "QA-gate status/history/checks) to a real JSON sidecar file -- named "
    "'<source_file>.provenance.json' beside the layer's own on-disk source when one can be "
    "resolved, or an explicit output_path when supplied. Falls back to a Desktop file named "
    "after the layer (with a warning in the result) for a layer with no real on-disk source, "
    "e.g. a scratch/memory layer.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "output_path": {
                "type": "string",
                "description": "Optional explicit file path for the sidecar. Omit to derive one from the layer's own source, or fall back to Desktop.",
            },
        },
        "required": ["layer_name"],
    },
)
def write_provenance_sidecar(layer_name, output_path=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    record = _prov.build_provenance_record(layer)
    if "error" in record:
        return record

    path, used_fallback = _derive_sidecar_path(layer, output_path)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
    except Exception as e:
        return {"error": f"Failed to write provenance sidecar: {e}"}

    result = {"success": True, "path": path, "record": record}
    if used_fallback:
        result["warning"] = (
            "Layer has no real on-disk source (a scratch/memory layer, or one QGIS "
            "couldn't resolve a file path for) -- wrote the sidecar to Desktop instead "
            "of beside the source data."
        )
    return result
