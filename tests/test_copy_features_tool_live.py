"""PLAN-023 R9-4 on real QGIS layers: 3 selected features of 5 arrive with the mapped fields (name -> title) and the field with no match stays empty; a type mismatch is refused;
a value that does not fit stops the copy with nothing written; a filter copies only matches; a different CRS is transformed; a single polygon goes into a MultiPolygon layer;
one undo. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestCopyFeaturesLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _points(self, name, fields, rows, crs="EPSG:32636"):
        layer = QgsVectorLayer(f"Point?crs={crs}&{fields}", name, "memory")
        feats = []
        for x, attrs in rows:
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, 0)))
            f.setAttributes(attrs)
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _pair(self):
        source = self._points("src", "field=name:string&field=pop:integer", [(i, [f"n{i}", i * 10]) for i in range(5)])
        target = self._points("dst", "field=title:string&field=pop:integer&field=note:string", [])
        return source, target

    def _call(self, **kw):
        from cartogen_ai.core.agent.tools.copy_features_tool import copy_features_between_layers
        return copy_features_between_layers(**kw)

    def test_three_selected_features_arrive_with_the_mapped_fields_after_a_preview(self):
        source, target = self._pair()
        source.selectByExpression('"pop" >= 20')
        card = self._call(source_layer="src", target_layer="dst", field_mapping={"title": "name"})
        self.assertEqual(card["status"], "PREVIEW_REQUIRED")
        self.assertIn("name -> title", card["rationale"])
        self.assertIn("note", card["rationale"])
        self.assertEqual(target.featureCount(), 0)
        out = self._call(confirmed=True, **{k: v for k, v in card["arguments"].items() if k != "confirmed"})
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["features_copied"], 3)
        rows = sorted((f["title"], f["pop"]) for f in target.getFeatures())
        self.assertEqual(rows, [("n2", 20), ("n3", 30), ("n4", 40)])
        self.assertTrue(all(f["note"] is None or f["note"] == "" or str(f["note"]) == "NULL" for f in target.getFeatures()))
        self.assertEqual(source.featureCount(), 5)

    def test_a_filter_copies_only_the_matches(self):
        _source, target = self._pair()
        out = self._call(source_layer="src", target_layer="dst", filter_expression='"pop" < 20', field_mapping={"title": "name"}, confirmed=True)
        self.assertEqual((out["features_copied"], target.featureCount()), (2, 2))

    def test_a_geometry_type_mismatch_is_refused(self):
        self._pair()
        poly = QgsVectorLayer("Polygon?crs=EPSG:32636&field=title:string", "poly", "memory")
        QgsProject.instance().addMapLayer(poly)
        self.assertIn("different geometry types", self._call(source_layer="src", target_layer="poly")["error"])

    def test_a_value_that_does_not_fit_stops_the_copy_with_nothing_written(self):
        self._points("s2", "field=name:string", [(0, ["abc"])])
        target = self._points("d2", "field=name:integer", [])
        out = self._call(source_layer="s2", target_layer="d2", confirmed=True)
        self.assertIn("Nothing was copied", out["error"])
        self.assertEqual(target.featureCount(), 0)

    def test_a_field_that_does_not_exist_is_refused(self):
        self._pair()
        self.assertIn("no field 'zzz'", self._call(source_layer="src", target_layer="dst", field_mapping={"zzz": "name"})["error"])

    def test_a_different_crs_is_transformed(self):
        self._points("s3", "field=name:string", [(33.0, ["a"])], crs="EPSG:4326")
        target = self._points("d3", "field=name:string", [], crs="EPSG:32636")
        out = self._call(source_layer="s3", target_layer="d3", only_selected=False, confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertIn("transformed", out["crs_note"])
        point = next(target.getFeatures()).geometry().asPoint()
        self.assertGreater(abs(point.x()), 1000.0)                         # metres, not degrees

    def test_a_single_polygon_goes_into_a_multipolygon_layer(self):
        source = QgsVectorLayer("Polygon?crs=EPSG:32636&field=name:string", "ps", "memory")
        f = QgsFeature(source.fields())
        f.setGeometry(QgsGeometry.fromWkt("POLYGON((0 0,1 0,1 1,0 0))"))
        f.setAttributes(["a"])
        source.dataProvider().addFeatures([f])
        target = QgsVectorLayer("MultiPolygon?crs=EPSG:32636&field=name:string", "pm", "memory")
        QgsProject.instance().addMapLayer(source)
        QgsProject.instance().addMapLayer(target)
        out = self._call(source_layer="ps", target_layer="pm", only_selected=False, confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertTrue(next(target.getFeatures()).geometry().isMultipart())

    def test_one_undo_removes_the_copied_features_when_the_target_is_in_edit_mode(self):
        _source, target = self._pair()
        target.startEditing()
        self._call(source_layer="src", target_layer="dst", only_selected=False, field_mapping={"title": "name"}, confirmed=True)
        self.assertEqual(target.featureCount(), 5)
        target.undoStack().undo()
        self.assertEqual(target.featureCount(), 0)
        self.assertTrue(target.isEditable())


if __name__ == "__main__":
    unittest.main()
