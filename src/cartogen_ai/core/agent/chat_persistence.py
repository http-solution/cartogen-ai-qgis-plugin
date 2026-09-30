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

from ...infrastructure.settings_keys import (
    SETTINGS_CHAT_HISTORY as CHAT_HISTORY_KEY,
    SETTINGS_PERSIST_CHAT_HISTORY as PERSIST_SETTING_KEY,
)



PERSIST_DEFAULT = True

# The full transcript lives in QgsProject.writeEntry storage, NOT in the custom property / project-variable
# slot the rolling window uses: on QGIS 4 that slot is customVariables(), which shows up in Project
# Properties > Variables, and a transcript of up to megabytes does not belong there. Entries are saved in
# the .qgz, are not shown in the variables UI, and work on QGIS 3 and 4.
TRANSCRIPT_SCOPE = "cartogen_ai"
TRANSCRIPT_KEY = "chat_transcript"
# Safety bounds so a very long project cannot bloat its own file without limit. These are NOT the
# retention policy (that is the project's lifetime); they only stop runaway growth. Oldest messages go first
# and the number dropped is recorded and reported in the data export.
MAX_TRANSCRIPT_MESSAGES = 2000
MAX_TRANSCRIPT_CHARS = 2_000_000


def is_persist_enabled() -> bool:
    """Whether the conversation is written into the project file at all.

    Default ON since 2026-09-30 (owner decision, recorded in IMPLEMENTATION_TRACKER 1.18): a mapping
    project has a purpose and a lifetime, and the conversation is part of its context. It was opt-in
    (default OFF) before, because a .qgz is a shareable artifact -- emailed, committed, uploaded -- and
    the conversation can reference sensitive data (humanitarian incident/security details, internal
    notes) that then travels with the map file. That risk is unchanged; it is now accepted by default
    and the user can turn it off in Settings > 'Save the conversation in the project file', and delete
    what is already saved from the Memory dialog."""
    if not QGIS_AVAILABLE:
        return False
    try:
        return bool(QgsSettings().value(PERSIST_SETTING_KEY, PERSIST_DEFAULT, type=bool))
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


