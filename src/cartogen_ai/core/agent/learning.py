# -*- coding: utf-8 -*-
"""
Adaptive learning helpers for Cartogen AI.

This module is deliberately kept separate from memory.py: memory.py owns
*storage* (project/global notes, action history, sqlite persistence),
learning.py owns the *policy* of what gets written there and when, layered
entirely on top of the existing store_global_note/get_global_notes API
rather than adding new storage plumbing. Everything here is pure Python
(no qgis.* imports) so it can be unit-tested without a QGIS environment --
see tests/test_learning.py.

Implements the four mechanisms requested 2026-09-02 ("i want the agent to
self learn and improve itself gradually based on the user context and
requests", clarified via AskUserQuestion -- user selected all four):

1. Auto-detect preferences passively -- maybe_infer_preferences() looks at
   accumulated usage:* counters (no separate "end of session" hook needed;
   it's cheap enough to call after every successful tool execution) and
   writes a `pref:*` global note once a signal is consistent enough to act
   on. Scoped deliberately to provider choice for the first pass -- that's
   the one signal available today with a clean, unambiguous count (exactly
   one provider is active per request, recorded in __init__). Mining
   arbitrary tool-argument values (CRS, region, etc.) was considered and
   deliberately deferred: log_spatial_action stores args as a stringified
   dict (str(args)), not structured data, so parsing that back out reliably
   enough to act on automatically needs more than a regex guess -- rather
   than ship a heuristic likely to store wrong "preferences" with false
   confidence, this starts with the one signal that's actually reliable and
   can be extended once real usage shows what's worth mining next.
2. Learn from corrections -- detect_correction() is a plain-text heuristic
   over the user's *next* message after a tool call; record_correction_rule()
   persists it as a `rule:*` global note the system prompt surfaces every
   turn. This is inherently a heuristic (there's no ground truth for "the
   user meant this as a correction" short of asking them) -- it will both
   miss some real corrections and occasionally fire on an unrelated message
   that happens to contain a matched phrase. Flagged here, in
   BUG_TRACKER.md, and to the user, the same way the rule-40/41 prompt
   changes were: not verifiable from this sandbox, needs real usage to
   tune.
3. Usage-pattern-driven defaults -- record_tool_usage()/record_provider_usage()
   maintain simple running counters as `usage:*` global notes; these feed
   both maybe_infer_preferences() (mechanism 1) and the formatted memory
   context (so the model itself sees "you've used X most often" and can
   factor that into suggestions) -- see memory.get_formatted_memory_context().
   No UI defaults (e.g. the provider combo's initial selection) are changed
   automatically by this module: doing that safely would mean touching
   settings_dialog.py / dock_widget.py's provider-selection code, which
   already has an unrelated, uncommitted "account" feature in flight this
   session has no context on -- surfacing the pattern to the user (mechanism
   4) and the model (this mechanism) is the safe subset; silently
   overriding a widget default is not, and is left for a follow-up once
   that file is back in a clean state.
4. Visible, editable memory panel -- this module doesn't touch the UI
   directly; tasks_tab_widget.py's existing "Project Notes & Memory" panel
   already renders whatever get_formatted_memory_context() returns, and was
   extended (see that file) with a "Forget" control wired to
   memory.delete_global_note() so a user can remove a wrong inferred
   preference or a stale correction rule.
"""

import re
import time

PREF_PREFIX = "pref:"
RULE_PREFIX = "rule:"
USAGE_TOOL_PREFIX = "usage:tool:"
USAGE_PROVIDER_PREFIX = "usage:provider:"

# Minimum number of provider-usage events, and minimum share of those events
# going to one provider, before maybe_infer_preferences() will act on it.
# Both thresholds exist so a single early session can't immediately declare
# a "preference" -- there needs to be a real pattern (at least 5 requests)
# and it needs to be dominant (70%+), not just a slight plurality.
_PREFERENCE_MIN_SAMPLES = 5
_PREFERENCE_MIN_SHARE = 0.7

# Phrases that plausibly signal the user is rejecting/correcting the agent's
# immediately preceding action, rather than starting a new unrelated request.
# Deliberately conservative (longer, more specific phrases) to keep the false
# -positive rate down, at the cost of missing softer corrections -- see the
# module docstring's honest caveat on mechanism 2.
_CORRECTION_PATTERNS = [
    r"\bthat'?s (not|wrong|incorrect)\b",
    r"\bnot what i (asked|meant|wanted)\b",
    r"\bno[,.]? (that'?s|please|don'?t|not)\b",
    r"\bdon'?t do that\b",
    r"\bundo (that|it)\b",
    r"\bplease redo\b",
    r"\bstop doing\b",
    r"^\s*no\b",
    r"\bactually,? i meant\b",
    r"\binstead of\b.{0,40}\bplease\b",
    r"\bwrong (layer|color|colour|style|year|crs|region)\b",
]
_CORRECTION_RE = re.compile("|".join(_CORRECTION_PATTERNS), re.IGNORECASE)


