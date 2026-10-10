# -*- coding: utf-8 -*-
"""
Centralized Logging Infrastructure for Cartogen AI.

Routes diagnostic, warning, and error messages to QgsMessageLog when running inside QGIS,
falling back gracefully to standard Python logging / sys.stderr in headless or test environments.
"""

import re
import sys
import time

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
    from qgis.core import QgsMessageLog, Qgis, QgsSettings
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
        except Exception:  # nosec B110 (best-effort: failure is non-fatal)
            pass
    print(f"[{tag}] {message}", file=sys.stdout)


def log_warning(message: str, tag: str = TAG) -> None:
    """Logs a warning message to QgsMessageLog."""
    message = _redact(message)
    if QGIS_LOG_AVAILABLE:
        try:
            QgsMessageLog.logMessage(message, tag, Qgis.Warning)
            return
        except Exception:  # nosec B110 (best-effort: failure is non-fatal)
            pass
    print(f"[{tag}] WARNING: {message}", file=sys.stderr)


def log_error(message: str, tag: str = TAG) -> None:
    """Logs an error message to QgsMessageLog."""
    message = _redact(message)
    if QGIS_LOG_AVAILABLE:
        try:
            QgsMessageLog.logMessage(message, tag, Qgis.Critical)
            return
        except Exception:  # nosec B110 (best-effort: failure is non-fatal)
            pass
    print(f"[{tag}] ERROR: {message}", file=sys.stderr)


# Structured, metadata-only logging -- product policy decision, 2026-09-20 audit
# (strict option chosen over regex-redacted free-form content): call sites that
# used to log raw prompt/response/tool-argument/tool-result text (even truncated
# and secret-redacted) now log ONLY safe structured fields through log_event
# below. _redact above stays in place on log_info/log_warning/log_error as
# defense-in-depth for anything else that still logs a free-form string, but it
# is deliberately no longer the primary control for tool/turn logging.
_SAFE_EVENT_FIELDS = {
    "tool", "status", "duration_ms", "correlation_id", "provider", "error_class", "count",
    # Startup state of behaviour-changing settings (F18) -- on/off or a mode name, never user content.
    "plan_validation_gate", "egress_gate_mode", "persist_chat",
    # classify_facilities_by_access phase timings -- counts and milliseconds only. rc11 smoke test: the event was
    # logged with these fields but this allowlist dropped them, so the line read just "classify_facilities_timing"
    # and the 124 s could not be broken down.
    "facilities", "reached_layers", "service_area_ms", "prepare_ms", "nearest_ms", "build_ms", "replace_ms",
    # isolated-script reconciliation: how many parts of a script's work could not be applied (a count)
    "problems",
    # model_call (core/agent/call_metrics.py): sizes, timings and tool NAMES of each request -- never prompt text, arguments or
    # results. est_* are character-count estimates; input/cached/output tokens are provider-reported (or absent).
    "call_index", "model", "latency_ms", "input_tokens", "cached_tokens", "output_tokens", "tool_count", "tool_calls", "outcome",
    "est_system_tokens", "est_tools_tokens", "est_history_tokens", "est_user_tokens", "tool_names",
}


def log_event(event: str, tag: str = TAG, error=False, **fields) -> None:
    """Structured, metadata-only logging for tool calls and agent turns --
    the default for anything that used to log raw content. Only pass safe
    fields: tool name, status, duration_ms, correlation_id, provider,
    error_class, counts -- NEVER raw prompt/response/tool-argument/tool-result
    content, file paths, coordinates, feature attributes, or personal data.
    Unrecognized field names are dropped (not silently passed through) so a
    future call site can't accidentally widen what gets logged just by
    passing a new kwarg -- extend _SAFE_EVENT_FIELDS deliberately instead."""
    parts = [event]
    for key, value in fields.items():
        if key not in _SAFE_EVENT_FIELDS:
            continue
        parts.append(f"{key}={value}")
    line = " ".join(parts)
    (log_error if error else log_info)(line, tag=tag)


