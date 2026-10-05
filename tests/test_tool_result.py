# -*- coding: utf-8 -*-
"""The tool-result contract (core/agent/tool_result.py). Lists are results, not failures: rc15 hand test, get_layers."""
import unittest

from cartogen_ai.core.agent import tool_result as tr


class TestToolResult(unittest.TestCase):
    def test_only_a_missing_result_is_replaced_by_the_error(self):
        self.assertEqual(tr.ensure_result(None), {"error": tr.MISSING_RESULT_ERROR})
        for ok in ([], [{"a": 1}], {}, {"success": True}, "text", 0, False):
            self.assertIs(tr.ensure_result(ok), ok)

    def test_error_detection_needs_a_dict_with_an_error_key(self):
        self.assertTrue(tr.is_error({"error": "x"}))
        self.assertEqual(tr.error_of({"error": "x"}), "x")
        for not_error in ([], [{"error": "x"}], {"success": True}, None, "error"):
            self.assertFalse(tr.is_error(not_error))
            self.assertIsNone(tr.error_of(not_error))

    def test_status_and_error_class_tolerate_every_shape(self):
        self.assertEqual(tr.status_of({"status": "PREVIEW_REQUIRED"}), "PREVIEW_REQUIRED")
        self.assertIsNone(tr.status_of([1]))
        self.assertEqual(tr.error_class_of({"error_class": "Boom"}), "Boom")
        self.assertEqual(tr.error_class_of({"error": "x"}), "ToolError")
        self.assertEqual(tr.error_class_of([1]), "ToolError")


if __name__ == "__main__":
    unittest.main()
