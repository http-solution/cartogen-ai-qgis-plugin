"""Live run of analyze_hotspots_gi_star (PLAN-023 R2-2) on real QGIS layers. Known answer: one cell of 10 among zeros on a 5 by 5 rook grid (each cell counts itself) has Gi* z = 2.0 exactly at the cell and at its four rook neighbours, and the new layer, its fields, the classes and every refusal are read back. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


def _grid(name, values, rows, cols, crs="EPSG:3857"):
    layer = QgsVectorLayer(f"Polygon?crs={crs}&field=v:double&field=label:string", name, "memory")
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


def _block_values():
    values = [1.0] * 36
    for r in (2, 3):
        for c in (2, 3):
            values[r * 6 + c] = 20.0
    return values


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestHotspotTool(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _run(self, *args, **kwargs):
        from cartogen_ai.core.agent.tools.hotspot_tool import analyze_hotspots_gi_star
        return analyze_hotspots_gi_star(*args, **kwargs)

    def test_one_high_cell_has_z_two_at_the_cell_and_its_neighbours(self):
        values = [0.0] * 25
        values[12] = 10.0
        _grid("g", values, 5, 5)
        result = self._run("g", "v", weights="rook", fdr=False, alpha=0.05)
        self.assertTrue(result.get("success"), result)
        out = QgsProject.instance().mapLayersByName("g_gi_star")[0]
        by_label = {f["src_id"]: f["gi_z"] for f in out.getFeatures()}
        first = min(by_label)                                           # memory-layer ids may start at 1, not 0
        z = {k - first: v for k, v in by_label.items()}
        for cell in (12, 7, 11, 13, 17):
            self.assertAlmostEqual(z[cell], 2.0, places=3)
        self.assertEqual(out.featureCount(), 25)
        self.assertAlmostEqual(max(z.values()), 2.0, places=3)

    def test_a_block_of_highs_is_found_and_the_new_layer_has_the_documented_fields(self):
        source = _grid("g", _block_values(), 6, 6)
        before = [(f.id(), f["v"], f["label"]) for f in source.getFeatures()]
        count_before = len(QgsProject.instance().mapLayers())
        result = self._run("g", "v", weights="queen")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["output_layer"], "g_gi_star")
        self.assertEqual(len(QgsProject.instance().mapLayers()), count_before + 1)
        out = QgsProject.instance().mapLayersByName("g_gi_star")[0]
        self.assertEqual([f.name() for f in out.fields()], ["src_id", "value", "gi_z", "gi_p", "gi_q", "gi_class", "neighbours"])
        self.assertEqual(out.crs().authid(), "EPSG:3857")
        classes = {f["gi_class"] for f in out.getFeatures()}
        self.assertLessEqual(classes, {"Hot spot 99%", "Hot spot 95%", "Hot spot 90%", "Cold spot 99%", "Cold spot 95%", "Cold spot 90%", "Not significant", "No neighbours"})
        self.assertGreaterEqual(result["hot_spots"], 1)
        self.assertEqual(sum(result["classes"].values()), 36)
        self.assertTrue(result["fdr"])
        self.assertIn("corrected", result["summary"])
        self.assertTrue(result["notes"])
        self.assertEqual([(f.id(), f["v"], f["label"]) for f in source.getFeatures()], before)
        self.assertFalse(source.isEditable())

    def test_without_the_correction_the_reply_says_so(self):
        _grid("g", _block_values(), 6, 6)
        result = self._run("g", "v", fdr=False)
        self.assertTrue(result.get("success"), result)
        self.assertFalse(result["fdr"])
        self.assertIn("NOT corrected", result["summary"])

    def test_a_uniform_field_has_no_spots_and_says_why(self):
        _grid("g", [3.0] * 16, 4, 4)
        result = self._run("g", "v")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["hot_spots"] + result["cold_spots"], 0)
        self.assertIn("same value", result["no_variation"])

    def test_a_custom_output_name_is_used(self):
        _grid("g", _block_values(), 6, 6)
        result = self._run("g", "v", output_layer_name="my_hot")
        self.assertEqual(result["output_layer"], "my_hot")
        self.assertTrue(QgsProject.instance().mapLayersByName("my_hot"))

    def test_refusals_name_the_cause(self):
        _grid("g", _block_values(), 6, 6)
        self.assertIn("not found", self._run("nope", "v")["error"])
        self.assertIn("not found", self._run("g", "nope")["error"])
        self.assertIn("not numeric", self._run("g", "label")["error"])
        self.assertIn("Unknown weights", self._run("g", "v", weights="bishop")["error"])
        self.assertIn("needs k", self._run("g", "v", weights="knn")["error"])
        self.assertIn("needs distance", self._run("g", "v", weights="distance")["error"])
        self.assertIn("alpha", self._run("g", "v", alpha=2)["error"].lower())


if __name__ == "__main__":
    unittest.main()
