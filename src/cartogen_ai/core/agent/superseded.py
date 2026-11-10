"""Mark superseded (PLAN-072, master-list row HU-5 part 3, owner decision 2026-11-09): when a tool run creates a layer and an earlier result of the
SAME tool already holds that name, the earlier layer is kept and renamed '<name> (superseded)' instead of piling up under an identical name.

Why: QgsProject.addMapLayer() does not deduplicate by name, so a re-run of an analysis left two layers with the same name, and every later
tool that looks a layer up by name could land on the old one (63 addMapLayer call sites in 26 files; only the service-area tools replaced the
earlier result). Of the three options the owner chose "mark superseded" over "replace" (destroys the earlier result) and "group" (changes the
layer tree): nothing is deleted or moved, the layer id and its lineage, sensitivity and source records stay, and the newest result keeps the name.

Deliberately narrow, so a layer the user made is never touched:
  * only a layer whose own lineage says this plugin made it with the same tool as the new run (a user's layer, or another tool's output, is not touched);
  * never for the tools that load data (add_*, load_*, import_*, create_empty*): loading the same file twice is the user's choice, not a stale result;
  * only on the main dispatch path, where the layers present before the call are known (the two-phase fetch tools are not covered yet);
  * switched off by the QgsSettings value cartogen_ai/mark_superseded = false.
Never raises: a failure here must not fail a tool call that already succeeded."""
import contextlib

from ..logger import log_event
from .lineage import get_layer_lineage

try:
    from qgis.core import QgsSettings
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

SETTINGS_KEY = "cartogen_ai/mark_superseded"
SUPERSEDED_KEY = "cartogen_ai/superseded_by"        # layer custom property: the id of the layer that replaced this one
NEVER_TOOL_PREFIXES = ("add_", "load_", "import_", "create_empty")


def enabled():
    """True unless the user switched it off (cartogen_ai/mark_superseded = false). Outside QGIS: True."""
    if not QGIS_AVAILABLE:
        return True
    with contextlib.suppress(Exception):
        return bool(QgsSettings().value(SETTINGS_KEY, True, type=bool))
    return True


def tool_may_supersede(tool):
    """False for the tools that load data the user asked for (see the module docstring). Pure."""
    return bool(tool) and not str(tool).startswith(NEVER_TOOL_PREFIXES)


def pick_new_layer(matches, layers_before):
    """Which of the layers called by a created layer's name is the one this call made: the one whose id was not loaded before the call. Without
    `layers_before` (two-phase tools), or when every match was already there (the call changed an existing layer), the first match, as before.
    The old code always took the first match, which with duplicate names could be the OLD layer and put the new result's lineage on it. Pure."""
    matches = list(matches or [])
    if layers_before is not None:
        for layer in matches:
            if layer.id() not in layers_before:
                return layer
    return matches[0] if matches else None


def superseded_name(base, taken):
    """'<base> (superseded)', or '<base> (superseded 2)' and so on, the first not in `taken`. Pure."""
    candidate, n = f"{base} (superseded)", 2
    while candidate in taken:
        candidate = f"{base} (superseded {n})"
        n += 1
    return candidate


def _last_tool(layer):
    """(tool, timestamp) of the last lineage entry of `layer`, or (None, '') when it has none."""
    history = get_layer_lineage(layer)
    last = history[-1] if history and isinstance(history[-1], dict) else {}
    return last.get("tool"), str(last.get("timestamp") or "")


def older_outputs(matches, new_layer, tool, layers_before):
    """The layers called like `new_layer` that were already there before this call and whose own lineage says the same tool made them, oldest
    first. Empty for a tool that may not supersede, and when the layers present before the call are not known."""
    if layers_before is None or not tool_may_supersede(tool) or new_layer.id() in layers_before:
        return []
    older = []
    for layer in matches:
        if layer.id() == new_layer.id() or layer.id() not in layers_before:
            continue
        made_by, stamp = _last_tool(layer)
        if made_by == tool and not layer.customProperty(SUPERSEDED_KEY):
            older.append((stamp or "", layer))
    return [layer for _stamp, layer in sorted(older, key=lambda pair: pair[0])]


def mark_older(project, new_layer, tool, layers_before):
    """Renames the earlier same-tool results of `new_layer`'s name (see the module docstring). Returns [{'was': old name, 'now': new name}]; [] when
    nothing was superseded. Never raises."""
    renamed = []
    try:
        base = new_layer.name()
        for layer in older_outputs(list(project.mapLayersByName(base)), new_layer, tool, layers_before):
            taken = {other.name() for other in project.mapLayers().values()}
            new_name = superseded_name(base, taken)
            layer.setName(new_name)
            layer.setCustomProperty(SUPERSEDED_KEY, new_layer.id())
            renamed.append({"was": base, "now": new_name})
            log_event("layer_superseded", tag="Agent", tool=str(tool)[:60], status="ok")
    except Exception as e:
        log_event("swallowed_exception", tag="Agent", tool="mark_superseded", error_class=type(e).__name__, error=True)
    return renamed


def note(renamed):
    """The sentence the reply must relay when earlier results were superseded. Pure."""
    detail = "; ".join(f"'{r['was']}' is now '{r['now']}'" for r in renamed)
    return (f"An earlier result of this tool with the same name was kept and renamed ({detail}); the new result has the name. "
            "Nothing was deleted, and you can delete or hide the earlier one in the layer panel.")