def _attach_timestamps(history, previous_entries, user_ts=None) -> list:
    """Pairs each {"role", "content"} message in `history` (the plain
    API-shaped list agent_orchestrator.py's conversation_history actually is -- see
    agent_orchestrator.py's run(), which extends it straight into an LLM `messages` list)
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
    suffix of (see agent_orchestrator.py's _trim_history, which drops from the front),
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
        # rc7 smoke test F25: every message new since the last save used to get the SAME `now`
        # (the moment the reply finished), so a user message was stamped minutes after it was sent.
        # A new user message takes the time it was actually sent, when the caller knows it.
        fresh = user_ts if (entry.get("role") == "user" and user_ts) else now
        result.append({"role": entry.get("role"), "content": entry.get("content"), "ts": ts or fresh})
    return result


def save_chat_history(history, user_ts=None) -> bool:
    """Persists the conversation history list into the active project --
    only if the user has opted in (see is_persist_enabled). Attaches a real
    per-message timestamp (see _attach_timestamps) before writing, without
    mutating the caller's `history` list itself -- that list is agent_orchestrator.py's
    live conversation_history, which gets extended straight into the next
    LLM `messages` call, so it must stay exactly {"role", "content"} pairs
    with no extra keys added to it in place."""
    if not QGIS_AVAILABLE or not is_persist_enabled():
        return False
    try:
        timestamped = _attach_timestamps(history, _load_raw_entries(), user_ts=user_ts)
        ok = set_project_custom_property(
            QgsProject.instance(), CHAT_HISTORY_KEY, json.dumps(timestamped, default=str)
        )
        # The agent's window above is what restores the model's context; the transcript below is the full
        # record kept for the life of the project (and what "Export My Data" reports).
        save_chat_transcript(history, user_ts=user_ts)
        return ok
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
    straight into agent_orchestrator.py's conversation_history, which in turn gets
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


def load_chat_digest() -> list:
    """The stored conversation digest entries (role "system"), which load_chat_history*() deliberately
    filter out because they must not be fed back to an LLM as turns. They ARE stored text derived from
    earlier user messages (agent/history_manager.py keeps one extractive line per trimmed message), so
    a data export must include them: rc7 smoke test F25 found the export silently omitting them."""
    return [e for e in _load_raw_entries() if e.get("role") == "system" and e.get("content")]


def describe_retention(max_messages=None) -> dict:
    """What the chat_history part of a data export does and does not contain, stated inside the export
    itself so nobody reads it as something it is not (F25: an export with 8 messages from a 50-minute
    session looked like data loss; it was the agent's rolling window).

    Since 2026-09-30 the export carries the project's FULL stored transcript when one exists; the rolling
    window is only the fallback for projects that have no transcript (saving was off, or the conversation
    predates it)."""
    enabled = is_persist_enabled()
    doc = _read_transcript_document()
    stored = len([m for m in doc["messages"] if m.get("role") in ("user", "assistant") and m.get("content")])
    dropped = doc["dropped"]
    if stored:
        note = (f"Full stored conversation for this project: {stored} messages, kept for the life of the project "
                "in the project file. ")
        if dropped:
            note += (f"{dropped} older messages were dropped to keep the file from growing without limit "
                     f"(bounds: {MAX_TRANSCRIPT_MESSAGES} messages / {MAX_TRANSCRIPT_CHARS:,} characters). ")
        note += ("Saving is currently ON." if enabled else
                 "Saving is currently OFF (Settings), so nothing new is being added.")
        note += " chat_history_digest is the agent's short summary of turns older than its working window."
    elif not enabled:
        note = ("Saving the conversation in the project file is OFF (Settings), so nothing is stored and "
                "chat_history is empty by design.")
    else:
        kept = f"the most recent {max_messages} messages" if max_messages else "only the most recent messages"
        note = (f"No full transcript is stored for this project yet; chat_history holds {kept} of the agent's "
                "working window. Older messages, if any, are summarised under chat_history_digest.")
    return {"persistence_enabled": enabled, "max_messages_kept": max_messages,
            "transcript_messages": stored, "transcript_dropped": dropped, "note": note}


# ---- full transcript (project lifetime) --------------------------------------------------------------

def merge_into_transcript(transcript, window):
    """Append to `transcript` the messages in `window` that it does not hold yet. Pure.

    `window` is the agent's current history (role/content dicts, possibly starting with a role-"system"
    digest, which is skipped). It is always the tail of the full conversation so far plus this turn's
    new messages, so the new ones are found by the longest overlap between the end of the transcript and
    the start of the window. Returns (existing_transcript, new_messages)."""
    conv = [{"role": m.get("role"), "content": m.get("content")} for m in (window or [])
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")]
    have = [{"role": m.get("role"), "content": m.get("content")} for m in (transcript or [])]
    overlap = 0
    for k in range(min(len(have), len(conv)), 0, -1):
        if have[-k:] == conv[:k]:
            overlap = k
            break
    return list(transcript or []), conv[overlap:]


def apply_transcript_caps(messages, max_messages=None, max_chars=None):
    """Drop the OLDEST messages until both safety bounds hold. Returns (kept, dropped_count). Pure.
    Always keeps at least the newest message."""
    max_messages = MAX_TRANSCRIPT_MESSAGES if max_messages is None else max_messages
    max_chars = MAX_TRANSCRIPT_CHARS if max_chars is None else max_chars
    kept = list(messages)
    dropped = 0
    total = sum(len(str(m.get("content", ""))) for m in kept)
    while len(kept) > 1 and (len(kept) > max_messages or total > max_chars):
        total -= len(str(kept[0].get("content", "")))
        kept.pop(0)
        dropped += 1
    return kept, dropped


def _read_transcript_document() -> dict:
    """{"messages": [...], "dropped": int} as stored, or an empty one. Independent of the persist
    setting: what is on disk can be exported or deleted even after the setting is turned off."""
    empty = {"messages": [], "dropped": 0}
    if not QGIS_AVAILABLE:
        return empty
    try:
        raw, ok = QgsProject.instance().readEntry(TRANSCRIPT_SCOPE, TRANSCRIPT_KEY, "")
        if ok and isinstance(raw, str) and raw.strip():
            doc = json.loads(raw)
            if isinstance(doc, dict) and isinstance(doc.get("messages"), list):
                return {"messages": [m for m in doc["messages"] if isinstance(m, dict)],
                        "dropped": int(doc.get("dropped") or 0)}
    except Exception as e:
        print(f"[ChatPersistence] Failed to read chat transcript: {e}")
    return empty


def load_chat_transcript() -> list:
    """The full stored conversation for the open project: [{"role", "content", "ts"}]."""
    return [m for m in _read_transcript_document()["messages"]
            if m.get("role") in ("user", "assistant") and m.get("content")]


def save_chat_transcript(history, user_ts=None) -> bool:
    """Add this turn's new messages to the project's full transcript -- only when saving is enabled."""
    if not QGIS_AVAILABLE or not is_persist_enabled():
        return False
    try:
        doc = _read_transcript_document()
        existing = doc["messages"]
        _, new_messages = merge_into_transcript(existing, history)
        if not new_messages:
            return True
        stamped = _attach_timestamps(new_messages, [], user_ts=user_ts)
        kept, dropped = apply_transcript_caps(existing + stamped)
        payload = json.dumps({"version": 1, "dropped": doc["dropped"] + dropped, "messages": kept},
                             default=str, ensure_ascii=False)
        return bool(QgsProject.instance().writeEntry(TRANSCRIPT_SCOPE, TRANSCRIPT_KEY, payload))
    except Exception as e:
        print(f"[ChatPersistence] Failed to save chat transcript: {e}")
        return False


def clear_saved_chat_history() -> dict:
    """Delete everything saved for this project: the full transcript and the rolling window/digest. Does
    not touch the live in-memory conversation, and cannot reach copies of the project file already shared."""
    if not QGIS_AVAILABLE:
        return {"success": False, "removed": 0}
    removed = len(load_chat_transcript())
    ok = True
    try:
        QgsProject.instance().removeEntry(TRANSCRIPT_SCOPE, TRANSCRIPT_KEY)
    except Exception:
        ok = False
    try:
        set_project_custom_property(QgsProject.instance(), CHAT_HISTORY_KEY, "")
    except Exception:
        ok = False
    return {"success": ok, "removed": removed}
