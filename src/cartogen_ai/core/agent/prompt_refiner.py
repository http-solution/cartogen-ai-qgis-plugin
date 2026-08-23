# -*- coding: utf-8 -*-
"""
Prompt Refinement Layer for Cartogen AI.
Optional, opt-in step that rewrites a raw chat message into two better-
specified candidates before it ever reaches agent.run() -- see
docs/PROMPT_REFINEMENT_LAYER_SPEC.md for the full design.

Deliberately structured like model_selector.py: small pure functions plus
one thin API-calling function, no QGIS import anywhere in this module, so
should_refine()/build_refinement_messages()/parse_refinement_response() are
all directly unit-testable without QGIS. The one function that isn't pure
(refine(), which makes a real API call) still never touches QgsProject or
any tool -- it calls client.complete(messages, tools=None, ...), the same
method every provider client already implements, with no tools passed.
"""

import json

try:
    from qgis.core import QgsSettings
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# Word-count boundary below which a message is already unambiguous enough
# that refining it would just add latency and a cheap-model-call cost for no
# benefit ("list layers", "zoom to X", "undo that"). Same "deterministic
# heuristic, not ML" honesty as model_selector.classify_complexity(), applied
# to a different decision (whether to refine at all, not which model to use).
_MIN_WORDS_TO_REFINE = 6

PROFILE_LABELS = {
    "general": "GIS Generalist",
    "humanitarian": "Humanitarian Aid / Crisis Response",
    "engineering": "Engineering / Infrastructure",
    "urban_planning": "Urban Planning / Local Government",
    "logistics": "Logistics / Supply Chain",
    "agriculture": "Agriculture / Food Security",
    "environment": "Environment / Natural Resources",
    "public_health": "Public Health / Epidemiology",
    "disaster_risk": "Disaster Risk / Climate Resilience",
    "utilities": "Utilities / Energy / Water",
    "transport": "Transport / Mobility",
    "public_safety": "Public Safety / Security",
    "research": "Research / Academia",
    "real_estate": "Real Estate / Site Selection",
    "defense_intel": "Defense / Intelligence",
}
DEFAULT_PROFILE = "general"

PROFILE_GUIDANCE = {
    "general": "Use clear GIS terminology and ask for the target layer, coordinate system, output, and validation steps when they are ambiguous.",
    "humanitarian": "Prioritize affected populations, administrative levels, 3W/4W presence, needs/severity, protection, do-no-harm handling, data provenance, uncertainty, and decision-ready map outputs.",
    "engineering": "Prioritize survey accuracy, coordinate reference systems, construction phases, asset condition, constraints, measurements, QA checks, and deliverables suitable for engineering review.",
    "urban_planning": "Prioritize parcels, zoning, land use, accessibility, service catchments, population, development scenarios, planning constraints, and stakeholder-readable outputs.",
    "logistics": "Prioritize origins/destinations, network accessibility, travel cost, hub-and-spoke coverage, route constraints, service levels, fleet assumptions, and operational map outputs.",
    "agriculture": "Prioritize fields, crop/soil conditions, vegetation indices, irrigation, seasonal comparisons, yield proxies, and uncertainty in remote-sensing interpretation.",
    "environment": "Prioritize habitat, land cover, protected areas, watersheds, pollution/exposure, change detection, conservation constraints, and reproducible evidence.",
    "public_health": "Prioritize privacy, aggregation, catchment areas, accessibility, exposure, service coverage, temporal trends, and safe handling of sensitive locations.",
    "disaster_risk": "Prioritize hazard, exposure, vulnerability, scenario assumptions, evacuation/access constraints, time sensitivity, and uncertainty-aware decision products.",
    "utilities": "Prioritize network assets, service areas, outages, maintenance priority, dependencies, reliability, and field-verifiable asset records.",
    "transport": "Prioritize network topology, travel time, accessibility, demand locations, mode assumptions, bottlenecks, safety, and route alternatives.",
    "public_safety": "Prioritize lawful data handling, aggregation, incident trends, response coverage, route safety, uncertainty, and avoidance of sensitive-person identification.",
    "research": "Prioritize reproducibility, documented methods, source citations, assumptions, parameterization, uncertainty, and exportable analytical outputs.",
    "real_estate": "Prioritize site constraints, proximity, accessibility, demographics, market context, scenario comparison, and auditable decision criteria.",
    "defense_intel": "Prioritize provenance, uncertainty, temporal context, access controls, lawful use, and explicit separation of observation from inference.",
}

_DEFAULT_REFINEMENT_MAX_TOKENS = 400

