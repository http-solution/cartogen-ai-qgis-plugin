"""find_incident_reports: normalising, filtering, merging and the parallel fan-out with every source stubbed. The shapes of the stubbed source
results are the ones the live services returned on 2026-10-11/12. The layer phase needs QGIS (tests/test_incident_search_live.py)."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools import incident_search_tools as inc

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>ReliefWeb - Disasters</title>
<item><title>Panama: Earthquake - Oct 2026</title><link>https://reliefweb.int/disaster/eq-2026-000188-pan</link>
<pubDate>Fri, 09 Oct 2026 00:00:00 +0000</pubDate>
<description>&lt;div class="tag country"&gt;Affected country: Panama&lt;/div&gt;&lt;div class="tag glide"&gt;Glide: EQ-2026-000188-PAN&lt;/div&gt;&lt;p&gt;A 7.2 quake.&lt;/p&gt;</description></item>
<item><title>Sudan: Floods - Aug 2026</title><link>https://reliefweb.int/disaster/fl-2026-000150-sdn</link>
<pubDate>Mon, 03 Aug 2026 00:00:00 +0000</pubDate>
<description>&lt;div class="tag country"&gt;Affected country: Sudan&lt;/div&gt;&lt;div class="tag glide"&gt;Glide: FL-2026-000150-SDN&lt;/div&gt;</description></item>
</channel></rss>"""


class TestNormalising(unittest.TestCase):
    def test_reliefweb_rss_gives_country_glide_link_and_date_and_filters(self):
        recs = inc.parse_reliefweb_rss(RSS)
        self.assertEqual([r["id"] for r in recs], ["EQ-2026-000188-PAN", "FL-2026-000150-SDN"])
        self.assertEqual((recs[0]["country"], recs[0]["date"], recs[0]["lat"]), ("Panama", "2026-10-09", None))
        self.assertEqual([r["country"] for r in inc.parse_reliefweb_rss(RSS, country="sudan")], ["Sudan"])
        self.assertEqual([r["country"] for r in inc.parse_reliefweb_rss(RSS, since="2026-09-01")], ["Panama"])

    def test_a_feed_that_declares_entities_is_refused_not_parsed(self):
        bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
        with self.assertRaises(ValueError):
            inc.parse_reliefweb_rss(bomb)

    def test_each_source_maps_to_the_common_record_with_its_tier_and_link(self):
        g = inc.from_gdacs({"alerts": [{"unit": "1", "lat": 1.0, "lon": 2.0, "event_type": "TC", "name": "SIMON", "description": "d",
                                        "alert_level": "Red", "country": "Mexico", "from_date": "2026-10-03T00:00:00"}]})[0]
        self.assertEqual((g["source"], g["tier"], g["date"], g["severity"], g["country"]), ("gdacs", 1, "2026-10-03", "Red", "Mexico"))
        u = inc.from_usgs({"events": [{"event_id": "us1", "lat": 3.0, "lon": 4.0, "title": "Greece", "time": "2026-10-10 22:33 UTC",
                                       "magnitude": 4.2, "depth_km": 10.0, "link": "https://x/us1", "category": "M4-5"}]})[0]
        self.assertEqual((u["kind"], u["url"], u["date"]), ("earthquake", "https://x/us1", "2026-10-10"))
        c = inc.from_ucdp({"events": [{"event_id": "9", "lat": 5.0, "lon": 6.0, "conflict_name": "X", "date": "2026-08-31", "deaths_best": 4,
                                       "deaths_low": 4, "deaths_high": 4, "adm_1": "Darfur", "country": "Sudan", "category": "State-based conflict"}]})[0]
        self.assertIn("deaths best 4", c["detail"])
        self.assertEqual(c["tier"], 1)


class TestFilteringAndMerging(unittest.TestCase):
    def _rec(self, source, rid, date, title="t", lat=1.0, lon=1.0, country=""):
        return inc._record(source, rid, "k", title, date, lat, lon, "", "", country)

    def test_date_bbox_and_name_matching(self):
        recs = [self._rec("usgs", "a", "2026-10-01", "5 km N of Aden, Yemen"), self._rec("usgs", "b", "2026-10-01", "Alaska"),
                self._rec("usgs", "c", "2026-08-01", "Yemen old")]
        kept = inc.filter_records(recs, country="Yemen", since="2026-09-01", require_name_match=True)
        self.assertEqual([r["id"] for r in kept], ["a"])
        inside = inc.filter_records([self._rec("eonet", "x", "2026-10-01", lat=15.0, lon=44.0), self._rec("eonet", "y", "2026-10-01", lat=60.0, lon=10.0)],
                                    bbox=[40, 10, 50, 20])
        self.assertEqual([r["id"] for r in inside], ["x"])

    def test_merge_dedupes_per_source_and_sorts_newest_first(self):
        a, b = self._rec("gdacs", "1", "2026-10-01"), self._rec("usgs", "1", "2026-10-05")
        merged = inc.merge_records([[a], [b, a]])
        self.assertEqual([r["source"] for r in merged], ["usgs", "gdacs"])

    def test_the_source_table_rates_every_source_and_says_what_is_not_searched(self):
        # News (added 2026-10-14 at the owner's request) is the one source that is NOT asked by default and the only one below tier 1.
        self.assertEqual(set(inc.DEFAULT_SOURCES), set(inc.SOURCES) - {"news"})
        self.assertTrue(all(s["tier"] == 1 for k, s in inc.SOURCES.items() if k != "news"))
        self.assertEqual(inc.SOURCES["news"]["tier"], 3)
        for name in ("Reuters Fact Check", "AFP Fact Check", "ACLED", "Social media"):
            self.assertIn(name, inc.NOT_SEARCHED)


