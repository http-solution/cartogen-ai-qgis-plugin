# -*- coding: utf-8 -*-
"""
Core CartogenAi class for Cartogen AI.
Integrates Multi-LLM provider clients, Spatial Memory Engine,
Task List Manager, and Thread-Safe Tool Dispatching.
"""

import json

try:
    from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot, Qt, QThread
    from qgis.core import QgsSettings
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    class QObject:
        pass
    def pyqtSignal(*args, **kwargs):
        class SignalMock:
            def emit(self, *a, **kw): pass
            def connect(self, *a, **kw): pass
        return SignalMock()
    def pyqtSlot(*args, **kwargs):
        return lambda fn: fn
    class Qt:
        # Mirrors the Qt6 shape the real code now uses. The plugin reaches enum
        # members through their enum type (Qt.ConnectionType.X) because Qt6
        # requires it, so this stub has to expose the nested type too -- not
        # just the flat name -- or every no-QGIS path that builds a
        # ToolDispatcher raises AttributeError. Caught by the test suite:
        # 21 tests in test_new_tools.py failed on
        # "type object 'Qt' has no attribute 'ConnectionType'".
        # The flat alias is kept so any older call site still resolves.
        class ConnectionType:
            BlockingQueuedConnection = 1

        BlockingQueuedConnection = 1
    class QThread:
        @staticmethod
        def currentThread():
            return None
    class QgsSettings:
        def value(self, k, default=""): return default
        def setValue(self, k, v): pass

from .providers import (
    OpenRouterClient, GeminiClient, OllamaClient, OpenAIClient, ClaudeClient, CartogenClient,
)
from .providers.cartogen import FALLBACK_MODELS as CARTOGEN_FALLBACK_MODELS
from .model_selector import AUTO_SENTINEL, classify_complexity, pick_model_for_complexity
from .memory import SpatialMemoryManager
from .task_manager import AgentTaskManager
from .prompts import build_system_prompt
from .tools import TOOL_REGISTRY, TOOLS_SCHEMA
from .tools.task_tools import bind_agent_context
from . import learning

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
TWO_PHASE_TOOLS = frozenset({"add_layer_from_path", "fetch_geoboundaries", "fetch_hdx_admin_boundaries", "fetch_building_footprints", "fetch_worldpop_population", "gemini_grounded_search", "openai_grounded_search"})


class ToolDispatcher(QObject):
    # The result-container parameter is `object`, NOT `list` -- this is the actual fix for
    # a confirmed bug (diagnosed live, not guessed): PyQt's `list`-typed signal parameters
    # get converted to QVariantList for queued delivery and reconstructed as a NEW Python
    # list on the receiving side, so `result_container.append(...)` inside the slot mutated
    # a copy, never the original list the caller kept waiting on -- the slot always computed
    # the right answer, but the caller always saw an empty list and fell through to the
    # generic "Execution failed unexpectedly." PyQt's `object` type is specifically exempt
    # from QVariant round-tripping and preserves exact Python object identity across queued
    # connections (including BlockingQueuedConnection), which is what this "mutate a
    # container to get a result back across threads" pattern actually requires.
    request_execution = pyqtSignal(str, object, object)
    request_callable = pyqtSignal(object, object, object)

    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        # Connect to slots on the thread where this object was created (main Qt thread).
        self.request_execution.connect(self._do_execute, Qt.ConnectionType.BlockingQueuedConnection)
        self.request_callable.connect(self._do_execute_callable, Qt.ConnectionType.BlockingQueuedConnection)

    @pyqtSlot(str, object, object)
    def _do_execute(self, name, arguments, result_container):
        try:
            result_container.append(self.agent._real_execute_tool(name, arguments))
        except Exception as e:
            result_container.append({"error": f"_do_execute raised: {e}"})

    @pyqtSlot(object, object, object)
    def _do_execute_callable(self, func, arg, result_container):
        try:
            result_container.append(func(arg))
        except Exception as e:
            result_container.append({"error": str(e)})


MAX_HISTORY_MESSAGES = 20
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


