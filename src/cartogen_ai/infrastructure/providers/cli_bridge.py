"""CLI bridge providers (PLAN-038): a locally installed vendor CLI used as the model, with no API key.

Design A of the plan: the CLI is a text-in/text-out model and the plugin keeps the tool loop. The prompt carries the tool schemas and asks
for one JSON reply; `parse_reply` turns it back into the OpenAI-shaped assistant message every other provider returns, so the
orchestrator, previews, confirmations and egress gate are untouched. The CLI's own file, shell, web and MCP tools are switched off.

Gemini CLI was removed on 2026-10-30 (owner decision, PLAN-041): Google stopped serving personal Google accounts through it on 2026-06-18.
Claude Code and Codex remain.

Status: SHIPPED AS A MODULE ONLY, not yet selectable in Settings or the orchestrator. UNVERIFIED against a real logged-in CLI: the flags
below come from Claude Code's CLI reference (code.claude.com/docs/en/cli-reference, read 2026-10-28) and the shape of its `--output-format
json` result is the documented one; the Codex flags and `--json` event names come from OpenAI's non-interactive-mode page (read 2026-10-28)
and a third-party event reference. CI has no CLI and no login for either. The owner's spike (PLAN-038 acceptance 3) is what verifies it.
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
from . import cli_flags, cli_locator
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


class CliToolUnavailableError(CliBridgeError):
    """The model named a tool that was not offered in this request. Still an error (a guessed call could write to the user's project), but a
    recoverable one: `complete` asks once more, naming the tools that exist. Live smoke round 3 (rows B1 prompt 5 and B2 prompt 8, Claude Code
    CLI): the model asked for execute_pyqgis_script and import_humanitarian_table, neither offered that turn, and the task ended on the error."""

    def __init__(self, name):
        super().__init__(f"The model asked for a tool that is not available: {str(name)[:60]!r}.")
        self.name = str(name)[:60]


def _extra_bin_dirs(existing_only=True):
    """Folders where npm, Homebrew, Volta, nvm, bun, pnpm or scoop put CLIs. A QGIS started from a desktop icon or Finder has a
    shorter PATH than the user's terminal, so `shutil.which("codex")` fails there even though the terminal finds it (user report,
    2026-10-28: Codex installed, Settings said 'program not found'). Only existing directories are returned."""
    home = os.path.expanduser("~")
    dirs = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        dirs += [os.path.join(appdata, "npm"), os.path.join(home, ".local", "bin"), os.path.join(home, ".bun", "bin"),
                 os.path.join(local, "Volta", "bin"), os.path.join(local, "pnpm"), os.path.join(home, "scoop", "shims"),
                 # Codex's own Windows installer, not npm (user report 2026-10-30: `Get-Command codex` gave this folder and Cartogen
                 # said "Codex CLI not found" because it was in none of the folders above).
                 os.path.join(local, "Programs", "OpenAI", "Codex", "bin"),
                 os.path.join(local, "Microsoft", "WinGet", "Links"),  # where winget puts the shims of the CLIs it installs
                 os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "nodejs")]
        nvm = os.environ.get("NVM_SYMLINK")
        if nvm:
            dirs.append(nvm)
    else:
        dirs += [os.path.join(home, ".local", "bin"), "/usr/local/bin", "/opt/homebrew/bin", os.path.join(home, ".npm-global", "bin"),
                 os.path.join(home, ".volta", "bin"), os.path.join(home, ".bun", "bin"), os.path.join(home, ".claude", "local")]
        nvm_root = os.path.join(home, ".nvm", "versions", "node")
        with contextlib.suppress(OSError):
            dirs += [os.path.join(nvm_root, v, "bin") for v in sorted(os.listdir(nvm_root), reverse=True)]
    seen, out = set(), []
    for d in dirs:
        if d and d not in seen and (not existing_only or os.path.lexists(d)):
            seen.add(d)
            out.append(d)
    return out


def _clean_path_text(text):
    return os.path.expandvars(os.path.expanduser((text or "").strip().strip("\"'").strip()))


def _with_pathext(path):
    """npm writes `codex` (a shell script Windows cannot run) next to `codex.cmd`; a path pasted without the ending means the .cmd/.exe."""
    if os.path.splitext(path)[1]:
        return None
    for ext in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";"):
        if ext and os.path.isfile(path + ext):
            return path + ext
    return None


def find_executable(name_or_path):
    """Resolves a configured path or a bare command name to a real file, or None. Never invokes a shell.

    Tolerates what people paste: surrounding quotes or spaces, ~ and %VAR%, and on Windows a path without its .cmd/.exe ending.
    A bare name is looked for on PATH first, then in the usual install folders (see `_extra_bin_dirs`).
    """
    text = _clean_path_text(name_or_path)
    if not text or os.path.isdir(text):
        return None
    if os.sep in text or (os.altsep and os.altsep in text):
        if os.path.isfile(text) or os.path.lexists(text):  # lexists: a link or app alias Python cannot open is still a program to start
            return text
        return _with_pathext(text) if os.name == "nt" else None
    found = shutil.which(text)
    if found:
        return found
    # Then the usual install folders, then what the OS says the user's own terminal would search (cli_locator; read from its cache only,
    # because looking starts a shell and this runs on the UI thread too).
    for folders in (_extra_bin_dirs(), cli_locator.cached_dirs()):
        path = os.pathsep.join(folders)
        found = shutil.which(text, path=path) if path else None
        if found:
            return found
    # A file Python cannot open (a link, an app alias) is invisible to `which` but can still be started: look for the name by its
    # directory entry, with each Windows extension.
    for folder in [*(os.environ.get("PATH", "").split(os.pathsep)), *_extra_bin_dirs(), *cli_locator.cached_dirs()]:
        for ext in ([""] + [e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e]) if os.name == "nt" else [""]:
            candidate = os.path.join(folder, text + ext) if folder else ""
            if candidate and os.path.lexists(candidate) and not os.path.isdir(candidate):
                return candidate
    # Last, what Windows itself says (filled on a background thread by cli_locator.ensure).
    return cli_locator.resolved(text) or None


def diagnose_missing(name):
    """Lines saying what is known about a program that was not found: what Windows said, and any file named like it that Python cannot
    open. Empty when there is nothing to add. Reads the filesystem only (no program is started), cheap enough for the UI thread."""
    lines = []
    said = cli_locator.where_said(name)
    if said:
        lines.append(f"where.exe {name} said: {said}")
    folders = [*(os.environ.get("PATH", "").split(os.pathsep)), *_extra_bin_dirs(), *cli_locator.cached_dirs()]
    for path, status in cli_locator.look_alikes(name, [d for d in dict.fromkeys(folders) if d]):
        lines.append(f"{path}: {status}")
    lines.extend(f"{d}: the folder exists but cannot be opened" for d in _extra_bin_dirs() if not os.path.isdir(d))
    return lines


def search_folders():
    """Every folder a bare program name is looked for in, in order, for telling the user where was searched."""
    seen, out = set(), []
    for d in [*(os.environ.get("PATH", "").split(os.pathsep)), *_extra_bin_dirs(), *cli_locator.cached_dirs()]:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def find_in_folder(folder, name):
    """When the program field holds a folder, the program is <name> inside it."""
    folder = _clean_path_text(folder)
    if not (folder and os.path.isdir(folder)):
        return None
    return shutil.which(name, path=folder)


def scrubbed_environment(base=None):
    env = dict(os.environ if base is None else base)
    for key in SCRUBBED_ENV:
        env.pop(key, None)
    # Node-based CLIs are launcher scripts that need `node` on PATH; add the usual folders after the existing PATH.
    have = env.get("PATH", "").split(os.pathsep)
    extra = [d for d in [*_extra_bin_dirs(), *cli_locator.cached_dirs()] if d not in have]
    if extra:
        env["PATH"] = os.pathsep.join([p for p in [env.get("PATH", ""), *extra] if p])
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
                raise CliToolUnavailableError(name)
            if not isinstance(args, dict):
                raise CliBridgeError(f"The model gave arguments for {name} that are not a JSON object.")
            calls.append({"id": f"cli_{uuid.uuid4().hex[:12]}", "type": "function",
                          "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}})
        return {"role": "assistant", "content": None, "tool_calls": calls}
    final = obj["final"]
    return {"role": "assistant", "content": final if isinstance(final, str) else json.dumps(final, ensure_ascii=False)}


_REPLY_MARKER = "\n\nYour reply (one JSON object):"


def retry_prompt(prompt, tool_name, tool_names):
    """The prompt for the one retry after a reply named a tool that was not offered: the same prompt plus a correction that lists the tools
    that exist. The list is the names already in the prompt, so it adds nothing the model could not see."""
    note = (f"\n\nCORRECTION: your last reply asked for the tool {tool_name!r}, which is not available in this request. Use only these tools: "
            f"{', '.join(n for n in tool_names if n) or '(none)'}. If none fits, answer in words with {{\"final\": \"...\"}} and say what you cannot do.")
    head = prompt[:-len(_REPLY_MARKER)] if prompt.endswith(_REPLY_MARKER) else prompt
    return head + note + _REPLY_MARKER


# ---------------------------------------------------------------------------------------------------------------------------------
# Claude Code adapter
# ---------------------------------------------------------------------------------------------------------------------------------

def claude_argv(executable, system_prompt_file, model=None, skip=()):
    """The exact command line for one Claude Code call. Everything that could let the CLI act on its own is switched off:
    `--tools ""` removes every built-in tool, `--strict-mcp-config` with no `--mcp-config` loads no MCP server, and no session is saved.
    `skip` names droppable flags (cli_flags.CLAUDE_FLAGS) a CLI version has rejected; a required flag in it raises CliBridgeError."""
    if model and not _MODEL_RE.match(model):
        raise CliBridgeError("The model name contains characters that are not allowed.")
    try:
        flags = cli_flags.build(cli_flags.CLAUDE_FLAGS, skip)
    except ValueError as e:
        raise CliBridgeError(str(e)) from e
    argv = [executable, *flags, *cli_flags.CLAUDE_TAIL, system_prompt_file]
    if model:
        argv += ["--model", model]
    return argv


def _stderr_tail(err, limit=300):
    """The end of a CLI's own error output, on one line, for the message shown to the user. Before this the exit-status errors dropped
    stderr entirely, so a Codex failure read only "exited with status 1" (user report 2026-10-29) with no way to see why."""
    text = " ".join((err or "").split())
    return (" CLI said: " + text[-limit:]) if text else ""


_LOGIN_WORDS = ("oauth", "authenticate", "log in", "login", "sign in", "unauthorized", "401")


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
        detail = str(data.get("result") or data.get("subtype") or "unknown")[:300]
        hint = " Sign in again in a terminal (`claude auth login`, or `/login` inside `claude`), then retry." if any(
            w in detail.lower() for w in _LOGIN_WORDS) else ""
        raise CliBridgeError("The Claude CLI reported an error: " + detail + hint)
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


# Droppable flags a program file has rejected, remembered so the next call does not fail first: {(path, modified time): {flag names}}. In memory only.
_FLAG_SKIPS: dict[tuple[str, int], set[str]] = {}
MAX_FLAG_DROPS = 3          # a run is tried at most this many times more, each time without one more rejected flag


def _flag_key(exe):
    try:
        return (exe, os.stat(exe).st_mtime_ns)
    except OSError:
        return (exe, 0)


def _cli_version(exe, timeout=15):
    """The first line `<exe> --version` prints, or '' when it cannot be read. Used in messages only; never raises."""
    try:
        code, out, err = run_cli([exe, "--version"], "", timeout=timeout, max_output_bytes=16 * 1024)
    except CliBridgeError:
        return ""
    return next((ln.strip() for ln in (out or err or "").splitlines() if ln.strip()), "")[:80] if code == 0 else ""


class _AgentStop:
    """Adapts the agent's Stop button (core/agent/cancel_signal) to the `.is_set()` the runner polls, so pressing Stop ends the CLI
    process instead of waiting for the call to time out."""

    @staticmethod
    def is_set():
        try:
            from ...core import cancel_signal
            return cancel_signal.is_cancelled()
        except Exception:
            return False


class _CliClient(BaseAiProvider):
    """Shared client flow: build the prompt, run the CLI in an empty temp folder, parse the answer into the plugin's message shape.
    A subclass supplies the command line and the output parser; everything that keeps the CLI inside the plugin's gates (no shell,
    scrubbed environment, limits, strict reply parsing) lives here and in `run_cli`."""

    label = ""            # shown to the user: "Claude Code CLI"
    log_name = ""         # metadata-only log provider name
    default_exe = ""
    default_model_name = ""
    not_signed_in_hint = ""

    def __init__(self, executable=None, model=None, status_callback=None, timeout=DEFAULT_TIMEOUT_SECONDS, cancel_event=None):
        self.executable = executable or self.default_exe
        self.model = model
        self.timeout = timeout
        self.cancel_event = cancel_event if cancel_event is not None else _AgentStop()
        self._status_callback = status_callback

    def _emit_status(self, text):
        if self._status_callback:
            with contextlib.suppress(Exception):
                self._status_callback(text)

    def _invoke(self, exe, system_text, prompt, workdir):
        """Runs the CLI once and returns (reply_text, usage_or_None, model_or_None). Raises CliBridgeError."""
        raise NotImplementedError

    flag_table: tuple[cli_flags.Flag, ...] = ()       # cli_flags.CLAUDE_FLAGS or CODEX_FLAGS, set by a subclass

    def _run_with_flag_fallback(self, exe, make_argv, stdin_text, workdir):
        """run_cli, plus the one thing PLAN-053 stage 2 adds: when the CLI itself says it does not know a flag, a DROPPABLE one is left out and the run
        repeated (the user is told what that means, and the choice is remembered for this program file); a REQUIRED one stops the run with a plain
        message. Anything else, including a rejection text this does not recognise, comes back unchanged for the caller's usual handling.
        `make_argv(skip)` builds the command line without the flags in `skip`."""
        key = _flag_key(exe)
        skipped = set(_FLAG_SKIPS.get(key, ()))
        for _attempt in range(MAX_FLAG_DROPS + 1):
            code, out, err = run_cli(make_argv(skipped), stdin_text, timeout=self.timeout, cancel_event=self.cancel_event, cwd=workdir)
            if code == 0 or out.strip():
                return code, out, err
            droppable, required, notes = cli_flags.sort_rejected(self.flag_table, cli_flags.rejected_flags(err))
            if required:
                version = _cli_version(exe)
                log_event("cli_flag_required_rejected", provider=self.log_name, status="refused", flags=",".join(required), cli_version=version, error=True)
                raise CliBridgeError(cli_flags.required_message(self.label, version, required) + f" (It exited with status {code}.)" + _stderr_tail(err))
            droppable -= skipped
            if not droppable:
                return code, out, err
            version = _cli_version(exe)
            for flag in sorted(droppable):
                self._emit_status(cli_flags.dropped_message(self.label, version, flag, notes[flag]))
            log_event("cli_flag_dropped", provider=self.log_name, status="retry", flags=",".join(sorted(droppable)), cli_version=version)
            skipped |= droppable
            _FLAG_SKIPS[key] = set(skipped)
        return code, out, err

    def complete(self, messages, tools=None, max_tokens=None):  # max_tokens unused: the CLIs have no output-token flag
        cli_locator.ensure()  # first call looks at the OS's own PATH (a few seconds at most, once); this runs on a worker thread
        exe = find_executable(self.executable) or find_in_folder(self.executable, self.default_exe)
        if not exe:
            return {"error": f"{self.label} not found. Install it and sign in, or set its path in Settings."}
        self._emit_status(f"Using {self.label}" + (f": {self.model}" if self.model else ""))
        system_text, prompt = build_prompt(messages, tools)
        names = [(t.get("function", t) or {}).get("name", "") for t in (tools or []) if isinstance(t, dict)]
        started = time.monotonic()
        # An empty working directory keeps the CLI from reading a project instruction file or listing files next to the user's data.
        with tempfile.TemporaryDirectory(prefix="cartogen_cli_") as workdir:
            try:
                text, usage, model = self._invoke(exe, system_text, prompt, workdir)
                try:
                    message = parse_reply(text, names)
                except CliToolUnavailableError as unavailable:
                    # One retry only: a second unknown tool is reported as before, so the loop cannot spin on a model that keeps asking.
                    log_event("cli_tool_retry", provider=self.log_name, status="retry")
                    prompt = retry_prompt(prompt, unavailable.name, names)
                    text, usage, model = self._invoke(exe, system_text, prompt, workdir)
                    message = parse_reply(text, names)
            except CliBridgeError as e:
                log_event("cli_bridge_error", provider=self.log_name, error_class="CliBridgeError",
                          duration_ms=int((time.monotonic() - started) * 1000))
                return {"error": str(e)}
        log_event("cli_bridge_call", provider=self.log_name, status="ok", duration_ms=int((time.monotonic() - started) * 1000))
        return {"message": message, "model": model or self.model or self.default_model_name,
                "usage": usage or estimate_usage(prompt, text)}


class ClaudeCliClient(_CliClient):
    """Claude Code (`claude -p`) used as a model on the user's own login. See the module docstring for status."""
    label = "Claude Code CLI"
    log_name = "claude_cli"
    default_exe = "claude"
    default_model_name = "claude-cli"
    flag_table = cli_flags.CLAUDE_FLAGS

    def _invoke(self, exe, system_text, prompt, workdir):
        system_file = os.path.join(workdir, "system.txt")
        with open(system_file, "w", encoding="utf-8") as fh:
            fh.write(system_text)
        code, out, err = self._run_with_flag_fallback(exe, lambda skip: claude_argv(exe, system_file, self.model, skip), prompt, workdir)
        if code != 0 and not out.strip():
            raise CliBridgeError(f"The Claude CLI exited with status {code}. Is it signed in (`claude` once, then /login)?" + _stderr_tail(err))
        return parse_claude_result(out)


