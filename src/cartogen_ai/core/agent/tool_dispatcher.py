# -*- coding: utf-8 -*-
"""
Thread-safe tool dispatch for Cartogen AI.

Extracted from agent.py (2026-09-20, Phase 11 architecture restructuring --
docs/IMPLEMENTATION_TRACKER.md §4) as the first of that file's god-class-decomposition
targets: ToolDispatcher was already a fully self-contained class (only ever touching the
`agent` object passed to its constructor via duck typing, never CartogenAi's internals
directly), so moving it out is a pure file move with zero behavior change -- unlike
history/usage tracking, which are woven through CartogenAi's shared, lock-guarded
conversation_history state and would need real interface design, not just a cut-paste, to
split safely. See that section's own note on why the harder half of the split (history_
manager.py, usage_tracker.py, the agent.py -> agent_orchestrator.py rename) is deliberately
scoped out of this pass.
"""

try:
    from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot, Qt
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
