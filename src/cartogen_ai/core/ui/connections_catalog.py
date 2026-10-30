"""The connections a user can choose between (hosted API, local, own CLI login) and how they are grouped.

Qt-free so it can be tested without QGIS. Moved out of settings_dialog.py when the connection settings got their own window
(PLAN-041); settings_dialog.py and connections_dialog.py both import from here, so there is one list."""
import contextlib  # noqa: F401  (kept: callers import names from here)

from ..model_selector import AUTO_SENTINEL
from ...infrastructure.providers.openrouter import list_models as _list_openrouter
from ...infrastructure.providers.gemini import list_models as _list_gemini
from ...infrastructure.providers.ollama import list_models as _list_ollama
from ...infrastructure.providers.openai import list_models as _list_openai
from ...infrastructure.providers.claude import list_models as _list_claude
from ...infrastructure.providers.cartogen import list_models as _list_cartogen, FALLBACK_MODELS as _CARTOGEN_FALLBACK_MODELS
from ...infrastructure.settings_keys import (
    ENABLED_PROVIDERS,
    SETTINGS_CLAUDE_CLI_MODEL,
    SETTINGS_CODEX_CLI_MODEL,
    SETTINGS_OPENROUTER_MODEL,
    SETTINGS_GEMINI_MODEL,
    SETTINGS_OLLAMA_MODEL,
    SETTINGS_OPENAI_MODEL,
    SETTINGS_CLAUDE_MODEL,
    SETTINGS_CARTOGEN_MODEL,
)

AUTO_LABEL = "auto (recommended)"




# Single source of truth for every provider's UI row and behavior. Adding a
# new provider means adding one entry here (plus a provider client + list_models
# function) -- not another block of near-duplicate widget code.
_ALL_PROVIDERS = [
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
        # gemini-3.8-flash is the model Google names as the replacement for the retired gemini-2.5-flash (2026-10-11). The Pro model
        # has no free-tier quota (limit 0): it needs billing enabled on the key's Google project.
        "extra_seed_models": ["gemini-3.8-flash", "gemini-3.1-pro-preview"],
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

# Only the providers this build enables (settings_keys.ENABLED_PROVIDERS); the rest stay defined above.
PROVIDERS = [e for e in _ALL_PROVIDERS if e["value"] in ENABLED_PROVIDERS]

# Experimental CLI bridge providers (PLAN-038). Not in ENABLED_PROVIDERS: each dialog adds them to its own list only while the user has
# switched on SETTINGS_EXPERIMENTAL_CLI (see CartogenAiSettingsDialog._providers). The "key" field holds the executable path and is
# stored as a plain setting ("key_storage": "setting"), not in the credential store: a path is not a secret.
_CLI_NOTE = (
    "Experimental and not yet verified against a real signed-in CLI. Runs the program below on this computer with your own login "
    "and sends the conversation, including any layer or attribute data a tool surfaces, to that vendor's service, so treat it as a "
    "cloud provider. Cartogen AI never sees or stores your login. Check that your plan's terms allow this use."
)
_CLI_PROVIDERS = [
    {
        "value": "claude_cli", "provider_label": "Claude Code CLI (experimental)", "pill_label": "Claude Code CLI",
        "key_label": "claude program:", "model_label": "Model (optional):",
        "model_setting_key": SETTINGS_CLAUDE_CLI_MODEL, "default_model": AUTO_SENTINEL,
        "extra_seed_models": ["sonnet", "opus", "haiku"],
        "key_default": "claude", "group": "cli", "list_fn": None, "key_storage": "setting", "page_note": _CLI_NOTE,
        "key_tooltip": "Name or full path of the claude program. Sign in once by running `claude` in a terminal. "
                        "Auto = the CLI's own default model.",
    },
    {
        "value": "codex_cli", "provider_label": "Codex CLI (experimental)", "pill_label": "Codex CLI",
        "key_label": "codex program:", "model_label": "Model (optional):",
        "model_setting_key": SETTINGS_CODEX_CLI_MODEL, "default_model": AUTO_SENTINEL,
        "key_default": "codex", "group": "cli", "list_fn": None, "key_storage": "setting", "page_note": _CLI_NOTE,
        "key_tooltip": "Name or full path of the codex program. Sign in once with `codex login`. Auto = the CLI's own default model.",
    },
]



# How the connection choices are grouped in the dialog (PLAN-039): what a user is choosing between is not "which vendor" but "where does my
# data go and what do I need to bring" -- a key, nothing, or a program already signed in on this computer.
_GROUP_OF = {"openrouter": "hosted", "gemini": "hosted", "openai": "hosted", "claude": "hosted", "cartogen": "hosted", "ollama": "local"}
_GROUP_TITLES = {
    "hosted": "Hosted -- your prompts go to the provider; you bring an API key",
    "local": "Local -- nothing leaves this machine",
    "cli": "Your own CLI login -- your prompts go to that vendor; you bring a signed-in program (experimental)",
}


def _group_of(entry):
    return entry.get("group") or _GROUP_OF.get(entry["value"], "hosted")
