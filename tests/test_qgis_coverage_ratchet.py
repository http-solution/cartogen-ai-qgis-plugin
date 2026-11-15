"""The QGIS coverage can only go up. docs/qgis_coverage/baseline.json holds the status of every action in tools/qgis_coverage_actions.py
(163 rows taken from the QGIS 4.2 documentation) as of 2026-10-14. A change that makes a COVERED or PARTIAL action worse (a tool removed, a
phrase no longer routed), or deletes a row to hide it, fails here. Raising a row is done by building the tool and running
`python tools/build_qgis_coverage.py --write-baseline`, which is a reviewed change to the baseline file."""
import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANK = {"COVERED": 3, "PARTIAL": 2, "ROUTING-GAP": 1, "MISSING": 0}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCoverageRatchet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        cls.build = _load("build_qgis_coverage", os.path.join(ROOT, "tools", "build_qgis_coverage.py"))
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        from cartogen_ai.core.services.tool_router import ToolRouter
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        cls.rows = {r["action"]: r["status"] for r in cls.build.action_status(ToolRouter(TOOLS_SCHEMA), registered)}
        with open(os.path.join(ROOT, "docs", "qgis_coverage", "baseline.json"), encoding="utf-8") as fh:
            cls.baseline = json.load(fh)

    def test_no_action_row_was_deleted(self):
        self.assertEqual(sorted(set(self.baseline) - set(self.rows)), [])

    def test_no_action_got_worse(self):
        worse = [f"{a}: {old} -> {self.rows[a]}" for a, old in self.baseline.items()
                 if a in self.rows and old in RANK and self.rows[a] in RANK and RANK[self.rows[a]] < RANK[old]]
        self.assertEqual(worse, [], chr(10).join(worse))

    def test_blocked_rows_stay_blocked_on_purpose(self):
        changed = [a for a, old in self.baseline.items() if old == "BLOCKED" and self.rows.get(a) != "BLOCKED"]
        self.assertEqual(changed, [], "a BLOCKED row changed: that is a security decision, review it")


if __name__ == "__main__":
    unittest.main()
