# -*- coding: utf-8 -*-
"""A failed model download must not print a signed URL and must say what to do (rc15 hand test D06, 2026-10-06)."""
import unittest

from cartogen_ai.core.agent.tools.imagery_extraction import describe_model_failure

SIGNED = ("https://release-assets.githubusercontent.com/github-production-release-asset/1/FastSAM-s.pt?sp=r&sig=SECRET%2Fvalue&se=2026")


class TestDescribeModelFailure(unittest.TestCase):
    def test_no_url_survives_in_the_message(self):
        msg = describe_model_failure(RuntimeError(f"HTTP Error 416: Range Not Satisfiable while fetching {SIGNED}"))
        self.assertNotIn("http", msg.lower().replace("http error", "").replace("an http 416", ""))
        self.assertNotIn("SECRET", msg)

    def test_a_download_failure_says_what_to_do(self):
        msg = describe_model_failure(RuntimeError("HTTP Error 416: Range Not Satisfiable"))
        self.assertIn("FastSAM-s.pt", msg)
        self.assertIn("partial", msg)

    def test_other_failures_keep_the_original_wording_without_urls(self):
        msg = describe_model_failure(ValueError(f"bad tensor shape near {SIGNED}"))
        self.assertTrue(msg.startswith("FastSAM inference failed:"))
        self.assertIn("<url removed>", msg)


if __name__ == "__main__":
    unittest.main()
