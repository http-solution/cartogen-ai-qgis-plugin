"""GitHub #150, rc48 hand test OI-150 (2026-10-24): with Cloud data protection = Block and `smoke_points` tagged SENSITIVE, merging it with
another layer, renaming the result twice and then asking for its attributes let the cloud model read it with no card. This runs that exact
sequence through the real tools and the real gate method (`CartogenAi._egress_gate_decision`) in the QGIS image CI uses.
The existing lineage tests tag by hand; none ran a real tool, then `_tag_created_layers`, then renames, then the gate. Written without a QGIS
install: CI's first run is its first execution, and a failure here is the finding, not a test slip."""
import unittest
from types import SimpleNamespace

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsSettings, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False

CLOUD = SimpleNamespace(base_url="https://generativelanguage.googleapis.com/v1beta")


def _points(name, rows):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", name, "memory")
    features = []
    for label, x, y in rows:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} {y})"))
        f.setAttributes([label])
        features.append(f)
    layer.dataProvider().addFeatures(features)
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestProtectedLayerSurvivesMergeAndRenames(unittest.TestCase):
    def setUp(self):
        from cartogen_ai.core.agent import agent_orchestrator as agent_mod
        from cartogen_ai.core.models import sensitivity
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_EGRESS_GATE_MODE
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        settings = QgsSettings()
        previous = settings.value(SETTINGS_EGRESS_GATE_MODE, "off")
        settings.setValue(SETTINGS_EGRESS_GATE_MODE, "enforce")
        self.addCleanup(settings.setValue, SETTINGS_EGRESS_GATE_MODE, previous)
        self.points = _points("smoke_points", [("a", 0, 0), ("b", 1, 1)])
        self.hubs = _points("smoke_hubs", [("h", 2, 2)])
        QgsProject.instance().addMapLayer(self.points)
        QgsProject.instance().addMapLayer(self.hubs)
        self.assertTrue(sensitivity.set_layer_sensitivity(self.points, "SENSITIVE", "test"))
        self.agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        self.agent.client = CLOUD

    def _decision(self, tool, layer_name):
        return self.agent._egress_gate_decision(tool, {"layer_name": layer_name})

    def _rename(self, old, new):
        from cartogen_ai.core.agent.tools.vector_tools import rename_layer
        result = rename_layer(old, new)
        self.assertTrue(result.get("success"), result)
        self.agent._tag_created_layers("rename_layer", {"old_name": old, "new_name": new}, result)

    def test_the_source_itself_is_blocked(self):
        decision = self._decision("get_attributes", "smoke_points")
        self.assertIsNotNone(decision)
        self.assertEqual(decision["action"], "block")

    def test_merge_then_two_renames_then_read_is_blocked(self):
        from cartogen_ai.core.agent.tools.vector_tools import merge_layers
        args = {"layer_names_list": ["smoke_points", "smoke_hubs"]}
        before = self.agent._loaded_layer_ids()
        result = merge_layers(**args)
        print(f"EGRESSFLOW merge result {result}")
        self.assertTrue(result.get("success"), result)
        self.agent._tag_created_layers("merge_layers", args, result, before)
        merged = QgsProject.instance().mapLayersByName(result["layer_name"])[0]
        from cartogen_ai.core.agent.lineage import get_layer_lineage
        print(f"EGRESSFLOW lineage after merge {get_layer_lineage(merged)}")
        self.assertTrue(get_layer_lineage(merged), "the merge output has no lineage at all")
        self._rename(result["layer_name"], "merged_test")
        self._rename("merged_test", "harmless_name")
        for tool in ("get_attributes", "field_statistics", "get_layer_info"):
            decision = self._decision(tool, "harmless_name")
            print(f"EGRESSFLOW {tool} -> {decision and decision['action']}")
            self.assertIsNotNone(decision, f"{tool} on the renamed merge output was let through")
            self.assertEqual(decision["action"], "block")

    def test_a_merge_through_the_generic_processing_tool_is_blocked_too(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        args = {"alg_id": "native:mergevectorlayers", "params": {"LAYERS": ["smoke_points", "smoke_hubs"]}, "new_layer_name": "generic_merge"}
        before = self.agent._loaded_layer_ids()          # taken before the tool runs, as the dispatcher does
        result = run_allowlisted_processing_algorithm(**args)
        print(f"EGRESSFLOW generic merge result {str(result)[:300]}")
        self.assertTrue(result.get("success"), result)
        self.agent._tag_created_layers("run_allowlisted_processing_algorithm", args, result, before)
        name = result.get("layer_name") or "generic_merge"
        decision = self._decision("get_attributes", name)
        self.assertIsNotNone(decision, "the generic Processing merge output was let through")
        self.assertEqual(decision["action"], "block")


if __name__ == "__main__":
    unittest.main()
