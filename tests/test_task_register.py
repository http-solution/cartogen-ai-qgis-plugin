# -*- coding: utf-8 -*-
"""Tests for the Humanitarian Mapping Task Register and its matcher."""
import unittest

from cartogen_ai.core.agent import task_register as reg
from cartogen_ai.core.agent import task_matcher as tm


class TestRegisterIntegrity(unittest.TestCase):
    def setUp(self):
        self.data = reg.load()

    def test_register_loads_all_tasks(self):
        self.assertEqual(len(self.data), 792)

    def test_ids_are_unique(self):
        ids = [e["id"] for e in self.data]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_task_has_a_known_output_contract(self):
        for e in self.data:
            self.assertIn(e["out"], reg.OUTPUTS, e["id"])

    def test_every_tool_reference_is_a_real_registered_tool(self):
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        known = set(TOOL_REGISTRY)
        for e in self.data:
            for t in e["tools"]:
                self.assertIn(t, known, "%s references unknown tool %s" % (e["id"], t))

    def test_layer_and_layout_tasks_can_acquire_data(self):
        acquire = ("fetch_", "search_", "add_layer_from_path", "load_", "geocode_",
                   "georeference_image", "extract_features_from_imagery",
                   "add_point_layer", "add_incident_point")
        for e in self.data:
            if e["out"] in ("layer", "layout"):
                self.assertTrue(
                    any(t.startswith(acquire) or t in acquire for t in e["tools"]),
                    "%s (%s) has no way to get data" % (e["id"], e["text"]))

    def test_only_guidance_tasks_may_have_no_tools(self):
        for e in self.data:
            if not e["tools"]:
                self.assertEqual(e["out"], "guidance", e["id"])

    def test_every_slot_has_a_question_and_a_default_policy(self):
        for e in self.data:
            for s in e["slots"]:
                self.assertIn(s, reg.SLOT_QUESTIONS, s)
                self.assertIn(s, reg.SLOT_DEFAULTS, s)

    def test_by_id_round_trips(self):
        for e in self.data[:50]:
            self.assertEqual(reg.by_id(e["id"])["text"], e["text"])

    def test_missing_data_file_degrades_instead_of_raising(self):
        real = reg._data_path
        reg._DATA = None
        reg._data_path = lambda: "/nonexistent/task_register.json"
        try:
            self.assertEqual(reg.load(), [])
        finally:
            reg._data_path = real
            reg._DATA = None
            reg.load()


class TestMatching(unittest.TestCase):
    def test_matches_a_clear_request(self):
        r = tm.classify("map flooded areas in Sindh after the August floods")
        self.assertEqual(r["best"]["text"], "Map flooded areas")
        self.assertFalse(r["ambiguous"])

    def test_empty_query_matches_nothing(self):
        for q in ("", "   ", None):
            r = tm.classify(q)
            self.assertIsNone(r["best"])
            self.assertFalse(r["ambiguous"])

    def test_greeting_matches_nothing(self):
        self.assertIsNone(tm.classify("hello")["best"])

    def test_weak_match_is_flagged_ambiguous(self):
        r = tm.classify("how many people live within 5 km of a health facility")
        self.assertTrue(r["ambiguous"])

    def test_matches_are_ordered_best_first(self):
        ms = tm.match("map damaged buildings after the earthquake")
        self.assertTrue(all(ms[i][1] >= ms[i + 1][1] for i in range(len(ms) - 1)))

    def test_guidance_task_is_reachable(self):
        r = tm.classify("train our field team in GPS collection")
        self.assertEqual(r["best"]["out"], "guidance")

    def test_travel_time_language_prefers_the_service_area_task(self):
        """Live-reported bug, 2026-09-19: "Health facilities beyond one hour's
        travel" confidently matched 25c.01 ("Map health facilities", a plain
        add_layer_from_path task with no calculate_service_area tool at all) over
        7.23 ("Calculate travel time to health facilities", the actually-correct
        task) -- purely a side effect of _score's keyword-count normalisation
        favoring 25c.01's much shorter kw list. The model then had no
        calculate_service_area in its directive, couldn't find a nonexistent local
        data file, and burned its whole tool-call budget probing
        execute_pyqgis_script's sandbox instead. classify() must now surface the
        service-area task (flagged ambiguous is fine/expected here -- this is a
        genuine, close call the caller's disambiguation step should confirm, not
        something to answer with false confidence in either direction)."""
        r = tm.classify("Health facilities beyond one hour's travel")
        self.assertEqual(r["best"]["id"], "7.23")
        self.assertIn("calculate_service_area", r["best"]["tools"])

    def test_travel_time_override_does_not_fire_without_a_service_area_candidate(self):
        # Travel-time language is present, but no calculate_service_area task
        # scores at all for this query -- the override must be a no-op rather
        # than force a nonsensical pick just because the regex matched.
        r = tm.classify("map flooded areas beyond one hour's drive")
        self.assertEqual(r["best"]["text"], "Map flooded areas")

    def test_plain_distance_language_is_unaffected(self):
        # "within 5 km" has no hour/minute unit, so the travel-time override must
        # not fire here -- this must keep behaving exactly as
        # test_weak_match_is_flagged_ambiguous already asserts.
        r = tm.classify("how many people live within 5 km of a health facility")
        self.assertTrue(r["ambiguous"])


