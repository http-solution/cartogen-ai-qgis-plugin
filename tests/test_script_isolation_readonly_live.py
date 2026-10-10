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


class TestLockUncopyableLayers(unittest.TestCase):
    """#220 (audit A06): layers with no file to copy are locked read-only in the scratch project. Pure, with fakes."""

    class _Layer:
        def __init__(self, can_lock=True):
            self.read_only = False
            self._can_lock = can_lock

        def providerType(self):      # noqa: N802 -- QGIS API name
            return "postgres"

        def setReadOnly(self, value):  # noqa: N802
            if not self._can_lock:
                raise RuntimeError("no")
            self.read_only = value

    class _Project:
        def __init__(self, layers):
            self._layers = layers

        def mapLayers(self):   # noqa: N802
            return dict(self._layers)

    def test_unhandled_layers_are_locked_and_handled_ones_are_not(self):
        from cartogen_ai.core.agent.services.script_isolation import _lock_uncopyable_layers
        db, copied = self._Layer(), self._Layer()
        locked = _lock_uncopyable_layers(self._Project({"db": db, "copied": copied}), {"copied"})
        self.assertEqual(locked, ["db"])
        self.assertTrue(db.read_only)
        self.assertFalse(copied.read_only)

    def test_a_layer_that_rejects_the_flag_does_not_stop_the_others(self):
        from cartogen_ai.core.agent.services.script_isolation import _lock_uncopyable_layers
        bad, good = self._Layer(can_lock=False), self._Layer()
        self.assertEqual(_lock_uncopyable_layers(self._Project({"bad": bad, "good": good}), set()), ["good"])


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

    def test_a_layer_with_no_file_to_copy_cannot_be_edited_in_the_scratch_project(self):
        """#220: a /vsimem/ source stands in for a database layer (an OGR layer that local_file_path does not treat as a file)."""
        from osgeo import gdal
        from cartogen_ai.core.agent.services import script_isolation as si
        name = "/vsimem/cartogen_no_copy.geojson"
        gdal.FileFromMemBuffer(name, b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":1},'
                                     b'"geometry":{"type":"Point","coordinates":[1,1]}}]}')
        self.addCleanup(gdal.Unlink, name)
        live = QgsVectorLayer(name, "no_copy", "ogr")
        self.assertTrue(live.isValid())
        QgsProject.instance().addMapLayer(live)
        work = tempfile.mkdtemp(prefix="cartogen_ro_work_")
        self.addCleanup(shutil.rmtree, work, True)
        scratch_path, _ids = si._build_scratch_project(work)
        scratch = QgsProject()
        scratch.read(scratch_path)
        layer = scratch.mapLayersByName("no_copy")[0]
        self.assertTrue(layer.readOnly())
        self.assertFalse(layer.startEditing())


if __name__ == "__main__":
    unittest.main()
