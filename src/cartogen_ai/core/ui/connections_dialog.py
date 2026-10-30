"""The Connections window (PLAN-041): where the user configures and chooses the model connection -- hosted API keys, the local Ollama
server, and a CLI the user is already signed in to -- and where the NASA FIRMS data key lives.

Layout: a plain QListWidget of every connection on the left (grouped by where the prompts go, one heading per group, each row with a
status mark and an "in use" tag) and the selected connection's own page on the right (key or program path, model, Test / Check
connection, Sign in, and a "Use this connection" button). Choosing which page to look at and choosing which connection is in use are two
separate actions, so reading a page never changes what the assistant uses. No custom wrapping layout (one froze QGIS once; see
docs/BUG_TRACKER.md). The first version used a column of buttons that all rendered in the same brand blue, squeezed under a tall header;
the owner's screenshot (2026-10-30) showed it unreadable, so the list is now a native list and the header is two lines.

Everything here was section 01 and 02 of the Settings window until PLAN-041; the behaviour, the settings keys and the credential
storage are unchanged. CI-only until the owner has looked at it in QGIS."""
import contextlib
import json
import os
import threading
import time

from qgis.PyQt.QtCore import pyqtSignal, Qt, QTimer, QEvent
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QMessageBox, QApplication, QLineEdit, QComboBox, QFormLayout, QDialogButtonBox, QStackedWidget,
    QWidget, QCheckBox, QHBoxLayout, QPushButton, QScrollArea, QFrame, QListWidget, QListWidgetItem, QFileDialog,
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
# Short headings for the list on the left (the long ones in connections_catalog are the page subtitles), in the order shown.
_LIST_GROUPS = (
    ("hosted", "HOSTED -- API key"),
    ("local", "LOCAL -- stays on this computer"),
    ("cli", "YOUR OWN CLI LOGIN -- experimental"),
    ("data", "DATA SERVICES"),
)
_MARKS = {"verified": "\u2713", "set": "\u25cf", "unset": "\u25cb"}
_POLL_SECONDS = 3         # how often the window looks again while the user is signing in in a terminal
_POLL_GIVE_UP = 300       # and for how long


