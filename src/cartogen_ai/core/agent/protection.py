"""Effective data protection of a layer: its own sensitivity tag, else the tag it inherits through lineage (PLAN-016 item 2).

Why: the cloud (egress) gate already follows lineage, so a merged or renamed copy of a SENSITIVE layer is gated there (GitHub #150), but the
export gate for print layouts read only a layer's own tag, so a map drawing such a copy would have exported with no confirmation card, and the
Sensitivity dialog said plain "untagged". Both now ask this module, which uses the egress gate's own chain walk (models/egress_gate.py
protection_chain), so the two gates cannot drift apart. Non-strict: an untagged layer with no protected ancestor is not protected. An explicit
PUBLIC or INTERNAL tag on the layer wins, as it does in the egress gate. Nothing here writes a tag; the inherited level is derived each time."""
from ..models import egress_gate, sensitivity
from .lineage import effective_source_names, get_layer_lineage

PROTECTED = ("RESTRICTED", "SENSITIVE")


def lookups(all_layers):
    """(get_level, get_sources) over the loaded layers, by layer name, as the egress gate wants them. Two layers sharing a name are judged by
    the stricter one (GitHub #150), and a source recorded by id still resolves after a rename."""
    all_layers = list(all_layers or [])
    by_name = {}
    for layer in all_layers:
        by_name.setdefault(layer.name(), []).append(layer)

    def get_level(name):
        return egress_gate.most_protective_level(sensitivity.get_layer_sensitivity(lyr).get("level") for lyr in by_name.get(name, []))

    def get_sources(name):
        out = []
        for lyr in by_name.get(name, []):
            for entry in get_layer_lineage(lyr):
                if isinstance(entry, dict):
                    out.extend(n for n in effective_source_names(entry, all_layers) if n not in out)
        return out

    return get_level, get_sources


def effective_sensitivity(layer, all_layers):
    """get_layer_sensitivity(layer) plus {'derived_from': name or None}. A layer with a tag of its own is returned as it is. An untagged layer
    whose lineage leads back to a RESTRICTED or SENSITIVE layer reports that level, 'derived from ...' as its reason and the tagged layer's
    name. Never raises: an unreadable layer counts as untagged (advisory callers) and the egress gate has its own fail-closed handling."""
    try:
        record = dict(sensitivity.get_layer_sensitivity(layer))
    except Exception:
        record = {"level": None, "reason": None}
    record.setdefault("derived_from", None)
    if record.get("level") is not None:
        return record
    try:
        get_level, get_sources = lookups(all_layers)
        own_sources = []
        for entry in get_layer_lineage(layer):
            if isinstance(entry, dict):
                own_sources.extend(n for n in effective_source_names(entry, list(all_layers or [])) if n not in own_sources)
        seen = {layer.name()}
        for source in own_sources:
            found = egress_gate.protection_chain(source, get_level, get_sources, False, seen, 1)
            if found and found[1] in PROTECTED:
                path = [layer.name(), *found[0]]
                return {"level": found[1], "reason": egress_gate.reason_from_chain(path, found[2]), "derived_from": found[0][-1]}
    except Exception:
        return record
    return record


def sensitivity_label(level, reason, derived_from):
    """The 'Current: ...' text of the Sensitivity dialog. A derived level says where it comes from instead of 'untagged'. Pure."""
    if level and derived_from:
        return f"Current: untagged, protected through lineage from '{derived_from}' ({level})"
    if level:
        return f"Current: {level}" + (f" ({reason})" if reason else "")
    return "Current: untagged"