# ---------------------------------------------------------------------------------------------------------------------------------
# Codex CLI adapter
# ---------------------------------------------------------------------------------------------------------------------------------

# Item types in `codex exec --json` that mean Codex acted on its own (ran a command, edited a file, called an MCP tool, searched the
# web) instead of just answering. Any of these means a step happened outside the plugin's confirmation and egress gates.
_CODEX_OWN_ACTION_ITEMS = ("command_execution", "file_change", "mcp_tool_call", "web_search")


def codex_argv(executable, model=None, skip=()):
    """The exact command line for one Codex call. The prompt is read from stdin (the trailing `-`). `--sandbox read-only` stops writes
    and `--ephemeral` keeps no session file; `--ignore-user-config` and `--ignore-rules` keep the user's own config and exec-policy
    files from changing what runs. Unlike Claude Code, Codex has no documented switch that removes its shell tool, so
    `parse_codex_events` rejects a run in which Codex acted on its own.
    `skip` names droppable flags (cli_flags.CODEX_FLAGS) a CLI version has rejected; a required flag in it raises CliBridgeError."""
    if model and not _MODEL_RE.match(model):
        raise CliBridgeError("The model name contains characters that are not allowed.")
    try:
        argv = [executable, *cli_flags.build(cli_flags.CODEX_FLAGS, skip)]
    except ValueError as e:
        raise CliBridgeError(str(e)) from e
    if model:
        argv += ["--model", model]
    return [*argv, "-"]


