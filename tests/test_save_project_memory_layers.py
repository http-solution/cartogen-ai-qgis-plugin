# -*- coding: utf-8 -*-
"""save_project must not claim temporary layers were persisted (rc15 hand test D07, 2026-10-06)."""
import unittest

from cartogen_ai.core.agent.tools.project_tools import memory_layer_warning


class TestMemoryLayerWarning(unittest.TestCase):
    def test_no_temporary_layers_gives_no_warning(self):
        self.assertIsNone(memory_layer_warning([]))
        self.assertIsNone(memory_layer_warning(None))
        self.assertIsNone(memory_layer_warning(["", None]))

    def test_the_warning_names_the_layers_and_says_they_come_back_empty(self):
        text = memory_layer_warning(["smoke_points_buffer_500"])
        self.assertIn("smoke_points_buffer_500", text)
        self.assertIn("EMPTY", text)
        self.assertIn("1 temporary layer", text)

    def test_a_long_list_is_shortened_but_counted(self):
        text = memory_layer_warning([f"L{i}" for i in range(14)])
        self.assertIn("14 temporary layer", text)
        self.assertIn("and 4 more", text)
        self.assertNotIn("L13", text)


if __name__ == "__main__":
    unittest.main()
