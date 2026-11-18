"""The in-QGIS card dock for the computer-use smoke run. The agent reads ONE card here, does the steps, writes a short note and clicks Pass / Partial / Fail / Skip. The click is what saves the
evidence (window screenshot, canvas, layer table, project state, the plugin's own per-request evidence, the CartogenAI log) and writes the result line: nothing else has to be remembered.

Start it from QGIS with START_QGIS.bat (qgis --code tools\\smoke_dock_start.py), or paste into the Python console:
    import os, sys; sys.path.insert(0, r"<package>\\tools"); import smoke_dock; smoke_dock.show(r"<package>")

Status: the card/session logic is tested offline (tests/test_smoke_cards.py) and the widget is clicked through in the QGIS CI job (tests/test_smoke_dock_live.py). NOT yet run in a real
desktop QGIS 4.2.3 session, and window screenshots through window.grab() were last seen working on 2026-10-28 (QGIS 4.2.3)."""
import json
import os
import sys

import smoke_cards as cards_mod
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QDockWidget, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget

EXPECTED_QGIS = "4.2.3"
RULES = ("One row at a time. Read the card. Do the steps in QGIS exactly as written. Do NOT type a console command, do NOT paste anything, do NOT write files. "
         "When done, write one line in the note box saying what you saw, then click Pass, Partial, Fail or Skip. If a step cannot be done, click Skip (or Fail) with the reason. "
         "QGIS may look frozen for minutes while a tool runs: wait, do not click, do not restart it.")


class SmokeDock(QDockWidget):
    def __init__(self, session, cards, extra_shot=None, qgis_version="", parent=None):
        super().__init__("Smoke test", parent)
        self.session, self.cards, self.extra_shot = session, cards, extra_shot
        body = QWidget()
        lay = QVBoxLayout(body)
        self.version = QLabel(f"QGIS {qgis_version}" + ("" if qgis_version.startswith(EXPECTED_QGIS) else f"  -  WARNING: this run expects {EXPECTED_QGIS}"))
        self.rules = QLabel(RULES)
        self.rules.setWordWrap(True)
        self.combo = QComboBox()
        for c in cards:
            self.combo.addItem(c["id"], c["id"])
        self.view = QTextBrowser()
        self.note = QLineEdit()
        self.note.setPlaceholderText("one line: what you saw")
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.start_button = QPushButton("Start this row")
        buttons = QHBoxLayout()
        self.buttons = {}
        for name in cards_mod.STATUSES:
            b = QPushButton(name.title())
            b.clicked.connect(lambda _=False, n=name: self._finish(n))
            self.buttons[name] = b
            buttons.addWidget(b)
        self.shot_name = QLineEdit()
        self.shot_name.setPlaceholderText("extra screenshot name, e.g. B1-toolcount")
        self.shot_button = QPushButton("Extra screenshot")
        for w in (self.version, self.rules, self.combo, self.view, self.start_button):
            lay.addWidget(w)
        lay.addWidget(self.note)
        lay.addLayout(buttons)
        lay.addWidget(self.shot_name)
        lay.addWidget(self.shot_button)
        lay.addWidget(self.status)
        self.setWidget(body)
        self.combo.currentIndexChanged.connect(self._show_card)
        self.start_button.clicked.connect(self._start)
        self.shot_button.clicked.connect(self._extra)
        self._show_card()

    def _card(self):
        return self.cards[self.combo.currentIndex()]

    def _show_card(self, _=None):
        self.view.setPlainText(cards_mod.card_text(self._card()))

    def _start(self):
        ok, msg = self.session.start(self._card()["id"])
        self.status.setText(msg)
        return ok

    def _finish(self, status):
        if not self.session.current and status != "SKIP":
            self.status.setText("press 'Start this row' first")
            return
        if not self.session.current:
            self.session.start(self._card()["id"])
        ok, msg = self.session.finish(status, self.note.text().strip())
        self.status.setText(msg)
        if ok:
            self.note.clear()
            if self.combo.currentIndex() + 1 < self.combo.count():
                self.combo.setCurrentIndex(self.combo.currentIndex() + 1)

    def _extra(self):
        name = self.shot_name.text().strip()
        if not name or not self.session.current:
            self.status.setText("start a row and type a name first")
            return
        try:
            self.extra_shot(f"{self.session.current}-{name}")
            self.status.setText(f"saved screenshot {self.session.current}-{name}")
        except Exception as e:
            self.status.setText(f"screenshot failed: {type(e).__name__}: {e}")


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


def show(package_dir):
    """Wires the real evidence collector and docks the card window into the running QGIS. Returns the dock."""
    from qgis.core import Qgis, QgsSettings
    from qgis.utils import iface
    package_dir = os.path.abspath(package_dir)
    tools = os.path.join(package_dir, "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import collect_evidence as ce
    results = os.path.join(package_dir, "results")
    ce.setup(results)
    QgsSettings().setValue("cartogen_ai/evidence_enabled", True)       # the plugin writes its own per-request evidence folder: arguments, results and tools actually called
    with open(os.path.join(package_dir, "cards.json"), encoding="utf-8") as fh:
        cards = json.load(fh)
    version = Qgis.version()
    with open(os.path.join(results, "ENVIRONMENT.json"), "w", encoding="utf-8") as fh:
        json.dump({"qgis": version, "expected": EXPECTED_QGIS, "plugin": ce._plugin_version(), "python": sys.version}, fh, indent=1, default=str)
    interrupted = cards_mod.recover_interrupted(results)

    def snapshot(row, note):
        _capture(os.path.join(results, "screens", f"{row}.png"))       # first and from outside QGIS: it is the picture of what the agent just saw
        ce.snap(row, note, screenshots=False)                          # the rest reads only data (layers, properties, project, log, the plugin's own evidence)

    session = cards_mod.Session(results, cards, snapshot)
    dock = SmokeDock(session, cards, extra_shot=lambda name: _capture(os.path.join(results, "screens", f"{name}.png")) or ce.shot(name), qgis_version=version, parent=iface.mainWindow())
    if interrupted:
        dock.status.setText(f"Row {interrupted} was open when QGIS last closed; it was recorded as FAIL 'interrupted'. Carry on with the next row.")
    iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    return dock
