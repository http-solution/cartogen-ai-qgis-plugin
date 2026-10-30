"""What the Settings window needs to know about a CLI bridge provider (PLAN-039), kept free of Qt so it is testable without QGIS:
is the program there, which version, is the user signed in, and how do they sign in.

Status: UNVERIFIED against a real signed-in CLI, like cli_bridge.py. `--version` is assumed to exist on all three CLIs (it is
conventional; not read in their docs for each). The terminal launch is untested on every platform: it is attempted only when the program
path is made of plain characters, and otherwise the caller shows the command for the user to run themselves."""
import json
import os
import re
import shutil
import subprocess
import sys
import time

from . import cli_bridge as cb
from . import cli_locator

# provider -> (constructor, command that starts the sign-in, hint shown when the program is missing)
_SPECS = {
    # `claude auth status` is confirmed on the owner's machine (Claude Code 2.1.314, 2026-10-30), so `claude auth login`, the same command
    # group, is used for the sign-in; it was not run from the sandbox.
    "claude_cli": (cb.ClaudeCliClient, ["auth", "login"], "Install Claude Code, then run `claude auth login` in a terminal and sign in."),
    "codex_cli": (cb.CodexCliClient, ["login"], "Install the Codex CLI, then run `codex login`."),
}
DEFAULT_PROGRAM = {"claude_cli": "claude", "codex_cli": "codex"}
_PLAIN_PATH = re.compile(r"^[A-Za-z0-9_./\\:+-]+$")  # no spaces, quotes or shell characters: safe to hand to a terminal launcher
CHECK_PROMPT = "Reply with the single word: ok"
LABELS = {"claude_cli": "Claude Code CLI", "codex_cli": "Codex CLI"}
VENDORS = {"claude_cli": "Anthropic", "codex_cli": "OpenAI"}

# How to install each CLI, from the vendors' own pages as found by search on 2026-10-30 (Claude Code: its install script and npm package;
# Codex: the openai/codex README's PowerShell installer, the npm package and the Homebrew cask). Shown to the user to copy and run
# themselves: the plugin never runs an installer. Not run from the sandbox.
_INSTALL = {
    "claude_cli": {"windows": ["irm https://claude.ai/install.ps1 | iex", "npm install -g @anthropic-ai/claude-code"],
                   "mac": ["curl -fsSL https://claude.ai/install.sh | bash", "npm install -g @anthropic-ai/claude-code"],
                   "linux": ["curl -fsSL https://claude.ai/install.sh | bash", "npm install -g @anthropic-ai/claude-code"]},
    "codex_cli": {"windows": ["irm https://chatgpt.com/codex/install.ps1 | iex", "npm install -g @openai/codex"],
                  "mac": ["brew install --cask codex", "npm install -g @openai/codex"],
                  "linux": ["npm install -g @openai/codex"]},
}


def install_commands(provider, platform=None):
    """The commands that install this CLI on this OS, best first."""
    platform = platform or sys.platform
    key = "windows" if platform.startswith("win") else ("mac" if platform == "darwin" else "linux")
    return list(_INSTALL[provider][key])


def install_hint(provider):
    return _SPECS[provider][2]


def known(provider):
    return provider in _SPECS


def program_for(provider, configured):
    return (configured or "").strip() or DEFAULT_PROGRAM[provider]


def locate(provider, configured=""):
    """The real file for this provider's program, or None. A folder in the field means '<default program> inside that folder'."""
    program = program_for(provider, configured)
    return cb.find_executable(program) or cb.find_in_folder(program, DEFAULT_PROGRAM[provider])


def not_found_message(provider, configured=""):
    """Says what was looked for and how to give the plugin the exact location (the plugin may see a shorter PATH than a terminal)."""
    program = program_for(provider, configured)
    where = "where" if os.name == "nt" else "which"
    return (f"Program '{program}' was not found. {_SPECS[provider][2]} If it already works in your terminal, run "
            f"`{where} {DEFAULT_PROGRAM[provider]}` there and paste the full path it prints into this field.")


