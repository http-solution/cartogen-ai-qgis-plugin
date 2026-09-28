# -*- coding: utf-8 -*-
"""agent/local_data_sources.py: when to offer a local download, what the question lists, and
which Geofabrik region a location falls in. Live-reported 2026-09-24/25: the same travel-time
request failed twice because roads/facilities were fetched live from an overloaded Overpass."""
import unittest

from cartogen_ai.core.agent import local_data_sources as lds
from cartogen_ai.core.agent import task_matcher as tm

Q = "Health facilities beyond one hour's travel 3999682,3756232"


def _square(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def _region(rid, name, polys, iso2=None, shp=True):
    return {"type": "Feature",
            "properties": {"id": rid, "name": name, "iso3166-1:alpha2": [iso2] if iso2 else None,
                           "urls": {"shp": "https://download.geofabrik.de/%s-latest-free.shp.zip" % rid}
                           if shp else {"pbf": "x"}},
            "geometry": {"type": "MultiPolygon", "coordinates": polys}}


class TestWhenToOffer(unittest.TestCase):
    def setUp(self):
        self.entry = tm.classify(Q)["best"]

    def test_the_reported_request_needs_roads_and_health_facilities(self):
        self.assertEqual(lds.themes_needed(self.entry, Q), ["roads", "health_facilities"])

    def test_population_only_when_the_user_asks_about_people(self):
        # 7.23 lists population_access_gap among its tools, but this request doesn't need a grid.
        self.assertNotIn("population", lds.themes_needed(self.entry, Q))
        q = "how many people live beyond one hour's travel from health facilities"
        self.assertIn("population", lds.themes_needed(tm.classify(q)["best"], q))

    def test_offered_in_an_empty_project(self):
        self.assertEqual(lds.should_offer(self.entry, Q, []), ["roads", "health_facilities"])

    def test_roads_loaded_as_points_do_not_count(self):
        # The reported project: "Road Network" had been ingested as points (BUG-2026-09-24-3).
        layers = [{"name": "Road Network", "geometry": "point"},
                  {"name": "Health Facilities", "geometry": "point"}]
        self.assertEqual(lds.should_offer(self.entry, Q, layers), ["roads"])

    def test_not_offered_when_the_project_already_has_the_data(self):
        layers = [{"name": "OSM Roads (Jordan)", "geometry": "line"},
                  {"name": "Health Facilities (OSM, Jordan)", "geometry": "point"}]
        self.assertEqual(lds.should_offer(self.entry, Q, layers), [])

    def test_not_offered_after_declining_or_when_the_request_says_online(self):
        self.assertEqual(lds.should_offer(self.entry, Q, [], declined=True), [])
        self.assertEqual(lds.should_offer(self.entry, Q + " using online data", []), [])

    def test_not_offered_for_tasks_without_a_road_network(self):
        q = "map flooded areas in Sindh"
        self.assertEqual(lds.should_offer(tm.classify(q)["best"], q, []), [])
        self.assertEqual(lds.should_offer(None, "hello", []), [])


class TestQuestion(unittest.TestCase):
    def test_lists_every_other_source_for_the_themes_and_how_to_answer(self):
        text = lds.question_text(["roads", "health_facilities"], country="Jordan")
        for theme in ("roads", "health_facilities"):
            for src in lds.SOURCES[theme]:
                if not src.get("auto"):
                    self.assertIn(src["name"], text)
        self.assertIn("Geofabrik", text)
        self.assertIn("hotosm%20Jordan%20roads", text)
        self.assertIn("Reply **download**", text)
        self.assertIn("**online**", text)

    def test_links_still_work_without_a_country(self):
        text = lds.question_text(["roads"])
        self.assertIn("search?q=hotosm%20roads", text)
        self.assertNotIn("%20%20", text)

    def test_every_catalogued_url_is_https(self):
        for srcs in lds.SOURCES.values():
            for s in srcs:
                self.assertTrue(s["url"].startswith("https://"), s["name"])
        self.assertIn("WorldPop", lds.all_sources_markdown("Jordan"))


class TestReplies(unittest.TestCase):
    def test_download_and_online_replies(self):
        for t in ("download", "Download.", "local", "yes", "OK!"):
            self.assertEqual(lds.parse_reply(t), "download", t)
        for t in ("online", "no", "skip", "Not now"):
            self.assertEqual(lds.parse_reply(t), "online", t)

    def test_anything_else_is_a_new_request(self):
        for t in ("", "map schools in Irbid", "download roads for Syria please"):
            self.assertIsNone(lds.parse_reply(t), t)

    def test_single_letter_typos_of_the_headline_words_still_resolve(self):
        # Live-reported, 2026-09-28: "dowmload" (one transposed letter) fell through to
        # None, silently dropped the pending local-data question, and derailed the rest
        # of the conversation -- see local_data_sources.py's parse_reply docstring.
        for t in ("dowmload", "donwload", "Downlaod"):
            self.assertEqual(lds.parse_reply(t), "download", t)
        for t in ("onlien", "onlline", "Onlne"):
            self.assertEqual(lds.parse_reply(t), "online", t)

    def test_typo_tolerance_does_not_swallow_unrelated_short_replies(self):
        # A real new short request must never accidentally snap to "download"/"online"
        # just because it shares some letters.
        for t in ("decline", "delete", "cancel", "later", "roads"):
            self.assertIsNone(lds.parse_reply(t), t)


class TestExtractCoordinatePair(unittest.TestCase):
    """Live-reported, 2026-09-28: the local-data download offer picked its target region from
    the QGIS canvas's current view centre instead of the coordinate the request itself named
    -- wrong whenever the canvas hadn't been panned there yet (named the wrong neighboring
    country, or literally "(0.000, 0.000)"). This is the text-parsing half of the fix; see
    local_data_loader.query_point_wgs84 for the CRS-reprojection half."""

    def test_finds_the_pair_from_a_real_live_reported_request(self):
        pair = lds.extract_coordinate_pair(
            "Health facilities beyond one hour's travel 3999770.2,3743455.7")
        self.assertEqual(pair, (3999770.2, 3743455.7))

    def test_finds_a_negative_pair(self):
        self.assertEqual(lds.extract_coordinate_pair("origin -74.006,40.7128"), (-74.006, 40.7128))

    def test_no_pair_returns_none(self):
        for t in ("", "Buffer 5 km around active GDACS alerts", "Population within the flood extent"):
            self.assertIsNone(lds.extract_coordinate_pair(t), t)

    def test_requires_a_decimal_point_on_both_numbers(self):
        # A thousands separator or a plain list must never be mistaken for a coordinate pair.
        for t in ("Buffer 1,000 meters around the site", "facilities 1,2,3", "roads 12,34"):
            self.assertIsNone(lds.extract_coordinate_pair(t), t)


class TestFindRegion(unittest.TestCase):
    def setUp(self):
        self.index = {"features": [
            _region("asia", "Asia", [[_square(20, 0, 150, 60)]]),
            _region("jordan", "Jordan", [[_square(35, 29, 39, 33)]], iso2="JO"),
            # a country with a hole (an enclave) and a second part
            _region("holey", "Holey", [[_square(0, 0, 10, 10), _square(4, 4, 6, 6)],
                                       [_square(12, 0, 14, 2)]], iso2="HO"),
            _region("no-shp", "No shapefile", [[_square(35, 29, 39, 33)]], shp=False),
        ]}

    def test_picks_the_smallest_region_containing_the_point(self):
        r = lds.find_region(self.index, 35.93, 31.95)
        self.assertEqual((r["id"], r["iso2"]), ("jordan", "JO"))
        self.assertTrue(r["shp_url"].endswith("jordan-latest-free.shp.zip"))

    def test_falls_back_to_the_parent_outside_the_child(self):
        self.assertEqual(lds.find_region(self.index, 100.0, 30.0)["id"], "asia")

    def test_holes_and_multipart_outlines(self):
        self.assertEqual(lds.find_region(self.index, 2.0, 2.0)["id"], "holey")
        self.assertIsNone(lds.find_region(self.index, 5.0, 5.0))  # inside the hole
        self.assertEqual(lds.find_region(self.index, 13.0, 1.0)["id"], "holey")

    def test_nothing_found(self):
        self.assertIsNone(lds.find_region(self.index, -30.0, 30.0))
        self.assertIsNone(lds.find_region({}, 0, 0))


if __name__ == "__main__":
    unittest.main()
