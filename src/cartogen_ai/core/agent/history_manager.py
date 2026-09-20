# -*- coding: utf-8 -*-
"""
Conversation history storage, trimming, and mid-turn compaction for Cartogen AI.

Extracted from agent.py's CartogenAi class (2026-09-20, Phase 11 architecture
restructuring -- docs/IMPLEMENTATION_TRACKER.md §4), the harder half of that file's
god-class decomposition (ToolDispatcher and UsageTracker, extracted in the same pass,
were both already self-contained enough to be a pure file move -- this one owns real
shared, lock-guarded mutable state that CartogenAi.run(), chat_tab_widget.py's image-
attachment handler, and a large slice of test_agent_runner.py all touch directly).

Design note on why trim()/append() take their thresholds as PARAMETERS rather than
storing them as instance/class attributes on this module: test_agent_runner.py directly
monkeypatches `agent_mod.MAX_HISTORY_MESSAGES = <value>` mid-test to exercise trimming/
digest behavior at a controlled size, then calls agent._append_history(...) on an
already-constructed agent. Those constants have to stay live module-level globals in
agent.py itself (where CartogenAi._trim_history()/_append_history() read them fresh on
every call via normal Python name lookup) for that monkeypatch to keep working -- a
plain `from .history_manager import MAX_HISTORY_MESSAGES` re-export would silently break
it, since reassigning agent_mod.MAX_HISTORY_MESSAGES only rebinds agent.py's own
namespace, not a separate copy living in this module. Passing them through as call
arguments is also just the more correct design regardless of testing: it's what lets one
HistoryManager instance be reused correctly even if these thresholds were ever made
runtime-configurable instead of constants.
"""

import threading


class HistoryManager:
    def __init__(self):
        # RLock (not Lock): append() calls trim() internally under the same lock -- a
        # plain Lock would deadlock on that reentrant acquisition. See agent.py's
        # CartogenAi.__init__ for the original comment on why this needs to be an RLock
        # and why it must exist before anything else that might touch history.
        self.lock = threading.RLock()
        self.history = []

    @staticmethod
    def is_digest_message(msg, digest_marker):
        return (
            isinstance(msg, dict) and msg.get("role") == "system"
            and isinstance(msg.get("content"), str)
            and msg["content"].startswith(digest_marker)
        )

    @staticmethod
    def summarize_dropped_messages(dropped):
        """Extractive, non-LLM summary of messages about to be trimmed off history --
        one short line per message, not a call to an LLM. Deliberately not an API call:
        summarizing on every trim would add its own cost/latency to the exact code path
        this phase exists to make cheaper, and trim() runs synchronously inside every
        append() call."""
        lines = []
        for msg in dropped:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            content = " ".join(content.split())
            if len(content) > 100:
                content = content[:100] + "..."
            if content:
                lines.append(f"- {role}: {content}")
        return "\n".join(lines)

    def trim(self, max_messages, digest_marker, digest_max_chars):
        with self.lock:
            history = self.history
            has_digest = bool(history) and self.is_digest_message(history[0], digest_marker)
            body = history[1:] if has_digest else history
            if len(body) <= max_messages:
                return
            overflow = len(body) - max_messages
            dropped, kept = body[:overflow], body[overflow:]
            new_lines = self.summarize_dropped_messages(dropped)
            if not new_lines:
                self.history = ([history[0]] if has_digest else []) + kept
                return
            prior_body = history[0]["content"][len(digest_marker):].strip() if has_digest else ""
            digest_body = (prior_body + "\n" + new_lines).strip() if prior_body else new_lines
            if len(digest_body) > digest_max_chars:
                digest_body = digest_body[-digest_max_chars:]
            digest_msg = {"role": "system", "content": f"{digest_marker}\n{digest_body}"}
            self.history = [digest_msg] + kept

    def append(self, messages, max_messages, digest_marker, digest_max_chars):
        """Appends one or more messages to history and trims it, all under one lock
        acquisition -- the safe replacement for an unlocked '.append(); .append();
        trim()' pattern repeated at every return point in CartogenAi.run(). Also what
        chat_tab_widget.py's image-attachment handler (main thread) goes through instead
        of touching history directly, so a turn finishing concurrently on the background
        QgsTask thread can't interleave with it mid-mutation."""
        with self.lock:
            self.history.extend(messages)
            self.trim(max_messages, digest_marker, digest_max_chars)

    def snapshot(self):
        """Returns a shallow copy of history, taken under the lock -- the safe
        replacement for reading history directly while building a turn's outgoing
        message list, which could otherwise observe a torn read against a concurrent
        append() call from another thread. The copy itself is safe to iterate/extend
        from after the lock is released, same as any other already-built list."""
        with self.lock:
            return list(self.history)

    @staticmethod
    def compact_old_tool_results(messages, max_full_results, large_result_char_threshold, placeholder):
        """Mid-turn context compaction -- mutates `messages` in place, keeping the most
        recent max_full_results "tool"-role messages' content untouched and replacing
        older ones with a short placeholder. A tool result whose content contains an
        "error" key is NEVER compacted, at any age -- failures are load-bearing
        information the model may still need to reason about later in the same turn.

        A second, size-based rule: a tool result whose content is unusually large -- in
        practice, a base64 image payload like inspect_canvas_visually's, hundreds of
        times bigger than any normal JSON tool result -- gets compacted as soon as it's
        no longer the LATEST tool result, even if it's still within the count-based
        window above. A single oversized result can blow the provider's token ceiling on
        its own; waiting for max_full_results other tool calls to also happen first
        doesn't hold for it.

        Idempotent -- safe to call every iteration; already-compacted entries are
        skipped. Takes its thresholds as parameters for the same reason trim()/append()
        do -- see this module's own docstring."""
        tool_indices = [i for i, m in enumerate(messages) if isinstance(m, dict) and m.get("role") == "tool"]
        if not tool_indices:
            return
        most_recent = tool_indices[-1]
        keep_full_by_count = (
            set(tool_indices) if len(tool_indices) <= max_full_results
            else set(tool_indices[-max_full_results:])
        )
        for i in tool_indices:
            content = messages[i].get("content", "")
            if not isinstance(content, str):
                continue
            if content == placeholder or '"error"' in content:
                continue
            oversized = i != most_recent and len(content) > large_result_char_threshold
            if i in keep_full_by_count and not oversized:
                continue
            messages[i]["content"] = placeholder
