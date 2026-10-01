import json
import threading

from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QMessageBox, QApplication,
    QLineEdit, QComboBox, QFormLayout, QDialogButtonBox, QStackedWidget, QWidget, QCheckBox, QHBoxLayout, QPushButton, QSpinBox,
    QScrollArea, QFrame, QButtonGroup,
)
from qgis.core import QgsSettings

from ..agent.chat_persistence import PERSIST_DEFAULT, PERSIST_SETTING_KEY
from ..agent.memory import PERSIST_PROJECT_MEMORY_KEY

from ..agent.model_selector import AUTO_SENTINEL
from ..services.prompt_refiner import (
    PROFILE_LABELS, DEFAULT_PROFILE,
    PROMPT_REFINEMENT_ENABLED_KEY, PROMPT_PREVIEW_ENABLED_KEY, USER_PROFILE_KEY,
)
from ...infrastructure.providers.openrouter import list_models as _list_openrouter
from ...infrastructure.providers.gemini import list_models as _list_gemini
from ...infrastructure.providers.ollama import list_models as _list_ollama
from ...infrastructure.providers.openai import list_models as _list_openai
from ...infrastructure.providers.claude import list_models as _list_claude
from ...infrastructure.providers.cartogen import list_models as _list_cartogen, FALLBACK_MODELS as _CARTOGEN_FALLBACK_MODELS
from .chat_formatting import build_dock_stylesheet, BRAND_TEAL
from ...infrastructure.settings_keys import (
    SETTINGS_PROVIDER as PROVIDER_KEY,
    SETTINGS_OPENROUTER_MODEL,
    SETTINGS_GEMINI_MODEL,
    SETTINGS_OLLAMA_MODEL,
    SETTINGS_OPENAI_MODEL,
    SETTINGS_CLAUDE_MODEL,
    SETTINGS_CARTOGEN_MODEL,
    SETTINGS_PROJECT_INSPECTOR_ENABLED as PROJECT_INSPECTOR_ENABLED_KEY,
    SETTINGS_PLAN_VALIDATION_GATE_ENABLED as PLAN_VALIDATION_GATE_ENABLED_KEY,
    SETTINGS_EGRESS_GATE_MODE as EGRESS_GATE_MODE_KEY,
    SETTINGS_EGRESS_GATE_STRICT as EGRESS_GATE_STRICT_KEY,
    SETTINGS_MAX_TOOL_ITERATIONS as MAX_TOOL_ITERATIONS_KEY,
    SETTINGS_MAX_TURN_TOKENS as MAX_TURN_TOKENS_KEY,
    SETTINGS_LAYOUT_MASTHEAD_COLOR as LAYOUT_MASTHEAD_COLOR_KEY,
    SETTINGS_AUTO_OPEN_DOCK as AUTO_OPEN_DOCK_KEY,
    SETTINGS_LOCAL_DATA_ASK_ABOVE_MB as LOCAL_DATA_ASK_ABOVE_MB_KEY,
    provider_model_list_key,
)
AUTO_LABEL = "auto (recommended)"



def _extract_theme_palette():
    """Reads the live QGIS application's palette so this dialog's QSS follows
    whatever theme QGIS is actually running, matching dock_widget.py's own
    palette extraction. Duplicated in full rather than imported from
    dock_widget.py to keep this dialog importable/loadable independently of
    it -- both modules already require a real QGIS/PyQt process either way,
    so this costs nothing beyond a few duplicated lines."""
    from qgis.PyQt.QtGui import QPalette
    app = QApplication.instance()
    if app is None:
        return None
    p = app.palette()
    return {
        "window": p.color(QPalette.ColorRole.Window).name(),
        "alt_base": p.color(QPalette.ColorRole.AlternateBase).name(),
        "base": p.color(QPalette.ColorRole.Base).name(),
        "text": p.color(QPalette.ColorRole.WindowText).name(),
        "highlight": p.color(QPalette.ColorRole.Highlight).name(),
        "highlighted_text": p.color(QPalette.ColorRole.HighlightedText).name(),
        "muted_text": p.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText).name(),
        "mid": p.color(QPalette.ColorRole.Mid).name(),
    }

