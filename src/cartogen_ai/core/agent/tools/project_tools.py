# -*- coding: utf-8 -*-
"""
QGIS Project File Tools for Cartogen AI.
"""

import os

from .registry import register_tool

try:
    from qgis.core import QgsProject, QgsLayerTreeModel
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _new_layer_tree_model(project):
    """QgsMapThemeCollection.createThemeFromCurrentState()/applyTheme() both
    take a QgsLayerTreeModel|None model param -- confirmed live against a
    real QGIS 4.2.2 install that passing None crashes the process outright
    (a hard exit, not a catchable Python exception), even though the type
    hint marks it nullable. Always build a real model instead -- point 16
    of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md."""
    return QgsLayerTreeModel(project.layerTreeRoot())


def memory_layer_warning(names):
    """The sentence that must accompany a successful save when some layers are temporary, or None when there are none.

    rc15 hand test D07 (2026-10-06): a save reported that all layers were persisted; after the project was reloaded the five
    500 m buffer polygons were gone, because a temporary (memory) layer is saved as a reference to a provider that no longer
    exists, not as data. The save itself is correct; the claim around it was not. Pure."""
    names = [n for n in (names or []) if n]
    if not names:
        return None
    listed = ", ".join(f"'{n}'" for n in names[:10]) + (f" and {len(names) - 10} more" if len(names) > 10 else "")
    return (f"The project file was written, but {len(names)} temporary layer(s) hold their data in memory only and will come back "
            f"EMPTY when the project is reopened: {listed}. Export each to a file (GeoPackage) if the data must survive.")


def _temporary_layer_names(project):
    """Names of the project's layers that live only in memory. Best-effort; an unreadable layer is skipped."""
    names = []
    for layer in project.mapLayers().values():
        try:
            is_memory = layer.providerType() == "memory" or (hasattr(layer, "isTemporary") and layer.isTemporary())
        except Exception:
            continue
        if is_memory:
            names.append(layer.name())
    return sorted(names)


@register_tool(
    "save_project",
    "Save the current QGIS project (all layers, styles, and layout) to a .qgz/.qgs file. Use "
    "this as a checkpoint before a risky multi-step operation, or at the end of a task so the "
    "user's work is persisted. Temporary (memory) layers are NOT saved with their data -- the result "
    "lists them and they must be exported to a file separately.",
    {
        "type": "object",
        "properties": {
            "output_path": {
                "type": "string",
                "description": "Absolute path to save to, e.g. 'C:/maps/analysis.qgz'. Omit to save to the project's current file path (if it has one).",
            },
        },
        "required": [],
    },
)
def save_project(output_path=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    project = QgsProject.instance()
    if output_path:
        project.setFileName(output_path)
    elif not project.fileName():
        return {"error": "This project has never been saved -- pass output_path to give it a file name."}

    try:
        if not project.write():
            return {"error": f"QGIS reported the project write failed for '{project.fileName()}'."}
        result = {"success": True, "file_path": project.fileName()}
        temporary = _temporary_layer_names(project)
        if temporary:
            result["temporary_layers"] = temporary
            result["warning"] = memory_layer_warning(temporary)
        return result
    except Exception as e:
        return {"error": f"save_project failed: {e}"}


@register_tool(
    "load_project",
    "Open a different QGIS project file, replacing everything currently loaded. Destructive: any "
    "unsaved changes in the current project are lost -- save_project first if they matter.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to a .qgz/.qgs project file."},
        },
        "required": ["file_path"],
    },
)
def load_project(file_path: str, confirmed: bool = False):
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "load_project",
            "arguments": {"file_path": file_path, "confirmed": True},
            "code_snippet": f"QgsProject.instance().read('{file_path}')",
            "rationale": f"Destructive Action Preview: Replace the currently open project with '{file_path}'. Unsaved changes in the current project will be lost.",
            "message": f"Confirmation required before loading '{file_path}' -- this replaces the current project.",
        }

    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    import os
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    try:
        project = QgsProject.instance()
        if not project.read(file_path):
            return {"error": f"QGIS could not open '{file_path}' as a project file."}
        return {"success": True, "file_path": file_path, "layer_count": len(project.mapLayers())}
    except Exception as e:
        return {"error": f"load_project failed: {e}"}


@register_tool(
    "create_map_theme",
    "Saves the current layer visibility/style state as a named map theme, so it can be "
    "restored later with apply_map_theme -- for producing several different map products "
    "(e.g. 'overview', 'health facilities only', 'roads and admin boundaries') from one "
    "project without manually toggling layer visibility every time. Point 16 of "
    "docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.",
    {
        "type": "object",
        "properties": {
            "theme_name": {"type": "string", "description": "Name for the saved theme."},
        },
        "required": ["theme_name"],
    },
)
def create_map_theme(theme_name: str):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    try:
        project = QgsProject.instance()
        themes = project.mapThemeCollection()
        model = _new_layer_tree_model(project)
        record = themes.createThemeFromCurrentState(project.layerTreeRoot(), model)
        themes.insert(theme_name, record)
        return {"success": True, "theme_name": theme_name, "existing_themes": themes.mapThemes()}
    except Exception as e:
        return {"error": f"create_map_theme failed: {e}"}


