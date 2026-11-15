"""GitHub #150, rc48 hand test OI-150: the output a caller NAMES (new_layer_name) must be tagged with the layers it was made from.
Found by the CI reproduction tests/test_egress_flow_live.py: the name was already a loaded layer when the tagger ran, so it was counted as an
input, then skipped as "an echo of its own input", and a merge of a SENSITIVE layer came out with no lineage. These are the offline checks of
that rule, against a fake qgis.core (no QGIS needed)."""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent import agent_orchestrator as agent_mod


class _Layer:
    def __init__(self, layer_id, name):
        self._id, self._name = layer_id, name

    def id(self):
        return self._id

    def name(self):
        return self._name


def _project(layers):
    project = MagicMock()
    project.mapLayers.return_value = {lyr.id(): lyr for lyr in layers}
    project.mapLayersByName.side_effect = lambda n: [lyr for lyr in layers if lyr.name() == n]
    return project


def _tag(layers, before_ids, name, args, result):
    """The (layer, sources, source_ids) every tag_layer_lineage call received."""
    fake_core = types.ModuleType("qgis.core")
    fake_core.QgsProject = MagicMock()
    fake_core.QgsProject.instance.return_value = _project(layers)
    fake_qgis = types.ModuleType("qgis")
    fake_qgis.core = fake_core
    calls = []
    agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
    with patch.dict(sys.modules, {"qgis": fake_qgis, "qgis.core": fake_core}), \
            patch("cartogen_ai.core.agent.lineage.tag_layer_lineage",
                  side_effect=lambda layer, tool, params, sources, ids: calls.append((layer.name(), sources, ids)) or True):
        agent._tag_created_layers(name, args, result, before_ids)
    return calls


class TestNamedOutputIsTagged(unittest.TestCase):
    def setUp(self):
        self.points = _Layer("p1", "smoke_points")
        self.hubs = _Layer("h1", "smoke_hubs")
        self.merged = _Layer("m1", "generic_merge")
        self.layers = [self.points, self.hubs, self.merged]
        self.args = {"alg_id": "native:mergevectorlayers", "params": {"LAYERS": ["smoke_points", "smoke_hubs"]},
                     "new_layer_name": "generic_merge"}
        self.result = {"success": True, "alg_id": "native:mergevectorlayers", "layer_name": "generic_merge"}

    def test_a_caller_named_output_is_tagged_with_its_inputs(self):
        calls = _tag(self.layers, frozenset({"p1", "h1"}), "run_allowlisted_processing_algorithm", self.args, self.result)
        self.assertEqual(calls, [("generic_merge", ["smoke_hubs", "smoke_points"], ["h1", "p1"])])

    def test_the_output_name_is_never_one_of_its_own_sources(self):
        calls = _tag(self.layers, frozenset({"p1", "h1"}), "run_allowlisted_processing_algorithm", self.args, self.result)
        self.assertNotIn("generic_merge", calls[0][1])

    def test_a_tool_that_edits_an_existing_layer_does_not_tag_it_as_derived_from_itself(self):
        roads = _Layer("r1", "roads")
        calls = _tag([roads], frozenset({"r1"}), "set_layer_color", {"layer_name": "roads"}, {"success": True, "layer_name": "roads"})
        self.assertEqual(calls, [])

    def test_without_the_before_list_the_old_rule_still_applies(self):
        # two-phase tools add their layer on the main thread and are tagged without a before list
        calls = _tag([self.points, self.hubs], None, "merge_layers", {"layer_names_list": ["smoke_points", "smoke_hubs"]},
                     {"success": True, "layer_name": "merged_layer"})
        self.assertEqual(calls, [])             # "merged_layer" is not loaded in this fake project, so there is nothing to tag


if __name__ == "__main__":
    unittest.main()
