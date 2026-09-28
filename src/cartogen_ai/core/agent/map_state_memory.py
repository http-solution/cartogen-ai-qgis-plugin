# -*- coding: utf-8 -*-
"""
Map design-state memory: the "what did we draw last time, and how" half of the
dual-memory ("operational history" + "design state") architecture proposed for
IMPLEMENTATION_TRACKER.md §1.16 ("smart mapping"), modeled on the MapMate
framework's persistent design-state memory (see that section for the citation
and the fuller research writeup).

Operational history already existed before this module: SpatialMemoryManager.
log_spatial_action (memory.py) records every tool call, called from
agent_orchestrator.py on each successful execution. This module is the other
half -- what output_role got what visual treatment -- so a follow-up request
producing a similar output (e.g. "do the same for the other district") can
replicate the prior look automatically instead of silently reverting to
STYLE_PROFILES' hardcoded default every single time, closing the "replicating
the same layer and context aware analysis visualization" gap flagged in
§1.16's own writeup.

Deliberately layered on top of the existing store_project_note/get_project_notes
API (memory.py), the same pattern services/learning.py already established for
its pref:*/rule:*/usage:* global notes -- no new storage plumbing, no new
persistence mechanism invented. Project-scoped (not global, unlike learning.py's
notes): what a health-facility buffer should look like on THIS map is a
property of this project, not a preference that should follow the user into an
unrelated project. Pure Python, no qgis.* imports, so it's unit-testable
without a QGIS environment -- see tests/test_map_state_memory.py.
"""
import json

_LAYOUT_PREFIX = "layout:"


def record_output(memory_manager, output_role, layer_id, layer_name, style_profile=None, properties=None):
    """Records the most recently produced layer's styling for output_role,
    returning whatever was recorded for that role before this call (or None)
    so a caller can react to a role being superseded (e.g. decluttering a
    now-stale layer -- not yet wired up, see §1.16's still-open UX question
    on presentation). memory_manager may be None (no active agent session,
    e.g. a standalone Processing-provider run outside the chat loop) -- a
    no-op that always returns None, never raises."""
    if memory_manager is None:
        return None
    key = f"{_LAYOUT_PREFIX}{output_role}"
    previous = recall_output(memory_manager, output_role)
    entry = {
        "layer_id": layer_id,
        "layer_name": layer_name,
        "style_profile": style_profile,
        "properties": properties or {},
    }
    memory_manager.store_project_note(key, json.dumps(entry))
    return previous


def recall_output(memory_manager, output_role):
    """Returns the {layer_id, layer_name, style_profile, properties} dict
    last recorded for output_role in this project, or None if nothing's
    been recorded yet (or memory_manager is None)."""
    if memory_manager is None:
        return None
    key = f"{_LAYOUT_PREFIX}{output_role}"
    raw = memory_manager.get_project_notes().get(key)
    if not raw:
        return None
    try:
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, dict) else None
    except (TypeError, ValueError):
        return None
