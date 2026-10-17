"""Topic index for the approved Processing algorithms (core/agent/algorithm_topics.py), added in rc46 after the rc45 smoke run.

The run used prompts that spelled each algorithm's name and id; a real user describes the result they want. These rows are written the
way a person would ask, with no algorithm name or id, and check that (1) the right algorithm is among the first five the index finds,
(2) `find_processing_algorithm` finds it, (3) the router offers the generic Processing tools (or a dedicated tool), and (4) the task
library does not answer with an unrelated task. They check what is OFFERED and FOUND, not what a real model then chooses."""
import unittest

from cartogen_ai.core.agent import algorithm_topics as topics
from cartogen_ai.core.agent import task_matcher, task_register
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS
from cartogen_ai.core.agent.tools.processing_allowlist_tools import search_allowed_algorithms
from cartogen_ai.core.services.tool_router import ToolRouter

GENERIC = {"find_processing_algorithm", "run_allowlisted_processing_algorithm"}

# plain request -> algorithm ids, any one of which is a correct answer (equivalents exist: native, GDAL and GRASS versions)
ROWS = [
    ("fill the gaps in my elevation raster", {"grass:r.fillnulls", "gdal:fillnodata", "native:fillnodata"}),
    ("which areas are visible from this watchtower point", {"grass:r.viewshed"}),
    ("delineate the catchments from the DEM", {"grass:r.watershed", "native:watershed"}),
    ("extract the river network from the elevation model", {"grass:r.stream.extract"}),
    ("how many hours of sun does each slope get", {"grass:r.sun.insoltime", "grass:r.sunhours"}),
    ("estimate soil erosion from rainfall and slope", {"grass:r.usler"}),
    ("compute slope and aspect from the terrain", {"grass:r.slope.aspect", "native:slope", "native:aspect", "gdal:slope"}),
    ("make contour lines from the DEM", {"grass:r.contour", "gdal:contour"}),
    ("find which parts of the road network are disconnected from each other", {"grass:v.net.components"}),
    ("rank the road junctions by how central they are", {"grass:v.net.centrality"}),
    ("make a fishnet grid over the study area", {"grass:v.mkgrid", "native:creategrid"}),
    ("create thiessen polygons around the health facilities", {"native:voronoipolygons", "grass:v.voronoi"}),
    ("union all the districts into a single layer", {"native:multiunion", "native:union", "native:dissolve"}),
    ("percentile of each cell across several rasters", {"native:cellstackpercentile"}),
    ("add area and perimeter columns to my polygons", {"native:exportaddgeometrycolumns"}),
    ("which features changed between the old and the new version of the layer", {"native:detectvectorchanges"}),
    ("zonal statistics of the elevation raster for each district", {"native:rasterlayerzonalstats", "native:zonalstatisticsfb", "grass:v.rast.stats"}),
    ("reclassify the raster using a table of ranges", {"native:reclassifybytable", "native:reclassifybylayer"}),
    ("make a heatmap of incident points", {"native:heatmapkerneldensityestimation", "qgis:heatmapkerneldensityestimation", "grass:v.kernel.rast"}),
    ("interpolate the rainfall stations into a surface", {"qgis:idwinterpolation", "native:interpolatepoint", "grass:v.surf.idw", "grass:v.surf.rst"}),
    ("simulate how a wildfire would spread", {"grass:r.spread", "grass:r.ros"}),
    ("convert the raster to polygons", {"native:pixelstopolygons", "gdal:polygonize", "grass:r.to.vect"}),
    ("find the shortest path between all pairs of towns along the roads", {"grass:v.net.allpairs", "native:shortestpathlayertopoint"}),
    ("remove tiny duplicate and dangling pieces from my line layer", {"grass:v.clean"}),
    ("simplify the boundaries to reduce vertices", {"native:simplifygeometries", "grass:v.generalize"}),
    ("landform classification into ridges and valleys", {"grass:r.geomorphon"}),
    ("flood fill from a point at water level 5 metres", {"grass:r.lake"}),
    ("cluster the points into groups by distance", {"native:dbscanclustering", "grass:v.cluster"}),
    ("random points inside the districts", {"native:randompointsinpolygons", "grass:v.random"}),
    ("terrain ruggedness index", {"gdal:triterrainruggednessindex", "native:ruggednessindex"}),
]


