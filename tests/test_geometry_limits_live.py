"""rc48 B3: qgis:linestopolygons run on a layer that already holds polygons died with a raw TypeError and the model then made 28 more calls. The tool
now refuses a layer whose geometry type the parameter does not accept, before running anything. Written without a QGIS install: CI's first run is its
first execution."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cartogen_ai.core.agent.tools import processing_allowlist_tools as tools

try:
    from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


class _Layer:
    def __init__(self, kind, name="districts"):
        self._kind, self._name = kind, name

    def geometryType(self):
        return self._kind

    def name(self):
        return self._name


class TestGeometryViolation(unittest.TestCase):
    def setUp(self):
        stub = SimpleNamespace(geometryDisplayString=lambda kind: kind)
        patcher = patch.object(tools, "QgsWkbTypes", stub, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_polygon_layer_where_lines_are_needed_is_refused_with_the_name_and_the_remedy(self):
        text = tools.geometry_violation("qgis:linestopolygons", {"INPUT": _Layer("Polygon")}, {"INPUT": {"Line"}})
        self.assertIn("needs a line layer", text)
        self.assertIn("'districts' is a polygon layer", text)
        self.assertIn("Nothing was run", text)

    def test_a_layer_of_an_accepted_type_and_an_unresolved_name_pass(self):
        self.assertIsNone(tools.geometry_violation("x", {"INPUT": _Layer("Line")}, {"INPUT": {"Line"}}))
        self.assertIsNone(tools.geometry_violation("x", {"INPUT": "districts"}, {"INPUT": {"Line"}}))
        self.assertIsNone(tools.geometry_violation("x", {"INPUT": _Layer("Polygon")}, {}))

    def test_a_parameter_that_takes_polygons_or_lines_accepts_both(self):
        for kind in ("Polygon", "Line"):
            self.assertIsNone(tools.geometry_violation("x", {"INPUT": _Layer(kind)}, {"INPUT": {"Line", "Polygon"}}))


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestGeometryLimitsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        if QgsApplication.processingRegistry().algorithmById("qgis:linestopolygons") is None:
            self.skipTest("qgis:linestopolygons is not available in this QGIS")
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _layer(self, geometry, wkt, name):
        layer = QgsVectorLayer(f"{geometry}?crs=EPSG:4326&field=name:string", name, "memory")
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        feature.setAttributes(["a"])
        layer.dataProvider().addFeatures([feature])
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_the_limits_are_read_from_the_algorithm(self):
        for p in QgsApplication.processingRegistry().createAlgorithmById("qgis:linestopolygons").parameterDefinitions():   # rc48 B3: diagnosis for CI
            print("GEOMLIMIT", p.name(), repr(p.type()), [repr(t) for t in getattr(p, "dataTypes", list)()])
        self.assertEqual(tools._geometry_limits("qgis:linestopolygons"), {"INPUT": {"Line"}})
        self.assertEqual(tools._geometry_limits("native:buffer"), {})

    def test_linestopolygons_on_a_polygon_layer_is_refused_before_it_runs(self):
        self._layer("Polygon", "POLYGON((0 0,1 0,1 1,0 1,0 0))", "districts")
        result = tools.run_allowlisted_processing_algorithm("qgis:linestopolygons", {"INPUT": "districts"}, new_layer_name="poly_out")
        self.assertIn("needs a line layer", result.get("error", ""), result)
        self.assertEqual(QgsProject.instance().mapLayersByName("poly_out"), [])

    def test_linestopolygons_on_a_closed_line_layer_still_runs(self):
        self._layer("LineString", "LINESTRING(0 0,1 0,1 1,0 1,0 0)", "borders")
        result = tools.run_allowlisted_processing_algorithm("qgis:linestopolygons", {"INPUT": "borders"}, new_layer_name="poly_out")
        self.assertTrue(result.get("success"), result)


if __name__ == "__main__":
    unittest.main()
