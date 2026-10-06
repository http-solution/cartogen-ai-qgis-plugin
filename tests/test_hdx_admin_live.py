# -*- coding: utf-8 -*-
"""Live-QGIS test for the downloaded admin-boundary layer (GitHub #127): one layer after a re-download, name labels on, a pale
fill instead of the opaque default, and polygons drawn below points and lines. Written without a QGIS install: CI's first run is
its first execution; a failure is a finding about the code unless it shows a wrong expectation."""
import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _write_admin_geojson():
    def square(x, y):
        return [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]]
    collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"ADM1_EN": f"Governorate {i}", "ADM1_PCODE": f"YE{i:02d}"},
         "geometry": {"type": "Polygon", "coordinates": square(44 + i, 15)}} for i in range(3)]}
    path = os.path.join(tempfile.mkdtemp(prefix="cartogen_hdx_"), "yem_adm1.geojson")
    with open(path, "w") as handle:
        json.dump(collection, handle)
    return path


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestDownloadedAdminBoundaries(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.fetch = {"iso3": "YEM", "admin_level": "ADM1", "local_path": _write_admin_geojson(),
                      "dataset_title": "test", "source_url": "https://example.invalid", "pcode_field": "ADM1_PCODE"}

    def _add(self):
        from cartogen_ai.core.agent.tools.humanitarian_tools import add_hdx_admin_boundaries_layer_main_thread_phase
        return add_hdx_admin_boundaries_layer_main_thread_phase(dict(self.fetch))

    def test_a_second_download_replaces_the_first_instead_of_stacking(self):
        self.assertTrue(self._add().get("success"))
        self.assertTrue(self._add().get("success"))
        self.assertEqual(len(QgsProject.instance().mapLayersByName("YEM_ADM1_boundary_hdx")), 1)

    def test_the_layer_is_labelled_and_not_an_opaque_default_fill(self):
        self.assertTrue(self._add().get("success"))
        layer = QgsProject.instance().mapLayersByName("YEM_ADM1_boundary_hdx")[0]
        self.assertIsNotNone(layer.labeling(), "name labels were not switched on")
        self.assertTrue(layer.labelsEnabled())
        symbol = layer.renderer().symbol()
        self.assertLess(symbol.color().alpha(), 255, "the fill must be pale/translucent, not the opaque default colour")
        self.assertLess(symbol.color().alpha(), 150)

    def test_polygons_sit_below_points_and_lines(self):
        points = QgsVectorLayer("Point?crs=EPSG:4326", "Clinics", "memory")
        feature = QgsFeature(points.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POINT(44.5 15.5)"))
        points.dataProvider().addFeatures([feature])
        QgsProject.instance().addMapLayer(points)
        self.assertTrue(self._add().get("success"))
        order = [node.layer().name() for node in QgsProject.instance().layerTreeRoot().findLayers()]
        self.assertLess(order.index("Clinics"), order.index("YEM_ADM1_boundary_hdx"),
                        f"the admin polygons must be drawn below the points, got {order}")


if __name__ == "__main__":
    unittest.main()