def parse_codex_events(stdout):
    """Reads `codex exec --json` output (JSON Lines). Returns (text, usage_or_None, None).

    The answer is the last `item.completed` event whose item type is `agent_message`. Raises when the stream has an error or failed turn,
    has no answer, or shows Codex ran a command, edited a file, called an MCP tool or searched the web on its own."""
    events = []
    for raw in (stdout or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("{"):
            with contextlib.suppress(ValueError):
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    events.append(obj)
    if not events:
        raise CliBridgeError("The Codex CLI did not return JSON events. Is it a current version (`npm i -g @openai/codex`)?")
    text = None
    usage = None
    for ev in events:
        kind = ev.get("type")
        if kind in ("error", "turn.failed"):
            err = ev.get("error")
            detail = ev.get("message") or (err.get("message") if isinstance(err, dict) else None)
            raise CliBridgeError("The Codex CLI reported an error: " + str(detail or kind)[:300])
        item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
        if kind and kind.startswith("item.") and item.get("type") in _CODEX_OWN_ACTION_ITEMS:
            raise CliBridgeError(f"The Codex CLI tried to act on its own ({item.get('type')}) instead of answering; that is not allowed here.")
        if kind == "item.completed" and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            text = item["text"]
        if kind == "turn.completed" and isinstance(ev.get("usage"), dict):
            u = ev["usage"]
            usage = {"input_tokens": int(u.get("input_tokens") or 0), "output_tokens": int(u.get("output_tokens") or 0)
                     + int(u.get("reasoning_output_tokens") or 0)}
    if text is None:
        raise CliBridgeError("The Codex CLI returned no answer.")
    return text, usage, None


class CodexCliClient(_CliClient):
    """Codex (`codex exec`) used as a model on the user's own login. UNVERIFIED against a real logged-in Codex; see the module docstring."""
    label = "Codex CLI"
    log_name = "codex_cli"
    default_exe = "codex"
    default_model_name = "codex-cli"
    flag_table = cli_flags.CODEX_FLAGS

    def _invoke(self, exe, system_text, prompt, workdir):
        # Codex has no system-prompt slot, so the instructions lead the single stdin prompt.
        code, out, err = self._run_with_flag_fallback(exe, lambda skip: codex_argv(exe, self.model, skip), system_text + "\n\n" + prompt, workdir)
        if code != 0 and not out.strip():
            raise CliBridgeError(f"The Codex CLI exited with status {code}. Is it signed in (`codex login`)?" + _stderr_tail(err))
        try:
            return parse_codex_events(out)
        except CliBridgeError as e:
            # A non-zero exit with unusable stdout is almost always a rejected flag or a login problem, which Codex says on stderr.
            if code != 0:
                raise CliBridgeError(str(e) + _stderr_tail(err)) from e
            raise