# Owned here (not ui/settings_dialog.py) matching agent/chat_persistence.py's
# PERSIST_SETTING_KEY precedent: the module that actually consumes a setting
# owns its key and the QgsSettings read, rather than the UI file that merely
# exposes a checkbox/dropdown for it. PROMPT_REFINEMENT_MODEL_KEY has no
# reader yet -- spec explicitly scopes it as an advanced/optional override,
# "not required for v1"; a future caller should fall back to the same
# cheap-tier pick pick_model_for_complexity would choose for a "simple"
# query when it's unset.
PROMPT_REFINEMENT_ENABLED_KEY = "cartogen_ai/prompt_refinement_enabled"
USER_PROFILE_KEY = "cartogen_ai/user_profile"
PROMPT_REFINEMENT_MODEL_KEY = "cartogen_ai/prompt_refinement_model"


def is_refinement_enabled() -> bool:
    """Opt-in, default OFF -- see docs/PROMPT_REFINEMENT_LAYER_SPEC.md §8's
    honest cost tradeoff for why. Mirrors chat_persistence.is_persist_enabled()'s
    exact shape (QGIS_AVAILABLE guard, never raises)."""
    if not QGIS_AVAILABLE:
        return False
    try:
        return bool(QgsSettings().value(PROMPT_REFINEMENT_ENABLED_KEY, False, type=bool))
    except Exception:
        return False


def get_user_profile() -> str:
    if not QGIS_AVAILABLE:
        return DEFAULT_PROFILE
    try:
        return QgsSettings().value(USER_PROFILE_KEY, DEFAULT_PROFILE) or DEFAULT_PROFILE
    except Exception:
        return DEFAULT_PROFILE


def should_refine(query: str, enabled: bool) -> bool:
    """False for: disabled, empty/whitespace-only query, or a query short
    enough (<_MIN_WORDS_TO_REFINE words) that it's already unambiguous."""
    if not enabled or not query or not query.strip():
        return False
    return len(query.split()) >= _MIN_WORDS_TO_REFINE


def build_refinement_messages(query: str, profile: str) -> list:
    """Short, dedicated system message -- NOT build_system_prompt() (a much
    larger prompt, see docs/API_COST_OPTIMIZATION_REVIEW.md §0 for a
    point-in-time size measurement; check len(BASE_SYSTEM_PROMPT) directly
    for the current figure rather than trusting a hardcoded number here, it
    drifts with every rule added to agent/prompts.py). Also skips the task/
    memory/map context build_system_prompt() includes, which this call
    doesn't need. Kept under ~500 characters per spec §5.2."""
    label = PROFILE_LABELS.get(profile, PROFILE_LABELS[DEFAULT_PROFILE])
    guidance = PROFILE_GUIDANCE.get(profile, PROFILE_GUIDANCE[DEFAULT_PROFILE])
    system = (
        f"You rewrite a QGIS user's request into two improved versions, without changing "
        f"what they're asking for. Persona: {label}. Sector guidance: {guidance} Recommendation A ('Clarified') fixes "
        f"genuine ambiguity while staying close to the original wording. Recommendation B "
        f"('Visualization-forward') makes explicit which QGIS output/visualization/export "
        f"the request implies. Respond as JSON only, no other text: "
        f'{{"detected_profile": "...", "recommendations": ['
        f'{{"id": "A", "label": "Clarified", "refined_prompt": "...", "rationale": "..."}}, '
        f'{{"id": "B", "label": "Visualization-forward", "refined_prompt": "...", "rationale": "..."}}]}}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]


def parse_refinement_response(raw_content) -> dict:
    """Defensive parsing matching agent.py's _real_execute_tool pattern
    (json.loads wrapped in try/except, degrading rather than raising).
    Returns None for anything that isn't a complete, well-shaped response --
    that's the single signal the caller (dock_widget.py's send_message)
    checks to fall through to sending the original text unmodified. Never
    raises."""
    try:
        data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    except (TypeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    recommendations = data.get("recommendations")
    if not isinstance(recommendations, list) or len(recommendations) != 2:
        return None

    for rec in recommendations:
        if not isinstance(rec, dict) or not rec.get("refined_prompt"):
            return None

    return data


def refine(query: str, profile: str, client, max_tokens: int = _DEFAULT_REFINEMENT_MAX_TOKENS) -> dict:
    """Runs the refinement call and returns the parsed recommendations dict,
    or {"error": ...} on any failure (API error, malformed response) --
    never raises. tools=None guarantees this call can't enter
    ToolRouter/TOOLS_SCHEMA territory or trigger a tool call."""
    messages = build_refinement_messages(query, profile)
    try:
        result = client.complete(messages, tools=None, max_tokens=max_tokens)
    except Exception as e:
        print(f"[PromptRefiner] refinement call failed: {e}")
        return {"error": str(e)}

    if not isinstance(result, dict) or "error" in result:
        err = result.get("error") if isinstance(result, dict) else "unexpected response shape"
        print(f"[PromptRefiner] refinement call returned an error: {err}")
        return {"error": err}

    message = result.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    parsed = parse_refinement_response(content)
    if parsed is None:
        print("[PromptRefiner] refinement response was not valid/complete JSON")
        return {"error": "invalid refinement response"}

    return parsed
