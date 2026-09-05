# -*- coding: utf-8 -*-
"""
QGIS Project File Tools for Cartogen AI.
"""

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


@register_tool(
    "save_project",
    "Save the current QGIS project (all layers, styles, and layout) to a .qgz/.qgs file. Use "
    "this as a checkpoint before a risky multi-step operation, or at the end of a task so the "
    "user's work is persisted.",
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
        return {"success": True, "file_path": project.fileName()}
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
