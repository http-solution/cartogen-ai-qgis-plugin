# -*- coding: utf-8 -*-
"""Live-QGIS test for audit A06: the isolated script's scratch project holds COPIES of file-backed layers, so editing them cannot
change the user's files. Simulates the worker by editing the scratch project directly. Written without hand-testing; the Docker
QGIS run is the only execution evidence."""
import os
import shutil
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorFileWriter, QgsVectorLayer, QgsCoordinateTransformContext
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


class TestLocalFilePath(unittest.TestCase):
    def test_non_files_are_not_copied(self):
        from cartogen_ai.core.agent.services.script_isolation import local_file_path
        for source in ("", None, "dbname='x' table=\"t\"", "/vsicurl/http://a/b.tif", "https://a/b.gpkg", "PG:dbname=x"):
            self.assertIsNone(local_file_path(source))

    def test_a_real_file_with_layername_suffix_resolves(self):
        from cartogen_ai.core.agent.services.script_isolation import local_file_path
        handle, path = tempfile.mkstemp(suffix=".gpkg")
        os.close(handle)
        self.addCleanup(os.remove, path)
        self.assertEqual(local_file_path(path + "|layername=roads"), path)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestScratchProjectIsReadOnlyCopy(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tempdir = tempfile.mkdtemp(prefix="cartogen_ro_test_")
        self.addCleanup(shutil.rmtree, self.tempdir, True)

    def test_deleting_features_in_the_scratch_copy_leaves_the_users_file_alone(self):
        from cartogen_ai.core.agent.services import script_isolation as si
        mem = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", "src", "memory")
        feats = []
        for i in range(3):
            f = QgsFeature(mem.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({i} {i})"))
            f.setAttributes([i])
            feats.append(f)
        mem.dataProvider().addFeatures(feats)
        user_file = os.path.join(self.tempdir, "user_data.gpkg")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        QgsVectorFileWriter.writeAsVectorFormatV3(mem, user_file, QgsCoordinateTransformContext(), options)
        live = QgsVectorLayer(user_file, "user_data", "ogr")
        self.assertTrue(live.isValid())
        QgsProject.instance().addMapLayer(live)

        work = tempfile.mkdtemp(prefix="cartogen_ro_work_")
        self.addCleanup(shutil.rmtree, work, True)
        scratch_path, _memory_ids = si._build_scratch_project(work)
        scratch = QgsProject()
        scratch.read(scratch_path)
        layer = scratch.mapLayersByName("user_data")[0]
        self.assertNotEqual(os.path.normcase(layer.source().split("|")[0]), os.path.normcase(user_file))
        self.assertTrue(layer.startEditing())
        layer.deleteFeatures([f.id() for f in layer.getFeatures()])
        self.assertTrue(layer.commitChanges())

        reopened = QgsVectorLayer(user_file, "check", "ogr")
        self.assertEqual(reopened.featureCount(), 3)


if __name__ == "__main__":
    unittest.main()
