"""The QGIS coverage list must stay true: a row may only name Processing algorithms the plugin can run, may only be called hand-tested for
algorithms that really passed a hand test, and docs/qgis_coverage/SUMMARY.md must be exactly what the builder generates from the catalogue."""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    spec = importlib.util.spec_from_file_location("build_qgis_coverage", os.path.join(ROOT, "tools", "build_qgis_coverage.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCoverageEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = _load()
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        from cartogen_ai.core.services.tool_router import ToolRouter
        cls.rows = cls.build.action_status(ToolRouter(TOOLS_SCHEMA), {t["function"]["name"] for t in TOOLS_SCHEMA})

    def test_hand_tested_algorithms_are_all_on_the_allow_list(self):
        from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS
        import qgis_coverage_actions as catalogue
        self.assertEqual(sorted(catalogue.HAND_TESTED_ALGORITHMS - set(ALLOWED_ALGORITHM_IDS)), [])
        self.assertEqual(len(catalogue.HAND_TESTED_ALGORITHMS), 21)   # the rc46 Part 5 priority list

    def test_a_row_is_only_called_hand_tested_for_algorithms_that_were(self):
        for row in self.rows:
            if "hand-tested rc46" in row["note"]:
                self.assertNotEqual(row["evidence"], "CI only", row["action"])

    def test_algorithm_rows_use_the_generic_processing_tool_and_are_offered_it(self):
        for row in self.rows:
            if row["algorithms"]:
                self.assertIn("run_allowlisted_processing_algorithm", row["tools"], row["action"])
                self.assertIn("run_allowlisted_processing_algorithm", row["offered_for_phrase"], f"{row['action']}: the router does not offer it for {row['phrase']!r}")

    def test_evidence_wording(self):
        build = self.build
        self.assertEqual(build.evidence_of([], None), "")
        self.assertEqual(build.evidence_of(["gdal:slope"], None), "hand-tested rc46")
        self.assertEqual(build.evidence_of(["gdal:slope", "gdal:tri"], None), "partly hand-tested rc46 (1 of 2)")
        self.assertEqual(build.evidence_of(["gdal:tri"], None), "CI only")

    def test_summary_file_is_what_the_builder_generates(self):
        with open(os.path.join(ROOT, "docs", "qgis_coverage", "SUMMARY.md"), encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(committed, self.build.summary_text(self.rows), "run python tools/build_qgis_coverage.py and commit docs/qgis_coverage/")


if __name__ == "__main__":
    unittest.main()
