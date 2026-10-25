"""The owner's disclaimer wording (2026-10-25) is defined once (core/disclaimer_text.py) and must be the footer default, in the Help and in the
user guide, word for word."""
import html
import os
import re
import unittest

from cartogen_ai.core import disclaimer_text as d
from cartogen_ai.core.agent.tools.layout_style import DEFAULT_DISCLAIMER, disclaimer_text
from cartogen_ai.core.ui.help_content import build_help_html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _squash(text):
    return re.sub(r"\s+", " ", text).strip()


class TestDisclaimerText(unittest.TestCase):
    def test_the_footer_default_is_the_balanced_standard_wording(self):
        self.assertIs(DEFAULT_DISCLAIMER, d.LAYOUT_DISCLAIMER)
        self.assertEqual(disclaimer_text(True, ""), d.LAYOUT_DISCLAIMER)
        self.assertTrue(d.LAYOUT_DISCLAIMER.startswith("Boundaries, names, and designations shown on this map are for informational"))
        self.assertTrue(d.LAYOUT_DISCLAIMER.endswith("prior to internal use or external distribution."))

    def test_an_organisations_own_wording_and_the_switch_still_win(self):
        self.assertEqual(disclaimer_text(True, " Our wording. "), "Our wording.")
        self.assertEqual(disclaimer_text(False, "Our wording."), "")

    def test_the_help_carries_all_three_terms_paragraphs(self):
        text = _squash(html.unescape(re.sub(r"<[^>]+>", " ", build_help_html(version="x"))))
        self.assertIn(d.TERMS_TITLE, text)
        for heading, body in d.TERMS_PARAGRAPHS:
            self.assertIn(_squash(f"{heading} {body}"), text)

    def test_the_user_guide_carries_them_and_the_footer_line_verbatim(self):
        with open(os.path.join(ROOT, "docs", "USER_GUIDE.md"), encoding="utf-8") as fh:
            guide = _squash(fh.read().replace("**", ""))
        self.assertIn(f"## {d.TERMS_TITLE}", guide)
        for heading, body in d.TERMS_PARAGRAPHS:
            self.assertIn(_squash(f"{heading} {body}"), guide)
        self.assertIn(_squash(d.LAYOUT_DISCLAIMER), guide)


if __name__ == "__main__":
    unittest.main()
