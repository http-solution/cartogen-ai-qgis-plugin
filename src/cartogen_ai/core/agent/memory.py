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

    def clear_global_notes(self) -> dict:
        """Clears every global note in one action -- the bulk counterpart to
        store_global_note()'s single-key writes. Added to close GDPR review finding F1
        (docs/GDPR_COMPLIANCE_REVIEW.docx): global memory had store_global_note()/
        get_global_notes() but no erasure path at all, unlike clear_project_notes()'s
        existing project-scope equivalent. Symmetric with clear_project_notes(): clears
        the in-memory cache and the QgsSettings-backed store together, since a partial
        clear would just have the note reappear on the next get_global_notes() call.
        (Ported from cartogen-ai, commit eee84eb, where this same finding was fixed
        first -- this repo's memory.py predates that repo's self-learning system, so it
        has no per-key delete_global_note()/pref:/rule:/usage: key scheme to reconcile;
        this is a plain bulk clear.)"""
        self._in_memory_global_notes = {}
        if QGIS_AVAILABLE:
            try:
                settings = QgsSettings()
                settings.setValue(GLOBAL_MEMORY_KEY, json.dumps({}))
            except Exception as e:
                print(f"[MemoryManager] Failed to clear global notes: {e}")
        return {"success": True, "scope": "global"}

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
        """Formats active memory into a markdown block for agent system prompt injection."""
        proj_notes = self.get_project_notes()
        glob_notes = self.get_global_notes()
        actions = self.get_action_history()[-5:]

        lines = ["## 🧠 SPATIAL MEMORY CONTEXT"]
        
        if proj_notes:
            lines.append("### Project Notes:")
            for k, v in proj_notes.items():
                lines.append(f"- **{k}**: {v}")
        else:
            lines.append("### Project Notes: (None stored)")

        if glob_notes:
            lines.append("### User Global Preferences:")
            for k, v in glob_notes.items():
                lines.append(f"- **{k}**: {v}")

        if actions:
            lines.append("### Recent Spatial Operations Executed:")
            for act in actions:
                lines.append(f"- `{act['action']}`: {act['details']}")

        return "\n".join(lines)