@register_tool(
    "apply_map_theme",
    "Restores a previously saved map theme (layer visibility and style), created with "
    "create_map_theme -- switches the project's current view between different named map "
    "product states.",
    {
        "type": "object",
        "properties": {
            "theme_name": {"type": "string"},
        },
        "required": ["theme_name"],
    },
)
def apply_map_theme(theme_name: str):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    project = QgsProject.instance()
    themes = project.mapThemeCollection()
    if not themes.hasMapTheme(theme_name):
        return {
            "error": f"Map theme '{theme_name}' not found.",
            "existing_themes": themes.mapThemes(),
        }
    try:
        model = _new_layer_tree_model(project)
        themes.applyTheme(theme_name, project.layerTreeRoot(), model)
        return {"success": True, "theme_name": theme_name}
    except Exception as e:
        return {"error": f"apply_map_theme failed: {e}"}


@register_tool(
    "list_map_themes",
    "Lists the names of every map theme saved in the current project via create_map_theme.",
    {"type": "object", "properties": {}},
)
def list_map_themes():
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    try:
        themes = QgsProject.instance().mapThemeCollection().mapThemes()
        return {"success": True, "themes": themes}
    except Exception as e:
        return {"error": f"list_map_themes failed: {e}"}


# IMPLEMENTATION_TRACKER.md §1.7, option (c), decided by Alaa 2026-09-24: an opt-in scaffolding
# tool, not an enforced/default convention. The plugin's actual users (humanitarian GIS analysts)
# frequently already work inside an org-mandated data structure they don't control (e.g. OCHA's
# own field conventions); imposing a second structure from inside a QGIS plugin would add friction
# without the standing to enforce it. This tool exists only for a user who explicitly wants the
# convention from docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md's point 28 (raw source
# data kept immutable/separate from staging/processed derivatives) and asks for it -- it creates
# nothing unless called, and never on its own initiative.
_PROJECT_FOLDER_LAYOUT = [
    "project/templates",
    "data/00_raw",       # Immutable source data -- never written to by processing/analysis steps.
    "data/10_staging",   # Normalized/reprojected copies derived from 00_raw.
    "data/20_processed", # Analysis outputs.
    "data/30_reference",  # CODs, gazetteers, P-codes, and other stable reference datasets.
    "data/40_raster",
    "styles",
    "models",
    "scripts/processing",
    "scripts/atlas",
    "scripts/validation",
    "exports/pdf",
    "exports/geospatial",
    "exports/web",
    "exports/field",
    "metadata",
    "logs",
]


@register_tool(
    "create_project_folder_structure",
    "Creates the recommended humanitarian-GIS project folder layout (data/00_raw for immutable "
    "source data, 10_staging/20_processed for derived work, plus styles/models/scripts/exports/"
    "metadata/logs) under a base directory. Opt-in only -- call this ONLY when the user explicitly "
    "asks for a standard project structure; never on your own initiative, since many users already "
    "work inside an org-mandated data structure this would duplicate. Never overwrites or deletes "
    "anything -- only creates folders that don't already exist.",
    {
        "type": "object",
        "properties": {
            "base_path": {
                "type": "string",
                "description": "Absolute path to the project root the folder structure should be created under, e.g. 'C:/projects/flood_response'. Created if it doesn't exist.",
            },
        },
        "required": ["base_path"],
    },
)
def create_project_folder_structure(base_path):
    if not base_path or not isinstance(base_path, str):
        return {"error": "base_path is required and must be a non-empty string."}

    created, already_existed = [], []
    try:
        for rel_dir in _PROJECT_FOLDER_LAYOUT:
            full_path = os.path.join(base_path, *rel_dir.split("/"))
            if os.path.isdir(full_path):
                already_existed.append(rel_dir)
            else:
                os.makedirs(full_path, exist_ok=True)
                created.append(rel_dir)
    except OSError as e:
        return {
            "error": f"create_project_folder_structure failed: {e}",
            "created_before_failure": created,
        }

    return {
        "success": True,
        "base_path": base_path,
        "created": created,
        "already_existed": already_existed,
        "message": (
            f"Created {len(created)} folder(s) under '{base_path}'"
            + (f" ({len(already_existed)} already existed, left untouched)" if already_existed else "")
            + ". Keep data/00_raw untouched -- work from data/10_staging onward."
        ),
    }
