"""What the Settings window needs to know about a CLI bridge provider (PLAN-039), kept free of Qt so it is testable without QGIS:
is the program there, which version, is the user signed in, and how do they sign in.

Status: UNVERIFIED against a real signed-in CLI, like cli_bridge.py. `--version` is assumed to exist on all three CLIs (it is
conventional; not read in their docs for each). The terminal launch is untested on every platform: it is attempted only when the program
path is made of plain characters, and otherwise the caller shows the command for the user to run themselves."""
import os
import re
import shutil
import subprocess
import sys
import time

from . import cli_bridge as cb

# provider -> (constructor, command that starts the sign-in, hint shown when the program is missing)
_SPECS = {
    "claude_cli": (cb.ClaudeCliClient, [], "Install Claude Code, then run `claude` once in a terminal and sign in."),
    "codex_cli": (cb.CodexCliClient, ["login"], "Install the Codex CLI, then run `codex login`."),
    "gemini_cli": (cb.GeminiCliClient, [], "Install the Gemini CLI, then run `gemini` once and choose Login with Google."),
}
DEFAULT_PROGRAM = {"claude_cli": "claude", "codex_cli": "codex", "gemini_cli": "gemini"}
_PLAIN_PATH = re.compile(r"^[A-Za-z0-9_./\\:+-]+$")  # no spaces, quotes or shell characters: safe to hand to a terminal launcher
CHECK_PROMPT = "Reply with the single word: ok"


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


def stage_of(error_text):
    """Which step failed, from the client's error text: 'install', 'signin' or 'other'. Used to pick the button the user should press."""
    text = (error_text or "").lower()
    if "not found" in text or "executable path" in text:
        return "install"
    if "signed in" in text or "login" in text or "log in" in text:
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
