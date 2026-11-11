"""
Prompt Refinement Layer for Cartogen AI.
Optional, opt-in step that rewrites a raw chat message into two better-
specified candidates before it ever reaches agent.run() -- see
docs/archive/PROMPT_REFINEMENT_LAYER_SPEC.md for the full design.

Deliberately structured like model_selector.py: small pure functions plus
one thin API-calling function, no QGIS import anywhere in this module, so
should_refine()/build_refinement_messages()/parse_refinement_response() are
all directly unit-testable without QGIS. The one function that isn't pure
(refine(), which makes a real API call) still never touches QgsProject or
any tool -- it calls client.complete(messages, tools=None, ...), the same
method every provider client already implements, with no tools passed.
"""

import contextlib
import json

from .. import personas as _personas
from ..personas import selection as _selection

try:
    from qgis.core import QgsSettings
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# Owned here (not ui/settings_dialog.py) matching agent/chat_persistence.py's
# PERSIST_SETTING_KEY precedent: the module that actually consumes a setting
# owns its key and the QgsSettings read, rather than the UI file that merely
# exposes a checkbox/dropdown for it. PROMPT_REFINEMENT_MODEL_KEY has no
# reader yet -- spec explicitly scopes it as an advanced/optional override,
# "not required for v1"; a future caller should fall back to the same
# cheap-tier pick pick_model_for_complexity would choose for a "simple"
# query when it's unset.
from ..logger import log_warning
from ...infrastructure.settings_keys import (
    SETTINGS_PROMPT_REFINEMENT_ENABLED as PROMPT_REFINEMENT_ENABLED_KEY,
    SETTINGS_PROMPT_PREVIEW_ENABLED as PROMPT_PREVIEW_ENABLED_KEY,
)
from ..logger import log_event

# Word-count boundary below which a message is already unambiguous enough
# that refining it would just add latency and a cheap-model-call cost for no
# benefit ("list layers", "zoom to X", "undo that"). Same "deterministic
# heuristic, not ML" honesty as model_selector.classify_complexity(), applied
# to a different decision (whether to refine at all, not which model to use).
_MIN_WORDS_TO_REFINE = 6

# PLAN-023 R1-2: the persona pack (core/personas/*.json) is the one list of personas; these two dicts are views of it, kept under their old names because the settings dialog and the tests use them.
PROFILE_LABELS = {pid: persona["label"] for pid, persona in _personas.load_all().items()}
PROFILE_GUIDANCE = {pid: persona["guidance"] for pid, persona in _personas.load_all().items()}
DEFAULT_PROFILE = _selection.DEFAULT_PERSONA

_DEFAULT_REFINEMENT_MAX_TOKENS = 400


def is_refinement_enabled() -> bool:
    """Opt-in, default OFF -- see docs/archive/PROMPT_REFINEMENT_LAYER_SPEC.md §8's
    honest cost tradeoff for why. Mirrors chat_persistence.is_persist_enabled()'s
    exact shape (QGIS_AVAILABLE guard, never raises)."""
    if not QGIS_AVAILABLE:
        return False
    try:
        return bool(QgsSettings().value(PROMPT_REFINEMENT_ENABLED_KEY, False, type=bool))
    except Exception:
        return False


def is_prompt_preview_enabled() -> bool:
    """Whether to show the composed prompt before sending it. Default True --
    see PROMPT_PREVIEW_ENABLED_KEY. Outside QGIS there is no settings store and
    no UI to show it in, so False."""
    if not QGIS_AVAILABLE:
        return False
    try:
        return bool(QgsSettings().value(PROMPT_PREVIEW_ENABLED_KEY, True, type=bool))
    except Exception:
        return True


def _onboarding_role():
    """The role key of a finished onboarding, or None. Only used to choose a default persona the first time; never raises."""
    with contextlib.suppress(Exception):
        from ..agent.onboarding_profile import load_onboarding_profile
        profile = load_onboarding_profile()
        return profile["role"] if profile else None
    return None


def get_persona_selection() -> tuple:
    """(primary, secondary) persona ids. The first read migrates the old stored choice (or the onboarding role) into persona_primary; see core/personas/selection.py. Reads as the defaults
    outside QGIS or when the store fails (the failure is logged)."""
    if not QGIS_AVAILABLE:
        return DEFAULT_PROFILE, ""
    try:
        return _selection.read_selection(QgsSettings(), _onboarding_role())
    except Exception as e:
        log_event("persona_selection_failed", tag="Personas", error_class=type(e).__name__, error=True)
        return DEFAULT_PROFILE, ""


def get_user_profile() -> str:
    """The primary persona id (the refinement persona of old)."""
    return get_persona_selection()[0]


