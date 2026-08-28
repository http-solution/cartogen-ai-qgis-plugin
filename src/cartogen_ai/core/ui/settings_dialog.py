import json
import threading

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QMessageBox, QApplication,
    QLineEdit, QComboBox, QFormLayout, QDialogButtonBox, QStackedWidget, QWidget, QCheckBox, QHBoxLayout, QPushButton
)
from qgis.core import QgsSettings

from ..agent.chat_persistence import PERSIST_SETTING_KEY

from ..agent.model_selector import AUTO_SENTINEL
from ..agent.prompt_refiner import (
    PROFILE_LABELS, DEFAULT_PROFILE,
    PROMPT_REFINEMENT_ENABLED_KEY, USER_PROFILE_KEY,
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
        "window": p.color(QPalette.Window).name(),
        "alt_base": p.color(QPalette.AlternateBase).name(),
        "base": p.color(QPalette.Base).name(),
        "text": p.color(QPalette.WindowText).name(),
        "highlight": p.color(QPalette.Highlight).name(),
        "highlighted_text": p.color(QPalette.HighlightedText).name(),
        "muted_text": p.color(QPalette.Disabled, QPalette.WindowText).name(),
        "mid": p.color(QPalette.Mid).name(),
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
    },
    {
        # Ollama stays pinned to a concrete default (no auto-routing) -- local
        # models aren't a cost concern, and complexity-based naming heuristics
        # don't translate to an arbitrary local model catalog.
        "value": "ollama", "provider_label": "Ollama (Local)",
        "key_label": "Ollama Endpoint URL:", "model_label": "Ollama Model:",
        "model_setting_key": "cartogen_ai/ollama_model", "default_model": "llama3.1",
        "key_default": "http://localhost:11434/v1/chat/completions", "list_fn": _list_ollama,
    },
    {
        "value": "openai", "provider_label": "OpenAI (Hosted)",
        "key_label": "OpenAI API Key (paid):", "model_label": "OpenAI Model:",
        "model_setting_key": "cartogen_ai/openai_model", "default_model": AUTO_SENTINEL,
        "safe_starting_model": "gpt-5.6",
        "key_default": "", "list_fn": _list_openai,
    },
    {
        "value": "claude", "provider_label": "Claude / Anthropic (Hosted)",
        "key_label": "Claude API Key (paid):", "model_label": "Claude Model:",
        "model_setting_key": "cartogen_ai/claude_model", "default_model": AUTO_SENTINEL,
        "safe_starting_model": "claude-opus-5",
        "key_default": "", "list_fn": _list_claude,
    },
    {
        # Placed last, not first: docs/PRO_TIER_BUILD_PLAN_2026-08-21.md item 1.3 suggests
        # making this the default on a fresh install, but no gateway is deployed at
        # providers/cartogen.py's GATEWAY_BASE_URL anywhere yet -- defaulting a fresh
        # install to a provider that can't resolve would break the out-of-the-box
        # experience. Reorder to first once a real gateway exists (see that doc's Phase 1).
        "value": "cartogen", "provider_label": "Cartogen AI (Hosted)",
        "key_label": "Cartogen AI Key:", "model_label": "Cartogen AI Model:",
        "model_setting_key": "cartogen_ai/cartogen_model", "default_model": AUTO_SENTINEL,
        "safe_starting_model": _CARTOGEN_FALLBACK_MODELS[0],
        "key_default": "", "list_fn": _list_cartogen,
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
                key_edit.setEchoMode(QLineEdit.Password)
            saved_key = CredentialManager.get_credential(pv)
            key_edit.setText(saved_key if saved_key else entry["key_default"])
            key_edit.editingFinished.connect(lambda p=pv: self._fetch_models(p))
            page_form.addRow(entry["key_label"], key_edit)
            self._key_edits[pv] = key_edit

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

        # Roadmap feature per docs/PROMPT_REFINEMENT_LAYER_SPEC.md -- opt-in,
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
            "docs/API_COST_OPTIMIZATION_REVIEW.md and docs/PROMPT_REFINEMENT_LAYER_SPEC.md §8)."
        )
        layout.addWidget(self.prompt_refinement_checkbox)

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
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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
        self.settings.setValue(PROMPT_REFINEMENT_ENABLED_KEY, self.prompt_refinement_checkbox.isChecked())
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

        if fallback_providers:
            QMessageBox.warning(
                self,
                "Key stored without encryption",
                "QGIS's encrypted credential store (QgsAuthManager) wasn't available, so the "
                "API key for " + ", ".join(fallback_providers) + " was saved in plain text "
                "instead. This still works, but the key isn't encrypted at rest.",
            )

        super().accept()
