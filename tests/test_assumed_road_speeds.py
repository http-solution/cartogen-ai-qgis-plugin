"""HU-3b (owner chose B and D, 2026-11-23): one table of assumed road speeds (D), and an in-memory fallback to it when a 'fastest' run has no usable speeds (B).

Offline: the decision logic of _assume_class_speeds with the QGIS parts replaced; tests/test_assumed_road_speeds_live.py runs it on real layers in CI."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools import _road_speeds as rs
from cartogen_ai.core.agent.tools import impedance_tools as imp
from cartogen_ai.core.agent.tools import logistics_tools as lt


class FakeField:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class FakeNetwork:
    def __init__(self, names):
        self._names = names

    def fields(self):
        return [FakeField(n) for n in self._names]


class TestOneTable(unittest.TestCase):
    def test_the_two_tools_read_the_same_table_object(self):
        self.assertIs(lt.ASSUMED_SPEED_BY_ROAD_CLASS_KMH, rs.ASSUMED_SPEED_BY_ROAD_CLASS_KMH)
        self.assertIs(imp._HIGHWAY_BASE_SPEED_KMH, rs.ASSUMED_SPEED_BY_ROAD_CLASS_KMH)

    def test_the_main_classes_have_the_values_the_decision_named(self):
        table = rs.ASSUMED_SPEED_BY_ROAD_CLASS_KMH
        self.assertEqual([table[c] for c in ("motorway", "trunk", "primary", "secondary", "tertiary", "residential", "service", "track")],
                         [100, 80, 70, 60, 50, 40, 20, 20])

    def test_speed_for_class_ignores_case_and_spaces_and_reports_an_unknown_class(self):
        table = rs.ASSUMED_SPEED_BY_ROAD_CLASS_KMH
        self.assertEqual(rs.speed_for_class(" Primary ", table), (70.0, True))
        self.assertEqual(rs.speed_for_class("cobbled_lane", table, 33), (33.0, False))
        self.assertEqual(rs.speed_for_class(None, table, 50), (50.0, False))

    def test_the_class_field_is_fclass_or_highway_in_that_order(self):
        self.assertEqual(rs.road_class_field(["a", "highway", "fclass"]), "fclass")
        self.assertEqual(rs.road_class_field(["a", "highway"]), "highway")
        self.assertIsNone(rs.road_class_field(["a", "b"]))

    def test_country_scaling_still_works_and_an_unknown_country_falls_back(self):
        table, used = rs.speed_table("jo")
        self.assertEqual(used, "JO")
        self.assertEqual(table["motorway"], 110)
        table, used = rs.speed_table("YE")
        self.assertIsNone(used)
        self.assertEqual(table, rs.ASSUMED_SPEED_BY_ROAD_CLASS_KMH)


class TestTheNote(unittest.TestCase):
    def test_the_note_says_it_is_an_assumption_names_the_field_and_the_counts_and_that_the_layer_is_untouched(self):
        note = lt._assumed_speed_note("fclass", 150_000, 11_041, 50)
        for part in ("ASSUMED speeds by road class", "'fclass'", "150,000", "11,041", "50 km/h", "Your layer was not changed", "not been checked against a known journey",
                     "estimate_road_speeds"):
            self.assertIn(part, note)

    def test_a_dropped_speed_field_is_explained_first(self):
        note = lt._assumed_speed_note("highway", 10, 0, 50, "speed_field 'maxspeed' has a usable value on only 0.90% of roads.")
        self.assertTrue(note.startswith("speed_field 'maxspeed'"))

    def test_the_reused_field_variant_names_the_field(self):
        self.assertIn("assumed_speed_kmh", lt._assumed_speed_note(None, 0, 0, 50, None, reused=True))


class TestTheDecision(unittest.TestCase):
    def _run(self, names, speed_field=None, strategy="fastest", vet=(None, None), copy=("COPY", 8, 2), usable_share=(0.0, 0, 5)):
        network = FakeNetwork(names)
        with patch.object(lt, "_vet_speed_field", return_value=vet), \
             patch.object(lt, "_network_with_class_speeds", return_value=copy) as build, \
             patch.object(lt, "_usable_speed_share", return_value=usable_share), \
             patch.object(lt, "_field_values", return_value=[]):
            out = lt._assume_class_speeds(network, speed_field, strategy, 50)
        return network, out, build

    def test_a_shortest_run_is_never_touched(self):
        network, out, build = self._run(["fclass"], strategy="shortest")
        self.assertEqual(out, (network, None, None))
        build.assert_not_called()

    def test_a_usable_speed_field_always_wins(self):
        network, out, build = self._run(["fclass", "maxspeed"], speed_field="maxspeed", vet=("maxspeed", None))
        self.assertEqual(out, (network, "maxspeed", None))
        build.assert_not_called()

    def test_a_speed_field_that_does_not_exist_is_left_for_the_normal_error(self):
        network, out, build = self._run(["fclass"], speed_field="nope")
        self.assertEqual(out, (network, "nope", None))
        build.assert_not_called()

    def test_no_speed_and_a_class_field_builds_the_in_memory_copy_and_says_so(self):
        _network, (net, field, note), build = self._run(["fclass"])
        self.assertEqual((net, field), ("COPY", lt.ASSUMED_SPEED_FIELD))
        self.assertIn("ASSUMED speeds by road class", note)
        build.assert_called_once()
        self.assertEqual(build.call_args.args[1:], ("fclass", 50))

    def test_an_osm_ingest_with_highway_is_covered_too(self):
        _network, (net, field, _note), _build = self._run(["highway"])
        self.assertEqual((net, field), ("COPY", lt.ASSUMED_SPEED_FIELD))

    def test_a_nearly_empty_speed_field_is_dropped_for_the_class_speeds_and_the_reason_is_in_the_note(self):
        drop = "speed_field 'maxspeed' has a usable value on only 0.90% of roads (1,504 of 161,041; 0/NULL means unset), so it was ignored and a flat default_speed of 50 km/h was used instead. Run estimate_road_speeds first for road-class based speeds."
        _network, (net, field, note), _build = self._run(["fclass", "maxspeed"], speed_field="maxspeed", vet=(None, drop))
        self.assertEqual((net, field), ("COPY", lt.ASSUMED_SPEED_FIELD))
        self.assertIn("only 0.90% of roads", note)
        self.assertNotIn("Run estimate_road_speeds first", note)              # the flat-default sentence is replaced, not repeated

    def test_no_class_field_keeps_todays_flat_default(self):
        network, out, build = self._run(["name"])
        self.assertEqual(out, (network, None, None))
        build.assert_not_called()

    def test_a_usable_assumed_speed_field_already_on_the_layer_is_used_as_it_is(self):
        network, out, build = self._run(["fclass", "assumed_speed_kmh"], usable_share=(1.0, 5, 5))
        self.assertEqual(out[0:2], (network, "assumed_speed_kmh"))
        self.assertIn("already on the layer", out[2])
        build.assert_not_called()

    def test_a_copy_that_cannot_be_made_falls_back_to_the_flat_default_instead_of_failing(self):
        network, out, _build = self._run(["fclass"], copy=(None, 0, 0))
        self.assertEqual(out, (network, None, None))


class TestRouteSummary(unittest.TestCase):
    def test_the_route_result_carries_the_assumption(self):
        out = lt.route_strategy_summary(True, 0.5, 50, "assumed_speed_kmh", "ASSUMED note")
        self.assertEqual(out["speed_assumption"], "ASSUMED note")
        self.assertIn("assumed speeds by road class", out["route_note"])

    def test_without_an_assumption_the_summary_is_what_it_was(self):
        out = lt.route_strategy_summary(True, 0.5, 50, None)
        self.assertNotIn("speed_assumption", out)
        self.assertIn("a flat 50 km/h on every road", out["route_note"])


class TestMatrixOptions(unittest.TestCase):
    def test_the_matrix_result_carries_the_assumption_only_when_there_is_one(self):
        self.assertEqual(lt._with_matrix_options({}, "assumed_speed_kmh", 0, None, "N")["speed_assumption"], "N")
        self.assertNotIn("speed_assumption", lt._with_matrix_options({}, None, 0, None))


if __name__ == "__main__":
    unittest.main()
