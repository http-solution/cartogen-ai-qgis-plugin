# -*- coding: utf-8 -*-
"""
Centralized QgsSettings and QgsProject property keys for Cartogen AI.
Adheres to the standard 'cartogen_ai/' namespace to guarantee isolation
from other QGIS plugins and ensure consistent settings management.
"""

# Provider and Core Engine
SETTINGS_PROVIDER = "cartogen_ai/provider"
SETTINGS_API_KEY = "cartogen_ai/api_key"
SETTINGS_ACCOUNT_BASE_URL = "cartogen_ai/account_base_url"

# Provider-specific Model Configuration
SETTINGS_OPENROUTER_MODEL = "cartogen_ai/openrouter_model"
SETTINGS_GEMINI_MODEL = "cartogen_ai/gemini_model"
SETTINGS_OLLAMA_MODEL = "cartogen_ai/ollama_model"
SETTINGS_OPENAI_MODEL = "cartogen_ai/openai_model"
SETTINGS_CLAUDE_MODEL = "cartogen_ai/claude_model"
SETTINGS_CARTOGEN_MODEL = "cartogen_ai/cartogen_model"
SETTINGS_CARTOGEN_GATEWAY_URL = "cartogen_ai/cartogen_gateway_url"

# Persistence & State
SETTINGS_CHAT_HISTORY = "cartogen_ai/chat_history"
SETTINGS_PERSIST_CHAT_HISTORY = "cartogen_ai/persist_chat_history"
SETTINGS_GLOBAL_MEMORY = "cartogen_ai/global_memory"
SETTINGS_PERSIST_PROJECT_MEMORY = "cartogen_ai/persist_project_memory"
SETTINGS_ONBOARDING_COMPLETED = "cartogen_ai/onboarding_completed"
SETTINGS_HELP_LAST_SHOWN_VERSION = "cartogen_ai/help_last_shown_version"

# Cloud-provider egress gate (docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md) -- mode is
# "off" (default) / "warn" / "enforce"; strict additionally treats UNTAGGED layers as protected.
SETTINGS_EGRESS_GATE_MODE = "cartogen_ai/egress_gate_mode"
SETTINGS_EGRESS_GATE_STRICT = "cartogen_ai/egress_gate_strict"

# Prompt Refiner Settings
SETTINGS_PROMPT_REFINEMENT_ENABLED = "cartogen_ai/prompt_refinement_enabled"
SETTINGS_PROMPT_PREVIEW_ENABLED = "cartogen_ai/prompt_preview_enabled"

# Project Inspector snapshot (IMPLEMENTATION_TRACKER.md §1.5, option (b)) -- OFF by default. See
# core/services/project_inspector.py's module docstring for why this is feature-flagged
# separately from map_context.py's always-on summary.
SETTINGS_PROJECT_INSPECTOR_ENABLED = "cartogen_ai/project_inspector_enabled"

# Plan-validation gate (IMPLEMENTATION_TRACKER.md §1.6, option (b)) -- OFF by default. See
# core/models/plan_gate.py's module docstring for why this is feature-flagged rather than
# always-on: it's a real narrow experiment awaiting live-LLM evaluation, not a settled default.
SETTINGS_PLAN_VALIDATION_GATE_ENABLED = "cartogen_ai/plan_validation_gate_enabled"
SETTINGS_USER_PROFILE = "cartogen_ai/user_profile"
SETTINGS_PROMPT_REFINEMENT_MODEL = "cartogen_ai/prompt_refinement_model"

# Custom Project & Layer Properties (stored via QgsProject/QgsMapLayer custom properties)
PROJECT_PROPERTY_MEMORY = "cartogen_ai/project_memory"
PROJECT_PROPERTY_DATASET_STATUS = "cartogen_ai/dataset_status"
PROJECT_PROPERTY_LINEAGE = "cartogen_ai/lineage"
PROJECT_PROPERTY_SENSITIVITY = "cartogen_ai/sensitivity"
PROJECT_PROPERTY_CONFIDENCE = "cartogen_ai/confidence"
PROJECT_PROPERTY_FETCHED_AT = "cartogen_ai/fetched_at"

# Workflow Settings Prefixes
SETTINGS_WORKFLOW_PREFIX = "cartogen_ai/workflows/"
SETTINGS_WORKFLOW_RUNS_PREFIX = "cartogen_ai/workflow_runs/"


def auth_id_setting_key(provider: str) -> str:
    """Returns the QgsSettings key used to store the QgsAuthManager config ID."""
    return f"cartogen_ai/auth_id_{provider}"


def fallback_credential_key(provider: str) -> str:
    """Returns the plaintext fallback QgsSettings key for a given provider."""
    return f"cartogen_ai/{provider}_key"


def provider_model_list_key(provider: str) -> str:
    """Returns the QgsSettings key used to cache available models for a provider."""
    return f"cartogen_ai/{provider}_model_list"


def workflow_preset_key(preset_name: str) -> str:
    """Returns the QgsSettings key used for a saved workflow preset."""
    return f"cartogen_ai/workflows/{preset_name}"


def workflow_run_key(run_id: str) -> str:
    """Returns the QgsSettings key used for a specific workflow run record."""
    return f"cartogen_ai/workflow_runs/{run_id}"


# Kill-switch for running long network analyses on a worker thread (default on). If it ever
# misbehaves in the field, setting this to false in QGIS's advanced settings restores the old
# synchronous behaviour without a new release. See core/agent/tools/_background_processing.py.
SETTINGS_BACKGROUND_NETWORK_ANALYSIS = "cartogen_ai/network_analysis_in_background"

# Size in MB above which a Geofabrik extract is offered as a choice instead of downloaded silently
# (rc7 smoke test F22: a 103 MB extract was fetched with no question). Default 150 = the previous
# fixed threshold, so nothing changes until someone lowers it in QGIS's advanced settings.
SETTINGS_LOCAL_DATA_ASK_ABOVE_MB = "cartogen_ai/local_data_ask_above_mb"
