# -*- coding: utf-8 -*-
"""Result labels come from a name-like field, not from the first attribute (CI on the release smoke fixture, 2026-10-06)."""
import unittest

from cartogen_ai.core.agent.tools.logistics_tools import label_field_index


class TestLabelFieldIndex(unittest.TestCase):
    def test_a_geopackage_fid_first_field_is_skipped_for_the_name_field(self):
        # QGIS lists a GeoPackage primary key as field 0: the smoke hubs came back labelled 1, 2, 3.
        self.assertEqual(label_field_index(["fid", "name"], ["Integer64", "String"]), 1)

    def test_known_name_fields_are_preferred_in_order(self):
        self.assertEqual(label_field_index(["id", "population", "admin_name"]), 2)
        self.assertEqual(label_field_index(["x", "Label", "name2"]), 1)
        self.assertEqual(label_field_index(["id", "hub_name", "name"]), 2)  # plain "name" outranks *_name

    def test_without_a_name_the_first_text_field_that_is_not_an_id_wins(self):
        self.assertEqual(label_field_index(["fid", "pop", "town"], ["Integer64", "Integer", "String"]), 2)

    def test_without_text_types_the_first_non_id_field_wins(self):
        self.assertEqual(label_field_index(["fid", "pop"]), 1)

    def test_a_layer_with_only_ids_or_one_field_keeps_the_old_behaviour(self):
        self.assertEqual(label_field_index(["fid"]), 0)
        self.assertEqual(label_field_index(["only"]), 0)
        self.assertEqual(label_field_index([]), 0)


if __name__ == "__main__":
    unittest.main()