# Single source of truth for every provider's UI row and behavior. Adding a
# new provider means adding one entry here (plus a provider client + list_models
# function) -- not another block of near-duplicate widget code.
PROVIDERS = [
    {
        "value": "openrouter", "provider_label": "OpenRouter (Hosted)", "pill_label": "OpenRouter",
        "key_label": "OpenRouter API Key:", "model_label": "OpenRouter Model:",
        "model_setting_key": SETTINGS_OPENROUTER_MODEL, "default_model": AUTO_SENTINEL,
        "key_default": "", "list_fn": _list_openrouter,
        "key_placeholder": "sk-or-v1-...",
        "key_help_url": "https://openrouter.ai/keys",
        "key_tooltip": "OpenRouter has a genuinely free tier covering many models -- a good "
                        "default if you don't already have a key with another provider. Free "
                        "models may route to an upstream provider that trains on prompts -- "
                        "check your OpenRouter account's Privacy settings (separate toggles "
                        "for free vs. paid models) before sending sensitive data.",
        "dpa_url": "https://trust.openrouter.ai/",
        "dpa_label": "Data processing info (self-serve; a signed DPA needs Enterprise)",
    },
    {
        "value": "gemini", "provider_label": "Google Gemini (Hosted)", "pill_label": "Gemini",
        "key_label": "Gemini API Key:", "model_label": "Gemini Model:",
        # default_model is AUTO_SENTINEL (not a fixed model) so a fresh install
        # with nothing saved yet shows "Auto" pre-selected here, matching
        # agent_orchestrator.py's resolve_model default -- complexity-based routing out of
        # the box instead of always landing on the same fixed model.
        # safe_starting_model is still seeded into the dropdown as a concrete
        # option/hint, just not pre-selected.
        "model_setting_key": SETTINGS_GEMINI_MODEL, "default_model": AUTO_SENTINEL,
        "safe_starting_model": "gemini-flash-latest",
        # Google has no "-latest" alias for the Pro tier (unlike Flash). gemini-2.5-pro was
        # seeded here before but was removed after a live user hit a 404 "no longer
        # available to new users" on it, despite Google's own docs still listing it as
        # stable -- these snapshot IDs get gated off per-account ahead of doc removal, so
        # don't re-add a bare Pro snapshot ID here without live verification against an
        # actual key. gemini-3.1-pro-preview is the current confirmed-working Pro tier.
        "extra_seed_models": ["gemini-3.1-pro-preview"],
        "key_default": "", "list_fn": _list_gemini,
        "key_placeholder": "AIza...",
        "key_help_url": "https://aistudio.google.com/apikey",
        "key_tooltip": "On the free tier, Google may use your prompts to improve its products "
                        "(human reviewers can read them) -- enable billing on this key for "
                        "Google's paid-tier terms, which exclude prompts from training, before "
                        "sending sensitive data.",
        "dpa_url": "https://cloud.google.com/terms/data-processing-addendum",
        "dpa_label": "Data Processing Addendum (paid tier)",
    },
    {
        # Ollama stays pinned to a concrete default (no auto-routing) -- local
        # models aren't a cost concern, and complexity-based naming heuristics
        # don't translate to an arbitrary local model catalog.
        "value": "ollama", "provider_label": "Ollama (Local)", "pill_label": "Ollama · local",
        "key_label": "Ollama Endpoint URL:", "model_label": "Ollama Model:",
        "model_setting_key": SETTINGS_OLLAMA_MODEL, "default_model": "llama3.1",
        "key_default": "http://localhost:11434/v1/chat/completions", "list_fn": _list_ollama,
        "key_tooltip": "Runs fully locally -- no account or key needed. Leave this as the "
                        "default unless your Ollama server runs somewhere else.",
    },
    {
        "value": "openai", "provider_label": "OpenAI (Hosted)", "pill_label": "OpenAI",
        "key_label": "OpenAI API Key (paid):", "model_label": "OpenAI Model:",
        "model_setting_key": SETTINGS_OPENAI_MODEL, "default_model": AUTO_SENTINEL,
        "safe_starting_model": "gpt-5.6",
        "key_default": "", "list_fn": _list_openai,
        "key_placeholder": "sk-...",
        "key_help_url": "https://platform.openai.com/api-keys",
        "dpa_url": "https://openai.com/policies/data-processing-addendum/",
        "dpa_label": "Data Processing Addendum",
    },
    {
        "value": "claude", "provider_label": "Claude / Anthropic (Hosted)", "pill_label": "Claude",
        "key_label": "Claude API Key (paid):", "model_label": "Claude Model:",
        "model_setting_key": SETTINGS_CLAUDE_MODEL, "default_model": AUTO_SENTINEL,
        "safe_starting_model": "claude-opus-5",
        "key_default": "", "list_fn": _list_claude,
        "key_placeholder": "sk-ant-...",
        "key_help_url": "https://console.anthropic.com/settings/keys",
        "dpa_url": "https://support.claude.com/en/articles/7996862-how-do-i-view-and-sign-your-data-processing-addendum-dpa",
        "dpa_label": "Data Processing Addendum (auto-incorporated into Commercial ToS)",
    },
    {
        # Placed last, not first: docs/archive/PRO_TIER_BUILD_PLAN_2026-08-21.md item 1.3 suggests
        # making this the default on a fresh install, but no gateway is deployed at
        # providers/cartogen.py's GATEWAY_BASE_URL anywhere yet -- defaulting a fresh
        # install to a provider that can't resolve would break the out-of-the-box
        # experience. Reorder to first once a real gateway exists (see that doc's Phase 1).
        "value": "cartogen", "provider_label": "Cartogen AI (Hosted)", "pill_label": "Cartogen AI",
        "key_label": "Cartogen AI Key:", "model_label": "Cartogen AI Model:",
        "model_setting_key": SETTINGS_CARTOGEN_MODEL, "default_model": AUTO_SENTINEL,
        "safe_starting_model": _CARTOGEN_FALLBACK_MODELS[0],
        "key_default": "", "list_fn": _list_cartogen,
        "key_tooltip": "No hosted gateway is deployed yet -- this option isn't usable today.",
    },
]



