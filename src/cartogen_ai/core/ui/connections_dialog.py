"""The Connections window (PLAN-041): where the user configures and chooses the model connection -- hosted API keys, the local Ollama
server, and a CLI the user is already signed in to -- and where the NASA FIRMS data key lives.

Layout: a list of every connection on the left (grouped by where the prompts go, each with a status mark and a "in use" tag) and the
selected connection's own page on the right (key or program path, model, Test / Check connection, Sign in, and a "Use this connection"
button). Choosing which page to look at and choosing which connection is in use are two separate actions, so reading a page never
changes what the assistant uses. Same plain vertical layouts as before (a wrapping custom layout froze QGIS once; see docs/BUG_TRACKER.md).

Everything here was section 01 and 02 of the Settings window until PLAN-041; the behaviour, the settings keys and the credential
storage are unchanged. CI-only until the owner has looked at it in QGIS."""
import contextlib
import json
import threading

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QMessageBox, QApplication, QLineEdit, QComboBox, QFormLayout, QDialogButtonBox, QStackedWidget,
    QWidget, QCheckBox, QHBoxLayout, QPushButton, QScrollArea, QFrame, QButtonGroup,
)
from qgis.core import QgsSettings

from ...infrastructure.providers import cli_bridge_status as _cli_status
from ...infrastructure.providers import provider_check as _provider_check
from ...infrastructure.settings_keys import (
    SETTINGS_PROVIDER as PROVIDER_KEY,
    DEFAULT_PROVIDER,
    normalize_provider,
    cli_path_setting_key,
    cli_providers_enabled,
    SETTINGS_EXPERIMENTAL_CLI as EXPERIMENTAL_CLI_KEY,
    provider_model_list_key,
)
from ..model_selector import AUTO_SENTINEL
from .chat_formatting import build_dock_stylesheet, BRAND_TEAL
from .connections_catalog import AUTO_LABEL, PROVIDERS, _CLI_PROVIDERS, _GROUP_TITLES, _group_of
from .theme_palette import extract_theme_palette

FIRMS_KEY = "firms"  # the NASA FIRMS data key's name in the credential store (not an LLM provider)


