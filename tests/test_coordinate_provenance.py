"""Point positions the model typed that nothing in the conversation supports are flagged (GitHub follow-up to #75, rule 42)."""
import json
import unittest

from cartogen_ai.core.services import coordinate_provenance as cp


class TestPointsFromCall(unittest.TestCase):
    def test_add_point_layer_reads_lon_lat_and_xy(self):
        args = {"points": [{"name": "A", "lon": 44.2, "lat": 15.3}, {"name": "B", "x": 4902068, "y": 1799912}]}
        self.assertEqual([(p[0], p[1]) for p in cp.points_from_call("add_point_layer", args)], [(44.2, 15.3), (4902068.0, 1799912.0)])

    def test_add_incident_point_and_script_literals(self):
        self.assertEqual(len(cp.points_from_call("add_incident_point", {"lat": 33.89, "lon": 35.5, "description": "x"})), 1)
        script = "p = QgsPointXY(35.5018, 33.8938)\nq = QgsPoint(1, 2)\nr = QgsPointXY(x, y)"
        self.assertEqual([(a, b) for a, b, _ in cp.points_from_call("execute_pyqgis_script", {"script": script})],
                         [(35.5018, 33.8938), (1.0, 2.0)])

    def test_unrelated_or_malformed_calls_give_nothing(self):
        self.assertEqual(cp.points_from_call("buffer_analysis", {"points": [{"lon": 1, "lat": 2}]}), [])
        self.assertEqual(cp.points_from_call("add_point_layer", {"points": [{"lon": "n/a", "lat": None}]}), [])
        self.assertEqual(cp.points_from_call("add_point_layer", "not a dict"), [])


class TestUnverified(unittest.TestCase):
    EVIDENCE = "User: put a marker at 15.3694, 44.1910. geocode result: {'lat': 33.8938, 'lon': 35.5018}"

    def test_coordinates_the_user_or_a_tool_gave_are_grounded(self):
        pts = [(44.1910, 15.3694, "user"), (35.5018, 33.8938, "geocoder")]
        self.assertEqual(cp.unverified_points(pts, self.EVIDENCE), [])

    def test_a_rounded_value_within_tolerance_is_grounded(self):
        self.assertEqual(cp.unverified_points([(35.50, 33.89, "r")], self.EVIDENCE), [])

    def test_coordinates_from_nowhere_are_flagged(self):
        bad = cp.unverified_points([(35.62, 33.81, "Invented"), (35.5018, 33.8938, "ok")], self.EVIDENCE)
        self.assertEqual([p[2] for p in bad], ["Invented"])

    def test_one_grounded_number_is_not_enough(self):
        self.assertEqual(len(cp.unverified_points([(35.5018, 12.34, "half")], self.EVIDENCE)), 1)

    def test_negative_coordinates_match_by_magnitude_text(self):
        self.assertEqual(cp.unverified_points([(-74.006, 40.7128, "NYC")], "user said 40.7128 and -74.006"), [])


class TestCheckCall(unittest.TestCase):
    def test_a_failed_call_and_an_unrelated_tool_are_ignored(self):
        args = {"points": [{"lon": 1.5, "lat": 2.5}]}
        self.assertEqual(cp.check_call("add_point_layer", args, {"error": "boom"}, ""), (0, []))
        self.assertEqual(cp.check_call("buffer_analysis", args, {"success": True}, ""), (0, []))

    def test_a_successful_ungrounded_call_is_flagged_with_a_note(self):
        args = {"points": [{"name": "X", "lon": 35.62, "lat": 33.81}]}
        total, bad = cp.check_call("add_point_layer", args, {"success": True}, "nothing relevant 7 8 9")
        self.assertEqual((total, len(bad)), (1, 1))
        self.assertIn("typed by the model", cp.result_note(total, bad))
        self.assertIsNone(cp.result_note(1, []))

    def test_the_final_note_is_added_once_and_only_when_flagged(self):
        text = cp.apply_final_note("Done.", 3)
        self.assertIn(cp.MARKER, text)
        self.assertEqual(cp.apply_final_note(text, 3), text)
        self.assertEqual(cp.apply_final_note("Done.", 0), "Done.")


class TestOrchestratorHook(unittest.TestCase):
    def _agent(self, grounding):
        from cartogen_ai.core.agent.agent_orchestrator import CartogenAi
        agent = CartogenAi.__new__(CartogenAi)
        agent._grounding_texts = list(grounding)
        agent._turn_unverified_points = 0
        return agent

    def test_the_result_the_model_reads_carries_the_warning_and_the_turn_is_counted(self):
        agent = self._agent(["place a marker at 15.3694, 44.1910"])
        args = json.dumps({"layer_name": "L", "points": [{"name": "A", "lon": 44.191, "lat": 15.3694},
                                                          {"name": "B", "lon": 35.62, "lat": 33.81}]})
        result = agent._check_point_provenance("add_point_layer", args, {"success": True})
        self.assertEqual(agent._turn_unverified_points, 1)
        self.assertEqual(result["unverified_coordinates"][0]["label"], "B")
        self.assertIn("unverified", result["coordinate_provenance_note"])

    def test_a_call_cannot_ground_itself_and_other_tools_are_untouched(self):
        agent = self._agent([])
        res = agent._check_point_provenance("buffer_analysis", "{}", {"success": True})
        self.assertEqual(res, {"success": True})
        self.assertEqual(agent._turn_unverified_points, 0)


if __name__ == "__main__":
    unittest.main()
