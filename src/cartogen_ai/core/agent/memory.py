# -*- coding: utf-8 -*-
"""
Spatial Memory Manager for Cartogen AI.
Provides project-bound long-term spatial memory, sidecar SQLite database persistence,
and global user memory (via QgsSettings).
"""

import os
import json
import sqlite3
import traceback

try:
    from qgis.core import QgsProject, QgsSettings
    from .qgis_compat import get_project_custom_property, set_project_custom_property
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


PROJECT_MEMORY_KEY = "cartogen_ai/project_memory"
GLOBAL_MEMORY_KEY = "cartogen_ai/global_memory"


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class SpatialMemoryManager:
    """Manages short-term and long-term memory with sidecar SQLite database storage."""

    def __init__(self):
        self._in_memory_project_notes = {}
        self._in_memory_global_notes = {}
        self._in_memory_actions = []
        self._db_path = self._get_db_path()
        self._init_db()

    def _get_db_path(self) -> str:
        if QGIS_AVAILABLE:
            try:
                proj_path = QgsProject.instance().fileName()
                if proj_path:
                    base_dir = os.path.dirname(proj_path)
                    proj_name = os.path.splitext(os.path.basename(proj_path))[0]
                    return os.path.join(base_dir, f"{proj_name}_spatial_memory.sqlite")
            except Exception:
                pass
        
        home_dir = os.path.expanduser("~")
        return os.path.join(home_dir, "cartogen_ai_spatial_memory.sqlite")

    def _init_db(self):
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS spatial_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT,
                    key TEXT UNIQUE,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS spatial_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MemoryManager] SQLite init failed: {e}")

    def store_project_note(self, key: str, value: str) -> dict:
        """Stores a note in the active project scope and sidecar SQLite DB."""
        self._in_memory_project_notes[key] = value

        # Persist in SQLite sidecar DB
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO spatial_notes (scope, key, value) VALUES (?, ?, ?)",
                ("project", key, value)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MemoryManager] SQLite store failed: {e}")

        if QGIS_AVAILABLE:
            try:
                proj = QgsProject.instance()
                notes = self.get_project_notes()
                notes[key] = value
                set_project_custom_property(proj, PROJECT_MEMORY_KEY, json.dumps(notes))
            except Exception as e:
                print(f"[MemoryManager] Failed to persist project note: {e}")

        return {"success": True, "key": key, "value": value, "scope": "project", "db_path": self._db_path}

    def clear_project_notes(self) -> dict:
        """Clears all project-scoped notes from every storage location store_project_note
        writes to: the in-memory cache, the sidecar SQLite DB, and the QgsProject custom
        property. Symmetric with store_project_note -- clearing only one location would
        leave the note reappearing on next load."""
        self._in_memory_project_notes = {}

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM spatial_notes WHERE scope = 'project'")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MemoryManager] SQLite clear failed: {e}")

        if QGIS_AVAILABLE:
            try:
                set_project_custom_property(QgsProject.instance(), PROJECT_MEMORY_KEY, json.dumps({}))
            except Exception as e:
                print(f"[MemoryManager] Failed to clear project note property: {e}")

        return {"success": True, "scope": "project"}

    def get_project_notes(self) -> dict:
        """Retrieves all project notes from SQLite sidecar and project custom properties."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM spatial_notes WHERE scope = 'project'")
            rows = cursor.fetchall()
            conn.close()
            for k, v in rows:
                self._in_memory_project_notes[k] = v
        except Exception:
            pass

        if QGIS_AVAILABLE:
            try:
                raw = get_project_custom_property(QgsProject.instance(), PROJECT_MEMORY_KEY, "{}")
                if isinstance(raw, str) and raw.strip():
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        self._in_memory_project_notes.update(loaded)
            except Exception:
                pass

        return dict(self._in_memory_project_notes)

    def store_global_note(self, key: str, value: str) -> dict:
        """Stores a global preference note across sessions."""
        self._in_memory_global_notes[key] = value
        if QGIS_AVAILABLE:
            try:
                settings = QgsSettings()
                notes = self.get_global_notes()
                notes[key] = value
                settings.setValue(GLOBAL_MEMORY_KEY, json.dumps(notes))
            except Exception as e:
                print(f"[MemoryManager] Failed to persist global note: {e}")
        return {"success": True, "key": key, "value": value, "scope": "global"}

    def get_global_notes(self) -> dict:
        """Retrieves all global notes across QGIS sessions."""
        if QGIS_AVAILABLE:
            try:
                settings = QgsSettings()
                raw = settings.value(GLOBAL_MEMORY_KEY, "{}")
                if isinstance(raw, str) and raw.strip():
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        self._in_memory_global_notes.update(loaded)
            except Exception:
                pass
        return dict(self._in_memory_global_notes)

    def delete_global_note(self, key: str) -> dict:
        """Removes a single global note (used by the learning module's
        pref:*/rule:*/usage:* entries, and by the memory panel's "Forget"
        control -- store_global_note has no per-key delete counterpart today,
        and an editable memory panel needs one: a user has to be able to
        remove a wrong inferred preference or a stale correction rule
        without wiping every other global note via QgsSettings by hand."""
        self.get_global_notes()  # ensure in-memory cache is populated first
        existed = key in self._in_memory_global_notes
        self._in_memory_global_notes.pop(key, None)
        if QGIS_AVAILABLE:
            try:
                settings = QgsSettings()
                settings.setValue(GLOBAL_MEMORY_KEY, json.dumps(self._in_memory_global_notes))
            except Exception as e:
                print(f"[MemoryManager] Failed to persist global note deletion: {e}")
        return {"success": True, "key": key, "existed": existed, "scope": "global"}

    def log_spatial_action(self, action: str, details: str):
        """Logs a completed spatial processing step to SQLite DB and memory."""
        entry = {"action": action, "details": details}
        self._in_memory_actions.append(entry)
        if len(self._in_memory_actions) > 50:
            self._in_memory_actions = self._in_memory_actions[-50:]

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO spatial_actions (action, details) VALUES (?, ?)", (action, details))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_action_history(self) -> list:
        return list(self._in_memory_actions)

    def get_formatted_memory_context(self) -> str:
        """Formats active memory into a markdown block for agent system prompt injection.

        Global notes are bucketed by key prefix (pref:/rule:/usage:) rather than
        dumped into one flat "User Global Preferences" list -- see agent/learning.py,
        which is what actually writes pref:*/rule:*/usage:* entries via
        store_global_note/get_global_notes. Splitting them here gives the model (and
        the memory panel in tasks_tab_widget.py, which renders this same string)
        clearly labeled sections instead of a mix of raw keys. Any pre-existing
        global note that predates this categorization (no recognized prefix) still
        renders under "User Global Preferences" exactly as before, so nothing already
        stored is silently hidden by this change."""
        proj_notes = self.get_project_notes()
        glob_notes = self.get_global_notes()
        actions = self.get_action_history()[-5:]

        preferences = {k[len("pref:"):]: v for k, v in glob_notes.items() if k.startswith("pref:")}
        rules = {k: v for k, v in glob_notes.items() if k.startswith("rule:")}
        usage = {k[len("usage:"):]: v for k, v in glob_notes.items() if k.startswith("usage:")}
        other_notes = {
            k: v for k, v in glob_notes.items()
            if not (k.startswith("pref:") or k.startswith("rule:") or k.startswith("usage:"))
        }

        lines = ["## \U0001f9e0 SPATIAL MEMORY CONTEXT"]

        if proj_notes:
            lines.append("### Project Notes:")
            for k, v in proj_notes.items():
                lines.append(f"- **{k}**: {v}")
        else:
            lines.append("### Project Notes: (None stored)")

        if preferences:
            lines.append("### Learned Preferences (auto-detected -- treat as a soft default, not a hard rule):")
            for k, v in preferences.items():
                lines.append(f"- **{k}**: {v}")

        if rules:
            lines.append("### Correction Rules (from past user corrections -- follow these):")
            # Sorted so the most recently added rule (highest index) reads last,
            # i.e. most-recent-and-most-likely-relevant ends up closest to the
            # rest of the prompt the model attends to most.
            for k in sorted(rules, key=lambda rk: (len(rk), rk)):
                lines.append(f"- {rules[k]}")

        if usage:
            lines.append("### Usage Patterns (most-used first, for context only -- not an instruction to keep using them):")
            top_usage = sorted(usage.items(), key=lambda kv: _safe_int(kv[1]), reverse=True)[:5]
            for k, v in top_usage:
                lines.append(f"- **{k}**: used {v} times")

        if other_notes:
            lines.append("### User Global Preferences:")
            for k, v in other_notes.items():
                lines.append(f"- **{k}**: {v}")

        if actions:
            lines.append("### Recent Spatial Operations Executed:")
            for act in actions:
                lines.append(f"- `{act['action']}`: {act['details']}")

        return "\n".join(lines)
