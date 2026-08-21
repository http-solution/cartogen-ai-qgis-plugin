# -*- coding: utf-8 -*-
"""
Cross-QGIS-version compatibility helpers.

QGIS 4.0 (Qt6 migration, released 2026-03-06) removed QgsProject.customProperty()/
setCustomProperty() -- verified directly against the current QGIS API docs (raw HTML,
not a summarized fetch): the QgsProject class reference no longer lists either method,
only customVariables()/setCustomVariables() (a QVariantMap bulk get/set). This plugin
declares qgisMinimumVersion=3.0 through qgisMaximumVersion=4.99 in metadata.txt, so it
needs to keep working on both APIs rather than picking one.
"""


def get_project_custom_property(project, key, default=""):
    """QgsProject.customProperty() equivalent that works on both QGIS 3.x (native
    customProperty) and QGIS 4.x (customVariables() dict)."""
    try:
        return project.customProperty(key, default)
    except AttributeError:
        try:
            return project.customVariables().get(key, default)
        except Exception:
            return default


def set_project_custom_property(project, key, value):
    """QgsProject.setCustomProperty() equivalent that works on both QGIS 3.x (native
    setCustomProperty) and QGIS 4.x (customVariables() dict, read-modify-write since
    setCustomVariables() replaces the whole map rather than setting a single key)."""
    try:
        project.setCustomProperty(key, value)
        return True
    except AttributeError:
        try:
            variables = dict(project.customVariables())
            variables[key] = value
            project.setCustomVariables(variables)
            return True
        except Exception:
            return False
