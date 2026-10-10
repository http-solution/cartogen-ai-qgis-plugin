# -*- coding: utf-8 -*-
"""metadata.txt must parse the way plugins.qgis.org parses it. 2026-10-10: the QGIS plugin directory rejected the upload with
"Errors parsing cartogen-ai/metadata.txt. '%' must be followed by '%' or '(' ..." because an old changelog block said "under 25% keyword
coverage". The server reads the file with Python's ConfigParser, whose default interpolation treats '%' as special; desktop QGIS did not
care, and no test read the file that way, so nine releases carried the problem. Write "percent", never the symbol, anywhere in this file."""
import configparser
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "metadata.txt")

# What the directory's upload check needs in [general] (docs.qgis.org "Plugin metadata"). The email is the project address the owner chose to
# publish (info@cartogenai.com, 2026-10-10), not a personal one; the homepage must be a page describing usage, which for this plugin is the
# README in the repository.
REQUIRED = ("name", "qgisMinimumVersion", "description", "about", "version", "author", "email", "homepage", "tracker", "repository")


class TestMetadataParsesLikeTheDirectory(unittest.TestCase):
    def test_every_value_reads_with_the_default_configparser(self):
        parser = configparser.ConfigParser()          # default BasicInterpolation, as the server uses
        parser.read(PATH, encoding="utf-8")
        for key, _value in parser["general"].items():      # iterating applies the interpolation to every value
            pass
        self.assertIn("version", parser["general"])

    def test_no_percent_sign_anywhere(self):
        with open(PATH, encoding="utf-8") as fh:
            text = fh.read()
        hits = [m.start() for m in re.finditer("%", text)]
        self.assertEqual(hits, [], "write 'percent' instead of '%' in metadata.txt (plugins.qgis.org parses it with ConfigParser)")

    def test_the_required_fields_are_present_and_not_empty(self):
        parser = configparser.ConfigParser()
        parser.read(PATH, encoding="utf-8")
        missing = [k for k in REQUIRED if not parser["general"].get(k, "").strip()]
        self.assertEqual(missing, [])

    def test_the_homepage_and_email_are_the_published_ones(self):
        parser = configparser.ConfigParser()
        parser.read(PATH, encoding="utf-8")
        self.assertEqual(parser["general"]["homepage"], "https://github.com/http-solution/cartogen-ai-qgis-plugin")
        self.assertEqual(parser["general"]["email"], "info@cartogenai.com")


if __name__ == "__main__":
    unittest.main()
