# -*- coding: utf-8 -*-
"""Live-QGIS tests for H2 generate_mapping_task_grid. Written without a QGIS install: CI's first run is their first execution."""
import json
import os
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


def _aoi():
    # about 4.3 km x 2.2 km near Sanaa (0.04 x 0.02 degrees)
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string", "aoi", "memory")
    f = QgsFeature(layer.fields())
    f.setGeometry(QgsGeometry.fromWkt("POLYGON((44.20 15.30, 44.24 15.30, 44.24 15.32, 44.20 15.32, 44.20 15.30))"))
    layer.dataProvider().addFeatures([f])
    layer.updateExtents()
    return layer


def _points(wkts):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=n:integer", "damage", "memory")
    feats = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([i])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestGenerateMappingTaskGrid(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        QgsProject.instance().addMapLayer(_aoi())

    def test_builds_a_grid_that_covers_the_area_once(self):
        from cartogen_ai.core.agent.tools.task_grid_tools import generate_mapping_task_grid
        res = generate_mapping_task_grid("aoi", cell_size_m=1000)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["metric_crs"], "EPSG:32638")
        # about 4.3 x 2.2 km -> 5 x 3 = 15 cells at most, a few fewer if edge slivers are dropped
        self.assertTrue(10 <= res["task_count"] <= 15, res)
        layer = QgsProject.instance().mapLayersByName("mapping_tasks")[0]
        total_km2 = sum(f["area_km2"] for f in layer.getFeatures())
        self.assertAlmostEqual(total_km2, 4.3 * 2.2, delta=1.2)
        ids = [f["task_id"] for f in layer.getFeatures()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_points_rank_the_cells_and_geojson_is_written(self):
        from cartogen_ai.core.agent.tools.task_grid_tools import generate_mapping_task_grid
        QgsProject.instance().addMapLayer(_points(["POINT(44.201 15.301)"] * 5 + ["POINT(44.239 15.319)"]))
        path = os.path.join(tempfile.mkdtemp(prefix="cartogen_grid_"), "tasks.geojson")
        res = generate_mapping_task_grid("aoi", cell_size_m=1000, priority_points_layer="damage", export_geojson_path=path)
        self.assertTrue(res.get("success"), res)
        layer = QgsProject.instance().mapLayersByName("mapping_tasks")[0]
        by_value = sorted(layer.getFeatures(), key=lambda f: -(f["value"] or 0))
        self.assertEqual(by_value[0]["value"], 5.0)
        self.assertEqual(by_value[0]["priority"], "High")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(len(data["features"]), res["task_count"])
        self.assertIn("task_id", data["features"][0]["properties"])

    def test_bad_inputs_are_errors(self):
        from cartogen_ai.core.agent.tools.task_grid_tools import generate_mapping_task_grid
        self.assertIn("error", generate_mapping_task_grid("ghost"))
        self.assertIn("error", generate_mapping_task_grid("aoi", cell_size_m=50))
        QgsProject.instance().addMapLayer(_points(["POINT(44.2 15.3)"]))
        self.assertIn("error", generate_mapping_task_grid("damage"))       # not a polygon layer


if __name__ == "__main__":
    unittest.main()
