"""PLAN-023 R1-6: docs/PERSONA_CATALOGUE.md is generated, never hand-edited. It must equal what docs/generate_persona_catalogue.py produces now, and it must not say more than the persona files do."""
import importlib.util
import unittest
from pathlib import Path

from cartogen_ai.core import personas as pp

ROOT = Path(__file__).resolve().parent.parent


def _generator():
    spec = importlib.util.spec_from_file_location("generate_persona_catalogue", ROOT / "docs" / "generate_persona_catalogue.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPersonaCatalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _generator().render()

    def test_the_committed_file_is_what_the_generator_writes(self):
        self.assertEqual((ROOT / "docs" / "PERSONA_CATALOGUE.md").read_text(encoding="utf-8"), self.text,
                         "docs/PERSONA_CATALOGUE.md is stale: run python docs/generate_persona_catalogue.py")

    def test_every_persona_has_a_section_and_a_row(self):
        for pid in pp.ids():
            persona = pp.get(pid)
            self.assertIn(f"## {persona['number']}. {persona['label']}", self.text, pid)
            self.assertIn(f"| {persona['number']} | {persona['label']} |", self.text, pid)

    def test_nothing_is_called_built_unless_a_persona_file_says_built(self):
        any_built = any(r["state"] == "built" for pid in pp.ids() for r in pp.get(pid)["readiness"])
        self.assertEqual("**Built and seen working:**" in self.text, any_built)

    def test_persona_fifteen_keeps_its_sentence_and_the_catalogue_shows_it(self):
        self.assertIn("Classified data must never be used with this plugin", self.text)

    def test_the_output_is_deterministic(self):
        self.assertEqual(_generator().render(), self.text)


if __name__ == "__main__":
    unittest.main()
