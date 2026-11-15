"""PLAN-058 (DEF-24, issue 362): _resolve_animation_fields against a REAL QgsVectorLayer, so the temporalProperties() calls it relies on (isActive, startField,
endField) are checked against the actual QGIS API, not a mock. CI live job only; written without a QGIS install, so CI's first run is its first execution."""
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestResolveAnimationFieldsOnARealLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.layer = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer&field=when:date", "events", "memory")
        feature = QgsFeature(self.layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POINT(44 15)"))
        self.layer.dataProvider().addFeatures([feature])
        QgsProject.instance().addMapLayer(self.layer)
        from cartogen_ai.core.agent.tools import export_tools, project_ops_tools
        self.resolve, self.set_temporal = export_tools._resolve_animation_fields, project_ops_tools.set_layer_temporal

    def test_a_layer_made_temporal_by_the_plugin_gives_its_start_field_back(self):
        self.assertTrue(self.set_temporal("events", start_field="when").get("success"))
        self.assertEqual(self.resolve(self.layer, None, None), ("when", None, None))

    def test_a_start_and_end_pair_comes_back_whole(self):
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=a:date&field=b:date", "spans", "memory")
        QgsProject.instance().addMapLayer(layer)
        self.assertTrue(self.set_temporal("spans", start_field="a", end_field="b").get("success"))
        self.assertEqual(self.resolve(layer, None, None), ("a", "b", None))

    def test_a_layer_that_is_not_temporal_names_its_date_field(self):
        start, _end, error = self.resolve(self.layer, None, None)
        self.assertIsNone(start)
        self.assertIn("'when'", error)
        self.assertNotIn("'id'", error)


if __name__ == "__main__":
    unittest.main()
