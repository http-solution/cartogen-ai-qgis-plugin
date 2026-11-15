"""PLAN-023 R11-2 in real QGIS: native:buffer over three layers gives three temporary result layers named <layer>_buffer in one new group, each with its input's feature count and the inputs
unchanged; a layer that cannot be buffered (a raster) fails alone while the others succeed; a missing layer, an existing group name, an unapproved algorithm, a selection algorithm and 21 layers
are refused before anything runs. Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from osgeo import gdal
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestRunProcessingBatchLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _points(self, name, count):
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

    def _raster(self, name):
        import numpy as np
        path = os.path.join(tempfile.mkdtemp(prefix="cartogen_batch_"), f"{name}.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 4, 4, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((500000.0, 10.0, 0.0, 4000040.0, 0.0, -10.0))
        ds.GetRasterBand(1).WriteArray(np.ones((4, 4), dtype=np.float32))
        ds = None
        layer = QgsRasterLayer(path, name)
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)

    def _run(self, **kw):
        from cartogen_ai.core.agent.tools.batch_tool import run_processing_batch
        return run_processing_batch(**kw)

    def test_three_layers_give_three_result_layers_in_one_new_group(self):
        inputs = [self._points("p1", 1), self._points("p2", 2), self._points("p3", 3)]
        out = self._run(algorithm_id="native:buffer", layers=["p1", "p2", "p3"], parameters={"DISTANCE": 10})
        self.assertTrue(out.get("success"), out)
        self.assertEqual((out["requested"], out["succeeded"], out["partial"], out["group"]), (3, 3, False, "buffer_batch"))
        group = QgsProject.instance().layerTreeRoot().findGroup("buffer_batch")
        self.assertIsNotNone(group)
        self.assertEqual(sorted(node.name() for node in group.findLayers()), ["p1_buffer", "p2_buffer", "p3_buffer"])
        for layer, expected in zip(inputs, (1, 2, 3), strict=True):
            self.assertEqual(QgsProject.instance().mapLayersByName(f"{layer.name()}_buffer")[0].featureCount(), expected)
            self.assertEqual(layer.featureCount(), expected)                                    # the inputs are unchanged

    def test_a_layer_that_cannot_be_processed_fails_alone_and_the_others_succeed(self):
        self._points("p1", 1)
        self._raster("dem")
        self._points("p3", 2)
        out = self._run(algorithm_id="native:buffer", layers=["p1", "dem", "p3"], parameters={"DISTANCE": 10}, group_name="mixed")
        self.assertTrue(out.get("success"), out)
        self.assertEqual((out["succeeded"], out["partial"]), (2, True))
        self.assertEqual([f["layer"] for f in out["failed"]], ["dem"])
        self.assertTrue(out["failed"][0]["error"])
        self.assertEqual(sorted(n.name() for n in QgsProject.instance().layerTreeRoot().findGroup("mixed").findLayers()), ["p1_buffer", "p3_buffer"])

    def test_requests_that_cannot_run_are_refused_before_anything_runs(self):
        self._points("p1", 1)
        before = len(QgsProject.instance().mapLayers())
        cases = [({"algorithm_id": "native:buffer", "layers": ["p1", "nope"]}, "not found"),
                 ({"algorithm_id": "native:notarealalgorithm", "layers": ["p1"]}, "not on the allowed"),
                 ({"algorithm_id": "native:selectbylocation", "layers": ["p1"]}, "may not do"),
                 ({"algorithm_id": "native:buffer", "layers": [f"l{i}" for i in range(21)]}, "1 to 20")]
        for kwargs, word in cases:
            out = self._run(**kwargs)
            self.assertIn(word, out["error"], kwargs["algorithm_id"])
        self.assertEqual(len(QgsProject.instance().mapLayers()), before)
        QgsProject.instance().layerTreeRoot().addGroup("taken")
        taken = self._run(algorithm_id="native:buffer", layers=["p1"], parameters={"DISTANCE": 5}, group_name="taken")
        self.assertIn("already exists", taken["error"])
        self.assertTrue(taken["nothing_was_run"])


if __name__ == "__main__":
    unittest.main()