class TestOutputContract(unittest.TestCase):
    def test_explicit_dashboard_overrides_the_task_default(self):
        q = "make a dashboard of displacement over time"
        e = tm.classify(q)["best"]
        c = tm.output_contract(e, q)
        self.assertEqual(c["kind"], "dashboard")
        self.assertTrue(c["overridden"])
        self.assertIn("generate_html_dashboard", c["render"])

    def test_no_override_keeps_the_task_default(self):
        q = "map flooded areas in Sindh"
        e = tm.classify(q)["best"]
        c = tm.output_contract(e, q)
        self.assertEqual(c["kind"], e["out"])
        self.assertFalse(c["overridden"])

    def test_export_request_becomes_a_dataset(self):
        q = "export the camp boundaries as geopackage"
        e = tm.classify(q)["best"]
        self.assertEqual(tm.output_contract(e, q)["kind"], "dataset")

    def test_contract_is_none_without_a_task(self):
        self.assertIsNone(tm.output_contract(None, "anything"))


class TestSlots(unittest.TestCase):
    def setUp(self):
        self.q = "map flood hazard"
        self.e = tm.classify(self.q)["best"]

    def test_hazard_named_in_query_is_not_asked_for(self):
        self.assertNotIn("hazard_type", tm.missing_slots(self.e, self.q))

    def test_qgis_context_suppresses_the_question(self):
        self.assertEqual(tm.missing_slots(self.e, self.q, {"aoi": "canvas extent"}), [])

    def test_detail_in_the_query_suppresses_the_question(self):
        q = "map flood hazard in Sindh district using sentinel imagery from 2026 within 10 km"
        self.assertEqual(tm.missing_slots(tm.classify(q)["best"], q), [])

    def test_a_service_area_request_is_not_matched_to_an_unrelated_task(self):
        # rc10 smoke test: matched 21.23 "Calculate area and density" at 0.42 and the model went on to fetch a population
        # raster, estimate exposure and export a CSV nobody asked for. No directive is better than a wrong one.
        q = "Calculate a one-hour driving service area from the point 4902068.0, 1799912.0 using the roads layer"
        verdict = tm.classify(q)
        self.assertTrue(verdict["ambiguous"])
        self.assertEqual(verdict["reason"], "below confidence floor")

    def test_a_travel_time_request_still_gets_its_task(self):
        q = "Health facilities beyond one hour's travel from the point 4902068.0, 1799912.0 in Yemen."
        self.assertEqual(tm.classify(q)["best"]["id"], "7.23")

    def test_download_as_an_input_is_not_a_request_for_an_exported_file(self):
        # rc10 smoke test: "download the whole Yemen population raster and then estimate ..." forced a GPKG+CSV deliverable
        # and a follow-up call that wrote four unrequested export files.
        q = "Yes, download the whole Yemen population raster and then estimate the population within one hour's drive"
        self.assertNotEqual(tm.output_override(q), "dataset")
        self.assertEqual(tm.output_override("export the clinics to CSV"), "dataset")
        self.assertEqual(tm.output_override("save it as a geopackage"), "dataset")
    def test_a_point_origin_answers_the_facility_question(self):
        # rc10 smoke test: "Which facility or service type?" was asked three times of a request that names a coordinate.
        q = ("Estimate the population within one hour's drive of the point 4902068.0, 1799912.0 "
             "using WorldPop in Yemen")
        entry = tm.classify(q)["best"]
        self.assertNotIn("facility_type", tm.missing_slots(entry, q))
        q2 = "population within one hour of the origin using WorldPop in Yemen"
        self.assertNotIn("facility_type", tm.missing_slots(tm.classify(q2)["best"], q2))

    def test_a_request_with_no_origin_and_no_facility_still_asks(self):
        q = "Calculate population within service areas using WorldPop in Yemen within 1 hour"
        entry = tm.classify(q)["best"]
        if entry and "facility_type" in (entry.get("slots") or []):
            self.assertIn("facility_type", tm.missing_slots(entry, q))

    def test_one_question_covers_every_missing_slot(self):
        miss = tm.missing_slots(self.e, self.q)
        text = tm.clarify_question(self.e, miss)
        for s in miss:
            self.assertIn(reg.SLOT_QUESTIONS[s], text)

    def test_defaults_are_stated_in_the_question(self):
        miss = tm.missing_slots(self.e, self.q)
        self.assertIn("current canvas extent", tm.clarify_question(self.e, miss))

    def test_spelled_out_and_plural_thresholds_count_as_given(self):
        # Live-reported 2026-09-24: "one hour's travel" wasn't recognised, so the 5 km default
        # was added next to the user's own one-hour limit ("Given: threshold = 5 km").
        q = "Health facilities beyond one hour's travel 3996804,3754118"
        entry = tm.classify(q)["best"]
        self.assertIn("threshold", entry.get("slots", []))  # guard: the task really asks for it
        self.assertNotIn("threshold", tm.missing_slots(entry, q))
        for phrase in ("within 2 hours", "within 30 minutes", "half an hour", "an hour",
                       "2.5 kilometres", "500 m", "5km"):
            self.assertNotIn("threshold", tm.missing_slots(entry, "health facilities " + phrase), phrase)
        for phrase in ("I am here", "a map of clinics", "one more layer"):
            self.assertIn("threshold", tm.missing_slots(entry, "health facilities " + phrase), phrase)

    def test_consequential_slots_have_no_silent_default(self):
        # guessing a hazard type or sector produces confidently wrong output
        for s in ("hazard_type", "sector", "facility_type"):
            self.assertEqual(tm.defaults([s]), {})
            self.assertEqual(tm.unresolvable([s]), [s])

    def test_no_question_when_nothing_is_missing(self):
        self.assertEqual(tm.clarify_question(self.e, []), "")


