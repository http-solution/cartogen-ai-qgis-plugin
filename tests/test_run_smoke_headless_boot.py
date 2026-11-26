"""Offline guard for the headless smoke runner's start-up (needs no QGIS). The owner's Windows run on 2026-11-26 failed H17 and H18 with "Algorithm native:buffer
not found" because boot_qgis never registered the native algorithms; CI could not see it because its live test boots QGIS another way. This pins that both the
real start-up and run_rows register them, so a later edit cannot drop the call unnoticed."""
import ast
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "tools" / "run_smoke_headless.py").read_text(encoding="utf-8")


def _body(name):
    for node in ast.walk(ast.parse(SRC)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(SRC, node)
    raise AssertionError(name)


class TestHeadlessBoot(unittest.TestCase):
    def test_boot_qgis_registers_native_algorithms(self):
        self.assertIn("init_processing()", _body("boot_qgis"))

    def test_run_rows_registers_native_algorithms(self):
        self.assertIn("init_processing()", _body("run_rows"))

    def test_init_processing_initialises_and_checks_the_provider(self):
        body = _body("init_processing")
        self.assertIn("Processing.initialize()", body)
        self.assertIn('algorithmById("native:buffer")', body)


if __name__ == "__main__":
    unittest.main()