class CartogenAi:
    def __init__(self):
        from .auth import CredentialManager
        settings = QgsSettings()
        provider_name = settings.value("cartogen_ai/provider", "openrouter")
        key = CredentialManager.get_credential(provider_name)

        # When a model setting is the "auto" sentinel, use the provider's normal
        # default as a safe starting model, but remember to re-pick per request
        # in run() based on query complexity (see _apply_auto_model_selection).
        self._auto_model_provider = None

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
                return safe_starting_model
            return raw or safe_starting_model

        if provider_name == "gemini":
            gemini_model = resolve_model("cartogen_ai/gemini_model", "gemini-flash-latest")
            self.client = GeminiClient(api_key=key, model=gemini_model)
        elif provider_name == "ollama":
            url = key if key else "http://localhost:11434/v1/chat/completions"
            if not url.endswith("chat/completions"):
                url = url.rstrip("/") + "/v1/chat/completions"
            ollama_model = resolve_model("cartogen_ai/ollama_model", "llama3.1", default_to_auto=False)
            self.client = OllamaClient(endpoint_url=url, model=ollama_model)
        elif provider_name == "openai":
            openai_model = resolve_model("cartogen_ai/openai_model", "gpt-5.6")
            self.client = OpenAIClient(api_key=key, model=openai_model)
        elif provider_name == "claude":
            claude_model = resolve_model("cartogen_ai/claude_model", "claude-opus-5")
            self.client = ClaudeClient(api_key=key, model=claude_model)
        elif provider_name == "cartogen":
            cartogen_model = resolve_model("cartogen_ai/cartogen_model", CARTOGEN_FALLBACK_MODELS[0])
            # No gateway is deployed anywhere this repo can reach yet (see
            # providers/cartogen.py's module docstring) -- gateway_url stays None
            # (client falls back to its own GATEWAY_BASE_URL placeholder) unless
            # someone has explicitly set this for local/self-hosted testing.
            gateway_url = settings.value("cartogen_ai/cartogen_gateway_url", None) or None
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
            openrouter_model = settings.value("cartogen_ai/openrouter_model", AUTO_SENTINEL)
            if openrouter_model and openrouter_model != AUTO_SENTINEL:
                self.client = OpenRouterClient(api_key=key, model=openrouter_model)
            else:
                self.client = OpenRouterClient(api_key=key)

        self.memory_manager = SpatialMemoryManager()
        self.task_manager = AgentTaskManager()

        # Bind active task and memory managers to task tool execution handlers
        bind_agent_context(self.task_manager, self.memory_manager)

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
        self.dispatcher = ToolDispatcher(self)

        # Session-scoped token usage totals (docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md
        # SS3.2: "no cost/usage visibility in the UI despite real, documented cost-
        # engineering work"). Not persisted across QGIS restarts or project
        # switches -- this agent instance IS the session (see _get_agent() in
        # plugin_main.py), so a fresh instance naturally means a fresh count,
        # matching how a user would think about "this session's usage."
        # calls_without_usage tracks turns where the provider's response didn't
        # include token counts at all, so the UI can caveat the total as a
        # partial figure instead of presenting it as exact when it isn't.
        self.session_usage = {"input_tokens": 0, "output_tokens": 0, "calls_with_usage": 0, "calls_without_usage": 0}

    @property
    def tools_schema(self):
        return TOOLS_SCHEMA

    def clear_history(self):
        self.conversation_history = []
        self.task_manager.clear_plan()

    def _accumulate_usage(self, usage):
        """Adds one API call's token usage into the session running total.
        usage is either the normalized {'input_tokens', 'output_tokens'} dict a
        provider's complete() returns, or None if that provider/response didn't
        report it -- counted separately (calls_without_usage) rather than as
        zero, so get_session_usage_text() can honestly caveat the total instead
        of understating it.

        Lazily initializes session_usage if missing rather than assuming
        __init__ ran -- tests/test_agent_runner.py's _make_bare_agent()
        constructs a CartogenAi via __new__() (bypassing __init__ entirely)
        to isolate run()'s tool-calling loop from real provider/task-manager
        setup, a pattern this shouldn't have to know about or require every
        such bare-agent helper to replicate."""
        if not hasattr(self, "session_usage"):
            self.session_usage = {"input_tokens": 0, "output_tokens": 0, "calls_with_usage": 0, "calls_without_usage": 0}
        if isinstance(usage, dict) and ("input_tokens" in usage or "output_tokens" in usage):
            self.session_usage["input_tokens"] += usage.get("input_tokens") or 0
            self.session_usage["output_tokens"] += usage.get("output_tokens") or 0
            self.session_usage["calls_with_usage"] += 1
        else:
            self.session_usage["calls_without_usage"] += 1

    def get_session_usage_text(self):
        """Short, human-readable summary of this session's token usage for
        ui/dock_widget.py's usage_label -- e.g. '~4,230 tokens this session
        (12 calls)' or '~4,230 tokens this session (12 calls; 3 calls with no
        usage reported)' once at least one provider call has actually reported
        usage. Returns None (not a misleading '0 tokens') if no call so far
        has reported usage at all -- e.g. a fresh session, or a provider/model
        that never reports it. Intentionally no dollar-cost estimate: accurate
        per-model pricing across 5 providers would need a pricing table that's
        guaranteed to go stale and mislead; see
        docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md's reasoning for a similar
        accuracy-over-completeness call on a different feature."""
        u = getattr(self, "session_usage", None)
        if u is None:
            return None
        if u["calls_with_usage"] == 0:
            return None
        total = u["input_tokens"] + u["output_tokens"]
        text = f"~{total:,} tokens this session ({u['calls_with_usage']} calls)"
        if u["calls_without_usage"] > 0:
            text = (
                f"~{total:,} tokens this session ({u['calls_with_usage']} calls; "
                f"{u['calls_without_usage']} call(s) with no usage reported)"
            )
        return text

    def reload_chat_history(self):
        """Re-reads project-bound chat history from QgsProject. Call this after
        the active QGIS project changes (readProject/cleared signals) -- the
        agent instance is cached and reused across projects (see _get_agent()
        in plugin_main.py), so without this its conversation_history would
        stay stuck on whichever project was active when it was constructed.
        Must be called from the main Qt thread (QgsProject is not thread-safe)."""
        from .chat_persistence import load_chat_history
        self.conversation_history = load_chat_history()

    def _real_execute_tool(self, name, arguments, user_confirmed: bool = False):
        from .lineage import tag_layer_lineage
        try:
            from qgis.core import QgsProject
        except ImportError:
            QgsProject = None

        func = TOOL_REGISTRY.get(name)
        if func is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            args = arguments if isinstance(arguments, dict) else json.loads(arguments or "{}")
        except (TypeError, ValueError) as e:
            return {"error": f"Invalid tool arguments: {e}"}

        # Dispatcher-level schema enforcement: filter out any argument keys not in the registered tool schema
        schema_props = {}
        for item in TOOLS_SCHEMA:
            fn_def = item.get("function", {})
            if fn_def.get("name") == name:
                schema_props = fn_def.get("parameters", {}).get("properties", {})
                break

        # Strip unadvertised arguments (prevents model self-approval via injected parameters)
        filtered_args = {k: v for k, v in args.items() if k in schema_props}
        if user_confirmed:
            filtered_args["confirmed"] = True

        try:
            res = func(**filtered_args)
            if isinstance(res, dict):
                if res.get("status") == "PREVIEW_REQUIRED":
                    # Register preview safety task in TaskManager
                    if not self.task_manager.tasks:
                        self.task_manager.create_plan(
                            f"Safety Gate Preview: {name}",
                            [f"Preview {name} operation"]
                        )
                    self.task_manager.set_task_preview(
                        task_id=self.task_manager.tasks[0]["id"] if self.task_manager.tasks else "1",
                        code_snippet=res.get("code_snippet", ""),
                        rationale=res.get("rationale", ""),
                        is_destructive=res.get("is_destructive", True)
                    )
                    # Attach pending execution arguments to task object
                    if self.task_manager.tasks:
                        self.task_manager.tasks[0]["pending_tool"] = name
                        self.task_manager.tasks[0]["pending_args"] = res.get("arguments", {**args, "confirmed": True})

                elif res.get("success"):
                    self.memory_manager.log_spatial_action(name, str(args))
                    learning.record_tool_usage(self.memory_manager, name)
                    learning.maybe_infer_preferences(self.memory_manager)
                    self._last_tool_call = (name, args)
                    created_layer_name = res.get("layer_name")
                    if created_layer_name and QgsProject is not None:
                        layers = QgsProject.instance().mapLayersByName(created_layer_name)
                        if layers:
                            source_layers = [v for k, v in args.items() if isinstance(v, str) and "layer" in k]
                            tag_layer_lineage(layers[0], name, args, source_layers)
                    if name not in TASK_MANAGEMENT_TOOLS:
                        self.task_manager.auto_advance_if_unambiguous(f"{name} succeeded", tool_name=name)
            return res
        except TypeError as e:
            return {"error": f"Invalid arguments for {name}: {e}"}
        except Exception as e:
            return {"error": f"Tool {name} failed: {e}"}

    def _on_dispatcher_thread(self):
        """True if the calling thread is already the dispatcher's own thread (normally
        the main Qt thread)."""
        try:
            return QThread.currentThread() == self.dispatcher.thread()
        except Exception:
            return False

    def _execute_tool(self, name, arguments):
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
        return {"error": "Execution failed unexpectedly."}

    def _get_schema_props(self, name):
        for item in TOOLS_SCHEMA:
            fn_def = item.get("function", {})
            if fn_def.get("name") == name:
                return fn_def.get("parameters", {}).get("properties", {})
        return {}

    def _run_on_main_thread(self, func, arg):
        if self._on_dispatcher_thread():
            try:
                return func(arg)
            except Exception as e:
                return {"error": str(e)}

        result = []
        self.dispatcher.request_callable.emit(func, arg, result)
        if result:
            return result[0]
        return {"error": "Execution failed unexpectedly."}

    def _log_tool_success(self, name, args, res):
        """Mirrors _real_execute_tool's success-path side effects (spatial memory
        log + layer lineage tagging) for TWO_PHASE_TOOLS, which don't go through
        _real_execute_tool directly. Kept as a separate small helper rather than
        refactoring _real_execute_tool itself, to avoid touching that already
        security-critical, well-tested code path."""
        if not (isinstance(res, dict) and res.get("success")):
            return
        from .lineage import tag_layer_lineage
        try:
            from qgis.core import QgsProject
        except ImportError:
            QgsProject = None
        self.memory_manager.log_spatial_action(name, str(args))
        created_layer_name = res.get("layer_name")
        if created_layer_name and QgsProject is not None:
            layers = QgsProject.instance().mapLayersByName(created_layer_name)
            if layers:
                source_layers = [v for k, v in args.items() if isinstance(v, str) and "layer" in k]
                tag_layer_lineage(layers[0], name, args, source_layers)
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
                    lambda a: add_layer_from_path(a["file_path"], a.get("layer_name")),
                    {"file_path": local_path, "layer_name": filtered_args.get("layer_name")},
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

        if name == "fetch_geoboundaries":
            from .tools.humanitarian_tools import (
                fetch_geoboundaries_network_phase, add_geoboundaries_layer_main_thread_phase,
            )
            fetch_result = fetch_geoboundaries_network_phase(
                filtered_args.get("iso3", ""), filtered_args.get("admin_level", "ADM1")
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
                filtered_args.get("iso3", ""), filtered_args.get("admin_level", "ADM1")
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
                filtered_args.get("max_features", 5000),
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
            )
            fetch_result = fetch_worldpop_population_network_phase(
                filtered_args.get("iso3", ""), filtered_args.get("year")
            )
            # No cleanup here, deliberately -- unlike fetch_geoboundaries above,
            # the downloaded file must stay on disk for as long as the raster
            # layer exists (see add_worldpop_population_layer_main_thread_phase).
            res = self._run_on_main_thread(add_worldpop_population_layer_main_thread_phase, fetch_result)
            self._log_tool_success(name, filtered_args, res)
            return res

        if name == "gemini_grounded_search":
            # Reversed order vs the other two-phase tools: the QGIS-touching part
            # (reading provider/model/credential from QgsSettings/QgsAuthManager)
            # is fast and goes first on the main thread; the slow network call
            # to Gemini goes second, on the calling (background) thread.
            from .tools.system_tools import resolve_gemini_search_config
            from .providers.gemini import grounded_search
            config = self._run_on_main_thread(lambda _: resolve_gemini_search_config(), None)
            if "error" in config:
                return config
            return grounded_search(config["api_key"], filtered_args.get("query", ""), model=config["model"])

        if name == "openai_grounded_search":
            # Same two-phase split as gemini_grounded_search above.
            from .tools.system_tools import resolve_openai_search_config
            from .providers.openai import grounded_search
            config = self._run_on_main_thread(lambda _: resolve_openai_search_config(), None)
            if "error" in config:
                return config
            return grounded_search(config["api_key"], filtered_args.get("query", ""))

        return {"error": f"Unknown two-phase tool: {name}"}

    def _trim_history(self):
        if len(self.conversation_history) > MAX_HISTORY_MESSAGES:
            self.conversation_history = self.conversation_history[-MAX_HISTORY_MESSAGES:]

    def _apply_auto_model_selection(self, user_query):
        """If the active provider's model setting is "auto", pick a concrete
        model from the live list fetched in Settings, based on how complex
        this query looks. Never invents a model -- if no live list was ever
        fetched, this is a silent no-op and the provider's normal default
        (already set in __init__) keeps being used."""
        if not self._auto_model_provider:
            return
        try:
            settings = QgsSettings()
            raw_list = settings.value(f"cartogen_ai/{self._auto_model_provider}_model_list", "")
            model_ids = json.loads(raw_list) if raw_list else []
            if not model_ids:
                return
            complexity = classify_complexity(user_query)
            picked = pick_model_for_complexity(model_ids, complexity)
            if picked:
                self.client.model = picked
                if hasattr(self.client, "_emit_status"):
                    self.client._emit_status(f"Auto-selected {picked} ({complexity} request)")
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

    def run(self, user_query, map_context=None, should_stop=None, tool_step_callback=None):
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
        from .tool_router import ToolRouter
        self._apply_auto_model_selection(user_query)
        user_message = {"role": "user", "content": user_query}

        # Correction detection (self-learning mechanism 2, 2026-09-02): a plain-
        # text heuristic over this new message, checked against the last tool
        # call this session actually made. Deliberately conservative and known-
        # imperfect -- see learning.py's module docstring for the honest caveat
        # (there's no ground truth for "the user meant this as a correction"
        # short of asking them). False negatives just mean nothing extra gets
        # remembered; false positives store an overly specific rule, which the
        # memory panel's Forget control (tasks_tab_widget.py) lets the user remove.
        if learning.detect_correction(user_query) and self._last_tool_call:
            last_name, last_args = self._last_tool_call
            learning.record_correction_rule(self.memory_manager, user_query, last_name, last_args)
        system_prompt_content = build_system_prompt(self.task_manager, self.memory_manager, map_context)
        
        messages = [{"role": "system", "content": system_prompt_content}]
        messages.extend(self.conversation_history)
        messages.append(user_message)

        router = ToolRouter(TOOLS_SCHEMA)
        active_tools = router.filter_relevant_tools(user_query, top_k=40)

        final_text = None
        # (name, is_error, error_message) for every tool call made in THIS turn --
        # feeds _reconcile_final_text_with_tool_log's code-level backstop below.
        turn_tool_log = []

        for _ in range(MAX_ITERATIONS):
            if should_stop is not None and should_stop():
                final_text = "[Agent stopped] Stopped by user."
                self.conversation_history.append(user_message)
                self.conversation_history.append({"role": "assistant", "content": final_text})
                self._trim_history()
                return final_text
            try:
                result = self.client.complete(messages, tools=active_tools)
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
                self.conversation_history.append(user_message)
                self.conversation_history.append({"role": "assistant", "content": final_text})
                self._trim_history()
                return final_text

            for call in tool_calls:
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
                print(f"[Agent] Tool call: {name}({str(arguments)[:300]})")
                if tool_step_callback is not None:
                    try:
                        tool_step_callback(name, "running", None)
                    except Exception:
                        pass
                tool_result = self._execute_tool(name, arguments)
                is_error = isinstance(tool_result, dict) and "error" in tool_result
                turn_tool_log.append((name, is_error, tool_result.get("error") if is_error else None))
                print(f"[Agent] Tool {name} {'FAILED' if is_error else 'succeeded'}: {str(tool_result)[:300]}")
                if tool_step_callback is not None:
                    try:
                        tool_step_callback(name, "failed" if is_error else "done", tool_result.get("error") if is_error else None)
                    except Exception:
                        pass
                try:
                    serialized = json.dumps(tool_result, default=str)
                except Exception as e:
                    serialized = json.dumps({"error": f"Could not serialize tool result: {e}"})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", "") if isinstance(call, dict) else "",
                    "name": name,
                    "content": serialized,
                })

        # Save this attempt to history even though it didn't finish -- otherwise a retry
        # starts with zero memory of what was already tried and can repeat the exact same
        # doomed step-per-item approach (e.g. one tool call per item in a long list)
        # instead of the more efficient path rule 14 in the system prompt asks for.
        final_text = (
            "[Agent stopped] Reached the tool-call limit for this request before finishing. This usually "
            "means the request needed many individual actions (e.g. one call per item in a long list). Try "
            "rephrasing so it can be done in bulk (e.g. \"create one layer with all of them\"), or break the "
            "request into smaller pieces."
        )
        self.conversation_history.append(user_message)
        self.conversation_history.append({"role": "assistant", "content": final_text})
        self._trim_history()
        return final_text
