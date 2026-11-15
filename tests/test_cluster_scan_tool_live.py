"""Live run of detect_spatial_clusters (PLAN-023 R2-3) on real QGIS layers. Known answer: on a 10 by 10 grid of areas with 100 people each, a 3 by 3 block with 15 cases among 5 elsewhere is found centred on the middle
area (feature at row 4, column 4), with 9 areas, 135 cases against 53.1 expected, radius sqrt(2) and p <= 0.01; a layer with no planted block has no significant cluster; the new circle layer, its fields and every refusal are read back.
Written without a QGIS install: CI's first run is its first execution."""
import math
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


def _points(name, cases, pops=None, crs="EPSG:3857", case_type="integer"):
    layer = QgsVectorLayer(f"Point?crs={crs}&field=cases:{case_type}&field=pop:double&field=label:string", name, "memory")
    feats = []
    for i, c in enumerate(cases):
        r, col = divmod(i, 10)
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({col * 1000} {r * 1000})"))
        f.setAttributes([c, 100.0 if pops is None else pops[i], f"a{i}"])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    return layer


def _planted():
    cases = [5] * 100
    for y in (3, 4, 5):
        for x in (3, 4, 5):
            cases[y * 10 + x] = 15
    return cases


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestClusterScanTool(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _run(self, *args, **kwargs):
        from cartogen_ai.core.agent.tools.cluster_scan_tool import detect_spatial_clusters
        return detect_spatial_clusters(*args, **kwargs)

    def test_a_planted_block_is_found_with_the_hand_computed_numbers(self):
        source = _points("pts", _planted())
        before = [(f.id(), f["cases"], f["label"]) for f in source.getFeatures()]
        result = self._run("pts", "cases", "pop", monte_carlo=499)
        self.assertTrue(result.get("success"), result)
        best = result["clusters"][0]
        first = min(f.id() for f in source.getFeatures())
        self.assertEqual(best["centre_id"] - first, 44)
        self.assertEqual(best["areas"], 9)
        self.assertEqual(best["cases"], 135)
        self.assertAlmostEqual(best["expected"], 53.1, places=2)
        self.assertAlmostEqual(best["radius"], math.sqrt(2) * 1000, places=1)
        self.assertLessEqual(best["p_value"], 0.01)
        self.assertTrue(best["significant"])
        self.assertIn("Most likely cluster", result["summary"])
        self.assertEqual([(f.id(), f["cases"], f["label"]) for f in source.getFeatures()], before)
        self.assertFalse(source.isEditable())

    def test_the_circle_layer_has_the_documented_fields_and_one_polygon_per_cluster(self):
        _points("pts", _planted())
        count = len(QgsProject.instance().mapLayers())
        result = self._run("pts", "cases", "pop", monte_carlo=199)
        self.assertEqual(result["output_layer"], "pts_scan_clusters")
        self.assertEqual(len(QgsProject.instance().mapLayers()), count + 1)
        out = QgsProject.instance().mapLayersByName("pts_scan_clusters")[0]
        self.assertEqual([f.name() for f in out.fields()], ["cluster", "centre_id", "areas", "radius", "cases", "expected", "rel_risk", "llr", "p_value", "significant"])
        self.assertEqual(out.crs().authid(), "EPSG:3857")
        self.assertEqual(out.featureCount(), len(result["clusters"]))
        self.assertTrue(all(f.geometry().area() > 0 for f in out.getFeatures()))

    def test_no_planted_block_means_no_significant_cluster(self):
        cases = [5] * 100
        cases[44], cases[12] = 6, 4
        _points("pts", cases)
        result = self._run("pts", "cases", "pop", monte_carlo=499)
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["significant_clusters"], 0)
        self.assertIn("No cluster stands out", result["summary"])

    def test_the_same_seed_gives_the_same_answer(self):
        _points("pts", _planted())
        a = self._run("pts", "cases", "pop", monte_carlo=199, seed=9, output_layer_name="a")
        b = self._run("pts", "cases", "pop", monte_carlo=199, seed=9, output_layer_name="b")
        a.pop("output_layer"), b.pop("output_layer")
        self.assertEqual(a, b)

    def test_a_custom_name_and_the_population_cap_are_used(self):
        _points("pts", _planted())
        result = self._run("pts", "cases", "pop", monte_carlo=99, max_pop_fraction=0.05, output_layer_name="mine")
        self.assertEqual(result["output_layer"], "mine")
        for c in result["clusters"]:
            self.assertLessEqual(c["areas"] * 100, 0.05 * 10000 + 1e-9)

    def test_refusals_name_the_cause(self):
        _points("pts", _planted())
        _points("geo", _planted(), crs="EPSG:4326")
        _points("frac", [2.5] + [5] * 99, case_type="double")
        _points("zero", [5] * 100, pops=[0.0] + [100.0] * 99)
        self.assertIn("not found", self._run("nope", "cases", "pop")["error"])
        self.assertIn("not found", self._run("pts", "nope", "pop")["error"])
        self.assertIn("not numeric", self._run("pts", "cases", "label")["error"])
        self.assertIn("projected", self._run("geo", "cases", "pop")["error"])
        self.assertIn("whole-number", self._run("frac", "cases", "pop")["error"])
        self.assertIn("population above zero", self._run("zero", "cases", "pop")["error"])
        self.assertIn("not built", self._run("pts", "cases", "pop", model="bernoulli")["error"])
        self.assertIn("99 to 9999", self._run("pts", "cases", "pop", monte_carlo=5)["error"])
        self.assertIn("max_pop_fraction", self._run("pts", "cases", "pop", max_pop_fraction=0.9)["error"])


if __name__ == "__main__":
    unittest.main()
