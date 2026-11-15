"""search_fact_checks: feed parsing, matching and the honest reply (owner request 2026-10-13). Fixtures are small copies of the shapes the
live feeds had on 2026-10-13; the network phase is exercised with a patched fetch (the live feeds were also queried from a development session)."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools import fact_check_tools as fc

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title><![CDATA[Old video of a protest in Idlib is not from Taiz]]></title><link>https://example.org/a</link>
<pubDate>Tue, 13 Oct 2026 14:37:00 +0000</pubDate><description><![CDATA[<p>The clip shows <b>Idlib</b> in 2024.</p>]]></description></item>
<item><title>Unrelated budget claim</title><link>https://example.org/b</link><pubDate>Mon, 01 Jun 2026 09:00:00 +0000</pubDate><description>Budget.</description></item>
<item><title>No link here</title><pubDate>Mon, 01 Jun 2026 09:00:00 +0000</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Fact Check: Missile video is fake</title>
<link rel="alternate" type="text/html" href="https://example.org/atom1"/><published>2026-10-10T08:00:00Z</published>
<summary>Does the video show a missile hit? No.</summary></entry></feed>"""

POLITIFACT_STYLE = """


<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" version="2.0"><channel>
<item><title>Claim about Texas</title><link>https://example.org/pf</link><pubDate>Mon, 12 Oct 2026 21:42:10 +0000</pubDate>
<description><![CDATA[Short.]]></description><content:encoded><![CDATA[<p>body</p>]]></content:encoded><snf:analytics>x</snf:analytics></item>
</channel></rss>"""

