# -*- coding: utf-8 -*-
"""Live-QGIS regression tests for the rc7 smoke-test fixes (finding F17: the offline suite cannot
see real-QGIS behaviour). Runs only where qgis.core exists (the CI `qgis-live-tests` job).

Written 2026-09-30 WITHOUT access to a QGIS install, so these have not been run yet -- the first CI
run is their first execution."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsProject
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False



def _boot_qgis():
    """Reuse test_chat_widget_live's QgsApplication -- one per process, as
    test_network_units_live does. The first CI run of this module created a second
    QgsApplication of its own and the job then segfaulted at exit (after 'OK'); a second
    application object is a plausible, unproven contributor, so don't create one."""
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestAddPointLayerConvertsInCode(unittest.TestCase):
    """F04: EPSG:3857 (4902068, 1799912) is lon 44.036026, lat 15.958454 -- not the ~1.3 km-off
    value the model produced by hand."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_projected_point_lands_on_the_qgis_transform(self):
        from cartogen_ai.core.agent.tools.humanitarian_tools import add_point_layer
        res = add_point_layer("Origin", [{"name": "Sanaa", "x": 4902068.0, "y": 1799912.0}], crs="EPSG:3857",
                              crs_stated_by_user=True)      # #119: an unstated CRS that is not the project's is asked about
        self.assertNotIn("error", res, res)
        layer = QgsProject.instance().mapLayersByName("Origin")[0]
        geom = next(layer.getFeatures()).geometry().asPoint()
        self.assertAlmostEqual(geom.x(), 44.036026, places=4)
        self.assertAlmostEqual(geom.y(), 15.958454, places=4)

    def test_projected_numbers_without_a_crs_are_refused(self):
        from cartogen_ai.core.agent.tools.humanitarian_tools import add_point_layer
        res = add_point_layer("Bad", [{"name": "x", "lon": 4902068.0, "lat": 1799912.0}])
        layers = QgsProject.instance().mapLayersByName("Bad")
        feature_count = layers[0].featureCount() if layers else 0
        self.assertEqual(feature_count, 0, res)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestLayerTreeHasOneNodePerLayer(unittest.TestCase):
    """F07: 10 tree nodes for 7 layers. insert_layer_semantically added a second node for a layer
    the tool had already added with addMapLayer(), and a re-run left an orphan node."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _counts(self):
        root = QgsProject.instance().layerTreeRoot()
        nodes = root.findLayers()
        orphans = [n for n in nodes if n.layer() is None]
        return len(nodes), len(QgsProject.instance().mapLayers()), len(orphans)

    def _memory_layer(self, name):
        from qgis.core import QgsVectorLayer
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", name, "memory")
        self.assertTrue(layer.isValid())
        return layer

    def test_semantic_insertion_reuses_the_existing_node(self):
        from cartogen_ai.core.agent.map_intelligence import MapOutputDescriptor, insert_layer_semantically
        layer = self._memory_layer("lines")
        QgsProject.instance().addMapLayer(layer)
        insert_layer_semantically(layer, MapOutputDescriptor(layer_id=layer.id(), output_role="route_line"))
        self.assertEqual(self._counts(), (1, 1, 0))

    def test_rerun_with_replace_named_layer_leaves_no_orphan(self):
        from cartogen_ai.core.agent.map_intelligence import MapOutputDescriptor, insert_layer_semantically
        from cartogen_ai.core.agent.tools.logistics_tools import _replace_named_layer
        for _ in range(2):   # the second pass is the "re-run the same analysis" case
            layer = self._memory_layer("x")
            _replace_named_layer("service_area_lines_0", layer)
            insert_layer_semantically(layer, MapOutputDescriptor(layer_id=layer.id(), output_role="route_line"))
        self.assertEqual(self._counts(), (1, 1, 0))


if __name__ == "__main__":
    unittest.main()
