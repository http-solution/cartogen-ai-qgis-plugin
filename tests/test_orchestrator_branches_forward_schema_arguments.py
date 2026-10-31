"""PLAN-033 item 2 (LEAD-4): every special-cased orchestrator branch reads or forwards every argument its tool's schema offers.

Why: three arguments were dropped in two days (the GDACS `country` filter, `population_access_gap`'s speed field, `add_layer_from_path`'s
`sublayer`). The registry layer is consistent (measured 2026-10-28); the risk is the orchestrator's own `if name == ...` branches that call the
tool function themselves. test_orchestrator_passes_all_arguments.py covers the `*_network_phase` calls; this reads the source of every
TWO_PHASE_TOOLS branch (no QGIS) and fails when a schema property is neither read from `filtered_args` nor forwarded wholesale (`**filtered_args`).
A property that is deliberately not forwarded goes in DELIBERATELY_NOT_FORWARDED with the reason.

Limit, shown by mutation on 2026-10-31: removing the GDACS `country` read makes this fail; removing only the `a.get("sublayer")` in the
add_layer_from_path lambda does NOT, because the same branch still reads `filtered_args.get("sublayer")` into the dict it hands over. That
second hop is covered by test_add_layer_sublayer_through_orchestrator.py, which drives the real branch."""
import ast
import unittest
from pathlib import Path

from cartogen_ai.core.agent.agent_orchestrator import TWO_PHASE_TOOLS
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA

ORCH = Path(__file__).resolve().parents[1] / "src" / "cartogen_ai" / "core" / "agent" / "agent_orchestrator.py"
DISPATCH, CLEANUP = "_execute_two_phase_tool", "_execute_two_phase_with_cleanup"
ARGS = "filtered_args"

# {tool: {schema property: why the orchestrator branch does not forward it}}. Empty until a drop is shown to be deliberate.
DELIBERATELY_NOT_FORWARDED: dict = {}


def _functions():
    return {n.name: n for n in ast.walk(ast.parse(ORCH.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef)}


def _names_tested(test):
    """Tool names an `if name == "x"` / `if name in ("x", "y")` test selects, else None."""
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "name" and len(test.comparators) == 1:
        comp = test.comparators[0]
        if isinstance(test.ops[0], ast.Eq) and isinstance(comp, ast.Constant):
            return {comp.value}
        if isinstance(test.ops[0], ast.In) and isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
            return {e.value for e in comp.elts if isinstance(e, ast.Constant)}
    return None


def _branch(func, tool):
    """The statements run for `tool` inside `func`: its own `if name == tool` body, else the final `else` of the if/elif chain."""
    last_chain_else = None
    for node in ast.walk(func):
        if not isinstance(node, ast.If):
            continue
        names = _names_tested(node.test)
        if names is not None and tool in names:
            return node.body
        if names is not None and node.orelse and not (len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If)):
            last_chain_else = node.orelse
    return last_chain_else


def _preamble(func):
    """The function's statements outside any if/elif chain: `large = bool(filtered_args.get("allow_large_download"))` is read there once
    for the three boundary and footprint fetches and handed to each branch as `large`."""
    return [stmt for stmt in func.body if not isinstance(stmt, (ast.If, ast.Expr))]


def _reads(statements):
    keys, whole = set(), False
    for stmt in statements:
        for x in ast.walk(stmt):
            if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "get" and x.args \
                    and isinstance(x.args[0], ast.Constant) and isinstance(x.func.value, ast.Name) and x.func.value.id == ARGS:
                keys.add(x.args[0].value)
            if isinstance(x, ast.Subscript) and isinstance(x.value, ast.Name) and x.value.id == ARGS and isinstance(x.slice, ast.Constant):
                keys.add(x.slice.value)
            if isinstance(x, ast.keyword) and x.arg is None and isinstance(x.value, ast.Name) and x.value.id == ARGS:
                whole = True
            if isinstance(x, ast.Dict):
                whole = whole or any(k is None and isinstance(v, ast.Name) and v.id == ARGS for k, v in zip(x.keys, x.values, strict=True))
    return keys, whole


class TestEverySpecialBranchForwardsItsSchema(unittest.TestCase):
    def test_each_two_phase_branch_reads_every_schema_property(self):
        funcs = _functions()
        props = {t["function"]["name"]: set(t["function"]["parameters"].get("properties", {})) for t in TOOLS_SCHEMA}
        problems = []
        for tool in sorted(TWO_PHASE_TOOLS):
            shared = tool in {"fetch_geoboundaries", "fetch_hdx_admin_boundaries", "fetch_building_footprints"}
            body = _branch(funcs[CLEANUP], tool) if shared else _branch(funcs[DISPATCH], tool)
            self.assertIsNotNone(body, f"{tool}: no branch found in the orchestrator (did the dispatch move?)")
            keys, whole = _reads(list(body) + (_preamble(funcs[CLEANUP]) if shared else []))
            if whole:
                continue
            missing = props[tool] - keys - set(DELIBERATELY_NOT_FORWARDED.get(tool, {}))
            if missing:
                problems.append(f"{tool}: schema offers {sorted(missing)} but its orchestrator branch never reads them")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_allow_list_only_names_real_properties_and_gives_a_reason(self):
        props = {t["function"]["name"]: set(t["function"]["parameters"].get("properties", {})) for t in TOOLS_SCHEMA}
        for tool, omitted in DELIBERATELY_NOT_FORWARDED.items():
            for prop, why in omitted.items():
                self.assertIn(prop, props[tool], f"{tool}.{prop} is not a schema property")
                self.assertGreater(len(why), 20, f"{tool}.{prop} needs a reason")

    def test_the_known_branches_are_all_found(self):
        funcs = _functions()
        for tool in ("add_layer_from_path", "fetch_gdacs_disaster_alerts", "fetch_building_footprints", "ingest_osm_features"):
            fn = funcs[CLEANUP] if tool == "fetch_building_footprints" else funcs[DISPATCH]
            self.assertTrue(_branch(fn, tool), tool)


if __name__ == "__main__":
    unittest.main()
