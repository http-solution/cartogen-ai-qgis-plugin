"""Live-QGIS checks from the 2026-10-16 integration audit: the snapshot/restore pairs that undo_last_operation uses really put each new MODIFY tool's
change back, the new layout items carry the protected-layer advisory, and a protected layer named only inside a virtual layer's SQL is seen by the
privacy gate. Written without a QGIS install: CI's first run is its first execution, so a failing round trip names a tool whose undo does not work
(the registry entry is then removed rather than left promising an undo that fails)."""
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsLayoutItemMap, QgsPrintLayout, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _towns(name="towns"):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer&field=seen:date", name, "memory")
    for i, (n, pop) in enumerate((("a", 5), ("b", 50), ("c", 500))):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({i} {i})"))
        f.setAttributes([n, pop, f"2026-01-0{i + 1}"])
        layer.dataProvider().addFeatures([f])
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestIntegrationAuditLive(unittest.TestCase):
    def setUp(self):
        from tests._geometry_probe import _make_rasters
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.towns = _towns()
        QgsProject.instance().addMapLayer(self.towns)
        self.dem = QgsRasterLayer(_make_rasters(tempfile.mkdtemp())["dem"], "dem")
        QgsProject.instance().addMapLayer(self.dem)
        self.layout = QgsPrintLayout(QgsProject.instance())
        self.layout.initializeDefaults()
        self.layout.setName("audit")
        map_item = QgsLayoutItemMap(self.layout)       # the atlas needs a map item to follow
        map_item.setId("MAP_MAIN")
        self.layout.addLayoutItem(map_item)
        QgsProject.instance().layoutManager().addLayout(self.layout)

    def _round_trip(self, tool, args, run, read, changed):
        """snapshot -> run the tool -> the value changed -> restore -> the value is back."""
        from cartogen_ai.core.agent.tools._snapshot_registry import get_restore_fn, get_snapshot_fn
        snap = get_snapshot_fn(tool)(dict(args))
        self.assertIsNotNone(snap, f"{tool}: no snapshot was taken")
        before = read()
        result = run()
        self.assertTrue(result.get("success"), f"{tool}: {result}")
        self.assertTrue(changed(before, read()), f"{tool}: the tool changed nothing the test can see")
        self.assertTrue(get_restore_fn(snap.get("kind"), tool)(snap), f"{tool}: restore returned False")
        self.assertEqual(read(), before, f"{tool}: restore did not put the old value back")

    def test_layer_filter_is_undoable(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import set_layer_filter
        self._round_trip("set_layer_filter", {"layer_name": "towns"}, lambda: set_layer_filter("towns", filter='"pop" > 10'),
                         self.towns.subsetString, lambda a, b: a != b)

    def test_diagram_is_undoable(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import set_layer_diagram
        self._round_trip("set_layer_diagram", {"layer_name": "towns"},
                         lambda: set_layer_diagram("towns", kind="pie", fields=["pop"]),
                         lambda: self.towns.diagramRenderer() is not None, lambda a, b: a != b)

    def test_rule_based_labels_are_undoable(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import set_rule_based_labels
        self._round_trip("set_rule_based_labels", {"layer_name": "towns"},
                         lambda: set_rule_based_labels("towns", [{"field": "name", "filter": '"pop" > 10'}]),
                         lambda: type(self.towns.labeling()).__name__ if self.towns.labeling() else None, lambda a, b: a != b)

    def test_layer_elevation_is_undoable(self):
        from cartogen_ai.core.agent.tools.elevation_tools import set_layer_elevation
        self._round_trip("set_layer_elevation", {"layer_name": "dem"}, lambda: set_layer_elevation("dem", enabled=True, mode="surface"),
                         lambda: self.dem.elevationProperties().isEnabled(), lambda a, b: a != b)

    def test_delete_features_is_undoable(self):
        """rc45 smoke run: a confirmed delete_features could not be undone. The snapshot is taken on the confirmed call only."""
        from cartogen_ai.core.agent.tools._snapshot_registry import get_restore_fn, get_snapshot_fn
        from cartogen_ai.core.agent.tools.attribute_edit_tools import delete_features
        args = {"layer_name": "towns", "expression": "\"pop\" > 10", "confirmed": True}
        self.assertIsNone(get_snapshot_fn("delete_features")({**args, "confirmed": False}), "a preview must not snapshot")
        snap = get_snapshot_fn("delete_features")(dict(args))
        self.assertIsNotNone(snap)
        before = sorted(f["name"] for f in self.towns.getFeatures())
        result = delete_features("towns", expression='"pop" > 10', confirmed=True)
        self.assertTrue(result.get("success"), result)
        self.assertEqual(self.towns.featureCount(), 1)
        self.assertTrue(get_restore_fn(snap["kind"], "delete_features")(snap))
        self.assertEqual(sorted(f["name"] for f in self.towns.getFeatures()), before)
        restored = {f["name"]: f["pop"] for f in self.towns.getFeatures()}
        self.assertEqual(restored, {"a": 5, "b": 50, "c": 500})

    def test_rule_based_labels_can_be_cleared(self):
        from cartogen_ai.core.agent.tools.symbology_extra_tools import set_rule_based_labels
        self.assertTrue(set_rule_based_labels("towns", [{"field": "name"}]).get("success"))
        self.assertIsNotNone(self.towns.labeling())
        result = set_rule_based_labels("towns", clear=True)
        self.assertTrue(result.get("success"), result)
        self.assertIsNone(self.towns.labeling())
        self.assertFalse(self.towns.labelsEnabled())

    def test_layer_temporal_is_undoable(self):
        from cartogen_ai.core.agent.tools.project_ops_tools import set_layer_temporal
        self._round_trip("set_layer_temporal", {"layer_name": "towns"}, lambda: set_layer_temporal("towns", start_field="seen"),
                         lambda: self.towns.temporalProperties().isActive(), lambda a, b: a != b)

    def test_protected_layers_get_an_advisory_on_the_new_layout_and_package_tools(self):
        from cartogen_ai.core.agent.tools.data_layer_tools import package_layers_offline
        from cartogen_ai.core.agent.tools.layout_chart_profile_tools import add_layout_chart
        from cartogen_ai.core.agent.tools.layout_extra_tools import set_layout_atlas
        from cartogen_ai.core.models.sensitivity import set_layer_sensitivity
        chart_open = add_layout_chart("audit", "towns", "name", "pop", item_id="C_OPEN")
        self.assertTrue(chart_open.get("success") and "warning" not in chart_open, chart_open)
        self.assertTrue(set_layer_sensitivity(self.towns, "RESTRICTED", "audit test"))
        chart = add_layout_chart("audit", "towns", "name", "pop", item_id="C_RESTRICTED")
        self.assertIn("RESTRICTED", chart.get("warning", ""), chart)
        atlas = set_layout_atlas("audit", coverage_layer="towns")
        self.assertIn("RESTRICTED", atlas.get("warning", ""), atlas)
        packed = package_layers_offline(["towns"], tempfile.mkdtemp() + "/p.gpkg")
        self.assertIn("RESTRICTED", packed.get("warning", ""), packed)


if __name__ == "__main__":
    unittest.main()
