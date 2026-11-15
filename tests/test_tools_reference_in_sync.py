"""docs/TOOLS_REFERENCE.md is generated from the live tool registry. rc47 changed add_layout_elevation_profile (new along_layer, coordinates
optional) and the committed reference still showed the old parameters because nothing failed when it drifted; this does."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestToolsReferenceInSync(unittest.TestCase):
    def test_committed_reference_matches_the_registry(self):
        spec = importlib.util.spec_from_file_location("generate_tools_reference", ROOT / "docs" / "generate_tools_reference.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        text, _ = module.render()
        committed = (ROOT / "docs" / "TOOLS_REFERENCE.md").read_text(encoding="utf-8")
        self.assertEqual(committed, text, "docs/TOOLS_REFERENCE.md is out of date: run python docs/generate_tools_reference.py")


if __name__ == "__main__":
    unittest.main()
