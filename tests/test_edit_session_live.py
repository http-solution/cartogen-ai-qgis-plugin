# -*- coding: utf-8 -*-
"""Live-QGIS tests for owned, checked attribute edits and SI measurements (audit F05, F07, F08 -> GitHub #141, #143, #144).
Written without a QGIS install: CI's first run is their first execution."""
import unittest

try:
    from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _layer(kind, wkts, name, crs="EPSG:4326"):
    layer = QgsVectorLayer(f"{kind}?crs={crs}&field=name:string&field=keep:integer", name, "memory")
    feats = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([f"f{i}", 1])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestOwnedCheckedFieldWrites(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _calc(self, layer, field, expression):
        from cartogen_ai.core.agent.tools.vector_tools import field_calculator
        QgsProject.instance().addMapLayer(layer)
        return field_calculator(layer.name(), field, expression, confirmed=True)

    def test_a_valid_expression_writes_and_saves(self):
        layer = _layer("Point", ["POINT(0 0)", "POINT(1 1)"], "pts")
        res = self._calc(layer, "doubled", '"keep" * 2')
        self.assertTrue(res.get("success"), res)
        self.assertFalse(layer.isEditable())
        self.assertEqual(sorted(f["doubled"] for f in layer.getFeatures()), [2.0, 2.0])

    def test_a_malformed_or_unknown_function_expression_changes_nothing(self):
        layer = _layer("Point", ["POINT(0 0)"], "pts")
        for expression in ("1 +", "missing_fn(1)"):
            res = self._calc(layer, "bad", expression)
            self.assertIn("error", res, expression)
            self.assertEqual(layer.fields().indexOf("bad"), -1, expression)
            self.assertFalse(layer.isEditable())

    def test_a_read_only_layer_is_an_error_and_gets_no_field(self):
        layer = _layer("Point", ["POINT(0 0)"], "pts")
        layer.setReadOnly(True)
        res = self._calc(layer, "x", "1")
        self.assertIn("error", res)
        self.assertEqual(layer.fields().indexOf("x"), -1)

    def test_a_layer_the_user_is_editing_keeps_its_session_and_its_unrelated_edit(self):
        layer = _layer("Point", ["POINT(0 0)", "POINT(1 1)"], "pts")
        QgsProject.instance().addMapLayer(layer)
        self.assertTrue(layer.startEditing())
        first = next(iter(layer.getFeatures()))
        layer.changeAttributeValue(first.id(), layer.fields().indexOf("keep"), 99)    # the user's pending edit
        from cartogen_ai.core.agent.tools.vector_tools import field_calculator
        res = field_calculator("pts", "extra", "1", confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertIn("NOT saved", res["note"])
        self.assertTrue(layer.isEditable())                       # not committed, not rolled back, still the user's session
        self.assertTrue(layer.isModified())
        # the provider still has the OLD value: nothing was committed on the user's behalf
        provider_values = {f["name"]: f["keep"] for f in layer.dataProvider().getFeatures()}
        self.assertEqual(provider_values["f0"], 1)
        self.assertEqual(layer.getFeature(first.id())["keep"], 99)

    def test_a_failed_write_inside_the_users_session_removes_only_this_tools_changes(self):
        layer = _layer("Point", ["POINT(0 0)"], "pts")
        QgsProject.instance().addMapLayer(layer)
        layer.startEditing()
        fid = next(iter(layer.getFeatures())).id()
        layer.changeAttributeValue(fid, layer.fields().indexOf("keep"), 7)
        from cartogen_ai.core.agent.tools.vector_tools import field_calculator
        res = field_calculator("pts", "extra", "missing_fn(1)", confirmed=True)
        self.assertIn("error", res)
        self.assertTrue(layer.isEditable())
        self.assertEqual(layer.getFeature(fid)["keep"], 7)       # the user's edit survived the failed tool call
        self.assertEqual(layer.fields().indexOf("extra"), -1)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestSiUnitsIgnoreProjectUnitSettings(unittest.TestCase):
    """GitHub #141: area_sqm / length_m must be metres whatever the project's measurement units are."""

    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_area_in_square_metres_with_the_project_set_to_square_kilometres(self):
        from cartogen_ai.core.agent.tools.vector_tools import calculate_area
        project = QgsProject.instance()
        project.setAreaUnits(Qgis.AreaUnit.SquareKilometers)
        layer = _layer("Polygon", ["POLYGON((0 0, 0.01 0, 0.01 0.01, 0 0.01, 0 0))"], "sq")
        project.addMapLayer(layer)
        res = calculate_area("sq", confirmed=True)
        self.assertTrue(res.get("success"), res)
        value = next(layer.getFeatures())["area_sqm"]
        self.assertAlmostEqual(value / 1230907.0, 1.0, delta=0.03)      # ~1,230,907 m2; 1.23 would be the km2 bug

    def test_length_in_metres_with_the_project_set_to_kilometres(self):
        from cartogen_ai.core.agent.tools.vector_tools import calculate_length
        project = QgsProject.instance()
        project.setDistanceUnits(Qgis.DistanceUnit.Kilometers)
        layer = _layer("LineString", ["LINESTRING(0 0, 0.01 0)"], "ln")
        project.addMapLayer(layer)
        res = calculate_length("ln", confirmed=True)
        self.assertTrue(res.get("success"), res)
        value = next(layer.getFeatures())["length_m"]
        self.assertAlmostEqual(value / 1113.2, 1.0, delta=0.03)


if __name__ == "__main__":
    unittest.main()
