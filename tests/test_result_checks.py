"""PLAN-031 (verified result gate), step 1: each check returns fail for a deliberately wrong input and pass for a correct one, and three of the
historical silent wrong answers are reproduced as inputs the gate flags (not only the fix that removed them)."""
import unittest

from cartogen_ai.core.validators import result_checks as rc


def summary(**kw):
    base = {"name": "out", "crs_authid": "EPSG:32638", "crs_geographic": False, "feature_count": 10, "input_feature_count": 10,
            "geometry": {"total": 10, "invalid": 0, "empty": 0}, "fields": {}}
    base.update(kw)
    return base


def field(count=10, null=0, distinct=10, low=0.0, high=1.0, fingerprint="a"):
    return {"count": count, "null": null, "distinct": distinct, "min": low, "max": high, "fingerprint": fingerprint}


def status_of(checks, check_id):
    return next(c["status"] for c in checks if c["id"] == check_id)


class TestEachCheck(unittest.TestCase):
    def test_crs_fails_on_a_geographic_layer_only_when_a_distance_was_used(self):
        wrong = rc.run_checks(summary(crs_authid="EPSG:4326", crs_geographic=True), {"distance_based": True})
        self.assertEqual(status_of(wrong, "crs"), rc.FAIL)
        self.assertIn("degrees", next(c["detail"] for c in wrong if c["id"] == "crs"))
        self.assertEqual(status_of(rc.run_checks(summary(), {"distance_based": True}), "crs"), rc.PASS)
        self.assertEqual(status_of(rc.run_checks(summary(crs_geographic=None), {"distance_based": True}), "crs"), rc.WARN)
        self.assertNotIn("crs", [c["id"] for c in rc.run_checks(summary(crs_geographic=True), {})])

    def test_geometry_warns_then_fails_as_the_share_grows(self):
        ok = rc.run_checks(summary(), {})
        some = rc.run_checks(summary(geometry={"total": 100, "invalid": 3, "empty": 0}), {})
        many = rc.run_checks(summary(geometry={"total": 100, "invalid": 4, "empty": 3}), {})
        self.assertEqual([status_of(x, "geometry") for x in (ok, some, many)], [rc.PASS, rc.WARN, rc.FAIL])

    def test_a_field_that_is_empty_or_constant_fails(self):
        context = {"written_fields": {"sev": "score_0_1"}}
        good = rc.run_checks(summary(fields={"sev": field()}), context)
        empty = rc.run_checks(summary(fields={"sev": field(count=0, null=10, distinct=0, low=None, high=None)}), context)
        constant = rc.run_checks(summary(fields={"sev": field(distinct=1, low=0.5, high=0.5)}), context)
        missing = rc.run_checks(summary(fields={}), context)
        self.assertEqual([status_of(x, "field:sev") for x in (good, empty, constant, missing)], [rc.PASS, rc.FAIL, rc.FAIL, rc.FAIL])

    def test_a_constant_on_two_features_means_nothing(self):
        checks = rc.run_checks(summary(feature_count=2, input_feature_count=2, geometry=None, fields={"sev": field(count=2, distinct=1)}),
                               {"written_fields": {"sev": "score_0_1"}})
        self.assertEqual(status_of(checks, "field:sev"), rc.PASS)

    def test_some_nulls_warn(self):
        checks = rc.run_checks(summary(fields={"sev": field(count=7, null=3)}), {"written_fields": {"sev": "count"}})
        self.assertEqual(status_of(checks, "field:sev"), rc.WARN)

    def test_value_ranges_by_unit(self):
        for kind, low, high, expected in (("percent", 0, 100, rc.PASS), ("percent", 0, 140, rc.FAIL), ("fraction", 0, 1, rc.PASS),
                                          ("fraction", -0.2, 0.9, rc.FAIL), ("count", 0, 500, rc.PASS), ("count", -3, 5, rc.FAIL),
                                          ("hours", 0, 6.5, rc.PASS), ("hours", 0, 4000, rc.FAIL), ("distance_m", 0, 1e6, rc.PASS)):
            checks = rc.run_checks(summary(fields={"x": field(low=low, high=high)}), {"written_fields": {"x": kind}})
            self.assertEqual(status_of(checks, "range:x"), expected, (kind, low, high))

    def test_an_unknown_unit_or_missing_min_max_is_skipped_not_passed(self):
        self.assertNotIn("range:x", [c["id"] for c in rc.run_checks(summary(fields={"x": field()}), {"written_fields": {"x": "furlongs"}})])
        self.assertNotIn("range:x", [c["id"] for c in rc.run_checks(summary(fields={"x": field(low=None, high=None)}),
                                                                      {"written_fields": {"x": "percent"}})])

    def test_stale_fields(self):
        context = {"written_fields": {"sev": "score_0_1"}, "previous_fingerprints": {"sev": "same"}}
        same = rc.run_checks(summary(fields={"sev": field(fingerprint="same")}), context)
        changed = rc.run_checks(summary(fields={"sev": field(fingerprint="new")}), context)
        self.assertEqual(status_of(same, "stale:sev"), rc.FAIL)
        self.assertEqual(status_of(changed, "stale:sev"), rc.PASS)
        self.assertNotIn("stale:sev", [c["id"] for c in rc.run_checks(summary(fields={"sev": field()}), {"written_fields": {"sev": "count"}})])

    def test_feature_count(self):
        self.assertEqual(status_of(rc.run_checks(summary(feature_count=0, geometry=None), {}), "feature_count"), rc.FAIL)
        self.assertEqual(status_of(rc.run_checks(summary(feature_count=8), {"one_to_one": True}), "feature_count"), rc.FAIL)
        self.assertEqual(status_of(rc.run_checks(summary(feature_count=8), {"one_to_one": False}), "feature_count"), rc.PASS)
        self.assertEqual(status_of(rc.run_checks(summary(), {"one_to_one": True}), "feature_count"), rc.PASS)

    def test_a_missing_summary_key_is_a_skip(self):
        checks = rc.run_checks({"name": "x"}, {"distance_based": True, "one_to_one": True, "written_fields": {}})
        self.assertEqual([c["id"] for c in checks], ["crs"])      # only the CRS check can say anything, and it says "not known"
        self.assertEqual(checks[0]["status"], rc.WARN)

    def test_summarize_names_the_failures(self):
        checks = [{"id": "a", "status": rc.PASS, "detail": ""}, {"id": "b", "status": rc.WARN, "detail": ""}, {"id": "c", "status": rc.FAIL, "detail": ""}]
        self.assertEqual(rc.summarize(checks), ("1 passed, 1 warning, 1 failed: c", ["c"]))
        self.assertEqual(rc.summarize([]), ("0 passed, 0 warnings, 0 failed", []))