class CartogenAiSettingsDialog(QDialog):
    # Fetching a model list hits the network -- must never block the UI thread
    # (a slow/unreachable endpoint would otherwise freeze the whole dialog, and
    # QGIS with it, for the full request timeout). The background thread in
    # _fetch_models emits this signal with the result; Qt auto-queues delivery
    # to _on_models_fetched on the main thread since the receiver (this dialog)
    # lives there -- same cross-thread pattern already used in dock_widget.py.
    modelsFetchedSignal = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cartogen AI — Settings")
        self.setMinimumWidth(420)
        self.settings = QgsSettings()
        self._key_edits = {}
        self._model_combos = {}
        self._cached_model_lists = {}
        self._fetching = set()
        self._provider_buttons = {}
        # A provider only ever enters this set after a real _on_models_fetched success in
        # THIS dialog session -- a saved key that has never been exercised this session is
        # "set", not "verified": this dialog has no way to know a key still works without
        # actually calling the provider, so the Keys section (see _rebuild_keys_summary)
        # deliberately shows two different words rather than claiming more than it knows.
        self._verified_providers = set()
        self.modelsFetchedSignal.connect(self._on_models_fetched)
        self.init_ui()

    def init_ui(self):
        from ...infrastructure.auth import CredentialManager

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

        account_row = QHBoxLayout()
        account_status = QLabel("Hosted Cartogen AI account")
        self.account_button = QPushButton("Manage account")
        self.account_button.clicked.connect(self._open_account_dialog)
        account_row.addWidget(account_status)
        account_row.addStretch(1)
        account_row.addWidget(self.account_button)
        layout.addLayout(account_row)

        # Visual design proposal, 2026-09-16 (adapted from Settings Window.pdf's option 1c):
        # one-glance status line -- which connection, which model, how many of the provider
        # keys that need one actually have one set. Kept honest rather than mirroring the
        # mockup's "N keys verified" literally: see _verified_providers's comment above for
        # why a freshly-opened dialog can only ever claim a key is "set", not "verified".
        # Directly useful given the FIRMS-key bug this replaces the neighbourhood of: this
        # line would have shown a count that didn't match what the user just typed, instead
        # of the dialog giving no feedback at all about whether a save actually took.
        self.masthead_label = QLabel()
        self.masthead_label.setWordWrap(True)
        self.masthead_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.masthead_label)

        layout.addWidget(self._section_header("01", "Where your prompts go"))

        current_provider = self.settings.value(PROVIDER_KEY, "openrouter")
        self._active_provider = current_provider if any(e["value"] == current_provider for e in PROVIDERS) else PROVIDERS[0]["value"]

        # Visual design proposal, 2026-09-16 (adapted from Settings Window.pdf's option 1c):
        # a row of pills instead of a QComboBox -- every connection (including Ollama's
        # "local" qualifier) is visible at once instead of hidden inside a closed dropdown.
        # REVERTED from FlowLayout back to a plain vertical QVBoxLayout, 2026-09-16: a real
        # live report ("the software completely freeze") right after this dialog's first real
        # interactive use with FlowLayout -- a custom QLayout subclass nested inside this
        # dialog's QScrollArea is a known way to trigger a resize feedback loop that pegs the
        # Qt event loop, and headless/offscreen testing (everything this was verified with
        # before shipping) doesn't reliably exercise real interactive resize/paint behavior the
        # way a live windowed session does. A plain QVBoxLayout can't overflow -- it was
        # already the working, freeze-free version -- so this trades the mockup's wrapping chip
        # row back for one pill per line rather than risk the same freeze again. See docs/
        # BUG_TRACKER.md if this is later revisited with a safer wrap approach.
        pills_col = QVBoxLayout()
        pills_col.setSpacing(4)
        self._provider_button_group = QButtonGroup(self)
        self._provider_button_group.setExclusive(True)
        for entry in PROVIDERS:
            pv = entry["value"]
            btn = QPushButton(entry["provider_label"])
            btn.setObjectName("providerPill")
            btn.setCheckable(True)
            btn.setChecked(pv == self._active_provider)
            btn.clicked.connect(lambda checked, p=pv: self._select_provider(p))
            self._provider_button_group.addButton(btn)
            self._provider_buttons[pv] = btn
            pills_col.addWidget(btn)
        layout.addLayout(pills_col)

        # GDPR review (docs/GDPR_COMPLIANCE_REVIEW.docx, 2026-09-01) finding F2: nothing
        # in the product told a user what happens to data once a cloud provider is picked.
        # Static, provider-agnostic -- each provider page below adds its own specifics
        # (dpa_url / key_tooltip) where they differ.
        privacy_note = QLabel(
            "Chat text and any layer/attribute data a tool call surfaces to the model are "
            "sent to whichever provider is selected above (Ollama excepted -- fully local, "
            "nothing leaves this machine). Each provider's Data Processing Addendum link "
            "below is a starting point, not a substitute for your organization's own GDPR "
            "review before processing real beneficiary data. See docs/USER_GUIDE.md and "
            "SECURITY.md's \"Data protection\" section."
        )
        privacy_note.setWordWrap(True)
        privacy_note.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(privacy_note)

        # One page per provider, holding just that provider's key/URL field and
        # model combo -- only the selected provider's page is ever shown, instead
        # of all providers' rows being present in one long form and merely
        # greyed out when not selected (the previous design).
        self.provider_stack = QStackedWidget()
        self._provider_page_index = {}
        for entry in PROVIDERS:
            pv = entry["value"]
            page = QWidget()
            page_form = QFormLayout(page)
            page_form.setContentsMargins(0, 2, 0, 2)

            key_edit = QLineEdit()
            if pv != "ollama":
                key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            saved_key = CredentialManager.get_credential(pv)
            key_edit.setText(saved_key if saved_key else entry["key_default"])
            key_edit.editingFinished.connect(lambda p=pv: self._fetch_models(p))
            # Live feedback for the Keys summary below (masked value + Set/Verified badge) --
            # not gated on editingFinished/blur like the model fetch above, so the summary
            # reflects what's actually typed even before the user tabs away or saves.
            key_edit.textChanged.connect(self._rebuild_keys_summary)
            # A user who has never used an LLM API before has no way to know
            # what belongs in this field or where to get it -- found in the UX
            # audit dated 2026-08-31 ("Settings gives no guidance on what an
            # API key is or where to get one, for any of the 5 providers").
            key_placeholder = entry.get("key_placeholder", "")
            if key_placeholder:
                key_edit.setPlaceholderText(key_placeholder)
            key_tooltip = entry.get("key_tooltip", "")
            if key_tooltip:
                key_edit.setToolTip(key_tooltip)
            page_form.addRow(entry["key_label"], key_edit)
            self._key_edits[pv] = key_edit

            key_help_url = entry.get("key_help_url")
            if key_help_url:
                help_label = QLabel(f'<a href="{key_help_url}">Get a key \u2192</a>')
                help_label.setOpenExternalLinks(True)
                help_label.setStyleSheet("color: gray; font-size: 11px;")
                page_form.addRow("", help_label)

            # GDPR review (docs/GDPR_COMPLIANCE_REVIEW.docx, 2026-09-01) finding F4: the
            # deploying org needs its own Data Processing Agreement with whichever cloud
            # provider it enables -- nothing in this codebase can provide or verify that on
            # the org's behalf, but not pointing at it at all left the org to discover the
            # need unprompted. Mirrors the key_help_url pattern above.
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

                try:
                    self._cached_model_lists[pv] = json.loads(cached_raw)
                except (TypeError, ValueError):
                    pass

            self._provider_page_index[pv] = self.provider_stack.addWidget(page)

        layout.addWidget(self.provider_stack)

        layout.addWidget(self._section_header("02", "Keys"))

        # Visual design proposal, 2026-09-16 (adapted from Settings Window.pdf's option 1b):
        # a compact, read-only summary of every credential -- masked value, and whether it's
        # set or verified -- with a "Replace"/"Add key" link that jumps to the real editable
        # field above (provider_stack's key_edit, or firms_key_edit below). This is the piece
        # that most directly targets the live-reported bug: the plain password-dot field gave
        # no confirmation a key had actually been typed or saved, so a save that silently
        # failed (the settings dialog being too tall to reach Save, in that report) looked
        # identical to one that worked. Rebuilt on every keystroke (_rebuild_keys_summary) and
        # after every model-fetch result, never edited in place.
        self.keys_summary_layout = QVBoxLayout()
        self.keys_summary_layout.setSpacing(0)
        layout.addLayout(self.keys_summary_layout)

        # NASA FIRMS active-fire monitoring (hazard_monitoring_tools.py) needs its own free API
        # key -- separate from any LLM provider key above, so it gets its own standalone field
        # rather than a page in provider_stack (it isn't an LLM connection choice). Stored/read
        # via the same CredentialManager every provider key above already uses, keyed by the
        # provider string "firms" -- CredentialManager.LEGACY_SETTINGS_KEYS falls back to
        # f"cartogen_ai/{provider}_key" for any provider not in its explicit mapping, so "firms"
        # works with zero changes needed there.
        firms_form = QFormLayout()
        self.firms_key_edit = QLineEdit()
        self.firms_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.firms_key_edit.setText(CredentialManager.get_credential("firms"))
        self.firms_key_edit.setPlaceholderText("Optional -- only needed for live active-fire monitoring")
        self.firms_key_edit.setToolTip(
            "Powers fetch_nasa_active_fires (NASA FIRMS active fire/thermal-anomaly detections). "
            "Leave blank if you don't need this -- every other tool works without it."
        )
        self.firms_key_edit.textChanged.connect(self._rebuild_keys_summary)
        firms_form.addRow("NASA FIRMS API Key:", self.firms_key_edit)
        layout.addLayout(firms_form)
        firms_help_label = QLabel('<a href="https://firms.modaps.eosdis.nasa.gov/api/area/">Get a free key →</a>')
        firms_help_label.setOpenExternalLinks(True)
        firms_help_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(firms_help_label)

        self._rebuild_keys_summary()

        layout.addWidget(self._section_header("03", "What gets kept and shown"))

        # S2: opt-in, default OFF -- chat history used to always be written
        # into the project (.qgz) file with no way to turn it off. A project
        # file is a shareable artifact (emailed, committed, uploaded), so
        # saving the conversation into it by default risked carrying
        # sensitive content (humanitarian incident/security details, internal
        # notes) along with the map without the user ever choosing that.
        self.auto_open_dock_checkbox = QCheckBox("Open the Cartogen AI panel when QGIS starts")
        self.auto_open_dock_checkbox.setChecked(bool(self.settings.value(AUTO_OPEN_DOCK_KEY, True, type=bool)))
        layout.addWidget(self.auto_open_dock_checkbox)

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
        layout.addWidget(self.persist_history_checkbox)

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
        layout.addWidget(self.persist_project_memory_checkbox)

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
        layout.addWidget(self.prompt_refinement_checkbox)

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
        layout.addWidget(self.prompt_preview_checkbox)

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
        layout.addWidget(self.project_inspector_checkbox)

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
        layout.addWidget(self.plan_validation_gate_checkbox)

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
        self.max_turn_tokens_spin.setValue(self._int_setting(MAX_TURN_TOKENS_KEY, 0, 0, 5_000_000))
        self.max_turn_tokens_spin.setToolTip(
            "Stops a request once the model calls in it have used this many tokens (input + output). "
            "0 = no limit. The chat footer shows what each request used, so you can pick a number from real use.")
        limits_form.addRow("Max tokens per request:", self.max_turn_tokens_spin)
        self.layout_masthead_edit = QLineEdit()
        self.layout_masthead_edit.setPlaceholderText("#1f2d3a (default slate)")
        self.layout_masthead_edit.setMaxLength(7)
        self.layout_masthead_edit.setText(str(self.settings.value(LAYOUT_MASTHEAD_COLOR_KEY, "") or ""))
        self.layout_masthead_edit.setToolTip(
            "Title-bar colour on exported print layouts, as #rrggbb. Empty or invalid = the default slate. "
            "Light colours automatically get dark title text.")
        limits_form.addRow("Print layout title colour:", self.layout_masthead_edit)
        self.local_data_ask_spin = QSpinBox()
        self.local_data_ask_spin.setRange(0, 100_000)
        self.local_data_ask_spin.setSuffix(" MB")
        self.local_data_ask_spin.setSpecialValueText("always ask")
        self.local_data_ask_spin.setValue(self._int_setting(LOCAL_DATA_ASK_ABOVE_MB_KEY, 50, 0, 100_000))
        self.local_data_ask_spin.setToolTip(
            "Downloads larger than this (or of unknown size, or on a metered connection) ask you first. "
            "Default 50 MB; 'always ask' asks for every download.")
        limits_form.addRow("Ask before downloads larger than:", self.local_data_ask_spin)
        layout.addLayout(limits_form)

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
        layout.addLayout(egress_form)

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
        layout.addWidget(egress_recommendation)

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
        layout.addWidget(self.egress_gate_strict_checkbox)

        layout.addWidget(self._section_header("04", "Who the assistant writes for"))

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

        self.fetch_status_label = QLabel("Model lists refresh automatically when you leave an API key field.")
        self.fetch_status_label.setObjectName("secondaryLabel")
        self.fetch_status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.fetch_status_label.setWordWrap(True)
        layout.addWidget(self.fetch_status_label)

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
QPushButton#providerPill {{
    padding: 5px 10px;
}}
QPushButton#providerPill:checked {{
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

        self.update_fields()

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

    def _select_provider(self, provider_value):
        self._active_provider = provider_value
        self.update_fields()

    def _open_account_dialog(self):
        from .account_dialog import CartogenAccountDialog
        dialog = CartogenAccountDialog(self)
        dialog.exec()

    def _open_onboarding_profile(self):
        from .onboarding_dialog import OnboardingDialog
        dialog = OnboardingDialog(self)
        dialog.exec()

    def update_fields(self):
        provider = self._active_provider
        page_index = self._provider_page_index.get(provider)
        if page_index is not None:
            self.provider_stack.setCurrentIndex(page_index)
        self._update_masthead()

    def _update_masthead(self):
        entry = next((e for e in PROVIDERS if e["value"] == self._active_provider), None)
        if entry is None:
            return
        model_text = self._model_combos[self._active_provider].currentText().strip() or AUTO_LABEL
        # Ollama excluded from the count: it's a local endpoint URL with a working default,
        # not a credential a user needs to go obtain -- counting it would make "N of 6" read
        # as if something were missing when nothing is.
        keyed_providers = [e["value"] for e in PROVIDERS if e["value"] != "ollama"]
        set_count = sum(1 for pv in keyed_providers if self._key_edits[pv].text().strip())
        self.masthead_label.setText(
            f"{entry['provider_label']} &middot; {model_text} model &middot; "
            f"{set_count} of {len(keyed_providers)} keys set &middot; "
            f'<a href="#" style="color:inherit;">Manage account →</a>'
        )

    def _rebuild_keys_summary(self):
        """Redraws the '02 Keys' summary from scratch against current field text -- cheap
        (6 rows, no network) so it can safely run on every keystroke. See its construction
        site in init_ui for what real bug this addresses."""
        if not hasattr(self, "keys_summary_layout"):
            return  # called via textChanged before init_ui has built this section yet
        while self.keys_summary_layout.count():
            item = self.keys_summary_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        rows = [(e["value"], e["provider_label"]) for e in PROVIDERS if e["value"] != "ollama"]
        rows.append(("firms", "NASA FIRMS"))
        for pv, label in rows:
            key_edit = self.firms_key_edit if pv == "firms" else self._key_edits[pv]
            value = key_edit.text().strip()
            self.keys_summary_layout.addWidget(self._build_key_row(pv, label, value))
        self._update_masthead()

    def _build_key_row(self, provider_value, label, value):
        row = QWidget()
        row.setObjectName("keyRow")
        # WA_StyledBackground: a plain QWidget ignores border/background from its own
        # stylesheet by default (a real Qt gotcha) -- needed for the dashed row divider
        # below (mockup's .key-row: border-bottom:1px dashed) to actually paint.
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row.setStyleSheet("QWidget#keyRow { border: none; border-bottom: 1px dashed palette(mid); }")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 6, 0, 6)
        row_layout.setSpacing(8)

        name_label = QLabel(label)
        name_label.setMinimumWidth(110)
        name_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        row_layout.addWidget(name_label)

        if value:
            masked = ("•••• " * 2 + value[-4:]) if len(value) > 4 else "•" * len(value)
            mask_label = QLabel(masked)
            mask_label.setStyleSheet("font-size: 11.5px; color: gray; font-family: monospace;")
            row_layout.addWidget(mask_label, 1)

            verified = provider_value in self._verified_providers
            status = QLabel("Verified" if verified else "Set")
            status.setStyleSheet(
                "font-size: 11px; font-weight: 700; color: %s;" % ("#1c7a4d" if verified else "gray")
            )
            row_layout.addWidget(status)

            replace_btn = QPushButton("Replace")
            replace_btn.setObjectName("linkButton")
            replace_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            replace_btn.clicked.connect(lambda: self._go_to_key(provider_value))
            row_layout.addWidget(replace_btn)
        else:
            row_layout.addWidget(QLabel(""), 1)
            unset_label = QLabel("not set")
            unset_label.setStyleSheet("font-size: 11px; color: gray;")
            row_layout.addWidget(unset_label)

            add_btn = QPushButton("Add key →")
            add_btn.setObjectName("linkButton")
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_btn.clicked.connect(lambda: self._go_to_key(provider_value))
            row_layout.addWidget(add_btn)

        return row

    def _go_to_key(self, provider_value):
        """A Keys-summary row's Replace/Add-key link jumps straight to the real editable
        field, rather than making the user hunt for which provider pill owns which key."""
        if provider_value == "firms":
            target = self.firms_key_edit
        else:
            btn = self._provider_buttons.get(provider_value)
            if btn is not None:
                btn.setChecked(True)
            self._select_provider(provider_value)
            target = self._key_edits[provider_value]
        target.setFocus()
        target.selectAll()

    def _fetch_models(self, provider_value):
        entry = next(e for e in PROVIDERS if e["value"] == provider_value)
        key_text = self._key_edits[provider_value].text().strip()
        if not key_text or provider_value in self._fetching:
            return

        self._fetching.add(provider_value)
        self.fetch_status_label.setText(f"Fetching {entry['provider_label']} models...")

        def worker():
            try:
                result = entry["list_fn"](key_text)
            except Exception as e:
                result = {"error": f"Unexpected error: {e}"}
            try:
                self.modelsFetchedSignal.emit(provider_value, result)
            except RuntimeError:
                pass  # dialog was closed/deleted before the fetch finished -- nothing to update

        threading.Thread(target=worker, daemon=True).start()

    def _on_models_fetched(self, provider_value, result):
        self._fetching.discard(provider_value)
        entry = next(e for e in PROVIDERS if e["value"] == provider_value)
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
            self._rebuild_keys_summary()
        else:
            self.fetch_status_label.setText(
                f"{entry['provider_label']} fetch failed: {result.get('error', 'unknown error')}"
            )

    def _resolve_model_value(self, provider_value):
        text = self._model_combos[provider_value].currentText().strip()
        if not text or text == AUTO_LABEL:
            return AUTO_SENTINEL
        return text

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
        from ...infrastructure.auth import CredentialManager
        provider = self._active_provider
        self.settings.setValue(PROVIDER_KEY, provider)
        self.settings.setValue(PERSIST_SETTING_KEY, self.persist_history_checkbox.isChecked())
        self.settings.setValue(PERSIST_PROJECT_MEMORY_KEY, self.persist_project_memory_checkbox.isChecked())
        self.settings.setValue(PROMPT_REFINEMENT_ENABLED_KEY, self.prompt_refinement_checkbox.isChecked())
        self.settings.setValue(PROMPT_PREVIEW_ENABLED_KEY, self.prompt_preview_checkbox.isChecked())
        self.settings.setValue(PROJECT_INSPECTOR_ENABLED_KEY, self.project_inspector_checkbox.isChecked())
        self.settings.setValue(PLAN_VALIDATION_GATE_ENABLED_KEY, self.plan_validation_gate_checkbox.isChecked())
        self.settings.setValue(MAX_TOOL_ITERATIONS_KEY, self.max_tool_iterations_spin.value())
        self.settings.setValue(MAX_TURN_TOKENS_KEY, self.max_turn_tokens_spin.value())
        self.settings.setValue(AUTO_OPEN_DOCK_KEY, self.auto_open_dock_checkbox.isChecked())
        self.settings.setValue(LAYOUT_MASTHEAD_COLOR_KEY, self.layout_masthead_edit.text().strip())
        self.settings.setValue(LOCAL_DATA_ASK_ABOVE_MB_KEY, self.local_data_ask_spin.value())
        self.settings.setValue(EGRESS_GATE_MODE_KEY, self.egress_gate_mode_combo.currentData())
        self.settings.setValue(EGRESS_GATE_STRICT_KEY, self.egress_gate_strict_checkbox.isChecked())
        self.settings.setValue(USER_PROFILE_KEY, self.user_profile_combo.currentData())

        # Product policy decision, 2026-09-20 (strict option chosen over an opt-in
        # plaintext-persist path): save_credential() has no way to write a new key to
        # disk in plaintext at all now -- session_only_entries only drives the
        # informational notice below, there is no consent prompt or plaintext-persist
        # call to make regardless of what the user chooses.
        session_only_entries = []
        for entry in PROVIDERS:
            pv = entry["value"]
            self.settings.setValue(entry["model_setting_key"], self._resolve_model_value(pv))
            if pv in self._cached_model_lists:
                self.settings.setValue(
                    provider_model_list_key(pv), json.dumps(self._cached_model_lists[pv])
                )

            key_text = self._key_edits[pv].text().strip()
            if key_text and CredentialManager.save_credential(pv, key_text) and CredentialManager.used_session_only_fallback(pv):
                session_only_entries.append(entry.get("provider_label", pv))

        firms_key_text = self.firms_key_edit.text().strip()
        if firms_key_text and CredentialManager.save_credential("firms", firms_key_text) and CredentialManager.used_session_only_fallback("firms"):
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
