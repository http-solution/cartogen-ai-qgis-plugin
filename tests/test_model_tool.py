"""PLAN-023 R11-1: the registration contract of run_processing_model (offline: no QGIS needed). The checks are in test_model_ops.py and the real-model behaviour in test_model_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "run_processing_model")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_the_model_file_required(self):
        self.assertIn("run_processing_model", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["model_file"])
        for key in ("inputs", "output_name"):
            self.assertIn(key, params["properties"], key)

    def test_the_description_states_the_refusal_rule_and_the_limits(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["run_processing_model"], tool_operations.CREATE)
        text = schema()["description"]
        for word in ("ONLY if every step is an approved algorithm", "REFUSED", "names the step", "temporary new layers", "cannot be stopped"):
            self.assertIn(word, text)
        self.assertIn("run a model", TOOL_KEYWORDS["run_processing_model"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["run_processing_model"]("m.model3"), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