class TestHistoricalWrongAnswersAreFlagged(unittest.TestCase):
    """PLAN-026 classes A, B, C as the inputs a tool would have produced, reproduced as what the gate must flag."""

    def test_class_a_a_buffer_in_degrees(self):
        """C9: the route-risk buffer took 1000 in the layer's own units on EPSG:4326."""
        checks = rc.run_checks(summary(crs_authid="EPSG:4326", crs_geographic=True), {"distance_based": True})
        self.assertEqual(status_of(checks, "crs"), rc.FAIL)

    def test_class_b_a_signed_difference_read_as_a_score(self):
        """D7: the damage score came from a signed change raster; a 0-to-1 score with negative values is that mistake."""
        checks = rc.run_checks(summary(fields={"dmg": field(low=-0.62, high=0.91)}), {"written_fields": {"dmg": "score_0_1"}})
        self.assertEqual(status_of(checks, "range:dmg"), rc.FAIL)

    def test_class_c_an_old_column_read_as_this_runs_result(self):
        """The damage tool read chg_mean from an earlier run on the second call."""
        checks = rc.run_checks(summary(fields={"chg_mean": field(fingerprint="run1")}),
                               {"written_fields": {"chg_mean": "score_0_1"}, "previous_fingerprints": {"chg_mean": "run1"}})
        self.assertEqual(status_of(checks, "stale:chg_mean"), rc.FAIL)


if __name__ == "__main__":
    unittest.main()
