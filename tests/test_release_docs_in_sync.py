# -*- coding: utf-8 -*-
"""Fails when a version bump leaves release-facing text behind: the in-plugin Help, the README "What's new" and humanitarian table, the
CHANGELOG and the metadata changelog must all describe the same version, and the counts they quote must match the live registries.
Update core/release_notes.py (checklist: CONTRIBUTING.md, "Releasing") to fix a failure here."""
import json
import os
import re
import unittest

from cartogen_ai.core import release_notes as rn
from cartogen_ai.core.agent import tools as _all_tools  # noqa: F401  (registers every tool)
from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
from cartogen_ai.core.ui.help_content import build_help_html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestReleaseDocsInSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = _read("metadata.txt")
        cls.readme = _read("README.md")
        cls.changelog = _read("CHANGELOG.md")
        cls.version = re.search(r"^version=(\S+)", cls.meta, re.M).group(1)

    def test_every_place_names_the_metadata_version(self):
        v = self.version
        self.assertEqual(rn.WHATS_NEW_VERSION, v, "core/release_notes.py WHATS_NEW_VERSION is not the metadata version")
        self.assertIn(f"changelog=v{v} ", self.meta)
        self.assertIn(f"## [{v}]", self.changelog)
        self.assertIn(f'(#v{v.replace(".", "-")})', self.changelog)
        self.assertIn(f"Version {v} (pre-release)" if "rc" in v else f"Version {v}", self.readme)
        self.assertIn(f"## What's new in {v}", self.readme)
        self.assertIn(f"What's new in {v}", build_help_html(version=v))
        self.assertIn(f"Version {v}", build_help_html(version=v))

    def test_the_new_mark_versions_include_the_current_version_and_items_exist(self):
        self.assertIn(rn.WHATS_NEW_VERSION, rn.NEW_MARK_VERSIONS)
        self.assertTrue(rn.WHATS_NEW_ITEMS)

    def test_readme_humanitarian_table_is_the_rendered_one(self):
        rows = [line for line in self.readme.splitlines() if line.startswith("| **")]
        self.assertEqual(rows, rn.render_readme_table(), "README table differs from core/release_notes.py (run render_readme_table())")

    def test_listed_tools_are_registered_and_marks_use_known_versions(self):
        listed = {t for _title, tools in rn.HUMANITARIAN_WORKFLOWS for t in tools}
        self.assertEqual(sorted(t for t in listed if t not in TOOL_REGISTRY), [])
        self.assertEqual(sorted(t for t in rn.TOOL_NEW_IN if t not in listed), [], "a tool marked new is missing from the workflow list")

    def test_help_lists_every_humanitarian_tool(self):
        html = build_help_html(version=self.version)
        missing = [t for _title, tools in rn.HUMANITARIAN_WORKFLOWS for t in tools if f"<code>{t}</code>" not in html]
        self.assertEqual(missing, [])

    def test_quoted_counts_match_the_live_registries(self):
        n = len(TOOL_REGISTRY)
        self.assertIn(f"**{n} tools**", self.readme)
        self.assertIn(f"All {n} tools", self.readme)
        self.assertIn(f"and {n} tools across", self.readme)
        with open(os.path.join(ROOT, "src", "cartogen_ai", "core", "agent", "task_register.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        tasks, sections = len(data), len({t["cat"] for t in data})
        self.assertIn(f"{tasks} mapping\ntasks grouped into {sections} sections", _read("docs", "USER_GUIDE.md"))
        html = build_help_html(version=self.version)
        self.assertIn(f"{tasks} tasks across {sections} sections", html)
        self.assertIn(f"all {n} tools", html)


if __name__ == "__main__":
    unittest.main()
