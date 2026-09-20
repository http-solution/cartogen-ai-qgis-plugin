# -*- coding: utf-8 -*-
"""Layer context picker -- Broadsheet redesign Phase 3, mockup state 1l ("Context for
this question ... Cartogen sends schema and a sample of rows -- never the whole table.
Uncheck anything sensitive."). Explicit, per-question control over which loaded layers'
schema actually reaches the model, instead of every loaded layer's schema always being
sent unconditionally.

Opt-out, not opt-in (see map_context.py's filter_layers_by_selection docstring): a user
who never opens this dialog at all sees today's unchanged behavior. Opening it once and
clicking OK commits whatever was checked at that point as the new selection, which then
applies to every send until the dialog is reopened and changed again -- it is not
re-asked on every single turn, matching the mockup's own framing ("chosen before you ask
rather than guessed", not "asked every time")."""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QScrollArea, QWidget,
)

from ..agent.map_context import estimate_layer_context_tokens


class LayerContextPickerDialog(QDialog):
    def __init__(self, layers, selection, sensitivity_lookup=None, parent=None):
        """`layers`: the list get_map_context_summary()["layers"] returns.
        `selection`: the CURRENT {layer_name: bool} dict (chat_tab_widget.py's
        self._layer_context_selection) -- an entry already present here wins over the
        sensitivity-based default, so re-opening the dialog doesn't forget a choice the
        user already made.
        `sensitivity_lookup`: optional callable(layer_name) -> level-or-None, used ONLY
        to pick each checkbox's INITIAL state the first time a layer is seen (never
        called again after that -- see _checkboxes' construction below). Defaults to
        agent/tools/sensitivity_tools.get_layer_sensitivity when not given."""
        super().__init__(parent)
        self.setWindowTitle("Context for this question")
        self._layers = layers
        self._selection = dict(selection or {})
        self._sensitivity_lookup = sensitivity_lookup or self._default_sensitivity_lookup
        self._checkboxes = {}
        self.init_ui()

    @staticmethod
    def _default_sensitivity_lookup(layer_name):
        from ..agent.tools.sensitivity_tools import get_layer_sensitivity
        try:
            result = get_layer_sensitivity(layer_name)
        except Exception:
            return None
        if not isinstance(result, dict) or "error" in result:
            return None
        return result.get("level")

    def init_ui(self):
        layout = QVBoxLayout(self)

        note = QLabel(
            "Cartogen sends each checked layer's schema and a sample of rows -- never "
            "the whole table. Uncheck anything sensitive."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.token_label = QLabel("")
        layout.addWidget(self.token_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        rows_widget = QWidget()
        rows_layout = QVBoxLayout(rows_widget)
        for layer in self._layers:
            name = layer.get("name", "")
            checked = self._initial_checked_state(name)
            label = f"{name}  ({layer.get('type', '')}, {layer.get('feature_count', '?')} features)"
            box = QCheckBox(label)
            box.setChecked(checked)
            box.stateChanged.connect(self._update_token_label)
            rows_layout.addWidget(box)
            self._checkboxes[name] = box
        rows_layout.addStretch()
        scroll.setWidget(rows_widget)
        layout.addWidget(scroll, stretch=1)

        self._update_token_label()

        button_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(ok_btn)
        layout.addLayout(button_row)

    def _initial_checked_state(self, layer_name):
        """An entry already in self._selection (a choice made in a PRIOR opening of this
        dialog) always wins. Otherwise: unchecked if the layer carries a real sensitivity
        classification (set_layer_sensitivity was ever called on it), checked otherwise --
        the mockup's own stated default."""
        if layer_name in self._selection:
            return bool(self._selection[layer_name])
        level = self._sensitivity_lookup(layer_name)
        return not level

    def _update_token_label(self, *_args):
        checked_layers = [layer for layer in self._layers if self._checkboxes.get(layer.get("name")) and
                           self._checkboxes[layer.get("name")].isChecked()]
        tokens = estimate_layer_context_tokens(checked_layers)
        self.token_label.setText(f"~{tokens:,} tokens" if checked_layers else "No layers selected")

    def result_selection(self):
        """{layer_name: bool} reflecting every checkbox's final state -- the caller
        (chat_tab_widget.py) replaces its own self._layer_context_selection with this
        wholesale on accept(), so a layer unchecked here stays excluded on every future
        send until this dialog is reopened and rechecked, and a layer removed from the
        project entirely simply has no matching entry to look up next time."""
        return {name: box.isChecked() for name, box in self._checkboxes.items()}
