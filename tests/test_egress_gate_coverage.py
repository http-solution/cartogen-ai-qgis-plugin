# -*- coding: utf-8 -*-
"""Keeps the egress gate's coverage claim true (docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md §9).

The gate decides, BEFORE a tool runs, whether the call touches a protected layer -- and it can only
tell by the layer names in the call's arguments. A tool that reads feature values without naming a
layer (e.g. one that loops over every layer in the project) would slip past it silently. On
2026-09-24 every registered tool that reads features took a layer argument, so no separate catch-all
was built; this test is what stops that quietly becoming untrue when a new tool is added.

If this fails for a new tool: give it a layer argument, or add it to egress_gate.WHOLE_PROJECT_TOOLS
(the gate then treats every layer in the project as touched, as it does for execute_pyqgis_script),
or -- only if it genuinely never sends feature values to the model -- to _NOT_VALUE_BEARING below with
a comment saying why."""
import inspect
import unittest

from cartogen_ai.core.agent.tools import TOOL_REGISTRY, TOOLS_SCHEMA
from cartogen_ai.core.models import egress_gate

# Tools that call getFeatures() but never return feature values to the model. Empty today; each
# entry is a claim someone has to be able to defend.
_NOT_VALUE_BEARING = frozenset()

_FEATURE_READ_MARKERS = ("getFeatures(", ".attributes()", "dataProvider().getFeatures")


def _names_a_layer(properties):
    return any("layer" in k.lower() or k in ("input", "INPUT") for k in properties)


class TestEveryFeatureReaderIsClassifiable(unittest.TestCase):
    def test_every_tool_that_reads_features_names_a_layer_or_is_whole_project(self):
        props = {t["function"]["name"]: t["function"]["parameters"].get("properties", {})
                 for t in TOOLS_SCHEMA}
        unclassifiable = []
        for name, fn in TOOL_REGISTRY.items():
            try:
                src = inspect.getsource(fn)
            except (OSError, TypeError):
                continue
            if not any(m in src for m in _FEATURE_READ_MARKERS):
                continue
            if name in egress_gate.WHOLE_PROJECT_TOOLS or name in _NOT_VALUE_BEARING:
                continue
            if not _names_a_layer(props.get(name, {})):
                unclassifiable.append(name)
        self.assertEqual(unclassifiable, [], "these read features without a layer argument, so the "
                         "egress gate cannot see what they touch -- see this module's docstring")

    def test_the_scan_actually_finds_feature_readers(self):
        # Guards against the check above passing vacuously (e.g. getsource failing for everything).
        readers = []
        for n, fn in TOOL_REGISTRY.items():
            try:
                if "getFeatures(" in inspect.getsource(fn):
                    readers.append(n)
            except (OSError, TypeError):
                continue
        self.assertGreater(len(readers), 10)


if __name__ == "__main__":
    unittest.main()
