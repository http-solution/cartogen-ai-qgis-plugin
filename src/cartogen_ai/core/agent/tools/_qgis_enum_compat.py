# -*- coding: utf-8 -*-
"""Shared helper for QGIS's Qt5->Qt6 enum-scoping migration. Newer PyQGIS
(QGIS 4.x/Qt6) nests enum members under a named sub-enum (e.g.
QgsGraduatedSymbolRenderer.Mode.Jenks) while older PyQGIS (QGIS 3.x/Qt5) only
ever exposed them flat on the class itself (QgsGraduatedSymbolRenderer.Jenks).
Resolving both forms at runtime -- rather than guessing which one a given
install uses and rewriting to just that form -- is what closes the ~15-site
unscoped-enum risk flagged in docs/BUG_TRACKER.md BUG-2026-09-02-3 and the
2026-09-04 incomplete-code audit without needing a live QGIS session to
verify each one: a blanket rewrite to one literal form only works until this
plugin is run against the other QGIS major version, but resolving at import/
call time works on either.
"""


def resolve_qgis_enum(cls, nested_enum_name, member_name):
    """Returns cls.<nested_enum_name>.<member_name> if that resolves (the
    scoped/Qt6 form), else cls.<member_name> (the flat/Qt5 form), else None
    if neither exists on this QGIS install."""
    nested = getattr(cls, nested_enum_name, None)
    if nested is not None:
        value = getattr(nested, member_name, None)
        if value is not None:
            return value
    return getattr(cls, member_name, None)
