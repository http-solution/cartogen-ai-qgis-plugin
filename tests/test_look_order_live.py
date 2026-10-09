# -*- coding: utf-8 -*-
"""apply_humanitarian_look(damage_class) on a point layer drawn BELOW a polygon layer lifts the points above it (issue 232, row T3)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestLookOrderLive(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_points_are_lifted_above_a_covering_polygon_layer(self):
        import cartogen_ai.core.agent.tools  # noqa: F401
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        pts = QgsVectorLayer("Point?crs=EPSG:4326&field=Main_Damage_Site_Class:string", "unosat_pts", "memory")
        feats = []
        for i, cls in enumerate(["Destroyed", "Severe Damage", "Moderate Damage", "Possible Damage"]):
            f = QgsFeature(pts.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"Point({44 + i * 0.01} 15)"))
            f.setAttributes([cls])
            feats.append(f)
        pts.dataProvider().addFeatures(feats)
        adm = QgsVectorLayer("Polygon?crs=EPSG:4326&field=n:string", "admin", "memory")
        g = QgsFeature(adm.fields())
        g.setGeometry(QgsGeometry.fromWkt("Polygon((43.9 14.9,44.2 14.9,44.2 15.1,43.9 15.1,43.9 14.9))"))
        adm.dataProvider().addFeatures([g])
        project = QgsProject.instance()
        project.addMapLayer(pts)          # added first, so it ends up below the polygon layer
        project.addMapLayer(adm)
        order = [c.name() for c in project.layerTreeRoot().children()]
        self.assertLess(order.index("admin"), order.index("unosat_pts"), order)
        result = TOOL_REGISTRY["apply_humanitarian_look"](layer_name="unosat_pts", look="damage_class", field="Main_Damage_Site_Class")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result.get("moved_above_polygons"), ["admin"])
        order = [c.name() for c in project.layerTreeRoot().children()]
        self.assertLess(order.index("unosat_pts"), order.index("admin"), order)
        renderer = project.mapLayersByName("unosat_pts")[0].renderer()
        self.assertNotEqual(renderer.type(), "singleSymbol")        # the damage-class look is a rule renderer, not the default symbol
        self.assertGreaterEqual(len(renderer.rootRule().children()), 4)


if __name__ == "__main__":
    unittest.main()
