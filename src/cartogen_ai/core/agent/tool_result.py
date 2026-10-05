# -*- coding: utf-8 -*-
"""One place that says what a tool result is.

A tool may return a dict (most do) or a plain list (get_layers, get_attributes and other read tools). Code that handled results
used to test `isinstance(result, dict)` on its own, and the #138 rewrite of the dispatcher treated every non-dict as a failure:
in the rc15 hand test (2026-10-06) get_layers and get_attributes came back as "Execution failed unexpectedly." Callers now ask
these helpers instead of re-deriving the rule, so a new result shape is a change here, not a hunt through the dispatcher.
Pure: no QGIS, no Qt."""

MISSING_RESULT_ERROR = "Execution failed unexpectedly."


def ensure_result(result):
    """The result unchanged, or the standard error dict when nothing came back (None).

    Only a MISSING result is a failure. Lists, strings and numbers are legitimate results and pass through."""
    return {"error": MISSING_RESULT_ERROR} if result is None else result


def error_of(result):
    """The error text of a failed result, or None. Only a dict carrying an "error" key is a failure."""
    if isinstance(result, dict) and "error" in result:
        return result["error"]
    return None


def is_error(result):
    return isinstance(result, dict) and "error" in result


def status_of(result):
    """The result's own `status` (for example PREVIEW_REQUIRED), or None for anything that has none."""
    return result.get("status") if isinstance(result, dict) else None


def error_class_of(result, default="ToolError"):
    """The error class a failed result names, for metadata-only logging."""
    return result.get("error_class", default) if isinstance(result, dict) else default
