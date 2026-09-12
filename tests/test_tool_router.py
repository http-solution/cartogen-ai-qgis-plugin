# -*- coding: utf-8 -*-
import ast
import inspect
import unittest
from unittest.mock import patch
from cartogen_ai.core.agent.tool_router import ToolRouter
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
import cartogen_ai.core.agent.tool_router as tool_router_module


class TestToolAliasesNoDuplicateKeys(unittest.TestCase):
    """_TOOL_ALIASES is a plain dict literal -- a second `"some_tool": [...]`
    entry for a name already present doesn't raise or warn, it just silently
    overwrites the first one's aliases (confirmed live: this exact mistake
    was made and shipped in this file, discarding load_3w_data's original
    5-phrase alias list down to a narrower 4-phrase replacement, and wasn't
    caught until a full test run surfaced the recall regression). A runtime
    dict can't tell you it had a duplicate key -- this parses the source
    itself via ast to catch a repeat key before it can silently ship again."""

    def test_no_duplicate_keys_in_tool_aliases_dict(self):
        source = inspect.getsource(tool_router_module)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_TOOL_ALIASES" for t in node.targets
            ):
                keys = [k.value for k in node.value.keys]
                duplicates = {k for k in keys if keys.count(k) > 1}
                self.assertEqual(duplicates, set(), f"Duplicate _TOOL_ALIASES key(s): {duplicates}")
                return
        self.fail("_TOOL_ALIASES assignment not found via ast parse")


class TestToolRouter(unittest.TestCase):
    def test_router_filtering(self):
        router = ToolRouter(TOOLS_SCHEMA)
        filtered = router.filter_relevant_tools("Calculate NDVI on Sentinel image", top_k=15)
        self.assertLessEqual(len(filtered), 15)
        tool_names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("calculate_ndvi", tool_names)
        self.assertIn("get_layers", tool_names)  # Always included core tool


class TestExecutePyqgisScriptFallbackOnly(unittest.TestCase):
    """Point 1 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md:
    execute_pyqgis_script used to be unconditionally guaranteed a slot on
    every single query regardless of relevance (an always_include entry
    scored 1000 flat, same as genuinely-always-relevant bookkeeping tools).
    Now it only gets that guaranteed slot as a true last resort, when
    nothing else in the whole candidate set scored any real relevance --
    otherwise it competes on its own natural score like every other tool."""

    def setUp(self):
        self.router = ToolRouter(TOOLS_SCHEMA)

    def test_excluded_when_a_specific_tool_clearly_matches(self):
        # Same query as test_router_filtering above -- calculate_ndvi and
        # several other tools clearly share real vocabulary with this
        # query, so execute_pyqgis_script should no longer ride along on
        # an unconditional boost at a small top_k.
        filtered = self.router.filter_relevant_tools("Calculate NDVI on Sentinel image", top_k=15)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("calculate_ndvi", names)
        self.assertNotIn("execute_pyqgis_script", names)

    def test_included_as_a_true_last_resort_when_nothing_else_matches(self):
        # Nonsense query sharing no real vocabulary with any registered
        # tool's name/description/aliases -- the genuine "nothing else
        # fits" case this fallback exists to cover.
        filtered = self.router.filter_relevant_tools("zzqxx wqvbn fltrpz", top_k=15)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("execute_pyqgis_script", names)


