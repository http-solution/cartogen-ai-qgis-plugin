"""Import-direction and import-cycle guard (PLAN-040, stage 0).

Why: the layering described in CLAUDE.md was only a convention; `test_architecture_boundaries.py` checks that names are exported, not which way
imports point. The audit (tools/structure_audit.py) found 17 edges pointing the wrong way. Stage 3 removed nine by moving three stdlib-only
leaf modules (`cancel_signal`, `model_selector`, `tool_operations`) from `core/agent/` to `core/`.

How it works: a ratchet. Rules that the code already satisfies are hard. The few edges that still break a rule are listed below with the reason;
a listed edge that no longer exists FAILS this test, so the list can only get shorter, and a new offending edge fails too.

The layers, low to high: `infrastructure` and `core/models` and `core/validators` (data and plumbing) < `core/services` and
`core/representation` < `core/agent` and its `tools` < `core/ui`. `core/net.py`, `core/logger.py` and the other `core/*.py` leaves must not
reach up into the agent, the tools or the UI. `settings_keys` (constants only) may be imported from anywhere."""
import collections
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("structure_audit", ROOT / "tools" / "structure_audit.py")
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

PREFIX = "cartogen_ai."

# area -> areas it must not import (module-level or inside functions)
FORBIDDEN = {
    "infrastructure": {"ui", "agent", "tools", "services", "representation"},
    "core-root": {"ui", "agent", "tools"},
    "models": {"ui", "agent", "tools", "services", "representation"},
    "validators": {"ui", "agent", "tools", "services", "representation"},
    "services": {"ui"},
    "representation": {"ui"},
    "agent": {"ui"},
    "tools": {"ui"},
}

# Edges that still break a rule. Remove a line when the edge is fixed; the test fails if a listed edge is gone.
KNOWN_VIOLATIONS = set()

# Modules that take part in an import cycle only through imports made inside functions (lazy imports). No module may join a cycle, and a
# module that leaves one must be removed from this set. Stage 2 of the plan removes the styling cluster.
KNOWN_CYCLIC_MODULES = {
    "core.agent.tools.analysis_tools", "core.agent.tools.data_source_tools", "core.agent.tools.export_tools",
    "core.agent.tools.humanitarian_style", "core.agent.tools.layout_credits", "core.agent.tools.layout_style",
    "core.agent.tools.logistics_tools", "core.agent.tools.multimodal_remote_sensing", "core.agent.tools.output_style",
    "core.agent.tools.raster_tools", "core.agent.tools.styling_tools", "core.agent.tools.table_importers",
    "core.agent.tools.vector_tools",
    "core.agent.agent_orchestrator", "core.agent.prompts", "core.agent.tools", "core.agent.tools.data_export_tools",
}


def _area(module):
    name = module[len(PREFIX):] if module.startswith(PREFIX) else module
    for start, area in (("infrastructure", "infrastructure"), ("processing", "processing"), ("core.ui", "ui"),
                        ("core.agent.tools", "tools"), ("core.agent", "agent"), ("core.models", "models"),
                        ("core.validators", "validators"), ("core.services", "services"),
                        ("core.representation", "representation")):
        if name == start or name.startswith(start + "."):
            return area
    return "core-root" if name.startswith("core") else "root"


def _short(module):
    return module[len(PREFIX):] if module.startswith(PREFIX) else module


class TestImportArchitecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mods = audit._modules()
        cls.top, cls.lazy = audit._edges(cls.mods)
        cls.all_edges = collections.defaultdict(set)
        for edges in (cls.top, cls.lazy):
            for src, targets in edges.items():
                cls.all_edges[src] |= targets

    def test_no_import_time_cycles(self):
        cycles = audit._cycles(self.mods, self.top)
        self.assertEqual(cycles, [], "modules import each other when loaded: " + "; ".join(", ".join(map(_short, c)) for c in cycles))

    def test_no_module_joins_an_import_cycle_and_none_is_left_listed_after_leaving_one(self):
        cyclic = {m for group in audit._cycles(self.mods, self.all_edges) for m in group}
        shortened = {_short(m) for m in cyclic}
        self.assertEqual(sorted(shortened - KNOWN_CYCLIC_MODULES), [], "new module in an import cycle (use a lazy import the other way, or move shared code to a leaf)")
        self.assertEqual(sorted(KNOWN_CYCLIC_MODULES - shortened), [], "no longer in a cycle: remove it from KNOWN_CYCLIC_MODULES")

    def test_imports_point_the_right_way(self):
        found = set()
        for src, targets in self.all_edges.items():
            banned = FORBIDDEN.get(_area(src), ())
            for target in targets:
                if _area(target) in banned and not target.endswith("infrastructure.settings_keys"):
                    found.add((_short(src), _short(target)))
        self.assertEqual(sorted(found - KNOWN_VIOLATIONS), [], "new import against the layering (see the module docstring)")
        self.assertEqual(sorted(KNOWN_VIOLATIONS - found), [], "fixed: remove it from KNOWN_VIOLATIONS")

    def test_the_moved_modules_still_answer_to_their_old_names_and_share_state(self):
        import sys

        from cartogen_ai.core import cancel_signal, model_selector, tool_operations
        from cartogen_ai.core.agent import cancel_signal as old_cancel
        from cartogen_ai.core.agent import model_selector as old_selector
        from cartogen_ai.core.agent import tool_operations as old_ops
        self.assertIs(old_cancel, cancel_signal)
        self.assertIs(old_selector, model_selector)
        self.assertIs(old_ops, tool_operations)
        self.assertIs(sys.modules["cartogen_ai.core.agent.cancel_signal"], cancel_signal)


class TestCheckRunnersAreRegisteredByTheTools(unittest.TestCase):
    def test_importing_the_tools_registers_the_checks_the_model_cannot_import(self):
        from cartogen_ai.core.agent.tools import qa_checklist_tools, vector_tools  # noqa: F401
        from cartogen_ai.core.models import dataset_status
        self.assertIn("geometry_validity", dataset_status._CHECK_RUNNERS)
        self.assertIn("map_qa", dataset_status._CHECK_RUNNERS)

    def test_a_missing_runner_is_reported_not_raised(self):
        from unittest import mock

        from cartogen_ai.core.models import dataset_status
        layer = mock.Mock()
        with mock.patch.dict(dataset_status._CHECK_RUNNERS, {}, clear=True):
            passed, detail = dataset_status._run_automated_check("geometry_validity", layer)
        self.assertFalse(passed)
        self.assertIn("not loaded", detail["error"])


if __name__ == "__main__":
    unittest.main()
