# -*- coding: utf-8 -*-
"""Live-QGIS test of result adoption after an isolated script (audit F09, F10 -> GitHub #145, #146).

Simulates the worker's output instead of spawning it: the live project is snapshotted with the real _build_scratch_project, the
scratch copy is changed the way a script would change it, and the real _reconcile_results applies it. Written without a QGIS
install: CI's first run is its first execution."""
import os
import shutil
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _memory_layer(name, rows):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer&field=v:integer", name, "memory")
    feats = []
    for i, (value, wkt) in enumerate(rows):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([i + 1, value])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestReconcileAdoption(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tempdir = tempfile.mkdtemp(prefix="cartogen_reconcile_test_")
        self.addCleanup(shutil.rmtree, self.tempdir, True)

    def _simulate_worker(self, change):
        """Snapshot the live project, let `change(result_project)` edit it like a script would, write the result project."""
        from cartogen_ai.core.agent.services import script_isolation as si
        scratch_path, memory_ids = si._build_scratch_project(self.tempdir)
        result = QgsProject()
        result.read(scratch_path)
        change(result)
        result_path = os.path.join(self.tempdir, "result.qgz")
        result.write(result_path)
        return result_path, memory_ids

    def test_a_same_count_attribute_edit_reaches_the_live_memory_layer(self):
        live = _memory_layer("mem", [(1, "POINT(0 0)"), (2, "POINT(1 1)")])
        QgsProject.instance().addMapLayer(live)
        pre_ids = set(QgsProject.instance().mapLayers().keys())

        def change(result):
            layer = result.mapLayersByName("mem")[0]
            layer.startEditing()
            idx = layer.fields().indexOf("v")
            fid = next(f.id() for f in layer.getFeatures() if f["id"] == 1)
            layer.changeAttributeValue(fid, idx, 99)
            self.assertTrue(layer.commitChanges())

        result_path, memory_ids = self._simulate_worker(change)
        from cartogen_ai.core.agent.services import script_isolation as si
        _new, updated, problems = si._reconcile_results(result_path, pre_ids, memory_ids)
        self.assertEqual(problems, [])
        self.assertEqual(updated, ["mem"])
        self.assertEqual(sorted(f["v"] for f in live.getFeatures()), [2, 99])
        self.assertEqual(live.featureCount(), 2)

    def test_an_unchanged_memory_layer_is_left_alone(self):
        live = _memory_layer("mem", [(1, "POINT(0 0)")])
        QgsProject.instance().addMapLayer(live)
        pre_ids = set(QgsProject.instance().mapLayers().keys())
        result_path, memory_ids = self._simulate_worker(lambda result: None)
        from cartogen_ai.core.agent.services import script_isolation as si
        _new, updated, problems = si._reconcile_results(result_path, pre_ids, memory_ids)
        self.assertEqual((updated, problems), ([], []))

    def test_a_new_layer_survives_the_scratch_directory_being_deleted(self):
        QgsProject.instance().addMapLayer(_memory_layer("mem", [(1, "POINT(0 0)")]))
        pre_ids = set(QgsProject.instance().mapLayers().keys())

        def change(result):
            from cartogen_ai.core.agent.services import script_isolation as si
            made = _memory_layer("made_by_script", [(5, "POINT(3 3)"), (6, "POINT(4 4)")])
            path = os.path.join(self.tempdir, "out_made.gpkg")
            si._export_layer_to_gpkg(made, path)
            result.addMapLayer(QgsVectorLayer(path, "made_by_script", "ogr"))

        result_path, memory_ids = self._simulate_worker(change)
        from cartogen_ai.core.agent.services import script_isolation as si
        new, _updated, problems = si._reconcile_results(result_path, pre_ids, memory_ids)
        self.assertEqual(problems, [])
        self.assertEqual(new, ["made_by_script"])
        adopted = QgsProject.instance().mapLayersByName("made_by_script")[0]
        self.assertEqual(adopted.providerType(), "memory")                  # not an OGR source inside the temp directory
        shutil.rmtree(self.tempdir, ignore_errors=True)                      # what run_isolated_script's `finally` does
        self.assertEqual(adopted.featureCount(), 2)
        self.assertEqual(sorted(f["v"] for f in adopted.getFeatures()), [5, 6])


if __name__ == "__main__":
    unittest.main()
