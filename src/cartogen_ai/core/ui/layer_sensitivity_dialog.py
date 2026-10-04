# -*- coding: utf-8 -*-
"""Layer data-sensitivity classification dialog.

IMPLEMENTATION_TRACKER.md §1.4 decision 3 (who classifies layers, and how),
answered 2026-09-28: manual tagging stays the model -- no automatic prompt at
layer-load time (see that entry for why an interrupt on every load was
rejected) -- but manual tagging is no longer chat-only. Before this dialog,
the only way to call `set_layer_sensitivity` was to ask the AI to do it in
chat; there was no direct QGIS UI control at all. This dialog is that
control, opened from the dock's header button (dock_widget.py), the same
"small standalone dialog" pattern settings_dialog.py/memory_dialog.py
already established.

Calls `agent/tools/sensitivity_tools.py`'s `set_layer_sensitivity` with
`confirmed=True` -- not `models/sensitivity.py`'s bare function directly --
so the existing egress-gate loosening lock (docs/
OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md) still applies uniformly: that
lock's whole point is "only a human via the UI can lower a protected layer's
tag, never the model." A human filling out this dialog and clicking Apply
*is* that UI confirmation -- the same trust boundary the chat confirm-card
flow already grants, just via a second, more direct path to it, not a way
around it.
"""

from qgis.core import QgsProject
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QMessageBox,
)

from ..agent.tools.sensitivity_tools import (
    set_layer_sensitivity as _set_layer_sensitivity,
    get_layer_sensitivity as _get_layer_sensitivity,
)
from ..models.sensitivity import SENSITIVITY_LEVELS
from ..models import egress_gate as _egress
from ..models.model_view import SCHEMA_DISCLOSURE


class LayerSensitivityDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Layer Data Sensitivity")
        self.resize(420, 340)
        self.init_ui()
        self.refresh_layers()

    def init_ui(self):
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Tag how sensitive a layer's data is. RESTRICTED/SENSITIVE layers get an export "
            "warning, and are protected from cloud AI providers whenever Settings → "
            "“Cloud data protection” is on. No automatic classification exists -- a "
            "layer is only as sensitive as what you set here."
        )
        intro.setWordWrap(True)
        intro.setObjectName("secondaryLabel")
        layout.addWidget(intro)

        disclosure = QLabel(SCHEMA_DISCLOSURE)      # #93: said where the user sets protection, not only in SECURITY.md
        disclosure.setWordWrap(True)
        disclosure.setObjectName("secondaryLabel")
        layout.addWidget(disclosure)

        layout.addWidget(QLabel("Layer:"))
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        layout.addWidget(self.layer_combo)

        self.current_level_label = QLabel("Current: (no layers loaded)")
        self.current_level_label.setObjectName("secondaryLabel")
        layout.addWidget(self.current_level_label)

        layout.addWidget(QLabel("New classification:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(SENSITIVITY_LEVELS)
        layout.addWidget(self.level_combo)

        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText(
            "Optional reason, e.g. 'contains individual beneficiary GPS coordinates'"
        )
        layout.addWidget(self.reason_edit)

        btn_row = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setObjectName("successButton")
        self.apply_btn.clicked.connect(self._apply_clicked)
        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("secondaryButton")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def refresh_layers(self):
        """Re-reads the live project's loaded layers -- called once on open (same
        "read live state when opened" convention as memory_dialog.py's refresh())."""
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        try:
            names = sorted(layer.name() for layer in QgsProject.instance().mapLayers().values())
        except Exception:
            names = []
        self.layer_combo.addItems(names)
        self.layer_combo.blockSignals(False)
        self.apply_btn.setEnabled(bool(names))
        self._on_layer_changed()

    def _on_layer_changed(self, *_args):
        name = self.layer_combo.currentText()
        if not name:
            self.current_level_label.setText("Current: (no layers loaded)")
            return
        result = _get_layer_sensitivity(name)
        level = result.get("level")
        reason = result.get("reason")
        if level:
            text = f"Current: {level}" + (f" ({reason})" if reason else "")
        else:
            text = "Current: untagged"
        self.current_level_label.setText(text)
        idx = self.level_combo.findText(level) if level else -1
        self.level_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _apply_clicked(self):
        name = self.layer_combo.currentText()
        if not name:
            return
        # Refuse rather than guess which one when the name is ambiguous --
        # set_layer_sensitivity resolves by name and silently acts on
        # mapLayersByName(name)[0], so two layers sharing a name is a real
        # way for this dialog to tag the wrong one (CodeRabbit, PR #57).
        # This is a pre-existing limitation of the by-name tool API itself
        # (shared with the model's own chat-based calls, out of scope to
        # redesign here), but this dialog can at least decline to proceed
        # instead of silently picking one.
        matches = QgsProject.instance().mapLayersByName(name)
        if len(matches) > 1:
            QMessageBox.warning(
                self, "Layer Data Sensitivity",
                f"'{name}' matches {len(matches)} layers in this project -- rename the "
                "duplicates in the Layers panel first so this can act on the right one.",
            )
            return
        level = self.level_combo.currentText()
        reason = self.reason_edit.text().strip() or None

        # Re-read the CURRENT level fresh here rather than trusting
        # current_level_label's text -- that was fetched when the combo
        # selection last changed, and could be stale by the time Apply is
        # clicked (another confirm click elsewhere, the model re-tagging it
        # mid-turn, or simply a duplicate-named layer if the project has
        # one -- CodeRabbit flagged this on PR #57, 2026-09-28). Passing
        # confirmed=True below bypasses the tool's own loosening-preview
        # step entirely, so this dialog is the ONLY place that gap would
        # otherwise go unchecked -- close it here instead of relying on a
        # label that might not reflect reality anymore.
        fresh = _get_layer_sensitivity(name)
        current_level = fresh.get("level")
        if _egress.is_loosening(current_level, level, strict=_egress.read_strict()):
            reply = QMessageBox.question(
                self, "Layer Data Sensitivity",
                f"'{name}' is currently {current_level or 'untagged'}. Change it to {level}?\n\n"
                "This layer will no longer be protected from cloud AI providers.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._on_layer_changed()
                return

        # confirmed=True: this dialog itself IS the UI confirmation the
        # egress-gate loosening lock requires -- see module docstring. The
        # question box above, checked against the freshly-read level, is
        # what actually earns that confirmation for a loosening change.
        result = _set_layer_sensitivity(name, level, reason, confirmed=True)
        if result.get("error"):
            QMessageBox.warning(self, "Layer Data Sensitivity", f"Failed: {result['error']}")
            return
        self.reason_edit.clear()
        self._on_layer_changed()
        # rc7 smoke test F15: a successful change used to give no feedback at all, so the operator
        # could not tell whether the click had applied anything.
        QMessageBox.information(
            self, "Layer Data Sensitivity", f"'{name}' is now tagged {level}.")
