# -*- coding: utf-8 -*-
"""Pure rules behind isolated-script result adoption (GitHub #145, #146; audit F09, F10)."""
import os
import tempfile
import unittest

from cartogen_ai.core.agent.services import script_isolation as si


class TestSourceIsUnder(unittest.TestCase):
    def test_a_file_inside_the_scratch_directory(self):
        d = tempfile.mkdtemp()
        self.assertTrue(si.source_is_under(os.path.join(d, "out_x.gpkg"), d))
        self.assertTrue(si.source_is_under(os.path.join(d, "out_x.gpkg") + "|layername=out_x", d))

    def test_a_file_elsewhere_or_a_sibling_with_the_same_prefix_is_not(self):
        d = tempfile.mkdtemp()
        self.assertFalse(si.source_is_under(os.path.join(os.path.dirname(d), "other", "a.gpkg"), d))
        self.assertFalse(si.source_is_under(d + "_sibling" + os.sep + "a.gpkg", d))

    def test_empty_inputs(self):
        self.assertFalse(si.source_is_under("", "/tmp"))
        self.assertFalse(si.source_is_under("/tmp/a", ""))


class TestContentSignature(unittest.TestCase):
    def test_an_attribute_change_with_the_same_count_is_a_difference(self):
        a = si.content_signature(["id", "v"], [([1, 1], "aa"), ([2, 5], "bb")])
        b = si.content_signature(["id", "v"], [([1, 99], "aa"), ([2, 5], "bb")])
        self.assertNotEqual(a, b)

    def test_a_geometry_change_with_the_same_count_is_a_difference(self):
        a = si.content_signature(["id"], [([1], "aa")])
        b = si.content_signature(["id"], [([1], "cc")])
        self.assertNotEqual(a, b)

    def test_a_schema_change_is_a_difference(self):
        self.assertNotEqual(si.content_signature(["id"], []), si.content_signature(["id", "extra"], []))

    def test_row_order_and_null_spellings_do_not_matter(self):
        a = si.content_signature(["id", "v"], [([1, None], "aa"), ([2, 5], "bb")])
        b = si.content_signature(["id", "v"], [([2, 5], "bb"), ([1, "NULL"], "aa")])
        self.assertEqual(a, b)

    def test_floats_that_differ_only_below_nine_decimals_are_the_same(self):
        a = si.content_signature(["v"], [([1.0000000001], "")])
        b = si.content_signature(["v"], [([1.0], "")])
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
