"""One advisory note per protected layer for the tools added since package C that put layer data somewhere a person may share it.

The older export tools append `export_warning_for(layer)` (models/sensitivity.py) to their result; package_layers_offline, add_layout_chart and
set_layout_atlas did not, found by the 2026-10-16 integration audit. Advisory only, like the original: nothing is blocked. Uses the same
RESTRICTED / SENSITIVE rule, so the two cannot disagree about which layers are protected."""
from ...models.sensitivity import get_layer_sensitivity

_PROTECTED = ("RESTRICTED", "SENSITIVE")


def protected_layer_notes(layers, what_happens):
    """[str] one note per layer tagged RESTRICTED or SENSITIVE; [] when none is or the tag cannot be read. Never raises."""
    notes = []
    for layer in layers or []:
        try:
            record = get_layer_sensitivity(layer)
        except Exception:
            record = {}          # an unreadable tag counts as no tag: this is an advisory note, never a gate
        level = record.get("level")
        if level in _PROTECTED:
            reason = record.get("reason")
            notes.append(f"'{layer.name()}' is tagged {level}{f' ({reason})' if reason else ''}: {what_happens}")
    return notes
