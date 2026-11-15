"""One advisory note per protected layer for the tools added since package C that put layer data somewhere a person may share it.

The older export tools append `export_warning_for(layer)` (models/sensitivity.py) to their result; package_layers_offline, add_layout_chart and
set_layout_atlas did not, found by the 2026-10-16 integration audit. Advisory only, like the original: nothing is blocked. Uses the same
RESTRICTED / SENSITIVE rule, so the two cannot disagree about which layers are protected."""
from ..protection import effective_sensitivity

_PROTECTED = ("RESTRICTED", "SENSITIVE")


def protected_layer_notes(layers, what_happens, all_layers=None):
    """[str] one note per layer that is RESTRICTED or SENSITIVE, by its own tag or through lineage (PLAN-016 item 2); [] when none is or the
    tag cannot be read. Never raises."""
    if all_layers is None:
        try:
            from qgis.core import QgsProject
            all_layers = list(QgsProject.instance().mapLayers().values())
        except Exception:
            all_layers = []
    notes = []
    for layer in layers or []:
        try:
            record = effective_sensitivity(layer, all_layers)
        except Exception:
            record = {}          # an unreadable tag counts as no tag: this is an advisory note, never a gate
        level = record.get("level")
        if level in _PROTECTED:
            reason = record.get("reason")
            origin = f"derived from '{record['derived_from']}' ({level})" if record.get("derived_from") else f"tagged {level}{f' ({reason})' if reason else ''}"
            notes.append(f"'{layer.name()}' is {origin}: {what_happens}")
    return notes
