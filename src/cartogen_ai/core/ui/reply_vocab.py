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