class CartogenAiConnectionsDialog(QDialog):
    # Fetching a model list hits the network -- must never block the UI thread (a slow or unreachable endpoint would otherwise freeze the
    # window, and QGIS with it, for the full request timeout). The background thread emits one of these signals; Qt queues delivery to
    # the slot on the main thread because this dialog lives there -- the same cross-thread pattern as dock_widget.py.
    modelsFetchedSignal = pyqtSignal(str, dict)
    cli_check_signal = pyqtSignal(str, dict)  # the CLI connection check runs a subprocess and a model call
    api_check_signal = pyqtSignal(str, dict)  # the Test button of the key-based providers
    detect_signal = pyqtSignal(list)          # the result of looking for CLIs already installed and signed in on this computer

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cartogen AI \u2014 Connections")
        self.setMinimumSize(780, 460)
        self.settings = QgsSettings()
        # The CLI entries are always listed, under their own heading. Their pages can be read at any time, but "Use this connection" stays
        # disabled until the user ticks the acknowledgement box under the list, and normalize_provider() ignores a saved CLI provider
        # while it is unticked.
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
        self._row_items = {}          # the list on the left: one item per connection (the item that is current is the page shown)
        self._use_buttons = {}        # "Use this connection" on each page
        self._in_use_labels = {}      # "In use" tag on each page
        self._step_details = {}       # the "what to do next" line on each CLI page
        self._verified_cli = set()    # CLIs that answered a test question in this window session
        self._poll_provider = None    # the CLI whose sign-in the window is waiting for
        self._poll_deadline = 0.0
        self._connect_after_check = None  # use this CLI as soon as its test answers
        self._page_index = {}
        # A provider only enters this set after a real _on_models_fetched success in THIS window session: a saved key that has not been
        # exercised this session is "set", not "verified" -- the window cannot know a key still works without calling the provider, so
        # the list shows two different marks rather than claiming more than it knows.
        self._verified_providers = set()
        self._detected = {}           # provider -> the last detection result (cli_bridge_status.detect_all)
        self._detecting = False
        self._last_detect_started = 0.0
        self._detect_labels = {}
        self._detect_buttons = {}
        self._shown_provider = None
        self.modelsFetchedSignal.connect(self._on_models_fetched)
        self.cli_check_signal.connect(self._on_cli_check)
        self.api_check_signal.connect(self._on_api_check)
        self.detect_signal.connect(self._on_detected)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_SECONDS * 1000)
        self._poll_timer.timeout.connect(self._on_poll)
        self.init_ui()
        self._start_detect()

    # ------------------------------------------------------------------ layout

    def init_ui(self):
        from ...infrastructure.auth import CredentialManager

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        screen = QApplication.primaryScreen()
        height = 620
        if screen is not None:
            height = min(height, max(460, int(screen.availableGeometry().height() * 0.85)))
        self.resize(900, height)

        # ---- header: what is in use now, and the hosted account
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 4)
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        header_layout.addWidget(self.summary_label, 1)
        self.account_button = QPushButton("Manage account")
        self.account_button.setObjectName("secondaryButton")
        self.account_button.setToolTip("Sign in to or manage your hosted Cartogen AI account.")
        self.account_button.clicked.connect(self._open_account_dialog)
        header_layout.addWidget(self.account_button)
        outer_layout.addWidget(header)

        data_note = QLabel("Chat text and any layer or attribute data a tool surfaces go to the connection in use.")
        data_note.setStyleSheet("color: gray; font-size: 11px;")
        data_note.setContentsMargins(16, 0, 16, 8)
        data_note.setToolTip(
            "Ollama stays on this computer; a CLI login sends it to that CLI's vendor. A provider's Data Processing Addendum link is a "
            "starting point, not a substitute for your organization's own GDPR review. See docs/USER_GUIDE.md and SECURITY.md.")
        outer_layout.addWidget(data_note)

        # ---- body: the list of connections on the left, the selected connection's page on the right
        body = QHBoxLayout()
        body.setContentsMargins(16, 0, 16, 0)
        body.setSpacing(16)

        left = QWidget()
        left.setFixedWidth(280)
        left_col = QVBoxLayout(left)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(6)
        self.connection_list = QListWidget()
        self.connection_list.setObjectName("connectionList")
        self.connection_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_col.addWidget(self.connection_list, 1)
        self.experimental_cli_checkbox = QCheckBox("Allow CLI logins (experimental)")
        self.experimental_cli_checkbox.setChecked(cli_providers_enabled())
        self.experimental_cli_checkbox.setToolTip(
            "I understand: use a CLI I am already signed in to as the model. Experimental and not yet verified against every CLI. "
            "Cartogen AI runs the program on this computer with your own account; it never sees or stores your login. The conversation, "
            "including any layer or attribute data a tool surfaces, goes to that vendor's service. Off by default.")
        self.experimental_cli_checkbox.toggled.connect(self._on_cli_ack_toggled)
        left_col.addWidget(self.experimental_cli_checkbox)
        legend = QLabel(f"{_MARKS['verified']} ready or checked    {_MARKS['set']} set    {_MARKS['unset']} not set")
        legend.setStyleSheet("color: gray; font-size: 11px;")
        left_col.addWidget(legend)
        body.addWidget(left)

        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.provider_stack = QStackedWidget()
        page_scroll.setWidget(self.provider_stack)
        body.addWidget(page_scroll, 1)

        self._active_provider = normalize_provider(self.settings.value(PROVIDER_KEY, "openrouter"))
        for entry in self._providers:
            self._page_index[entry["value"]] = self.provider_stack.addWidget(self._build_page(entry, CredentialManager))
        self._page_index[FIRMS_KEY] = self.provider_stack.addWidget(self._build_firms_page(CredentialManager))

        # Items go in group by group so each heading appears once (the provider table is not ordered by group).
        by_group = {}
        for entry in self._providers:
            by_group.setdefault(_group_of(entry), []).append(entry["value"])
        by_group["data"] = [FIRMS_KEY]
        for group, title in _LIST_GROUPS:
            heading = QListWidgetItem(title)
            heading.setFlags(Qt.ItemFlag.NoItemFlags)
            font = heading.font()
            font.setBold(True)
            font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
            heading.setFont(font)
            self.connection_list.addItem(heading)
            for pv in by_group.get(group, []):
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, pv)
                self.connection_list.addItem(item)
                self._row_items[pv] = item
        self.connection_list.currentItemChanged.connect(self._on_row_changed)

        body_holder = QWidget()
        body_holder.setLayout(body)
        outer_layout.addWidget(body_holder, 1)

        self.fetch_status_label = QLabel("Model lists refresh automatically when you leave an API key field.")
        self.fetch_status_label.setObjectName("secondaryLabel")
        self.fetch_status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.fetch_status_label.setWordWrap(True)
        self.fetch_status_label.setContentsMargins(16, 6, 16, 0)
        outer_layout.addWidget(self.fetch_status_label)

        # OK/Cancel are added to outer_layout, NOT to a scroll area, so they stay reachable at any window height.
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.setContentsMargins(16, 8, 16, 12)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setObjectName("settingsOkButton")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setObjectName("settingsCancelButton")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        outer_layout.addWidget(self.button_box)

        # Same narrowly scoped styling as the Settings window for OK and Cancel, scoped to object names unique to these windows so it
        # cannot touch the chat dock's own buttons. Only "Use this connection" keeps the filled brand colour; every other button on a
        # page is the quiet secondaryButton style, so the one action that matters is the one that stands out.
        self.setStyleSheet(build_dock_stylesheet(extract_theme_palette()) + f"""
QListWidget#connectionList {{
    border: 1px solid palette(mid);
    outline: 0;
}}
QListWidget#connectionList::item {{
    padding: 7px 8px;
}}
QListWidget#connectionList::item:selected {{
    background-color: {BRAND_TEAL};
    color: #ffffff;
}}
QPushButton#primaryAction {{
    background-color: {BRAND_TEAL};
    color: #ffffff;
}}
QPushButton#primaryAction:disabled {{
    background-color: palette(mid);
    color: palette(window);
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
    color: palette(window-text);
    border: 1px solid {BRAND_TEAL};
}}
""")
        self._refresh_rows()
        self._show_provider(self._active_provider if self._active_provider in self._page_index else DEFAULT_PROVIDER)

    def _build_page(self, entry, credentials):
        """One connection's page: title and 'Use this connection', then its key or program path, model, test buttons and help links."""
        pv = entry["value"]
        group = _group_of(entry)
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 4, 0)
        col.setSpacing(6)
        title_row = QHBoxLayout()
        title = QLabel(entry["provider_label"])
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        in_use = QLabel("\u2713 In use")
        in_use.setStyleSheet("font-size: 12px; font-weight: 700; color: #1c7a4d;")
        title_row.addWidget(title)
        title_row.addWidget(in_use)
        title_row.addStretch(1)
        self._in_use_labels[pv] = in_use
        col.addLayout(title_row)
        where = QLabel(_GROUP_TITLES[group])
        where.setWordWrap(True)
        where.setStyleSheet("color: gray; font-size: 11px;")
        col.addWidget(where)
        use_row = QHBoxLayout()
        use_btn = QPushButton("Use this connection")
        use_btn.setObjectName("primaryAction")
        use_btn.setToolTip("Makes this the connection the assistant uses. Nothing changes until you press OK.")
        if group == "cli":
            # On a CLI page this one button is the next step of the guided setup (install, sign in, connect, use); its text follows the
            # step (cli_bridge_status.setup_step), and _cli_primary does what it says.
            use_btn.clicked.connect(lambda _checked=False, p=pv: self._cli_primary(p))
        else:
            use_btn.clicked.connect(lambda _checked=False, p=pv: self._use_provider(p))
        use_row.addWidget(use_btn)
        self._use_buttons[pv] = use_btn
        use_row.addStretch(1)
        col.addLayout(use_row)
        if group == "cli":
            detect_row = QHBoxLayout()
            detect_label = QLabel("Looking...")
            detect_label.setWordWrap(True)
            detect_label.setStyleSheet("font-size: 12px; font-weight: 600;")
            self._detect_labels[pv] = detect_label
            detect_row.addWidget(detect_label, 1)
            detect_btn = QPushButton("Detect again")
            detect_btn.setObjectName("secondaryButton")
            detect_btn.setToolTip("Looks for the Claude Code and Codex programs and whether you are signed in. Runs only their "
                                  "version and sign-in status commands: no question is asked of any model.")
            detect_btn.clicked.connect(self._start_detect)
            self._detect_buttons[pv] = detect_btn
            detect_row.addWidget(detect_btn)
            col.addLayout(detect_row)
            step_detail = QLabel("")
            step_detail.setWordWrap(True)
            step_detail.setStyleSheet("color: gray; font-size: 11px;")
            step_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._step_details[pv] = step_detail
            col.addWidget(step_detail)

        page_form = QFormLayout()
        page_form.setContentsMargins(0, 8, 0, 2)
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
        if is_setting:
            field_row = QHBoxLayout()
            field_row.setContentsMargins(0, 0, 0, 0)
            field_row.addWidget(key_edit, 1)
            browse = QPushButton("Browse...")
            browse.setObjectName("secondaryButton")
            browse.setToolTip("Pick the program yourself if it was not found automatically.")
            browse.clicked.connect(lambda _checked=False, p=pv: self._browse_program(p))
            field_row.addWidget(browse)
            field_holder = QWidget()
            field_holder.setLayout(field_row)
            page_form.addRow(entry["key_label"], field_holder)
        else:
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
            check_btn.setObjectName("secondaryButton")
            check_btn.setToolTip("Finds the program, then asks the model one tiny question through your own login "
                                 "(a few tokens of your plan).")
            check_btn.clicked.connect(lambda _checked=False, p=pv: self._check_cli(p))
            signin_btn = QPushButton("Sign in...")
            signin_btn.setObjectName("secondaryButton")
            signin_btn.setToolTip("Opens a terminal running the program's own sign-in. Your login stays with that program.")
            signin_btn.clicked.connect(lambda _checked=False, p=pv: self._signin_and_wait(p))
            button_row.addWidget(check_btn)
            button_row.addWidget(signin_btn)
            button_row.addStretch(1)
            self._cli_buttons[pv] = (check_btn, signin_btn)
            button_holder = QWidget()
            button_holder.setLayout(button_row)
            page_form.addRow("", button_holder)
            key_edit.textChanged.connect(lambda text, p=pv: self._cli_status_labels[p].setText(self._cli_quick_status(p, text)))
            key_edit.textChanged.connect(lambda _text="", p=pv: self._forget_verified(p))
            # A path typed or pasted by hand is looked at as soon as the user leaves the field (the owner typed Codex's absolute path
            # and nothing happened, 2026-10-30: detection only ran on open).
            key_edit.editingFinished.connect(self._start_detect)

        if not is_setting and pv in _provider_check.TESTABLE:
            test_btn = QPushButton("Test")
            test_btn.setObjectName("secondaryButton")
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
        col.setContentsMargins(0, 0, 4, 0)
        col.setSpacing(6)
        title = QLabel("NASA FIRMS (active fires)")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        col.addWidget(title)
        note = QLabel("A data key, not a model: it powers fetch_nasa_active_fires. Leave it blank if you do not need live fire "
                      "monitoring; every other tool works without it.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        col.addWidget(note)
        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 2)
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

    def done(self, result):
        self._stop_poll()  # no timer keeps running after the window is closed
        super().done(result)

    def _on_row_changed(self, current, _previous):
        pv = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        if pv:
            self._display(pv)

    def _display(self, provider_value):
        index = self._page_index.get(provider_value)
        if index is not None:
            self.provider_stack.setCurrentIndex(index)
        self._shown_provider = provider_value

    def _show_provider(self, provider_value):
        """Shows a connection's page. Looking at a page does not change which connection is in use."""
        item = self._row_items.get(provider_value)
        if item is not None and self.connection_list.currentItem() is not item:
            self.connection_list.setCurrentItem(item)
        self._display(provider_value)

    def _use_provider(self, provider_value):
        """Makes a connection the one in use (saved when OK is pressed)."""
        self._active_provider = provider_value
        self._refresh_rows()

    def _row_mark(self, provider_value):
        """'verified' / 'set' / 'unset' for the mark in the list. Ollama has a URL, a CLI has a program: for a CLI 'verified' means the
        program was found and its own status says you are signed in; for a key it means this window got a real answer from the provider."""
        if provider_value == FIRMS_KEY:
            return "set" if self.firms_key_edit.text().strip() else "unset"
        edit = self._key_edits.get(provider_value)
        if edit is None or not edit.text().strip():
            return "unset"
        entry = next((e for e in self._providers if e["value"] == provider_value), None)
        if entry is not None and entry.get("key_storage") == "setting":
            found = self._detected.get(provider_value)
            if found is not None:
                if not found["found"]:
                    return "unset"
                return "verified" if found["state"] == "yes" else "set"
            return "set" if _cli_status.locate(provider_value, edit.text()) else "unset"
        return "verified" if provider_value in self._verified_providers else "set"

    def _refresh_rows(self):
        """Redraws the list marks, the 'In use' tags and the summary line from the current field text. Cheap (no network), so it runs on
        every keystroke."""
        if not hasattr(self, "firms_key_edit") or not self._row_items:
            return  # called via textChanged before init_ui has built everything
        for entry in self._providers:
            pv = entry["value"]
            item = self._row_items.get(pv)
            if item is None:
                continue
            active = pv == self._active_provider
            item.setText(f"{_MARKS[self._row_mark(pv)]}  {entry['pill_label']}" + ("   \u2022 in use" if active else ""))
            font = item.font()
            font.setBold(active)
            item.setFont(font)
            self._in_use_labels[pv].setVisible(active)
            self._use_buttons[pv].setVisible(not active)
        for cli in self._step_details:
            self._refresh_cli_step(cli)
        self._row_items[FIRMS_KEY].setText(f"{_MARKS[self._row_mark(FIRMS_KEY)]}  NASA FIRMS")
        entry = next((e for e in self._providers if e["value"] == self._active_provider), None)
        if entry is not None:
            model_text = self._model_combos[self._active_provider].currentText().strip() or AUTO_LABEL
            self.summary_label.setText(f"In use: {entry['provider_label']} \u00b7 {model_text} model")

    # ------------------------------------------------------- finding installed CLIs

    def _start_detect(self):
        """Looks for installed, signed-in CLIs on a background thread (it starts programs, so never on the UI thread)."""
        if self._detecting:
            return
        self._detecting = True
        self._last_detect_started = time.monotonic()
        for button in self._detect_buttons.values():
            button.setEnabled(False)
        for label in self._detect_labels.values():
            label.setText("Looking...")
        configured = {p: self._key_edits[p].text().strip() for p in _cli_status.DEFAULT_PROGRAM if p in self._key_edits}

        def worker():
            try:
                result = _cli_status.detect_all(configured)
            except Exception as e:
                result = [{"provider": p, "label": _cli_status.LABELS[p], "found": False, "path": "", "version": "",
                           "problem": f"Detection failed: {type(e).__name__}", "state": "unknown", "note": "", "tried": ""}
                          for p in _cli_status.DEFAULT_PROGRAM]
            with contextlib.suppress(RuntimeError):
                self.detect_signal.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_detected(self, results):
        self._detecting = False
        for button in self._detect_buttons.values():
            button.setEnabled(True)
        self._detected = {entry["provider"]: entry for entry in results}
        self._apply_detection()
        self._after_poll_detection()

    def _apply_detection(self):
        """Writes each result on its CLI page and into the list marks. Nothing is switched automatically: a CLI sends the conversation to
        that vendor's service, so moving to one is the user's decision (and needs the acknowledgement box ticked)."""
        for provider, label in self._detect_labels.items():
            entry = self._detected.get(provider)
            if entry is None:
                continue
            label.setText(_cli_status.describe(entry, short=True))
            folders = entry.get("searched") or []
            # Where the program was looked for, so "not found" can be checked against the folder it is really in.
            label.setToolTip("Looked in:\n" + "\n".join(folders) if (folders and not entry["found"]) else "")
            if entry["found"]:
                edit = self._key_edits[provider]
                # A saved path that no longer exists (program moved or reinstalled) while the program was found under its usual name:
                # put the real path in the field, so Check connection and Save use what was found instead of the stale text.
                if not _cli_status.locate(provider, edit.text()):
                    edit.setText(entry["path"])
                if provider not in self._cli_checking:
                    self._cli_status_labels[provider].setText(self._cli_quick_status(provider, edit.text()))
        self._refresh_rows()


    def _browse_program(self, provider):
        """Lets the user pick the program when it was not found: works the same on every OS, and fills the path field."""
        current = self._key_edits[provider].text().strip()
        start = os.path.dirname(current) if current and os.path.isabs(current) else os.path.expanduser("~")
        filters = "Programs (*.exe *.cmd *.bat);;All files (*)" if os.name == "nt" else "All files (*)"
        path, _selected = QFileDialog.getOpenFileName(self, f"Choose the {_cli_status.DEFAULT_PROGRAM[provider]} program", start, filters)
        if path:
            self._key_edits[provider].setText(path)
            self._start_detect()

    def _on_cli_ack_toggled(self, checked):
        """Unticking the box withdraws the consent: if a CLI was the connection in use the choice goes back to the default provider so Save
        cannot store a provider this window no longer offers. Ticking it is only the saved setting; the guided setup asks for the consent
        itself the first time a CLI is connected."""
        if not checked and self._active_provider in _cli_status.DEFAULT_PROGRAM:
            self._use_provider(DEFAULT_PROVIDER)
            self._show_provider(DEFAULT_PROVIDER)
        self._refresh_rows()

    # ------------------------------------------------------- guided setup of a CLI

    def _forget_verified(self, provider):
        if provider in self._verified_cli:
            self._verified_cli.discard(provider)
            self._refresh_rows()

    def _refresh_cli_step(self, provider):
        button = self._use_buttons.get(provider)
        if button is None:
            return
        step = _cli_status.setup_step(self._detected.get(provider), provider in self._verified_cli, provider == self._active_provider)
        button.setText(step["button"])
        button.setEnabled(step["kind"] != "looking" and provider not in self._cli_checking)
        self._step_details[provider].setText(step["detail"])

    def _confirm_cli_consent(self, provider):
        """Asks the user to agree to a CLI being used as the model (the conversation goes to that vendor). A method of its own so a test can
        answer it without a dialog."""
        box = QMessageBox(self)
        box.setWindowTitle("Cartogen AI")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(_cli_status.consent_text(provider))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Yes

    def _ensure_cli_consent(self, provider):
        if self.experimental_cli_checkbox.isChecked():
            return True
        if not self._confirm_cli_consent(provider):
            return False
        self.experimental_cli_checkbox.setChecked(True)
        return True

    def _cli_primary(self, provider):
        """What the page's main button does, by the step the CLI is at."""
        step = _cli_status.setup_step(self._detected.get(provider), provider in self._verified_cli, provider == self._active_provider)
        kind = step["kind"]
        if kind == "install":
            QApplication.clipboard().setText(step["command"])
            self._cli_status_labels[provider].setText(
                "Install command copied. Paste it into a terminal, wait for it to finish, then press Detect again.")
            return
        if kind in ("looking", "in_use"):
            return
        if not self._ensure_cli_consent(provider):
            return
        if kind == "signin":
            self._signin_and_wait(provider, consent_done=True)
        elif kind == "verify":
            self._connect_after_check = provider
            self._check_cli(provider)
        elif kind == "ready":
            self._use_provider(provider)
            self._show_provider(provider)

    def _start_poll(self, provider):
        """After the sign-in terminal is opened: look again every few seconds until the program says the user is signed in."""
        self._poll_provider = provider
        self._poll_deadline = time.monotonic() + _POLL_GIVE_UP
        self._poll_timer.start()

    def _stop_poll(self):
        self._poll_timer.stop()
        self._poll_provider = None

    def _on_poll(self):
        if self._poll_provider is None:
            self._poll_timer.stop()
            return
        if time.monotonic() > self._poll_deadline:
            provider = self._poll_provider
            self._stop_poll()
            self._cli_status_labels[provider].setText("Still not signed in after 5 minutes. Press Sign in... to try again.")
            return
        if not self._detecting:
            self._start_detect()

    def _after_poll_detection(self):
        """Called after every detection: when the user the window is waiting for has signed in, test the connection and use it."""
        provider = self._poll_provider
        if provider is None:
            return
        entry = self._detected.get(provider)
        if entry is not None and entry["found"] and entry["state"] in ("yes", "likely"):
            self._stop_poll()
            self._cli_status_labels[provider].setText("Signed in. Testing the connection...")
            self._connect_after_check = provider
            self._check_cli(provider)

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
        self._refresh_cli_step(provider)

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
        connect = self._connect_after_check == provider
        if connect:
            self._connect_after_check = None
        if result.get("ok"):
            version = f" ({result['version']})" if result.get("version") else ""
            self._verified_cli.add(provider)
            if connect:
                self._use_provider(provider)
                self._show_provider(provider)
                label.setText(f"Connected{version} and in use. Press OK to save.")
            else:
                label.setText(f"Ready{version}. Signed in. {result.get('message', '')}")
            self._refresh_rows()
            return
        hint = {"install": " Fix the program name or path above.", "signin": " Press Sign in..., finish there, then check again."}
        label.setText(f"Not ready: {result.get('message', 'unknown error')}{hint.get(result.get('stage'), '')}")
        if result.get("stage") == "signin" and provider in self._detected:
            self._detected[provider]["state"] = "no"  # the test says it is not signed in: the next step is the sign-in
        self._refresh_rows()

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
        return outcome

    def _signin_and_wait(self, provider, consent_done=False):
        """Opens the program's own sign-in, then waits for it: looks again every few seconds and when the window is clicked back into
        (after a browser or terminal), notices the login, tests the connection and uses it. The page's main button and its small
        "Sign in..." button both come here (the small one used to open the sign-in and then forget about it)."""
        if not consent_done and not self._ensure_cli_consent(provider):
            return
        outcome = self._signin_cli(provider)
        self._cli_status_labels[provider].setText(outcome["message"] + " This window is waiting for you to finish and will notice.")
        self._start_poll(provider)

    def changeEvent(self, event):  # noqa: N802 -- Qt virtual, the name is fixed
        """Coming back to this window (from the browser or terminal of a sign-in, or from installing a program) looks again, at most
        every 5 seconds, so the page shows what changed without anyone pressing Detect again."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow() and self._detected:
            now = time.monotonic()
            if not self._detecting and now - self._last_detect_started > 5:
                self._start_detect()

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
