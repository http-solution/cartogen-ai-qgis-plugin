"""Fixes from the rc18 hand test (2026-10-06): polite confirmations, 'report' as a verb, raster named in the request, named tool first,
a bbox that comes from the layer and not from memory, and the checkpoint download that cannot 416."""
import io
import os
import tempfile
import unittest

from cartogen_ai.core.agent import task_matcher as tm
from cartogen_ai.core.agent.tools import imagery_extraction as ie
from cartogen_ai.core.agent.tools.vector_tools import bbox_orders
from cartogen_ai.core.ui import reply_vocab as rv

LAYERS = ["smoke_image", "smoke_dem", "smoke_points", "smoke_hubs", "smoke_admin", "smoke_zones", "smoke_boundary"]
R3 = ("Run extract_features_from_imagery on loaded raster smoke_image with confidence threshold 0.4. Report the model used and actual "
      "detection count; do not label synthetic shapes as real buildings.")


class TestPoliteConfirmations(unittest.TestCase):
    def test_everyday_yes_phrases_confirm_a_router_card(self):
        for t in ("Yes, proceed.", "Yes please", "ok go ahead", "sure, run it", "Do it!", "Sounds good, go ahead", "yes please send"):
            self.assertEqual(rv.router_reply(t), "confirm", t)

    def test_a_yes_with_changes_is_still_an_edit(self):
        for t in ("Yes but use the roads layer", "yes, buffer 500 m instead", "go to the north", "ok but only the clinics"):
            self.assertIsNone(rv.router_reply(t), t)

    def test_destructive_gates_stay_strict(self):
        for t in ("Yes, proceed.", "yes please", "ok", "sure"):
            self.assertIsNone(rv.gate_reply(t), t)
        self.assertEqual(rv.gate_reply("Apply"), "confirm")

    def test_cancel_is_unchanged(self):
        self.assertEqual(rv.router_reply("no"), "cancel")
        self.assertEqual(rv.router_reply("cancel"), "cancel")


class TestTaskMatcherRc18(unittest.TestCase):
    def test_report_as_a_verb_is_not_a_report_deliverable(self):
        self.assertNotEqual(tm.output_override(R3), "report")
        self.assertNotEqual(tm.output_override("Add the result to the project and report the actual feature count."), "report")

    def test_report_as_a_noun_still_is(self):
        for q in ("Write a report on flood exposure", "Make a situation report", "generate a spatial report", "report on the damage"):
            self.assertEqual(tm.output_override(q), "report", q)

    def test_a_named_raster_answers_the_imagery_question(self):
        entry = tm.classify(R3)["best"]
        self.assertNotIn("imagery", tm.missing_slots(entry, R3, None, LAYERS))
        self.assertNotIn("imagery", tm.defaults(tm.missing_slots(entry, R3, None, LAYERS)))

    def test_the_named_tool_leads_the_chain(self):
        entry = tm.classify(R3)["best"]
        directive = tm.task_directive(entry, None, R3)
        chain = directive.split("in order: ")[1].split(".")[0].split(", ")
        self.assertEqual(chain[0], "extract_features_from_imagery")


class TestBboxOrders(unittest.TestCase):
    def test_both_orders_are_named_and_consistent(self):
        b = bbox_orders(35.9141156995706, 31.9401917668625, 35.9508951918742, 31.9698086420047)
        self.assertEqual(b["bbox_south_west_north_east"], [31.940192, 35.914116, 31.969809, 35.950895])
        self.assertEqual(b["bbox_west_south_east_north"], [35.914116, 31.940192, 35.950895, 31.969809])


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestCheckpointDownload(unittest.TestCase):
    def test_a_complete_download_is_renamed_into_place(self):
        d = tempfile.mkdtemp()
        seen = []

        def opener(req, timeout):
            seen.append(dict(req.header_items()))
            return _Resp(b"x" * 200)
        path = ie.download_checkpoint("m.pt", d, opener=opener, min_bytes=100)
        self.assertEqual(os.path.basename(path), "m.pt")
        self.assertEqual(sorted(os.listdir(d)), ["m.pt"])
        self.assertTrue(all("Range" not in h for h in seen), "a Range header is what earns HTTP 416")

    def test_a_short_file_is_rejected_and_nothing_is_left_behind(self):
        d = tempfile.mkdtemp()
        with self.assertRaises(Exception):
            ie.download_checkpoint("m.pt", d, opener=lambda r, timeout: _Resp(b"x" * 10), min_bytes=100)
        self.assertEqual(os.listdir(d), [])

    def test_the_second_url_is_tried_when_the_first_fails(self):
        d = tempfile.mkdtemp()
        calls = []

        def opener(req, timeout):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise OSError("boom")
            return _Resp(b"x" * 200)
        ie.download_checkpoint("m.pt", d, opener=opener, min_bytes=100, urls=("https://a/{name}", "https://b/{name}"))
        self.assertEqual(calls, ["https://a/m.pt", "https://b/m.pt"])


if __name__ == "__main__":
    unittest.main()


class TestUrlsAreNotMistakenForFilePaths(unittest.TestCase):
    def test_a_thumbnail_url_in_a_table_cell_stays_a_web_link(self):
        from cartogen_ai.core.ui import chat_formatting as cf
        html = cf.render_markdown("| Scene | Preview |\n|---|---|\n| S2B | [Preview Image](https://cogs.example.com/x/y/preview.jpg) |")
        self.assertIn('<a href="https://cogs.example.com/x/y/preview.jpg">Preview Image</a>', html)
        self.assertNotIn("file:///", html)

    def test_a_real_windows_path_is_still_linked(self):
        from cartogen_ai.core.ui import chat_formatting as cf
        self.assertIn('file:///C:/Users/a/out/map.pdf', cf.render_markdown("Saved to C:\\Users\\a\\out\\map.pdf"))
