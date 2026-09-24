# -*- coding: utf-8 -*-
"""
Cloud-provider egress gate -- the technical half of the DPO determination recorded in SECURITY.md
("DPIA determination and deployment constraints", 2026-09-24).

Scope, design and the decisions still open are in docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md;
read that first. In short: when the selected provider is NOT local, a tool call that touches a
protected layer is blocked (or, in warn mode, allowed with a warning) instead of letting that
layer's data flow into the request to the provider.

What this is, and is not:
- It prevents ACCIDENTS. Its mode lives in QgsSettings on the user's own machine, which that user
  can edit, so it does not stop someone who means to bypass it. Real organizational enforcement
  needs a managed configuration deployed outside this plugin.
- It is OFF by default. Nothing changes for anyone until a mode is chosen in Settings.
- This module is deliberately Qt-free and pure so it is unit-testable without QGIS, matching
  plan_gate.py. The QGIS-backed lookups (a layer's tag, its lineage) are passed in by the caller.

Only the tool-call route is covered here (the pre-dispatch check). The other routes to the provider
listed in the scope doc -- attachments, the prompt refiner's separate request, conversation history
after a provider switch, the result-serialization chokepoint -- are NOT gated yet.
"""

import ipaddress
from urllib.parse import urlparse

MODE_OFF = "off"
MODE_WARN = "warn"
MODE_ENFORCE = "enforce"
MODES = (MODE_OFF, MODE_WARN, MODE_ENFORCE)

# Levels that are protected regardless of mode strictness (see models/sensitivity.py).
PROTECTED_LEVELS = frozenset({"RESTRICTED", "SENSITIVE"})
# Levels an owner has explicitly declared safe to leave the machine.
OPEN_LEVELS = frozenset({"PUBLIC", "INTERNAL"})

# Tools whose arguments name a layer but which never read its data into their result: tagging a
# layer must work on a cloud provider (otherwise a layer could never be classified while on one),
# and the sensitivity tools return only the level/reason. Kept deliberately minimal -- each entry is
# a claim about what the tool returns, so an over-cautious list costs some friction while an
# over-generous one silently opens a route for data to leave.
EXEMPT_TOOLS = frozenset({"set_layer_sensitivity", "get_layer_sensitivity"})

# execute_pyqgis_script names layers as string literals inside the script, not as arguments, so
# the argument scan cannot see which it reads. The conservative rule is to treat every layer in
# the project as touched.
WHOLE_PROJECT_TOOLS = frozenset({"execute_pyqgis_script"})

_MAX_LINEAGE_DEPTH = 8
_MAX_ARG_DEPTH = 6


def is_local_endpoint(url) -> bool:
    """True only when the endpoint is on this machine or a private network: `localhost`, or an IP
    literal that is loopback, private (RFC 1918 / ULA) or link-local.

    Deliberately conservative and does NO DNS lookup. A hostname other than `localhost` is treated
    as non-local, because resolving it here would be slow, spoofable, and could change between the
    check and the request; a LAN-hosted server should be addressed by its IP. Malformed input, an
    empty URL and anything unrecognised are non-local -- the safe direction for a privacy gate.
    `http://localhost@evil.example/` and `http://127.0.0.1.evil.example/` are both non-local
    (urllib takes the real host after the `@`; the second is a hostname, not an IP literal).
    Reserved non-routable ranges that Python's `ipaddress` calls private (documentation ranges and
    the like) count as local; they cannot reach a public server."""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        host = urlparse(url if "://" in url else "//" + url).hostname
    except ValueError:
        return False
    if not host:
        return False
    host = host.strip("[]").lower()
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local)


def is_protected(level, strict: bool) -> bool:
    """RESTRICTED/SENSITIVE are always protected. An UNTAGGED layer (level None) is protected only
    in strict (fail-closed) mode. PUBLIC/INTERNAL are explicit owner declarations and never are."""
    if level in PROTECTED_LEVELS:
        return True
    if level is None:
        return bool(strict)
    return False


def is_loosening(current_level, new_level, strict: bool) -> bool:
    """True when re-tagging a layer from `current_level` to `new_level` would move it from
    protected to open. Such a change must not be something the model can do to itself: if it could,
    it could simply tag a sensitive layer PUBLIC and unblock the very call the gate just stopped."""
    return is_protected(current_level, strict) and new_level in OPEN_LEVELS


def collect_layer_names(value, known_names, _depth=0):
    """Every string in `value` (recursing through dicts and lists) that is exactly the name of a
    loaded layer. Matching on the *value* rather than on parameter names means this does not depend
    on each tool naming its layer parameter the same way, and it sees layer names nested inside a
    Processing `params` dict."""
    found = set()
    if _depth > _MAX_ARG_DEPTH:
        return found
    if isinstance(value, str):
        if value in known_names:
            found.add(value)
    elif isinstance(value, dict):
        for v in value.values():
            found |= collect_layer_names(v, known_names, _depth + 1)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            found |= collect_layer_names(v, known_names, _depth + 1)
    return found


