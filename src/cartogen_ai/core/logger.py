# -*- coding: utf-8 -*-
"""
Centralized Logging Infrastructure for Cartogen AI.

Routes diagnostic, warning, and error messages to QgsMessageLog when running inside QGIS,
falling back gracefully to standard Python logging / sys.stderr in headless or test environments.
"""

import re
import sys

# P1 fix, 2026-09-20 audit: log_info/log_warning/log_error used to forward
# whatever string a caller built -- including tool arguments and tool results,
# which can embed a provider API key (e.g. a script argument or a config dict
# a tool was handed), a bearer token, or a password. Centralized here so every
# call site is covered without having to remember to sanitize at each one.
# Deliberately pattern-based rather than an allowlist of "safe fields": the
# callers in agent_orchestrator.py/task_runner.py pass free-form strings
# (str(arguments), str(tool_result)), not structured data, so there's no
# schema to allowlist against -- this catches the shapes real secrets take.
_REDACTED = "***REDACTED***"
_SECRET_PATTERNS = [
    # Provider API key formats seen in this codebase's own providers/ clients.
    re.compile(r"sk-(?:or-v1-)?[A-Za-z0-9_-]{10,}"),  # OpenRouter / OpenAI-style
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),  # Google / Gemini
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),  # Anthropic / Claude
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    # Generic key=value / "key": "value" pairs whose key name says it's a
    # credential -- covers tool args/results carrying a dict-shaped secret
    # under a name this codebase itself uses (api_key, password, token, ...).
    re.compile(
        r"(?i)([\"']?(?:api[_-]?key|apikey|password|passwd|secret|token|auth[_-]?token)[\"']?\s*[:=]\s*[\"']?)"
        r"[^\s\"',}]+"
    ),
]


def _redact(message: str) -> str:
    text = str(message)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + _REDACTED, text)
        else:
            text = pattern.sub(_REDACTED, text)
    return text


try:
    from qgis.core import QgsMessageLog, Qgis
    QGIS_LOG_AVAILABLE = True
except ImportError:
    QGIS_LOG_AVAILABLE = False
    class Qgis:
        Info = 0
        Warning = 1
        Critical = 2
        Success = 3

TAG = "CartogenAI"


def log_info(message: str, tag: str = TAG) -> None:
    """Logs an informational message to QgsMessageLog."""
    message = _redact(message)
    if QGIS_LOG_AVAILABLE:
        try:
            QgsMessageLog.logMessage(message, tag, Qgis.Info)
            return
        except Exception:
            pass
    print(f"[{tag}] {message}", file=sys.stdout)


def log_warning(message: str, tag: str = TAG) -> None:
    """Logs a warning message to QgsMessageLog."""
    message = _redact(message)
    if QGIS_LOG_AVAILABLE:
        try:
            QgsMessageLog.logMessage(message, tag, Qgis.Warning)
            return
        except Exception:
            pass
    print(f"[{tag}] WARNING: {message}", file=sys.stderr)


def log_error(message: str, tag: str = TAG) -> None:
    """Logs an error message to QgsMessageLog."""
    message = _redact(message)
    if QGIS_LOG_AVAILABLE:
        try:
            QgsMessageLog.logMessage(message, tag, Qgis.Critical)
            return
        except Exception:
            pass
    print(f"[{tag}] ERROR: {message}", file=sys.stderr)
