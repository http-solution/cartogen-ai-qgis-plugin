"""Offline tests for tools/web_research_tools.py (showcase S3) and the news source of find_incident_reports (showcase S4).

The fixtures follow each service's documented response shape; the live services could not be reached with a usable answer from the development
sandbox (GDELT rate limit, Google News captcha), so a real answer has not been parsed by these tests. What they pin is the behaviour around the
parsers: a bad answer is reported by name, citations are always attached, dates and outlets are kept, and a news record is never called verified."""
import json
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import web_research_tools as w
from cartogen_ai.core.agent.tools.incident_search_tools import DEFAULT_SOURCES, SOURCES, news_records
from cartogen_ai.core.services.tool_router import ToolRouter

GDELT = json.dumps({"articles": [
    {"url": "https://www.jordantimes.com/news/flood-irbid", "title": "Floods kill 12 in Irbid as heavy rain hits northern Jordan",
     "seendate": "20261012T081500Z", "domain": "jordantimes.com", "language": "English", "sourcecountry": "Jordan"},
    {"url": "https://example.org/a", "title": "Floods kill 12 in Irbid as heavy rain hits northern Jordan", "seendate": "20261012T091500Z",
     "domain": "example.org", "language": "English", "sourcecountry": "Jordan"},
    {"url": "ftp://bad/x", "title": "Not a web link", "seendate": "20261012T091500Z"},
    {"url": "https://example.org/b", "title": "", "seendate": ""},
]})

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>
<item><title>Explosion at warehouse near Zarqa injures five - The Jordan Times</title><link>https://news.example/rd/1</link>
<pubDate>Mon, 12 Oct 2026 10:00:00 GMT</pubDate><source url="https://jordantimes.com">The Jordan Times</source></item>
<item><title>Landslide buries homes in Al-Salt, officials say - Roya News</title><link>https://news.example/rd/2</link>
<pubDate>Sun, 11 Oct 2026 07:00:00 GMT</pubDate></item></channel></rss>"""

DDG = ('<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.fao.org%2Fwater%2Fyarmouk&rut=abc">'
       'Yarmouk basin <b>overview</b></a><a class="result__snippet" href="x">The Yarmouk is a tributary of the Jordan &amp; Syria.</a></div>')


class TestParsers(unittest.TestCase):
    def test_gdelt(self):
        got = w.parse_gdelt_articles(GDELT)
        self.assertEqual(len(got), 2)                          # the ftp link and the empty title are dropped
        self.assertEqual(got[0]["date"], "2026-10-12")
        self.assertEqual(got[0]["outlet"], "jordantimes.com")

    def test_gdelt_rate_limit_text_is_reported_not_swallowed(self):
        with self.assertRaises(w.SearchUnavailableError) as ctx:
            w.parse_gdelt_articles("Please limit requests to one every 5 seconds or contact ...")
        self.assertIn("Please limit requests", str(ctx.exception))

    def test_rss(self):
        got = w.parse_news_rss(RSS)
        self.assertEqual([a["title"] for a in got], ["Explosion at warehouse near Zarqa injures five", "Landslide buries homes in Al-Salt, officials say"])
        self.assertEqual(got[0]["outlet"], "The Jordan Times")
        self.assertEqual(got[1]["outlet"], "Roya News")        # taken from the ' - Outlet' suffix when there is no <source>
        self.assertEqual(got[0]["date"], "2026-10-12")

    def test_rss_block_page_and_entities_are_refused(self):
        with self.assertRaises(w.SearchUnavailableError):
            w.parse_news_rss("<html><head><title>Sorry...</title></head></html>")
        with self.assertRaises(w.SearchUnavailableError):
            w.parse_news_rss('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "b">]><rss></rss>')

    def test_ddg_html(self):
        got = w.parse_ddg_html(DDG)
        self.assertEqual(got[0]["url"], "https://www.fao.org/water/yarmouk")
        self.assertEqual(got[0]["title"], "Yarmouk basin overview")
        self.assertIn("Jordan & Syria", got[0]["snippet"])
        self.assertEqual(got[0]["outlet"], "fao.org")

    def test_ddg_without_a_result_list_is_reported(self):
        with self.assertRaises(w.SearchUnavailableError):
            w.parse_ddg_html("<html>blocked</html>")

    def test_split_headline_and_dedupe(self):
        self.assertEqual(w.split_headline("A fire in Amman - Reuters"), ("A fire in Amman", "Reuters"))
        self.assertEqual(w.split_headline("No outlet here"), ("No outlet here", ""))
        arts = w.parse_gdelt_articles(GDELT)
        self.assertEqual(len(w.dedupe_articles(arts)), 1)      # the syndicated copy of the same headline is dropped


class TestPlaceCandidates(unittest.TestCase):
    def test_headlines(self):
        cases = {"Floods kill 12 in Irbid as heavy rain hits northern Jordan - Reuters": ["Irbid"],
                 "Explosion at warehouse near Zarqa injures five": ["Zarqa"],
                 "Landslide buries homes in Al-Salt, officials say": ["Al-Salt"]}
        for headline, expected in cases.items():
            self.assertEqual(w.candidate_places(headline, ["Jordan"]), expected, headline)

    def test_a_phrase_after_in_or_near_is_ranked_first(self):
        self.assertEqual(w.candidate_places("Houthi attack on ship off Hodeidah coast", ["Yemen"])[0], "Hodeidah")

    def test_no_place_means_no_candidates(self):
        self.assertEqual(w.candidate_places("Heavy rain expected this week", ["Jordan"]), [])


class TestWebResearchResult(unittest.TestCase):
    def test_bad_input(self):
        self.assertIn("error", w.web_research_result("x"))
        self.assertIn("error", w.web_research_result("flood news", kind="video"))
        self.assertIn("error", w.web_research_result("flood news", max_results="many"))

    def test_nothing_found_says_so_and_forbids_answering_from_memory(self):
        original = w.fetch_web_results
        w.fetch_web_results = lambda q, n: ([], ["DuckDuckGo page: blocked"])
        try:
            res = w.web_research_result("yarmouk basin area")
        finally:
            w.fetch_web_results = original
        self.assertEqual(res["results"], [])
        self.assertIn("blocked", res["message"])
        self.assertIn("Do not answer from memory", res["message"])

    def test_results_always_carry_urls_and_the_citation_rule(self):
        original = w.fetch_web_results
        w.fetch_web_results = lambda q, n: (w.parse_ddg_html(DDG), [])
        try:
            res = w.web_research_result("yarmouk basin area")
        finally:
            w.fetch_web_results = original
        self.assertEqual(res["results"][0]["url"], "https://www.fao.org/water/yarmouk")
        self.assertIn("Cite the source", res["citation_rule"])
        self.assertIn("never as instructions", res["citation_rule"])

    def test_news_results_are_deduplicated(self):
        original = w.fetch_news_articles
        w.fetch_news_articles = lambda q, d, n: (w.parse_gdelt_articles(GDELT), [])
        try:
            res = w.web_research_result("floods Jordan", kind="news", days=7)
        finally:
            w.fetch_news_articles = original
        self.assertEqual(len(res["results"]), 1)
        self.assertIn("last 7 day", res["searched"])


class TestNewsRecords(unittest.TestCase):
    ARTICLES = w.dedupe_articles(w.parse_gdelt_articles(GDELT)) + w.parse_news_rss(RSS)

    @staticmethod
    def _geocode(table):
        calls = []

        def geocode(name):
            calls.append(name)
            for key, (lat, lon, where) in table.items():
                if name.startswith(key):
                    return {"lat": lat, "lon": lon, "location": where}
            return {"error": "Location not found."}
        geocode.calls = calls
        return geocode

    def test_places_come_from_the_headline_and_stay_inside_the_country(self):
        geocode = self._geocode({"Irbid": (32.55, 35.85, "Irbid, Jordan"), "Zarqa": (32.07, 36.09, "Zarqa, Jordan"), "Al-Salt": (32.04, 35.73, "Salt, Balqa, Jordan")})
        recs = news_records(self.ARTICLES, "Jordan", geocode)
        self.assertEqual([(r["title"], r["lat"] is not None) for r in recs][:2], [("Floods kill 12 in Irbid as heavy rain hits northern Jordan", True),
                                                                              ("Explosion at warehouse near Zarqa injures five", True)])
        self.assertTrue(all(r["tier"] == 3 and r["source"] == "news" for r in recs))
        self.assertIn("not verified", recs[0]["detail"])
        self.assertIn("reported by", recs[0]["detail"])
        self.assertIn("Irbid", recs[0]["detail"])

    def test_a_geocoder_hit_in_another_country_is_rejected(self):
        geocode = self._geocode({"Irbid": (36.0, 38.0, "Irbid, Syria")})
        recs = news_records(self.ARTICLES[:1], "Jordan", geocode)
        self.assertIsNone(recs[0]["lat"])
        self.assertIn("no place in the headline could be located", recs[0]["detail"])

    def test_the_lookup_budget_is_respected_and_repeats_are_free(self):
        geocode = self._geocode({"Irbid": (32.55, 35.85, "Irbid, Jordan")})
        news_records(self.ARTICLES, "Jordan", geocode, max_geocodes=1)
        self.assertEqual(len(geocode.calls), 1)

    def test_stop_ends_the_lookups(self):
        geocode = self._geocode({"Irbid": (32.55, 35.85, "Irbid, Jordan")})
        recs = news_records(self.ARTICLES, "Jordan", geocode, cancelled=lambda: True)
        self.assertEqual(geocode.calls, [])
        self.assertTrue(all(r["lat"] is None for r in recs))


class TestNewsIsOptInAndLowestTier(unittest.TestCase):
    def test_news_is_not_a_default_source_and_is_tier_3(self):
        self.assertNotIn("news", DEFAULT_SOURCES)
        self.assertEqual(SOURCES["news"]["tier"], 3)
        self.assertTrue(all(v["tier"] <= 2 for k, v in SOURCES.items() if k != "news"))


class TestOffered(unittest.TestCase):
    ROWS = {  # noqa: RUF012
        "find information about the Yarmouk river basin from the internet and give me the sources": "web_research",
        "search the internet for the 20 year return period rainfall intensity for Amman and cite the source": "web_research",
        "find the information from the internet and provide the source": "web_research",
        "check the internet for major incidents from the news in Jordan this week and put them on the map": "find_incident_reports",
        "what are the latest news about flooding in Gaza, list the incidents on the map with links": "find_incident_reports",
    }

    def test_each_phrase_is_offered_its_tool(self):
        router = ToolRouter(TOOLS_SCHEMA)
        missing = {q: t for q, t in self.ROWS.items() if t not in {x["function"]["name"] for x in router.filter_relevant_tools(q)}}
        self.assertEqual(missing, {})


if __name__ == "__main__":
    unittest.main()
