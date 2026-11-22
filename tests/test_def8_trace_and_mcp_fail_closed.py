"""Master-list row DEF-8 (owner decision 2026-11-22: when protection cannot be applied, fail closed), two more handlers:
  - api_trace._redact: the opt-in trace holds RAW prompts and tool results; text that could not be run through the key redaction is withheld, not written as it is;
  - mcp_server._layer_ids: when QGIS cannot list the open layers before a write call, every layer counts as a source of what the call creates, so protection is
    only ever added, never dropped. All offline against fakes; not seen on a real QGIS failure."""
import sys
import types
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent import api_trace, mcp_server


class TestTheTraceWithholdsTextItCannotRedact(unittest.TestCase):
    def test_a_redaction_helper_that_fails_withholds_the_text(self):
        with patch("cartogen_ai.core.logger._redact", side_effect=RuntimeError("boom sk-abc123secret")):
            out = api_trace._clip("my key is sk-abc123secretkey0000")
        self.assertNotIn("sk-abc", out)
        self.assertIn("withheld", out)
        self.assertIn("RuntimeError", out)

    def test_the_normal_path_still_redacts_and_keeps_the_text(self):
        out = api_trace._clip("plain text")
        self.assertEqual(out, "plain text")


class FakeLayer:
    def __init__(self, name):
        self._n = name

    def id(self):
        return "id_" + self._n

    def name(self):
        return self._n


def _fake_qgis(layers):
    project = types.SimpleNamespace(mapLayers=lambda: {f"id_{lyr.name()}": lyr for lyr in layers}, mapLayersByName=lambda n: [])
    core = types.ModuleType("qgis.core")
    core.QgsProject = types.SimpleNamespace(instance=lambda: project)
    return {"qgis": types.ModuleType("qgis"), "qgis.core": core}


class TestMcpLineageWhenTheLayerListCannotBeRead(unittest.TestCase):
    def test_an_unreadable_layer_list_is_none_not_empty(self):
        class Broken:
            @staticmethod
            def instance():
                raise RuntimeError("no project")
        core = types.ModuleType("qgis.core")
        core.QgsProject = Broken
        with patch.dict(sys.modules, {"qgis": types.ModuleType("qgis"), "qgis.core": core}):
            self.assertIsNone(mcp_server._layer_ids())

    def _sources_seen(self, ids_before):
        layers = [FakeLayer("clinics"), FakeLayer("roads")]
        seen = []
        with patch.dict(sys.modules, _fake_qgis(layers)), \
             patch("cartogen_ai.core.agent.lineage.derive_sources", side_effect=lambda name, args, names: seen.append(list(names)) or list(names)), \
             patch("cartogen_ai.core.agent.lineage.source_layer_ids", return_value=[]), \
             patch("cartogen_ai.core.agent.lineage.created_layer_names", return_value=[]):
            mcp_server._tag_lineage("some_tool", {}, {"success": True}, ids_before)
        return seen[0]

    def test_when_the_list_could_not_be_read_every_layer_counts_as_read(self):
        self.assertEqual(sorted(self._sources_seen(None)), ["clinics", "roads"])

    def test_a_readable_list_still_narrows_to_the_layers_that_were_open(self):
        self.assertEqual(self._sources_seen({"id_clinics"}), ["clinics"])
        self.assertEqual(self._sources_seen(set()), [])


if __name__ == "__main__":
    unittest.main()