def signin_command(provider, exe="", configured=""):
    """The command a user would type to sign in, as text for display."""
    program = exe or program_for(provider, configured)
    return " ".join([program, *_SPECS[provider][1]])


def detect(provider, configured="", timeout=15):
    """{'found': bool, 'path': str, 'version': str, 'problem': str}. Runs `<program> --version` (no model call, no tokens)."""
    path = locate(provider, configured)
    if not path:
        return {"found": False, "path": "", "version": "", "problem": not_found_message(provider, configured)}
    try:
        code, out, err = cb.run_cli([path, "--version"], "", timeout=timeout, max_output_bytes=64 * 1024, cwd=os.path.dirname(path) or None)
    except cb.CliBridgeError as e:
        return {"found": True, "path": path, "version": "", "problem": str(e)}
    first = next((ln.strip() for ln in (out or err or "").splitlines() if ln.strip()), "")
    if code != 0 and not first:
        return {"found": True, "path": path, "version": "", "problem": f"'{os.path.basename(path)} --version' exited with status {code}."}
    return {"found": True, "path": path, "version": first[:80], "problem": ""}


def signin_status(provider, path, timeout=15):
    """Is the user signed in to this CLI? Asks the program itself, with no model call and no tokens. Returns {'state', 'note'} where state
    is 'yes', 'no' or 'unknown' ('likely' is accepted by `usable` for a future adapter); never raises.

    UNVERIFIED except the Codex 'logged in' case (`codex login status` printed "Logged in using ChatGPT" on the owner's machine,
    2026-10-30). `claude auth status` was confirmed by the owner's Connections window (2026-10-30); when the answer cannot
    be read the state is 'unknown' rather than a guess, and Check connection stays the one test that proves the login works."""
    try:
        if provider == "codex_cli":
            code, out, err = cb.run_cli([path, "login", "status"], "", timeout=timeout, max_output_bytes=64 * 1024)
            text = " ".join((out or err or "").split())
            low = text.lower()
            if "not logged in" in low or "logged out" in low:
                return {"state": "no", "note": text[:120]}
            if code == 0 and "logged in" in low:
                return {"state": "yes", "note": text[:120]}
            return {"state": "unknown", "note": text[:120]}
        if provider == "claude_cli":
            code, out, err = cb.run_cli([path, "auth", "status"], "", timeout=timeout, max_output_bytes=64 * 1024)
            try:
                data = json.loads(out)
            except ValueError:
                data = None
            if isinstance(data, dict) and isinstance(data.get("loggedIn"), bool):
                method = str(data.get("authMethod") or "").strip()
                return {"state": "yes" if data["loggedIn"] else "no", "note": f"sign-in method: {method}" if method else ""}
            low = " ".join((out or err or "").split()).lower()
            if "not logged in" in low or "not signed in" in low:
                return {"state": "no", "note": ""}
            return {"state": "unknown", "note": ""}
    except cb.CliBridgeError as e:
        return {"state": "unknown", "note": str(e)[:120]}
    return {"state": "unknown", "note": ""}


def detect_all(configured=None):
    """Looks for every CLI provider on this computer: program found, version, and whether the user is signed in. `configured` maps a
    provider to the program text from the form (blank = the default name). Runs `--version` and a sign-in status command per CLI found;
    no model call, nothing sent anywhere. Returns a list of dicts in a fixed order."""
    configured = configured or {}
    cli_locator.ensure(refresh=True)  # ask the OS what the user's own terminal would search (a shell / the registry / npm), once per detection
    searched = cb.search_folders()
    out = []
    for provider in _SPECS:
        tried = (configured.get(provider) or "").strip() or DEFAULT_PROGRAM[provider]
        info = detect(provider, configured.get(provider, ""))
        if not info["found"] and tried != DEFAULT_PROGRAM[provider]:
            # A saved path that no longer exists (program moved or reinstalled) should not hide a CLI that is on PATH under its usual name.
            fallback = detect(provider, "")
            if fallback["found"]:
                info = {**fallback, "problem": ""}
        sign = signin_status(provider, info["path"]) if info["found"] else {"state": "missing", "note": ""}
        out.append({"provider": provider, "label": LABELS[provider], "found": info["found"], "path": info["path"],
                    "version": info["version"], "problem": info["problem"], "state": sign["state"], "note": sign["note"],
                    "tried": tried, "searched": searched,
                    "diagnosis": [] if info["found"] else cb.diagnose_missing(DEFAULT_PROGRAM[provider])})
    return out


