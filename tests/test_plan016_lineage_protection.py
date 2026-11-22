"""PLAN-016 item 2, offline: a layer made from a protected layer is protected through lineage, for the export gate as for the cloud gate."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent import protection
from cartogen_ai.core.agent.tools.layout_export_checks import protected_in, protected_preview, publication_problems


class FakeLayer:
    def __init__(self, name, level=None, sources=(), source_ids=(), reason=None):
        self._name, self.level, self.reason = name, level, reason
        self.lineage = [{"tool": "merge", "sources": list(sources), "source_ids": list(source_ids)}] if (sources or source_ids) else []

    def name(self):
        return self._name

    def id(self):
        return "id_" + self._name


def run(layers, target):
    """protected_in([target]) with the sensitivity and lineage of the fake layers."""
    by_obj = {id(layer): layer for layer in layers}
    with patch.object(protection.sensitivity, "get_layer_sensitivity", lambda lyr: {"level": by_obj[id(lyr)].level, "reason": by_obj[id(lyr)].reason}), \
            patch.object(protection, "get_layer_lineage", lambda lyr: by_obj[id(lyr)].lineage):
        return protected_in([target], layers)


class TestInheritedProtection(unittest.TestCase):
    def test_an_own_tag_is_reported_as_before(self):
        a = FakeLayer("a", "SENSITIVE", reason="GBV")
        found = run([a], a)
        self.assertEqual((found[0]["level"], found[0]["reason"], found[0]["derived_from"]), ("SENSITIVE", "GBV", None))

    def test_a_merged_copy_of_a_sensitive_layer_is_protected(self):
        src = FakeLayer("smoke_points", "SENSITIVE")
        out = FakeLayer("merged_test", sources=["smoke_points"])
        found = run([src, out], out)
        self.assertEqual((found[0]["layer"], found[0]["level"], found[0]["derived_from"]), ("merged_test", "SENSITIVE", "smoke_points"))

    def test_a_rename_of_the_source_does_not_hide_it(self):
        src = FakeLayer("renamed_source", "RESTRICTED")
        out = FakeLayer("out", sources=["old_name"], source_ids=["id_renamed_source"])
        self.assertEqual(run([src, out], out)[0]["level"], "RESTRICTED")

    def test_two_hops_and_the_original_is_named(self):
        a = FakeLayer("a", "SENSITIVE")
        b = FakeLayer("b", sources=["a"])
        c = FakeLayer("harmless_name", sources=["b"])
        found = run([a, b, c], c)
        self.assertEqual(found[0]["derived_from"], "a")
        self.assertIn("derived from 'b'", found[0]["reason"])

    def test_an_explicit_public_tag_wins_over_a_protected_source(self):
        src = FakeLayer("src", "SENSITIVE")
        out = FakeLayer("aggregated", "PUBLIC", sources=["src"])
        self.assertEqual(run([src, out], out), [])

    def test_an_unrelated_layer_and_an_unprotected_source_stay_open(self):
        open_src = FakeLayer("open", "INTERNAL")
        out = FakeLayer("out", sources=["open"])
        other = FakeLayer("other")
        self.assertEqual(run([open_src, out, other], out), [])
        self.assertEqual(run([open_src, out, other], other), [])

    def test_a_lineage_cycle_ends(self):
        a = FakeLayer("a", sources=["b"])
        b = FakeLayer("b", sources=["a"])
        self.assertEqual(run([a, b], a), [])

    def test_a_same_named_protected_twin_counts_for_the_source(self):
        twin = FakeLayer("src", "SENSITIVE")
        open_twin = FakeLayer("src")
        out = FakeLayer("out", sources=["src"])
        self.assertEqual(run([open_twin, twin, out], out)[0]["level"], "SENSITIVE")


class TestWording(unittest.TestCase):
    def test_the_confirm_card_and_publication_problem_name_the_source(self):
        protected = [{"layer": "harmless_name", "level": "SENSITIVE", "reason": "derived from 'smoke_points' (tagged SENSITIVE)", "derived_from": "smoke_points"}]
        card = protected_preview("export_layout", {}, protected)
        self.assertIn("'harmless_name' (SENSITIVE, derived from 'smoke_points')", card["rationale"])
        self.assertIn("derived from 'smoke_points'", publication_problems([], protected)[0])

    def test_the_dialog_label_says_where_the_protection_comes_from(self):
        self.assertEqual(protection.sensitivity_label(None, None, None), "Current: untagged")
        self.assertEqual(protection.sensitivity_label("SENSITIVE", "test", None), "Current: SENSITIVE (test)")
        self.assertEqual(protection.sensitivity_label("SENSITIVE", None, "smoke_points"),
                         "Current: untagged, protected through lineage from 'smoke_points' (SENSITIVE)")


class TestUnreadableProtectionFailsClosed(unittest.TestCase):
    """Owner decision 2026-11-22 (DEF-8 review): a layer whose tag or lineage cannot be read is treated as protected, not as untagged, for every gate
    that asks effective_sensitivity (geocoding, export, the model's view)."""

    def test_a_lineage_that_cannot_be_read_makes_an_untagged_layer_sensitive_and_is_logged(self):
        layer = FakeLayer("derived_copy")
        with patch.object(protection.sensitivity, "get_layer_sensitivity", lambda lyr: {"level": None, "reason": None}), \
                patch.object(protection, "get_layer_lineage", side_effect=RuntimeError("boom")), \
                patch.object(protection, "log_event") as log:
            record = protection.effective_sensitivity(layer, [layer])
        self.assertEqual(record["level"], "SENSITIVE")
        self.assertIn("could not be read", record["reason"])
        self.assertEqual(log.call_args.args[0], "lineage_read_failed")
        self.assertEqual(log.call_args.kwargs["error_class"], "RuntimeError")

    def test_the_export_gate_therefore_asks_about_such_a_layer(self):
        layer = FakeLayer("derived_copy")
        with patch.object(protection.sensitivity, "get_layer_sensitivity", lambda lyr: {"level": None, "reason": None}), \
                patch.object(protection, "get_layer_lineage", side_effect=RuntimeError("boom")), patch.object(protection, "log_event"):
            found = protected_in([layer], [layer])
        self.assertEqual([(f["layer"], f["level"]) for f in found], [("derived_copy", "SENSITIVE")])

    def test_a_tag_read_that_raises_counts_as_sensitive_too(self):
        layer = FakeLayer("a")
        with patch.object(protection.sensitivity, "get_layer_sensitivity", side_effect=RuntimeError("boom")), patch.object(protection, "log_event") as log:
            self.assertEqual(protection.effective_sensitivity(layer, [layer])["level"], "SENSITIVE")
        self.assertEqual(log.call_args.args[0], "sensitivity_read_failed")

    def test_a_plain_untagged_layer_with_no_lineage_is_still_untagged(self):
        layer = FakeLayer("plain")
        self.assertEqual(run([layer], layer), [])

    def test_the_returned_default_cannot_be_changed_by_a_caller(self):
        layer = FakeLayer("a")
        with patch.object(protection.sensitivity, "get_layer_sensitivity", side_effect=RuntimeError("boom")), patch.object(protection, "log_event"):
            protection.effective_sensitivity(layer, [layer])["level"] = "PUBLIC"
            self.assertEqual(protection.effective_sensitivity(layer, [layer])["level"], "SENSITIVE")


if __name__ == "__main__":
    unittest.main()