class CartogenAiConnectionsDialog(QDialog):
    # Fetching a model list hits the network -- must never block the UI thread (a slow or unreachable endpoint would otherwise freeze the
    # window, and QGIS with it, for the full request timeout). The background thread emits one of these signals; Qt queues delivery to
    # the slot on the main thread because this dialog lives there -- the same cross-thread pattern as dock_widget.py.
    modelsFetchedSignal = pyqtSignal(str, dict)
    cli_check_signal = pyqtSignal(str, dict)  # the CLI connection check runs a subprocess and a model call
    api_check_signal = pyqtSignal(str, dict)  # the Test button of the key-based providers

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cartogen AI \u2014 Connections")
        self.setMinimumWidth(640)
        self.settings = QgsSettings()
        # The CLI entries are always listed, under their own heading; their rows stay disabled until the user ticks the acknowledgement
        # box under that heading, and normalize_provider() ignores a saved CLI provider while it is unticked.
        self._providers = PROVIDERS + _CLI_PROVIDERS
        self._cli_status_labels = {}
        self._cli_buttons = {}
        self._cli_checking = set()
        self._api_status_labels = {}
        self._api_test_buttons = {}
        self._api_testing = set()
        self._key_edits = {}
        self._model_combos = {}
        self._cached_model_lists = {}
        self._fetching = set()
        self._provider_buttons = {}   # the list on the left: one checkable row per connection (the row that is checked is shown)
        self._use_buttons = {}        # "Use this connection" on each page
        self._in_use_labels = {}      # "In use" tag on each page
        self._page_index = {}
        # A provider only enters this set after a real _on_models_fetched success in THIS window session: a saved key that has not been
        # exercised this session is "set", not "verified" -- the window cannot know a key still works without calling the provider, so
        # the list shows two different marks rather than claiming more than it knows.
        self._verified_providers = set()
        self.modelsFetchedSignal.connect(self._on_models_fetched)
        self.cli_check_signal.connect(self._on_cli_check)
        self.api_check_signal.connect(self._on_api_check)
        self.init_ui()

    # ------------------------------------------------------------------ layout

    def init_ui(self):
        from ...infrastructure.auth import CredentialManager

        # The whole window except the button row sits in scroll areas, and OK/Cancel stay fixed outside them: a window taller than a
        # short screen once left OK/Cancel off-screen so a typed key could never be saved (live report 2026-09-15, see the Settings window).
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        screen = QApplication.primaryScreen()
        if screen is not None:
            self.setMaximumHeight(max(300, int(screen.availableGeometry().height() * 0.85)))

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(12, 12, 12, 6)
        top_layout.setSpacing(4)
        intro = QLabel(
            "Pick a connection on the left to set it up, then press \u201cUse this connection\u201d to make it the one the assistant "
            "uses. Chat text and any layer or attribute data a tool surfaces go to the connection in use (Ollama excepted: fully local, "
            "nothing leaves this machine; a CLI login sends it to that CLI's vendor). A provider's Data Processing Addendum link is a "
            "starting point, not a substitute for your organization's own GDPR review. See docs/USER_GUIDE.md and SECURITY.md.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: gray; font-size: 11px;")
        top_layout.addWidget(intro)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        top_layout.addWidget(self.summary_label)
        account_row = QHBoxLayout()
        account_row.addWidget(QLabel("Hosted Cartogen AI account"))
        account_row.addStretch(1)
        self.account_button = QPushButton("Manage account")
        self.account_button.clicked.connect(self._open_account_dialog)
        account_row.addWidget(self.account_button)
        top_layout.addLayout(account_row)
        outer_layout.addWidget(top)

        body = QHBoxLayout()
        body.setContentsMargins(12, 0, 12, 0)
        body.setSpacing(12)

        # ---- left: every connection, grouped by where the prompts go
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setMinimumWidth(250)
        side_scroll.setMaximumWidth(250)
        side = QWidget()
        side_col = QVBoxLayout(side)
        side_col.setContentsMargins(0, 0, 4, 0)
        side_col.setSpacing(4)
        side_scroll.setWidget(side)
        self._row_group = QButtonGroup(self)
        self._row_group.setExclusive(True)
        self._active_provider = normalize_provider(self.settings.value(PROVIDER_KEY, "openrouter"))
        last_group = None
        for entry in self._providers:
            pv = entry["value"]
            group = _group_of(entry)
            if group != last_group:
                group_label = QLabel(_GROUP_TITLES[group])
                group_label.setWordWrap(True)
                group_label.setStyleSheet("color: gray; font-size: 11px; font-weight: 600; margin-top: 6px;")
                side_col.addWidget(group_label)
                if group == "cli":
                    self.experimental_cli_checkbox = QCheckBox("I understand: use a CLI I am already signed in to as the model")
                    self.experimental_cli_checkbox.setChecked(cli_providers_enabled())
                    self.experimental_cli_checkbox.setToolTip(
                        "Experimental and not yet verified against a real signed-in CLI. Cartogen AI runs the program on this computer "
                        "with your own account; it never sees or stores your login. The conversation, including any layer or "
                        "attribute data a tool surfaces, goes to that vendor's service. Off by default.")
                    self.experimental_cli_checkbox.toggled.connect(self._on_cli_ack_toggled)
                    side_col.addWidget(self.experimental_cli_checkbox)
                last_group = group
            row = QPushButton()
            row.setObjectName("connectionRow")
            row.setCheckable(True)
            row.setChecked(pv == self._active_provider)
            if group == "cli":
                row.setEnabled(self.experimental_cli_checkbox.isChecked())
            row.clicked.connect(lambda _checked=False, p=pv: self._show_provider(p))
            self._row_group.addButton(row)
            self._provider_buttons[pv] = row
            side_col.addWidget(row)
        data_label = QLabel("Data services -- a key for a data source, not a model")
        data_label.setWordWrap(True)
        data_label.setStyleSheet("color: gray; font-size: 11px; font-weight: 600; margin-top: 6px;")
        side_col.addWidget(data_label)
        self.firms_row = QPushButton()
        self.firms_row.setObjectName("connectionRow")
        self.firms_row.setCheckable(True)
        self.firms_row.clicked.connect(lambda _checked=False: self._show_provider(FIRMS_KEY))
        self._row_group.addButton(self.firms_row)
        self._provider_buttons[FIRMS_KEY] = self.firms_row
        side_col.addWidget(self.firms_row)
        side_col.addStretch(1)
        body.addWidget(side_scroll)

        # ---- right: one page per connection
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.provider_stack = QStackedWidget()
        page_scroll.setWidget(self.provider_stack)
        body.addWidget(page_scroll, 1)
        for entry in self._providers:
            self._page_index[entry["value"]] = self.provider_stack.addWidget(self._build_page(entry, CredentialManager))
        self._page_index[FIRMS_KEY] = self.provider_stack.addWidget(self._build_firms_page(CredentialManager))

        body_holder = QWidget()
        body_holder.setLayout(body)
        outer_layout.addWidget(body_holder, 1)

        self.fetch_status_label = QLabel("Model lists refresh automatically when you leave an API key field.")
        self.fetch_status_label.setObjectName("secondaryLabel")
        self.fetch_status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.fetch_status_label.setWordWrap(True)
        self.fetch_status_label.setContentsMargins(12, 6, 12, 0)
        outer_layout.addWidget(self.fetch_status_label)

        # OK/Cancel are added to outer_layout, NOT to a scroll area, so they stay reachable at any window height.
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.setContentsMargins(12, 8, 12, 12)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setObjectName("settingsOkButton")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setObjectName("settingsCancelButton")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        outer_layout.addWidget(self.button_box)

        # Same narrowly scoped styling as the Settings window: brand teal for OK and for the row being looked at; scoped to object names
        # unique to these windows so it cannot touch the chat dock's own buttons.
        self.setStyleSheet(build_dock_stylesheet(extract_theme_palette()) + f"""
QPushButton#connectionRow {{
    text-align: left;
    padding: 6px 10px;
}}
QPushButton#connectionRow:checked {{
    background-color: #ffffff;
    color: {BRAND_TEAL};
    border: 1.5px solid {BRAND_TEAL};
}}
QPushButton#settingsOkButton, QPushButton#settingsCancelButton {{
    padding: 5px 16px;
    font-size: 12px;
    border-radius: 4px;
}}
QPushButton#settingsOkButton {{
    background-color: {BRAND_TEAL};
    color: #ffffff;
}}
QPushButton#settingsCancelButton {{
    background-color: transparent;
    color: {BRAND_TEAL};
    border: 1px solid {BRAND_TEAL};
}}
""")
        self._show_provider(self._active_provider if self._active_provider in self._page_index else DEFAULT_PROVIDER)
        self._refresh_rows()

    def _build_page(self, entry, credentials):
        """One connection's page: header and 'Use this connection', then its key or program path, model, test buttons and help links."""
        pv = entry["value"]
        group = _group_of(entry)
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(4, 0, 0, 0)
        title = QLabel(entry["provider_label"])
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        col.addWidget(title)
        where = QLabel(_GROUP_TITLES[group])
        where.setWordWrap(True)
        where.setStyleSheet("color: gray; font-size: 11px;")
        col.addWidget(where)
        use_row = QHBoxLayout()
        use_btn = QPushButton("Use this connection")
        use_btn.setToolTip("Makes this the connection the assistant uses. Nothing changes until you press OK.")
        if group == "cli":
            use_btn.setEnabled(self.experimental_cli_checkbox.isChecked())
        use_btn.clicked.connect(lambda _checked=False, p=pv: self._use_provider(p))
        in_use = QLabel("\u2713 In use")
        in_use.setStyleSheet("font-size: 11px; font-weight: 700; color: #1c7a4d;")
        use_row.addWidget(use_btn)
        use_row.addWidget(in_use)
        use_row.addStretch(1)
        self._use_buttons[pv] = use_btn
        self._in_use_labels[pv] = in_use
        col.addLayout(use_row)

        page_form = QFormLayout()
        page_form.setContentsMargins(0, 6, 0, 2)
        key_edit = QLineEdit()
        is_setting = entry.get("key_storage") == "setting"
        if pv != "ollama" and not is_setting:
            key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        saved_key = self.settings.value(cli_path_setting_key(pv), "") if is_setting else credentials.get_credential(pv)
        key_edit.setText(saved_key if saved_key else entry["key_default"])
        key_edit.editingFinished.connect(lambda p=pv: self._fetch_models(p))
        # Live feedback for the list on the left (the Set / Verified mark), not gated on blur like the model fetch above, so it reflects
        # what is typed even before the user tabs away or saves.
        key_edit.textChanged.connect(lambda _text="": self._refresh_rows())
        # A user who has never used an LLM API has no way to know what belongs in this field or where to get it (UX audit 2026-08-31).
        key_placeholder = entry.get("key_placeholder", "")
        if key_placeholder:
            key_edit.setPlaceholderText(key_placeholder)
        key_tooltip = entry.get("key_tooltip", "")
        if key_tooltip:
            key_edit.setToolTip(key_tooltip)
        page_form.addRow(entry["key_label"], key_edit)
        self._key_edits[pv] = key_edit

        page_note = entry.get("page_note")
        if page_note:
            note_label = QLabel(page_note)
            note_label.setWordWrap(True)
            note_label.setStyleSheet("color: gray; font-size: 11px;")
            page_form.addRow("", note_label)

        if is_setting:
            status_label = QLabel(self._cli_quick_status(pv, key_edit.text()))
            status_label.setWordWrap(True)
            status_label.setStyleSheet("font-size: 11px;")
            self._cli_status_labels[pv] = status_label
            page_form.addRow("", status_label)
            button_row = QHBoxLayout()
            check_btn = QPushButton("Check connection")
            check_btn.setToolTip("Finds the program, then asks the model one tiny question through your own login "
                                 "(a few tokens of your plan).")
            check_btn.clicked.connect(lambda _checked=False, p=pv: self._check_cli(p))
            signin_btn = QPushButton("Sign in...")
            signin_btn.setToolTip("Opens a terminal running the program's own sign-in. Your login stays with that program.")
            signin_btn.clicked.connect(lambda _checked=False, p=pv: self._signin_cli(p))
            button_row.addWidget(check_btn)
            button_row.addWidget(signin_btn)
            button_row.addStretch(1)
            self._cli_buttons[pv] = (check_btn, signin_btn)
            button_holder = QWidget()
            button_holder.setLayout(button_row)
            page_form.addRow("", button_holder)
            key_edit.textChanged.connect(lambda text, p=pv: self._cli_status_labels[p].setText(self._cli_quick_status(p, text)))

        if not is_setting and pv in _provider_check.TESTABLE:
            test_btn = QPushButton("Test")
            test_btn.setToolTip("Uses what is typed above (it does not have to be saved yet): lists the provider's models, then "
                                "asks the chosen model one tiny question (a few tokens of your own key).")
            test_btn.clicked.connect(lambda _checked=False, p=pv: self._test_api(p))
            self._api_test_buttons[pv] = test_btn
            test_row = QHBoxLayout()
            test_row.addWidget(test_btn)
            test_row.addStretch(1)
            test_holder = QWidget()
            test_holder.setLayout(test_row)
            page_form.addRow("", test_holder)
            api_status = QLabel("")
            api_status.setWordWrap(True)
            api_status.setStyleSheet("font-size: 11px;")
            self._api_status_labels[pv] = api_status
            page_form.addRow("", api_status)

        key_help_url = entry.get("key_help_url")
        if key_help_url:
            help_label = QLabel(f'<a href="{key_help_url}">Get a key \u2192</a>')
            help_label.setOpenExternalLinks(True)
            help_label.setStyleSheet("color: gray; font-size: 11px;")
            page_form.addRow("", help_label)

        # GDPR review (docs/GDPR_COMPLIANCE_REVIEW.docx) finding F4: the deploying organisation needs its own Data Processing Agreement
        # with whichever cloud provider it enables; pointing at it here saves the organisation discovering the need unprompted.
        dpa_url = entry.get("dpa_url")
        if dpa_url:
            dpa_label_text = entry.get("dpa_label", "Data Processing Agreement")
            dpa_label = QLabel(f'<a href="{dpa_url}">{dpa_label_text} \u2192</a>')
            dpa_label.setOpenExternalLinks(True)
            dpa_label.setStyleSheet("color: gray; font-size: 11px;")
            dpa_label.setWordWrap(True)
            page_form.addRow("", dpa_label)

        model_combo = QComboBox()
        model_combo.setEditable(True)
        saved_model = self.settings.value(entry["model_setting_key"], entry["default_model"])
        model_combo.addItem(AUTO_LABEL)
        seeded = []
        if entry["default_model"] and entry["default_model"] != AUTO_SENTINEL:
            seeded.append(entry["default_model"])
        elif entry.get("safe_starting_model"):
            seeded.append(entry["safe_starting_model"])
        for m in entry.get("extra_seed_models", []):
            if m not in seeded:
                seeded.append(m)
        if saved_model and saved_model != AUTO_SENTINEL and saved_model not in seeded:
            seeded.append(saved_model)
        for seed_model in seeded:
            model_combo.addItem(seed_model)
        model_combo.setCurrentText(AUTO_LABEL if saved_model == AUTO_SENTINEL else saved_model)
        page_form.addRow(entry["model_label"], model_combo)
        self._model_combos[pv] = model_combo

        cached_raw = self.settings.value(provider_model_list_key(pv), "")
        if cached_raw:
            with contextlib.suppress(TypeError, ValueError):
                self._cached_model_lists[pv] = json.loads(cached_raw)
        col.addLayout(page_form)
        col.addStretch(1)
        return page

    def _build_firms_page(self, credentials):
        """NASA FIRMS active-fire monitoring (hazard_monitoring_tools.py) needs its own free key, separate from any model connection, so it
        gets its own page rather than being a choice. Stored through the same CredentialManager as the provider keys."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(4, 0, 0, 0)
        title = QLabel("NASA FIRMS (active fires)")
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        col.addWidget(title)
        note = QLabel("A data key, not a model: it powers fetch_nasa_active_fires. Leave it blank if you do not need live fire "
                      "monitoring; every other tool works without it.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        col.addWidget(note)
        form = QFormLayout()
        self.firms_key_edit = QLineEdit()
        self.firms_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.firms_key_edit.setText(credentials.get_credential(FIRMS_KEY))
        self.firms_key_edit.setPlaceholderText("Optional -- only needed for live active-fire monitoring")
        self.firms_key_edit.setToolTip("Powers fetch_nasa_active_fires (NASA FIRMS active fire/thermal-anomaly detections).")
        self.firms_key_edit.textChanged.connect(lambda _text="": self._refresh_rows())
        form.addRow("NASA FIRMS API Key:", self.firms_key_edit)
        col.addLayout(form)
        help_label = QLabel('<a href="https://firms.modaps.eosdis.nasa.gov/api/area/">Get a free key \u2192</a>')
        help_label.setOpenExternalLinks(True)
        help_label.setStyleSheet("color: gray; font-size: 11px;")
        col.addWidget(help_label)
        col.addStretch(1)
        return page

    # ----------------------------------------------------------- list and choice

    def _show_provider(self, provider_value):
        """Shows a connection's page. Looking at a page does not change which connection is in use."""
        index = self._page_index.get(provider_value)
        if index is not None:
            self.provider_stack.setCurrentIndex(index)
        self._shown_provider = provider_value
        button = self._provider_buttons.get(provider_value)
        if button is not None and not button.isChecked():
            button.setChecked(True)

    def _use_provider(self, provider_value):
        """Makes a connection the one in use (saved when OK is pressed)."""
        self._active_provider = provider_value
        self._refresh_rows()

    def _row_mark(self, provider_value):
        """'verified' / 'set' / 'unset' for the mark in the list; Ollama and the CLIs have no key, so 'set' means a program or URL is there."""
        if provider_value == FIRMS_KEY:
            return "set" if self.firms_key_edit.text().strip() else "unset"
        edit = self._key_edits.get(provider_value)
        if edit is None or not edit.text().strip():
            return "unset"
        entry = next((e for e in self._providers if e["value"] == provider_value), None)
        if entry is not None and entry.get("key_storage") == "setting" and not _cli_status.locate(provider_value, edit.text()):
            return "unset"
        return "verified" if provider_value in self._verified_providers else "set"

    def _refresh_rows(self):
        """Redraws the list marks, the 'In use' tags and the summary line from the current field text. Cheap (no network), so it runs on
        every keystroke."""
        if not hasattr(self, "summary_label") or not hasattr(self, "firms_key_edit"):
            return  # called via textChanged before init_ui has built everything
        marks = {"verified": "\u2713", "set": "\u25cf", "unset": "\u25cb"}
        for entry in self._providers:
            pv = entry["value"]
            tag = "   (in use)" if pv == self._active_provider else ""
            self._provider_buttons[pv].setText(f"{marks[self._row_mark(pv)]}  {entry['pill_label']}{tag}")
            self._in_use_labels[pv].setVisible(pv == self._active_provider)
            self._use_buttons[pv].setVisible(pv != self._active_provider)
        self.firms_row.setText(f"{marks[self._row_mark(FIRMS_KEY)]}  NASA FIRMS")
        entry = next((e for e in self._providers if e["value"] == self._active_provider), None)
        if entry is not None:
            model_text = self._model_combos[self._active_provider].currentText().strip() or AUTO_LABEL
            self.summary_label.setText(f"In use: {entry['provider_label']} \u00b7 {model_text} model")

    def _on_cli_ack_toggled(self, checked):
        """Ticking the acknowledgement enables the CLI rows and their 'Use this connection' buttons; unticking disables them and, if one
        was the connection in use, moves the choice back to the default provider so Save cannot store a provider this window is no
        longer offering."""
        for entry in self._providers:
            if _group_of(entry) == "cli":
                self._provider_buttons[entry["value"]].setEnabled(checked)
                self._use_buttons[entry["value"]].setEnabled(checked)
        if not checked and self._active_provider in _cli_status.DEFAULT_PROGRAM:
            self._use_provider(DEFAULT_PROVIDER)
            self._provider_buttons[DEFAULT_PROVIDER].setChecked(True)
            self._show_provider(DEFAULT_PROVIDER)
        self._refresh_rows()

    @staticmethod
    def _cli_quick_status(provider, program_text):
        """A one-line status that needs no subprocess: is the program on this computer? (Signed in or not only the check button knows.)"""
        path = _cli_status.locate(provider, program_text)
        if path:
            return f"Program found: {path}. Press Check connection to confirm you are signed in."
        return _cli_status.not_found_message(provider, program_text)

    def _cli_form_values(self, provider):
        program = self._key_edits[provider].text().strip()
        model = self._resolve_model_value(provider)
        return program, (None if model == AUTO_SENTINEL else model)

    def _check_cli(self, provider):
        if provider in self._cli_checking:
            return
        program, model = self._cli_form_values(provider)
        self._cli_checking.add(provider)
        for btn in self._cli_buttons[provider]:
            btn.setEnabled(False)
        self._cli_status_labels[provider].setText("Checking... (this asks the model one short question and can take a minute)")

        def worker():
            try:
                result = _cli_status.check_connection(provider, program, model)
            except Exception as e:
                result = {"ok": False, "stage": "other", "message": f"Unexpected error: {type(e).__name__}", "seconds": 0.0}
            with contextlib.suppress(RuntimeError):
                self.cli_check_signal.emit(provider, result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_cli_check(self, provider, result):
        self._cli_checking.discard(provider)
        for btn in self._cli_buttons[provider]:
            btn.setEnabled(True)
        label = self._cli_status_labels[provider]
        if result.get("ok"):
            version = f" ({result['version']})" if result.get("version") else ""
            label.setText(f"Ready{version}. Signed in. {result.get('message', '')}")
            return
        hint = {"install": " Fix the program name or path above.", "signin": " Press Sign in..., finish there, then check again."}
        label.setText(f"Not ready: {result.get('message', 'unknown error')}{hint.get(result.get('stage'), '')}")

    def _test_api(self, provider):
        """The Test button of a key-based provider: runs provider_check.check_provider on a background thread with the values typed in the
        form. Nothing is saved by testing."""
        if provider in self._api_testing:
            return
        key_text = self._key_edits[provider].text().strip()
        model = self._resolve_model_value(provider)
        model = None if model == AUTO_SENTINEL else model
        self._api_testing.add(provider)
        self._api_test_buttons[provider].setEnabled(False)
        self._api_status_labels[provider].setText("Testing... (lists the models, then asks one short question; can take a minute)")

        def worker():
            try:
                result = _provider_check.check_provider(provider, key_text, model)
            except Exception as e:
                result = {"ok": False, "stage": "other", "message": f"Unexpected error: {type(e).__name__}", "models": []}
            with contextlib.suppress(RuntimeError):
                self.api_check_signal.emit(provider, result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_api_check(self, provider, result):
        self._api_testing.discard(provider)
        self._api_test_buttons[provider].setEnabled(True)
        label = self._api_status_labels[provider]
        if result.get("ok"):
            label.setText(result.get("message", "Works."))
            if result.get("models"):
                self._on_models_fetched(provider, {"success": True, "models": result["models"]})  # fills the model box, marks it verified
            else:
                self._verified_providers.add(provider)
                self._refresh_rows()
            return
        hint = _provider_check.HINTS.get(result.get("stage"), "")
        label.setText(f"Not working: {result.get('message', 'unknown error')}" + (f" {hint}" if hint else ""))

    def _signin_cli(self, provider):
        program = self._key_edits[provider].text().strip()
        outcome = _cli_status.open_signin_terminal(provider, program)
        self._cli_status_labels[provider].setText(outcome["message"])

    def _open_account_dialog(self):
        from .account_dialog import CartogenAccountDialog
        dialog = CartogenAccountDialog(self)
        dialog.exec()

    def _fetch_models(self, provider_value):
        entry = next(e for e in self._providers if e["value"] == provider_value)
        key_text = self._key_edits[provider_value].text().strip()
        if not key_text or provider_value in self._fetching or entry.get("key_storage") == "setting":
            return  # a CLI provider has no model list to fetch: its "key" is just a program path

        self._fetching.add(provider_value)
        self.fetch_status_label.setText(f"Fetching {entry['provider_label']} models...")

        def worker():
            try:
                result = entry["list_fn"](key_text)
            except Exception as e:
                result = {"error": f"Unexpected error: {e}"}
            # dialog was closed/deleted before the fetch finished -- nothing to update
            with contextlib.suppress(RuntimeError):
                self.modelsFetchedSignal.emit(provider_value, result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_models_fetched(self, provider_value, result):
        self._fetching.discard(provider_value)
        entry = next(e for e in self._providers if e["value"] == provider_value)
        combo = self._model_combos[provider_value]

        if result.get("success"):
            models = result.get("models", [])
            self._cached_model_lists[provider_value] = models
            previous = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(AUTO_LABEL)
            for model_id in models:
                combo.addItem(model_id)
            restore_idx = combo.findText(previous)
            combo.setCurrentIndex(restore_idx if restore_idx >= 0 else 0)
            combo.blockSignals(False)
            self.fetch_status_label.setText(
                f"Loaded {len(models)} {entry['provider_label']} model(s)."
            )
            # A successful model fetch is the one thing this dialog actually knows for sure
            # about a key -- the provider accepted it and returned real data. That's what
            # "Verified" in the Keys summary means; see _verified_providers's comment in
            # __init__ for why nothing else in this dialog is allowed to claim that word.
            self._verified_providers.add(provider_value)
            self._refresh_rows()
        else:
            self.fetch_status_label.setText(
                f"{entry['provider_label']} fetch failed: {result.get('error', 'unknown error')}"
            )

    def _resolve_model_value(self, provider_value):
        text = self._model_combos[provider_value].currentText().strip()
        if not text or text == AUTO_LABEL:
            return AUTO_SENTINEL
        return text


    def accept(self):
        from ...infrastructure.auth import CredentialManager
        self.settings.setValue(PROVIDER_KEY, self._active_provider)
        self.settings.setValue(EXPERIMENTAL_CLI_KEY, self.experimental_cli_checkbox.isChecked())

        # Product policy decision, 2026-09-20 (strict option chosen over an opt-in plaintext-persist path): save_credential() has no way
        # to write a new key to disk in plaintext at all now -- session_only_entries only drives the informational notice below.
        session_only_entries = []
        for entry in self._providers:
            pv = entry["value"]
            self.settings.setValue(entry["model_setting_key"], self._resolve_model_value(pv))
            if pv in self._cached_model_lists:
                self.settings.setValue(provider_model_list_key(pv), json.dumps(self._cached_model_lists[pv]))

            key_text = self._key_edits[pv].text().strip()
            if entry.get("key_storage") == "setting":
                self.settings.setValue(cli_path_setting_key(pv), key_text)
                continue
            if key_text and CredentialManager.save_credential(pv, key_text) and CredentialManager.used_session_only_fallback(pv):
                session_only_entries.append(entry.get("provider_label", pv))

        firms_key_text = self.firms_key_edit.text().strip()
        if firms_key_text and CredentialManager.save_credential(FIRMS_KEY, firms_key_text) and CredentialManager.used_session_only_fallback(FIRMS_KEY):
            session_only_entries.append("NASA FIRMS")

        if session_only_entries:
            labels = ", ".join(session_only_entries)
            message = (
                "QGIS's encrypted credential store (QgsAuthManager) wasn't available, so the "
                "API key for " + labels + " will only be kept for this QGIS session -- it has "
                "NOT been saved to disk, and you'll need to re-enter it next time you start "
                "QGIS. Cartogen AI never stores API keys in plain text, so this isn't optional."
            )
            diagnostic = CredentialManager.get_auth_system_diagnostic_message()
            if diagnostic:
                message += "\n\n" + diagnostic
            QMessageBox.information(self, "Key kept for this session only", message)

        super().accept()
