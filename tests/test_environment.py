"""PLAN-053 stage 1: the plugin knows what it is running on (QGIS, Qt, Python, OS) and says so plainly when that is outside what it was built for.
Pure functions plus the two places that carry the result (evidence context, Help). Nothing here runs QGIS; the startup call in plugin_main is
covered by the live test."""
import unittest

from cartogen_ai.core import environment as env


def sample(**changes):
    base = {"os": "Windows", "os_release": "11", "arch": "AMD64", "python": "3.12.3", "qgis": "4.2.3-Prizren", "qt": "6.8.1", "gdal": "3.10.0"}
    base.update(changes)
    return base


class TestParseVersion(unittest.TestCase):
    def test_versions_with_suffixes_and_noise(self):
        self.assertEqual(env.parse_version("4.2.3-Prizren"), (4, 2, 3))
        self.assertEqual(env.parse_version("3.40.1"), (3, 40, 1))
        self.assertEqual(env.parse_version("claude 2.1.317 (build x)"), (2, 1, 317))
        self.assertEqual(env.parse_version("v1.0.6"), (1, 0, 6))
        self.assertEqual(env.parse_version("5"), (5,))

    def test_text_with_no_number_is_empty_not_a_guess(self):
        for text in ("", None, "unknown", "no version here"):
            self.assertEqual(env.parse_version(text), ())

    def test_versions_compare_as_numbers_not_text(self):
        self.assertLess(env.parse_version("4.2.10"), env.parse_version("4.10.0"))
        self.assertLess(env.parse_version("3.9"), env.parse_version("3.10"))


class TestDetect(unittest.TestCase):
    def test_it_reads_this_machine_and_never_raises(self):
        found = env.detect()
        for key in ("os", "os_release", "arch", "python", "qgis", "qt", "gdal"):
            self.assertIn(key, found)
            self.assertIsInstance(found[key], str)
        self.assertTrue(found["os"])
        self.assertRegex(found["python"], r"^\d+\.\d+")

    def test_the_operating_system_gets_the_name_a_person_uses(self):
        from unittest import mock
        for system, wanted in (("Darwin", "macOS"), ("Windows", "Windows"), ("Linux", "Linux"), ("FreeBSD", "FreeBSD")):
            with mock.patch.object(env.platform, "system", return_value=system):
                self.assertEqual(env.detect()["os"], wanted)

    def test_a_broken_probe_gives_blank_text_not_an_exception(self):
        from unittest import mock
        with mock.patch.object(env.platform, "release", side_effect=OSError("boom")), mock.patch.object(env.platform, "machine", side_effect=OSError("boom")):
            found = env.detect()
        self.assertEqual((found["os_release"], found["arch"]), ("", ""))


class TestDescribe(unittest.TestCase):
    def test_one_line_a_person_can_paste_into_a_bug_report(self):
        self.assertEqual(env.describe(sample()), "QGIS 4.2.3-Prizren, Qt 6.8.1, Windows 11 (AMD64), Python 3.12.3")

    def test_missing_parts_are_left_out_not_shown_as_none(self):
        text = env.describe(sample(qgis="", qt="", gdal=""))
        self.assertNotIn("None", text)
        self.assertNotIn("QGIS", text)
        self.assertIn("Python 3.12.3", text)


class TestFindings(unittest.TestCase):
    def levels(self, **changes):
        return [(f["level"], f["code"]) for f in env.findings(sample(**changes))]

    def test_a_supported_machine_has_no_findings(self):
        self.assertEqual(env.findings(sample()), [])
        self.assertEqual(env.findings(sample(os="macOS", os_release="14.5", arch="arm64")), [])
        self.assertEqual(env.findings(sample(os="Linux")), [])

    def test_qgis_older_than_the_minimum_is_unsupported_and_says_what_is_needed(self):
        found = env.findings(sample(qgis="3.40.1"))
        self.assertEqual([(f["level"], f["code"]) for f in found], [("unsupported", "qgis_too_old")])
        self.assertIn("3.40.1", found[0]["text"])
        self.assertIn("4.2", found[0]["text"])

    def test_the_minimum_itself_and_later_4_x_versions_are_fine(self):
        self.assertEqual(self.levels(qgis="4.2.0"), [])
        self.assertEqual(self.levels(qgis="4.10.1"), [])

    def test_a_future_major_version_is_untested_not_refused(self):
        self.assertEqual(self.levels(qgis="5.0.1"), [("untested", "qgis_newer_than_tested")])

    def test_old_python_is_unsupported(self):
        self.assertEqual(self.levels(python="3.9.18"), [("unsupported", "python_too_old")])
        self.assertEqual(self.levels(python="3.10.0"), [])

    def test_an_operating_system_outside_the_three_is_untested(self):
        self.assertEqual(self.levels(os="FreeBSD"), [("untested", "os_untested")])

    def test_no_qgis_at_all_is_not_a_finding(self):
        self.assertEqual(env.findings(sample(qgis="", qt="")), [])

    def test_a_qgis_version_that_cannot_be_read_is_a_note_not_a_refusal(self):
        self.assertEqual(self.levels(qgis="dev-build"), [("note", "qgis_version_unreadable")])


