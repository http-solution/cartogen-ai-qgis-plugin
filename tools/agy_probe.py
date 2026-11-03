#!/usr/bin/env python3
"""One-step check of the Antigravity CLI (`agy`) for the plugin's planned provider (master list LEAD-10), the same on Windows, macOS and Linux.

    python agy_probe.py [--exe PATH_TO_AGY] [--out agy_probe_report.md] [--timeout 60]

Run it in a normal terminal (not inside QGIS), signed in to agy as you normally use it. Standard library only, Python 3.8 or newer.
What it does, in order, with no files read or changed outside --out:
  1. records this machine (OS, version, architecture, Python), so the result says which PC it is about;
  2. finds agy: --exe, else PATH, else the usual install folders for this OS;
  3. runs `agy --version` and `agy --help` (no model call);
  4. runs ONE short prompt the way the plugin would run a CLI: `agy -p "Reply with the single word: ok"` with standard input closed and standard
     output and error captured by pipes (not a terminal), killing it after --timeout seconds if it hangs. This one call uses your agy sign-in
     and may count against your quota; it sends only that prompt.
It prints a plain verdict and writes a report to send back. It cannot see whether a browser or permission prompt opened: look, and say so.
Nothing is sent anywhere by this script."""
import argparse
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import time

PROMPT = "Reply with the single word: ok"


def candidate_folders():
    """Folders where agy is commonly installed on this OS, besides PATH. Pure apart from reading the environment."""
    home = os.path.expanduser("~")
    folders = [os.path.join(home, ".local", "bin"), os.path.join(home, "bin"), os.path.join(home, ".npm-global", "bin")]
    if sys.platform.startswith("win"):
        for key in ("APPDATA", "LOCALAPPDATA", "ProgramFiles"):
            base = os.environ.get(key)
            if base:
                folders += [os.path.join(base, "npm"), os.path.join(base, "Programs", "agy"), os.path.join(base, "agy"), os.path.join(base, "Antigravity", "bin")]
    elif sys.platform == "darwin":
        folders += ["/opt/homebrew/bin", "/usr/local/bin", "/Applications/Antigravity.app/Contents/Resources/app/bin"]
    else:
        folders += ["/usr/local/bin", "/usr/bin", "/opt/antigravity/bin", "/snap/bin"]
    return [f for f in folders if os.path.isdir(f)]


def find_agy(exe=None):
    """(path or None, how it was found). Pure apart from the file system."""
    if exe:
        return (exe, "--exe") if os.path.isfile(exe) else (None, f"--exe {exe} is not a file")
    found = shutil.which("agy")
    if found:
        return found, "PATH"
    found = shutil.which("agy", path=os.pathsep.join(candidate_folders()))
    return (found, "a usual install folder") if found else (None, "not on PATH or in the usual folders")


def run(cmd, timeout):
    """(exit code or None when killed, stdout, stderr, seconds). Standard input is closed; output is piped; the whole process tree is stopped on timeout."""
    started = time.time()
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True, "errors": "replace"}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)                                                   # noqa: S603  # fixed argv, the user's own agy
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err, time.time() - started
    except subprocess.TimeoutExpired:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)   # noqa: S603, S607
        else:
            import signal
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
        out, err = proc.communicate()
        return None, out or "", err or "", time.time() - started


def verdict(code, out, err, seconds, timeout):
    """One plain sentence about the `-p` call. Pure."""
    if code is None:
        return f"HUNG: no exit within {timeout} s with output piped (the plugin would freeze waiting). Captured output: {len(out)} chars."
    if code != 0:
        return f"FAILED: exit code {code} after {seconds:.1f} s. {('Error text: ' + err.strip()[:300]) if err.strip() else 'No error text.'}"
    if not out.strip():
        return f"SILENT: exit code 0 after {seconds:.1f} s but nothing printed to standard output (the plugin would see an empty answer)."
    return f"ANSWERED: exit code 0 after {seconds:.1f} s; standard output: {out.strip()[:200]!r}."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--exe")
    parser.add_argument("--out", default="agy_probe_report.md")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)
    lines = ["# agy probe", "", f"- machine: {platform.system()} {platform.release()} ({platform.version()[:80]}), {platform.machine()}",
             f"- python: {platform.python_version()}", f"- shell: {os.environ.get('SHELL') or os.environ.get('COMSPEC') or 'unknown'}"]
    path, how = find_agy(args.exe)
    lines.append(f"- agy: {path or 'NOT FOUND'} ({how})")
    if not path:
        lines += ["", "agy was not found. Install it, or run again with --exe <full path to agy>. Nothing else was tried."]
        text = "\n".join(lines) + "\n"
        print(text)
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
        return 2
    for cmd in ([path, "--version"], [path, "--help"]):
        code, out, err, seconds = run(cmd, 30)
        lines += ["", f"## agy {cmd[-1]}", f"exit code: {code} ({seconds:.1f} s)", "```", (out or err).strip()[:4000] or "(no output)", "```"]
    code, out, err, seconds = run([path, "-p", PROMPT], args.timeout)
    said = verdict(code, out, err, seconds, args.timeout)
    lines += ["", f"## agy -p {PROMPT!r} (stdin closed, output piped)", said, "", "stdout:", "```", out.strip()[:2000] or "(empty)", "```", "stderr:", "```",
              err.strip()[:2000] or "(empty)", "```", "", "Also write by hand: did a browser, a sign-in or a permission prompt open? Did any file appear in the current folder?"]
    text = "\n".join(lines) + "\n"
    pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print(said)
    print(f"Report written to {os.path.abspath(args.out)}. Send that file back.")
    return 0 if said.startswith("ANSWERED") else 1


if __name__ == "__main__":
    sys.exit(main())
