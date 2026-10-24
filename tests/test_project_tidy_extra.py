"""rc48 OI-120: one dataset loaded two ways is one duplicate; a near miss is shown in the report (pure, no QGIS)."""
import unittest

from cartogen_ai.core.agent.tools.project_tidy_tools import (
    duplicate_groups,
    normalize_source,
    same_name_different_data,
    vector_signature,
)


class TestNormalizeSource(unittest.TestCase):
    def test_slashes_drive_case_and_geometrytype_do_not_make_two_layers_different(self):
        a = "C:/Users/x/smoke_network.gpkg|layername=smoke_roads"
        b = "c:\\Users\\x\\smoke_network.gpkg|layername=smoke_roads|geometrytype=LineString"
        self.assertEqual(normalize_source(a), normalize_source(b))

    def test_a_subset_filter_or_another_layer_still_differs(self):
        base = "/d/x.gpkg|layername=roads"
        self.assertNotEqual(normalize_source(base), normalize_source(base + "|subset=speed > 10"))
        self.assertNotEqual(normalize_source(base), normalize_source("/d/x.gpkg|layername=rivers"))

    def test_an_empty_source_stays_empty(self):
        self.assertFalse(normalize_source(""))
        self.assertIsNone(normalize_source(None))


class TestDuplicatesAcrossLoadStyles(unittest.TestCase):
    def test_the_same_geopackage_layer_loaded_twice_is_found_whatever_the_load_style(self):
        entries = [
            {"id": "1", "name": "smoke_roads", "visible": True,
             "signature": vector_signature("ogr", "C:/d/smoke_network.gpkg|layername=smoke_roads", 24, [])},
            {"id": "2", "name": "smoke_roads", "visible": True,
             "signature": vector_signature("ogr", "c:\\d\\smoke_network.gpkg|layername=smoke_roads|geometrytype=LineString", 24, [])},
        ]
        self.assertEqual(duplicate_groups(entries), [["1", "2"]])

    def test_a_same_name_near_miss_is_listed_with_both_sources(self):
        entries = [
            {"id": "1", "name": "roads", "provider": "ogr", "source": "/a/x.gpkg|layername=roads", "signature": "s1"},
            {"id": "2", "name": "roads", "provider": "ogr", "source": "/b/x.gpkg|layername=roads", "signature": "s2"},
            {"id": "3", "name": "mem", "provider": "memory", "source": "memory?x", "signature": None},
            {"id": "4", "name": "mem", "provider": "memory", "source": "memory?x", "signature": None},
        ]
        out = same_name_different_data(entries)
        self.assertEqual([o["name"] for o in out], ["roads"])
        self.assertEqual(len(out[0]["sources"]), 2)

    def test_grouped_duplicates_are_not_repeated_as_near_misses(self):
        entries = [{"id": "1", "name": "r", "provider": "ogr", "source": "a", "signature": "s"},
                   {"id": "2", "name": "r", "provider": "ogr", "source": "a", "signature": "s"}]
        self.assertEqual(same_name_different_data(entries, {"1", "2"}), [])


if __name__ == "__main__":
    unittest.main()
