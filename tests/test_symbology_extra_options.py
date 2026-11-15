import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools.symbology_extra_options import (check_callout, check_diagram, check_marker_source, check_relief,
                                                                  check_rules, check_svg_file, symbol_name)


class RulesTests(unittest.TestCase):
    def test_valid_and_invalid(self):
        out, err = check_rules([{"field": "name", "filter": '"pop" > 10', "font_size": 9, "max_scale": 50000}])
        self.assertIsNone(err)
        self.assertEqual(out[0]["max_scale"], 50000.0)
        for bad in (None, [], "x", [1], [{"filter": "1=1"}], [{"field": "a", "font_size": 500}], [{"field": "a"}] * 21):
            self.assertIsNotNone(check_rules(bad)[1], bad)


class CalloutTests(unittest.TestCase):
    def test_options(self):
        self.assertEqual(check_callout(enabled=True, style="Manhattan", width_mm=0.3)[0]["style"], "manhattan")
        for kwargs in ({}, {"enabled": "yes"}, {"style": "wavy"}, {"width_mm": 99}, {"mask": 1}, {"mask_size_mm": 0}):
            self.assertIsNotNone(check_callout(**kwargs)[1], kwargs)


class MarkerTests(unittest.TestCase):
    def test_svg_and_font(self):
        self.assertIsNone(check_marker_source("svg", svg_path="/a/b.svg", size_mm=5)[1])
        self.assertIsNone(check_marker_source("font", font_family="Arial", character="A")[1])
        for args in (("svg", ), ("svg", "http://x/a.svg"), ("svg", "/a/b.png"), ("font", None, "Arial", "AB"), ("font", None, "", "A"), ("dot",)):
            kwargs = dict(zip(("kind", "svg_path", "font_family", "character"), args, strict=False))
            self.assertIsNotNone(check_marker_source(**kwargs)[1], args)

    def test_svg_file_checks(self):
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "a.svg")
            with open(good, "w") as fh:
                fh.write("<svg/>")
            empty = os.path.join(d, "e.svg")
            open(empty, "w").close()
            self.assertIsNone(check_svg_file(good))
            self.assertIsNotNone(check_svg_file(empty))
            self.assertIsNotNone(check_svg_file(os.path.join(d, "missing.svg")))


class DiagramReliefNameTests(unittest.TestCase):
    def test_diagram(self):
        out, err = check_diagram("pie", ["a", "b"], colors=["red", "blue"])
        self.assertIsNone(err)
        self.assertEqual(out["size_mm"], 10.0)
        self.assertTrue(check_diagram(None, None, clear=True)[0]["clear"])
        for args in (("donut", ["a"]), ("pie", []), ("pie", ["a", "a"]), ("pie", ["a"] * 9), ("pie", ["a", "b"], 10, ["red"])):
            self.assertIsNotNone(check_diagram(*args)[1], args)

    def test_relief(self):
        self.assertIsNone(check_relief("hillshade", azimuth=315, altitude=45)[1])
        self.assertIsNone(check_relief("contour", interval=10, index_interval=50, band=1)[1])
        for kwargs in ({"style": "slope"}, {"style": "hillshade", "altitude": 120}, {"style": "contour", "interval": 50, "index_interval": 10},
                       {"style": "contour", "band": 0}):
            self.assertIsNotNone(check_relief(**kwargs)[1], kwargs)

    def test_symbol_name(self):
        self.assertEqual(symbol_name(" Camp icon ")[0], "Camp icon")
        for bad in ("", "a/b", "x" * 81, None):
            self.assertIsNotNone(symbol_name(bad)[1], bad)


if __name__ == "__main__":
    unittest.main()