_STATE_TEXT = {"yes": "signed in", "likely": "probably signed in", "no": "not signed in", "unknown": "sign-in not confirmed"}


def describe(entry, short=False):
    """One line saying whether the program is there and whether the user is signed in. `short` drops the program's name, for a page
    that already has it as its title (a narrow window wrapped the long form onto two lines)."""
    state = _STATE_TEXT.get(entry["state"], "sign-in not confirmed")
    if not entry["found"]:
        looked = entry.get("searched") or []
        if short:
            return f"Not found on this computer (looked in {len(looked)} folders; hover to list them)" if looked else "Not found on this computer"
        return f"{entry['label']}: not found on this computer"
    if entry.get("problem") and not entry["version"]:
        return f"Found at {entry['path']}, but it could not be started: {entry['problem']}" if short else (
            f"{entry['label']}: found at {entry['path']}, but it could not be started: {entry['problem']}")
    if short:
        return f"Found {entry['version']} \u00b7 {state}" if entry["version"] else f"Found \u00b7 {state}"
    version = f", {entry['version']}" if entry["version"] else ""
    return f"{entry['label']}: found{version}, {state}"


def setup_step(entry, verified=False, active=False, platform=None):
    """The next thing the user has to do to get this CLI working, for the guided setup on its page. Returns {'kind', 'button', 'detail',
    'command'}; kind is one of 'install', 'signin', 'verify', 'ready', 'in_use'. `entry` is a `detect_all` result (None = not looked yet).
    Pure; the window decides what pressing the button does."""
    if entry is None:
        return {"kind": "looking", "button": "Looking...", "detail": "", "command": ""}
    label = entry["label"]
    if not entry["found"]:
        commands = install_commands(entry["provider"], platform)
        diagnosis = entry.get("diagnosis") or []
        seen = ("\n\nQGIS could see these, but could not use them (if " + label + " works in your terminal, pick the program with "
                "Browse...):\n  " + "\n  ".join(diagnosis)) if diagnosis else ""
        return {"kind": "install", "button": "Copy install command", "command": commands[0],
                "detail": f"{label} was not found. If it is not installed, run this in a terminal, then press Detect again:\n  "
                          + "\n  or ".join(commands) + seen}
    if active:
        return {"kind": "in_use", "button": "In use", "detail": f"{label} is the connection in use. Press OK to save.", "command": ""}
    if verified:
        return {"kind": "ready", "button": "Use this connection", "detail": "Connected: it answered a test question.", "command": ""}
    if entry["state"] == "no":
        return {"kind": "signin", "button": "Sign in...", "command": "",
                "detail": f"{label} is installed but you are not signed in. A terminal opens for the sign-in; this window notices when you "
                          "finish, tests the connection and starts using it."}
    if entry["state"] in ("yes", "likely"):
        return {"kind": "verify", "button": "Connect", "command": "",
                "detail": "Signed in. Connect asks it one short test question (a few tokens of your own plan), then starts using it."}
    return {"kind": "verify", "button": "Connect", "command": "",
            "detail": "The sign-in status could not be read. Connect tests it with one short question; if you are not signed in you are "
                      "taken to the sign-in."}


def consent_text(provider):
    """What the user agrees to before the plugin runs their CLI as the model (shown in a confirmation, once per window)."""
    label, vendor = LABELS[provider], VENDORS[provider]
    return (f"Use {label} as the model?\n\nCartogen AI will run the {DEFAULT_PROGRAM[provider]} program on this computer with your own "
            f"login. The conversation, including any layer or attribute data a tool surfaces, is sent to {vendor}'s service, so treat it "
            "as a cloud provider and check that your plan's terms allow this use. Cartogen AI never sees or stores your login. "
            "This is experimental.")


