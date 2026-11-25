"""The evidence watcher for the computer-use smoke run: NO window, nothing to click, nothing for the agent to remember.

The agent writes its result as ONE line at the end of results/RESULTS_GUI.csv (and its notes into results/evidence/<row>/observations.txt). This module runs inside QGIS (started by
tools/smoke_watch_start.py), looks at that file every few seconds and, for every row that is new, saves the evidence next to the notes: a picture of the screen (taken from outside QGIS,
with a checked fallback to a picture of the QGIS window), the layer list, the project state, the log and the plugin's own tool-call record. The cards with the real package folder in every path (CARDS_FILLED.md) are written by tools/prepare_run.py, which the .bat files run before QGIS opens.

Replaces the 'Smoke test' dock (tools/smoke_dock.py, removed 2026-11-25): the owner did not want a panel, the dock's buttons were blocked by the Claude app's own safety check, and its
layout hid its buttons on a small screen. Status: the pure parts are tested offline (tests/test_smoke_cards.py); the QGIS half is exercised with fakes by tests/test_smoke_watch_live.py in the
CI live job. NOT yet run in a real desktop QGIS 4.2.3 session."""
import contextlib
import json
import os
import sys

import smoke_cards as cards_mod
from qgis.PyQt.QtCore import QTimer

EXPECTED_QGIS = "4.2.3"
POLL_MS = 3000
_KEEP = []          # the watcher and its timer must stay referenced, or Qt may collect them


def _capture(path):
    """Starts the out-of-process screen capture and returns at once (never waits, never raises): a screenshot must not be able to take QGIS down with it."""
    import subprocess
    argv = cards_mod.screen_capture_command(path)
    if argv is None:
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(argv, creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)  # noqa: S603
    except OSError:
        return False
    return True


def _grab_window(path):
    """The picture taken from INSIDE QGIS (its main window), used only when the out-of-process capture left no file."""
    from qgis.utils import iface
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return bool(iface.mainWindow().grab().save(path))


def capture_with_fallback(path, start=None, grab=None, schedule=None, delay_ms=6000, done=None):
    """Starts the out-of-process screen capture and, `delay_ms` later, checks that a file really exists; when it does not, takes the picture from inside QGIS instead.
    Why: the capture function returns True as soon as PowerShell has been STARTED, so a blocked PowerShell (an antivirus window was open on the owner's PC in the 2026-11-24 run) left no
    PNG while the old dock still said 'saved screenshot'. `done(ok, how)` is told the truth. Never raises."""
    start = start or _capture
    grab = grab or _grab_window
    schedule = schedule or QTimer.singleShot

    def check():
        try:
            ok = os.path.isfile(path) and os.path.getsize(path) > 0
            how = "screen capture"
            if not ok:
                how = "QGIS window picture (the screen capture left no file)"
                ok = bool(grab(path)) and os.path.isfile(path)
        except Exception as e:                     # a screenshot must never be able to take the run down
            ok, how = False, f"failed: {type(e).__name__}"
        if done is not None:
            with contextlib.suppress(Exception):
                done(ok, how)
    started = False
    with contextlib.suppress(Exception):
        started = start(path)
    schedule(delay_ms, check)
    return started


class Watcher:
    """Takes the evidence for every row that gets a new line in RESULTS_GUI.csv. `snap(row, note)` and `capture(path, done=...)` are injected so the logic runs without QGIS."""

    def __init__(self, results, snap, capture=capture_with_fallback, log=None):
        self.results, self.snap, self.capture = results, snap, capture
        self.log = log or (lambda text: cards_mod.start_log(results, text))
        self.seen = set(cards_mod.load_results(results))        # rows that already have a line when we start are not re-snapped

    def poll(self):
        """One look at the file. Returns the row ids handled. Never raises (a Qt timer must not let anything escape)."""
        handled = []
        try:
            fresh = cards_mod.new_result_rows(self.results, self.seen)
        except Exception as e:
            self.log(f"watcher: could not read RESULTS_GUI.csv ({type(e).__name__}: {e})")
            return handled
        for row_id, line in fresh:
            self.seen.add(row_id)
            handled.append(row_id)
            try:
                self.capture(os.path.join(self.results, "screens", f"{row_id}.png"),
                             done=lambda ok, how, r=row_id: self.log(f"watcher: {r} screen picture {'saved' if ok else 'NOT saved'} ({how})"))
                self.snap(row_id, str(line.get("note", "")))
                self.log(f"watcher: evidence taken for {row_id} ({line.get('status', '')})")
            except Exception as e:
                cards_mod.start_error(self.results, f"taking the evidence for {row_id}", e)
        return handled


def start(package_dir):
    """Wires the evidence collector, writes the filled cards, records the human rows and starts the timer. Returns the watcher."""
    from qgis.core import Qgis, QgsSettings
    package_dir = os.path.abspath(package_dir)
    tools = os.path.join(package_dir, "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import collect_evidence as ce
    results = os.path.join(package_dir, "results")
    cards_mod.start_log(results, "start(): building the watcher")
    ce.setup(results)
    QgsSettings().setValue("cartogen_ai/evidence_enabled", True)       # the plugin writes its own per-request evidence folder: arguments, results and tools actually called
    with open(os.path.join(package_dir, "cards.json"), encoding="utf-8") as fh:
        cards = json.load(fh)
    version = Qgis.version()
    build = ""
    with contextlib.suppress(OSError), open(os.path.join(package_dir, "BUILD.txt"), encoding="utf-8") as fh:
        build = fh.read().strip()
    with open(os.path.join(results, "ENVIRONMENT.json"), "w", encoding="utf-8") as fh:
        json.dump({"qgis": version, "expected": EXPECTED_QGIS, "plugin": ce._plugin_version(), "python": sys.version, "package": build or "no BUILD.txt"}, fh, indent=1, default=str)
    import prepare_run
    filled, _recorded = prepare_run.prepare(package_dir)       # CARDS_FILLED.md and the SKIP lines for human rows (the .bat files already ran this; it is safe to repeat)
    watcher = Watcher(results, lambda row, note: ce.snap(row, note, screenshots=False))
    timer = QTimer()
    timer.setInterval(POLL_MS)
    timer.timeout.connect(watcher.poll)
    timer.start()
    _KEEP.extend([watcher, timer])
    warning = "" if str(version).startswith(EXPECTED_QGIS) else f" WARNING: this run expects QGIS {EXPECTED_QGIS}"
    cards_mod.start_log(results, f"watcher running (rows={len(cards)}, package={build or 'no BUILD.txt'}, qgis={version}, cards={filled}){warning}")
    return watcher
