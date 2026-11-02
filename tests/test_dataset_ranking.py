"""PLAN-046: ranking of data-set search results. Pure; every missing field is unknown, never guessed."""
import json
import unittest
from datetime import date
from unittest import mock

from cartogen_ai.core.agent import dataset_ranking as dr

TODAY = date(2026, 11, 2)


def item(**kw):
    base = {"title": "T", "license_title": "Creative Commons Attribution International", "metadata_modified": "2026-06-01T10:00:00",
            "groups": [{"name": "yem", "display_name": "Yemen"}], "resources": [{"name": "r", "format": "GeoJSON", "url": "u"}]}
    base.update(kw)
    return base


class TestParts(unittest.TestCase):
    def test_open_unknown_and_non_open_licences(self):
        self.assertEqual(dr.licence_part(item())[0], 40)
        points, _label, reason = dr.licence_part(item(license_title="License not specified"))
        self.assertEqual(points, 0)
        self.assertIn("no licence stated", reason)
        self.assertEqual(dr.licence_part({})[0], 0)
        points, _label, reason = dr.licence_part(item(license_title="Other (Not Open)"))
        self.assertEqual(points, 0)
        self.assertIn("NOT open", reason)
        self.assertEqual(dr.licence_part(item(license_title="Custom Terms v2"))[0], 10)

    def test_freshness_steps_and_unknown_date(self):
        self.assertEqual(dr.freshness_part(item(), TODAY)[0], 40)
        self.assertEqual(dr.freshness_part(item(metadata_modified="2024-06-01"), TODAY)[0], 20)
        self.assertEqual(dr.freshness_part(item(metadata_modified="2021-06-01"), TODAY)[0], 10)
        self.assertEqual(dr.freshness_part(item(metadata_modified="2015-01-01"), TODAY)[0], 0)
        points, months, reason = dr.freshness_part({}, TODAY)
        self.assertEqual((points, months), (0, None))
        self.assertIn("unknown", reason)
        self.assertIn("never updated", dr.freshness_part(item(data_update_frequency="-1"), TODAY)[2])

    def test_coverage_country_and_formats(self):
        self.assertEqual(dr.coverage_part(item(), "Yemen")[0], 20)
        self.assertEqual(dr.coverage_part(item(), "yem")[0], 20)
        points, reason = dr.coverage_part(item(), "Syria")
        self.assertEqual(points, 10)
        self.assertIn("does not list Syria", reason)
        self.assertEqual(dr.coverage_part(item(resources=[{"format": "CSV"}]))[0], 5)
        self.assertEqual(dr.coverage_part(item(resources=[{"format": "PDF"}]))[0], 0)
        self.assertEqual(dr.coverage_part({})[0], 0)


class TestRank(unittest.TestCase):
    def test_open_current_local_beats_stale_unlicensed(self):
        old = item(title="old", license_title="License not specified", metadata_modified="2015-01-01", groups=[{"name": "syr"}])
        good = item(title="good")
        ranked = dr.rank([old, good], TODAY, "Yemen")
        self.assertEqual([r["title"] for r in ranked], ["good", "old"])
        self.assertGreater(ranked[0]["ranking"]["score"], ranked[1]["ranking"]["score"])
        self.assertEqual(len(ranked[0]["ranking"]["why"]), 3)

    def test_ties_keep_the_search_order_and_input_is_not_changed(self):
        a, b = item(title="a"), item(title="b")
        before = json.dumps([a, b])
        self.assertEqual([r["title"] for r in dr.rank([a, b], TODAY)], ["a", "b"])
        self.assertEqual(json.dumps([a, b]), before)

    def test_garbage_does_not_raise(self):
        ranked = dr.rank([{"groups": [None, "x"], "resources": ["y"], "license_title": 5}], TODAY, "Yemen")
        self.assertEqual(len(ranked), 1)


class TestTool(unittest.TestCase):
    def test_the_tool_returns_the_best_first_with_licence_and_reasons(self):
        from cartogen_ai.core.agent.tools import humanitarian_tools as ht
        payload = {"result": {"results": [item(title="old", license_title="License not specified", metadata_modified="2012-01-01"), item(title="good")]}}

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch.object(ht, "_qgis_urlopen", return_value=Resp()), mock.patch.object(ht, "_read_capped", return_value=json.dumps(payload).encode()):
            ht._LOOKUP_CACHE.clear() if hasattr(ht._LOOKUP_CACHE, "clear") else None
            result = ht.search_hdx_datasets("clinics ranking test", limit=2, country="Yemen")
        self.assertEqual([d["title"] for d in result["datasets"]], ["good", "old"])
        self.assertIn("score", result["datasets"][0])
        self.assertIn("not opened", result["ranking_note"])


if __name__ == "__main__":
    unittest.main()
