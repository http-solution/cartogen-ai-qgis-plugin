"""The dialog for opening a workflow file someone else made (PLAN-048 stage 3). It shows everything first and runs nothing: the person reads every
step, maps each role to one of their own layers, optionally starts part-way, and presses Run; the caller then hands the steps to the chat, which runs
them through the usual gates.

The decisions (what a role needs, what a start step means, what a mismatch is) are in core/agent/workflow_import.py, pure and tested; this module
only draws them. MAIN THREAD. Real-QGIS construction is covered by tests/test_workflow_import_live.py (CI only); how it looks and reads to a person
has not been seen."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QLabel, QPlainTextEdit,
                                 QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..agent import workflow_import

CHOOSE = "(choose a layer)"
WARNING = ("This workflow was written by someone else. Read every step below before you run it. Nothing runs until you press Run, and "
           "each step then goes through the same checks and confirmations as a request you type yourself.")


class WorkflowImportDialog(QDialog):
    """`document` is a validated workflow (or None with `problems` to show). `layers` is [(name, info)] from the open project; `operation_of(tool)`
    gives READ/CREATE/MODIFY/PUBLISH."""

    def __init__(self, parent, file_name, document, problems, warnings, layers, operation_of):
        super().__init__(parent)
        self.setWindowTitle("Open a workflow file")
        self.resize(780, 640)
        self._document = document
        self._layers = dict(layers)
        self._operation_of = operation_of
        self._combos = {}
        root = QVBoxLayout(self)
        if document is None:
            self._build_refusal(root, file_name, problems)
            return
        warn = QLabel(WARNING)
        warn.setWordWrap(True)
        root.addWidget(warn)
        title = QLabel(f"<b>{self._esc(document['name'])}</b>")
        root.addWidget(title)
        meta = [f"File: {self._esc(file_name)}", f"Checksum (SHA-256): {document['fingerprint']}"]
        if document.get("author"):
            meta.append(f"Author (as written in the file): {self._esc(document['author'])}")
        if document.get("description"):
            meta.append(self._esc(document["description"]))
        info = QLabel("<br>".join(meta))
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)      # so the checksum can be copied and compared
        root.addWidget(info)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["#", "Tool", "Kind of change", "Arguments", "Note"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setWordWrap(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self._table, 1)
        form = QFormLayout()
        for role, spec in document.get("roles", {}).items():
            combo = QComboBox()
            combo.addItem(CHOOSE, "")
            for name, layer_info in self._layers.items():
                if not spec.get("kind") or not layer_info.get("kind") or layer_info["kind"] == spec["kind"]:
                    combo.addItem(name, name)
            combo.currentIndexChanged.connect(self._refresh)
            self._combos[role] = combo
            hint = ", ".join(x for x in (spec.get("kind"), spec.get("geometry")) if x)
            form.addRow(QLabel(f"<b>{self._esc(role)}</b> ({hint})<br>{self._esc(spec.get('about', ''))}"), combo)
        self._start = QSpinBox()
        self._start.setRange(1, max(1, len(document["steps"])))
        self._start.valueChanged.connect(self._refresh)
        form.addRow(QLabel("Start at step (1 runs the whole file)"), self._start)
        root.addLayout(form)
        self._messages = QLabel("")
        self._messages.setWordWrap(True)
        root.addWidget(self._messages)
        notes = []
        if document.get("limitations"):
            notes.append("Limitations the author wrote:\n- " + "\n- ".join(document["limitations"]))
        if document.get("data_sources"):
            notes.append("Data it expects (the licences are the author's note, not checked):\n- " + "\n- ".join(
                " | ".join(v for v in (s.get("name"), s.get("url"), s.get("licence")) if v) for s in document["data_sources"]))
        if warnings:
            notes.append("About the file:\n- " + "\n- ".join(warnings))
        if notes:
            box = QPlainTextEdit("\n\n".join(notes))
            box.setReadOnly(True)
            box.setMaximumHeight(110)
            root.addWidget(box)
        buttons = QDialogButtonBox()
        self._run = QPushButton("Run")
        self._run.setEnabled(False)
        buttons.addButton(self._run, QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        cancel.clicked.connect(self.reject)
        root.addWidget(buttons)
        self._refresh()

    @staticmethod
    def _esc(text):
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _build_refusal(self, root, file_name, problems):
        head = QLabel(f"<b>This file cannot be opened.</b><br>{self._esc(file_name)}")
        head.setWordWrap(True)
        root.addWidget(head)
        box = QPlainTextEdit("\n".join(f"- {p}" for p in problems))
        box.setReadOnly(True)
        root.addWidget(box, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def mapping(self):
        """{role: chosen layer name} for the roles the person has chosen."""
        return {role: combo.currentData() for role, combo in self._combos.items() if combo.currentData()}

    def start_at(self):
        return self._start.value()

    def _refresh(self, *_args):
        document, mapping = self._document, self.mapping()
        rows = workflow_import.step_rows(document, mapping, self._operation_of)
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, text in enumerate((str(row["n"]), row["tool"], row["operation"], row["arguments"], row["note"])):
                self._table.setItem(r, c, QTableWidgetItem(text))
        self._table.resizeRowsToContents()
        _steps, problems = workflow_import.apply_mapping(document, mapping, self._start.value(), available=set(self._layers))
        fit_problems, warnings = workflow_import.compatibility(document, mapping, self._layers.get)
        problems = list(dict.fromkeys(problems + fit_problems))
        lines = [f"Problem: {p}" for p in problems] + [f"Check: {w}" for w in warnings]
        self._messages.setText("\n".join(lines))
        self._run.setEnabled(not problems)