def usable(entry):
    """Worth offering a 'Use' button: the program is there and a sign-in was found (or is likely)."""
    return bool(entry["found"]) and entry["state"] in ("yes", "likely")


def stage_of(error_text):
    """Which step failed, from the client's error text: 'install', 'signin' or 'other'. Used to pick the button the user should press."""
    text = (error_text or "").lower()
    if "not found" in text or "executable path" in text:
        return "install"
    # Codex 0.165 signed out reports "Reconnecting... unexpected status 401 Unauthorized: Missing bearer or basic authentication"
    # (seen in the 2026-10-28 audit against the real CLI), with none of the words below it, so it was filed under "other".
    if any(w in text for w in ("signed in", "login", "log in", "sign in", "401", "unauthorized", "not authenticated", "authentication")):
        return "signin"
    return "other"


def check_connection(provider, configured="", model=None, timeout=120):
    """Finds the program, then asks the model one tiny question through the same client the agent uses (this spends a few tokens of the
    user's own plan). Returns {'ok', 'stage', 'message', 'seconds', 'version', 'path'}."""
    info = detect(provider, configured)
    if not info["found"]:
        return {"ok": False, "stage": "install", "message": info["problem"], "seconds": 0.0, "version": "", "path": ""}
    client = _SPECS[provider][0](executable=info["path"], model=model or None, timeout=timeout)
    started = time.monotonic()
    result = client.complete([{"role": "user", "content": CHECK_PROMPT}], None)
    seconds = round(time.monotonic() - started, 1)
    base = {"seconds": seconds, "version": info["version"], "path": info["path"]}
    if "error" in result:
        return {**base, "ok": False, "stage": stage_of(result["error"]), "message": result["error"]}
    text = (result.get("message") or {}).get("content") or ""
    return {**base, "ok": True, "stage": "ready", "message": f"Answered in {seconds} s ({text.strip()[:40] or 'no text'})."}


def terminal_command(provider, exe, platform=None, which=shutil.which):
    """An argument list that opens a terminal running the sign-in command, or None when it cannot be done safely or no terminal program
    is found (the caller then shows signin_command() for the user to run). Pure apart from `which`."""
    platform = platform or sys.platform
    if not exe or not _PLAIN_PATH.match(exe):
        return None
    args = _SPECS[provider][1]
    if platform.startswith("win"):
        return ["cmd.exe", "/c", "start", "", "cmd.exe", "/k", exe, *args]
    line = " ".join([exe, *args])
    if platform == "darwin":
        return ["osascript", "-e", f'tell application "Terminal" to do script "{line}"', "-e", 'tell application "Terminal" to activate']
    for term, flag in (("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"), ("xterm", "-e")):
        found = which(term)
        if found:
            return [found, flag, exe, *args]
    return None


def open_signin_terminal(provider, configured=""):
    """Tries to open a terminal for signing in. {'launched': bool, 'command': str, 'message': str}; never raises."""
    program = program_for(provider, configured)
    path = locate(provider, configured)
    command_text = signin_command(provider, path or program)
    if not path:
        return {"launched": False, "command": command_text, "message": not_found_message(provider, configured)}
    argv = terminal_command(provider, path)
    if argv is None:
        return {"launched": False, "command": command_text,
                "message": f"Open a terminal yourself and run: {command_text}"}
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,  # noqa: S603 -- list, no shell
                         env=cb.scrubbed_environment(), close_fds=True)
    except OSError as e:
        return {"launched": False, "command": command_text, "message": f"Could not open a terminal ({type(e).__name__}). Run: {command_text}"}
    return {"launched": True, "command": command_text,
            "message": f"A terminal window should have opened running: {command_text}. Sign in there, then press Check connection."}
