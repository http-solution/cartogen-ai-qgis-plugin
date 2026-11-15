"""PLAN-016 item 1, offline: an export judges a layout by the CURRENT profile file's requirements and the sign-off the layout was built with."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools.layout_export_checks import current_profile, merge_current_profile
from cartogen_ai.core.agent.tools.map_profiles import sign_off_missing

REVIEWED = {"prepared_by": "A", "reviewed_by": "B", "review_date": "2026-10-20", "status": "Reviewed"}


class FakeLayout:
    def __init__(self, stored=None, name=None):
        self.props = {}
        if stored is not None:
            self.props["cartogen_ai/profile_json"] = json.dumps(stored)
        if name:
            self.props["cartogen_ai/profile_name"] = name

    def customProperty(self, key, default=None):
        return self.props.get(key, default)


class TestMerge(unittest.TestCase):
    def test_requirements_come_from_the_file_and_the_sign_off_from_the_layout(self):
        merged = merge_current_profile({"sign_off": {"prepared_by": "A"}}, {"require_sign_off": True, "required_elements": ["TITLE"], "sign_off": REVIEWED})
        self.assertTrue(merged["require_sign_off"])
        self.assertEqual(merged["required_elements"], ["TITLE"])
        self.assertEqual(merged["sign_off"], {"prepared_by": "A"})          # the printed one, not the file's newer review

    def test_a_layout_built_without_a_sign_off_does_not_inherit_one_from_the_file(self):
        merged = merge_current_profile({}, {"require_sign_off": True, "sign_off": REVIEWED})
        self.assertNotIn("sign_off", merged)
        self.assertTrue(sign_off_missing(merged))


class TestCurrentProfile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch("cartogen_ai.core.agent.tools.map_profiles.profile_dirs", lambda: [self.tmp.name])
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write(self, data):
        with open(os.path.join(self.tmp.name, "p.json"), "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def test_a_requirement_added_after_the_layout_was_built_applies(self):
        """The A29 case: the layout was built before require_sign_off was added to the file."""
        layout = FakeLayout({"profile_version": 1}, "p")
        self._write({"profile_version": 1, "require_sign_off": True})
        profile, note = current_profile(layout)
        self.assertIsNone(note)
        self.assertTrue(sign_off_missing(profile))

    def test_a_requirement_removed_from_the_file_no_longer_applies(self):
        layout = FakeLayout({"require_sign_off": True}, "p")
        self._write({"profile_version": 1})
        self.assertFalse(sign_off_missing(current_profile(layout)[0]))

    def test_a_review_added_to_the_file_does_not_pass_a_layout_whose_footer_says_draft(self):
        layout = FakeLayout({"sign_off": {"prepared_by": "A"}}, "p")
        self._write({"profile_version": 1, "require_sign_off": True, "sign_off": REVIEWED})
        self.assertTrue(sign_off_missing(current_profile(layout)[0]))

    def test_a_layout_built_with_the_review_passes(self):
        layout = FakeLayout({"sign_off": REVIEWED}, "p")
        self._write({"profile_version": 1, "require_sign_off": True, "sign_off": REVIEWED})
        self.assertFalse(sign_off_missing(current_profile(layout)[0]))

    def test_a_deleted_or_broken_file_falls_back_to_the_stored_copy_with_a_note(self):
        layout = FakeLayout({"require_sign_off": True}, "p")
        profile, note = current_profile(layout)                              # no file at all
        self.assertTrue(profile["require_sign_off"])
        self.assertIn("could not be re-read", note)
        with open(os.path.join(self.tmp.name, "p.json"), "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        self.assertIn("could not be re-read", current_profile(layout)[1])

    def test_a_layout_without_a_profile_name_keeps_its_stored_copy(self):
        layout = FakeLayout({"require_sign_off": True})
        self._write({"profile_version": 1})
        profile, note = current_profile(layout)
        self.assertEqual((profile, note), ({"require_sign_off": True}, None))

    def test_a_layout_with_no_profile_at_all_has_none(self):
        self.assertEqual(current_profile(FakeLayout()), ({}, None))


if __name__ == "__main__":
    unittest.main()
