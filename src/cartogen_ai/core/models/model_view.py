# -*- coding: utf-8 -*-
"""The one place that decides what the model may SEE about a layer (rc7 smoke test F21).

The egress gate (egress_gate.py) stops tool calls that read a protected layer's DATA from going to a cloud model.
It could not stop the layer's SCHEMA: get_layers and the map-context summary listed every layer's field names and
feature count to the model, so the model quoted the field names of a SENSITIVE layer that the gate was protecting.
OWASP LLM02 (sensitive information disclosure) asks for least privilege on what reaches the model; this module is that
rule, applied in one place so every tool that describes a layer goes through it instead of each one remembering to.

Rule: when the egress gate is in ENFORCE mode, the provider is not local, and the layer is protected
(egress_gate.is_protected: RESTRICTED/SENSITIVE, or untagged in strict mode), the layer's field names are withheld.
Its name, type, CRS and feature count stay visible: tools address layers by name, and a count is not a value.
In warn mode nothing is withheld (the gate itself lets the data through with a warning), and a local provider sees
everything (nothing leaves the machine).

Pure and Qt-free. The policy is read lazily through a provider function the agent registers, so switching provider
or gate mode in Settings takes effect on the next call without restarting.
"""
from . import egress_gate

SCHEMA_HIDDEN_NOTE = (
    "Field names are withheld from the cloud model for this protected layer. Ask the user to confirm the call, or "
    "switch to a local provider, if the field names are needed."
)

# What a cloud model still sees of ANY layer, protected or not, however the gate is set (owner decision 2026-10-04, #93:
# acceptable if declared and the user is told, with no sensitive values exposed). One text, shown in Settings, in the
# layer-sensitivity dialog and recorded in SECURITY.md, so the declaration cannot drift between places.
SCHEMA_DISCLOSURE = (
    "A cloud AI provider is always told each layer's NAME, geometry type, CRS and feature count, so it can address layers "
    "and plan. For layers protected by the data-protection setting it is not told the field names, and it never receives "
    "attribute values unless a tool call returns them (which the protection setting can block). Do not put sensitive "
    "information in a layer's name."
)

_policy_provider = None


def set_policy_provider(provider):
    """provider: a zero-argument callable returning (mode, provider_is_local, strict), or None to clear."""
    global _policy_provider
    _policy_provider = provider


def current_policy():
    """(mode, provider_is_local, strict); the gate-off default when no provider is registered or it fails."""
    if _policy_provider is None:
        return egress_gate.MODE_OFF, True, False
    try:
        mode, is_local, strict = _policy_provider()
        return mode, bool(is_local), bool(strict)
    except Exception:
        # A privacy rule that silently fails open is worse than one that over-hides: if the policy cannot be read,
        # hide. (The gate itself makes the same call for its own failure in enforce mode.)
        return egress_gate.MODE_ENFORCE, False, True


def masks_schema(level, policy=None):
    mode, is_local, strict = policy or current_policy()
    if mode != egress_gate.MODE_ENFORCE or is_local:
        return False
    return egress_gate.is_protected(level, strict)


def apply_to_layer_entry(entry, level, policy=None):
    """`entry` (a dict describing one layer, with an optional 'fields' list) as the model may see it."""
    if not isinstance(entry, dict) or not masks_schema(level, policy):
        return entry
    masked = dict(entry)
    if "fields" in masked:
        masked["fields"] = []
    masked["schema_hidden"] = True
    masked["schema_note"] = SCHEMA_HIDDEN_NOTE
    return masked