def _read_int_note(memory_manager, key, default=0):
    try:
        raw = memory_manager.get_global_notes().get(key)
        return int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


def _increment_note(memory_manager, key):
    current = _read_int_note(memory_manager, key, 0)
    memory_manager.store_global_note(key, str(current + 1))


def record_tool_usage(memory_manager, tool_name):
    """Increments the running-use counter for a tool. Called from every
    successful tool execution path in agent.py (_real_execute_tool and
    _log_tool_success both have their own success branch)."""
    if not tool_name:
        return
    _increment_note(memory_manager, f"{USAGE_TOOL_PREFIX}{tool_name}")


def record_provider_usage(memory_manager, provider_name):
    """Increments the running-use counter for an LLM provider. Called once
    per CartogenAi() construction (== once per session, per plugin_main.py's
    _get_agent() docstring), with whichever provider that session resolved
    to from QgsSettings."""
    if not provider_name:
        return
    _increment_note(memory_manager, f"{USAGE_PROVIDER_PREFIX}{provider_name}")


def get_usage_counts(memory_manager, prefix):
    """Returns {name: count} for every usage:<prefix>:<name> note, sorted
    by count descending. `prefix` is USAGE_TOOL_PREFIX or USAGE_PROVIDER_PREFIX."""
    notes = memory_manager.get_global_notes()
    counts = {}
    for key, value in notes.items():
        if key.startswith(prefix):
            try:
                counts[key[len(prefix):]] = int(value)
            except (TypeError, ValueError):
                continue
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def maybe_infer_preferences(memory_manager):
    """Passive preference inference (mechanism 1). Idempotent and cheap --
    safe to call after every successful tool execution. Only acts on the
    provider-usage signal today; see module docstring for why that's the
    deliberately scoped first pass."""
    provider_counts = get_usage_counts(memory_manager, USAGE_PROVIDER_PREFIX)
    total = sum(provider_counts.values())
    if total < _PREFERENCE_MIN_SAMPLES:
        return
    top_provider, top_count = next(iter(provider_counts.items()))
    share = top_count / total
    if share < _PREFERENCE_MIN_SHARE:
        return
    value = f"{top_provider} (used in {top_count}/{total} recent sessions)"
    existing = memory_manager.get_global_notes().get(f"{PREF_PREFIX}preferred_provider")
    if existing != value:
        memory_manager.store_global_note(f"{PREF_PREFIX}preferred_provider", value)


def detect_correction(user_message):
    """Pure-text heuristic (mechanism 2): does this message read like the
    user rejecting/correcting the agent's immediately preceding action?
    See module docstring for the honest false-positive/false-negative
    caveat -- this is a starting heuristic, not a verified classifier."""
    if not user_message or not isinstance(user_message, str):
        return False
    return bool(_CORRECTION_RE.search(user_message))


def record_correction_rule(memory_manager, user_message, last_tool_name, last_tool_args):
    """Persists a detected correction as a standing `rule:*` global note so
    the system prompt surfaces it on every future turn (via
    memory.get_formatted_memory_context()), not just this session."""
    notes = memory_manager.get_global_notes()
    existing_indices = []
    for key in notes:
        if key.startswith(RULE_PREFIX):
            try:
                existing_indices.append(int(key[len(RULE_PREFIX):]))
            except ValueError:
                continue
    next_index = (max(existing_indices) + 1) if existing_indices else 1

    excerpt = user_message.strip()
    if len(excerpt) > 160:
        excerpt = excerpt[:157] + "..."
    when = time.strftime("%Y-%m-%d")
    if last_tool_name:
        rule_text = (
            f'On {when}, after `{last_tool_name}` (args: {str(last_tool_args)[:120]}), '
            f'the user responded: "{excerpt}". Treat this as a correction -- avoid repeating '
            f"that same choice unless the user asks for it again."
        )
    else:
        rule_text = f'On {when}, the user said: "{excerpt}". Treat this as a correction to the previous turn.'

    key = f"{RULE_PREFIX}{next_index}"
    memory_manager.store_global_note(key, rule_text)
    return key
