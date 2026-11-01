
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QApplication,
    QLineEdit, QComboBox, QFormLayout, QDialogButtonBox, QWidget, QCheckBox, QHBoxLayout, QPushButton, QSpinBox,
    QScrollArea, QFrame, QToolButton,
)
from qgis.core import QgsSettings

from ..agent.agent_orchestrator import DEFAULT_TURN_TOKEN_BUDGET
from ..agent.chat_persistence import PERSIST_DEFAULT, PERSIST_SETTING_KEY
from ..agent.memory import PERSIST_PROJECT_MEMORY_KEY

from ..models.model_view import SCHEMA_DISCLOSURE
from ..services.prompt_refiner import (
    PROFILE_LABELS, DEFAULT_PROFILE,
    PROMPT_REFINEMENT_ENABLED_KEY, PROMPT_PREVIEW_ENABLED_KEY, USER_PROFILE_KEY,
)
from .chat_formatting import build_dock_stylesheet, BRAND_TEAL
from ...infrastructure.settings_keys import (
    SETTINGS_API_TRACE_ENABLED,
    SETTINGS_EVIDENCE_ENABLED,
    SETTINGS_PROVIDER as PROVIDER_KEY,
    normalize_provider,
    SETTINGS_PROJECT_INSPECTOR_ENABLED as PROJECT_INSPECTOR_ENABLED_KEY,
    SETTINGS_PLAN_VALIDATION_GATE_ENABLED as PLAN_VALIDATION_GATE_ENABLED_KEY,
    SETTINGS_EGRESS_GATE_MODE as EGRESS_GATE_MODE_KEY,
    SETTINGS_EGRESS_GATE_STRICT as EGRESS_GATE_STRICT_KEY,
    SETTINGS_MAX_TOOL_ITERATIONS as MAX_TOOL_ITERATIONS_KEY,
    SETTINGS_MAX_TURN_TOKENS as MAX_TURN_TOKENS_KEY,
    SETTINGS_LAYOUT_MASTHEAD_COLOR as LAYOUT_MASTHEAD_COLOR_KEY,
    SETTINGS_LAYOUT_DISCLAIMER_ENABLED as LAYOUT_DISCLAIMER_ENABLED_KEY,
    SETTINGS_LAYOUT_DISCLAIMER_TEXT as LAYOUT_DISCLAIMER_TEXT_KEY,
    SETTINGS_AUTO_OPEN_DOCK as AUTO_OPEN_DOCK_KEY,
    SETTINGS_LOCAL_DATA_ASK_ABOVE_MB as LOCAL_DATA_ASK_ABOVE_MB_KEY,
)
from .connections_catalog import PROVIDERS, _CLI_PROVIDERS
from .theme_palette import extract_theme_palette as _extract_theme_palette


class CartogenAiSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cartogen AI — Settings")
        self.setMinimumWidth(420)
        self.settings = QgsSettings()
        self._collapsibles = []
        self.init_ui()

    def init_ui(self):

        # Real live report, 2026-09-15: "the setting window unable to save NASA free Api key,
        # and the window is too long can not press ok or cancel" -- confirmed via screenshot.
        # Every field used to go straight into one QVBoxLayout on the dialog itself, so the
        # dialog auto-sized to fit ALL of it (account row, provider picker, privacy note, the
        # per-provider key/model page, the FIRMS key, 4 checkboxes, persona picker, profile
        # button) with nothing capping its height -- on a screen too short for that (a laptop, or
        # a QGIS window not maximized), the bottom of the dialog -- OK/Cancel -- ends up entirely
        # off-screen with no way to reach it, so the FIRMS key the user typed could never
        # actually be saved: accept() only runs when OK is clicked. Fixed by putting everything
        # except the button row inside a QScrollArea, and keeping the button row fixed outside
        # it in its own outer layout, so OK/Cancel always stay reachable regardless of content
        # height or screen size.
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        scroll_area.setWidget(content)
        outer_layout.addWidget(scroll_area)

        screen = QApplication.primaryScreen()
        if screen is not None:
            self.setMaximumHeight(max(300, int(screen.availableGeometry().height() * 0.85)))

        # The connections (hosted API keys, Ollama, a CLI login, NASA FIRMS) have their own window since PLAN-041; this row says which one
        # is in use and opens it. Choosing a connection is saved by that window's own OK, not by this window's.
        connection_row = QHBoxLayout()
        self.connection_summary_label = QLabel()
        self.connection_summary_label.setWordWrap(True)
        self.connection_summary_label.setStyleSheet("font-size: 12px;")
        connection_row.addWidget(self.connection_summary_label, 1)
        self.open_connections_button = QPushButton("Connections…")
        self.open_connections_button.setToolTip("API keys, models, Ollama, and signed-in CLIs such as Claude Code or Codex.")
        self.open_connections_button.clicked.connect(self._open_connections)
        connection_row.addWidget(self.open_connections_button)
        layout.addLayout(connection_row)
        self._update_connection_summary()

        # PLAN-039 slice 2: the old "03 What gets kept and shown" mixed privacy, behaviour, print-layout and diagnostic settings, and put
        # the cloud data protection gate (the most consequential switch here) below the print-layout colour. Widgets are still built where
        # they always were; each goes into the column of the section it belongs to, and the sections are laid out in order below.
        privacy_gate_col = QVBoxLayout()
        privacy_keep_col = QVBoxLayout()
        behaviour_col = QVBoxLayout()
        experimental_col = QVBoxLayout()
        layouts_col = QVBoxLayout()
        diag_col = QVBoxLayout()
        layout_form = QFormLayout()

        # S2: opt-in, default OFF -- chat history used to always be written
        # into the project (.qgz) file with no way to turn it off. A project
        # file is a shareable artifact (emailed, committed, uploaded), so
        # saving the conversation into it by default risked carrying
        # sensitive content (humanitarian incident/security details, internal
        # notes) along with the map without the user ever choosing that.
        self.auto_open_dock_checkbox = QCheckBox("Open the Cartogen AI panel when QGIS starts")
        self.auto_open_dock_checkbox.setChecked(bool(self.settings.value(AUTO_OPEN_DOCK_KEY, True, type=bool)))
        behaviour_col.addWidget(self.auto_open_dock_checkbox)

        self.persist_history_checkbox = QCheckBox("Save the conversation in the project file")
        self.persist_history_checkbox.setChecked(
            bool(self.settings.value(PERSIST_SETTING_KEY, PERSIST_DEFAULT, type=bool)))
        self.persist_history_checkbox.setToolTip(
            "On by default. The full conversation for this project is saved inside its .qgz file and kept "
            "for the life of the project, so it is still there -- and exportable -- next time you open it "
            "(very long projects are bounded; the oldest messages are dropped first). The project file "
            "may be shared, emailed, or committed elsewhere, and the conversation travels with it: turn "
            "this off for projects that discuss sensitive material. Turning it off does not remove what is "
            "already saved; use 'Clear Saved Chat' in the Memory window for that."
        )
        privacy_keep_col.addWidget(self.persist_history_checkbox)

        # GDPR review finding F6 (docs/GDPR_COMPLIANCE_REVIEW.docx): project-scoped
        # memory notes had no equivalent opt-in at all -- always written to a sidecar
        # .sqlite file next to the project and a QgsProject custom property embedded
        # in the .qgz, both shareable artifacts, same risk as chat history above.
        self.persist_project_memory_checkbox = QCheckBox("Save project notes/memory in the project file and sidecar database")
        self.persist_project_memory_checkbox.setChecked(
            bool(self.settings.value(PERSIST_PROJECT_MEMORY_KEY, False, type=bool))
        )
        self.persist_project_memory_checkbox.setToolTip(
            "When on, project-scoped AI memory notes are saved inside this project's .qgz file and a "
            "sidecar .sqlite database next to it, so they're still there next time you open it. Both "
            "files may be shared, emailed, or committed elsewhere -- the notes travel with them. "
            "Turning this off does not remove notes already saved from before this was disabled."
        )
        privacy_keep_col.addWidget(self.persist_project_memory_checkbox)

        self.evidence_checkbox = QCheckBox("Save an evidence folder for each request (testing and review)")
        self.evidence_checkbox.setChecked(bool(self.settings.value(SETTINGS_EVIDENCE_ENABLED, False, type=bool)))
        self.evidence_checkbox.setToolTip(
            "When on, every request writes a folder 'cartogen_evidence/<time>_<n>' next to the project (or in the QGIS profile "
            "folder for an unsaved project) holding the request, every tool call with its REAL arguments and results, timings, the "
            "layers created, the final reply, a map-canvas screenshot and copies of any files written, with SHA-256 hashes. "
            "Unlike the logs, this includes raw values such as coordinates and attribute data, so do not share the folder "
            "without checking it. Nothing is uploaded. Off by default.")
        diag_col.addWidget(self.evidence_checkbox)

        self.api_trace_checkbox = QCheckBox("Record every model request and reply to a local folder (diagnostics)")
        self.api_trace_checkbox.setChecked(bool(self.settings.value(SETTINGS_API_TRACE_ENABLED, False, type=bool)))
        self.api_trace_checkbox.setToolTip(
            "When on, every call to the model provider is written as one line to 'cartogen_api_trace/api_calls_<date>.jsonl' next to "
            "the project (or in the QGIS profile folder for an unsaved project): the system instruction (kept once per distinct text), "
            "the messages sent, the tool names offered, the reply and the token usage. It holds RAW text, including layer and field "
            "names, attribute values and tool results, so check the folder before you share it. Nothing is uploaded. "
            "Off by default. Use tools/summarize_api_trace.py to read it.")
        diag_col.addWidget(self.api_trace_checkbox)

        # Roadmap feature per docs/archive/PROMPT_REFINEMENT_LAYER_SPEC.md -- opt-in,
        # default OFF (§9: the spec's own honest cost tradeoff in §8 means
        # this shouldn't silently change every user's per-message cost
        # profile until real usage data justifies flipping the default).
        self.prompt_refinement_checkbox = QCheckBox("Suggest clarified prompt rewrites before sending")
        self.prompt_refinement_checkbox.setChecked(
            bool(self.settings.value(PROMPT_REFINEMENT_ENABLED_KEY, False, type=bool))
        )
        self.prompt_refinement_checkbox.setToolTip(
            "When on, a longer or ambiguous message shows two AI-rewritten alternatives to pick "
            "from, edit, or skip before it's sent. Off by default -- this adds one small extra "
            "API call per refined message (roughly 300-650 tokens, see "
            "docs/archive/API_COST_OPTIMIZATION_REVIEW.md and docs/archive/PROMPT_REFINEMENT_LAYER_SPEC.md §8)."
        )
        behaviour_col.addWidget(self.prompt_refinement_checkbox)

        # Default ON, unlike the checkbox above: this one costs nothing (it
        # renders text that has already been composed locally) and exists so
        # that the register's enrichment -- assumed defaults, attachment
        # handling, the task directive added to the system prompt -- is never
        # applied to a message without the user seeing it first.
        self.prompt_preview_checkbox = QCheckBox("Show the prompt and reasoning before sending")
        self.prompt_preview_checkbox.setChecked(
            bool(self.settings.value(PROMPT_PREVIEW_ENABLED_KEY, True, type=bool))
        )
        self.prompt_preview_checkbox.setToolTip(
            "When on, a message that matches a task in the Humanitarian Mapping Task Register "
            "shows the exact text that will be sent -- including any values assumed on your "
            "behalf and what each attached file will be read as -- with the reasoning behind "
            "it, before anything reaches the API. No extra API call. On by default."
        )
        behaviour_col.addWidget(self.prompt_preview_checkbox)

        # IMPLEMENTATION_TRACKER.md §1.5, option (b), narrow experiment -- opt-in, default OFF.
        # Same "don't silently change every user's cost/friction profile" reasoning as the
        # refinement checkbox above: this adds project layout/theme/metadata info to every
        # system prompt when on -- see project_inspector.py's module docstring.
        self.project_inspector_checkbox = QCheckBox(
            "Include print layouts, map themes, and project metadata in context"
        )
        self.project_inspector_checkbox.setChecked(
            bool(self.settings.value(PROJECT_INSPECTOR_ENABLED_KEY, False, type=bool))
        )
        self.project_inspector_checkbox.setToolTip(
            "When on, the assistant sees this project's saved print layouts, map themes, and "
            "title/abstract/author/keywords metadata on every turn, without needing a separate "
            "tool call to look them up. Off by default -- this is a narrow, experimental "
            "addition (IMPLEMENTATION_TRACKER.md §1.5) that adds a small amount of extra prompt "
            "content on every turn, whether or not the current request needs it."
        )
        experimental_col.addWidget(self.project_inspector_checkbox)

        # IMPLEMENTATION_TRACKER.md §1.6, option (b), narrow experiment -- opt-in, default OFF.
        # Same "don't silently change every user's cost/friction profile" reasoning as the
        # refinement checkbox above: this adds one extra required tool call (create_plan)
        # before any DELETE/PUBLISH-classified tool -- see plan_gate.py's module docstring.
        self.plan_validation_gate_checkbox = QCheckBox(
            "Require a stated plan before destructive or export/report actions"
        )
        self.plan_validation_gate_checkbox.setChecked(
            bool(self.settings.value(PLAN_VALIDATION_GATE_ENABLED_KEY, False, type=bool))
        )
        self.plan_validation_gate_checkbox.setToolTip(
            "When on, the assistant must state a plan (create_plan) before removing a layer, "
            "replacing the project, running a script, or exporting/printing/reporting anything -- "
            "once per turn, not before every individual call. Off by default -- this is a narrow, "
            "experimental safety gate (IMPLEMENTATION_TRACKER.md §1.6) that adds friction to "
            "exactly the operation types that already carry the most real-world consequence if "
            "wrong, at the cost of one extra tool call before the first one of them each turn."
        )
        experimental_col.addWidget(self.plan_validation_gate_checkbox)

        # rc7 smoke test F10/F22: limits that keep one request's cost and download size in the user's hands.
        limits_form = QFormLayout()
        self.max_tool_iterations_spin = QSpinBox()
        self.max_tool_iterations_spin.setRange(1, 100)
        self.max_tool_iterations_spin.setValue(self._int_setting(MAX_TOOL_ITERATIONS_KEY, 20, 1, 100))
        self.max_tool_iterations_spin.setToolTip(
            "The most tool-call rounds one request may use before the assistant stops and says so. Default 20.")
        limits_form.addRow("Max tool-call rounds per request:", self.max_tool_iterations_spin)
        self.max_turn_tokens_spin = QSpinBox()
        self.max_turn_tokens_spin.setRange(0, 5_000_000)
        self.max_turn_tokens_spin.setSingleStep(10_000)
        self.max_turn_tokens_spin.setSpecialValueText("no limit")
        self.max_turn_tokens_spin.setValue(self._int_setting(MAX_TURN_TOKENS_KEY, DEFAULT_TURN_TOKEN_BUDGET, 0, 5_000_000))
        self.max_turn_tokens_spin.setToolTip(
            "Stops a request once the model calls in it have used this many tokens (input + output; input the provider served from its cache counts at 10 percent). "
            "0 = no limit. The default (450,000) is a provisional guardrail from observed use, not an optimum; the chat footer shows what each request used, so you can pick a number from real use.")
        limits_form.addRow("Max tokens per request:", self.max_turn_tokens_spin)
        self.layout_masthead_edit = QLineEdit()
        self.layout_masthead_edit.setPlaceholderText("#1f2d3a (default slate)")
        self.layout_masthead_edit.setMaxLength(7)
        self.layout_masthead_edit.setText(str(self.settings.value(LAYOUT_MASTHEAD_COLOR_KEY, "") or ""))
        self.layout_masthead_edit.setToolTip(
            "Title-bar colour on exported print layouts, as #rrggbb. Empty or invalid = the default slate. "
            "Light colours automatically get dark title text.")
        layout_form.addRow("Print layout title colour:", self.layout_masthead_edit)
        self.layout_disclaimer_checkbox = QCheckBox("Add a boundary / data-sensitivity line to the footer of print layouts")
        self.layout_disclaimer_checkbox.setChecked(bool(self.settings.value(LAYOUT_DISCLAIMER_ENABLED_KEY, True, type=bool)))
        layout_form.addRow("Layout disclaimer:", self.layout_disclaimer_checkbox)
        self.layout_disclaimer_edit = QLineEdit()
        self.layout_disclaimer_edit.setMaxLength(300)
        self.layout_disclaimer_edit.setPlaceholderText("empty = the standard Cartogen AI disclaimer; enter your organisation's wording here")
        self.layout_disclaimer_edit.setText(str(self.settings.value(LAYOUT_DISCLAIMER_TEXT_KEY, "") or ""))
        self.layout_disclaimer_edit.setToolTip(
            "The exact boundary and data-sensitivity wording your organisation requires on a published map. "
            "Empty uses the standard Cartogen AI disclaimer (about four lines). Keep your own to a few lines: the footer grows to fit, taking height from the bottom of the map, but the space on the page is limited.")
        layout_form.addRow("Disclaimer wording:", self.layout_disclaimer_edit)
        self.local_data_ask_spin = QSpinBox()
        self.local_data_ask_spin.setRange(0, 100_000)
        self.local_data_ask_spin.setSuffix(" MB")
        self.local_data_ask_spin.setSpecialValueText("always ask")
        self.local_data_ask_spin.setValue(self._int_setting(LOCAL_DATA_ASK_ABOVE_MB_KEY, 50, 0, 100_000))
        self.local_data_ask_spin.setToolTip(
            "Downloads larger than this (or of unknown size, or on a metered connection) ask you first. "
            "Default 50 MB; 'always ask' asks for every download.")
        limits_form.addRow("Ask before downloads larger than:", self.local_data_ask_spin)
        behaviour_col.addLayout(limits_form)
        layouts_col.addLayout(layout_form)

        # Cloud-provider egress gate (docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md) -- OFF by
        # default. A safeguard against ACCIDENTS: the setting lives in this user's own QgsSettings,
        # so it does not stop someone determined to bypass it (see egress_gate.py's docstring).
        egress_form = QFormLayout()
        self.egress_gate_mode_combo = QComboBox()
        self.egress_gate_mode_combo.addItem("Off", "off")
        self.egress_gate_mode_combo.addItem("Warn only", "warn")
        self.egress_gate_mode_combo.addItem("Block", "enforce")
        egress_index = self.egress_gate_mode_combo.findData(
            self.settings.value(EGRESS_GATE_MODE_KEY, "off")
        )
        self.egress_gate_mode_combo.setCurrentIndex(egress_index if egress_index >= 0 else 0)
        self.egress_gate_mode_combo.setToolTip(
            "Protects layers you have tagged RESTRICTED or SENSITIVE (and layers derived from "
            "them) from being sent to a cloud AI provider. 'Block' stops the tool call; 'Warn "
            "only' lets it run and tells you. It only applies while a cloud provider is selected "
            "-- a local Ollama server on this machine or your own network is never restricted. "
            "Off by default. This guards against mistakes, not against someone determined to "
            "bypass it. See SECURITY.md, 'DPIA determination and deployment constraints'."
        )
        egress_form.addRow("Cloud data protection:", self.egress_gate_mode_combo)
        privacy_gate_col.addLayout(egress_form)

        # Decision 1 of docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md §7's six deployment
        # decisions, recorded 2026-09-28: the code default stays Off (reversible, no surprise
        # for a fresh install), but a deployment that has completed the DPIA sign-off for
        # protection/incident/displacement data should not stay on that default -- surfaced as
        # guidance here rather than auto-switched, matching this project's existing
        # document-don't-silently-decide pattern for the Ollama-only posture (SECURITY.md).
        egress_recommendation = QLabel(
            "Recommended: set this to “Block” once your deployment has completed the "
            "DPIA sign-off for protection, incident, or displacement data (see SECURITY.md, "
            "“DPIA determination and deployment constraints”). Off is the safe, "
            "no-surprises default for a general install -- this plugin cannot detect on its own "
            "whether your deployment's DPIA is complete, so it is not switched automatically."
        )
        egress_recommendation.setWordWrap(True)
        egress_recommendation.setStyleSheet("color: gray; font-size: 11px;")
        privacy_gate_col.addWidget(egress_recommendation)

        # #93: what the setting does NOT hide, stated where the setting is.
        schema_disclosure = QLabel(SCHEMA_DISCLOSURE)
        schema_disclosure.setWordWrap(True)
        schema_disclosure.setStyleSheet("color: gray; font-size: 11px;")
        privacy_gate_col.addWidget(schema_disclosure)

        self.egress_gate_strict_checkbox = QCheckBox(
            "Treat layers with no sensitivity tag as protected"
        )
        self.egress_gate_strict_checkbox.setChecked(
            bool(self.settings.value(EGRESS_GATE_STRICT_KEY, False, type=bool))
        )
        self.egress_gate_strict_checkbox.setToolTip(
            "Strict mode: on a cloud provider, only layers explicitly tagged PUBLIC or INTERNAL "
            "may be used; an untagged layer counts as protected. Safer, but every layer must be "
            "classified before the cloud assistant can work with it. Off by default -- without "
            "it, a layer you forgot to tag is NOT protected."
        )
        privacy_gate_col.addWidget(self.egress_gate_strict_checkbox)

        layout.addWidget(self._section_header("01", "Privacy and data protection"))
        layout.addWidget(self._section_note(
            "What may leave this machine, and what is saved into files that can be shared. Settings here are the ones to review first."))
        layout.addLayout(privacy_gate_col)
        layout.addLayout(privacy_keep_col)

        layout.addWidget(self._section_header("02", "How the assistant works"))
        layout.addWidget(self._section_note("Prompts, limits and downloads. The experimental options are off by default."))
        layout.addLayout(behaviour_col)
        layout.addWidget(self._collapsible(
            "Experimental options", experimental_col,
            expanded=self.project_inspector_checkbox.isChecked() or self.plan_validation_gate_checkbox.isChecked()))

        layout.addWidget(self._section_header("03", "Who the assistant writes for"))

        profile_form = QFormLayout()
        self.user_profile_combo = QComboBox()
        for value, label in PROFILE_LABELS.items():
            self.user_profile_combo.addItem(label, value)
        current_profile = self.settings.value(USER_PROFILE_KEY, DEFAULT_PROFILE)
        profile_index = self.user_profile_combo.findData(current_profile)
        if profile_index >= 0:
            self.user_profile_combo.setCurrentIndex(profile_index)
        profile_form.addRow("Refinement Persona:", self.user_profile_combo)
        layout.addLayout(profile_form)

        # Not to be confused with "Refinement Persona" just above -- this is the separate
        # onboarding profile (role/experience/communication style, agent/onboarding_profile.py),
        # shown once at first use and re-editable here. Opens its own dialog rather than being
        # inlined as more combo rows in this already-dense dialog.
        self.edit_onboarding_profile_btn = QPushButton("Edit My Profile…")
        self.edit_onboarding_profile_btn.setObjectName("secondaryButton")
        self.edit_onboarding_profile_btn.setToolTip(
            "Your role, QGIS experience level, and preferred communication style -- helps "
            "Cartogen AI tailor its tone and detail level. Saved as a local .md file you can "
            "also edit by hand."
        )
        self.edit_onboarding_profile_btn.clicked.connect(self._open_onboarding_profile)
        layout.addWidget(self.edit_onboarding_profile_btn)

        layout.addWidget(self._section_header("04", "Print layouts"))
        layout.addWidget(self._section_note("How exported maps look and what their footer says."))
        layout.addLayout(layouts_col)

        layout.addWidget(self._section_header("05", "Diagnostics"))
        layout.addWidget(self._section_note(
            "For testing and support. These write raw request data to local folders; nothing is uploaded."))
        layout.addWidget(self._collapsible(
            "Diagnostic recording", diag_col,
            expanded=self.evidence_checkbox.isChecked() or self.api_trace_checkbox.isChecked()))

        # Buttons -- deliberately added to outer_layout, NOT layout/scroll_area, so OK/Cancel
        # stay fixed and reachable at the bottom of the dialog regardless of how tall the
        # scrollable content above grows. See init_ui's opening comment for the live bug this fixes.
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.setContentsMargins(12, 8, 12, 12)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setObjectName("settingsOkButton")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setObjectName("settingsCancelButton")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        outer_layout.addWidget(self.button_box)

        # Real live report, 2026-09-16: a first pass at this redesign left OK/Cancel as the
        # shared build_dock_stylesheet's default QPushButton rule -- large, rounded, and
        # colored from _brand_accent(), which BLENDS the live QGIS theme's own accent toward
        # the brand teal rather than using it outright, so on a theme with a strong native
        # blue it read as generic Windows-blue, not the design proposal's teal. Confirmed via
        # a real screenshot: the result looked nothing like the approved mockup. This extra,
        # narrowly-scoped stylesheet (appended after, so it wins) pins OK/Cancel and the
        # active provider pill to the actual brand teal constant, and trims their padding
        # closer to the mockup's compact pills -- scoped to object names unique to this
        # dialog so it can't affect the chat dock's own Send/Stop buttons, which still use
        # the shared, theme-blended style on purpose.
        self.setStyleSheet(build_dock_stylesheet(_extract_theme_palette()) + f"""
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

    def _section_note(self, text):
        """A one-line, grey description under a section heading, saying what the section governs."""
        note = QLabel(text)
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        return note

    def _collapsible(self, title, content_layout, expanded=False):
        """A heading with a show/hide arrow above `content_layout`. It opens by itself when anything inside is already switched on, so a
        setting that is in effect is never hidden. Everything inside stays a normal attribute, so Save reads it whether open or not."""
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        toggle = QToolButton()
        toggle.setText(title)
        toggle.setCheckable(True)
        toggle.setChecked(expanded)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        toggle.setStyleSheet("QToolButton { border: none; font-weight: 600; font-size: 12px; }")
        body = QWidget()
        body.setLayout(content_layout)
        body.setVisible(expanded)

        def on_toggled(on):
            body.setVisible(on)
            toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)

        toggle.toggled.connect(on_toggled)
        holder_layout.addWidget(toggle)
        holder_layout.addWidget(body)
        self._collapsibles.append((title, toggle, body))
        return holder

    def _section_header(self, number, title):
        """Visual design proposal, 2026-09-16 (adapted from Settings Window.pdf's option 1c):
        a small serif numeral beside a section title, the same device used for the chat
        panel's capability index. Purely a scan aid for a dialog that has grown to 4 real,
        distinct groups (connection, keys, what's kept, who it writes for) -- the numbering
        isn't claiming any ordering dependency between them, just giving each one a landmark."""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 10, 0, 2)
        row_layout.setSpacing(8)
        no_label = QLabel(number)
        no_label.setStyleSheet(
            "color: #a3255a; font-weight: 700; font-size: 13px; "
            "font-family: Georgia, 'Times New Roman', serif;"
        )
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: 700; font-size: 12.5px;")
        row_layout.addWidget(no_label)
        row_layout.addWidget(title_label)
        row_layout.addStretch(1)
        return row

    def _open_connections(self):
        from .connections_dialog import CartogenAiConnectionsDialog
        dialog = CartogenAiConnectionsDialog(self)
        if dialog.exec():
            self._update_connection_summary()

    def _update_connection_summary(self):
        provider = normalize_provider(self.settings.value(PROVIDER_KEY, "openrouter"))
        entry = next((e for e in PROVIDERS + _CLI_PROVIDERS if e["value"] == provider), None)
        label = entry["provider_label"] if entry else provider
        self.connection_summary_label.setText(f"Connection in use: {label}")

    def _open_onboarding_profile(self):
        from .onboarding_dialog import OnboardingDialog
        dialog = OnboardingDialog(self)
        dialog.exec()

    def _int_setting(self, key, default, low, high):
        """An int setting clamped to [low, high]; the default when unset or unreadable."""
        try:
            raw = self.settings.value(key, None)
            if raw in (None, ""):
                return default
            return min(max(int(float(raw)), low), high)
        except (TypeError, ValueError):
            return default

    def accept(self):
        self.settings.setValue(PERSIST_SETTING_KEY, self.persist_history_checkbox.isChecked())
        self.settings.setValue(PERSIST_PROJECT_MEMORY_KEY, self.persist_project_memory_checkbox.isChecked())
        self.settings.setValue(SETTINGS_EVIDENCE_ENABLED, self.evidence_checkbox.isChecked())
        self.settings.setValue(SETTINGS_API_TRACE_ENABLED, self.api_trace_checkbox.isChecked())
        self.settings.setValue(PROMPT_REFINEMENT_ENABLED_KEY, self.prompt_refinement_checkbox.isChecked())
        self.settings.setValue(PROMPT_PREVIEW_ENABLED_KEY, self.prompt_preview_checkbox.isChecked())
        self.settings.setValue(PROJECT_INSPECTOR_ENABLED_KEY, self.project_inspector_checkbox.isChecked())
        self.settings.setValue(PLAN_VALIDATION_GATE_ENABLED_KEY, self.plan_validation_gate_checkbox.isChecked())
        self.settings.setValue(MAX_TOOL_ITERATIONS_KEY, self.max_tool_iterations_spin.value())
        self.settings.setValue(MAX_TURN_TOKENS_KEY, self.max_turn_tokens_spin.value())
        self.settings.setValue(AUTO_OPEN_DOCK_KEY, self.auto_open_dock_checkbox.isChecked())
        self.settings.setValue(LAYOUT_MASTHEAD_COLOR_KEY, self.layout_masthead_edit.text().strip())
        self.settings.setValue(LAYOUT_DISCLAIMER_ENABLED_KEY, self.layout_disclaimer_checkbox.isChecked())
        self.settings.setValue(LAYOUT_DISCLAIMER_TEXT_KEY, self.layout_disclaimer_edit.text().strip())
        self.settings.setValue(LOCAL_DATA_ASK_ABOVE_MB_KEY, self.local_data_ask_spin.value())
        self.settings.setValue(EGRESS_GATE_MODE_KEY, self.egress_gate_mode_combo.currentData())
        self.settings.setValue(EGRESS_GATE_STRICT_KEY, self.egress_gate_strict_checkbox.isChecked())
        self.settings.setValue(USER_PROFILE_KEY, self.user_profile_combo.currentData())

        super().accept()
