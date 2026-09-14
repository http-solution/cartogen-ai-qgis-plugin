# -*- coding: utf-8 -*-
"""Tests for agent/tools/_urllib_retry.py -- API-003, 2026-09-14 audit."""
import io
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools._urllib_retry import urlopen_with_retry


class TestUrlopenWithRetry(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools._urllib_retry.urllib.request.urlopen")
    def test_success_on_first_try_returns_response(self, mock_urlopen):
        mock_urlopen.return_value = "the response"
        result = urlopen_with_retry("req", timeout=10)
        self.assertEqual(result, "the response")
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("cartogen_ai.core.agent.tools._urllib_retry.time.sleep")
    @patch("cartogen_ai.core.agent.tools._urllib_retry.urllib.request.urlopen")
    def test_retries_on_transient_503_then_succeeds(self, mock_urlopen, mock_sleep):
        err = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, io.BytesIO())
        mock_urlopen.side_effect = [err, "the response"]
        result = urlopen_with_retry("req", timeout=10)
        self.assertEqual(result, "the response")
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("cartogen_ai.core.agent.tools._urllib_retry.time.sleep")
    @patch("cartogen_ai.core.agent.tools._urllib_retry.urllib.request.urlopen")
    def test_does_not_retry_on_permanent_404(self, mock_urlopen, mock_sleep):
        err = urllib.error.HTTPError("url", 404, "Not Found", {}, io.BytesIO())
        mock_urlopen.side_effect = err
        with self.assertRaises(urllib.error.HTTPError):
            urlopen_with_retry("req", timeout=10)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("cartogen_ai.core.agent.tools._urllib_retry.time.sleep")
    @patch("cartogen_ai.core.agent.tools._urllib_retry.urllib.request.urlopen")
    def test_gives_up_after_max_retries_on_persistent_failure(self, mock_urlopen, mock_sleep):
        err = urllib.error.URLError("connection refused")
        mock_urlopen.side_effect = err
        with self.assertRaises(urllib.error.URLError):
            urlopen_with_retry("req", timeout=10, max_retries=2)
        self.assertEqual(mock_urlopen.call_count, 3)

    @patch("cartogen_ai.core.agent.tools._urllib_retry.time.sleep")
    def test_uses_the_given_opener_instead_of_urllib_urlopen(self, mock_sleep):
        opener = MagicMock()
        opener.open.side_effect = [urllib.error.URLError("blip"), "the response"]
        result = urlopen_with_retry("req", timeout=10, opener=opener)
        self.assertEqual(result, "the response")
        self.assertEqual(opener.open.call_count, 2)


if __name__ == "__main__":
    unittest.main()
