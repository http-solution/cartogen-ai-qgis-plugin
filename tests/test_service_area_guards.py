# -*- coding: utf-8 -*-
"""
Guards for calculate_service_area (rc7 smoke test, 2026-09-30, finding F05).

Live symptom: after the second run the project's `..._service_area_lines_0` had ONE feature of
length 0.0 (extent a single point), the previous good road network had been removed by
_replace_named_layer, and the chat still reported success from the earlier run's leftovers.
Two independent ways to get there, both guarded:
  * a speed_field that is almost entirely empty/0 (OSM Roads (Yemen): 929 of 139,758 roads,
    0.66%, have a maxspeed) -- almost nothing is traversable and the reach also uses the field's
    maximum, disabling the fast clipped path (graph build 50 s instead of 4 s);
  * travel_cost=1 meaning "one hour" without strategy='fastest' -- one METRE.
"""
import unittest

from cartogen_ai.core.agent.tools import logistics_tools as lt


class _Geom:
    def __init__(self, length, null=False):
        self._length = length
        self._null = null

    def isNull(self):
        return self._null

    def length(self):
        return self._length


class _Feature:
    def __init__(self, geometry=None, **attrs):
        self._geometry = geometry
        self._attrs = attrs

    def geometry(self):
        return self._geometry

    def __getitem__(self, key):
        return self._attrs[key]


class _Layer:
    def __init__(self, features):
        self._features = features

    def getFeatures(self, *args, **kwargs):
        return iter(self._features)

    def featureCount(self):
        return len(self._features)


class TestUsableSpeedShare(unittest.TestCase):
    def test_zero_and_null_count_as_unset(self):
        share, usable, total = lt._usable_speed_share([0, None, 50, 0, 80, "", "abc"])
        self.assertEqual((usable, total), (2, 7))
        self.assertAlmostEqual(share, 2 / 7)

    def test_the_yemen_roads_case_is_far_below_the_threshold(self):
        values = [60] * 929 + [0] * (139758 - 929)
        share, usable, total = lt._usable_speed_share(values)
        self.assertEqual((usable, total), (929, 139758))
        self.assertLess(share, lt.MIN_USABLE_SPEED_SHARE)

    def test_an_empty_layer_has_zero_share(self):
        self.assertEqual(lt._usable_speed_share([]), (0.0, 0, 0))

    def test_numeric_strings_are_read(self):
        self.assertEqual(lt._usable_speed_share(["50", "60"])[1], 2)


class TestSpeedFieldIsIgnoredWhenMostlyEmpty(unittest.TestCase):
    def test_a_sparse_field_is_dropped_with_a_note(self):
        layer = _Layer([_Feature(maxspeed=0)] * 99 + [_Feature(maxspeed=60)])
        field, note = lt._vet_speed_field(layer, "maxspeed", default_speed=50)
        self.assertIsNone(field)
        self.assertIn("1%", note)
        self.assertIn("50", note)
        self.assertIn("estimate_road_speeds", note)

    def test_a_well_populated_field_is_kept(self):
        layer = _Layer([_Feature(speed=40)] * 8 + [_Feature(speed=0)] * 2)
        field, note = lt._vet_speed_field(layer, "speed", default_speed=50)
        self.assertEqual(field, "speed")
        self.assertIsNone(note)

    def test_an_empty_layer_leaves_the_field_alone(self):
        self.assertEqual(lt._vet_speed_field(_Layer([]), "maxspeed", 50), ("maxspeed", None))

    def test_no_speed_field_is_a_no_op(self):
        self.assertEqual(lt._vet_speed_field(_Layer([]), None, 50), (None, None))


class TestDegenerateReachableNetwork(unittest.TestCase):
    def test_the_observed_zero_length_line_is_degenerate(self):
        self.assertTrue(lt._reachable_network_is_degenerate(_Layer([_Feature(_Geom(0.0))])))

    def test_a_real_network_is_not(self):
        self.assertFalse(lt._reachable_network_is_degenerate(
            _Layer([_Feature(_Geom(1200.5)), _Feature(_Geom(0.0))])))

    def test_null_geometries_are_ignored_and_all_null_is_degenerate(self):
        self.assertTrue(lt._reachable_network_is_degenerate(_Layer([_Feature(_Geom(5, null=True)), _Feature(None)])))

    def test_an_empty_layer_is_degenerate(self):
        self.assertTrue(lt._reachable_network_is_degenerate(_Layer([])))


class TestTravelCostUnitNote(unittest.TestCase):
    def test_one_meaning_an_hour_without_fastest_is_flagged(self):
        note = lt._travel_cost_unit_note("shortest", [1])
        self.assertIn("METRES", note)
        self.assertIn("fastest", note)

    def test_fastest_hours_are_fine(self):
        self.assertIsNone(lt._travel_cost_unit_note("fastest", [1]))

    def test_a_normal_distance_is_fine(self):
        self.assertIsNone(lt._travel_cost_unit_note("shortest", [5000]))


if __name__ == "__main__":
    unittest.main()
