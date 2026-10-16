"""Live-QGIS tests for package B (project_ops_tools.py). Written without a QGIS install: CI's first run is their first execution.
zoom_history needs a map canvas and is not exercised here."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _layer(uri, name, rows):
    layer = QgsVectorLayer(uri, name, "memory")
    for row in rows:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt("POINT(1 1)"))
        f.setAttributes(list(row))
        layer.dataProvider().addFeatures([f])
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestProjectOpsToolsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.districts = _layer("Point?crs=EPSG:4326&field=pcode:string&field=name:string", "districts", [("D1", "one"), ("D2", "two")])
        self.schools = _layer("Point?crs=EPSG:4326&field=sid:integer&field=dpcode:string&field=opened:date", "schools",
                              [(1, "D1", None), (2, "D1", None), (3, "D2", None)])
        QgsProject.instance().addMapLayer(self.districts)
        QgsProject.instance().addMapLayer(self.schools)

    def test_rename_layer_group(self):
        from cartogen_ai.core.agent.tools.map_view_tools import create_layer_group
        from cartogen_ai.core.agent.tools.project_ops_tools import rename_layer_group
        create_layer_group("Transport")
        create_layer_group("Other")
        res = rename_layer_group("Transport", "Roads")
        self.assertTrue(res.get("success"), res)
        root = QgsProject.instance().layerTreeRoot()
        self.assertIsNotNone(root.findGroup("Roads"))
        self.assertIsNone(root.findGroup("Transport"))
        self.assertIn("already exists", rename_layer_group("Roads", "Other")["error"])
        self.assertIn("not found", rename_layer_group("Nope", "X")["error"])

    def test_layer_metadata_round_trip(self):
        from cartogen_ai.core.agent.tools.project_ops_tools import get_layer_metadata, set_layer_metadata
        res = set_layer_metadata("districts", title="Districts", abstract="Admin level 2", license="CC-BY-4.0",
                                 keywords=["admin", "yemen"], contact_name="Ali", contact_email="ali@example.org")
        self.assertTrue(res.get("success"), res)
        got = get_layer_metadata("districts")
        self.assertEqual((got["title"], got["abstract"], got["licenses"]), ("Districts", "Admin level 2", ["CC-BY-4.0"]))
        self.assertEqual(got["keywords"], {"keywords": ["admin", "yemen"]})
        self.assertEqual(got["contacts"][0]["name"], "Ali")
        set_layer_metadata("districts", title="Districts v2")
        self.assertEqual(get_layer_metadata("districts")["abstract"], "Admin level 2")   # left-out fields are kept
        self.assertIn("error", set_layer_metadata("districts"))
        self.assertIn("error", set_layer_metadata("nope", title="x"))

    def test_snapping_options(self):
        from cartogen_ai.core.agent.tools.project_ops_tools import set_snapping_options
        res = set_snapping_options(enabled=True, snap_type="vertex", tolerance=15, units="pixels", mode="all layers", topological_editing=True)
        self.assertTrue(res.get("success"), res)
        config = QgsProject.instance().snappingConfig()
        self.assertTrue(config.enabled())
        self.assertEqual(config.tolerance(), 15)
        self.assertTrue(QgsProject.instance().topologicalEditing())
        self.assertIn("error", set_snapping_options(snap_type="teleport"))
        self.assertIn("error", set_snapping_options())

    def test_relations(self):
        from cartogen_ai.core.agent.tools.project_ops_tools import create_relation, list_relations
        res = create_relation("district schools", "districts", "pcode", "schools", "dpcode")
        self.assertTrue(res.get("success"), res)
        rows = list_relations()["relations"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["parent_layer"], rows[0]["child_layer"], rows[0]["valid"]), ("districts", "schools", True))
        self.assertIn("already exists", create_relation("district schools", "districts", "pcode", "schools", "dpcode")["error"])
        self.assertIn("no field", create_relation("r2", "districts", "nope", "schools", "dpcode")["error"])
        self.assertIn("error", create_relation("r3", "nope", "pcode", "schools", "dpcode"))

    def test_layer_temporal(self):
        from cartogen_ai.core.agent.tools.project_ops_tools import set_layer_temporal
        res = set_layer_temporal("schools", start_field="opened")
        self.assertTrue(res.get("success"), res)
        self.assertTrue(self.schools.temporalProperties().isActive())
        self.assertEqual(self.schools.temporalProperties().startField(), "opened")
        self.assertIn("not a date", set_layer_temporal("schools", start_field="dpcode")["error"])
        self.assertIn("error", set_layer_temporal("schools", start_field="nope"))
        self.assertTrue(set_layer_temporal("schools", clear=True)["success"])
        self.assertFalse(self.schools.temporalProperties().isActive())

    def test_project_time_range(self):
        from cartogen_ai.core.agent.tools.project_ops_tools import set_project_time_range
        res = set_project_time_range("2026-03-01", "2026-03-31T12:00:00")
        self.assertTrue(res.get("success"), res)
        span = QgsProject.instance().timeSettings().temporalRange()
        self.assertEqual(span.begin().date().month(), 3)
        self.assertEqual(span.end().date().day(), 31)
        self.assertIn("error", set_project_time_range("2026-03-31", "2026-03-01"))

    def test_annotations(self):
        from cartogen_ai.core.agent.tools.project_ops_tools import add_text_annotation, remove_annotations
        self.assertIn("error", remove_annotations())   # nothing yet
        res = add_text_annotation("Camp A", 44.1, 15.3)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["annotations"], 1)
        self.assertEqual(len(QgsProject.instance().mainAnnotationLayer().items()), 1)
        self.assertIn("error", add_text_annotation("", 1, 1))
        self.assertEqual(remove_annotations()["status"], "PREVIEW_REQUIRED")
        self.assertEqual(remove_annotations(confirmed=True)["removed"], 1)
        self.assertEqual(len(QgsProject.instance().mainAnnotationLayer().items()), 0)


if __name__ == "__main__":
    unittest.main()
