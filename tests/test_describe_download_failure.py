"""describe_download_failure: a person-readable reason for a failed download, never the signed link."""
import socket
import unittest
import urllib.error

from cartogen_ai.core import net

SIGNED = ("https://s3.us-east-1.amazonaws.com/bucket/file.zip?AWSAccessKeyId=ASIAEXAMPLE&Signature=abc%3D"
          "&x-amz-security-token=SECRETTOKEN&Expires=1793000686")


class TestDescribeDownloadFailure(unittest.TestCase):
    def _http(self, code, reason="Error transferring " + SIGNED + " - server replied: Forbidden"):
        return urllib.error.HTTPError(SIGNED, code, reason, net._Headers([]), None)

    def test_a_403_says_who_refused_and_what_to_try_and_never_quotes_the_link(self):
        msg = net.describe_download_failure(self._http(403), SIGNED)
        self.assertIn("refused", msg)
        self.assertIn("HTTP 403", msg)
        self.assertIn("s3.us-east-1.amazonaws.com", msg)
        for secret in ("SECRETTOKEN", "ASIAEXAMPLE", "Signature", "?"):
            self.assertNotIn(secret, msg)

    def test_each_kind_of_failure_has_its_own_sentence(self):
        cases = {
            401: "refused", 404: "not found", 407: "login", 429: "too many requests", 502: "error",
        }
        for code, word in cases.items():
            with self.subTest(code=code):
                self.assertIn(word, net.describe_download_failure(self._http(code), "https://h.example.org/f"))
        self.assertIn("timed out", net.describe_download_failure(TimeoutError("timed out"), "https://h.example.org/f"))
        self.assertIn("could not be found", net.describe_download_failure(urllib.error.URLError(socket.gaierror(-2, "x")), "https://h.example.org/f"))
        self.assertIn("proxy", net.describe_download_failure(OSError("boom"), "https://h.example.org/f"))

    def test_redact_url_drops_query_and_fragment(self):
        self.assertEqual(net.redact_url(SIGNED + "#frag"), "https://s3.us-east-1.amazonaws.com/bucket/file.zip")


if __name__ == "__main__":
    unittest.main()
