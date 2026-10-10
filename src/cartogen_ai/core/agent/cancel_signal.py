# -*- coding: utf-8 -*-
"""How a long-running tool learns that the user pressed Stop, and how it reports progress.

Why this exists (2026-09-25): agent.run() is given a `should_stop` callable (the running QgsTask's
isCanceled) but only checks it between tool calls -- its own docstring says it "can't interrupt an
in-flight ... tool execution". Ordinary tools run on QGIS's GUI thread (ToolDispatcher, a
BlockingQueuedConnection), so a network analysis over a national road network (measured: 6-10
minutes per call on 161,041 roads) froze QGIS with no way to stop it. The tool itself now has to
poll for Stop, and it needs a way to say what it is doing; run() publishes both here for the
duration of one request.

Module-level state, not passed through the tool signature: tool signatures are the model-facing
schema, and the dispatcher calls tools by name with the model's arguments. Everything here is
best-effort and never raises -- a broken callback must not break a tool."""

_state = {"should_stop": None, "status": None}


def begin(should_stop=None, status=None):
    """Called by agent.run() at the start of a request. Returns a token for end(), so a request
    started inside another one (a workflow step) restores the outer one's registration instead of
    wiping it."""
    previous = (_state["should_stop"], _state["status"])
    _state["should_stop"] = should_stop
    _state["status"] = status
    return previous


def end(previous=None):
    """Called by agent.run() when the request finishes, however it finishes. Without this a stale
    should_stop from a finished (possibly cancelled) request would abort the next tool call made
    outside any request, e.g. by a scheduled workflow."""
    _state["should_stop"], _state["status"] = previous if previous else (None, None)


def is_cancelled():
    fn = _state["should_stop"]
    if fn is None:
        return False
    try:
        return bool(fn())
    except Exception:
        return False


def report(text):
    fn = _state["status"]
    if fn is None:
        return
    try:
        fn(text)
    except Exception:  # nosec B110 (best-effort: failure is non-fatal)
        pass