class TestDirective(unittest.TestCase):
    def test_directive_stays_within_the_prompt_budget(self):
        for e in reg.load():
            d = tm.task_directive(e, {"aoi": "current canvas extent"})
            self.assertLess(len(d), 500, "%s directive too long" % e["id"])

    def test_directive_names_the_task_and_the_deliverable(self):
        e = reg.by_id("14.01")
        d = tm.task_directive(e)
        self.assertIn("14.01", d)
        self.assertIn("Deliver:", d)

    def test_no_task_gives_no_directive(self):
        self.assertEqual(tm.task_directive(None), "")


if __name__ == "__main__":
    unittest.main()


class TestSlotContextFromTheOpenProject(unittest.TestCase):
    """QGIS already knows some of what the register would otherwise ask for."""

    def test_a_project_with_layers_answers_the_area_question(self):
        ctx = tm.slot_context_from_map({"layers": [{"name": "admin2"}],
                                        "active_layer": "admin2"})
        self.assertIn("aoi", ctx)
        self.assertIn("admin2", ctx["aoi"])

    def test_an_empty_project_answers_nothing(self):
        self.assertEqual(tm.slot_context_from_map({"layers": []}), {})
        self.assertEqual(tm.slot_context_from_map({}), {})

    def test_a_non_dict_never_raises(self):
        self.assertEqual(tm.slot_context_from_map(None), {})
        self.assertEqual(tm.slot_context_from_map("layers"), {})

    def test_the_string_none_active_layer_is_not_reported_as_a_layer_name(self):
        ctx = tm.slot_context_from_map({"layers": [{"name": "x"}], "active_layer": "None"})
        self.assertNotIn("None", ctx["aoi"])


