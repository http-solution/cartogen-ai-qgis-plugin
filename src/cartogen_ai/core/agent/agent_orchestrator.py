# -*- coding: utf-8 -*-
"""
Core CartogenAi class for Cartogen AI: the tool-calling orchestration loop.
Integrates Multi-LLM provider clients, Spatial Memory Engine, and Task List Manager.
Thread-safe tool dispatching, session usage tracking, and conversation history
management live in their own files now (tool_dispatcher.py, usage_tracker.py,
history_manager.py -- extracted 2026-09-20, Phase 11 architecture restructuring, see
docs/IMPLEMENTATION_TRACKER.md §4) and CartogenAi composes them rather than owning
their logic directly. Renamed from agent.py in the same pass, once those three
extractions already existed, to match docs/IMPLEMENTATION_TRACKER.md's own plan naming
-- a plain filename change with no behavior difference.
"""

import json
import time
import uuid

try:
    from qgis.PyQt.QtCore import QThread
    from qgis.core import QgsSettings
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    class QThread:
        @staticmethod
        def currentThread():
            return None
    class QgsSettings:
        def value(self, k, default=""): return default
        def setValue(self, k, v): pass

from ...infrastructure.providers import (
    OpenRouterClient, GeminiClient, OllamaClient, OpenAIClient, ClaudeClient, CartogenClient,
)
from ...infrastructure.providers.base import DEFAULT_MAX_TOKENS
from ...infrastructure.providers.cartogen import FALLBACK_MODELS as CARTOGEN_FALLBACK_MODELS
from .model_selector import AUTO_SENTINEL, classify_complexity, is_cheap_tier, pick_model_for_complexity
from .tool_dispatcher import ToolDispatcher
from .usage_tracker import UsageTracker
from .history_manager import HistoryManager
from .memory import SpatialMemoryManager
from .task_manager import AgentTaskManager
from .prompts import build_system_prompt
from .tools import TOOL_REGISTRY, TOOLS_SCHEMA
from .tools._snapshot_registry import get_snapshot_fn
from .tools.task_tools import bind_agent_context
from .tools.transaction_tools import bind_transaction_log
from . import tool_operations, tool_result as tool_results
from ..models.transactions import TurnTransactionLog
from ..models.plan_gate import PlanValidationGate
from ..models import egress_gate
from ..services import learning, response_guard
from . import onboarding_profile
from ..logger import log_event
from ...infrastructure.settings_keys import (
    SETTINGS_PROVIDER, SETTINGS_GEMINI_MODEL, SETTINGS_OLLAMA_MODEL,
    SETTINGS_OPENAI_MODEL, SETTINGS_CLAUDE_MODEL, SETTINGS_CARTOGEN_MODEL,
    SETTINGS_CARTOGEN_GATEWAY_URL, SETTINGS_OPENROUTER_MODEL,
    SETTINGS_PROJECT_INSPECTOR_ENABLED,
    SETTINGS_PLAN_VALIDATION_GATE_ENABLED,
    SETTINGS_MAX_TOOL_ITERATIONS,
    SETTINGS_MAX_TURN_TOKENS,
    provider_model_list_key,
)


# Tools that only do HTTP I/O, or local file/CPU work (chart rendering, table
# extraction), and never touch qgis.core/Qt objects. These are safe to run
# directly on whatever thread called them (agent.run() already executes on a
# background QgsTask thread -- see task_runner.py) instead of bouncing through
# the BlockingQueuedConnection dispatch that every other tool needs for
# main-thread PyQGIS safety. Routing these through it too would just freeze
# the QGIS GUI for the duration of each request/render.
NETWORK_ONLY_TOOLS = frozenset({
    "search_web", "geocode_and_enrich", "search_hdx_datasets",
    "fetch_osm_features", "search_stac_satellite_imagery", "fetch_fts_funding_data",
    "generate_chart", "extract_pdf_tables", "extract_word_tables", "aggregate_data",
})

# Bookkeeping tools excluded from auto-advancing the task plan on success (see
# auto_advance_if_unambiguous) -- these ARE the plan-tracking mechanism, so treating
# their own success as "a step's real work finished" would double-advance/misfire.
TASK_MANAGEMENT_TOOLS = frozenset({
    "create_plan", "set_task_preview", "update_task",
    "store_project_memory", "store_global_memory",
})

# Tools that mix a fast QGIS-state touch (QgsProject, QgsSettings/QgsAuthManager)
# with slow network I/O in one call. Routing them through the plain main-thread
# dispatch above would block the QGIS GUI for the duration of the HTTP
# request(s). Instead, _execute_two_phase_tool runs only the fast QGIS-touching
# part on the main thread, and the network part on the calling (background) thread.
TWO_PHASE_TOOLS = frozenset({
    "add_layer_from_path", "fetch_geoboundaries", "fetch_hdx_admin_boundaries", "fetch_building_footprints",
    "fetch_worldpop_population", "gemini_grounded_search", "openai_grounded_search",
    "fetch_nasa_active_fires", "fetch_nasa_eonet_events", "fetch_gdacs_disaster_alerts",
    "ingest_osm_features", "extract_features_from_imagery",
})


MAX_HISTORY_MESSAGES = 10
# Cross-turn history digest: trimmed messages are collapsed into a compact micro-summary
# capped at 600 chars (approx 120-150 tokens) to prevent context inflation across turns.
_HISTORY_DIGEST_MARKER = "[Earlier conversation digest -- older turns summarized, not verbatim]"
_HISTORY_DIGEST_MAX_CHARS = 600
# Was "Task completed successfully!" -- an empty model response means the
# model asserted nothing at all, so claiming success here was an unearned
# claim with zero evidence, directly contradicting prompt rules 12/15 (never
# state something as fact/success without a basis). Neutral instead.
EMPTY_RESPONSE_FALLBACK = "The model returned an empty response for this turn."
# Code-level backstop for the tool-result narrative-mismatch bug: prompt rule 15
# tells the model not to claim success/failure that contradicts its own last
# tool result, but nothing enforced that in code. If any of these words appear
# in the final answer, we trust the model already acknowledged the failure and
# leave its text alone -- this is a deliberately loose check (a false negative
# here just means no correction gets appended, not a wrong one).
FAILURE_ACK_KEYWORDS = (
    "error", "fail", "unable", "couldn't", "could not", "issue", "problem",
    "wasn't able", "was not able", "did not", "didn't",
)
# A plan+search+geocode+create_plan/update_task bookkeeping sequence for a
# realistic multi-step request can plausibly run 12-15 tool calls even with
# add_point_layer batching multi-location adds into one call (e.g. plan, search,
# a few geocode lookups, the bulk add, a couple of task updates). 10 was too
# tight and caused "Maximum iterations reached" on legitimate requests before
# they could produce a final answer.
MAX_ITERATIONS = 20

# Rate-limit resilience for large/complex requests (2026-09-12): up to MAX_ITERATIONS calls to
# client.complete() used to fire back-to-back with zero pacing -- a genuinely complex multi-step
# request (buffer this, then clip that, then style each, then export) could burst 15-20 API
# calls in a few seconds, well past most free/low-tier providers' requests-per-minute limits.
# Small/typical turns (<=3 tool-call rounds) pay nothing at all; only once a turn is genuinely
# getting large does it start spacing its own remaining calls out, proportional to how large it's
# getting -- throttling exactly the requests that are actually at risk, not every request.
PACING_THRESHOLD_ITERATIONS = 3
PACING_DELAY_SECONDS = 1.2

# Dynamic max_tokens scaling by iteration (2026-09-19, cost/performance pass): every
# client.complete() call in the loop below used to request the same DEFAULT_MAX_TOKENS
# (providers/base.py) regardless of what that particular call was actually likely to produce.
# A mid-turn tool-dispatch response (just a tool_calls block, little/no prose) genuinely never
# needs anywhere near the full budget, but the FIRST call of a turn is deliberately exempted
# from any cut -- it's the single most common shape a turn takes (a plain question with no
# tool call at all), and that's exactly the response most likely to be a long free-text
# synthesis needing the full budget, so capping it would risk truncating a normal one-shot
# answer. Every call after that is known to be a continuation of an already-in-progress
# tool-calling turn -- still allowed a materially smaller budget (half, not a hard 1-tool-call
# minimum) since even half of DEFAULT_MAX_TOKENS remains far larger than any real final-
# synthesis reply this plugin has produced, keeping the truncation risk low while still
# recovering real savings on the iterations that are, in practice, mostly short tool calls.
INTERMEDIATE_MAX_TOKENS = DEFAULT_MAX_TOKENS // 2


def _max_tokens_for_iteration(iteration_index):
    """See INTERMEDIATE_MAX_TOKENS's own comment -- iteration 0 always gets the full budget,
    every later iteration of the same turn gets the reduced one."""
    return DEFAULT_MAX_TOKENS if iteration_index == 0 else INTERMEDIATE_MAX_TOKENS

# Live-reported, 2026-09-19: on two separate runs of the identical "Health facilities
# beyond one hour's travel" request -- even WITH a correct task_directive already in the
# system prompt naming calculate_service_area/travel_time_matrix/etc. -- the model instead
# spent its whole MAX_ITERATIONS budget calling execute_pyqgis_script over and over trying
# to probe the filesystem/interpreter for a "real" data file (os/sys/QDir/pathlib imports,
# all correctly rejected by the sandbox), never once calling a directed tool, and failed
# the turn outright. A prompt-level fix ("LAST RESORT ONLY" is already execute_pyqgis_
# script's own tool description) clearly isn't reliable enough on its own -- this is a
# deterministic, code-level circuit breaker for the specific pattern that actually
# recurred: N consecutive execute_pyqgis_script calls in the SAME turn, every one rejected
# by the safety sandbox, is a strong signal the model is flailing rather than making
# progress. 3 was chosen as tight enough to interrupt this pattern well before it can burn
# through a 20-call budget, loose enough that a single legitimate blocked attempt (the
# model tries something reasonable, gets told no, tries a different approach) never
# triggers it.
SANDBOX_FLAILING_THRESHOLD = 3

