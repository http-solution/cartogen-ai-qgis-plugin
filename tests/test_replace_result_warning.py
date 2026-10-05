# -*- coding: utf-8 -*-
"""#130 point 3: when a result layer is replaced by name with one built with DIFFERENT parameters, the tool result says so. The pure helpers run offline;
the layer behaviour runs only in real QGIS (the `qgis-live-tests` job; written without a local QGIS, so CI's first run is its first execution)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cartogen_ai.core.agent.tools import logistics_tools as lt

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

OLD = {"tool": "calculate_service_area", "strategy": "shortest", "travel_cost": [3600.0], "speed_field": None}


class TestDescribeParamChanges(unittest.TestCase):
    def test_same_parameters_have_no_changes_even_if_a_list_is_reordered(self):
        self.assertEqual(lt.describe_param_changes(OLD, dict(OLD)), [])
        self.assertEqual(lt.describe_param_changes({"travel_cost": [1, 2]}, {"travel_cost": [2, 1]}), [])

    def test_changed_added_and_removed_parameters_are_listed_in_a_stable_order(self):
        new = {"tool": "calculate_service_area", "strategy": "fastest", "travel_cost": [5000.0], "direction_field": "oneway"}
        got = lt.describe_param_changes(OLD, new)
        self.assertEqual([k for k, _a, _b in got], ["direction_field", "strategy", "travel_cost"])
        self.assertEqual(got[1], ("strategy", "shortest", "fastest"))
        self.assertEqual(got[0], ("direction_field", None, "oneway"))

    def test_the_note_names_the_layer_and_each_change(self):
        note = lt.replacement_note("Origin_service_area_0", [("travel_cost", [3600.0], [5000.0]), ("speed_field", None, "speed_kmh")])
        self.assertIn("'Origin_service_area_0'", note)
        self.assertIn("travel_cost: [3600.0] -> [5000.0]", note)
        self.assertIn("speed_field: not set -> speed_kmh", note)
        self.assertIn("no longer in the project", note)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestReplaceNamedLayerLive(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _layer(self):
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "x", "memory")
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromWkt("LINESTRING(0 0, 1 1)"))
        layer.dataProvider().addFeatures([f])
        return layer

    def test_different_parameters_report_the_replacement_and_the_new_layer_carries_its_own(self):
        first = lt._replace_named_layer("Origin_service_area_0", self._layer(), params=OLD)
        self.assertIsNone(first)  # nothing was replaced
        new = dict(OLD, strategy="fastest", travel_cost=[1.0])
        second = lt._replace_named_layer("Origin_service_area_0", self._layer(), params=new)
        self.assertEqual(second["layer"], "Origin_service_area_0")
        self.assertEqual({c["parameter"] for c in second["changes"]}, {"strategy", "travel_cost"})
        self.assertEqual(len(QgsProject.instance().mapLayersByName("Origin_service_area_0")), 1)
        third = lt._replace_named_layer("Origin_service_area_0", self._layer(), params=new)
        self.assertIsNone(third)  # a re-run with the same parameters is silent

    def test_a_layer_without_recorded_parameters_is_replaced_silently(self):
        old = self._layer()
        old.setName("Origin_service_area_0")
        QgsProject.instance().addMapLayer(old)
        self.assertIsNone(lt._replace_named_layer("Origin_service_area_0", self._layer(), params=OLD))
        self.assertEqual(len(QgsProject.instance().mapLayersByName("Origin_service_area_0")), 1)

    def test_callers_that_pass_no_parameters_behave_as_before(self):
        lt._replace_named_layer("A", self._layer())
        self.assertIsNone(lt._replace_named_layer("A", self._layer()))
        self.assertEqual(len(QgsProject.instance().mapLayersByName("A")), 1)


if __name__ == "__main__":
    unittest.main()
