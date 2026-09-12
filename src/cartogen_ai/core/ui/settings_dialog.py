import json
import threading

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QMessageBox, QApplication,
    QLineEdit, QComboBox, QFormLayout, QDialogButtonBox, QStackedWidget, QWidget, QCheckBox, QHBoxLayout, QPushButton
)
from qgis.core import QgsSettings

from ..agent.chat_persistence import PERSIST_SETTING_KEY
from ..agent.memory import PERSIST_PROJECT_MEMORY_KEY

from ..agent.model_selector import AUTO_SENTINEL
from ..agent.prompt_refiner import (
    PROFILE_LABELS, DEFAULT_PROFILE,
    PROMPT_REFINEMENT_ENABLED_KEY, PROMPT_PREVIEW_ENABLED_KEY, USER_PROFILE_KEY,
)
from ..agent.providers.openrouter import list_models as _list_openrouter
from ..agent.providers.gemini import list_models as _list_gemini
from ..agent.providers.ollama import list_models as _list_ollama
from ..agent.providers.openai import list_models as _list_openai
from ..agent.providers.claude import list_models as _list_claude
from ..agent.providers.cartogen import list_models as _list_cartogen, FALLBACK_MODELS as _CARTOGEN_FALLBACK_MODELS
from .chat_formatting import build_dock_stylesheet

