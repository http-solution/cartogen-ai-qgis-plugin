# -*- coding: utf-8 -*-
"""Tests for the pure-Python half of ui/icons.py -- icon_svg()'s color substitution and template
lookup. themed_icon() (QSvgRenderer/QPainter rasterization) needs a live QGIS process and is
covered by the live-QGIS verification for the UI/chat redesign workstream instead (2026-09-12);
see docs/RELEASE_SMOKE_TEST.md's Run log."""
import unittest
from cartogen_ai.core.ui.icons import icon_svg, _ICON_TEMPLATES


class TestIconSvg(unittest.TestCase):
    def test_unknown_icon_name_raises_clear_error(self):
        with self.assertRaises(ValueError) as ctx:
            icon_svg("bogus", "#000000")
        self.assertIn("bogus", str(ctx.exception))
        self.assertIn("attach", str(ctx.exception))  # names the known icons

    def test_every_known_icon_produces_well_formed_svg(self):
        for name in _ICON_TEMPLATES:
            svg = icon_svg(name, "#123456")
            self.assertTrue(svg.startswith("<svg "), f"{name}: doesn't start with <svg")
            self.assertTrue(svg.endswith("</svg>"), f"{name}: doesn't end with </svg>")
            self.assertIn('viewBox="0 0 24 24"', svg)
            self.assertIn("#123456", svg)  # the requested color actually made it in

    def test_color_is_the_only_thing_that_changes_between_calls(self):
        red = icon_svg("send", "#ff0000")
        blue = icon_svg("send", "#0000ff")
        self.assertNotEqual(red, blue)
        self.assertEqual(red.replace("#ff0000", "X"), blue.replace("#0000ff", "X"))

    def test_no_leftover_template_placeholder(self):
        # {color} must be fully substituted -- a leftover literal "{color}" would mean a
        # template's .format() call missed an occurrence (e.g. the settings icon's 3 repeated
        # substitutions).
        for name in _ICON_TEMPLATES:
            svg = icon_svg(name, "#abcdef")
            self.assertNotIn("{color}", svg)


if __name__ == "__main__":
    unittest.main()