def startup_state_fields(read_setting):
    """The on/off state of the settings that silently change behaviour, for one startup log line.

    rc7 smoke test F18: the plan-validation gate was ON in the operator's profile although they believed
    it untouched, which made every export make a wasted first call; nothing said so anywhere. `read_setting`
    is QgsSettings().value-like: (key, default) -> value. Never raises."""
    from ..infrastructure import settings_keys as k

    def flag(key, default):
        try:
            v = read_setting(key, default)
            return "ON" if str(v).lower() in ("true", "1", "yes") else "OFF"
        except Exception:
            return "unknown"

    def text(key, default):
        try:
            return str(read_setting(key, default))
        except Exception:
            return "unknown"

    return {
        "plan_validation_gate": flag(k.SETTINGS_PLAN_VALIDATION_GATE_ENABLED, False),
        "egress_gate_mode": text(k.SETTINGS_EGRESS_GATE_MODE, "off"),
        "persist_chat": flag(k.SETTINGS_PERSIST_CHAT_HISTORY, True),
    }


_DIAGNOSTIC_SETTING = "cartogen_ai/debug_verbose_logging_until"
_diagnostic_warning_shown = False
_DEFAULT_DIAGNOSTIC_DURATION_SECONDS = 3600  # 1 hour


def enable_diagnostic_logging(duration_seconds: int = _DEFAULT_DIAGNOSTIC_DURATION_SECONDS) -> None:
    """Turns on log_diagnostic() output for the next duration_seconds (default
    1 hour), then it automatically expires on its own. Second-review correction,
    2026-09-20: a plain boolean toggle doesn't meet the "explicit, TIME-BOUND
    diagnostic mode" policy -- a developer could flip it on and forget to flip
    it back off, leaving raw-content logging silently active indefinitely.
    Storing an expiry timestamp instead means it can only ever be on for a
    bounded window, no matter what. Call this from QGIS's own Python console
    when actively debugging; there is no Settings UI toggle for it by design."""
    if not QGIS_LOG_AVAILABLE:
        return
    try:
        QgsSettings().setValue(_DIAGNOSTIC_SETTING, time.time() + duration_seconds)
    except Exception:  # nosec B110 (best-effort: failure is non-fatal)
        pass


def disable_diagnostic_logging() -> None:
    """Ends diagnostic logging immediately, without waiting for it to expire."""
    if not QGIS_LOG_AVAILABLE:
        return
    try:
        QgsSettings().remove(_DIAGNOSTIC_SETTING)
    except Exception:  # nosec B110 (best-effort: failure is non-fatal)
        pass


def _diagnostic_logging_enabled() -> bool:
    """Explicit, local-only, OFF-by-default, TIME-BOUND escape hatch for
    raw-content diagnostic logging. log_event above is always metadata-only;
    this exists only for a developer actively debugging a specific issue on
    their own machine, never on by default and never synced/shared. See
    enable_diagnostic_logging's docstring for why this checks an expiry
    timestamp rather than a persistent boolean."""
    if not QGIS_LOG_AVAILABLE:
        return False
    try:
        expiry = QgsSettings().value(_DIAGNOSTIC_SETTING, 0.0, type=float)
        return bool(expiry) and time.time() < expiry
    except Exception:
        return False


def log_diagnostic(message: str, tag: str = TAG) -> None:
    """Explicit, temporary, local-only, time-bound raw-content diagnostic
    logging. Does nothing unless enable_diagnostic_logging() has been called
    and its window hasn't expired yet (see _diagnostic_logging_enabled's
    docstring) -- silently a no-op otherwise, so it's safe to leave calls to
    this in place without them ever logging anything by default. The first
    time it actually emits in a process, it logs a visible warning that raw
    content is being logged locally, so this is never a silent exception to
    the metadata-only default. Still passes through _redact (via
    log_warning/log_info) as defense-in-depth against known secret shapes,
    even in this explicit debugging mode."""
    if not _diagnostic_logging_enabled():
        return
    global _diagnostic_warning_shown
    if not _diagnostic_warning_shown:
        log_warning(
            "Verbose diagnostic logging is ON -- raw prompt/response/tool "
            "content may now be logged locally to QgsMessageLog, which can "
            "include sensitive data (coordinates, file paths, personal "
            "information). This window expires automatically; call "
            "disable_diagnostic_logging() to end it immediately instead.",
            tag=tag,
        )
        _diagnostic_warning_shown = True
    log_info(f"[DIAGNOSTIC] {message}", tag=tag)