def get_secondary_persona() -> str:
    """The secondary persona id, or '' for none (R1-4 ranks its tools at half weight)."""
    return get_persona_selection()[1]


def should_refine(query: str, enabled: bool) -> bool:
    """False for: disabled, empty/whitespace-only query, or a query short
    enough (<_MIN_WORDS_TO_REFINE words) that it's already unambiguous."""
    if not enabled or not query or not query.strip():
        return False
    return len(query.split()) >= _MIN_WORDS_TO_REFINE


def build_refinement_messages(query: str, profile: str) -> list:
    """Short, dedicated system message -- NOT build_system_prompt() (a much
    larger prompt, see docs/archive/API_COST_OPTIMIZATION_REVIEW.md §0 for a
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


def parse_refinement_response(raw_content) -> dict | None:
    """Defensive parsing matching agent_orchestrator.py's _real_execute_tool pattern
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
        log_event("refinement_call_failed", tag="PromptRefiner", error_class=type(e).__name__, error=True)
        return {"error": str(e)}

    if not isinstance(result, dict) or "error" in result:
        err = result.get("error") if isinstance(result, dict) else "unexpected response shape"
        log_event("refinement_call_returned_an_error", tag="PromptRefiner", error=True)
        return {"error": err}

    message = result.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    parsed = parse_refinement_response(content)
    if parsed is None:
        log_warning("refinement response was not valid/complete JSON", tag="PromptRefiner")
        return {"error": "invalid refinement response"}

    return parsed


# --------------------------------------------------------------------------
# Task-register integration (Humanitarian Mapping Task Register, 791 tasks).
#
# Added alongside refine() rather than inside it: refine() is exercised by an
# existing test suite and by dock_widget.send_message, and its contract must
# not change. analyze_request() is the new entry point; callers that do not
# use it see no behavioural difference at all.
#
# Stage 1 is local (task_matcher, no API call). Stage 2 -- the disambiguation
# call -- is only worth making when stage 1 reports ambiguous, and remains the
# caller's decision, because only the caller knows whether a client is
# available and whether the user has refinement switched on.
# --------------------------------------------------------------------------

def _empty_analysis(query):
    """The shape analyze_request() returns when nothing matched or something
    went wrong. Same keys every time, so no caller needs a `.get` guard on the
    happy path -- and `user_message` is the untouched query, so sending it is
    exactly today's behaviour."""
    text = (query or "").strip()
    return {"task": None, "score": 0.0, "ambiguous": False, "missing": [],
            "unresolved": [], "defaults": {}, "question": "",
            "directive": "", "contract": None, "blocking": False, "attachments": [],
            "user_message": text, "optimum_prompt": text,
            "reasoning": [], "expected_output": ""}


def compose_optimum_prompt(user_message, directive):
    """Exactly what the model will receive, as one reviewable block.

    Two pieces, both real: the user turn as it will be sent, and the addendum
    that is added to the system prompt (agent/prompts._format_map_context
    renders it under REGISTERED TASK CONTEXT). Showing anything the model will
    not see, or hiding anything it will, would make the preview a decoration
    rather than a disclosure -- so this function does no formatting beyond
    labelling the two parts.
    """
    if not directive:
        return user_message
    return (f"Message sent as you:\n{user_message}\n\n"
            f"Added to the system prompt:\n{directive}")


