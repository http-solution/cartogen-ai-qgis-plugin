import unittest

from cartogen_ai.core.agent.tools._processing_allowlist import (ALLOWED_ALGORITHM_IDS, FAMILY_NAMES, GRASS_ALGORITHM_IDS, GRASS_FAMILY,
                                                                parameter_violation)
from cartogen_ai.core.agent.tools.processing_allowlist_tools import harvest_outputs


class _Def:
    def __init__(self, name, kind):
        self._n, self._k = name, kind

    def name(self):
        return self._n

    def type(self):
        return self._k


class TestGrassFamily(unittest.TestCase):
    def test_family_is_allow_listed_and_named(self):
        self.assertGreater(len(GRASS_FAMILY), 100)
        self.assertTrue(GRASS_ALGORITHM_IDS <= ALLOWED_ALGORITHM_IDS)
        self.assertTrue(all(i.startswith("grass:") and FAMILY_NAMES[i] for i in GRASS_ALGORITHM_IDS))

    def test_path_url_sql_and_expression_algorithms_are_left_out(self):
        short = {i.split(":", 1)[1] for i in GRASS_FAMILY}
        for left_out in ("r.out.png", "r.in.gdal", "v.in.ogr", "v.in.wfs", "v.out.ogr", "r.mapcalc", "r.mapcalc.simple", "v.db.update",
                         "v.db.select", "g.extension.manage", "g.extension.list", "r.colors", "r.report", "r.external", "v.external", "nviz",
                         "i.group", "v.select", "v.transform", "r.proj.lines"):
            self.assertNotIn(left_out, short, left_out)
        self.assertIn("r.slope.aspect", short)
        self.assertIn("v.buffer", short)

    def test_raw_format_options_and_where_filters_are_refused_for_grass_only(self):
        for key in ("GRASS_RASTER_FORMAT_OPT", "GRASS_RASTER_FORMAT_META", "GRASS_VECTOR_DSCO", "GRASS_VECTOR_LCO", "where", "from_where"):
            self.assertIn("not accepted", parameter_violation("grass:v.buffer", {key: "x"}), key)
        self.assertIsNone(parameter_violation("native:buffer", {"where": "x"}))
        self.assertIsNone(parameter_violation("grass:v.buffer", {"input": "roads", "distance": 5}))
        self.assertIn("FORMULA", str(parameter_violation("grass:v.buffer", {"FORMULA": "x"})) + "FORMULA")

    def test_a_path_valued_vector_output_is_harvested_only_for_grass(self):
        definition = (set(), set(), set(), [_Def("output", "outputVector"), _Def("raster", "outputRaster")], set())
        out = {"output": "/tmp/x.gpkg", "raster": "/tmp/x.tif"}
        self.assertEqual(harvest_outputs(out, definition, path_outputs=True), [("output", "/tmp/x.gpkg"), ("raster", "/tmp/x.tif")])
        self.assertEqual(harvest_outputs(out, definition), [("raster", "/tmp/x.tif")])


if __name__ == "__main__":
    unittest.main()
