# -*- coding: utf-8 -*-
"""H9 critical links on a real road layer. Written without a local QGIS: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _points(rows):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=w:double", "pts", "memory")
    feats = []
    for x, y, w in rows:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} {y})"))
        f.setAttributes([w])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestCriticalLinks(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        # A chain of three segments, 0.01 degree each: A(0) - B(.01) - C(.02) - D(.03)
        roads = QgsVectorLayer("LineString?crs=EPSG:4326&field=speed:double", "roads", "memory")
        feats = []
        for i in range(3):
            f = QgsFeature(roads.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"LINESTRING({i * 0.01} 15, {(i + 1) * 0.01} 15)"))
            f.setAttributes([40.0])
            feats.append(f)
        roads.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(roads)
        self.roads = roads
        for name, rows in (("hub", [(0.0, 15.0, 1.0)]), ("sites", [(0.03, 15.0, 1.0), (0.02, 15.0, 2.0)])):
            layer = _points(rows)
            layer.setName(name)
            QgsProject.instance().addMapLayer(layer)

    def _run(self, **kw):
        from cartogen_ai.core.agent.tools.critical_link_tools import analyze_critical_links
        return analyze_critical_links("roads", "hub", kw.pop("destinations_layer", "sites"), **kw)

    def _loads(self):
        layer = QgsProject.instance().mapLayersByName("critical_links")[0]
        return sorted(round(f["load"], 6) for f in layer.getFeatures())

    def test_loads_follow_the_demand_below_each_segment(self):
        out = self._run(destination_weight_field="w")
        self.assertTrue(out["success"], out)
        self.assertEqual(self._loads(), [1.0, 3.0, 3.0])
        self.assertEqual(out["weight_unreachable"], 0.0)
        self.assertEqual(out["heaviest_segments"][0]["load"], 3.0)
        self.assertEqual(out["load_unit"], "weighted OD pairs")
        self.assertFalse(out.get("partial"))

    def test_without_weights_it_counts_pairs(self):
        out = self._run()
        self.assertTrue(out["success"], out)
        self.assertEqual(self._loads(), [1.0, 2.0, 2.0])
        self.assertEqual(out["load_unit"], "OD pairs")

    def test_a_closed_segment_is_removed_and_the_cut_off_demand_is_reported(self):
        idx = self.roads.fields().indexOf("speed")
        fid = sorted(f.id() for f in self.roads.getFeatures())[1]
        self.roads.startEditing()
        self.roads.changeAttributeValue(fid, idx, -1.0)
        self.roads.commitChanges()
        out = self._run(speed_field="speed", destination_weight_field="w")
        self.assertTrue(out["success"], out)
        self.assertEqual(out["closed_segments_removed"], 1)
        self.assertEqual(out["weight_unreachable"], 3.0)

    def test_far_destinations_are_left_out_and_counted(self):
        far = _points([(5.0, 40.0, 1.0), (0.03, 15.0, 1.0)])
        far.setName("far")
        QgsProject.instance().addMapLayer(far)
        out = self._run(destinations_layer="far")
        self.assertTrue(out["success"], out)
        self.assertEqual(out["destinations_too_far_from_road"], 1)
        self.assertEqual(out["destinations_used"], 1)

    def test_bad_inputs(self):
        self.assertIn("error", self._run(strategy="quickest"))
        self.assertIn("error", self._run(destination_weight_field="nope"))
        self.assertIn("error", self._run(max_snap_m=0))


if __name__ == "__main__":
    unittest.main()
