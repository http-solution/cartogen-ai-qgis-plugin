"""CLI bridge providers (PLAN-038): a locally installed vendor CLI used as the model, with no API key.

Design A of the plan: the CLI is a text-in/text-out model and the plugin keeps the tool loop. The prompt carries the tool schemas and asks
for one JSON reply; `parse_reply` turns it back into the OpenAI-shaped assistant message every other provider returns, so the
orchestrator, previews, confirmations and egress gate are untouched. The CLI's own file, shell, web and MCP tools are switched off.

Status: SHIPPED AS A MODULE ONLY, not yet selectable in Settings or the orchestrator. UNVERIFIED against a real logged-in CLI: the flags
below come from Claude Code's CLI reference (code.claude.com/docs/en/cli-reference, read 2026-10-28) and the shape of its `--output-format
json` result is the documented one, but CI has no CLI and no login. The owner's spike (PLAN-038 acceptance 3) is what verifies it.
"""
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid

from ...core.logger import log_event
from .base import BaseAiProvider

DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_MAX_OUTPUT_BYTES = 4 * 1024 * 1024
_POLL_SECONDS = 0.2

# Variables that would make the CLI bill an API account or reach a different backend than the user's own login, or that carry this
# plugin's own provider keys. The CLI inherits everything else (it needs PATH and HOME to find its login).
SCRUBBED_ENV = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "CARTOGEN_API_KEY",
)

# A model name is the one user-supplied value that reaches argv; keep it to what real model ids and aliases use.
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-\[\]]{0,80}$")
# Windows runs .cmd/.bat shims through cmd.exe even without shell=True, where these characters are interpreted.
_CMD_UNSAFE = re.compile(r'["%&|<>^!\r\n]')


class CliBridgeError(Exception):
    """A CLI could not be run or its output could not be used. The message is safe to show the user (no prompt content)."""


def find_executable(name_or_path):
    """Resolves a configured path or a bare command name to a real file, or None. Never invokes a shell."""
    if not name_or_path:
        return None
    candidate = shutil.which(name_or_path)
    if candidate:
        return candidate
    return name_or_path if os.path.isfile(name_or_path) else None


def scrubbed_environment(base=None):
    env = dict(os.environ if base is None else base)
    for key in SCRUBBED_ENV:
        env.pop(key, None)
    return env


def _check_argv(argv):
    if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(a, str) for a in argv):
        raise CliBridgeError("CLI command must be an argument list, not a shell string.")
    exe = argv[0].lower()
    if os.name == "nt" and exe.endswith((".cmd", ".bat")):
        for arg in argv[1:]:
            if _CMD_UNSAFE.search(arg):
                raise CliBridgeError("An argument contains characters that are unsafe for a .cmd launcher.")


