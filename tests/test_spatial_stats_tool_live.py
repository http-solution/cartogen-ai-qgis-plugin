"""Live run of calculate_spatial_autocorrelation (PLAN-023 R2-1) on real QGIS layers: the statistic, the neighbour counts, the new local layer and every refusal are read back. Known answers: a 4 by 4 checkerboard with
rook weights has Moran's I = -1 exactly and 3.0 neighbours per feature on average (48 links); queen adds the 18 diagonal pairs (84 links, 5.25 on average). Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


def _grid_layer(name, values, rows=4, cols=4, crs="EPSG:3857", field_type="double"):
    layer = QgsVectorLayer(f"Polygon?crs={crs}&field=v:{field_type}&field=label:string", name, "memory")
    feats = []
    for i, value in enumerate(values):
        r, c = divmod(i, cols)
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({c} {r},{c + 1} {r},{c + 1} {r + 1},{c} {r + 1},{c} {r}))"))
        f.setAttributes([value, f"cell{i}"])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    return layer


def _points_layer(name, coords, values, crs="EPSG:3857"):
    layer = QgsVectorLayer(f"Point?crs={crs}&field=v:double", name, "memory")
    feats = []
    for (x, y), value in zip(coords, values, strict=True):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} {y})"))
        f.setAttributes([value])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    return layer


CHECKER = [float((-1) ** (r + c)) for r in range(4) for c in range(4)]


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestSpatialAutocorrelationTool(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _run(self, *args, **kwargs):
        from cartogen_ai.core.agent.tools.spatial_stats_tool import calculate_spatial_autocorrelation
        return calculate_spatial_autocorrelation(*args, **kwargs)

    def test_rook_on_a_checkerboard_is_minus_one_with_three_neighbours_on_average(self):
        _grid_layer("board", CHECKER)
        result = self._run("board", "v", weights="rook", permutations=199)
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["moran_i"], -1.0)
        self.assertAlmostEqual(result["expected_i"], -0.0667, places=4)
        self.assertEqual(result["features"], 16)
        self.assertEqual(result["mean_neighbours"], 3.0)
        self.assertEqual(result["islands"], 0)
        self.assertEqual(result["separate_groups"], 1)
        self.assertLessEqual(result["p_value"], 0.02)
        self.assertIn("DIFFERENT values", result["interpretation"])
        self.assertIn("not why", result["note"])

    def test_queen_adds_the_diagonal_neighbours(self):
        _grid_layer("board", CHECKER)
        result = self._run("board", "v", weights="queen", permutations=199)
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["mean_neighbours"], 5.25)
        self.assertGreater(result["moran_i"], -1.0)

    def test_a_smooth_gradient_is_clustered(self):
        _grid_layer("grad", [float(r + c) for r in range(6) for c in range(6)], rows=6, cols=6)
        result = self._run("grad", "v", weights="rook", permutations=499, seed=3)
        self.assertTrue(result.get("success"), result)
        self.assertAlmostEqual(result["moran_i"], 0.8889, places=4)
        self.assertLessEqual(result["p_value"], 0.01)
        self.assertIn("SIMILAR values", result["interpretation"])

    def test_the_same_seed_gives_the_same_answer(self):
        _grid_layer("grad", [float(r * 3 + (c * 7) % 5) for r in range(5) for c in range(5)], rows=5, cols=5)
        a = self._run("grad", "v", permutations=199, seed=7)
        b = self._run("grad", "v", permutations=199, seed=7)
        self.assertEqual(a, b)

    def test_write_local_adds_a_new_layer_and_leaves_the_input_alone(self):
        source = _grid_layer("board", [float(r + c) for r in range(4) for c in range(4)])
        before = [(f.id(), f["v"], f["label"]) for f in source.getFeatures()]
        fields_before = [f.name() for f in source.fields()]
        count_before = len(QgsProject.instance().mapLayers())
        result = self._run("board", "v", weights="rook", permutations=199, write_local=True)
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["local_layer"], "board_lisa")
        self.assertEqual(len(QgsProject.instance().mapLayers()), count_before + 1)
        local = QgsProject.instance().mapLayersByName("board_lisa")[0]
        self.assertEqual(local.featureCount(), 16)
        self.assertEqual([f.name() for f in local.fields()], ["src_id", "value", "lisa_i", "lisa_p", "lisa_class"])
        self.assertEqual(local.crs().authid(), "EPSG:3857")
        classes = {f["lisa_class"] for f in local.getFeatures()}
        self.assertLessEqual(classes, {"HH", "LL", "HL", "LH", "not significant", "no neighbours"})
        self.assertEqual(sum(result["local_counts"].values()), 16)
        self.assertIn("not corrected", result["local_note"])
        self.assertEqual([(f.id(), f["v"], f["label"]) for f in source.getFeatures()], before)
        self.assertEqual([f.name() for f in source.fields()], fields_before)
        self.assertFalse(source.isEditable())

    def test_a_custom_output_name_is_used(self):
        _grid_layer("board", [float(r + c) for r in range(4) for c in range(4)])
        result = self._run("board", "v", permutations=99, write_local=True, output_name="my_lisa")
        self.assertEqual(result["local_layer"], "my_lisa")
        self.assertTrue(QgsProject.instance().mapLayersByName("my_lisa"))

    def test_knn_and_distance_on_points(self):
        coords = [(x * 100.0, y * 100.0) for y in range(4) for x in range(4)]
        _points_layer("pts", coords, [float(x + y) for y in range(4) for x in range(4)])
        knn = self._run("pts", "v", weights="knn", k=4, permutations=199)
        self.assertTrue(knn.get("success"), knn)
        self.assertEqual(knn["mean_neighbours"], 4.0)
        band = self._run("pts", "v", weights="distance", distance=101.0, permutations=199)
        self.assertTrue(band.get("success"), band)
        self.assertEqual(band["mean_neighbours"], 3.0)

    def test_two_polygons_that_do_not_touch_are_islands_and_the_reply_says_so(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:3857&field=v:double", "apart", "memory")
        feats = []
        for x, v in [(0, 1.0), (1, 2.0), (2, 3.0), (20, 9.0)]:
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 0,{x + 1} 0,{x + 1} 1,{x} 1,{x} 0))"))
            f.setAttributes([v])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        result = self._run("apart", "v", weights="rook", permutations=99)
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["islands"], 1)
        self.assertEqual(result["separate_groups"], 2)
        self.assertIn("no neighbour", result["island_warning"])

    def test_refusals(self):
        _grid_layer("board", CHECKER)
        _grid_layer("flat", [4.0] * 16)
        _points_layer("pts", [(0, 0), (1, 1), (2, 2), (3, 3)], [1.0, 2.0, 3.0, 4.0])
        _points_layer("deg", [(0, 0), (1, 1), (2, 2), (3, 3)], [1.0, 2.0, 3.0, 4.0], crs="EPSG:4326")
        gappy = _grid_layer("gappy", CHECKER)
        gappy.dataProvider().changeAttributeValues({3: {0: None}})
        cases = [
            (("missing", "v"), {}, "not found"),
            (("board", "nope"), {}, "Field 'nope' not found"),
            (("board", "label"), {}, "not numeric"),
            (("board", "v"), {"weights": "bishop"}, "Unknown weights"),
            (("pts", "v"), {"weights": "queen"}, "not a polygon layer"),
            (("board", "v"), {"weights": "knn"}, "needs k"),
            (("board", "v"), {"weights": "distance"}, "needs distance"),
            (("deg", "v"), {"weights": "distance", "distance": 1.0}, "projected CRS"),
            (("flat", "v"), {"permutations": 99}, "all values are equal"),
            (("board", "v"), {"permutations": 5}, "permutations must be"),
            (("gappy", "v"), {"permutations": 99}, "have no number"),
            (("pts", "v"), {"weights": "knn", "k": 9, "permutations": 99}, "k must be"),
        ]
        for args, kwargs, expected in cases:
            result = self._run(*args, **kwargs)
            self.assertIn(expected, result.get("error", ""), f"{args} {kwargs}: {result}")


if __name__ == "__main__":
    unittest.main()
