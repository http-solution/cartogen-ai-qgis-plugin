# -*- coding: utf-8 -*-
"""A derived output must stay protected when its protected source is renamed, or shares its name with an open layer (GitHub #150)."""
import unittest

from cartogen_ai.core.agent.lineage import effective_source_names, source_layer_ids
from cartogen_ai.core.models import egress_gate


class _L:
    def __init__(self, lid, name):
        self._id, self._name = lid, name

    def id(self):
        return self._id

    def name(self):
        return self._name


class TestSourceIds(unittest.TestCase):
    def test_every_layer_sharing_a_source_name_is_recorded(self):
        layers = [_L("a", "clinics"), _L("b", "clinics"), _L("c", "roads")]
        self.assertEqual(source_layer_ids(["clinics"], layers), ["a", "b"])

    def test_no_sources(self):
        self.assertEqual(source_layer_ids([], [_L("a", "x")]), [])


class TestEffectiveSourceNames(unittest.TestCase):
    def test_a_renamed_source_is_found_by_its_id(self):
        entry = {"sources": ["clinics"], "source_ids": ["a"]}
        self.assertEqual(effective_source_names(entry, [_L("a", "clinics_renamed")]), ["clinics", "clinics_renamed"])

    def test_an_old_entry_without_ids_still_works(self):
        self.assertEqual(effective_source_names({"sources": ["clinics"]}, []), ["clinics"])

    def test_a_vanished_id_adds_nothing(self):
        self.assertEqual(effective_source_names({"sources": ["x"], "source_ids": ["gone"]}, []), ["x"])


class TestGateAfterRename(unittest.TestCase):
    def test_the_derived_layer_is_protected_after_its_sensitive_source_was_renamed(self):
        layers = [_L("a", "renamed"), _L("o", "output")]
        levels = {"renamed": "SENSITIVE", "output": None}
        lineage = {"output": [{"sources": ["original"], "source_ids": ["a"]}]}
        found = egress_gate.find_protected(
            ["output"], lambda n: levels.get(n),
            lambda n: [s for e in lineage.get(n, []) for s in effective_source_names(e, layers)], strict=False)
        self.assertIn("output", found)

    def test_without_ids_the_same_rename_would_have_opened_it(self):
        layers = [_L("a", "renamed"), _L("o", "output")]
        levels = {"renamed": "SENSITIVE", "output": None}
        lineage = {"output": [{"sources": ["original"]}]}
        found = egress_gate.find_protected(
            ["output"], lambda n: levels.get(n),
            lambda n: [s for e in lineage.get(n, []) for s in effective_source_names(e, layers)], strict=False)
        self.assertEqual(found, {})        # documents why ids are recorded: names alone lose the link


class TestMostProtectiveLevel(unittest.TestCase):
    def test_order(self):
        f = egress_gate.most_protective_level
        self.assertEqual(f(["PUBLIC", "SENSITIVE"]), "SENSITIVE")
        self.assertEqual(f(["PUBLIC", "RESTRICTED", "INTERNAL"]), "RESTRICTED")
        self.assertIsNone(f(["PUBLIC", None]))
        self.assertEqual(f(["PUBLIC", "INTERNAL"]), "INTERNAL")
        self.assertIsNone(f([]))

    def test_a_duplicate_named_open_twin_does_not_open_a_protected_layer(self):
        self.assertTrue(egress_gate.is_protected(egress_gate.most_protective_level(["PUBLIC", "SENSITIVE"]), strict=False))


if __name__ == "__main__":
    unittest.main()