class TestFanOut(unittest.TestCase):
    def _stub(self, outcomes):
        def ask(source, country, bbox, days, since):
            return outcomes[source]
        return patch.object(inc, "_ask", ask)

    def _ok(self, source, n):
        return ([inc._record(source, f"{source}{i}", "k", "t", "2026-10-0" + str(1 + i % 9), 1.0, 1.0) for i in range(n)], None)

    def test_a_failing_source_is_reported_and_the_others_still_answer(self):
        outcomes = {"gdacs": self._ok("gdacs", 2), "usgs": (None, "HTTP 503"), "eonet": self._ok("eonet", 1), "ucdp": self._ok("ucdp", 0),
                    "reliefweb": (None, "timed out")}
        with self._stub(outcomes):
            out = inc.find_incident_reports_network_phase(country="Yemen", days=30)
        self.assertEqual(out["total_matched"], 3)
        self.assertEqual(sorted(f["source"] for f in out["sources_failed"]), ["reliefweb", "usgs"])
        self.assertEqual({c["source"]: c["records"] for c in out["sources_checked"]}, {"gdacs": 2, "eonet": 1, "ucdp": 0})
        self.assertIn("Reuters Fact Check", out["not_searched"])

    def test_a_request_with_no_place_is_refused(self):
        self.assertIn("error", inc.find_incident_reports_network_phase())
        self.assertIn("error", inc.find_incident_reports_network_phase(country="Yemen", days=0))
        self.assertIn("error", inc.find_incident_reports_network_phase(country="Yemen", sources=["twitter"]))
        self.assertIn("error", inc.find_incident_reports_network_phase(bbox=[10, 10, 5, 20]))

    def test_max_reports_truncates_and_says_so(self):
        outcomes = {s: self._ok(s, 3) for s in inc.SOURCES}
        with self._stub(outcomes):
            out = inc.find_incident_reports_network_phase(country="Yemen", sources=list(inc.SOURCES), max_reports=4)
        self.assertEqual((len(out["records"]), out["total_matched"], out["truncated"]), (4, 3 * len(inc.SOURCES), True))

    def test_the_reply_names_what_answered_what_failed_and_what_was_not_searched(self):
        outcomes = {"gdacs": self._ok("gdacs", 1), "usgs": (None, "HTTP 503"), "eonet": self._ok("eonet", 0), "ucdp": self._ok("ucdp", 0),
                    "reliefweb": self._ok("reliefweb", 0)}
        with self._stub(outcomes):
            fetched = inc.find_incident_reports_network_phase(country="Yemen")
        text = inc._reply_text(fetched, 1, "Incident reports")
        for needle in ("GDACS", "Could NOT be reached", "USGS", "did not verify", "not_searched", "empty result"):
            self.assertIn(needle, text)


class TestWordingNote(unittest.TestCase):
    def test_the_result_tells_the_model_not_to_call_records_verified(self):
        # rc40 hand test RC37-N2: a reply headed "Verified Incident Reports" and said "verified by USGS network"
        fetch = {"total_matched": 0, "truncated": False, "sources_checked": [], "sources_failed": [], "not_searched": [],
                 "since": "2026-09-14", "records": []}
        out = inc.add_incident_reports_layer_main_thread_phase(fetch)
        self.assertIn("never 'verified'", out["wording_note"])


class TestRegistered(unittest.TestCase):
    def test_wired_in_two_phases_as_a_create_tool(self):
        from cartogen_ai.core.agent.agent_orchestrator import TWO_PHASE_TOOLS
        from cartogen_ai.core.agent.tool_operations import get_tool_operation_type
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        self.assertIn("find_incident_reports", TOOL_REGISTRY)
        self.assertIn("find_incident_reports", TWO_PHASE_TOOLS)
        self.assertEqual(get_tool_operation_type("find_incident_reports"), "CREATE")

    def test_the_router_offers_it_for_an_incident_question(self):
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        from cartogen_ai.core.services.tool_router import ToolRouter
        names = {t["function"]["name"] for t in ToolRouter(TOOLS_SCHEMA).filter_relevant_tools("check the internet for incidents in Yemen", top_k=40)}
        self.assertIn("find_incident_reports", names)


if __name__ == "__main__":
    unittest.main()