class TestNoSignalQueryStaysSmall(unittest.TestCase):
    """Direct live report, 2026-09-12: a plain "hi" greeting cost ~22K total tokens for one
    API call, traced to filter_relevant_tools always padding out to the full top_k=40 even
    when nothing in the query is remotely tool-relevant -- ~8K tokens of that from irrelevant
    tool schemas alone. Two real, separate bugs found and fixed: (1) substring containment
    (not word-boundary matching) let short/common query words spuriously match inside
    unrelated tool names/descriptions ("hi" inside "histogram_equalization", "there" -- a
    genuine standalone word in several descriptions' ordinary prose -- inside real GIS
    content), which was enough to make the router think real signal existed and pad to top_k;
    (2) even a correctly-detected no-signal query still padded to top_k with random 0-score
    filler instead of returning only the genuinely useful always-include + fallback set."""

    def setUp(self):
        self.router = ToolRouter(TOOLS_SCHEMA)

    def test_hi_no_longer_false_matches_histogram_or_highlight_or_hillshade(self):
        filtered = self.router.filter_relevant_tools("hi", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertNotIn("histogram_equalization", names)
        self.assertNotIn("highlight_features", names)
        self.assertNotIn("hillshade", names)

    def test_hi_returns_only_the_always_include_and_fallback_set_not_padded_to_top_k(self):
        filtered = self.router.filter_relevant_tools("hi", top_k=40)
        names = {t.get("function", {}).get("name") for t in filtered}
        expected = {
            "get_layers", "get_attributes", "create_plan", "update_task",
            "set_task_preview", "store_project_memory", "store_global_memory",
            "generate_spatial_report", "execute_pyqgis_script",
        }
        self.assertEqual(names, expected)

    def test_common_filler_words_dont_pull_in_the_full_candidate_set(self):
        # "there" is a real standalone word in several tool descriptions' ordinary English
        # prose (not a false substring match) -- word-boundary matching alone wasn't enough
        # here, a small stopword list is what actually keeps this one small.
        for query in ("hello there", "thanks!", "ok thanks", "yes please"):
            filtered = self.router.filter_relevant_tools(query, top_k=40)
            self.assertLessEqual(len(filtered), 10, f"query {query!r} should stay small, got {len(filtered)} tools")

    def test_a_real_short_query_still_gets_the_full_candidate_pool(self):
        # Confirms the fixes above don't over-correct into suppressing genuine short
        # relevant queries -- "buffer" alone is real signal (3+ chars, a genuine tool-name
        # word, not a stopword) and must still get the full top_k treatment.
        filtered = self.router.filter_relevant_tools("buffer this layer", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("buffer_analysis", names)
        self.assertEqual(len(filtered), 40)


class TestToolRouterAliasCoverage(unittest.TestCase):
    """Regression coverage for 3 real paraphrased queries that measurably
    missed the top-30 candidate set before the alias list was added -- see
    docs/archive/API_COST_OPTIMIZATION_REVIEW.md section 1.1. Each of these tools has
    little/no vocabulary overlap with its own name/description for how a
    real user actually phrased the request."""

    def setUp(self):
        self.router = ToolRouter(TOOLS_SCHEMA)

    def test_rank_districts_by_severity_finds_severity_index(self):
        filtered = self.router.filter_relevant_tools("rank the districts by how bad the situation is", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("calculate_severity_index", names)

    def test_who_else_is_working_finds_3w_data(self):
        filtered = self.router.filter_relevant_tools("who else is working in this area", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("load_3w_data", names)

    def test_interactive_map_for_donors_finds_html_dashboard(self):
        filtered = self.router.filter_relevant_tools("make an interactive map I can send to the donors", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("generate_html_dashboard", names)

    def test_getting_more_dangerous_finds_incident_trend(self):
        """analyze_incident_trend (added v1.2.17) shares no vocabulary with this
        exact paraphrase from prompts.py rule 35's own natural-language mapping
        -- same gap category as the 3 above, closed the same way."""
        filtered = self.router.filter_relevant_tools("is this area getting more dangerous", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("analyze_incident_trend", names)

    def test_how_green_finds_ndvi(self):
        """calculate_ndvi's own description was 7 words ('Calculate NDVI from Red
        and NIR raster layers'), with zero shared vocabulary with how a real user
        actually asks -- confirmed missing from the top-40 candidate set on this
        exact query before the description was expanded and an alias added."""
        filtered = self.router.filter_relevant_tools("how green is this area", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("calculate_ndvi", names)

    def test_compare_before_after_finds_change_detection(self):
        """calculate_raster_change_detection's original description ('Compute
        pixel-wise differential change between two temporal rasters') never says
        'before'/'after'/'damage'/'compare' -- confirmed missing on this exact
        real-world phrasing before the description was expanded."""
        filtered = self.router.filter_relevant_tools("compare before and after images for damage", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("calculate_raster_change_detection", names)

    def test_cash_and_voucher_feasibility_finds_population_access_gap(self):
        """population_access_gap's description never mentions cash/voucher
        assistance despite prompts.py rule 37 explicitly routing this exact
        intent to it -- confirmed missing from the candidate set before the
        alias was added, meaning rule 37 could never have fired."""
        filtered = self.router.filter_relevant_tools("is cash and voucher assistance viable in this area", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("population_access_gap", names)

    def test_surface_water_finds_ndwi(self):
        """Same thin-description pattern as calculate_ndvi -- calculate_ndwi's
        original description never said 'water'/'flood', just the acronym NDWI,
        which no real user searching for a water/flood index would type."""
        filtered = self.router.filter_relevant_tools("how much water is in this area", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("calculate_ndwi", names)

    def test_crop_nitrogen_stress_finds_ndre(self):
        """Same thin-description pattern -- calculate_ndre's original description
        never said 'chlorophyll'/'nitrogen'/'precision agriculture', just NDRE."""
        filtered = self.router.filter_relevant_tools("crop nitrogen stress index", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("calculate_ndre", names)

    def test_raster_looks_washed_out_finds_apply_raster_stretch(self):
        """apply_raster_stretch's own name/description share little vocabulary
        with how a user actually complains about an unstyled raster -- same gap
        category as the NDVI/NDWI/NDRE cases above, closed with an alias."""
        filtered = self.router.filter_relevant_tools("this raster layer looks washed out and grey", top_k=40)
        names = [t.get("function", {}).get("name") for t in filtered]
        self.assertIn("apply_raster_stretch", names)


class TestToolRouterRecallRegression(unittest.TestCase):
    """Table-driven regression test for docs/archive/API_COST_OPTIMIZATION_REVIEW.md
    section 0's exact measurement: 9 realistic paraphrased humanitarian
    queries (the kind of phrasing a real user types, not the tool's own
    vocabulary) checked against the tool actually expected to handle each
    one. 3 of 9 (33%) missed the top-30 candidate set before section 1.1's
    fixes; this covers the full original set, not just the 3 that were
    failing, so a future change to ToolRouter or a tool's description can't
    silently regress recall on a query that happened to already be passing.
    Uses top_k=40, the value agent.py's real dispatch actually passes."""

    QUERY_TO_EXPECTED_TOOL = [
        ("which districts are underserved and need more funding", "calculate_presence_gap"),
        ("rank the districts by how bad the situation is", "calculate_severity_index"),
        ("how many people cannot reach a hospital within an hour", "population_access_gap"),
        ("hide the exact location of these GBV survivors before I share this map", "obfuscate_sensitive_points"),
        ("who else is working in this area", "load_3w_data"),
        ("get me official admin boundaries with proper codes", "fetch_hdx_admin_boundaries"),
        ("make an interactive map I can send to the donors", "generate_html_dashboard"),
        ("show reached vs target by cluster", "generate_sector_coverage_report"),
        ("get building outlines for this town", "fetch_building_footprints"),
        ("is this area getting more dangerous", "analyze_incident_trend"),
        ("how risky is this route", "score_route_incident_risk"),
        ("how green is this area", "calculate_ndvi"),
        ("compare before and after images for damage", "calculate_raster_change_detection"),
        ("is cash and voucher assistance viable in this area", "population_access_gap"),
        ("who is active in this district", "load_3w_data"),
        ("how much water is in this area", "calculate_ndwi"),
        ("crop nitrogen stress index", "calculate_ndre"),
        ("this raster layer looks washed out and grey", "apply_raster_stretch"),
    ]

    def setUp(self):
        self.router = ToolRouter(TOOLS_SCHEMA)

    def test_all_measured_queries_find_their_expected_tool(self):
        failures = []
        for query, expected_tool in self.QUERY_TO_EXPECTED_TOOL:
            filtered = self.router.filter_relevant_tools(query, top_k=40)
            names = [t.get("function", {}).get("name") for t in filtered]
            if expected_tool not in names:
                failures.append(f"{query!r} -> expected {expected_tool!r}, not in candidate set")
        self.assertEqual(failures, [])


class TestToolRouterTieBreak(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tool_router.random.shuffle")
    def test_shuffles_candidates_before_scoring_to_avoid_fixed_tie_break_order(self, mock_shuffle):
        router = ToolRouter(TOOLS_SCHEMA)
        router.filter_relevant_tools("some query with no strong matches", top_k=40)
        mock_shuffle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
