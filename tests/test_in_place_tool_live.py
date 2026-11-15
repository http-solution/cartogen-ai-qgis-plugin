"""PLAN-023 R11-3 in real QGIS: native:translategeometry run in place on the selected points moves exactly those points by the same amount as the normal (new-layer) run does, leaves the
other points and the user's selection alone, stays unsaved in the edit session and is one undo step; selected_only false changes every feature; a preview comes first; an unapproved
algorithm, an algorithm that cannot edit in place (buffer), a missing layer and a nothing-selected request are refused. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestRunAlgorithmInPlaceLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _points(self, name, count=3):
        layer = QgsVectorLayer("Point?crs=EPSG:32636&field=id:integer", name, "memory")
        feats = []
        for i in range(count):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i * 100.0, 0.0)))
            f.setAttributes([i])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    @staticmethod
    def _xs(layer):
        return {f["id"]: round(f.geometry().asPoint().x(), 6) for f in layer.getFeatures()}

    def _run(self, **kw):
        from cartogen_ai.core.agent.tools.in_place_tool import run_algorithm_in_place
        return run_algorithm_in_place(**kw)

    def test_selected_points_move_like_the_new_layer_run_and_undo_in_one_step(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import undo_manual_edit
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        layer = self._points("pts")
        reference = run_allowlisted_processing_algorithm("native:translategeometry", {"INPUT": "pts", "DELTA_X": 10, "DELTA_Y": 0}, new_layer_name="pts_translated")
        self.assertTrue(reference.get("success"), reference)
        expected = self._xs(QgsProject.instance().mapLayersByName("pts_translated")[0])
        layer.selectByIds([f.id() for f in layer.getFeatures() if f["id"] in (0, 2)])
        selection = sorted(layer.selectedFeatureIds())
        args = {"algorithm_id": "native:translategeometry", "layer_name": "pts", "selected_only": True, "parameters": {"DELTA_X": 10, "DELTA_Y": 0}}
        card = self._run(**args)
        self.assertEqual(card.get("status"), "PREVIEW_REQUIRED", card)
        self.assertIn("2 features", card["rationale"])
        self.assertEqual(self._xs(layer), {0: 0.0, 1: 100.0, 2: 200.0})                        # the preview changed nothing
        out = self._run(**args, confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["features_changed"], 2)
        now = self._xs(layer)
        self.assertEqual((now[0], now[2]), (expected[0], expected[2]))                      # equals the not-in-place output
        self.assertEqual(now[1], 100.0)                                                      # the unselected point did not move
        self.assertEqual(sorted(layer.selectedFeatureIds()), selection)                      # the selection is back as it was
        self.assertTrue(layer.isEditable())                                                  # unsaved, in the edit session
        undone = undo_manual_edit("pts")
        self.assertNotIn("error", undone, undone)
        self.assertEqual(self._xs(layer), {0: 0.0, 1: 100.0, 2: 200.0})                      # one undo step puts it all back

    def test_selected_only_false_changes_every_feature_and_restores_no_selection(self):
        layer = self._points("pts")
        out = self._run(algorithm_id="native:translategeometry", layer_name="pts", selected_only=False, parameters={"DELTA_X": 5, "DELTA_Y": 0}, confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["features_changed"], 3)
        self.assertEqual(self._xs(layer), {0: 5.0, 1: 105.0, 2: 205.0})
        self.assertEqual(layer.selectedFeatureCount(), 0)

    def test_requests_that_cannot_run_are_refused_and_change_nothing(self):
        layer = self._points("pts")
        cases = [({"algorithm_id": "native:translategeometry", "layer_name": "pts", "selected_only": True, "parameters": {"DELTA_X": 1}}, "nothing is selected"),
                 ({"algorithm_id": "native:notarealalgorithm", "layer_name": "pts", "selected_only": False}, "not on the allowed"),
                 ({"algorithm_id": "native:translategeometry", "layer_name": "nope", "selected_only": False}, "not found"),
                 ({"algorithm_id": "native:translategeometry", "layer_name": "pts", "selected_only": False, "parameters": {"INPUT": "x"}}, "must not contain"),
                 ({"algorithm_id": "native:buffer", "layer_name": "pts", "selected_only": False, "parameters": {"DISTANCE": 5}}, "in place")]
        for kwargs, word in cases:
            out = self._run(**kwargs, confirmed=True)
            self.assertIn(word, out.get("error", ""), kwargs)
        self.assertEqual(self._xs(layer), {0: 0.0, 1: 100.0, 2: 200.0})
        self.assertFalse(layer.isEditable())


if __name__ == "__main__":
    unittest.main()
