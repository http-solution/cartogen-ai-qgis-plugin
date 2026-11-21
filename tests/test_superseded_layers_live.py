"""PLAN-072 / HU-5 part 3: mark superseded, through the real hook (`_tag_created_layers`) on real QGIS layers and real lineage.

Written without a QGIS install: CI's first run is its first execution."""
import types
import unittest

try:
    from qgis.core import QgsProject, QgsSettings, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestMarkSupersededLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.addCleanup(lambda: QgsSettings().remove("cartogen_ai/mark_superseded"))

    def _run_tool(self, tool, output_name, source="roads"):
        """What the orchestrator does around a tool call: note the layers present, the tool adds its output layer, the hook runs."""
        from cartogen_ai.core.agent.agent_orchestrator import CartogenAi
        before = frozenset(QgsProject.instance().mapLayers())
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=id:integer", output_name, "memory")
        QgsProject.instance().addMapLayer(layer)
        res = {"success": True, "layer_name": output_name}
        CartogenAi._tag_created_layers(types.SimpleNamespace(), tool, {"layer_name": source}, res, before)
        return layer, res

    def _names(self):
        return sorted(layer.name() for layer in QgsProject.instance().mapLayers().values())

    def _roads(self):
        roads = QgsVectorLayer("LineString?crs=EPSG:4326", "roads", "memory")
        QgsProject.instance().addMapLayer(roads)
        return roads

    def test_a_rerun_keeps_the_older_result_renamed_and_the_new_one_holds_the_name(self):
        from cartogen_ai.core.agent.lineage import get_layer_lineage
        self._roads()
        first, res1 = self._run_tool("buffer_layer", "Buffered")
        self.assertNotIn("superseded_layers", res1)
        second, res2 = self._run_tool("buffer_layer", "Buffered")
        self.assertEqual(self._names(), ["Buffered", "Buffered (superseded)", "roads"])
        self.assertEqual(first.name(), "Buffered (superseded)")
        self.assertEqual(second.name(), "Buffered")
        self.assertEqual(res2["superseded_layers"], [{"was": "Buffered", "now": "Buffered (superseded)"}])
        self.assertIn("Nothing was deleted", res2["superseded_note"])
        self.assertEqual(QgsProject.instance().mapLayersByName("Buffered")[0].id(), second.id())
        # The lineage of the new result sits on the new layer, not on the older one that shares the name.
        self.assertEqual(len(get_layer_lineage(second)), 1)
        self.assertEqual(len(get_layer_lineage(first)), 1)

    def test_a_rerun_that_names_its_output_is_still_superseded(self):
        """Live trace 2026-11-20, row D2: buffer_analysis run twice with output_name given. The name of the first result is then a loaded layer
        and was counted as an input, so the second result was skipped as an echo: no lineage, no rename, two layers with one name."""
        from cartogen_ai.core.agent.agent_orchestrator import CartogenAi
        from cartogen_ai.core.agent.lineage import get_layer_lineage
        self._roads()

        def run():
            before = frozenset(QgsProject.instance().mapLayers())
            layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=id:integer", "roads_buffer_1deg", "memory")
            QgsProject.instance().addMapLayer(layer)
            res = {"success": True, "layer_name": "roads_buffer_1deg"}
            args = {"layer_name": "roads", "output_name": "roads_buffer_1deg", "distance": 1}
            CartogenAi._tag_created_layers(types.SimpleNamespace(), "buffer_analysis", args, res, before)
            return layer, res
        first, _res1 = run()
        second, res2 = run()
        self.assertEqual(self._names(), ["roads", "roads_buffer_1deg", "roads_buffer_1deg (superseded)"])
        self.assertEqual(first.name(), "roads_buffer_1deg (superseded)")
        self.assertEqual(res2["superseded_layers"], [{"was": "roads_buffer_1deg", "now": "roads_buffer_1deg (superseded)"}])
        self.assertEqual(len(get_layer_lineage(second)), 1)

    def test_the_third_run_numbers_the_next_superseded_name(self):
        self._roads()
        for _ in range(3):
            self._run_tool("buffer_layer", "Buffered")
        self.assertEqual(self._names(), ["Buffered", "Buffered (superseded 2)", "Buffered (superseded)", "roads"])

    def test_a_layer_the_user_made_with_the_same_name_is_left_alone(self):
        self._roads()
        mine = QgsVectorLayer("Polygon?crs=EPSG:4326", "Buffered", "memory")
        QgsProject.instance().addMapLayer(mine)
        self._run_tool("buffer_layer", "Buffered")
        self.assertEqual(mine.name(), "Buffered")
        self.assertEqual(self._names().count("Buffered"), 2)

    def test_another_tools_output_with_the_same_name_is_left_alone(self):
        self._roads()
        other, _ = self._run_tool("clip_layer", "Result")
        self._run_tool("buffer_layer", "Result")
        self.assertEqual(other.name(), "Result")

    def test_loading_the_same_data_twice_is_not_a_stale_result(self):
        first, _ = self._run_tool("add_layer_from_path", "Loaded")
        self._run_tool("add_layer_from_path", "Loaded")
        self.assertEqual(first.name(), "Loaded")

    def test_the_setting_switches_it_off(self):
        QgsSettings().setValue("cartogen_ai/mark_superseded", False)
        self._roads()
        first, _ = self._run_tool("buffer_layer", "Buffered")
        _second, res = self._run_tool("buffer_layer", "Buffered")
        self.assertEqual(first.name(), "Buffered")
        self.assertNotIn("superseded_layers", res)


if __name__ == "__main__":
    unittest.main()