# Mid-turn context compaction (same rate-limit/size-resilience work): the in-flight `messages`
# list for ONE turn keeps every prior tool call's result appended in full and re-sends the whole
# thing on every subsequent client.complete() call -- for a large task this grows the per-call
# payload unbounded, worsening both token-rate-limit exposure and the separate risk of hitting a
# provider's context-length ceiling outright. Only the most recent N tool results are kept in
# full; older ones (that succeeded -- see _compact_old_tool_results) get replaced with a short
# placeholder. This list (messages) is turn-local -- see run()'s own comment on
# conversation_history -- so compaction here never touches persisted conversation memory, only
# what gets sent for the REST of the turn already in flight.
MAX_FULL_TOOL_RESULTS_PER_TURN = 8
# Real live report, 2026-09-16: a Gemini 400 "input token count exceeds the maximum number of
# tokens allowed 1048576" after only 5 tool calls -- well under MAX_FULL_TOOL_RESULTS_PER_TURN,
# so the count-based window above never even kicked in. Root cause: inspect_canvas_visually
# (tools/multimodal_remote_sensing.py) returns a full base64-encoded PNG of the map canvas as
# its "image_b64" field -- a single call can easily be hundreds of thousands of tokens on its
# own, dwarfing every other tool's JSON output by orders of magnitude, and (unlike the 8-result
# window) needs no accumulation of many tool calls to blow the budget -- one is enough. The
# model only needs to see an image result once, right after the call that produced it; keeping
# it in full for every subsequent iteration of the same turn is pure waste. See
# _compact_old_tool_results's own updated comment for the size-based rule this adds.
_LARGE_TOOL_RESULT_CHAR_THRESHOLD = 20000
_COMPACTED_TOOL_RESULT_PLACEHOLDER = json.dumps({
    "note": "Result omitted from this request to keep it within size/rate limits -- "
            "this action already completed successfully earlier in this turn.",
})


def _accepts_confirmed(func):
    """True if `func` can take a `confirmed` keyword. Only the destructive-action tools declare
    it; the cloud-data override (agent/egress gate) confirms calls to ANY tool, most of which
    (execute_pyqgis_script, get_attributes, export_to_csv ...) do not. Injecting confirmed=True
    into those raised TypeError, so a user's Confirm click could never complete -- found in the
    rc7 smoke test, 2026-09-30 (tracker F02). The egress gate itself is bypassed by
    user_confirmed=True, so the tool has no use for the flag."""
    import inspect
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False
    return "confirmed" in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


