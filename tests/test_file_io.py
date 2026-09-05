# -*- coding: utf-8 -*-
"""Tests for the file-input/file-output half of the task register.

The point of these is that the register cannot advertise a capability the
plugin does not have. Every reader and writer named in agent/file_io.py is
checked against the live TOOL_REGISTRY, and the committed register is checked
against a fresh run of tools/derive_task_io.py -- so a rule change that is not
regenerated, or a tool that is renamed out from under the table, fails here
rather than at the user.
"""
import importlib.util
import json
import os
import unittest

from cartogen_ai.core.agent import file_io
from cartogen_ai.core.agent import task_register as reg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_deriver():
    spec = importlib.util.spec_from_file_location(
        "derive_task_io", os.path.join(ROOT, "tools", "derive_task_io.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestClassify(unittest.TestCase):
    def test_the_three_kinds_the_user_names_explicitly(self):
        self.assertEqual(file_io.classify("/x/sitrep.pdf"), "pdf")
        self.assertEqual(file_io.classify("/x/photo.JPG"), "image")
        self.assertEqual(file_io.classify("/x/notes.txt"), "txt")

    def test_geotiff_resolves_to_raster_not_image(self):
        # A GeoTIFF sent down the picture path loses its georeferencing.
        self.assertEqual(file_io.classify("/x/scene.tif"), "raster")
        self.assertEqual(file_io.classify("/x/scene.TIFF"), "raster")

    def test_unknown_and_empty_are_none(self):
        self.assertIsNone(file_io.classify("/x/thing.zzz"))
        self.assertIsNone(file_io.classify("/x/noext"))
        self.assertIsNone(file_io.classify(""))
        self.assertIsNone(file_io.classify(None))

    def test_every_extension_belongs_to_exactly_one_kind_except_tif(self):
        seen = {}
        for kind, exts in file_io.MEDIA.items():
            for e in exts:
                seen.setdefault(e, []).append(kind)
        overlapping = {e: k for e, k in seen.items() if len(k) > 1}
        self.assertEqual(overlapping, {}, "unexpected overlap: %s" % overlapping)


class TestReadersAreReal(unittest.TestCase):
    def test_every_reader_is_a_registered_tool(self):
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        for kind, tool in file_io.READERS.items():
            if tool is None:
                continue
            self.assertIn(tool, TOOL_REGISTRY, "%s reader %s is not registered" % (kind, tool))

    def test_every_specialised_reader_is_a_registered_tool(self):
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        for key, tool in file_io.SPECIALISED_READERS.items():
            self.assertIn(tool, TOOL_REGISTRY, "%s -> %s is not registered" % (key, tool))

    def test_every_writer_is_a_registered_tool(self):
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        for kind, (_exts, writer) in file_io.ARTIFACTS.items():
            if writer is None:
                continue
            self.assertIn(writer, TOOL_REGISTRY, "%s writer %s is not registered" % (kind, writer))

    def test_every_chart_tool_is_a_registered_tool(self):
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        for t in file_io.CHART_TOOLS:
            self.assertIn(t, TOOL_REGISTRY, t)

    def test_every_media_kind_has_a_reader_entry_and_an_effect_line(self):
        for kind in file_io.MEDIA:
            self.assertIn(kind, file_io.READERS, kind)
            self.assertIn(kind, file_io.READER_EFFECT, kind)

    def test_every_output_contract_has_an_artifact_rule(self):
        for kind in reg.OUTPUTS:
            self.assertIn(kind, file_io.ARTIFACTS, kind)


class TestSpecialisedRouting(unittest.TestCase):
    def test_a_spreadsheet_on_a_3w_task_goes_to_the_3w_reader(self):
        self.assertEqual(file_io.reader_for("table", "Map 3W operational presence"),
                         "load_3w_data")

    def test_a_spreadsheet_on_any_other_task_goes_to_the_generic_reader(self):
        self.assertEqual(file_io.reader_for("table", "Map health facilities"),
                         "load_tabular_data_as_layer")

    def test_a_picture_on_a_damage_task_goes_to_segmentation(self):
        self.assertEqual(file_io.reader_for("image", "Map damaged buildings"),
                         "extract_features_from_imagery")

    def test_a_picture_on_a_plain_task_is_georeferenced(self):
        self.assertEqual(file_io.reader_for("image", "Map village locations"),
                         "georeference_image")

    def test_txt_needs_no_tool(self):
        self.assertIsNone(file_io.reader_for("txt", "anything"))

    def test_describe_attachment_names_the_file_the_kind_and_the_tool(self):
        line = file_io.describe_attachment("/x/sitrep.pdf", "Produce situation maps")
        self.assertIn("sitrep.pdf", line)
        self.assertIn("pdf", line)
        self.assertIn("extract_pdf_tables", line)

    def test_describe_attachment_is_none_for_a_file_we_cannot_place(self):
        self.assertIsNone(file_io.describe_attachment("/x/archive.7z"))


class TestArtifacts(unittest.TestCase):
    def test_layout_promises_pdf_and_png(self):
        self.assertEqual(file_io.artifacts_for("layout"), [".pdf", ".png"])

    def test_dashboard_promises_html(self):
        self.assertEqual(file_io.artifacts_for("dashboard"), [".html"])

    def test_a_chart_tool_adds_a_png_without_duplicating_one(self):
        self.assertEqual(file_io.artifacts_for("report", ["generate_chart"]), [".md", ".png"])
        self.assertEqual(file_io.artifacts_for("layout", ["generate_chart"]), [".pdf", ".png"])

    def test_layer_and_guidance_write_no_file(self):
        self.assertEqual(file_io.artifacts_for("layer"), [])
        self.assertEqual(file_io.artifacts_for("guidance"), [])

    def test_a_map_task_that_also_draws_a_chart_promises_the_png(self):
        self.assertEqual(file_io.artifacts_for("layer", ["generate_chart"]), [".png"])

    def test_guidance_never_promises_a_file_even_with_a_chart_tool(self):
        # A few guidance tasks carry generate_chart in their suggested chain.
        # That is a mis-assignment in the chain, not a promise of a PNG.
        self.assertEqual(file_io.artifacts_for("guidance", ["generate_chart"]), [])

    def test_sentences_read_as_english(self):
        self.assertEqual(file_io.artifact_sentence("dashboard"), "an HTML file")
        self.assertEqual(file_io.artifact_sentence("analysis"), "a CSV file")
        self.assertEqual(file_io.artifact_sentence("layout"), "PDF, PNG files")
        self.assertIn("canvas", file_io.artifact_sentence("layer"))
        self.assertIn("no file", file_io.artifact_sentence("guidance"))


class TestRegisterFileFieldsAreDerivedAndCurrent(unittest.TestCase):
    def setUp(self):
        self.data = reg.load()

    def test_every_task_declares_both_fields(self):
        for e in self.data:
            self.assertIn("acc", e, e["id"])
            self.assertIn("prod", e, e["id"])

    def test_every_accepted_kind_is_a_real_media_kind(self):
        for e in self.data:
            for k in e["acc"]:
                self.assertIn(k, file_io.MEDIA, "%s accepts unknown kind %s" % (e["id"], k))

    def test_every_accepted_kind_has_a_way_to_be_read(self):
        for e in self.data:
            for k in e["acc"]:
                self.assertIn(k, file_io.READERS, "%s: nothing reads %s" % (e["id"], k))

    def test_produced_extensions_match_the_contract(self):
        for e in self.data:
            self.assertEqual(e["prod"], file_io.artifacts_for(e["out"], e["tools"]), e["id"])

    def test_guidance_tasks_never_claim_to_take_a_layer_file(self):
        for e in self.data:
            if e["out"] == "guidance":
                self.assertNotIn("vector", e["acc"], e["id"])
                self.assertNotIn("raster", e["acc"], e["id"])

    def test_pdf_docx_and_txt_are_offered_together_or_not_at_all(self):
        for e in self.data:
            doc = {k for k in ("pdf", "docx", "txt") if k in e["acc"]}
            self.assertIn(len(doc), (0, 3), "%s offers only %s" % (e["id"], sorted(doc)))

    def test_the_committed_register_matches_a_fresh_derivation(self):
        """tools/derive_task_io.py is the only source of acc/prod. If someone
        edits the rules and forgets to regenerate, this is where it shows."""
        deriver = _load_deriver()
        with open(deriver.REGISTER, encoding="utf-8") as fh:
            committed = json.load(fh)
        self.assertEqual(committed, deriver.derive(committed))


if __name__ == "__main__":
    unittest.main()
