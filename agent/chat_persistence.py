# -*- coding: utf-8 -*-
"""
Project-Bound Chat History Persistence for Cartogen AI.
Saves/restores conversation history via QgsProject custom properties, so
reopening a .qgz project restores the AI conversation tied to it. Must only
be called from the main Qt thread -- QgsProject is not thread-safe.
"""

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


def save_chat_history(history) -> bool:
    """Persists the conversation history list into the active project --
    only if the user has opted in (see is_persist_enabled)."""
    if not QGIS_AVAILABLE or not is_persist_enabled():
        return False
    try:
        return set_project_custom_property(
            QgsProject.instance(), CHAT_HISTORY_KEY, json.dumps(history, default=str)
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
    the user's behalf."""
    if not QGIS_AVAILABLE or not is_persist_enabled():
        return []
    try:
        raw = get_project_custom_property(QgsProject.instance(), CHAT_HISTORY_KEY, "")
        if isinstance(raw, str) and raw.strip():
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                return loaded
    except Exception as e:
        print(f"[ChatPersistence] Failed to load chat history: {e}")
    return []