def analyze_request(query, context=None, attachments=None):
    """Local, offline analysis of a request against the task register.

    Returns, and never raises:
        {
          "task":       entry | None,      matched register task
          "score":      float,
          "ambiguous":  bool,              True -> a stage-2 call is worthwhile
          "missing":    [slot, ...],       still unanswered
          "unresolved": [slot, ...],       missing AND unsafe to default
          "defaults":   {slot: value},     what would be assumed
          "question":   str,               the single consolidated ask ("" if none)
          "directive":  str,               inject into the prompt
          "contract":   {...} | None,      what to do with the response
          "attachments":    [ {...}, ... ],  what each attached file will become
          "user_message":   str,            the exact user turn that will be sent
          "optimum_prompt": str,            user turn + system addendum, verbatim
          "reasoning":      [str, ...],     why it is being sent that way
          "expected_output": str,           the artifact the user will get
        }

    `attachments` is a list of file paths the user has attached. Each is
    classified by agent/file_io and reported back -- a PDF, a picture and a
    text file each take a different route into the same answer, and the user
    is told which.

    `context` is whatever the host already knows, e.g. what QGIS can answer
    without asking: {"aoi": "current canvas extent", "admin_level": "admin2"}.
    """
    try:
        from ..agent import task_matcher as tmatch
        from ..agent import task_register as reg_module
    except Exception as e:  # pragma: no cover - diagnostic path
        log_event("task_register_unavailable", tag="PromptRefiner", error_class=type(e).__name__, error=True)
        return _empty_analysis(query)

    try:
        verdict = tmatch.classify(query, personas=get_persona_selection())
        # `ambiguous` means the local match is below the confidence floor, or
        # tied across sections -- the register's own signal that a second
        # (stage-2) opinion is warranted before trusting it. That stage-2 call
        # is not wired up anywhere in this codebase (build_disambiguation_messages/
        # parse_disambiguation_response are defined but never invoked), so
        # until it is, an ambiguous match must NOT be used to build a task
        # directive -- doing so silently pressures the model into a wrong
        # deliverable/tool-order for the turn (confirmed live, 2026-09-16: a
        # 0.12-confidence match routed "only create the layer, do not add
        # styling yet" to a satellite-orthophoto print-layout task, and a
        # 0.33-confidence match routed "apply a color ramp to the raster
        # layer" to an unrelated HDX/3W CSV-export task; the model then
        # answered the WRONG task convincingly, and later nagged the user for
        # a deliverable -- e.g. a CSV -- they never actually asked for).
        # Falling back to `entry = None` here reuses the exact same "nothing
        # matched" path the register already has for a genuinely unmatched
        # query: no directive, no contract, message sent as typed.
        #
        # Only the "below confidence floor" reason is treated this way. The
        # other ambiguous reason, "tie across sections", fires even when the
        # top score clears the floor by a healthy margin -- e.g. "build me a
        # dashboard of displacement by district" scores 0.38 (well above the
        # 0.34 floor) and is obviously the right match, but still gets flagged
        # ambiguous because a much weaker match (0.33) in a different section
        # happens to sit within AMBIGUITY_MARGIN. Nulling out entry for that
        # case throws away good matches, not just bad ones -- so leave that
        # branch's `entry` untouched pending an actual stage-2 tie-break.
        entry = None if verdict["ambiguous"] and verdict["reason"] == "below confidence floor" \
            else verdict["best"]
        # `context` is whatever the host has: either explicit slot values, or
        # the raw map summary from agent/map_context. Translate the latter into
        # slot answers so the user is never asked for something QGIS already
        # knows; explicit values win over anything inferred from the project.
        slot_ctx = dict(tmatch.slot_context_from_map(context))
        if isinstance(context, dict):
            slot_ctx.update({k: v for k, v in context.items()
                             if k in reg_module.SLOT_QUESTIONS and v})
        layer_names = ([entry_.get("name") for entry_ in context.get("layers") or [] if isinstance(entry_, dict)]
                       if isinstance(context, dict) and "layers" in context else None)
        missing = tmatch.missing_slots(entry, query, slot_ctx, layer_names)
        filled = tmatch.defaults(missing, entry)
        plan = tmatch.attachment_plan(entry, attachments)
        directive = tmatch.task_directive(entry, filled, query)
        with contextlib.suppress(Exception):  # a request that names three or more distinct steps is a workflow: one matched task would mislead it
            from ..agent import capabilities
            if capabilities.is_multi_step(query):
                directive = capabilities.workflow_directive(query)
        user_message = tmatch.compose_user_message(query, filled, plan)
        return {
            "task":       entry,
            "score":      verdict["score"],
            "ambiguous":  verdict["ambiguous"],
            "missing":    missing,
            "unresolved": tmatch.unresolvable(missing),
            "blocking":   bool(tmatch.unresolvable(missing)),
            "defaults":   filled,
            "question":   tmatch.clarify_question(entry, missing),
            "directive":  directive,
            "contract":   tmatch.output_contract(entry, query),
            "attachments":     plan,
            "user_message":    user_message,
            "optimum_prompt":  compose_optimum_prompt(user_message, directive),
            "reasoning":       tmatch.reasoning(entry, verdict["score"], filled, plan, query),
            "expected_output": tmatch.expected_output(entry, query),
        }
    except Exception as e:  # pragma: no cover - never break the send path
        log_event("analyze_request_failed", tag="PromptRefiner", error_class=type(e).__name__, error=True)
        return _empty_analysis(query)


def build_disambiguation_messages(query, candidates):
    """Stage 2: only for when analyze_request() reported ambiguous.

    Sends just the shortlisted task ids and labels -- never the register, which
    is ~40 KB and would dwarf every other prompt this plugin sends.
    """
    listing = "; ".join("{} = {}".format(e["id"], e["text"]) for e, _ in candidates[:5])
    system = (
        "Pick which task the user means. Candidates: " + listing + ". "
        'Respond as JSON only: {"task_id": "..."} using exactly one of the ids above, '
        'or {"task_id": null} if none fit.'
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": query}]


def parse_disambiguation_response(raw_content):
    """Task id from a stage-2 response, or None. Never raises."""
    try:
        data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tid = data.get("task_id")
    return tid if isinstance(tid, str) and tid else None
