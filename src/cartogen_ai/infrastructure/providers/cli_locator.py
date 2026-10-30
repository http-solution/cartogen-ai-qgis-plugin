"""Where the user's own terminal would find a program, worked out the same way on every OS (PLAN-041).

QGIS started from a desktop icon, the Start menu or Finder does not get the PATH a terminal has, so `shutil.which("codex")` can fail for a
program that works in the terminal. Three sources of the real PATH, none of them a guess about where a vendor's installer puts things:
  * Windows: the user and system PATH in the registry (what a new terminal reads). A program started from Explorer keeps the environment
    Explorer had when it started, so a CLI installed since then is missing from it until the next sign-in.
  * macOS and Linux: the user's own login shell asked for its PATH (what Terminal gets after .zprofile / .bashrc ran). A GUI session
    reads those files only at login, and often not at all.
  * Everywhere: the folder `npm prefix -g` names, because a custom npm prefix is the commonest reason an npm-installed CLI is not found.
Looking starts programs (a shell, npm) and can take seconds, so it is done once on a background thread (`ensure`) and the result is cached;
`cached_dirs` only reads the cache and is safe on the UI thread. Never raises. Not run against a real Windows or macOS machine from the
cloud sandbox: the registry read and the shell call are covered by tests with stand-ins.
"""
import contextlib
import os
import shutil
import subprocess
import threading

_SHELLS = frozenset({"bash", "zsh", "fish", "sh", "dash", "ksh"})
_START, _END = "__CARTOGEN_PATH_START__", "__CARTOGEN_PATH_END__"
_lock = threading.Lock()
_cache = {"dirs": None}  # None = not looked yet


def _split(path_text):
    return [p for p in (path_text or "").split(os.pathsep) if p]


def windows_registry_path():
    """System then user PATH from the registry, with %VARS% expanded; [] off Windows or when unreadable."""
    try:
        import winreg  # only exists on Windows
    except ImportError:
        return []
    out = []
    for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(hive, sub) as key:
                value, _kind = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        out += _split(os.path.expandvars(str(value)))
    return out


def login_shell_path(timeout=6):
    """The PATH the user's login shell has, or []. Only a plain shell named in `_SHELLS` at an absolute path is run, with no input and a
    time limit, and only the text between two markers is read (a shell may print banners)."""
    shell = os.environ.get("SHELL", "")
    if os.name == "nt" or not shell or not os.path.isabs(shell) or not os.path.isfile(shell) or os.path.basename(shell) not in _SHELLS:
        return []
    try:
        proc = subprocess.run([shell, "-l", "-i", "-c", f'printf "%s" "{_START}$PATH{_END}"'], stdin=subprocess.DEVNULL,  # noqa: S603 -- fixed command line, shell vetted above
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False, start_new_session=True)
    except (OSError, subprocess.SubprocessError):
        return []
    text = proc.stdout.decode("utf-8", "replace")
    start, end = text.find(_START), text.find(_END)
    if start == -1 or end == -1 or end < start:
        return []
    return _split(text[start + len(_START):end])


def npm_global_bin(search_dirs, timeout=10):
    """The folder npm puts global programs in (`npm prefix -g`; its bin/ subfolder except on Windows), or []."""
    npm = shutil.which("npm", path=os.pathsep.join(search_dirs)) if search_dirs else shutil.which("npm")
    if not npm:
        return []
    kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
    try:
        proc = subprocess.run([npm, "prefix", "-g"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,  # noqa: S603 -- fixed arguments, no shell
                              timeout=timeout, check=False, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return []
    prefix = proc.stdout.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
    prefix = prefix[0].strip()
    if not prefix or not os.path.isdir(prefix):
        return []
    return [prefix if os.name == "nt" else os.path.join(prefix, "bin")]


def _compute():
    base = windows_registry_path() if os.name == "nt" else login_shell_path()
    seen, out = set(), []
    for d in [*base, *npm_global_bin([*base, *_split(os.environ.get("PATH", ""))])]:
        if d and d not in seen and os.path.isdir(d):
            seen.add(d)
            out.append(d)
    return out


def ensure(refresh=False):
    """Looks once (or again with refresh=True) and caches the folders. Call from a background thread; may take several seconds."""
    with _lock:
        if _cache["dirs"] is None or refresh:
            with contextlib.suppress(Exception):
                _cache["dirs"] = _compute()
            if _cache["dirs"] is None:
                _cache["dirs"] = []
        return list(_cache["dirs"])


def cached_dirs():
    """What `ensure` found, or [] if it has not run. Never starts a program, so it is safe on the UI thread."""
    dirs = _cache["dirs"]
    return list(dirs) if dirs else []
