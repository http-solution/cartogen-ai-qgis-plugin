# -*- coding: utf-8 -*-
"""gather_facts against real QGIS layers: geometry type, numeric fields, feature count, WGS84 extent and the derived UTM zone."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestGatherFactsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_facts_describe_the_project(self):
        from cartogen_ai.core.agent import discovery
        pts = QgsVectorLayer("Point?crs=EPSG:32638&field=n:integer&field=label:string", "utm_pts", "memory")
        f = QgsFeature(pts.fields())
        f.setGeometry(QgsGeometry.fromWkt("Point(500000 1700000)"))
        f.setAttributes([1, "a"])
        pts.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(pts)
        line = QgsVectorLayer("LineString?crs=EPSG:4326", "roads", "memory")
        g = QgsFeature(line.fields())
        g.setGeometry(QgsGeometry.fromWkt("LineString(44.4 15.4,44.6 15.6)"))
        line.dataProvider().addFeatures([g])
        QgsProject.instance().addMapLayer(line)
        facts = discovery.gather_facts()
        self.assertEqual((facts["utm_pts"]["geometry"], facts["utm_pts"]["features"], facts["utm_pts"]["geographic"]), ("point", 1, False))
        self.assertEqual(dict(facts["utm_pts"]["fields"]), {"n": True, "label": False})
        self.assertEqual((facts["roads"]["geometry"], facts["roads"]["geographic"]), ("line", True))
        self.assertEqual(discovery.utm_for_fact(facts["roads"]), "EPSG:32638")
        self.assertAlmostEqual(facts["utm_pts"]["extent_wgs84"][0], 45.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