class TopicIndexTests(unittest.TestCase):
    def test_every_approved_algorithm_has_topic_words(self):
        index = topics._load()
        self.assertEqual(set(index), set(ALLOWED_ALGORITHM_IDS),
                         "rebuild: python tools/build_algorithm_topics.py --catalog <processing_catalog.json>")
        for alg_id, entry in index.items():
            self.assertTrue(entry["n"] or entry["k"], alg_id)

    def test_plain_requests_find_their_algorithm_in_the_first_five(self):
        misses = []
        for query, acceptable in ROWS:
            found = {alg_id for alg_id, _s, _h in topics.rank(query, limit=5)}
            if not found & acceptable:
                misses.append((query, sorted(found)[:5]))
        self.assertFalse(misses, misses)

    def test_find_processing_algorithm_search_uses_the_topic_index(self):
        for query, acceptable in ROWS:
            found = {alg_id for alg_id, _name in search_allowed_algorithms(query)}
            self.assertTrue(found & acceptable, (query, sorted(found)))

    def test_a_plain_request_is_offered_the_generic_processing_tools_or_a_dedicated_one(self):
        router = ToolRouter(TOOLS_SCHEMA)
        for query, _acceptable in ROWS:
            offered = {t["function"]["name"] for t in router.filter_relevant_tools(query)}
            self.assertTrue(offered & GENERIC, (query, "generic Processing tools not offered"))

    def test_ordinary_requests_do_not_match_an_algorithm(self):
        for query in ("zoom to the layer districts", "add the districts layer and style by population", "hi", "show me the health facilities on the map"):
            self.assertEqual(topics.rank(query), [], query)


class NamedAlgorithmTests(unittest.TestCase):
    def test_an_id_or_quoted_display_name_is_a_named_algorithm(self):
        self.assertTrue(topics.names_algorithm('Run the algorithm "Add geometry attributes" on the districts'))
        self.assertTrue(topics.names_algorithm("run grass:v.net.bridge on the roads"))
        self.assertFalse(topics.names_algorithm("add area and perimeter columns to my polygons"))
        self.assertFalse(topics.names_algorithm('Run the algorithm "Not a real algorithm name"'))

    def test_a_named_algorithm_gets_no_task_directive(self):
        """rc45 smoke run: these were answered with a confirm card for an OpenStreetMap, bridge-damage or change-detection task."""
        for query in ('Run the algorithm "Add geometry attributes" (native:exportaddgeometrycolumns) on a vector layer',
                      'Run the algorithm "v.net.bridge" (grass:v.net.bridge) on a vector layer',
                      'Run the algorithm "Detect dataset changes" (native:detectvectorchanges) on a vector layer',
                      'Run the algorithm "r.stats.zonal" (grass:r.stats.zonal) on dem + dem2'):
            verdict = task_matcher.classify(query)
            self.assertIsNone(verdict["best"], query)

    def test_a_computation_is_not_answered_by_a_show_the_data_task(self):
        for query in ("calculate soil erosion risk", "create thiessen polygons around the health facilities"):
            verdict = task_matcher.classify(query)
            self.assertTrue(verdict["best"] is None or (verdict["ambiguous"] and verdict["reason"] == "below confidence floor"), query)

    def test_a_task_that_has_its_own_analysis_tools_is_still_used(self):
        verdict = task_matcher.classify("zonal statistics of the elevation raster for each district")
        self.assertIsNotNone(verdict["best"])
        self.assertIn("zonal_statistics", verdict["best"]["tools"])



class ChartRequestTests(unittest.TestCase):
    def test_a_chart_request_is_not_answered_by_a_map_task(self):
        """rc45 smoke run, I4: 'make a chart of population by district' was matched to the WorldPop mapping task and cancelled."""
        for query in ("make a chart of population by district", "plot a histogram of the population of the districts"):
            verdict = task_matcher.classify(query)
            self.assertTrue(verdict["best"] is None or (verdict["ambiguous"] and verdict["reason"] == "below confidence floor"), query)



class TaskAlgorithmTests(unittest.TestCase):
    """rc46: register tasks now name the approved algorithms that fit them (data/task_algorithms.json)."""

    def test_every_curated_pair_names_a_real_task_and_approved_algorithms(self):
        import json

        from cartogen_ai.core.agent import task_register
        task_ids = {e["id"] for e in task_register.load()}
        with open(topics._TASK_PATH, encoding="utf-8") as fh:
            curated = json.load(fh)
        self.assertGreaterEqual(len(curated), 30)
        for task_id, algorithms in curated.items():
            self.assertIn(task_id, task_ids, task_id)
            self.assertTrue(algorithms, task_id)
            for alg_id in algorithms:
                self.assertIn(alg_id, ALLOWED_ALGORITHM_IDS, f"{task_id}: {alg_id}")

    def test_the_task_directive_names_them_and_the_generic_tools(self):
        entry = next(e for e in task_register.load() if e["id"] == "36.01")
        directive = task_matcher.task_directive(entry, {}, "determine watershed characteristics for this basin")
        self.assertIn("grass:r.watershed", directive)
        self.assertIn("run_allowlisted_processing_algorithm", directive)

    def test_a_request_the_register_recognises_gets_the_generic_processing_tools(self):
        router = ToolRouter(TOOLS_SCHEMA)
        for query in ("Map drainage systems for the camp", "Perform spatial interpolation of the rainfall readings"):
            verdict = task_matcher.classify(query)
            if verdict["best"] is None or (verdict["ambiguous"] and verdict["reason"] == "below confidence floor"):
                continue        # not recognised as a task: the topic-index route covers it (tests above)
            offered = {t["function"]["name"] for t in router.filter_relevant_tools(query)}
            self.assertTrue(offered >= GENERIC, (query, verdict["best"]["id"]))


if __name__ == "__main__":
    unittest.main()
