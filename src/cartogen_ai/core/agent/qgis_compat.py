# -*- coding: utf-8 -*-
"""
Cross-QGIS-version compatibility helpers.

QGIS 4.0 (Qt6 migration, released 2026-03-06) removed QgsProject.customProperty()/
setCustomProperty() -- verified directly against the current QGIS API docs (raw HTML,
not a summarized fetch): the QgsProject class reference no longer lists either method,
only customVariables()/setCustomVariables() (a QVariantMap bulk get/set). This plugin
declared qgisMinimumVersion=3.0 through qgisMaximumVersion=4.99 in metadata.txt when this was
written, so it needed to keep working on both APIs rather than picking one.

2026-09-24: QGIS 3.x support was dropped (metadata.txt now declares qgisMinimumVersion=4.2).
These helpers are deliberately KEPT: on QGIS 4.x they already take the 4.x path, so they cost
nothing, while replacing each call site with the literal 4.x form would need every site
re-verified live for no functional gain. The 3.x branches are now unsupported, untested
fallbacks -- not a statement that 3.x works.
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


def enum_member(name, *owners):
    """Resolve an enum member across the Qt5/Qt6 and QGIS 3/4 spellings.

    Qt6 (QGIS 4.0, released 2026-03-06) requires enum members to be reached
    through their enum type -- ``Qt.ItemDataRole.UserRole`` rather than
    ``Qt.UserRole`` -- and the same applies to QGIS's own sip enums. For most
    of them the scoped spelling also works on PyQt5, so the call sites just
    use it directly.

    QgsUnitTypes is the exception this helper exists for. Its members were
    reachable unscoped on QGIS 3 (``QgsUnitTypes.LayoutMillimeters``), while
    current API docs give the canonical types as ``Qgis.LayoutUnit`` and
    ``Qgis.DistanceUnit`` -- so neither a bare unscoped attribute nor one
    fixed scoped spelling is safe to hard-code across both majors.

    Each owner is searched directly, then one level into its nested enum
    types. The first hit wins. Resolve once at module import, not per call.
    """
    for owner in owners:
        if owner is None:
            continue
        found = getattr(owner, name, None)
        if found is not None:
            return found
        for attr in dir(owner):
            if not attr[:1].isupper():
                continue
            nested = getattr(owner, attr, None)
            if nested is None:
                continue
            found = getattr(nested, name, None)
            if found is not None:
                return found
    raise AttributeError(
        "enum member %r not found on any of: %s"
        % (name, ", ".join(getattr(o, "__name__", repr(o)) for o in owners if o is not None))
    )
