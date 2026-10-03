# -*- coding: utf-8 -*-
"""Pure rules behind tidy_project_layers (GitHub #120 / #128)."""
import unittest

from cartogen_ai.core.agent.tools import project_tidy_tools as pt
from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY


class TestDuplicateGroups(unittest.TestCase):
    def test_same_name_and_data_is_a_duplicate_and_the_visible_copy_is_kept(self):
        groups = pt.duplicate_groups([
            {"id": "a", "name": "YEM_ADM1", "signature": "src:/d/adm1.geojson", "visible": False},
            {"id": "b", "name": "YEM_ADM1", "signature": "src:/d/adm1.geojson", "visible": True},
            {"id": "c", "name": "Roads", "signature": "src:/d/roads.gpkg", "visible": True},
        ])
        self.assertEqual(groups, [["b", "a"]])

    def test_same_name_different_data_is_not_a_duplicate(self):
        self.assertEqual(pt.duplicate_groups([
            {"id": "a", "name": "Origin", "signature": "mem:1:aaa", "visible": True},
            {"id": "b", "name": "Origin", "signature": "mem:1:bbb", "visible": True},
        ]), [])

    def test_a_missing_signature_never_matches(self):
        self.assertEqual(pt.duplicate_groups([
            {"id": "a", "name": "Origin", "signature": None, "visible": True},
            {"id": "b", "name": "Origin", "signature": None, "visible": True},
        ]), [])


class TestSignatures(unittest.TestCase):
    def test_file_layers_use_their_source(self):
        self.assertEqual(pt.vector_signature("ogr", "/d/x.gpkg|layername=x", 10, []), "src:/d/x.gpkg|layername=x")

    def test_memory_layers_use_count_and_geometry_hash_and_ignore_order(self):
        a = pt.vector_signature("memory", "Point?crs=EPSG:4326", 2, ["01", "02"])
        b = pt.vector_signature("memory", "Point?crs=EPSG:4326", 2, ["02", "01"])
        c = pt.vector_signature("memory", "Point?crs=EPSG:4326", 2, ["01", "03"])
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_a_memory_layer_without_geometries_has_no_signature(self):
        self.assertIsNone(pt.vector_signature("memory", "Point?crs=EPSG:4326", 0, []))


class TestPopulationRampRule(unittest.TestCase):
    def test_only_a_population_named_raster_not_already_pseudocolour(self):
        self.assertTrue(pt.needs_population_ramp("yem_ppp_2020", "singlebandgray", True))
        self.assertFalse(pt.needs_population_ramp("yem_ppp_2020", "singlebandpseudocolor", True))
        self.assertFalse(pt.needs_population_ramp("dem", "singlebandgray", False))


class TestToolRegistration(unittest.TestCase):
    def test_it_is_registered_and_classified_as_modify_never_delete(self):
        from cartogen_ai.core.agent.tool_operations import TOOL_OPERATION_TYPES
        self.assertIn("tidy_project_layers", TOOL_REGISTRY)
        self.assertEqual(TOOL_OPERATION_TYPES["tidy_project_layers"], "MODIFY")

    def test_it_degrades_without_qgis(self):
        from unittest.mock import patch
        with patch.object(pt, "QGIS_AVAILABLE", False):
            self.assertIn("error", pt.tidy_project_layers())


if __name__ == "__main__":
    unittest.main()
