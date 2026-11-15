import unittest
import urllib.error

from tests._service_reach_check import EMPTY, REACHED, UNAVAILABLE, UNREACHABLE, classify, render


class ServiceReachCheckTests(unittest.TestCase):
    def test_a_result_is_classified_without_ever_raising(self):
        from cartogen_ai.core.agent.tools.web_research_tools import SearchUnavailableError

        def blocked():
            raise SearchUnavailableError("rate limited")

        def down():
            raise OSError("name resolution failed")

        self.assertEqual(classify("a", lambda: 3)["status"], REACHED)
        self.assertEqual(classify("b", lambda: 0)["status"], EMPTY)
        self.assertEqual(classify("c", blocked)["status"], UNAVAILABLE)
        self.assertEqual(classify("d", down)["status"], UNREACHABLE)

        def limited():
            raise urllib.error.HTTPError("https://x", 429, "Too Many Requests", {}, None)

        def missing():
            raise urllib.error.HTTPError("https://x", 404, "Not Found", {}, None)

        self.assertEqual(classify("e", limited)["status"], UNAVAILABLE)
        self.assertEqual(classify("f", missing)["status"], UNREACHABLE)
        self.assertIn("OSError", classify("d", down)["detail"])

    def test_the_table_has_one_row_per_service_and_no_stray_pipes(self):
        text = render([classify("x | y", lambda: 1), classify("z", lambda: 0)])
        self.assertEqual(len(text.splitlines()), 4)
        self.assertEqual({line.count("|") for line in text.splitlines()}, {4})


if __name__ == "__main__":
    unittest.main()
