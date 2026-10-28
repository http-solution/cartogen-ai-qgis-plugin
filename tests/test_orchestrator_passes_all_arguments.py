"""The two-phase fetch handlers in agent_orchestrator.py must pass on every argument the tool function takes.

Why: 1.18.4 smoke N7c and A7 asked GDACS for "Yemen" and got 86 alerts from around the world. fetch_gdacs_disaster_alerts_network_phase has filtered by
country since 2026-09-15, but the orchestrator's own call to it passed only bbox and alert level, so the filter never ran in the live path. This
reads the orchestrator source (no QGIS) and fails when a call to a *_network_phase function gives fewer arguments than the function declares."""
import ast
import glob
import os
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "src", "cartogen_ai", "core", "agent", "tools")
ORCH = os.path.join(ROOT, "src", "cartogen_ai", "core", "agent", "agent_orchestrator.py")

# Parameters that are deliberately left at their default because the tool's public schema does not offer them to the model.
NOT_IN_SCHEMA = {"fetch_nasa_active_fires_network_phase": {"source"}}


def _signatures():
    sigs = {}
    for path in glob.glob(os.path.join(TOOLS, "*.py")):
        for node in ast.walk(ast.parse(Path(path).read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.endswith("_network_phase"):
                sigs[node.name] = [a.arg for a in node.args.args]
    return sigs


class TestNetworkPhaseCalls(unittest.TestCase):
    def test_every_network_phase_call_passes_every_declared_argument(self):
        sigs = _signatures()
        problems = []
        for node in ast.walk(ast.parse(Path(ORCH).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in sigs:
                params = sigs[node.func.id]
                given = {params[i] for i in range(len(node.args))} | {k.arg for k in node.keywords}
                missing = set(params) - given - NOT_IN_SCHEMA.get(node.func.id, set())
                if missing:
                    problems.append(f"{node.func.id} (line {node.lineno}) is not given {sorted(missing)}")
        self.assertEqual(problems, [])

    def test_the_gdacs_call_is_among_those_checked(self):
        self.assertIn("fetch_gdacs_disaster_alerts_network_phase", _signatures())


if __name__ == "__main__":
    unittest.main()