class CartogenAi:
    def __init__(self):
        # Guards conversation_history against a genuine cross-thread race: run() executes
        # on the background QgsTask thread (see task_runner.py), but chat_tab_widget.py's
        # image-attachment handler (_analyze_attached_image or similar) appends to
        # agent.conversation_history directly from the main Qt thread while a turn could
        # still be in flight on the background thread. Created first, before anything else
        # in __init__, so it's always available no matter which of this method's several
        # conversation_history assignments below runs. See history_manager.py for why the
        # RLock (not Lock) lives there now, alongside the history list itself.
        self._history_manager = HistoryManager()

        from ...infrastructure.auth import CredentialManager
        settings = QgsSettings()
        provider_name = settings.value(SETTINGS_PROVIDER, "openrouter")
        key = CredentialManager.get_credential(provider_name)

        # When a model setting is the "auto" sentinel, use the provider's normal
        # default as a safe starting model, but remember to re-pick per request
        # in run() based on query complexity (see _apply_auto_model_selection).
        self._auto_model_provider = None
        # The model the client was built with while in auto mode: what "complex" requests use, and
        # what every request goes back to after a cheaper pick for a simple one.
        self._auto_default_model = None

        def resolve_model(model_key, safe_starting_model, default_to_auto=True):
            # "Nothing saved yet" defaults to the auto sentinel (not
            # safe_starting_model) -- so a fresh install with no explicit model
            # choice gets complexity-based auto-routing out of the box instead
            # of silently pinning to the priciest configured model forever.
            # safe_starting_model is still used as the model to actually
            # construct the client with while in auto mode, and as the
            # fallback if a stored value is somehow empty. Anyone who has
            # already picked a specific model keeps exactly that -- this only
            # changes behavior for installs that never touched the setting.
            # default_to_auto=False (Ollama only) opts out: local models aren't
            # a cost concern, and complexity-based naming heuristics don't
            # translate to an arbitrary local model catalog the way they do
            # for hosted providers.
            fallback = AUTO_SENTINEL if default_to_auto else safe_starting_model
            raw = settings.value(model_key, fallback)
            if raw == AUTO_SENTINEL:
                self._auto_model_provider = provider_name
                self._auto_default_model = safe_starting_model
                return safe_starting_model
            return raw or safe_starting_model

        if provider_name == "gemini":
            gemini_model = resolve_model(SETTINGS_GEMINI_MODEL, "gemini-flash-latest")
            self.client = GeminiClient(api_key=key, model=gemini_model)
        elif provider_name == "ollama":
            url = key if key else "http://localhost:11434/v1/chat/completions"
            if not url.endswith("chat/completions"):
                url = url.rstrip("/") + "/v1/chat/completions"
            ollama_model = resolve_model(SETTINGS_OLLAMA_MODEL, "llama3.1", default_to_auto=False)
            self.client = OllamaClient(endpoint_url=url, model=ollama_model)
        elif provider_name == "openai":
            openai_model = resolve_model(SETTINGS_OPENAI_MODEL, "gpt-5.6")
            self.client = OpenAIClient(api_key=key, model=openai_model)
        elif provider_name == "claude":
            claude_model = resolve_model(SETTINGS_CLAUDE_MODEL, "claude-opus-5")
            self.client = ClaudeClient(api_key=key, model=claude_model)
        elif provider_name == "cartogen":
            cartogen_model = resolve_model(SETTINGS_CARTOGEN_MODEL, CARTOGEN_FALLBACK_MODELS[0])
            # No gateway is deployed anywhere this repo can reach yet (see
            # providers/cartogen.py's module docstring) -- gateway_url stays None
            # (client falls back to its own GATEWAY_BASE_URL placeholder) unless
            # someone has explicitly set this for local/self-hosted testing.
            gateway_url = settings.value(SETTINGS_CARTOGEN_GATEWAY_URL, None) or None
            self.client = CartogenClient(api_key=key, model=cartogen_model, base_url=gateway_url)
        else:
            # OpenRouter already has its own multi-model fallback chain (see
            # openrouter.py FALLBACK_MODELS + 429/404 handling), which plays the
            # same role the generic complexity-based auto-selector plays for
            # every other provider. So "auto" here deliberately means "leave
            # that chain alone" rather than routing through
            # _auto_model_provider, which would otherwise overwrite
            # self.client.model with a single picked model on every request
            # and silently disable OpenRouter's own fallback behavior.
            openrouter_model = settings.value(SETTINGS_OPENROUTER_MODEL, AUTO_SENTINEL)
            if openrouter_model and openrouter_model != AUTO_SENTINEL:
                self.client = OpenRouterClient(api_key=key, model=openrouter_model)
            else:
                self.client = OpenRouterClient(api_key=key)


        self.memory_manager = SpatialMemoryManager()
        self.task_manager = AgentTaskManager()

        # Bind active task and memory managers to task tool execution handlers
        bind_agent_context(self.task_manager, self.memory_manager)

        # Turn-scoped operation log + best-effort undo (point 20 of the QGIS
        # production-architecture review) -- reset at the start of every run()
        # call, see transactions.py's own docstring for exactly what it covers.
        self._transaction_log = TurnTransactionLog()
        bind_transaction_log(self._transaction_log)

        # IMPLEMENTATION_TRACKER.md §1.6, option (b): plan-validation gate for DELETE/PUBLISH
        # tool calls, feature-flagged off by default (SETTINGS_PLAN_VALIDATION_GATE_ENABLED).
        # Same turn-scoped reset lifecycle as _transaction_log above -- see plan_gate.py.
        self._plan_gate = PlanValidationGate()

        # F21: what the cloud model may see about a protected layer (field names) follows the same egress-gate
        # settings and provider as the gate itself; read lazily so a Settings change applies on the next call.
        from ..models import model_view
        model_view.set_policy_provider(self._model_view_policy)

        # Usage-pattern tracking (self-learning mechanism 3, 2026-09-02): one
        # provider-usage sample per session, since CartogenAi() is constructed
        # once per session (see _get_agent() in plugin_main.py). Feeds both the
        # formatted memory context surfaced to the model and
        # learning.maybe_infer_preferences()'s passive preference detection
        # (mechanism 1), called after tool executions below.
        learning.record_provider_usage(self.memory_manager, provider_name)

        # Last successful tool call this session -- (name, args) or None. Used by
        # run() to attach a detected correction (mechanism 2) to the action it's
        # actually correcting, rather than just the bare user text.
        self._last_tool_call = None

        # CartogenAi() is always constructed synchronously from the main Qt
        # thread (via _get_agent() in plugin_main.py), so touching QgsProject
        # here to restore project-bound chat history is safe.
        from .chat_persistence import load_chat_history
        self.conversation_history = load_chat_history()
        # Plain text of what this conversation actually contained (user messages, project summary, tool results), kept
        # UNCOMPACTED because mid-turn compaction shrinks old tool results in `messages`. response_guard checks the final
        # answer's numbers, place names and terrain claims against it (GitHub #75). Bounded; cleared with the history.
        self._grounding_texts = []
        self.dispatcher = ToolDispatcher(self)

        # Session-scoped token usage totals -- see usage_tracker.py's own docstring for
        # the "why" (docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md SS3.2).
        self._usage_tracker = UsageTracker()

    @property
    def tools_schema(self):
        return TOOLS_SCHEMA

    def _get_usage_tracker(self):
        """Mirrors _get_history_lock()'s own lazy-init pattern (see its docstring):
        tests that construct CartogenAi via __new__() to skip __init__ entirely still
        get a working tracker on first access instead of an AttributeError."""
        tracker = self.__dict__.get("_usage_tracker")
        if tracker is None:
            tracker = UsageTracker()
            self._usage_tracker = tracker
        return tracker

    @property
    def session_usage(self):
        return self._get_usage_tracker().usage

    def _get_history_manager(self):
        """__init__ always creates _history_manager, but several tests in this codebase
        construct CartogenAi via CartogenAi.__new__(CartogenAi) to skip __init__ entirely
        (avoiding real QGIS/API-key setup) and hand-assign only the attributes they need --
        confirmed in tests/test_agent_runner.py. Lazily creating it here on first use
        (instead of every call site assuming __init__ ran) means those test doubles keep
        working without each one needing to know a new attribute exists. A benign race on
        first creation (two threads both finding none yet) isn't a practical concern here
        -- real usage always goes through __init__ first, which sets it before the instance
        is ever handed to another thread."""
        manager = self.__dict__.get("_history_manager")
        if manager is None:
            manager = HistoryManager()
            self._history_manager = manager
        return manager

    def _get_history_lock(self):
        return self._get_history_manager().lock

    @property
    def conversation_history(self):
        return self._get_history_manager().history

    @conversation_history.setter
    def conversation_history(self, value):
        self._get_history_manager().history = value

    def clear_history(self):
        with self._get_history_lock():
            self.conversation_history = []
        self._grounding_texts = []
        self._recent_tools = ((), 0)       # a new conversation does not inherit the last one's tools
        self.task_manager.clear_plan()

    def _accumulate_usage(self, usage):
        """Adds one API call's token usage into the session running total.
        See usage_tracker.UsageTracker.accumulate for the real logic -- this
        stays a thin delegator (rather than being removed) because
        chat_tab_widget.py and test_new_tools.py's usage-reporting suite call
        it directly on the agent object."""
        self._get_usage_tracker().accumulate(usage)

    def get_turn_usage_text(self):
        """'This turn ~N tokens (K calls)' for the turn that just ran, or None. See UsageTracker.turn_text."""
        return self._get_usage_tracker().turn_text()

    def _turn_limits(self):
        """(max tool-call rounds, max tokens) for one request. Settings override; a bad value falls back to the
        defaults (MAX_ITERATIONS, no token limit). The round cap is clamped to 1-100."""
        cap, budget = MAX_ITERATIONS, 0
        try:
            settings = QgsSettings()
            raw_cap = settings.value(SETTINGS_MAX_TOOL_ITERATIONS, None)
            raw_budget = settings.value(SETTINGS_MAX_TURN_TOKENS, None)
            if raw_cap not in (None, ""):
                cap = min(max(int(raw_cap), 1), 100)
            if raw_budget not in (None, ""):
                budget = max(int(raw_budget), 0)
        except Exception:
            cap, budget = MAX_ITERATIONS, 0
        return cap, budget

    def get_session_usage_text(self):
        """Short, human-readable summary of this session's token usage for
        ui/dock_widget.py's usage_label. See usage_tracker.UsageTracker.summary_text
        for the real logic and its full rationale -- this stays a thin delegator for
        the same reason as _accumulate_usage above."""
        return self._get_usage_tracker().summary_text()

    def reload_chat_history(self):
        """Re-reads project-bound chat history from QgsProject. Call this after
        the active QGIS project changes (readProject/cleared signals) -- the
        agent instance is cached and reused across projects (see _get_agent()
        in plugin_main.py), so without this its conversation_history would
        stay stuck on whichever project was active when it was constructed.
        Must be called from the main Qt thread (QgsProject is not thread-safe). The
        reassignment itself is still lock-protected, alongside every other
        conversation_history mutation -- see history_manager.py's own docstring."""
        from .chat_persistence import load_chat_history
        new_history = load_chat_history()
        with self._get_history_lock():
            self.conversation_history = new_history

    def _is_project_inspector_enabled(self) -> bool:
        """§1.5 option (b), OFF by default. Mirrors prompt_refiner.is_refinement_enabled()'s
        exact shape (QGIS_AVAILABLE guard, try/except, never raises)."""
        if not QGIS_AVAILABLE:
            return False
        try:
            return bool(QgsSettings().value(SETTINGS_PROJECT_INSPECTOR_ENABLED, False, type=bool))
        except Exception:
            return False

    def _model_view_policy(self):
        """(gate mode, provider is local, strict) for models/model_view.py."""
        base_url = getattr(getattr(self, "client", None), "base_url", None)
        return egress_gate.read_mode(), egress_gate.is_local_endpoint(base_url), egress_gate.read_strict()

    def _egress_gate_decision(self, name, filtered_args):
        """Cloud-provider egress gate (docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md): would
        this call send protected layer data to a non-local provider? Returns None (proceed) or
        egress_gate.evaluate()'s decision dict. Off by default -- returns before touching anything
        else, so it costs nothing and needs no per-instance state when the mode is "off".

        If the check itself fails in enforce mode the call is BLOCKED rather than let through: a
        privacy gate that silently fails open is worse than one that occasionally over-blocks."""
        mode = egress_gate.read_mode()
        if mode == egress_gate.MODE_OFF:
            return None
        try:
            from qgis.core import QgsProject
        except ImportError:
            return None
        try:
            from .lineage import effective_source_names, get_layer_lineage
            from ..models import sensitivity as _sens
            project = QgsProject.instance()

            all_layers = list(project.mapLayers().values())

            def get_level(layer_name):
                # Every layer sharing the name counts, strictest wins (#150): the first match alone could be the open twin.
                found = project.mapLayersByName(layer_name)
                return egress_gate.most_protective_level(
                    _sens.get_layer_sensitivity(lyr).get("level") for lyr in found)

            def get_sources(layer_name):
                out = []
                for lyr in project.mapLayersByName(layer_name):
                    for entry in get_layer_lineage(lyr):
                        if isinstance(entry, dict):
                            out.extend(n for n in effective_source_names(entry, all_layers) if n not in out)
                return out

            # A client with no readable endpoint (OpenRouter's, for one) counts as non-local --
            # the safe direction for a privacy gate.
            base_url = getattr(getattr(self, "client", None), "base_url", None)
            return egress_gate.evaluate(
                mode=mode,
                provider_is_local=egress_gate.is_local_endpoint(base_url),
                tool_name=name,
                arguments=filtered_args,
                project_layer_names=[lyr.name() for lyr in project.mapLayers().values()],
                get_level=get_level,
                get_sources=get_sources,
                strict=egress_gate.read_strict(),
            )
        except Exception:
            if mode == egress_gate.MODE_ENFORCE:
                return egress_gate.check_failed_decision(name)
            return None

    def _is_plan_gate_enabled(self) -> bool:
        """§1.6 option (b), OFF by default. Mirrors prompt_refiner.is_refinement_enabled()'s
        exact shape (QGIS_AVAILABLE guard, try/except, never raises)."""
        if not QGIS_AVAILABLE:
            return False
        try:
            return bool(QgsSettings().value(SETTINGS_PLAN_VALIDATION_GATE_ENABLED, False, type=bool))
        except Exception:
            return False

    def _register_preview_task(self, name, args, res):
        """Registers the dedicated, confirmable safety task for a PREVIEW_REQUIRED result --
        one code path for the destructive-action gate AND the cloud-data override, so the two
        can never disagree about what "Confirm" does."""
        # Register a DEDICATED preview safety task -- never reuse tasks[0] of
        # whatever plan happens to already be active. Real live bug, 2026-09-16:
        # this used to only start a fresh plan `if not self.task_manager.tasks`,
        # so when a plan from an earlier, unrelated turn was still active (the
        # common case -- plans aren't cleared between turns), the preview state
        # got glued onto tasks[0], silently overwriting an already-DONE task's
        # status/result with this gate's PREVIEW_READY state. add_task() appends
        # instead, so a pending confirmation can never collide with an existing
        # task that already means something else.
        # rc11 smoke test (#125): a vague reply made the model retry the same action through another tool, and every blocked
        # attempt left its own pending preview -- one typed "confirm" then ran a leftover from an earlier attempt. Only the
        # newest preview stays pending; older ones are closed so a confirmation always means the card on screen.
        for older in self.task_manager.tasks:
            if older.get("status") == "PREVIEW_READY" and older.get("pending_tool"):
                self.task_manager.update_task(older["id"], "FAILED", "Superseded by a newer confirmation request")
        if not self.task_manager.tasks:
            self.task_manager.create_plan(
                f"Safety Gate Preview: {name}",
                [f"Preview {name} operation"]
            )
            preview_task = self.task_manager.tasks[0]
        else:
            preview_task = self.task_manager.add_task(f"Preview {name} operation")["task"]
        self.task_manager.set_task_preview(
            task_id=preview_task["id"],
            code_snippet=res.get("code_snippet", ""),
            rationale=res.get("rationale", ""),
            is_destructive=res.get("is_destructive", True)
        )
        # Attach pending execution arguments to the SAME dedicated task object
        # (set_task_preview mutates self.task_manager.tasks in place, so
        # preview_task -- taken from that same list -- reflects it here too).
        preview_task["pending_tool"] = name
        preview_task["pending_args"] = res.get("arguments", {**args, "confirmed": True})
        preview_task["egress_override"] = bool(res.get("egress_override"))

    def _real_execute_tool(self, name, arguments, user_confirmed: bool = False):
        func = TOOL_REGISTRY.get(name)
        if func is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            args = arguments if isinstance(arguments, dict) else json.loads(arguments or "{}")
        except (TypeError, ValueError) as e:
            return {"error": f"Invalid tool arguments: {e}"}
        # A well-formed JSON document that isn't an object (a bare string, list, or number)
        # decodes successfully -- json.loads has no way to reject that on its own. A
        # double-JSON-encoded tool-call arguments string (a known real-world quirk: the
        # model's own arguments field is itself a JSON-encoded string, so parsing it once
        # yields a plain string, not the intended object) hits exactly this shape. Without
        # this check, the next line's args.items() raises an uncaught 'str' object has no
        # attribute 'items' -- same bug class as the already-fixed usage-parsing crashes
        # (extract_openai_style_usage, providers/base.py), just a different call site.
        if not isinstance(args, dict):
            return {"error": f"Invalid tool arguments: expected an object, got {type(args).__name__}."}

        # Dispatcher-level schema enforcement: filter out any argument keys not in the registered tool schema
        schema_props = {}
        for item in TOOLS_SCHEMA:
            fn_def = item.get("function", {})
            if fn_def.get("name") == name:
                schema_props = fn_def.get("parameters", {}).get("properties", {})
                break

        # Strip unadvertised arguments (prevents model self-approval via injected parameters)
        filtered_args = {k: v for k, v in args.items() if k in schema_props}
        if user_confirmed and _accepts_confirmed(func):
            filtered_args["confirmed"] = True

        # §1.6 option (b) plan-validation gate: checked BEFORE the call, not after --
        # blocking here means the DELETE/PUBLISH tool's own side effects never happen at
        # all, rather than happening and then being reported as needing a plan retroactively.
        gate_response = self._plan_gate.check(name, self._is_plan_gate_enabled())
        if gate_response is not None:
            return gate_response

        # Egress gate: also BEFORE the call, for the same reason -- a blocked call must never
        # execute, since executing is what reads the protected layer -- UNLESS a human has
        # already confirmed the override via the SAME UI Confirm-button path destructive
        # actions use (user_confirmed=True never comes from the model; see filtered_args'
        # own "confirmed" handling above). IMPLEMENTATION_TRACKER.md §1.4 decision 2.
        egress = self._egress_gate_decision(name, filtered_args)
        egress_overridable = egress is not None and egress["action"] == "block" and bool(egress.get("layers"))
        egress_override_applied = egress_overridable and user_confirmed
        if egress is not None and egress["action"] == "block" and not egress_override_applied:
            log_event("egress_blocked", tag="Agent", tool=name, layer_count=len(egress.get("layers") or {}))
            if egress_overridable:
                # The confirmable task MUST be registered here: this branch returns before the
                # generic PREVIEW_REQUIRED handling further down, so without it nothing
                # confirmable exists, a typed "confirm" reaches the model instead of the
                # plugin, and the model improvises (rc7 smoke test F02/F03, 2026-09-30).
                blocked = egress_gate.preview_required(name, filtered_args, egress)
                self._register_preview_task(name, args, blocked)
                return blocked
            return egress["result"]
        if egress_override_applied:
            log_event("egress_override_confirmed", tag="Agent", tool=name, layer_count=len(egress["layers"]))

        try:
            res = func(**filtered_args)
            if egress is not None and egress["action"] == "warn" and isinstance(res, dict):
                res["egress_warning"] = egress["warning"]
            if egress_override_applied and isinstance(res, dict):
                res["egress_override_note"] = (
                    "User confirmed sending protected data (%s) to a cloud provider for this call."
                    % ", ".join(sorted(egress["layers"]))
                )
            if name == "create_plan" and isinstance(res, dict) and res.get("success"):
                self._plan_gate.mark_plan_created()
            if isinstance(res, dict):
                if res.get("status") == "PREVIEW_REQUIRED":
                    self._register_preview_task(name, args, res)

                elif res.get("success"):
                    self.memory_manager.log_spatial_action(name, str(args))
                    learning.record_tool_usage(self.memory_manager, name)
                    learning.maybe_infer_preferences(self.memory_manager)
                    self._last_tool_call = (name, args)
                    self._tag_created_layers(name, args, res)
                    if name not in TASK_MANAGEMENT_TOOLS:
                        self.task_manager.auto_advance_if_unambiguous(f"{name} succeeded", tool_name=name)
            # One exit for every dispatch path: a tool that returns nothing is reported as a failure here, so the inline and the
            # dispatcher-thread paths no longer disagree (the model used to see a bare null on one of them).
            return tool_results.ensure_result(res)
        except TypeError as e:
            return {"error": f"Invalid arguments for {name}: {e}", "error_class": type(e).__name__}
        except Exception as e:
            return {"error": f"Tool {name} failed: {e}", "error_class": type(e).__name__}

    def _on_dispatcher_thread(self):
        """True if the calling thread is already the dispatcher's own thread (normally
        the main Qt thread)."""
        try:
            return QThread.currentThread() == self.dispatcher.thread()
        except Exception:
            return False

    def _live_layer_ids(self):
        """The live QgsProject's current layer ids, for transactions.py's
        before/after diff. Empty set with no error when QGIS isn't available
        or no project is open -- callers treat that as "nothing new ever
        detected", not a failure."""
        try:
            from qgis.core import QgsProject
        except ImportError:
            return set()
        try:
            return set(QgsProject.instance().mapLayers().keys())
        except Exception:
            return set()

    def _execute_tool(self, name, arguments):
        """Single entry point for every tool call in run()'s loop, regardless
        of which of the three dispatch paths below actually executes it --
        wrapping here (rather than duplicating the same before/after capture
        in _real_execute_tool AND _execute_two_phase_tool) is what lets
        transactions.py's TurnTransactionLog see every call uniformly,
        including the four fetch_* tools that only add their layer via
        _execute_two_phase_tool's separate main-thread callback.

        v1.7.0: also takes a _snapshot_registry.py snapshot BEFORE dispatch,
        for the priority subset of MODIFY/DELETE tools that module covers --
        must happen before the call runs, since the whole point is capturing
        state the call is about to overwrite/remove. A tool with no
        registered snapshot function, or whose snapshot_fn finds nothing to
        snapshot (e.g. layer not found), gets snapshot=None, which record()
        already treats as "fall back to the existing new-layer-diff
        mechanism" -- no different from before this change for every other
        tool.

        Real live crash, 2026-09-16, finally caught with a real traceback (every earlier
        report of the same "Error: 'str' object has no attribute 'get'" text this session had
        none): `arguments` arrives here as the RAW, still-JSON-encoded string from the model's
        tool call -- run()'s loop reads it straight off fn.get("arguments", "{}") with no
        parsing. _real_execute_tool/_execute_two_phase_tool each parse it into a dict
        internally before using it, but snapshot_fn(arguments) below was called with the raw
        string, BEFORE either of those ever runs -- and outside the try/except a few lines
        down, which only wraps the dispatch call, not this. _snapshot_style
        (_snapshot_registry.py) does `arguments.get("layer_name")`, assuming a dict, and
        apply_categorized_style is registered with exactly that snapshot function -- any turn
        that calls it (traceback confirmed: apply_categorized_style, after 15 unrelated
        successful tool calls in the same turn) hit this every time, regardless of what else
        ran first. Parsing once here, the same way the two dispatch targets already do
        (isinstance guard first, so re-parsing an already-dict value later is a no-op), fixes
        the actual reported bug -- the isinstance guard added to _compact_old_tool_results
        earlier this session was a real, separate gap, not this one."""
        if self._turn_is_stale():
            return {"error": "The project changed while this request was running, so the tool was not run. "
                             "Ask again in the project you now have open.", "project_changed": True}
        try:
            parsed_arguments = arguments if isinstance(arguments, dict) else json.loads(arguments or "{}")
            if not isinstance(parsed_arguments, dict):
                parsed_arguments = {}
        except (TypeError, ValueError):
            parsed_arguments = {}
        operation_type = tool_operations.get_tool_operation_type(name)

        # #138 (audit F02): the before-state (project layer ids + undo snapshot) and the after-state used to be read here, on
        # the calling context, which for a turn is the AgentQgsTask worker thread -- only the tool body itself was marshalled
        # to the main thread. QgsProject / layer access from the worker is not safe. Now the whole command (before-state,
        # tool, after-state, transaction record) is ONE unit on the main thread for ordinary tools. Network-only and two-phase
        # tools must keep their slow part on the worker, so only their project-state reads/writes are marshalled.
        if name in NETWORK_ONLY_TOOLS or name in TWO_PHASE_TOOLS:
            before = self._run_on_main_thread(lambda _a: self._capture_before(name, parsed_arguments), None)
            if not (isinstance(before, tuple) and len(before) == 2):
                before = (set(), None)
            result = self._guarded_dispatch(name, arguments)
            self._run_on_main_thread(
                lambda _a: self._record_after(name, operation_type, result, before[0], before[1]), None)
            return result

        def command(_unused):
            ids_before, snap = self._capture_before(name, parsed_arguments)
            res = self._guarded_dispatch(name, arguments)
            self._record_after(name, operation_type, res, ids_before, snap)
            return res

        result = self._run_on_main_thread(command, None)
        # Only a MISSING result is a failure. #138 (rc12) tested isinstance(result, dict) here, but get_layers, get_attributes and
        # other read tools legitimately return a list: every one of them came back as "Execution failed unexpectedly." in the rc15
        # hand test (2026-10-06, 0 ms, tool body never reported as run). _run_on_main_thread already turns an exception into an
        # {"error": ...} dict, so None is the only value that means nothing came back.
        return tool_results.ensure_result(result)

    def _capture_before(self, name, parsed_arguments):
        """(layer ids, undo snapshot) before a tool runs. MAIN THREAD ONLY. A snapshot function that raises is reported, not
        swallowed silently: the call then has no snapshot, which transactions.py already treats as 'fall back to the new-layer
        diff', i.e. undo of that call is limited -- visible in the log instead of a crash of the whole turn."""
        ids = self._live_layer_ids()
        snapshot_fn = get_snapshot_fn(name)
        snapshot = None
        if snapshot_fn:
            try:
                snapshot = snapshot_fn(parsed_arguments)
            except Exception as e:
                log_event("snapshot", tag="Agent", tool=name, status="failed", error_class=type(e).__name__, error=True)
        return ids, snapshot

    def _record_after(self, name, operation_type, result, ids_before, snapshot):
        """Records the call in the turn's transaction log. MAIN THREAD ONLY (reads the live project)."""
        ids_after = self._live_layer_ids()
        self._transaction_log.record(name, operation_type, result, ids_before, ids_after, snapshot=snapshot)

    def _guarded_dispatch(self, name, arguments):
        # Real live crash, 2026-09-13: a turn ended in a bare chat bubble reading
        # "Error: 'str' object has no attribute 'get'" -- an uncaught AttributeError
        # that escaped run()'s tool-call loop entirely (task_runner.py's outer
        # try/except is what actually caught it, surfacing the raw Python exception
        # text with no context). Root-caused via direct code reading, not guessed:
        # _real_execute_tool wraps its own func(**filtered_args) call in a broad
        # except Exception, but _execute_two_phase_tool (TWO_PHASE_TOOLS' dispatch
        # path -- the 3 hazard-monitoring fetch tools among them) has NO equivalent
        # wrapping at all, and this call site (the one place ALL THREE dispatch
        # paths funnel through) had none either. Confirmed a real, reachable trigger:
        # fetch_nasa_eonet_events_network_phase/fetch_gdacs_disaster_alerts_network_
        # phase/fetch_hdx_admin_boundaries_network_phase (hazard_monitoring_tools.py,
        # humanitarian_tools.py) each call `data.get(...)` on a freshly-`json.loads`'d
        # API response OUTSIDE their own try/except's coverage -- if the external API
        # (GDACS's own docs warn its data "may require further validation") ever
        # returns valid JSON that isn't a dict (a bare string/list/null error body),
        # that .get() raises uncaught, with nothing anywhere in the call chain to
        # catch it. Fixed at BOTH the specific sites (proper isinstance guards, see
        # each file) AND here, as the general safety net every tool call -- present
        # or future -- gets for free: any exception that reaches this point, from
        # any dispatch path, becomes a normal {"error": ...} result instead of
        # silently ending the whole turn.
        try:
            return self._execute_tool_dispatch(name, arguments)
        except Exception as e:
            return {"error": f"Tool {name} failed unexpectedly: {e}", "error_class": type(e).__name__}

    def _execute_tool_dispatch(self, name, arguments):
        if name in NETWORK_ONLY_TOOLS:
            return self._real_execute_tool(name, arguments)
        if name in TWO_PHASE_TOOLS:
            return self._execute_two_phase_tool(name, arguments)

        if self._on_dispatcher_thread():
            return self._real_execute_tool(name, arguments)

        result = []
        # Emit signal to main thread and block until execution returns
        self.dispatcher.request_execution.emit(name, arguments, result)
        if result:
            return result[0]
        return tool_results.ensure_result(None)

    def _get_schema_props(self, name):
        for item in TOOLS_SCHEMA:
            fn_def = item.get("function", {})
            if fn_def.get("name") == name:
                return fn_def.get("parameters", {}).get("properties", {})
        return {}

    def _run_on_main_thread(self, func, arg):
        # No dispatcher (no QGIS/Qt, e.g. the offline tests): there is no other thread to marshal to, run inline.
        if getattr(self, "dispatcher", None) is None or self._on_dispatcher_thread():
            try:
                return func(arg)
            except Exception as e:
                return {"error": str(e)}

        result = []
        self.dispatcher.request_callable.emit(func, arg, result)
        if result:
            return result[0]
        return tool_results.ensure_result(None)

    def _log_tool_success(self, name, args, res):
        """Mirrors _real_execute_tool's success-path side effects (spatial memory
        log + layer lineage tagging) for TWO_PHASE_TOOLS, which don't go through
        _real_execute_tool directly. Kept as a separate small helper rather than
        refactoring _real_execute_tool itself, to avoid touching that already
        security-critical, well-tested code path."""
        if not (isinstance(res, dict) and res.get("success")):
            return
        self.memory_manager.log_spatial_action(name, str(args))
        self._tag_created_layers(name, args, res)
        learning.record_tool_usage(self.memory_manager, name)
        learning.maybe_infer_preferences(self.memory_manager)
        self._last_tool_call = (name, args)
        # TWO_PHASE_TOOLS are never task-management tools, so no exclusion check needed here
        # (unlike the equivalent call in _real_execute_tool's success branch).
        self.task_manager.auto_advance_if_unambiguous(f"{name} succeeded", tool_name=name)

    def _execute_two_phase_tool(self, name, arguments):
        """Handles TWO_PHASE_TOOLS (see module-level comment): runs the network
        fetch on the calling thread (background, when invoked from run()), then
        bounces only the fast, local-disk-only QGIS layer-creation step to the
        main thread via the dispatcher's BlockingQueuedConnection."""
        try:
            args = arguments if isinstance(arguments, dict) else json.loads(arguments or "{}")
        except (TypeError, ValueError) as e:
            return {"error": f"Invalid tool arguments: {e}"}
        # See _real_execute_tool's identical check for why this is needed even though
        # json.loads already succeeded above.
        if not isinstance(args, dict):
            return {"error": f"Invalid tool arguments: expected an object, got {type(args).__name__}."}

        # Same dispatcher-level schema enforcement as _real_execute_tool
        schema_props = self._get_schema_props(name)
        filtered_args = {k: v for k, v in args.items() if k in schema_props}

        if name == "add_layer_from_path":
            from .tools.vector_tools import _prefetch_url_to_temp, add_layer_from_path
            file_path = filtered_args.get("file_path", "")
            try:
                local_path, is_temp = _prefetch_url_to_temp(file_path)
            except Exception as e:
                return {"error": f"Download failed: {e}"}
            try:
                res = self._run_on_main_thread(
                    lambda a: add_layer_from_path(a["file_path"], a.get("layer_name"), a.get("source_label")),
                    {"file_path": local_path, "layer_name": filtered_args.get("layer_name"),
                     "source_label": file_path if is_temp else None},
                )
            finally:
                if is_temp:
                    import os
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
            self._log_tool_success(name, filtered_args, res)
            return res

        if name == "extract_features_from_imagery":
            # The model checkpoint is fetched here, on the background thread; only the inference and layer creation run on the
            # main thread (rc15/rc17 hand tests: the in-tool download froze QGIS for ~43 s).
            from .tools.imagery_extraction import ensure_checkpoint, extract_features_from_imagery
            checkpoint = ensure_checkpoint()
            if "error" in checkpoint:
                return checkpoint
            res = self._run_on_main_thread(
                lambda a: extract_features_from_imagery(**a), {**filtered_args, "model_path": checkpoint.get("path")})
            self._log_tool_success(name, filtered_args, res)
            return res

        if name == "fetch_geoboundaries":
            from .tools.humanitarian_tools import (
                fetch_geoboundaries_network_phase, add_geoboundaries_layer_main_thread_phase,
            )
            fetch_result = fetch_geoboundaries_network_phase(
                filtered_args.get("iso3", ""), filtered_args.get("admin_level", "ADM1"),
                bool(filtered_args.get("allow_large_download")),
            )
            try:
                res = self._run_on_main_thread(add_geoboundaries_layer_main_thread_phase, fetch_result)
            finally:
                local_path = fetch_result.get("local_path")
                if local_path:
                    import os
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
            self._log_tool_success(name, filtered_args, res)
            return res

        if name == "fetch_hdx_admin_boundaries":
            from .tools.humanitarian_tools import (
                fetch_hdx_admin_boundaries_network_phase, add_hdx_admin_boundaries_layer_main_thread_phase,
            )
            fetch_result = fetch_hdx_admin_boundaries_network_phase(
                filtered_args.get("iso3", ""), filtered_args.get("admin_level", "ADM1"),
                bool(filtered_args.get("allow_large_download")),
            )
            try:
                res = self._run_on_main_thread(add_hdx_admin_boundaries_layer_main_thread_phase, fetch_result)
            finally:
                local_path = fetch_result.get("local_path")
                if local_path:
                    import os
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
            self._log_tool_success(name, filtered_args, res)
            return res

        if name == "fetch_building_footprints":
            from .tools.humanitarian_tools import (
                fetch_building_footprints_network_phase, add_building_footprints_layer_main_thread_phase,
            )
            fetch_result = fetch_building_footprints_network_phase(
                filtered_args.get("country_name", ""), filtered_args.get("bbox", []),
                filtered_args.get("max_features", 5000), bool(filtered_args.get("allow_large_download")),
            )
            try:
                res = self._run_on_main_thread(add_building_footprints_layer_main_thread_phase, fetch_result)
            finally:
                local_path = fetch_result.get("local_path")
                if local_path:
                    import os
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
            self._log_tool_success(name, filtered_args, res)
            return res

        if name == "fetch_worldpop_population":
            from .tools.humanitarian_tools import (
                fetch_worldpop_population_network_phase, add_worldpop_population_layer_main_thread_phase,
                resolve_extent_bbox,
            )
            wp_bbox = filtered_args.get("bbox")
            if filtered_args.get("extent_layer") and wp_bbox is None:
                # Needs QgsProject, so it runs on the main thread before the (background) download.
                try:
                    wp_bbox = self._run_on_main_thread(resolve_extent_bbox, filtered_args["extent_layer"])
                except ValueError as e:
                    return {"error": str(e)}
            # Where a whole-country file is cached (F19 fallback); asks QgsProject, so it runs on the main thread.
            try:
                from .tools.humanitarian_tools import worldpop_cache_dir
                wp_cache_dir = self._run_on_main_thread(worldpop_cache_dir, None)
            except Exception:
                wp_cache_dir = None
            fetch_result = fetch_worldpop_population_network_phase(
                filtered_args.get("iso3", ""), filtered_args.get("year"), wp_bbox,
                bool(filtered_args.get("allow_whole_country")), wp_cache_dir,
            )
            # No cleanup here, deliberately -- unlike fetch_geoboundaries above,
            # the downloaded file must stay on disk for as long as the raster
            # layer exists (see add_worldpop_population_layer_main_thread_phase).
            res = self._run_on_main_thread(add_worldpop_population_layer_main_thread_phase, fetch_result)
            self._log_tool_success(name, filtered_args, res)
            return res

        if name == "fetch_nasa_active_fires":
            from .tools.hazard_monitoring_tools import (
                fetch_nasa_active_fires_network_phase, add_nasa_active_fires_layer_main_thread_phase,
            )
            fetch_result = fetch_nasa_active_fires_network_phase(
                filtered_args.get("bbox"), filtered_args.get("days", 1), filtered_args.get("min_confidence", "nominal"),
            )
            res = self._run_on_main_thread(
                lambda a: add_nasa_active_fires_layer_main_thread_phase(a["fetch_result"], a["layer_name"]),
                {"fetch_result": fetch_result, "layer_name": filtered_args.get("layer_name", "NASA Active Fires")},
            )
            self._log_tool_success(name, filtered_args, res)
            return res

        if name == "fetch_nasa_eonet_events":
            from .tools.hazard_monitoring_tools import (
                fetch_nasa_eonet_events_network_phase, add_nasa_eonet_events_layer_main_thread_phase,
            )
            fetch_result = fetch_nasa_eonet_events_network_phase(
                filtered_args.get("bbox"), filtered_args.get("category"),
                filtered_args.get("days", 20), filtered_args.get("status", "open"),
            )
            res = self._run_on_main_thread(
                lambda a: add_nasa_eonet_events_layer_main_thread_phase(a["fetch_result"], a["layer_name"]),
                {"fetch_result": fetch_result, "layer_name": filtered_args.get("layer_name", "NASA EONET Events")},
            )
            self._log_tool_success(name, filtered_args, res)
            return res

        if name == "fetch_gdacs_disaster_alerts":
            from .tools.hazard_monitoring_tools import (
                fetch_gdacs_disaster_alerts_network_phase, add_gdacs_disaster_alerts_layer_main_thread_phase,
            )
            fetch_result = fetch_gdacs_disaster_alerts_network_phase(
                filtered_args.get("bbox"), filtered_args.get("min_alert_level", "Orange"),
            )
            res = self._run_on_main_thread(
                lambda a: add_gdacs_disaster_alerts_layer_main_thread_phase(a["fetch_result"], a["layer_name"]),
                {"fetch_result": fetch_result, "layer_name": filtered_args.get("layer_name", "GDACS Disaster Alerts")},
            )
            self._log_tool_success(name, filtered_args, res)
            return res

        if name == "gemini_grounded_search":
            # Reversed order vs the other two-phase tools: the QGIS-touching part
            # (reading provider/model/credential from QgsSettings/QgsAuthManager)
            # is fast and goes first on the main thread; the slow network call
            # to Gemini goes second, on the calling (background) thread.
            from .tools.system_tools import resolve_gemini_search_config
            from ...infrastructure.providers.gemini import grounded_search
            config = self._run_on_main_thread(lambda _: resolve_gemini_search_config(), None)
            if "error" in config:
                return config
            return grounded_search(config["api_key"], filtered_args.get("query", ""), model=config["model"])

        if name == "openai_grounded_search":
            # Same two-phase split as gemini_grounded_search above.
            from .tools.system_tools import resolve_openai_search_config
            from ...infrastructure.providers.openai import grounded_search
            config = self._run_on_main_thread(lambda _: resolve_openai_search_config(), None)
            if "error" in config:
                return config
            return grounded_search(config["api_key"], filtered_args.get("query", ""))

        if name == "ingest_osm_features":
            from .tools.humanitarian_tools import (
                ingest_osm_features_network_phase, add_osm_layer_main_thread_phase,
            )
            fetch_result = ingest_osm_features_network_phase(
                key=filtered_args.get("key", ""),
                value=filtered_args.get("value", ""),
                bbox=filtered_args.get("bbox"),
                center_lat=filtered_args.get("center_lat"),
                center_lon=filtered_args.get("center_lon"),
                radius_km=filtered_args.get("radius_km"),
                layer_name=filtered_args.get("layer_name"),
            )
            try:
                res = self._run_on_main_thread(add_osm_layer_main_thread_phase, fetch_result)
            finally:
                local_path = fetch_result.get("local_path")
                if local_path:
                    import os
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
            self._log_tool_success(name, filtered_args, res)
            return res

        return {"error": f"Unknown two-phase tool: {name}"}

    @staticmethod
    def _is_digest_message(msg):
        # See history_manager.py's module docstring for why the threshold constants stay
        # module-level globals here rather than living on HistoryManager itself --
        # test_agent_runner.py monkeypatches them directly on this module.
        return HistoryManager.is_digest_message(msg, _HISTORY_DIGEST_MARKER)

    @staticmethod
    def _summarize_dropped_messages(dropped):
        return HistoryManager.summarize_dropped_messages(dropped)

    def _trim_history(self):
        self._get_history_manager().trim(MAX_HISTORY_MESSAGES, _HISTORY_DIGEST_MARKER, _HISTORY_DIGEST_MAX_CHARS)

    _turn_project_session = None

    def _turn_is_stale(self):
        """True when the running turn was started in a project that has since been cleared or replaced (project_session.py)."""
        from . import project_session
        return project_session.is_stale(self._turn_project_session)

    def _append_history(self, *messages):
        """Appends one or more messages to conversation_history and trims it, all under
        one lock acquisition -- see history_manager.HistoryManager.append for the real
        logic. Also the method chat_tab_widget.py's image-attachment handler (main
        thread) goes through instead of touching conversation_history.append() directly,
        so a turn finishing concurrently on the background QgsTask thread can't
        interleave with it mid-mutation."""
        if self._turn_is_stale():
            return  # #147: a turn from the previous project must not write into the one open now
        self._get_history_manager().append(messages, MAX_HISTORY_MESSAGES, _HISTORY_DIGEST_MARKER, _HISTORY_DIGEST_MAX_CHARS)

    def _read_history_snapshot(self):
        """Returns a shallow copy of conversation_history, taken under the lock -- see
        history_manager.HistoryManager.snapshot for the real logic. The safe replacement
        for reading self.conversation_history directly while building a turn's outgoing
        message list (run()'s messages.extend(...) call), which could otherwise observe
        a torn read against a concurrent _append_history() call from another thread."""
        return self._get_history_manager().snapshot()

    def _compact_old_tool_results(self, messages):
        """Mid-turn context compaction -- see history_manager.HistoryManager.
        compact_old_tool_results for the real logic and its full rationale (why a
        count-based AND a size-based rule both exist, and the live "'str' object has no
        attribute 'get'" bug this was hardened against). Kept as a thin delegator on the
        agent since it's called from several points in run() below by that name."""
        HistoryManager.compact_old_tool_results(
            messages, MAX_FULL_TOOL_RESULTS_PER_TURN, _LARGE_TOOL_RESULT_CHAR_THRESHOLD,
            _COMPACTED_TOOL_RESULT_PLACEHOLDER,
        )

    def _apply_auto_model_selection(self, user_query):
        """If the active provider's model setting is "auto", choose the model for this request.

        Auto is a cost saver, not a performance escalator. It never selects a model in the
        "capable" tier: a simple request may get a smaller model from the live list fetched in
        Settings, and every other request uses the built-in default. What counts as "smaller" is
        inferred from the model's NAME (mini, flash, haiku, ...), which is not price information,
        so this does not guarantee a lower bill on every provider or account; actual billed cost
        is measured separately (docs/IMPLEMENTATION_TRACKER.md, API-cost plan item 2).

        Found 2026-09-25 (cost review), when the provider fix in providers/base.py made these
        picks take effect for the first time -- before that, Gemini/OpenAI/OpenRouter/Cartogen
        discarded them and always sent the configured model: the escalation target is a guess
        from the name ("pro", "max", "ultra"), and on a real list it was a research-agent model,
        or a top-priced "-pro" model. The built-in default is already the user's (or the plugin's)
        choice of capable model. A model that is already a small one is left alone, so a Gemini
        flash default never moves sideways to another flash.

        The model is assigned on every request, not only when a smaller one is found: without
        that, the smaller model picked for one simple request would stay selected for the next
        complex one. Never invents a model, and if the picker finds nothing suitable (no live list
        fetched, or only special-purpose models) the default is used. Tool-calling support is not
        checked -- only chat eligibility and special-purpose exclusion (a tracked follow-up)."""
        if not self._auto_model_provider:
            return
        try:
            default = self._auto_default_model or getattr(self.client, "model", None)
            if not default:
                return
            target = default
            complexity = classify_complexity(user_query)
            if complexity == "simple" and not is_cheap_tier(default):
                settings = QgsSettings()
                raw_list = settings.value(provider_model_list_key(self._auto_model_provider), "")
                model_ids = json.loads(raw_list) if raw_list else []
                if model_ids:
                    picked = pick_model_for_complexity(model_ids, "simple")
                    if picked and is_cheap_tier(picked):
                        target = picked
            self.client.model = target
            if target != default and hasattr(self.client, "_emit_status"):
                self.client._emit_status(f"Auto-selected {target} ({complexity} request)")
        except Exception as e:
            print(f"[CartogenAi] auto model selection failed: {e}")

    def _reconcile_final_text_with_tool_log(self, final_text, turn_tool_log):
        """Code-level backstop for the tool-result narrative-mismatch bug (see
        prompt rule 15): if any tool call made in this turn ended in an
        unresolved error and the model's final answer doesn't acknowledge any
        failure, append a factual correction instead of silently returning a
        false-success claim. Deterministic, no extra API call -- this doesn't
        replace rule 15, it's a cheap safety net for when the model doesn't
        follow it.

        Originally only checked the LAST call in the turn -- verified live
        that this missed the actual common shape of the bug: an EARLIER call
        fails, the model recovers with a different tool, and the final answer
        claims success while never mentioning the earlier failure at all. Now
        scans every call; an error is only treated as "resolved" (and not
        flagged) if a LATER call to that same tool name in the same turn
        succeeded -- a plain retry-then-success shouldn't generate a spurious
        warning about the first attempt."""
        if not turn_tool_log:
            return final_text
        lower_text = (final_text or "").lower()
        if any(kw in lower_text for kw in FAILURE_ACK_KEYWORDS):
            return final_text

        unresolved = []
        for i, (name, is_error, error_msg) in enumerate(turn_tool_log):
            if not is_error:
                continue
            resolved_later = any(
                later_name == name and not later_is_error
                for later_name, later_is_error, _ in turn_tool_log[i + 1:]
            )
            if not resolved_later:
                unresolved.append((name, error_msg))

        if not unresolved:
            return final_text
        if len(unresolved) == 1:
            name, error_msg = unresolved[0]
            note = (
                f"⚠️ Note: a tool call in this turn (`{name}`) actually returned "
                f"an error that isn't reflected above: {error_msg}"
            )
        else:
            lines = "\n".join(f"- `{name}`: {error_msg}" for name, error_msg in unresolved)
            note = (
                f"⚠️ Note: {len(unresolved)} tool calls in this turn returned errors that "
                f"aren't reflected above:\n{lines}"
            )
        return f"{final_text}\n\n{note}"

    def _tag_created_layers(self, name, args, res):
        """Records which layers a successful call read and tags every layer its result says it created (GitHub #150): sources are
        found by value, including list and nested arguments and SQL, and every created layer is tagged, not only `layer_name`."""
        from .lineage import created_layer_names, derive_sources, source_layer_ids, tag_layer_lineage
        try:
            from qgis.core import QgsProject
        except ImportError:
            return
        try:
            project = QgsProject.instance()
            known = [lyr.name() for lyr in project.mapLayers().values()]
            sources = derive_sources(name, args, known)
            source_ids = source_layer_ids(sources, project.mapLayers().values())
            for created in created_layer_names(res, sources, known):
                for layer in project.mapLayersByName(created)[:1]:
                    tag_layer_lineage(layer, name, args, sources, source_ids)
        except Exception as e:
            log_event("swallowed_exception", tag="Agent", tool="lineage_tagging",
                      error_class=type(e).__name__, error=True)

    _GROUNDING_PER_ITEM_CHARS = 60000
    _GROUNDING_TOTAL_CHARS = 400000

    def _remember_grounding(self, text):
        """Keeps `text` as evidence for the claim check, newest last, within a fixed total size. Never raises."""
        try:
            # setdefault, not a bare attribute: tests (and any subclass) build agents without running __init__.
            texts = self.__dict__.setdefault("_grounding_texts", [])
            texts.append(str(text)[:self._GROUNDING_PER_ITEM_CHARS])
            total = sum(len(t) for t in texts)
            while total > self._GROUNDING_TOTAL_CHARS and len(texts) > 1:
                total -= len(texts.pop(0))
        except Exception:
            pass

    def _guard_unbacked_data(self, final_text, turn_tool_log, turn_pending):
        """Appends a visible warning when the final answer contains a data table but a call this
        turn is still pending (waiting for the user, or blocked) or ended in an unresolved error --
        the table cannot have come from that call. Also counts a gate task still awaiting
        Confirm from an earlier turn. See services/response_guard.py (rc7 smoke test F03)."""
        pending = list(turn_pending)
        try:
            pending += [t.get("pending_tool") for t in self.task_manager.tasks
                        if t.get("status") == "PREVIEW_READY" and t.get("pending_tool")]
        except Exception:
            pass
        failed = []
        for i, (name, is_error, _msg) in enumerate(turn_tool_log):
            if is_error and not any(n == name and not e for n, e, _ in turn_tool_log[i + 1:]):
                failed.append(name)
        data_tool_ran = any((not is_error) and name not in response_guard.NO_DATA_TOOLS
                            for name, is_error, _msg in turn_tool_log)
        final_text = response_guard.apply_unbacked_data_warning(
            final_text, pending, failed, data_tool_ran, backed_by_success=data_tool_ran and not pending,
            evidence="\n".join(getattr(self, "_grounding_texts", [])))
        # #75: claims around real numbers that no tool returned (place names, national totals, terrain, file sizes).
        final_text = response_guard.apply_ungrounded_claims_note(
            final_text, "\n".join(getattr(self, "_grounding_texts", [])),
            data_tool_ran and not pending)   # a call still waiting on the user produced no data; the other guard covers it
        if pending:
            # F14: the app shows its own confirmation card for a pending call; drop the model's look-alike.
            final_text = response_guard.strip_confirmation_prose(final_text)
        return final_text

    def _sandbox_flailing_nudge(self, turn_tool_log):
        """Returns a corrective message to inject mid-turn, or None, when the most recent
        SANDBOX_FLAILING_THRESHOLD entries in turn_tool_log are all execute_pyqgis_script
        calls rejected by the safety sandbox specifically (an execute_pyqgis_script call
        that fails for some OTHER reason -- a real bug in the script, a missing layer --
        does not count; that's the model iterating on its own code, not flailing against a
        wall it can't get through). See SANDBOX_FLAILING_THRESHOLD's own comment for the
        live report this closes. Pure/deterministic, same "cheap code-level backstop, not a
        second agent" shape as _reconcile_final_text_with_tool_log above."""
        recent = turn_tool_log[-SANDBOX_FLAILING_THRESHOLD:]
        if len(recent) < SANDBOX_FLAILING_THRESHOLD:
            return None
        if not all(
            name == "execute_pyqgis_script" and is_error
            and isinstance(error_msg, str) and "rejected for safety" in error_msg
            for name, is_error, error_msg in recent
        ):
            return None
        return (
            f"You've made {SANDBOX_FLAILING_THRESHOLD} execute_pyqgis_script calls in a row, "
            "every one rejected by the safety sandbox. Stop trying to probe the filesystem or "
            "interpreter internals through it -- execute_pyqgis_script is a last resort, not a "
            "way to explore what data exists. If this task's directive already named specific "
            "tools to use, call those now. If you need data that isn't already in the project, "
            "use a registered acquisition tool (geocode_and_enrich/geocode_batch for named "
            "places, fetch_osm_features/search_hdx_datasets for real-world datasets) instead of "
            "searching for a local file that may not exist."
        )

    @staticmethod
    def _named_tool_drift_nudge(user_query, turn_tool_log, threshold=4):
        """A corrective message when the user NAMED a tool and `threshold` other tool calls have passed without it being called, else None.

        rc17 hand test B3: "call search_stac_satellite_imagery ..." took 15 tool calls (SQL, reports, severity, web search) before the
        named tool ran once, then the answer lost the result. Pure; the caller injects it at most once per turn."""
        from .task_matcher import named_tools
        wanted = named_tools(user_query)
        if not wanted or len(turn_tool_log) < threshold:
            return None
        called = {name for name, _err, _msg in turn_tool_log}
        if wanted & called:
            return None
        names = ", ".join(f"`{n}`" for n in sorted(wanted))
        return (f"The user's request named {names}, and {len(turn_tool_log)} other tool calls have run without it. Stop the unrelated "
                f"calls and call {names} now with the user's own inputs; if it cannot be called, say why in one sentence.")

    def run(self, user_query, map_context=None, should_stop=None, tool_step_callback=None):
        """Runs one request (see _run_impl for the full contract). Publishes should_stop and the
        status callback for the duration, so a long-running tool -- a network analysis over a
        national road network takes minutes -- can notice Stop and say what it is doing
        (cancel_signal.py). Before this, should_stop was only checked between tool calls, so a
        running tool could not be stopped and QGIS froze until it finished."""
        from . import cancel_signal, project_session
        # #147 (audit F11): bind this turn to the project that is open now. A project clear/read bumps the generation, which
        # both stops the turn at its next checkpoint (via the combined should_stop, also polled by long tools) and makes
        # _execute_tool / _append_history refuse to touch whatever project is open by then.
        captured = project_session.current()
        self._turn_project_session = captured

        def stop_or_stale():
            return project_session.is_stale(captured) or bool(should_stop is not None and should_stop())

        token = cancel_signal.begin(stop_or_stale, getattr(self.client, "_emit_status", None))
        try:
            return self._run_impl(user_query, map_context, stop_or_stale, tool_step_callback)
        finally:
            cancel_signal.end(token)
            self._turn_project_session = None

    def _run_impl(self, user_query, map_context=None, should_stop=None, tool_step_callback=None):
        """should_stop, if given, is a zero-arg callable returning True once the
        user has asked to abort (task_runner.py passes the running QgsTask's
        isCanceled()). Checked once per loop iteration -- this can't interrupt
        an in-flight API call or tool execution, but it does stop the agent
        from starting another one, which was previously not possible at all.

        tool_step_callback, if given, is called as tool_step_callback(name,
        status, error) around every individual tool call in the loop below --
        status is "running" right before execution and "done"/"failed" right
        after. This is what lets the UI show live per-step progress during a
        multi-tool-call turn (previously nothing was visible between "Thinking..."
        and the final answer, no matter how many tools ran in between). Wrapped
        in try/except so a UI-side rendering bug can never break the actual
        agent loop -- worst case is a missed visual update, not a failed turn."""
        from ..services.tool_router import ToolRouter
        # Structured-logging policy, 2026-09-20: every tool-call log line for this
        # turn carries the same correlation_id so a QgsMessageLog reader can group
        # them without any of the log content itself being the user's actual query.
        correlation_id = uuid.uuid4().hex[:8]
        provider_name = type(getattr(self, "client", None)).__name__
        # New turn -- undo must never reach back into a previous one (see
        # transactions.py's docstring).
        self._transaction_log.reset()
        # New turn -- a plan made last turn must not silently satisfy this turn's gate
        # (§1.6 option (b), plan_gate.py).
        self._plan_gate.reset()
        self._apply_auto_model_selection(user_query)
        user_message = {"role": "user", "content": user_query}

        # Correction detection (self-learning mechanism 2, 2026-09-02): a plain-
        # text heuristic over this new message, checked against the last tool
        # call this session actually made. Deliberately conservative and known-
        # imperfect -- see learning.py's module docstring for the honest caveat
        # (there's no ground truth for "the user meant this as a correction"
        # short of asking them). False negatives just mean nothing extra gets
        # remembered; false positives store an overly specific rule, which the
        # memory panel's Forget control (memory_dialog.py) lets the user remove.
        if learning.detect_correction(user_query) and self._last_tool_call:
            last_name, last_args = self._last_tool_call
            learning.record_correction_rule(self.memory_manager, user_query, last_name, last_args)
        # Router runs BEFORE build_system_prompt now (2026-09-12, prompt modularization --
        # following v1.13.1's fix to the same shape of problem on the tool-schema side): which
        # of the 47 base-prompt rules actually need sending depends on which tools this turn can
        # even reach, so the router's selection has to exist first. Nothing else depended on the
        # old ordering (confirmed by reading this whole function before reordering it).
        router = ToolRouter(TOOLS_SCHEMA)
        self._turn_counter = getattr(self, "_turn_counter", 0) + 1
        recent_names, recent_turn = getattr(self, "_recent_tools", ((), 0))
        # Only the last two turns count: a tool from twenty messages ago is not "what we were in the middle of".
        carry_over = recent_names if self._turn_counter - recent_turn <= 2 else ()
        active_tools = router.filter_relevant_tools(user_query, top_k=40, carry_over_tools=carry_over)
        active_tool_names = {
            t.get("function", {}).get("name", "") for t in active_tools if isinstance(t, dict)
        }

        # get_formatted_onboarding_context() does its own file read + QGIS_AVAILABLE guard and
        # never raises (see onboarding_profile.py) -- no try/except needed at this call site,
        # matching how map_context is passed through unguarded too.
        user_profile_ctx = onboarding_profile.get_formatted_onboarding_context()

        # §1.5 option (b): a deterministic Project Inspector snapshot (Layouts/Themes/Metadata),
        # run BEFORE the first LLM call of this turn -- exactly the "Project Inspector" stage's
        # own description: a snapshot step, not a reasoning step. Feature-flagged off by default,
        # same as plan_gate.py's §1.6 sibling; see project_inspector.py's module docstring for
        # why this is kept separate from map_context (already always-on) rather than merged into it.
        project_inspector_ctx = None
        if self._is_project_inspector_enabled():
            from ..services.project_inspector import inspect_project
            project_inspector_ctx = inspect_project()

        system_prompt_content = build_system_prompt(
            self.task_manager, self.memory_manager, map_context, user_profile_ctx=user_profile_ctx,
            active_tool_names=active_tool_names, project_inspector_ctx=project_inspector_ctx,
        )

        self._remember_grounding(user_query)
        self._remember_grounding(map_context)
        messages = [{"role": "system", "content": system_prompt_content}]
        messages.extend(self._read_history_snapshot())
        messages.append(user_message)

        self._get_usage_tracker().begin_turn()
        max_rounds, max_turn_tokens = self._turn_limits()
        final_text = None
        # (name, is_error, error_message) for every tool call made in THIS turn --
        # feeds _reconcile_final_text_with_tool_log's code-level backstop below.
        turn_tool_log = []
        # Tools whose call this turn did NOT run (waiting for the user's Confirm, or blocked) and
        # have not since succeeded -- feeds response_guard's unbacked-data warning below.
        turn_pending = []
        # One-shot flag for _sandbox_flailing_nudge below -- the nudge is a single course-
        # correction attempt, not a repeating scold on every iteration if the model keeps
        # flailing anyway (MAX_ITERATIONS' own hard cutoff still applies either way).
        sandbox_flailing_nudged = False
        drift_nudged = False

        token_budget_hit = False
        for iteration_index in range(max_rounds):
            if max_turn_tokens and iteration_index > 0 and self._get_usage_tracker().turn_tokens() >= max_turn_tokens:
                token_budget_hit = True
                break
            if should_stop is not None and should_stop():
                final_text = "[Agent stopped] Stopped by user."
                self._append_history(user_message, {"role": "assistant", "content": final_text})
                return final_text
            # Pacing (2026-09-12, see PACING_THRESHOLD_ITERATIONS's own comment): a normal,
            # small turn (<=3 tool-call rounds) never reaches here -- only once a turn is
            # genuinely getting large does it start spacing its own remaining API calls out,
            # reducing the chance of ever tripping a provider's requests-per-minute limit in
            # the first place, proportional to how large the task actually is.
            if iteration_index >= PACING_THRESHOLD_ITERATIONS:
                time.sleep(PACING_DELAY_SECONDS)
            try:
                result = self.client.complete(
                    messages, tools=active_tools, max_tokens=_max_tokens_for_iteration(iteration_index)
                )
            except Exception as e:
                return f"[API error] {e}"

            if not isinstance(result, dict):
                return "[API error] Unexpected response from model client."
            if "error" in result:
                return f"[API error] {result['error']}"
            self._accumulate_usage(result.get("usage"))

            message = result.get("message")
            if not isinstance(message, dict):
                return "[API error] Missing message in model response."
            messages.append(message)

            tool_calls = message.get("tool_calls")
            if not tool_calls:
                content = message.get("content")
                if content is None or (isinstance(content, str) and not content.strip()):
                    final_text = EMPTY_RESPONSE_FALLBACK
                else:
                    final_text = content
                final_text = self._reconcile_final_text_with_tool_log(final_text, turn_tool_log)
                final_text = self._guard_unbacked_data(final_text, turn_tool_log, turn_pending)
                self._append_history(user_message, {"role": "assistant", "content": final_text})
                return final_text

            for call in tool_calls:
                # QGIS-003, 2026-09-13 audit: should_stop was only checked once per LLM
                # round, at the top of the OUTER loop -- a multi-tool-call batch in one
                # response (common: buffer -> clip -> export style requests) couldn't be
                # interrupted mid-batch; the Stop button's own docstring claimed it "stops
                # before the next LLM call/tool step," but the "tool step" half overstated
                # what actually happened. Checked here too, so a stop request takes effect
                # before the NEXT tool call in the same batch, not just the next LLM call.
                if should_stop is not None and should_stop():
                    final_text = "[Agent stopped] Stopped by user."
                    self._append_history(user_message, {"role": "assistant", "content": final_text})
                    return final_text
                fn = call.get("function", {}) if isinstance(call, dict) else {}
                name = fn.get("name", "")
                arguments = fn.get("arguments", "{}")
                # Permanent, lightweight trace of every tool call the agent makes -- added
                # specifically to diagnose a reported (but never reproduced with a raw trace)
                # bug where the model's final text claimed a "backend issue" and offered a
                # manual script even though the actual tool call had succeeded. If that
                # recurs, this sequence in the QGIS Python Console will show whether an
                # earlier call in the same turn errored and the model silently recovered
                # from it without updating its final summary to match.
                #
                # Structured-logging policy, 2026-09-20 audit (strict option chosen): this
                # used to log the tool's actual arguments/result content (secret-redacted,
                # but still free-form -- names, coordinates, file paths, feature attributes
                # could all appear here). log_event below logs ONLY tool name, status,
                # duration, correlation_id, provider, and (on failure) an error class --
                # never argument/result content. See core/logger.py's log_event docstring.
                # Use log_diagnostic() (off by default) if raw content is ever needed while
                # actively debugging a specific issue locally.
                log_event("tool_call", tag="Agent", tool=name, status="running",
                           correlation_id=correlation_id, provider=provider_name)
                if tool_step_callback is not None:
                    try:
                        tool_step_callback(name, "running", None)
                    except Exception:
                        pass
                _tool_start = time.monotonic()
                tool_result = self._execute_tool(name, arguments)
                _duration_ms = int((time.monotonic() - _tool_start) * 1000)
                # Put "this call did not run" into the data the model reasons over, not only
                # in a rule it may not weigh (rc7 smoke test F03: it invented the missing rows).
                tool_result = response_guard.annotate_not_run(tool_result)
                is_error = tool_results.is_error(tool_result)
                turn_tool_log.append((name, is_error, tool_results.error_of(tool_result)))
                self._recent_tools = (tuple(dict.fromkeys(n for n, _e, _m in turn_tool_log))[-8:], self._turn_counter)
                _status = tool_results.status_of(tool_result)
                if _status in response_guard.NOT_RUN_STATUSES:
                    turn_pending.append(name)
                elif not is_error and name in turn_pending:
                    turn_pending = [n for n in turn_pending if n != name]
                if is_error:
                    error_class = tool_results.error_class_of(tool_result)
                    log_event("tool_call", tag="Agent", tool=name, status="failed",
                               duration_ms=_duration_ms, correlation_id=correlation_id,
                               provider=provider_name, error_class=error_class, error=True)
                else:
                    log_event("tool_call", tag="Agent", tool=name, status="done",
                               duration_ms=_duration_ms, correlation_id=correlation_id,
                               provider=provider_name)
                if tool_step_callback is not None:
                    try:
                        tool_step_callback(name, "failed" if is_error else "done", tool_results.error_of(tool_result))
                    except Exception:
                        pass
                try:
                    serialized = json.dumps(tool_result, default=str)
                except Exception as e:
                    serialized = json.dumps({"error": f"Could not serialize tool result: {e}"})
                self._remember_grounding(serialized)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", "") if isinstance(call, dict) else "",
                    "name": name,
                    "content": serialized,
                })

            # Mid-turn context compaction (see MAX_FULL_TOOL_RESULTS_PER_TURN's own comment) --
            # once per iteration, after this iteration's own tool results are appended, so a
            # large task's per-call payload to the model stays bounded for the rest of the turn.
            self._compact_old_tool_results(messages)

            if not sandbox_flailing_nudged:
                nudge = self._sandbox_flailing_nudge(turn_tool_log)
                if nudge:
                    messages.append({"role": "user", "content": nudge})
                    sandbox_flailing_nudged = True
            if not drift_nudged:
                drift = self._named_tool_drift_nudge(user_query, turn_tool_log)
                if drift:
                    messages.append({"role": "user", "content": drift})
                    drift_nudged = True

        # Save this attempt to history even though it didn't finish -- otherwise a retry
        # starts with zero memory of what was already tried and can repeat the exact same
        # doomed step-per-item approach (e.g. one tool call per item in a long list)
        # instead of the more efficient path rule 14 in the system prompt asks for.
        if token_budget_hit:
            final_text = (
                "[Agent stopped] This request used its token budget (%s tokens, setting "
                "cartogen_ai/max_turn_tokens) before finishing. Break it into smaller pieces, or raise the budget "
                "in QGIS's advanced settings." % f"{max_turn_tokens:,}")
            self._append_history(user_message, {"role": "assistant", "content": final_text})
            return final_text
        final_text = (
            "[Agent stopped] Reached the tool-call limit for this request before finishing. This usually "
            "means the request needed many individual actions (e.g. one call per item in a long list). Try "
            "rephrasing so it can be done in bulk (e.g. \"create one layer with all of them\"), or break the "
            "request into smaller pieces."
        )
        self._append_history(user_message, {"role": "assistant", "content": final_text})
        return final_text
