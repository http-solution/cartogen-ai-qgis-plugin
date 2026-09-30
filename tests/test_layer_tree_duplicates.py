# -*- coding: utf-8 -*-
"""F07 (rc7 smoke test, 2026-09-30): layerTreeRoot().findLayers() returned 10 nodes for 7 layers.

Root cause found by reading the call sites: calculate_service_area / optimize_delivery_route add
their layers with addMapLayer() (which creates a tree node) and THEN call process_map_output,
whose insert_layer_semantically inserted a second QgsLayerTreeLayer for the same layer. A later
removeMapLayer() removed only one of the pair and left an orphan. This file checks the fix
against a small fake layer tree; tests/test_rc8_live.py checks it in real QGIS (CI)."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent import map_intelligence as mi


class _Node:
    def __init__(self, layer_id):
        self.layer_id = layer_id
        self._parent = None

    def parent(self):
        return self._parent


class _Root:
    def __init__(self):
        self._kids = []

    def children(self):
        return list(self._kids)

    def insertChildNode(self, index, node):
        node._parent = self
        self._kids.insert(index, node)

    def removeChildNode(self, node):
        self._kids.remove(node)
        node._parent = None

    def findLayer(self, layer_id):
        return next((n for n in self._kids if n.layer_id == layer_id), None)


def _layer(layer_id):
    layer = MagicMock()
    layer.id.return_value = layer_id
    layer.isValid.return_value = True
    return layer


class TestInsertLayerSemanticallyDoesNotDuplicate(unittest.TestCase):
    def setUp(self):
        self.root = _Root()
        self.project = MagicMock()
        self.project.layerTreeRoot.return_value = self.root

        def add_map_layer(layer, add_to_tree=True):
            if add_to_tree:
                self.root.insertChildNode(0, _Node(layer.id()))
        self.project.addMapLayer.side_effect = add_map_layer
        for name, value in (
            ("QGIS_AVAILABLE", True),
            ("QgsProject", MagicMock(instance=MagicMock(return_value=self.project))),
            ("QgsLayerTreeLayer", lambda layer: _Node(layer.id())),
        ):
            p = patch.object(mi, name, value, create=True)
            p.start()
            self.addCleanup(p.stop)

    def _descriptor(self, layer_id, role):
        return mi.MapOutputDescriptor(layer_id=layer_id, output_role=role, source_layer_id=None,
                                      recommended_label_field=None, style_profile=role, properties={})

    def test_a_layer_already_in_the_tree_keeps_exactly_one_node(self):
        layer = _layer("lines")
        self.project.addMapLayer(layer)          # what _replace_named_layer / addMapLayer do
        self.assertTrue(mi.insert_layer_semantically(layer, self._descriptor("lines", "facilities")))
        ids = [n.layer_id for n in self.root.children()]
        self.assertEqual(ids, ["lines"])

    def test_a_layer_not_yet_in_the_tree_is_added_once(self):
        layer = _layer("buffer")
        self.assertTrue(mi.insert_layer_semantically(layer, self._descriptor("buffer", "facilities")))
        self.assertEqual([n.layer_id for n in self.root.children()], ["buffer"])

    def test_moving_an_existing_node_lands_it_at_the_requested_end(self):
        for lid in ("a", "b", "c"):
            self.project.addMapLayer(_layer(lid))        # tree is now c, b, a (top first)
        mi.insert_layer_semantically(_layer("c"), self._descriptor("c", "thematic_choropleth"))
        self.assertEqual([n.layer_id for n in self.root.children()], ["b", "a", "c"])
        mi.insert_layer_semantically(_layer("a"), self._descriptor("a", "facilities"))
        self.assertEqual([n.layer_id for n in self.root.children()], ["a", "b", "c"])

    def test_calling_it_repeatedly_never_grows_the_tree(self):
        layer = _layer("x")
        self.project.addMapLayer(layer)
        for _ in range(4):
            mi.insert_layer_semantically(layer, self._descriptor("x", "facilities"))
        self.assertEqual(len(self.root.children()), 1)


if __name__ == "__main__":
    unittest.main()
