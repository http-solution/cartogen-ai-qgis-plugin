# -*- coding: utf-8 -*-
"""
Which QGIS project a running agent turn belongs to (GitHub #147; audit F11).

The dock and the agent are cached across project switches, and a turn runs on a background QgsTask. Opening or clearing a project
reloaded the chat history and wiped the chat, but nothing told the turn already in flight, so its remaining tool calls could run
against the NEW project and its reply and history entries were written into it.

A generation counter is the minimal fix: a turn captures the number when it starts, plugin_main bumps it when the project is
cleared / read / the plugin unloads, and the agent loop, the tool entry point, the history writes and the chat completion callback
all compare. Pure Python (no QGIS import) so the control flow is unit tested offline; the real signals are wired in plugin_main.py
and have not been exercised in a live QGIS session.
"""
import threading

_lock = threading.Lock()
_generation = 0


def current():
    """The current project-session generation."""
    with _lock:
        return _generation


def invalidate():
    """The active project changed (cleared, read, plugin unloaded): every turn that captured an earlier generation is now stale."""
    global _generation
    with _lock:
        _generation += 1
        return _generation


def is_stale(captured):
    """True when `captured` (a value from current()) no longer matches the active project session. None means 'not bound'."""
    return captured is not None and captured != current()
