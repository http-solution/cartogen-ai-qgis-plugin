# -*- coding: utf-8 -*-
"""Audit A02: re-running an analysis replaces the plugin's OWN earlier result by name, but a layer the user made with the same name
(for example an unsaved memory layer) is kept, renamed, never removed. Real QGIS layers."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _points(name, n=1):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", name, "memory")
    feats = []
    for i in range(n):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({44 + i} 15)"))
        f.setAttributes([i])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestReplaceByNameKeepsTheUsersLayers(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_a_users_unsaved_memory_layer_with_the_same_name_survives(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _replace_named_layer
        mine = _points("Origin_service_area_0", n=3)
        QgsProject.instance().addMapLayer(mine)
        my_id = mine.id()
        result = _replace_named_layer("Origin_service_area_0", _points("new_result"))
        survivor = QgsProject.instance().mapLayer(my_id)
        self.assertIsNotNone(survivor, "the user's layer was removed")
        self.assertEqual(survivor.featureCount(), 3)
        self.assertEqual(survivor.name(), "Origin_service_area_0 (previous)")
        self.assertEqual(len(QgsProject.instance().mapLayersByName("Origin_service_area_0")), 1)
        self.assertIn("Nothing of yours was deleted", result["note"])

    def test_rerunning_replaces_the_plugins_own_result_and_keeps_one_layer(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _replace_named_layer
        _replace_named_layer("Origin_service_area_0", _points("first"))
        _replace_named_layer("Origin_service_area_0", _points("second", n=2))
        layers = QgsProject.instance().mapLayersByName("Origin_service_area_0")
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0].featureCount(), 2)
        self.assertEqual(len(QgsProject.instance().mapLayers()), 1)

    def test_both_exist_user_layer_kept_and_our_old_result_replaced(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _replace_named_layer
        mine = _points("Origin_service_area_0", n=4)
        QgsProject.instance().addMapLayer(mine)
        _replace_named_layer("Origin_service_area_0", _points("first"))                  # the user's layer is set aside here
        _replace_named_layer("Origin_service_area_0", _points("second", n=2))           # our own result is replaced here
        names = sorted(layer.name() for layer in QgsProject.instance().mapLayers().values())
        self.assertEqual(names, ["Origin_service_area_0", "Origin_service_area_0 (previous)"])
        kept = QgsProject.instance().mapLayersByName("Origin_service_area_0 (previous)")[0]
        self.assertEqual(kept.featureCount(), 4)


if __name__ == "__main__":
    unittest.main()
