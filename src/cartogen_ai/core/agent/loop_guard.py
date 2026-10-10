# -*- coding: utf-8 -*-
"""Stops an agent turn that is stuck, before it spends the whole round budget doing nothing.

Why (2026-10-09 cost investigation): a round cap alone lets a stuck turn burn every round. The three signs of a stuck turn are
visible without any model call: the SAME tool called with the SAME arguments again, a tool that keeps FAILING, and several rounds
in a row with no state-changing success (nothing created, changed, exported). This guard watches for those. It is pure (no Qt, no
QGIS) so it cannot fail inside the loop and is fully unit-testable, and a stop always reports what was done and what was not: a
guard stop is never presented as success.

The thresholds are provisional guardrails, chosen to catch loops and not legitimate work: a read-only prelude of a few calls is
normal, so only SIX progress-free rounds count as a stall, and a tool must fail three times IN A ROW (or eight times in a turn)."""
import hashlib
import json

# Bookkeeping tools are expected to repeat with the same arguments and are not progress either.
EXEMPT_FROM_DUPLICATES = frozenset({"update_task", "create_plan", "set_task_preview", "get_layers", "get_attributes"})
STATE_CHANGING = frozenset({"CREATE", "MODIFY", "DELETE", "PUBLISH"})


def canonical_arguments(arguments):
    """A stable text form of a call's arguments (a JSON string or a dict), so key order and whitespace never hide a duplicate."""
    try:
        data = json.loads(arguments) if isinstance(arguments, str) else arguments
        return json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
    except Exception:
        return str(arguments)


def call_key(name, arguments):
    return name + ":" + hashlib.sha1(canonical_arguments(arguments).encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:12]


class LoopGuard:
    def __init__(self, max_identical_calls=3, max_consecutive_failures=3, max_failures=8, stall_rounds=6):
        self.max_identical_calls = max_identical_calls
        self.max_consecutive_failures = max_consecutive_failures
        self.max_failures = max_failures
        self.stall_rounds = stall_rounds
        self._seen = {}
        self._consecutive = {}
        self._failures = 0
        self._rounds_without_progress = 0
        self._round_progress = False
        self.done = []          # tool names that succeeded, in order
        self.failed = []        # (tool name, short error)
        self.stop = None        # {"reason", "detail"} once triggered

    def record_call(self, name, arguments, is_error, error_text="", operation_type=None):
        """Record one finished tool call. Returns the stop dict if this call tripped a rule, else None."""
        key = call_key(name, arguments)
        if name not in EXEMPT_FROM_DUPLICATES:
            self._seen[key] = self._seen.get(key, 0) + 1
            if self._seen[key] >= self.max_identical_calls and self.stop is None:
                self.stop = {"reason": "duplicate_call", "detail": f"`{name}` was called {self._seen[key]} times with the same arguments"}
        if is_error:
            self._failures += 1
            self._consecutive[name] = self._consecutive.get(name, 0) + 1
            self.failed.append((name, (error_text or "")[:120]))
            if self.stop is None and self._consecutive[name] >= self.max_consecutive_failures:
                self.stop = {"reason": "repeated_failure", "detail": f"`{name}` failed {self._consecutive[name]} times in a row"}
            elif self.stop is None and self._failures >= self.max_failures:
                self.stop = {"reason": "repeated_failure", "detail": f"{self._failures} tool calls failed in this request"}
        else:
            self._consecutive[name] = 0
            self.done.append(name)
            if operation_type in STATE_CHANGING:
                self._round_progress = True
        return self.stop

    def end_round(self):
        """Call once per model round, after its tool calls. Returns the stop dict if the turn has stalled, else None."""
        if self._round_progress:
            self._rounds_without_progress = 0
        else:
            self._rounds_without_progress += 1
        self._round_progress = False
        if self.stop is None and self._rounds_without_progress >= self.stall_rounds:
            self.stop = {"reason": "no_progress",
                         "detail": f"{self._rounds_without_progress} rounds in a row changed nothing (no layer, field or file was created or modified)"}
        return self.stop

    def partial_report(self, stop=None):
        """Plain-language stop message that says what was done and what was not. Starts with '[Agent stopped]' so it cannot read as success."""
        stop = stop or self.stop or {"reason": "stopped", "detail": "the request was stopped"}
        done = list(dict.fromkeys(self.done))
        lines = [f"[Agent stopped] {stop['detail'].capitalize()}, so I stopped before spending more of your API credit."]
        lines.append("Done so far: " + (", ".join(f"`{n}`" for n in done[:12]) + (" ..." if len(done) > 12 else "") if done else "nothing completed."))
        if self.failed:
            recent = self.failed[-3:]
            lines.append("Failed: " + "; ".join(f"`{n}`" + (f" ({e})" if e else "") for n, e in recent))
        lines.append("The request is NOT complete. Tell me what to change, or reply 'continue' to try again from here.")
        return "\n".join(lines)


def budget_exceeded(turn_tokens, budget, next_call_estimate=None):
    """True when the next request should not be sent: observed turn tokens plus the observed size of the last call would pass the
    budget (the next call cannot cost less than the last one did, because the history only grows). budget 0/None means no limit.
    With no measured call yet only the tokens already spent are compared."""
    if not budget:
        return False
    return (turn_tokens + (next_call_estimate or 0)) > budget


# rc22 hand test J13 (#231): the model made 20 calls on file paths it had invented, then hit the tool limit. With the exact
# paths given the same tools worked, so the failure was guessing, not the tools. Two "file not found" results in a row is the
# earliest reliable sign; the corrective message is injected once per turn by the orchestrator.
MISSING_FILE_THRESHOLD = 2
_MISSING_FILE_WORDS = ("file not found", "no such file", "does not exist", "cannot find the file", "path not found")
MISSING_FILE_NUDGE = (
    "Your last {n} calls failed because the file path does not exist. Stop guessing paths. Use only a path the user gave "
    "in this conversation or one a tool returned (for example a layer's source from get_layers, or an output path in an "
    "earlier result). If you do not have the real path, ask the user for the file or folder in one short question instead "
    "of trying more names.")


def missing_file_nudge(turn_tool_log, threshold=MISSING_FILE_THRESHOLD):
    """The corrective message when the last `threshold` tool calls all failed with a missing-file error, else None. Pure.

    `turn_tool_log` is the orchestrator's list of (tool name, is_error, message)."""
    recent = list(turn_tool_log or [])[-threshold:]
    if len(recent) < threshold:
        return None
    for _name, is_error, message in recent:
        if not is_error or not any(w in str(message or "").lower() for w in _MISSING_FILE_WORDS):
            return None
    return MISSING_FILE_NUDGE.format(n=threshold)