def _protection_reason(name, get_level, get_sources, strict, seen, depth):
    """Why `name` is protected, or None if it is not.

    An explicit PUBLIC/INTERNAL tag on the layer itself wins outright -- that is how an
    anonymized/aggregated output is declared releasable even though it was derived from a
    protected source. Lineage only matters for a layer with no tag of its own (non-strict mode; in
    strict mode an untagged layer is protected without needing to look at its ancestors)."""
    level = get_level(name)
    if level in OPEN_LEVELS:
        return None
    if is_protected(level, strict):
        return "tagged " + level if level else "untagged (strict mode)"
    if depth >= _MAX_LINEAGE_DEPTH or name in seen:
        return None
    seen.add(name)
    for source in get_sources(name) or []:
        inherited = _protection_reason(source, get_level, get_sources, strict, seen, depth + 1)
        if inherited:
            return "derived from '%s' (%s)" % (source, inherited)
    return None


def find_protected(names, get_level, get_sources, strict):
    """{layer_name: reason} for every name in `names` that is protected."""
    protected = {}
    for name in sorted(names):
        reason = _protection_reason(name, get_level, get_sources, strict, set(), 0)
        if reason:
            protected[name] = reason
    return protected


def evaluate(*, mode, provider_is_local, tool_name, arguments, project_layer_names,
             get_level, get_sources, strict):
    """The decision for one tool call. Returns None when the call may proceed untouched, else
    {"action": "block" | "warn", "layers": {name: reason}, "result": <dict to hand the model>}."""
    if mode not in (MODE_WARN, MODE_ENFORCE) or provider_is_local or tool_name in EXEMPT_TOOLS:
        return None
    known = set(project_layer_names)
    if tool_name in WHOLE_PROJECT_TOOLS:
        touched = known
    else:
        touched = collect_layer_names(arguments, known)
    protected = find_protected(touched, get_level, get_sources, strict)
    if not protected:
        return None
    action = "block" if mode == MODE_ENFORCE else "warn"
    return {
        "action": action,
        "layers": protected,
        "result": _block_result(tool_name, protected) if action == "block" else None,
        "warning": _warning_text(tool_name, protected),
    }


def _layer_list(protected):
    return "; ".join("'%s' (%s)" % (n, r) for n, r in protected.items())


def _warning_text(tool_name, protected):
    return (
        "'%s' involved protected data (%s) while a non-local AI provider is selected, so that "
        "data may have been sent to it." % (tool_name, _layer_list(protected))
    )


def _block_result(tool_name, protected):
    return {
        "status": "EGRESS_BLOCKED",
        "requires_local_provider": True,
        "tool_name": tool_name,
        "layers": sorted(protected),
        "message": (
            "Blocked before running: '%s' would send protected data (%s) to a cloud AI provider, "
            "and this deployment restricts that to local inference. Do not retry this call with "
            "different arguments to get around this. Tell the user plainly that it needs a local "
            "provider (e.g. Ollama), or that the analysis should use only layers marked PUBLIC or "
            "INTERNAL (for example an aggregated or anonymized derivative they have released)."
            % (tool_name, _layer_list(protected))
        ),
    }


def check_failed_decision(tool_name):
    """The decision used when the gate's own machinery raised in enforce mode: block, and say why."""
    return {
        "action": "block",
        "layers": {},
        "result": {
            "status": "EGRESS_BLOCKED",
            "requires_local_provider": True,
            "tool_name": tool_name,
            "layers": [],
            "message": (
                "'%s' was blocked because the data-protection check could not be completed, and "
                "this deployment blocks rather than guesses. Tell the user; a local provider "
                "(e.g. Ollama) is not subject to this check." % tool_name
            ),
        },
        "warning": None,
    }


def _read_setting(key, default, type_=None):
    try:
        from qgis.core import QgsSettings
        s = QgsSettings()
        return s.value(key, default, type=type_) if type_ else s.value(key, default)
    except Exception:
        return default


def read_mode() -> str:
    """The configured mode, defaulting to OFF if unset, unreadable or not a known value."""
    from ...infrastructure.settings_keys import SETTINGS_EGRESS_GATE_MODE
    value = _read_setting(SETTINGS_EGRESS_GATE_MODE, MODE_OFF)
    return value if value in MODES else MODE_OFF


def read_strict() -> bool:
    from ...infrastructure.settings_keys import SETTINGS_EGRESS_GATE_STRICT
    return bool(_read_setting(SETTINGS_EGRESS_GATE_STRICT, False, bool))
