# -*- coding: utf-8 -*-
"""
QGIS Project File Tools for Cartogen AI.
"""

from .registry import register_tool

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


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
