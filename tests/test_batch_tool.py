"""PLAN-023 R11-2: the registration contract of run_processing_batch (offline: no QGIS needed). The checks are in test_batch_ops.py and the real-layer behaviour in test_batch_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools import batch_ops as bo
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "run_processing_batch")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_the_algorithm_and_layers_required(self):
        self.assertIn("run_processing_batch", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["algorithm_id", "layers"])
        for key in ("parameters", "input_parameter", "group_name"):
            self.assertIn(key, params["properties"], key)

    def test_the_description_states_the_limits(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["run_processing_batch"], tool_operations.CREATE)
        text = schema()["description"]
        for word in (f"1 to {bo.MAX_LAYERS}", "does not stop the others", "temporary", "refused", "must be new"):
            self.assertIn(word, text)
        self.assertIn("batch process", TOOL_KEYWORDS["run_processing_batch"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["run_processing_batch"]("native:buffer", ["a"]), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