def kill_process_tree(proc):
    """Ends the CLI and anything it spawned. The CLI starts helper processes, so killing only the parent can leave work running."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        with contextlib.suppress(Exception):
            taskkill = os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32", "taskkill.exe")
            subprocess.run([taskkill, "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=10, check=False)  # noqa: S603 -- fixed system binary, pid is ours
    else:
        with contextlib.suppress(Exception):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    with contextlib.suppress(Exception):
        proc.kill()


def _pump(stream, sink, cap, over_cap):
    """Reads a pipe to the end, keeping at most `cap` bytes and flagging overflow so the caller can stop the process."""
    size = 0
    while True:
        chunk = stream.read(4096)
        if not chunk:
            return
        size += len(chunk)
        if size > cap:
            over_cap.set()
            return
        sink.append(chunk)


def run_cli(argv, stdin_text="", timeout=DEFAULT_TIMEOUT_SECONDS, max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES,
            cancel_event=None, cwd=None, env=None):
    """Runs one CLI call. Returns (returncode, stdout, stderr) as text. Raises CliBridgeError for anything but a finished process.

    Argument list only (never a shell), a wall-clock timeout, an output size cap, and a cancel event polled every 200 ms; any of the
    three stops the whole process tree."""
    _check_argv(argv)
    popen_kwargs = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "cwd": cwd,
                    "env": scrubbed_environment() if env is None else env}
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        popen_kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(list(argv), **popen_kwargs)  # noqa: S603 -- argument list, no shell, checked above
    except OSError as e:
        raise CliBridgeError(f"Could not start the CLI ({type(e).__name__}). Check the executable path in Settings.") from e

    out_chunks, err_chunks, over_cap = [], [], threading.Event()
    readers = [threading.Thread(target=_pump, args=(proc.stdout, out_chunks, max_output_bytes, over_cap), daemon=True),
               threading.Thread(target=_pump, args=(proc.stderr, err_chunks, max_output_bytes, over_cap), daemon=True)]
    for t in readers:
        t.start()
    # The prompt is written from its own thread so a CLI that fills its output pipe before reading all of stdin cannot deadlock us.
    writer = threading.Thread(target=_feed_stdin, args=(proc.stdin, stdin_text), daemon=True)
    writer.start()

    deadline = time.monotonic() + timeout
    failure = None
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            failure = "The CLI request was cancelled."
        elif over_cap.is_set():
            failure = "The CLI produced more output than the size limit allows."
        elif time.monotonic() > deadline:
            failure = f"The CLI did not answer within {int(timeout)} seconds."
        if failure:
            kill_process_tree(proc)
            break
        time.sleep(_POLL_SECONDS)
    with contextlib.suppress(Exception):
        proc.wait(timeout=10)
    for t in readers:
        t.join(timeout=5)
    for stream in (proc.stdout, proc.stderr):
        with contextlib.suppress(Exception):
            stream.close()
    if failure:
        raise CliBridgeError(failure)
    if over_cap.is_set():
        raise CliBridgeError("The CLI produced more output than the size limit allows.")
    return (proc.returncode, b"".join(out_chunks).decode("utf-8", "replace"), b"".join(err_chunks).decode("utf-8", "replace"))


def _feed_stdin(stream, text):
    try:
        stream.write((text or "").encode("utf-8"))
    except OSError:
        pass  # the CLI exited before reading its prompt; the exit status reports the failure
    finally:
        with contextlib.suppress(OSError):
            stream.close()


# ---------------------------------------------------------------------------------------------------------------------------------
# Prompt and reply (pure, offline-testable)
# ---------------------------------------------------------------------------------------------------------------------------------

REPLY_INSTRUCTIONS = (
    "You are the reasoning engine of a QGIS assistant. You have NO tools of your own: do not read files, run commands or browse. "
    "The only actions available are the tools listed under TOOLS, which the host application runs for you.\n"
    "Reply with exactly one JSON object and nothing else.\n"
    'To call tools: {"tool_calls": [{"name": "<tool name>", "arguments": {...}}]}\n'
    'To answer the user: {"final": "<your answer>"}\n'
    "Use only tool names listed under TOOLS and only the arguments their schema declares. Never invent tool results; after a tool "
    "call you will be shown its result."
)


def _flatten_content(content):
    if isinstance(content, list):
        parts = [b.get("text", "") if isinstance(b, dict) and b.get("type") == "text" else "[image omitted]"
                 for b in content if isinstance(b, (dict, str))]
        return "\n".join(p for p in parts if p)
    return "" if content is None else str(content)


def _render_tools(tools):
    lines = []
    for tool in tools or []:
        fn = tool.get("function", tool) if isinstance(tool, dict) else {}
        lines.append(json.dumps({"name": fn.get("name", ""), "description": fn.get("description", ""),
                                 "parameters": fn.get("parameters", {})}, separators=(",", ":"), ensure_ascii=False))
    return "\n".join(lines)


def _render_message(msg):
    role = msg.get("role")
    text = _flatten_content(msg.get("content"))
    if role == "tool":
        return f"[tool result for {msg.get('tool_call_id', '')}]\n{text}"
    if role == "assistant":
        calls = []
        for call in msg.get("tool_calls") or []:
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            calls.append({"name": fn.get("name", ""), "arguments": args})
        if calls:
            return "[assistant]\n" + json.dumps({"tool_calls": calls}, ensure_ascii=False)
        return "[assistant]\n" + json.dumps({"final": text}, ensure_ascii=False)
    return f"[{role or 'user'}]\n{text}"


def build_prompt(messages, tools):
    """Splits an OpenAI-shaped conversation into (system_text, prompt_text). System text goes to the CLI's system-prompt slot; the
    prompt carries the tool list and the transcript."""
    system = [_flatten_content(m.get("content")) for m in messages if m.get("role") == "system"]
    body = [_render_message(m) for m in messages if m.get("role") != "system"]
    system_text = "\n\n".join([REPLY_INSTRUCTIONS] + [s for s in system if s])
    prompt = "TOOLS (one JSON object per line):\n" + (_render_tools(tools) or "(none)") + "\n\nCONVERSATION:\n" + "\n\n".join(body)
    return system_text, prompt + "\n\nYour reply (one JSON object):"


def _first_json_object(text):
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text, start)
        except ValueError:
            start = text.find("{", start + 1)
            continue
        if isinstance(obj, dict):
            return obj
        start = text.find("{", start + 1)
    return None


def parse_reply(text, tool_names):
    """Turns the CLI's reply into an assistant message, or raises CliBridgeError.

    Prose around the JSON is tolerated. A reply with no JSON object at all is treated as the model simply answering in words. A JSON
    object that asks for tools but is malformed or names an unknown tool is an error, never repaired by guessing: a guessed tool call
    could write to the user's project."""
    obj = _first_json_object(text or "")
    if obj is None or ("tool_calls" not in obj and "final" not in obj):
        return {"role": "assistant", "content": (text or "").strip() or None}
    if "tool_calls" in obj:
        raw = obj["tool_calls"]
        if not isinstance(raw, list) or not raw:
            raise CliBridgeError("The model's tool_calls was empty or not a list.")
        known = set(tool_names)
        calls = []
        for item in raw:
            name = item.get("name") if isinstance(item, dict) else None
            args = item.get("arguments", {}) if isinstance(item, dict) else None
            if name not in known:
                raise CliBridgeError(f"The model asked for a tool that is not available: {str(name)[:60]!r}.")
            if not isinstance(args, dict):
                raise CliBridgeError(f"The model gave arguments for {name} that are not a JSON object.")
            calls.append({"id": f"cli_{uuid.uuid4().hex[:12]}", "type": "function",
                          "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}})
        return {"role": "assistant", "content": None, "tool_calls": calls}
    final = obj["final"]
    return {"role": "assistant", "content": final if isinstance(final, str) else json.dumps(final, ensure_ascii=False)}


# ---------------------------------------------------------------------------------------------------------------------------------
# Claude Code adapter
# ---------------------------------------------------------------------------------------------------------------------------------

def claude_argv(executable, system_prompt_file, model=None):
    """The exact command line for one Claude Code call. Everything that could let the CLI act on its own is switched off:
    `--tools ""` removes every built-in tool, `--strict-mcp-config` with no `--mcp-config` loads no MCP server, and no session is saved."""
    if model and not _MODEL_RE.match(model):
        raise CliBridgeError("The model name contains characters that are not allowed.")
    argv = [executable, "-p", "--output-format", "json", "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
            "--no-session-persistence", "--max-turns", "1", "--system-prompt-file", system_prompt_file]
    if model:
        argv += ["--model", model]
    return argv


def parse_claude_result(stdout):
    """Reads Claude Code's `--output-format json` result. Returns (text, usage_dict_or_None, model_or_None)."""
    try:
        data = json.loads(stdout)
    except ValueError as e:
        raise CliBridgeError("The Claude CLI did not return JSON. Is it a current version (`claude update`)?") from e
    if isinstance(data, list):  # some versions return the event list; the result event is the last one
        data = next((d for d in reversed(data) if isinstance(d, dict) and d.get("type") == "result"), None)
    if not isinstance(data, dict):
        raise CliBridgeError("The Claude CLI returned an unexpected result.")
    if data.get("is_error"):
        raise CliBridgeError("The Claude CLI reported an error: " + str(data.get("result") or data.get("subtype") or "unknown")[:300])
    text = data.get("result")
    if not isinstance(text, str):
        raise CliBridgeError("The Claude CLI result had no text.")
    usage = data.get("usage") or {}
    reported = None
    if isinstance(usage, dict) and ("input_tokens" in usage or "output_tokens" in usage):
        full_input = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        reported = {"input_tokens": full_input, "output_tokens": int(usage.get("output_tokens") or 0)}
    models = list((data.get("modelUsage") or {}).keys()) if isinstance(data.get("modelUsage"), dict) else []
    return text, reported, (models[0] if models else None)


def estimate_usage(prompt, reply):
    """Character-count estimate, flagged so the footer can say 'estimated'. Used only when the CLI reports no tokens."""
    return {"input_tokens": max(1, len(prompt) // 4), "output_tokens": max(1, len(reply) // 4), "estimated": True}


class ClaudeCliClient(BaseAiProvider):
    """Claude Code (`claude -p`) used as a model on the user's own login. See the module docstring for status."""

    def __init__(self, executable="claude", model=None, status_callback=None, timeout=DEFAULT_TIMEOUT_SECONDS, cancel_event=None):
        self.executable = executable
        self.model = model
        self.timeout = timeout
        self.cancel_event = cancel_event
        self._status_callback = status_callback

    def _emit_status(self, text):
        if self._status_callback:
            with contextlib.suppress(Exception):
                self._status_callback(text)

    def complete(self, messages, tools=None, max_tokens=None):  # max_tokens unused: the CLI has no output-token flag
        exe = find_executable(self.executable)
        if not exe:
            return {"error": "Claude Code CLI not found. Install it and sign in, or set its path in Settings."}
        self._emit_status("Using Claude Code CLI" + (f": {self.model}" if self.model else ""))
        system_text, prompt = build_prompt(messages, tools)
        names = [(t.get("function", t) or {}).get("name", "") for t in (tools or []) if isinstance(t, dict)]
        started = time.monotonic()
        # An empty working directory keeps the CLI from reading a project CLAUDE.md or listing files next to the user's data.
        with tempfile.TemporaryDirectory(prefix="cartogen_cli_") as workdir:
            system_file = os.path.join(workdir, "system.txt")
            with open(system_file, "w", encoding="utf-8") as fh:
                fh.write(system_text)
            try:
                code, out, _err = run_cli(claude_argv(exe, system_file, self.model), prompt, timeout=self.timeout,
                                          cancel_event=self.cancel_event, cwd=workdir)
                if code != 0 and not out.strip():
                    raise CliBridgeError(f"The Claude CLI exited with status {code}. Is it signed in (`claude` once, then /login)?")
                text, usage, model = parse_claude_result(out)
                message = parse_reply(text, names)
            except CliBridgeError as e:
                log_event("cli_bridge_error", provider="claude_cli", error_class="CliBridgeError",
                          duration_ms=int((time.monotonic() - started) * 1000))
                return {"error": str(e)}
        log_event("cli_bridge_call", provider="claude_cli", status="ok", duration_ms=int((time.monotonic() - started) * 1000))
        return {"message": message, "model": model or self.model or "claude-cli", "usage": usage or estimate_usage(prompt, text)}