class TestStartupMessage(unittest.TestCase):
    def test_only_problems_are_shown_to_the_user(self):
        self.assertIsNone(env.startup_message(env.findings(sample())))
        self.assertIsNone(env.startup_message(env.findings(sample(qgis="dev-build"))))
        text = env.startup_message(env.findings(sample(qgis="3.40.1")))
        self.assertIn("3.40.1", text)

    def test_several_problems_are_joined_in_order_of_seriousness(self):
        text = env.startup_message(env.findings(sample(qgis="3.40.1", os="FreeBSD")))
        self.assertLess(text.index("3.40.1"), text.index("FreeBSD"))


class TestCarriedWhereItIsNeeded(unittest.TestCase):
    def test_the_evidence_context_includes_the_environment(self):
        import inspect
        from cartogen_ai.core.agent import evidence
        self.assertIn("environment", inspect.getsource(evidence.project_context))

    def test_the_help_shows_the_line_only_when_given_one(self):
        from cartogen_ai.core.ui import help_content
        plain = help_content.build_help_html(version="9.9.9", tool_count=1, task_count=1, section_count=1)
        shown = help_content.build_help_html(version="9.9.9", tool_count=1, task_count=1, section_count=1, environment_line="QGIS 4.2.3, Windows 11")
        self.assertNotIn("QGIS 4.2.3, Windows 11", plain)
        self.assertIn("QGIS 4.2.3, Windows 11", shown)

    def test_the_log_allows_the_environment_fields_and_nothing_personal(self):
        from cartogen_ai.core import logger
        for field in ("os", "os_release", "arch", "python", "qgis", "qt", "gdal", "findings"):
            self.assertIn(field, logger._SAFE_EVENT_FIELDS)
        for field in ("user", "username", "hostname", "path", "home"):
            self.assertNotIn(field, logger._SAFE_EVENT_FIELDS)


if __name__ == "__main__":
    unittest.main()


class TestReportText(unittest.TestCase):
    """PLAN-053 stage 3: the text of the Settings section 'This computer', the same lines a person pastes into a bug report."""

    def test_a_supported_machine_reads_all_clear(self):
        text = env.report_text(sample(), "1.18.5")
        lines = text.splitlines()
        self.assertEqual(lines[0], "Cartogen AI 1.18.5")
        self.assertIn("QGIS 4.2.3-Prizren", lines[1])
        self.assertIn("GDAL 3.10.0", text)
        self.assertIn("inside the range", text)

    def test_problems_are_listed_with_their_seriousness_in_words(self):
        text = env.report_text(sample(qgis="3.40.1", os="FreeBSD"), "1.18.5")
        self.assertIn("Not supported:", text)
        self.assertIn("Not tried:", text)
        self.assertIn("3.40.1", text)
        self.assertNotIn("inside the range", text)

    def test_nothing_personal_is_in_it(self):
        text = env.report_text(sample(), "1.18.5")
        for word in ("C:\\", "/home/", "/Users/", "@"):
            self.assertNotIn(word, text)

    def test_a_missing_plugin_version_leaves_the_heading_plain(self):
        self.assertEqual(env.report_text(sample(), "").splitlines()[0], "Cartogen AI")


class TestApiMismatchNote(unittest.TestCase):
    def test_a_qgis_looking_failure_gets_the_machine_line(self):
        for error in (AttributeError("module 'qgis.core' has no attribute 'QgsNewThing'"), ImportError("cannot import name 'QgsX' from 'qgis.core'"),
                      NameError("name 'Qgis' is not defined"), TypeError("QgsVectorLayer(): argument 1 has unexpected type 'int'")):
            self.assertEqual(env.api_mismatch_note(error, sample()), env.describe(sample()), repr(error))

    def test_other_failures_get_nothing(self):
        for error in (AttributeError("'NoneType' object has no attribute 'get'"), ValueError("bad input"), KeyError("name"), RuntimeError("Qgs thing broke")):
            self.assertEqual(env.api_mismatch_note(error, sample()), "", repr(error))


class TestWhereTheNoteAndTheSectionAre(unittest.TestCase):
    def test_an_unexpected_tool_failure_carries_the_machine_only_when_it_looks_like_a_qgis_version_problem(self):
        from cartogen_ai.core.agent import agent_orchestrator as agent_mod
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)

        def raising(error):
            def boom(name, arguments):
                raise error
            return boom

        agent._execute_tool_dispatch = raising(AttributeError("module 'qgis.core' has no attribute 'QgsNewThing'"))
        result = agent._guarded_dispatch("some_tool", "{}")
        self.assertIn("failed unexpectedly", result["error"])
        self.assertEqual(result["error_class"], "AttributeError")
        self.assertIn("environment", result)
        agent._execute_tool_dispatch = raising(ValueError("bad input"))
        self.assertNotIn("environment", agent._guarded_dispatch("some_tool", "{}"))

    def test_the_settings_window_has_the_section_and_a_copy_button(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "src" / "cartogen_ai" / "core" / "ui" / "settings_dialog.py").read_text(encoding="utf-8")
        for needle in ("environment.report_text(", "environmentReportText", "environmentCopyButton", '"This computer"'):
            self.assertIn(needle, text)
