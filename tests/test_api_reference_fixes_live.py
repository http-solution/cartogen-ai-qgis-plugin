"""Live-QGIS checks for the calls the 2026-10-16 API-reference review corrected: they ran against mocks (or inside contextlib.suppress) before,
so nothing had ever shown that they fail on real QGIS objects. Written without a QGIS install: CI's first run is their first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestApiReferenceFixesLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_diagnose_topology_counts_a_real_invalid_polygon(self):
        from cartogen_ai.core.agent.tools.vector_tools import diagnose_topology
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string", "shapes", "memory")
        for name, wkt in (("ok", "POLYGON((0 0,2 0,2 2,0 2,0 0))"), ("bowtie", "POLYGON((3 0,5 2,5 0,3 2,3 0))")):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([name])
            layer.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(layer)
        res = diagnose_topology("shapes")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["total_features"], 2)
        self.assertEqual(res["invalid_geometries"], 1, res)

    def test_point_displacement_representation_applies(self):
        from cartogen_ai.core.representation.applier import apply_representation
        from cartogen_ai.core.representation.models import RepresentationCandidate
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "pts", "memory")
        for i in range(3):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt("POINT(1 1)"))
            f.setAttributes([f"p{i}"])
            layer.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(layer)
        res = apply_representation(layer, RepresentationCandidate(id="point_displacement", label="Displace", renderer_type="displacement"))
        self.assertTrue(res.get("success"), res)
        self.assertEqual(layer.renderer().type(), "pointDisplacement")

    def test_proxy_detection_runs_against_the_real_network_manager(self):
        from cartogen_ai.core.proxy import get_qgis_proxy_dict
        res = get_qgis_proxy_dict()
        self.assertTrue(res is None or set(res) == {"http", "https"}, res)


if __name__ == "__main__":
    unittest.main()
