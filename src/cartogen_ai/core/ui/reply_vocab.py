# -*- coding: utf-8 -*-
"""
Which typed chat replies may answer which kind of pending question -- Qt-free so it can be unit
tested (same reasoning as chat_formatting.py and icons.py's pure half).

Two different questions can be waiting in the chat, and they must not share one vocabulary:

* A router card ("Reply to send this, or tell me what to change"): harmless either way, so a
  casual "yes" / "ok" / "sure" is the natural answer.
* A DESTRUCTIVE gate (load_project, field_calculator, the cloud-data-protection override ...):
  confirming replaces a project, edits data, or sends protected data to a cloud provider. Only an
  explicit word may confirm it.

rc7 interactive smoke test, 2026-09-30, finding F16: both used one shared set, so a destructive
preview left pending could be confirmed by a casual "yes" typed to answer a router card or an
unrelated question. Cancelling stays broad -- a cancel by accident is harmless.

A typed confirmation also stops working after PREVIEW_MAX_AGE_SECONDS: a preview the user walked
away from is not consent for what they type later. The Activity tab's Confirm button still works.
"""

import datetime

ROUTER_CONFIRM = frozenset({
    "yes", "y", "yeah", "yep", "ok", "okay", "sure", "go", "go ahead",
    "send", "send this", "confirm", "proceed", "do it",
})
GATE_CONFIRM = frozenset({
    "confirm", "confirmed", "proceed", "apply", "apply edit", "confirm and execute",
})
CANCEL = frozenset({
    "no", "n", "nope", "cancel", "stop", "abort", "never mind", "nevermind", "nvm",
})

PREVIEW_MAX_AGE_SECONDS = 600


def normalize_reply(text):
    return (text or "").strip().lower().rstrip("!.?")


def gate_reply(text):
    """"confirm", "cancel" or None for a reply typed while a destructive gate is pending."""
    key = normalize_reply(text)
    if key in GATE_CONFIRM:
        return "confirm"
    if key in CANCEL:
        return "cancel"
    return None


def router_reply(text):
    """"confirm", "cancel" or None (an edit) for a reply typed at a router card."""
    key = normalize_reply(text)
    if key in ROUTER_CONFIRM:
        return "confirm"
    if key in CANCEL:
        return "cancel"
    return None


def preview_is_fresh(updated_at_iso, now=None):
    """True when a pending preview was last touched within PREVIEW_MAX_AGE_SECONDS. An
    unreadable timestamp counts as stale, never as fresh."""
    try:
        updated = datetime.datetime.fromisoformat(updated_at_iso)
    except (TypeError, ValueError):
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=datetime.timezone.utc)
    current = now or datetime.datetime.now(datetime.timezone.utc)
    return (current - updated).total_seconds() <= PREVIEW_MAX_AGE_SECONDS


_NEW_REQUEST_MIN_WORDS = 7
_IMPERATIVE_STARTS = frozenset({
    "calculate", "compute", "create", "make", "build", "show", "map", "find", "list", "download", "fetch", "load", "add", "remove",
    "delete", "export", "estimate", "generate", "run", "classify", "compare", "analyze", "analyse", "draw", "plot", "clip", "buffer",
    "merge", "join", "style", "label", "zoom", "select", "count", "summarize", "summarise", "identify", "extract", "convert",
    "apply", "save", "use", "search", "transform", "rank", "write", "set",
})


def is_new_request(text):
    """True when a message typed while a clarification question is open is a whole NEW request, not the answer.

    The chat folded whatever came next into the pending request as "Details: <reply>", so a user who answered a question by typing
    a fresh full request got the OLD request run with the new one pasted underneath it. rc15 and rc17 hand tests: a severity request
    was answered with an OpenStreetMap download offer, a layout request with a historical title and path, and a footprint request ran
    an unrelated 14-call sequence, each after an earlier question was left open. An answer to "Which facility type?" is a few words
    ("health clinics"); a request names a tool, or is a sentence with an action word. Pure and deliberately conservative: when in
    doubt it is an answer, which is the old behaviour."""
    from ..agent import task_matcher
    body = (text or "").strip()
    if not body or body.endswith("?") and len(body.split()) < _NEW_REQUEST_MIN_WORDS:
        return False
    if task_matcher.named_tools(body):
        return True
    words = body.split()
    if len(words) >= _NEW_REQUEST_MIN_WORDS and task_matcher._ACTION_WORDS.search(body.lower()):
        return True
    # A short imperative ("Export smoke_points to CSV at outputs/x.csv") starts with its verb; an answer rarely does.
    first = words[0].lower().strip(",.:;")
    return len(words) >= 4 and first in _IMPERATIVE_STARTS


CONTINUATION_MARKER = "[Continuing my earlier request]"
MAX_CONTINUATIONS = 3
_SEQUENCE = ("then", "afterwards", "after that", "and also", "next", "finally", "followed by")


def has_followup_steps(request):
    """True when the original request asks for more than one thing, so a confirmed step may not be the last one. Pure.

    rc15 and rc17 hand tests (D05): "calculate the severity, write it to a field, and then style the layer" stopped after the
    confirmed write, because the Apply button runs the tool directly with no model turn and nothing resumed the request. A
    request with two or more distinct action words, or an explicit sequence word, gets one follow-up turn."""
    from ..agent import task_matcher
    text = (request or "").lower()
    if not text.strip():
        return False
    if any(f" {w} " in f" {text} " for w in _SEQUENCE):
        return True
    verbs = {m.group(0) for m in task_matcher._ACTION_WORDS.finditer(text)} - {
        "how", "what", "which", "where", "who", "when", "why", "can", "could", "please"}
    return len(verbs) >= 2


def continuation_prompt(original_request, tool_name, summary):
    """The text of the follow-up turn sent after a confirmed step finished."""
    return (f"{CONTINUATION_MARKER} The step `{tool_name}` I just confirmed has finished: {summary}. "
            f"Do not repeat it. Look at my original request below and carry out whatever part of it is still not done; "
            f"if nothing is left, reply with one short sentence saying so.\n\nOriginal request: {original_request}")

