# -*- coding: utf-8 -*-
"""
Session-scoped token usage tracking for Cartogen AI.

Extracted from agent_orchestrator.py's CartogenAi class (2026-09-20, Phase 11 architecture
restructuring -- docs/IMPLEMENTATION_TRACKER.md §4). Originally added per
docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md SS3.2: "no cost/usage visibility
in the UI despite real, documented cost-engineering work." Not persisted across QGIS
restarts or project switches -- CartogenAi IS the session (see _get_agent() in
plugin_main.py), so a fresh instance naturally means a fresh count, matching how a user
would think about "this session's usage."

CartogenAi.session_usage / _accumulate_usage() / get_session_usage_text() are kept as
thin delegators to an instance of this class rather than removed, since chat_tab_widget.py
and a large block of tests (test_new_tools.py's usage-reporting suite) read/call them
directly on the agent object -- this extraction changes where the logic lives, not the
public shape callers already depend on.
"""


class UsageTracker:
    def __init__(self):
        # calls_without_usage tracks turns where the provider's response didn't
        # include token counts at all, so the UI can caveat the total as a
        # partial figure instead of presenting it as exact when it isn't.
        # cached_tokens (2026-09-13, "implement gemini caching"): how many of
        # input_tokens were actually served from a provider-side prompt cache --
        # see providers/base.py's extract_openai_style_usage / providers/claude.py's
        # from_anthropic_response docstrings for exactly what this does and doesn't
        # mean per provider.
        self.usage = {
            "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0,
            "calls_with_usage": 0, "calls_without_usage": 0,
        }

    def accumulate(self, usage):
        """Adds one API call's token usage into the session running total.
        usage is either the normalized {'input_tokens', 'output_tokens'} dict a
        provider's complete() returns, or None if that provider/response didn't
        report it -- counted separately (calls_without_usage) rather than as
        zero, so summary_text() can honestly caveat the total instead of
        understating it."""
        if isinstance(usage, dict) and ("input_tokens" in usage or "output_tokens" in usage):
            self.usage["input_tokens"] += usage.get("input_tokens") or 0
            self.usage["output_tokens"] += usage.get("output_tokens") or 0
            self.usage["cached_tokens"] += usage.get("cached_tokens") or 0
            self.usage["calls_with_usage"] += 1
        else:
            self.usage["calls_without_usage"] += 1

    def summary_text(self):
        """Short, human-readable summary of this session's token usage for
        ui/dock_widget.py's usage_label -- e.g. '~4,230 tokens this session
        (12 calls)' or '~4,230 tokens this session (12 calls; 3 calls with no
        usage reported)' once at least one provider call has actually reported
        usage. Returns None (not a misleading '0 tokens') if no call so far
        has reported usage at all -- e.g. a fresh session, or a provider/model
        that never reports it. Intentionally no dollar-cost estimate: accurate
        per-model pricing across 5 providers would need a pricing table that's
        guaranteed to go stale and mislead; see
        docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md's reasoning for a similar
        accuracy-over-completeness call on a different feature.

        cached_tokens (2026-09-13, "implement gemini caching"), when any calls
        reported it, gets its own clause -- e.g. '~9,316 tokens this session
        (6 calls, ~7,200 served from cache)'. This is what makes prompt caching's
        effect (Claude's already-implemented cache_control breakpoints, Gemini
        2.5+/3.x's automatic implicit caching) actually visible instead of a
        silent, unverifiable assumption -- see providers/base.py's
        extract_openai_style_usage and providers/claude.py's
        from_anthropic_response for where this number comes from per provider."""
        u = self.usage
        if u["calls_with_usage"] == 0:
            return None
        total = u["input_tokens"] + u["output_tokens"]
        calls_clause = f"{u['calls_with_usage']} calls"
        if u["calls_without_usage"] > 0:
            calls_clause += f"; {u['calls_without_usage']} call(s) with no usage reported"
        if u.get("cached_tokens"):
            calls_clause += f", ~{u['cached_tokens']:,} served from cache"
        return f"~{total:,} tokens this session ({calls_clause})"
