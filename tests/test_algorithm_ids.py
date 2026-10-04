# -*- coding: utf-8 -*-
"""Offline check of the id scanner behind the live registry diagnostic (tests/test_processing_registry_diagnostic_live.py)."""
import unittest

from tests._algorithm_ids import referenced_algorithm_ids, suggestions


class TestScanner(unittest.TestCase):
    def test_finds_the_known_ids_and_their_files(self):
        ids = referenced_algorithm_ids()
        self.assertIn("native:buffer", ids)
        self.assertIn("core/agent/tools/_processing_allowlist.py", ids["native:buffer"])
        self.assertGreater(len(ids), 30)

    def test_every_id_is_provider_colon_name(self):
        for algorithm_id in referenced_algorithm_ids():
            provider, _, name = algorithm_id.partition(":")
            self.assertTrue(provider and name, algorithm_id)


class TestSuggestions(unittest.TestCase):
    ALL = ["native:heatmapkerneldensityestimation", "gdal:rastercalculator", "native:contraststretch_x", "gdal:merge", "qgis:other"]

    def test_same_short_name_under_another_provider_comes_first(self):
        self.assertEqual(suggestions("qgis:heatmapkerneldensityestimation", self.ALL)[0], "native:heatmapkerneldensityestimation")

    def test_a_stem_match_when_there_is_no_exact_name(self):
        self.assertIn("native:contraststretch_x", suggestions("gdal:contraststretch", self.ALL))

    def test_nothing_to_suggest(self):
        self.assertEqual(suggestions("saga:zzz", self.ALL), [])


if __name__ == "__main__":
    unittest.main()
