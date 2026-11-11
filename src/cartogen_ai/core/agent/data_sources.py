"""The data-source catalogue loader (PLAN-023 R1-8). The facts live in data_sources.json beside this module (read its `_about` for the fields); this file loads them, answers questions about them and checks them. Pure Python, no QGIS.

What reads it today, so nobody assumes more: stac_ops.ALLOWED_HOSTS (the hosts a STAC file may be read from) is built from the `asset_hosts` of `stac_search`; the persona readiness panel lists each persona's sources with how to get them; the persona checker rejects an unknown source id.
What does NOT read it yet: the size guards (check_download_size, allow_whole_country, local_data_loader.should_ask_before_download) and the egress gate keep their own code; the catalogue only RECORDS which guard covers each source and tests keep the record true. Making a guard ask because the catalogue says so would change what people
are asked, which is a decision for the owner, not a side effect of a catalogue."""
import json
import os

from ..logger import log_event

KINDS = ("file", "API", "STAC", "feed")
ACCESS = ("open", "free key", "licensed")
SIZE_CLASSES = ("small", "variable", "large")
SIZE_GUARDS = (None, "content_length", "whole_country_flag", "extract_ask")
EGRESS_CLASSES = ("none", "area", "text")
REQUIRED = ("id", "label", "personas", "kind", "access", "licence", "size_class", "size_guard", "egress_class", "egress_note", "hosts", "cache_folder", "tools")

_cache = {"data": None, "by_id": None}


def _data_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_sources.json")


def load():
    """The sources as a list of dicts. Cached. A missing or unreadable file reads as an empty catalogue and is logged, so the plugin still loads (what depends on it then fails closed: no STAC asset host is allowed)."""
    if _cache["data"] is not None:
        return _cache["data"]
    try:
        with open(_data_path(), encoding="utf-8") as fh:
            data = json.load(fh)["sources"]
    except Exception as e:
        log_event("could_not_load_data_sources_json", tag="DataSources", error_class=type(e).__name__, error=True)
        data = []
    _cache["data"] = data
    _cache["by_id"] = {s["id"]: s for s in data}
    return data


def get(source_id):
    load()
    return (_cache["by_id"] or {}).get(source_id)


def for_tool(tool_name):
    """The source a tool reads from, or None."""
    return next((s for s in load() if tool_name in s["tools"]), None)


def for_persona(persona_id):
    """The sources a persona's file lists, in catalogue order."""
    return [s for s in load() if persona_id in s["personas"]]


def asset_hosts(source_id):
    """frozenset of the hosts a file may be read from after a search of this source; empty for an unknown source or one without any."""
    return frozenset((get(source_id) or {}).get("asset_hosts") or ())


def access_text(source):
    """How a person gets the source, in plain words."""
    return {"open": "open", "free key": "needs a free key", "licensed": "licensed: bring your own file or key"}[source["access"]]


def lines_for_persona(persona_id):
    """Ready-made panel lines for a persona's sources: 'HDX (open)', 'NASA FIRMS active fires (needs a free key)'."""
    return [f"{s['label']} ({access_text(s)})" for s in for_persona(persona_id)]


def validate(sources, tool_names=None, persona_ids=None, persona_sources=None):
    """Problems with a list of source dicts as readable strings (empty = fine). `tool_names` is the set of registered tools, `persona_ids` the 15 persona ids and `persona_sources` {persona id: [source ids its file lists]}; a check that needs one is skipped when it is None. Pure."""
    problems, seen = [], set()
    for s in sources:
        sid = s.get("id", "?")
        problems += [f"{sid}: missing '{k}'" for k in REQUIRED if k not in s]
        if sid in seen:
            problems.append(f"{sid}: id appears twice")
        seen.add(sid)
        for key, allowed in (("kind", KINDS), ("access", ACCESS), ("size_class", SIZE_CLASSES), ("size_guard", SIZE_GUARDS), ("egress_class", EGRESS_CLASSES)):
            if key in s and s[key] not in allowed:
                problems.append(f"{sid}: {key} '{s[key]}' is not one of {allowed}")
        if (s.get("access") == "free key") != bool(s.get("credential")):
            problems.append(f"{sid}: a 'free key' source names its credential, and no other source does")
        for text_key in ("label", "licence", "egress_note"):
            if text_key in s and not str(s[text_key]).strip():
                problems.append(f"{sid}: '{text_key}' is empty")
        hosts = s.get("hosts") or []
        if not hosts:
            problems.append(f"{sid}: hosts is empty")
        problems += [f"{sid}: host '{h}' must be a bare lower-case host name" for h in hosts if h != h.lower() or "/" in h or ":" in h or " " in h or "." not in h]
        problems += [f"{sid}: asset host '{h}' is not in hosts" for h in s.get("asset_hosts") or [] if h not in hosts]
        if not s.get("tools"):
            problems.append(f"{sid}: tools is empty")
        elif tool_names is not None:
            problems += [f"{sid}: tool '{t}' is not a registered tool" for t in s["tools"] if t not in tool_names]
        if persona_ids is not None:
            problems += [f"{sid}: persona '{p}' does not exist" for p in s.get("personas", []) if p not in persona_ids]
        if persona_sources is not None:
            claimed = sorted(p for p, ids in persona_sources.items() if sid in ids)
            if sorted(s.get("personas", [])) != claimed:
                problems.append(f"{sid}: personas {sorted(s.get('personas', []))} differ from the persona files, which list it for {claimed}")
    return problems