class TestSlotsAreAnswerable(unittest.TestCase):
    def setUp(self):
        self.data = reg.load()

    def test_a_statistical_distribution_never_asks_which_facility(self):
        """'Map population distribution' asked "which facility or service
        type?" -- an unanswerable question, because the word `distribution`
        matched the distribution-POINT vocabulary. A distribution point is
        still a facility, so the two senses have to stay separated."""
        for tid in ("3.01", "3.18", "7.14", "7.20", "25b.05"):
            e = reg.by_id(tid)
            self.assertIsNotNone(e, tid)
            self.assertNotIn("facility_type", e["slots"], "%s: %s" % (tid, e["text"]))

    def test_a_real_distribution_point_task_still_asks(self):
        e = reg.by_id("24.05")
        self.assertIsNotNone(e)
        self.assertIn("facility_type", e["slots"], e["text"])

    def test_most_requests_are_not_blocked_once_a_project_is_open(self):
        """The gate exists to catch the genuinely unanswerable, not to
        interrogate. With a project open, a request phrased as the task's own
        title should get through unblocked in the large majority of cases."""
        ctx = {"aoi": "the current canvas extent"}
        blocked = sum(1 for e in self.data
                      if tm.unresolvable(tm.missing_slots(e, e["text"], ctx)))
        self.assertLess(blocked, len(self.data) * 0.15,
                        "%d of %d tasks would stop and ask" % (blocked, len(self.data)))


class TestEveryContractIsCoherent(unittest.TestCase):
    """Sweeps all 792 contracts rather than the handful anyone reads by hand.

    Written after an audit of the full set found ten tasks promising a file
    their contract does not write. Hand-inspecting a few dozen entries out of
    792 is not coverage; this is.
    """

    def setUp(self):
        self.data = reg.load()

    def test_every_file_producing_contract_has_a_renderer(self):
        for e in self.data:
            if e["out"] in ("layer", "guidance"):
                continue
            c = tm.output_contract(e)
            self.assertTrue(c["render"], "%s (%s) has no renderer" % (e["id"], e["out"]))

    def test_the_writer_for_a_produced_file_is_in_the_render_chain(self):
        from cartogen_ai.core.agent import file_io
        for e in self.data:
            w = file_io.writer_for(e["out"])
            if not e["prod"] or not w:
                continue
            self.assertIn(w, tm.output_contract(e)["render"], e["id"])

    def test_a_guidance_task_never_promises_a_file(self):
        for e in self.data:
            if e["out"] == "guidance":
                self.assertEqual(e["prod"], [], "%s: %s" % (e["id"], e["text"]))

    def test_every_non_guidance_task_can_take_some_file(self):
        for e in self.data:
            if e["out"] != "guidance":
                self.assertTrue(e["acc"], "%s takes no file at all" % e["id"])

    def test_no_directive_is_too_long_to_ride_alongside_the_system_prompt(self):
        for e in self.data:
            d = tm.task_directive(e, {}, e["text"])
            self.assertLess(len(d), 600, "%s directive is %d chars" % (e["id"], len(d)))

    def test_the_matcher_still_finds_every_task_from_its_own_title(self):
        """Self-retrieval. Not a claim about real user phrasing -- it is the
        floor: a task the matcher cannot find from its own words is
        unreachable by anything."""
        missed = [e["id"] for e in self.data
                  if e["id"] not in [m[0]["id"] for m in tm.match(e["text"])]]
        self.assertEqual(missed, [], "unreachable tasks: %s" % missed[:10])


class TestFacilityAccessToolHint(unittest.TestCase):
    """rc11 smoke test (#122): the 7.23 preview listed travel_time_matrix (44 min on 3,369 facilities) and not the fast tool."""

    def test_every_task_that_names_the_matrix_names_the_fast_classifier_first(self):
        import json
        import os
        import cartogen_ai.core.agent.task_register as reg
        data = json.load(open(os.path.join(os.path.dirname(reg.__file__), "task_register.json"), encoding="utf-8"))
        checked = 0
        for task in data:
            if "travel_time_matrix" in task["tools"]:
                checked += 1
                self.assertIn("classify_facilities_by_access", task["tools"], task["id"])
                self.assertLess(task["tools"].index("classify_facilities_by_access"),
                                task["tools"].index("travel_time_matrix"), task["id"])
        self.assertGreater(checked, 0)


class TestNonRequestFragments(unittest.TestCase):
    """rc11 smoke test (#130): a pasted fragment reached an analysis task and the user's 'yes' ran it."""

    def test_fragments_without_an_action_word_get_no_task(self):
        for text in ("template: access_map", "threshold = 5 km", "ok thanks", "the origin point"):
            verdict = tm.classify(text)
            self.assertIsNone(verdict["best"], text)
            self.assertEqual(verdict["reason"], "too short to be a request", text)

    def test_real_short_requests_still_match(self):
        for text in ("map health facilities in Aleppo", "Show roads in Sanaa", "Which facilities are beyond one hour?"):
            self.assertNotEqual(tm.classify(text)["reason"], "too short to be a request", text)
