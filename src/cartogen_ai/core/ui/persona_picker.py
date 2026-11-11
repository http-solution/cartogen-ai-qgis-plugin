"""The persona picker (PLAN-023 R1-3): two dropdowns (primary and an optional secondary persona) and, under them, the readiness panel that says what the plugin can and cannot do for them.

Shared by the Settings window and the onboarding dialog so both show the same thing. All text comes from core/personas (panel.py is pure and tested offline); this file is only the widgets. It imports
Qt, so it runs only inside QGIS: tests/test_persona_picker_live.py is its test in the CI live job, and hand row R1-H1 is the check by a person. No tool is hidden by any choice (the panel says so)."""
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from ..personas import ids as persona_ids
from ..personas import get as persona_get
from ..personas.panel import panel_text
from ..personas.selection import DEFAULT_PERSONA


class PersonaPicker(QWidget):
    def __init__(self, parent=None, primary=DEFAULT_PERSONA, secondary=""):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.primary_combo = QComboBox()
        self.secondary_combo = QComboBox()
        self.secondary_combo.addItem(self.tr("None"), "")
        for pid in persona_ids():
            label = persona_get(pid)["label"]
            self.primary_combo.addItem(label, pid)
            self.secondary_combo.addItem(label, pid)
        form.addRow(self.tr("Primary persona:"), self.primary_combo)
        form.addRow(self.tr("Secondary persona (optional):"), self.secondary_combo)
        layout.addLayout(form)
        hint = QLabel(self.tr("The panel below says what the assistant can do for the personas you pick. Every tool stays available whichever you choose."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.readiness_panel = QPlainTextEdit()
        self.readiness_panel.setReadOnly(True)
        self.readiness_panel.setMinimumHeight(150)
        self.readiness_panel.setMaximumHeight(240)
        layout.addWidget(self.readiness_panel)
        self.set_selection(primary, secondary)
        self.primary_combo.currentIndexChanged.connect(self._on_primary_changed)
        self.secondary_combo.currentIndexChanged.connect(self._refresh)

    def set_selection(self, primary, secondary=""):
        """Choose the personas (unknown ids fall back to the generalist / none) and refresh the panel."""
        for combo, value, fallback in ((self.primary_combo, primary, DEFAULT_PERSONA), (self.secondary_combo, secondary, "")):
            combo.blockSignals(True)
            index = combo.findData(value)
            combo.setCurrentIndex(index if index >= 0 else combo.findData(fallback))
            combo.blockSignals(False)
        self._refresh()

    def selection(self):
        """(primary id, secondary id or '')."""
        return self.primary_combo.currentData(), self.secondary_combo.currentData() or ""

    def _on_primary_changed(self, _index):
        # the same persona as primary and secondary means nothing: drop the secondary when the primary becomes it
        if self.secondary_combo.currentData() == self.primary_combo.currentData():
            self.secondary_combo.blockSignals(True)
            self.secondary_combo.setCurrentIndex(0)
            self.secondary_combo.blockSignals(False)
        self._refresh()

    def _refresh(self, _index=None):
        primary, secondary = self.selection()
        if secondary == primary:
            secondary = ""
        self.readiness_panel.setPlainText(panel_text(primary, secondary))
