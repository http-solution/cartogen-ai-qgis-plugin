"""PLAN-023 R10-2: the pure checks for conditional formatting, map tips and layer actions, including the no-command-execution policy. No QGIS and no numpy needed."""
import unittest

from cartogen_ai.core.agent.tools import display_rules as dr


class TestMapTip(unittest.TestCase):
    def test_the_expressions_of_a_template_are_read(self):
        self.assertEqual(dr.map_tip_expressions('<b>[% "name" %]</b> [% "pop" * 2 %]'), ['"name"', '"pop" * 2'])
        self.assertEqual(dr.map_tip_expressions("no fields"), [])

    def test_plain_html_with_fields_is_accepted(self):
        self.assertIsNone(dr.check_map_tip('<table><tr><td>[% "name" %]</td></tr></table><img src="logo.png"><style>b{color:red}</style>'))
        self.assertIsNone(dr.check_map_tip(""))

    def test_what_runs_code_is_refused(self):
        for bad in ("<script>alert(1)</script>", "< SCRIPT src=x>", "<iframe src=x>", '<img src=x onerror="a()">', '<a href="javascript:a()">x</a>', '<a href="data:text/html,x">x</a>',
                    "<object data=x>", "<form action=x>", "<meta http-equiv=refresh>"):
            self.assertIsNotNone(dr.check_map_tip(bad), bad)
        self.assertIsNotNone(dr.check_map_tip(5))
        self.assertIsNotNone(dr.check_map_tip("x" * 4001))


class TestFormatting(unittest.TestCase):
    def test_valid_rules(self):
        self.assertIsNone(dr.check_formatting([{"condition": "@value > 100", "background_color": "#ffcccc"}]))
        self.assertIsNone(dr.check_formatting([{"condition": '"pop" is null', "text_color": "red", "name": "no data"}]))

    def test_invalid_rules(self):
        for rules in ([], "x", [1], [{"background_color": "red"}], [{"condition": "1"}], [{"condition": "1", "background_color": "#12"}], [{"condition": "1", "text_color": 5}],
                      [{"condition": "1", "background_color": "red", "name": 3}], [{"condition": "1", "background_color": "red"}] * 21, [{"condition": "x" * 501, "text_color": "red"}]):
            self.assertIsNotNone(dr.check_formatting(rules), rules)


class TestAction(unittest.TestCase):
    def test_a_command_action_is_refused_with_the_policy(self):
        for kind in ("python", "Shell", "windows", "mac", "unix", "command", "generic"):
            text = dr.check_action("Run", kind, "notepad.exe")
            self.assertIn("run a command", text, kind)
            self.assertIn("policy", text)

    def test_an_open_url_action_is_accepted(self):
        self.assertIsNone(dr.check_action("Wikipedia", "open_url", "https://en.wikipedia.org/wiki/[% \"name\" %]"))

    def test_bad_open_url_requests(self):
        for args in (("", "open_url", "https://a"), ("x", "open_url", "ftp://a"), ("x", "open_url", "file:///etc/passwd"), ("x", "open_url", "https://a b"), ("x", "weird", "https://a"),
                     ("x", "open_url", None), ("x", "open_url", "https://" + "a" * 1000)):
            self.assertIsNotNone(dr.check_action(*args), args)


if __name__ == "__main__":
    unittest.main()
