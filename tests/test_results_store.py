# -*- coding: utf-8 -*-
"""rc7 smoke test F06: analysis outputs are memory layers and vanish on Save + Reopen. The pure parts of the per-project
results GeoPackage; the real write/reopen round trip is in tests/test_rc9_live.py."""
import os
import unittest

from cartogen_ai.core.agent import results_store as rs


class TestStorePath(unittest.TestCase):
    def test_lives_under_the_projects_data_folder(self):
        project = os.path.abspath(os.path.join("work", "yemen", "yemen.qgz"))   # abspath: Windows adds a drive letter
        p = rs.store_path(project)
        self.assertEqual(p, os.path.join(os.path.dirname(project), "data", "20_processed", "cartogen_results.gpkg"))

    def test_an_unsaved_project_has_no_store(self):
        self.assertIsNone(rs.store_path(""))
        self.assertIsNone(rs.store_path(None))


class TestTableNames(unittest.TestCase):
    def test_unsafe_characters_become_underscores(self):
        self.assertEqual(rs.table_base("Origin Point_service_area_0"), "Origin_Point_service_area_0")
        self.assertEqual(rs.table_base("Health (OSM, Yemen)"), "Health_OSM_Yemen")

    def test_a_leading_digit_is_prefixed(self):
        self.assertTrue(rs.table_base("3 roads").startswith("t_"))

    def test_empty_names_get_a_stem(self):
        self.assertEqual(rs.table_base(""), "layer")
        self.assertEqual(rs.table_base("***"), "layer")

    def test_long_names_are_capped(self):
        self.assertLessEqual(len(rs.table_base("x" * 200)), 48)

    def test_every_persist_gets_a_new_table_so_an_open_one_is_never_overwritten(self):
        self.assertNotEqual(rs.new_table_name("A", now=1_000_000), rs.new_table_name("A", now=1_000_001))

    def test_arabic_names_do_not_break_the_stem(self):
        self.assertEqual(rs.table_base("مستشفى"), "layer")


class TestProvenance(unittest.TestCase):
    def test_says_tool_sources_and_where_it_is_stored(self):
        text = rs.provenance_abstract("calculate_service_area", ["Roads", "Clinics"], now=0)
        self.assertIn("calculate_service_area", text)
        self.assertIn("Roads, Clinics", text)
        self.assertIn("cartogen_results.gpkg", text)

    def test_no_sources_is_stated_not_blank(self):
        self.assertIn("n/a", rs.provenance_abstract("t", None, now=0))


class TestPersistWithoutQgis(unittest.TestCase):
    def test_reports_why_it_did_nothing(self):
        if rs.QGIS_AVAILABLE:
            self.skipTest("QGIS present")
        res = rs.persist_layer(object())
        self.assertFalse(res["persisted"])
        self.assertIn("QGIS", res["reason"])


if __name__ == "__main__":
    unittest.main()


class TestStaleTables(unittest.TestCase):
    """rc10 smoke test: re-runs left old timestamped tables behind in cartogen_results.gpkg."""

    def test_only_older_stamped_tables_of_the_same_output_are_stale(self):
        names = ["Hull__20261001_205744", "Hull__20261001_214745", "Roads__20261001_205749", "Hull_notes",
                 "Hull__final", "HullTwo__20261001_100000", "user_table"]
        self.assertEqual(rs.stale_tables(names, "Hull", keep="Hull__20261001_214745"), ["Hull__20261001_205744"])

    def test_a_table_a_layer_still_uses_is_kept(self):
        names = ["Hull__20261001_205744", "Hull__20261001_214745"]
        self.assertEqual(rs.stale_tables(names, "Hull", keep="Hull__20261001_214745", in_use={"Hull__20261001_205744"}), [])

    def test_nothing_is_stale_when_there_is_only_the_kept_table(self):
        self.assertEqual(rs.stale_tables(["Hull__20261001_214745"], "Hull", keep="Hull__20261001_214745"), [])