PROVIDER_KEY = "cartogen_ai/provider"
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
        "value": "openrouter", "provider_label": "OpenRouter (Hosted)",
        "key_label": "OpenRouter API Key:", "model_label": "OpenRouter Model:",
        "model_setting_key": "cartogen_ai/openrouter_model", "default_model": AUTO_SENTINEL,
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
        "value": "gemini", "provider_label": "Google Gemini (Hosted)",
        "key_label": "Gemini API Key:", "model_label": "Gemini Model:",
        # default_model is AUTO_SENTINEL (not a fixed model) so a fresh install
        # with nothing saved yet shows "Auto" pre-selected here, matching
        # agent.py's resolve_model default -- complexity-based routing out of
        # the box instead of always landing on the same fixed model.
        # safe_starting_model is still seeded into the dropdown as a concrete
        # option/hint, just not pre-selected.
        "model_setting_key": "cartogen_ai/gemini_model", "default_model": AUTO_SENTINEL,
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
        "value": "ollama", "provider_label": "Ollama (Local)",
        "key_label": "Ollama Endpoint URL:", "model_label": "Ollama Model:",
        "model_setting_key": "cartogen_ai/ollama_model", "default_model": "llama3.1",
        "key_default": "http://localhost:11434/v1/chat/completions", "list_fn": _list_ollama,
        "key_tooltip": "Runs fully locally -- no account or key needed. Leave this as the "
                        "default unless your Ollama server runs somewhere else.",
    },
    {
        "value": "openai", "provider_label": "OpenAI (Hosted)",
        "key_label": "OpenAI API Key (paid):", "model_label": "OpenAI Model:",
        "model_setting_key": "cartogen_ai/openai_model", "default_model": AUTO_SENTINEL,
        "safe_starting_model": "gpt-5.6",
        "key_default": "", "list_fn": _list_openai,
        "key_placeholder": "sk-...",
        "key_help_url": "https://platform.openai.com/api-keys",
        "dpa_url": "https://openai.com/policies/data-processing-addendum/",
        "dpa_label": "Data Processing Addendum",
    },
    {
        "value": "claude", "provider_label": "Claude / Anthropic (Hosted)",
        "key_label": "Claude API Key (paid):", "model_label": "Claude Model:",
        "model_setting_key": "cartogen_ai/claude_model", "default_model": AUTO_SENTINEL,
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
        "value": "cartogen", "provider_label": "Cartogen AI (Hosted)",
        "key_label": "Cartogen AI Key:", "model_label": "Cartogen AI Model:",
        "model_setting_key": "cartogen_ai/cartogen_model", "default_model": AUTO_SENTINEL,
        "safe_starting_model": _CARTOGEN_FALLBACK_MODELS[0],
        "key_default": "", "list_fn": _list_cartogen,
        "key_tooltip": "No hosted gateway is deployed yet -- this option isn't usable in the "
                        "Community edition today (see docs/PRODUCT_TIERS.md).",
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
        self.modelsFetchedSignal.connect(self._on_models_fetched)
        self.init_ui()

    def init_ui(self):
        from ..agent.auth import CredentialManager

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        account_row = QHBoxLayout()
        account_status = QLabel("Hosted Cartogen AI account")
        self.account_button = QPushButton("Manage account")
        self.account_button.clicked.connect(self._open_account_dialog)
        account_row.addWidget(account_status)
        account_row.addStretch(1)
        account_row.addWidget(self.account_button)
        layout.addLayout(account_row)

        top_form = QFormLayout()
        self.provider_combo = QComboBox()
        for entry in PROVIDERS:
            self.provider_combo.addItem(entry["provider_label"], entry["value"])

        current_provider = self.settings.value(PROVIDER_KEY, "openrouter")
        index = self.provider_combo.findData(current_provider)
        if index >= 0:
            self.provider_combo.setCurrentIndex(index)
        top_form.addRow("Connection:", self.provider_combo)
        layout.addLayout(top_form)

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

            cached_raw = self.settings.value(f"cartogen_ai/{pv}_model_list", "")
            if cached_raw:
                try:
                    self._cached_model_lists[pv] = json.loads(cached_raw)
                except (TypeError, ValueError):
                    pass

            self._provider_page_index[pv] = self.provider_stack.addWidget(page)

        layout.addWidget(self.provider_stack)

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
        firms_form.addRow("NASA FIRMS API Key:", self.firms_key_edit)
        layout.addLayout(firms_form)
        firms_help_label = QLabel('<a href="https://firms.modaps.eosdis.nasa.gov/api/area/">Get a free key →</a>')
        firms_help_label.setOpenExternalLinks(True)
        firms_help_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(firms_help_label)

        # S2: opt-in, default OFF -- chat history used to always be written
        # into the project (.qgz) file with no way to turn it off. A project
        # file is a shareable artifact (emailed, committed, uploaded), so
        # saving the conversation into it by default risked carrying
        # sensitive content (humanitarian incident/security details, internal
        # notes) along with the map without the user ever choosing that.
        self.persist_history_checkbox = QCheckBox("Save chat history in the project file")
        self.persist_history_checkbox.setChecked(bool(self.settings.value(PERSIST_SETTING_KEY, False, type=bool)))
        self.persist_history_checkbox.setToolTip(
            "When on, the AI conversation is saved inside this project's .qgz file, so it's still there "
            "next time you open it. The project file may be shared, emailed, or committed elsewhere -- "
            "the conversation travels with it. Turning this off does not remove history already saved "
            "in a project from before this was disabled."
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

        self.fetch_status_label = QLabel("Model lists refresh automatically when you leave an API key field.")
        self.fetch_status_label.setObjectName("secondaryLabel")
        self.fetch_status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.fetch_status_label.setWordWrap(True)
        layout.addWidget(self.fetch_status_label)

        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.setStyleSheet(build_dock_stylesheet(_extract_theme_palette()))

        self.provider_combo.currentIndexChanged.connect(self.update_fields)
        self.update_fields()

    def _open_account_dialog(self):
        from .account_dialog import CartogenAccountDialog
        dialog = CartogenAccountDialog(self)
        dialog.exec()

    def update_fields(self):
        provider = self.provider_combo.currentData()
        page_index = self._provider_page_index.get(provider)
        if page_index is not None:
            self.provider_stack.setCurrentIndex(page_index)

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
        from ..agent.auth import CredentialManager
        provider = self.provider_combo.currentData()
        self.settings.setValue(PROVIDER_KEY, provider)
        self.settings.setValue(PERSIST_SETTING_KEY, self.persist_history_checkbox.isChecked())
        self.settings.setValue(PERSIST_PROJECT_MEMORY_KEY, self.persist_project_memory_checkbox.isChecked())
        self.settings.setValue(PROMPT_REFINEMENT_ENABLED_KEY, self.prompt_refinement_checkbox.isChecked())
        self.settings.setValue(PROMPT_PREVIEW_ENABLED_KEY, self.prompt_preview_checkbox.isChecked())
        self.settings.setValue(USER_PROFILE_KEY, self.user_profile_combo.currentData())

        fallback_providers = []
        for entry in PROVIDERS:
            pv = entry["value"]
            self.settings.setValue(entry["model_setting_key"], self._resolve_model_value(pv))
            if pv in self._cached_model_lists:
                self.settings.setValue(
                    f"cartogen_ai/{pv}_model_list", json.dumps(self._cached_model_lists[pv])
                )
            key_text = self._key_edits[pv].text().strip()
            if key_text and CredentialManager.save_credential(pv, key_text) and CredentialManager.used_plaintext_fallback(pv):
                fallback_providers.append(entry.get("provider_label", pv))

        firms_key_text = self.firms_key_edit.text().strip()
        if firms_key_text and CredentialManager.save_credential("firms", firms_key_text) and CredentialManager.used_plaintext_fallback("firms"):
            fallback_providers.append("NASA FIRMS")

        if fallback_providers:
            message = (
                "QGIS's encrypted credential store (QgsAuthManager) wasn't available, so the "
                "API key for " + ", ".join(fallback_providers) + " was saved in plain text "
                "instead. This still works, but the key isn't encrypted at rest."
            )
            diagnostic = CredentialManager.get_auth_system_diagnostic_message()
            if diagnostic:
                message += "\n\n" + diagnostic
            QMessageBox.warning(self, "Key stored without encryption", message)

        super().accept()
