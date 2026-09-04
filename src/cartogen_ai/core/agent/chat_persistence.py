# -*- coding: utf-8 -*-
"""
Project-Bound Chat History Persistence for Cartogen AI.
Saves/restores conversation history via QgsProject custom properties, so
reopening a .qgz project restores the AI conversation tied to it. Must only
be called from the main Qt thread -- QgsProject is not thread-safe.
"""

import datetime
import json

try:
    from qgis.core import QgsProject, QgsSettings
    from .qgis_compat import get_project_custom_property, set_project_custom_property
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

CHAT_HISTORY_KEY = "cartogen_ai/chat_history"
PERSIST_SETTING_KEY = "cartogen_ai/persist_chat_history"


def is_persist_enabled() -> bool:
    """Whether chat history should be written into the project file at all.
    Opt-in, default OFF: a .qgz project file is a shareable artifact --
    emailed, committed, uploaded -- and the conversation can reference
    sensitive data (humanitarian incident/security details, internal notes)
    the user never intended to travel with the map file itself. See Settings
    > 'Save chat history in project file'."""
    if not QGIS_AVAILABLE:
        return False
    try:
        return bool(QgsSettings().value(PERSIST_SETTING_KEY, False, type=bool))
    except Exception:
        return False


def _now_iso() -> str:
    """Naive local-time ISO timestamp -- deliberately the same format
    ui/chat_formatting.py's now_iso() uses (not UTC-aware), so a restored
    message's stored `ts` compares correctly against chat_formatting's
    `_relative_time()`, which assumes naive-vs-naive or aware-vs-aware, never
    a mix. This module can't import ui/chat_formatting.py directly (agent/
    code shouldn't depend on ui/ -- the existing cross-import goes the other
    way, ui/chat_tab_widget.py importing from here), so the format is
    duplicated rather than shared; keep the two in sync if either changes."""
    return datetime.datetime.now().isoformat()


def _load_raw_entries() -> list:
    """Internal: the raw persisted list of {"role", "content", "ts"} dicts,
    gated on is_persist_enabled() exactly like the old load_chat_history()
    was. Both load_chat_history() (API-shaped, ts stripped) and
    load_chat_history_with_timestamps() (UI-shaped, ts kept) build on this
    single read so there's one source of truth for "what's actually on disk"."""
    if not QGIS_AVAILABLE or not is_persist_enabled():
        return []
    try:
        raw = get_project_custom_property(QgsProject.instance(), CHAT_HISTORY_KEY, "")
        if isinstance(raw, str) and raw.strip():
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                return [e for e in loaded if isinstance(e, dict)]
    except Exception as e:
        print(f"[ChatPersistence] Failed to load chat history: {e}")
    return []


def _attach_timestamps(history, previous_entries) -> list:
    """Pairs each {"role", "content"} message in `history` (the plain
    API-shaped list agent.py's conversation_history actually is -- see
    agent.py's run(), which extends it straight into an LLM `messages` list)
    with a real timestamp: reuses the `ts` already on file for a message
    that was already persisted last save, and stamps `_now_iso()` only for a
    message that's genuinely new this turn.

    This is what fixes a real, live-reported bug: every restored chat bubble
    used to show "just now" (see ui/chat_tab_widget.py's old _add_message
    comment), because conversation_history itself never carried a timestamp
    and nothing else supplied one on restore. A leftover error bubble from an
    earlier turn or an earlier session -- e.g. a stale "[API error] Ollama
    connection failed" from before the user switched providers -- would then
    look like it had just happened, right next to a brand-new reply, which is
    exactly what a live user report described.

    `history` is always either identical to, or a monotonically-trimmed
    suffix of (see agent.py's _trim_history, which drops from the front),
    what was persisted last time it grew -- so matching by (role, content)
    and consuming previously-seen timestamps in FIFO order per key correctly
    threads old timestamps through even if the exact same text appears more
    than once (a real but rare case: relative order between duplicates of
    the same (role, content) pair is preserved by construction, since new
    entries are always appended, never inserted)."""
    pending = {}
    for entry in previous_entries:
        key = (entry.get("role"), entry.get("content"))
        pending.setdefault(key, []).append(entry.get("ts"))

    now = _now_iso()
    result = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        key = (entry.get("role"), entry.get("content"))
        bucket = pending.get(key)
        ts = bucket.pop(0) if bucket else None
        result.append({"role": entry.get("role"), "content": entry.get("content"), "ts": ts or now})
    return result


def save_chat_history(history) -> bool:
    """Persists the conversation history list into the active project --
    only if the user has opted in (see is_persist_enabled). Attaches a real
    per-message timestamp (see _attach_timestamps) before writing, without
    mutating the caller's `history` list itself -- that list is agent.py's
    live conversation_history, which gets extended straight into the next
    LLM `messages` call, so it must stay exactly {"role", "content"} pairs
    with no extra keys added to it in place."""
    if not QGIS_AVAILABLE or not is_persist_enabled():
        return False
    try:
        timestamped = _attach_timestamps(history, _load_raw_entries())
        return set_project_custom_property(
            QgsProject.instance(), CHAT_HISTORY_KEY, json.dumps(timestamped, default=str)
        )
    except Exception as e:
        print(f"[ChatPersistence] Failed to save chat history: {e}")
        return False


def load_chat_history() -> list:
    """Restores the conversation history list from the active project, if
    any -- only if the user has opted in. If persistence is off, any history
    already saved in the project (e.g. from before the user disabled this)
    is deliberately left unread rather than auto-deleted -- re-enabling the
    setting later shouldn't silently resurrect stale history, but this
    function also isn't the place to make a destructive delete decision on
    the user's behalf.

    Returns plain {"role", "content"} pairs with no `ts` key -- this feeds
    straight into agent.py's conversation_history, which in turn gets
    extended directly into an LLM `messages` list, and an extra key there
    isn't part of any provider's API contract. Use
    load_chat_history_with_timestamps() instead for anything display-only."""
    return [
        {"role": e.get("role"), "content": e.get("content")}
        for e in _load_raw_entries()
        if e.get("role") in ("user", "assistant") and e.get("content")
    ]


def load_chat_history_with_timestamps() -> list:
    """Same restored history as load_chat_history(), but keeping each
    entry's real `ts` (an ISO timestamp in _now_iso()'s format) instead of
    stripping it. For UI display only (see
    ui/chat_tab_widget.py._populate_initial_chat, which uses this to show a
    restored bubble's genuine relative age instead of "just now") -- never
    feed this into an LLM `messages` list; the extra `ts` key isn't part of
    any provider's API contract."""
    return [
        e for e in _load_raw_entries()
        if e.get("role") in ("user", "assistant") and e.get("content")
    ]