ARABIC = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>دعوة للخبراء والمدربين</title><link>https://example.org/ar0</link><pubDate>Mon, 12 Oct 2026 10:27:39 +0000</pubDate>
<category><![CDATA[أخبار منصة فتبينوا]]></category></item>
<item><title>هذا الفيديو قديم، ويُظهر عناصر من جماعة الحوثي في الضالع</title><link>https://example.org/ar1</link>
<pubDate>Mon, 12 Oct 2026 10:00:00 +0000</pubDate><category><![CDATA[زمالة_فتبينوا]]></category></item></channel></rss>"""


class TestParse(unittest.TestCase):
    def test_rss_items_become_clean_records_and_items_without_a_link_are_dropped(self):
        got = fc.parse_feed(RSS, "snopes")
        self.assertEqual([e["url"] for e in got], ["https://example.org/a", "https://example.org/b"])
        first = got[0]
        self.assertEqual((first["date"], first["source_name"]), ("2026-10-13", "Snopes"))
        self.assertNotIn("<", first["summary"])
        self.assertIn("Idlib", first["summary"])

    def test_atom_entries_are_read(self):
        got = fc.parse_feed(ATOM, "lead_stories")
        self.assertEqual((got[0]["title"], got[0]["url"], got[0]["date"]), ("Fact Check: Missile video is fake", "https://example.org/atom1", "2026-10-10"))

    def test_a_feed_with_leading_blank_lines_and_undeclared_prefixes_still_parses(self):
        got = fc.parse_feed(POLITIFACT_STYLE, "politifact")
        self.assertEqual([e["title"] for e in got], ["Claim about Texas"])

    def test_the_outlets_own_announcements_are_skipped(self):
        got = fc.parse_feed(ARABIC, "fatabyyano")
        self.assertEqual([e["url"] for e in got], ["https://example.org/ar1"])

    def test_a_feed_that_declares_entities_or_is_huge_is_refused(self):
        bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
        with self.assertRaises(ValueError):
            fc.parse_feed(bomb, "snopes")
        with self.assertRaises(ValueError):
            fc.parse_feed("<rss>" + "x" * 3_100_000 + "</rss>", "snopes")

    def test_summaries_are_capped_plain_text(self):
        long = "<rss><channel><item><title>T</title><link>https://example.org/c</link><description>" + "<b>x</b> " * 500 + "</description></item></channel></rss>"
        self.assertLessEqual(len(fc.parse_feed(long, "snopes")[0]["summary"]), 280)


class TestMatch(unittest.TestCase):
    ENTRIES = fc.parse_feed(RSS, "snopes") + fc.parse_feed(ATOM, "lead_stories") + fc.parse_feed(ARABIC, "fatabyyano")

    def test_all_words_rank_above_some_words(self):
        hits = fc.match_entries(self.ENTRIES, "old video Idlib protest")
        self.assertEqual(hits[0]["url"], "https://example.org/a")
        self.assertEqual(hits[0]["match"], "all words")

    def test_half_the_meaningful_words_is_enough_and_is_labelled(self):
        hits = fc.match_entries(self.ENTRIES, "missile video Hodeidah")
        self.assertEqual(hits[0]["match"], "some words")

    def test_nothing_in_common_is_no_match_and_filler_words_do_not_count(self):
        self.assertEqual(fc.match_entries(self.ENTRIES, "the video of the claim"), [])
        self.assertEqual(fc.match_entries(self.ENTRIES, "zzzz qqqq"), [])

    def test_the_date_window_applies(self):
        self.assertEqual(fc.match_entries(self.ENTRIES, "budget claim", since="2026-09-01"), [])
        self.assertEqual(len(fc.match_entries(self.ENTRIES, "budget claim", since="2026-01-01")), 1)

    def test_arabic_words_match(self):
        hits = fc.match_entries(self.ENTRIES, "الضالع الحوثي")
        self.assertEqual(hits[0]["url"], "https://example.org/ar1")


class TestNetworkPhase(unittest.TestCase):
    def _fake_fetch(self, source):
        if source == "snopes":
            return fc.parse_feed(RSS, "snopes"), None
        if source == "lead_stories":
            return None, "TimeoutError: slow"
        return [], None

    def test_the_reply_says_who_answered_who_failed_and_what_cannot_be_asked(self):
        with patch.object(fc, "_fetch", side_effect=self._fake_fetch):
            res = fc.search_fact_checks_network_phase("protest Idlib", days=3650, max_results=5)
        self.assertTrue(res["success"])
        self.assertEqual(res["results"][0]["url"], "https://example.org/a")
        self.assertIn("Snopes", res["sources_answered"])
        self.assertEqual(res["sources_failed"], {"Lead Stories": "TimeoutError: slow"})
        self.assertIn("Reuters Fact Check", res["sources_not_searched"])
        self.assertIn("does NOT mean the claim is true", res["coverage_note"])

    def test_no_match_still_carries_the_coverage_sentence(self):
        with patch.object(fc, "_fetch", return_value=([], None)):
            res = fc.search_fact_checks_network_phase("nothing at all here", days=30)
        self.assertEqual((res["results"], res["match_count"]), ([], 0))
        self.assertIn("NO match", res["coverage_note"])

    def test_bad_input_is_refused_with_a_reason(self):
        self.assertIn("meaningful word", fc.search_fact_checks_network_phase("the of and")["error"])
        self.assertIn("No known outlet", fc.search_fact_checks_network_phase("protest", sources=["nope"])["error"])
        self.assertIn("whole numbers", fc.search_fact_checks_network_phase("protest", days="soon")["error"])

    def test_unknown_sources_are_reported_not_hidden(self):
        with patch.object(fc, "_fetch", return_value=([], None)):
            res = fc.search_fact_checks_network_phase("protest", sources=["snopes", "reuters"])
        self.assertEqual(res["unknown_sources_ignored"], ["reuters"])


class TestWiring(unittest.TestCase):
    def test_registered_as_a_read_only_network_tool_the_router_can_find(self):
        from cartogen_ai.core.agent import agent_orchestrator, tool_operations
        from cartogen_ai.core.agent.tools import registry
        from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA
        from cartogen_ai.core.services.tool_router import ToolRouter
        self.assertIn("search_fact_checks", registry.TOOL_REGISTRY)
        self.assertIn("search_fact_checks", agent_orchestrator.NETWORK_ONLY_TOOLS)
        self.assertEqual(tool_operations.get_tool_operation_type("search_fact_checks"), tool_operations.READ)
        for query in ("is this video really from Taiz or has it been debunked", "was this footage fact-checked", "تحقق من هذا الفيديو"):
            names = {t["function"]["name"] for t in ToolRouter(TOOLS_SCHEMA).filter_relevant_tools(query, top_k=40)}
            self.assertIn("search_fact_checks", names, query)


if __name__ == "__main__":
    unittest.main()
