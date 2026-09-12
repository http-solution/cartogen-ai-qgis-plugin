# -*- coding: utf-8 -*-
import os
import tempfile
import shutil
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent import onboarding_profile as op


class OnboardingProfileTestCase(unittest.TestCase):
    """All file I/O redirected to a throwaway temp dir via patching _profile_base_dir --
    exercising the real save/load round trip without ever touching the developer's/CI's actual
    home directory (unlike this codebase's existing SpatialMemoryManager test precedent, which
    does write a small file to the real home dir as an accepted side effect -- avoided here
    since it's simple to do properly for newly-written tests)."""

    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp()
        self._patcher = patch.object(op, "_profile_base_dir", return_value=self._tmp_dir)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self._tmp_dir, ignore_errors=True)


class TestGetProfileMdPath(OnboardingProfileTestCase):
    def test_path_is_inside_the_base_dir(self):
        path = op.get_profile_md_path()
        self.assertEqual(os.path.dirname(path), self._tmp_dir)
        self.assertTrue(path.endswith("user_profile.md"))


class TestSaveAndLoadRoundTrip(OnboardingProfileTestCase):
    def test_save_then_load_returns_the_same_values(self):
        op.save_onboarding_profile(
            role="cartographer", role_other="", experience="expert", style="concise",
        )
        profile = op.load_onboarding_profile()
        self.assertEqual(profile["role"], "cartographer")
        self.assertEqual(profile["role_other"], "")
        self.assertEqual(profile["experience"], "expert")
        self.assertEqual(profile["style"], "concise")

    def test_other_role_round_trips_its_free_text(self):
        op.save_onboarding_profile(
            role="other", role_other="Freelance surveyor", experience="beginner", style="plain_language",
        )
        profile = op.load_onboarding_profile()
        self.assertEqual(profile["role"], "other")
        self.assertEqual(profile["role_other"], "Freelance surveyor")

    def test_non_other_role_never_writes_a_role_other_line(self):
        path = op.save_onboarding_profile(
            role="gis_student", role_other="ignored, should not appear", experience="beginner", style="detailed",
        )
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("Role (other)", content)
        self.assertNotIn("ignored, should not appear", content)

    def test_file_content_uses_human_readable_labels_not_raw_keys(self):
        path = op.save_onboarding_profile(
            role="humanitarian_analyst", role_other="", experience="intermediate", style="technical",
        )
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Humanitarian / Crisis Response Analyst", content)
        self.assertNotIn("humanitarian_analyst", content)

    def test_save_calls_mark_onboarding_completed(self):
        # mark_onboarding_completed() itself is QGIS_AVAILABLE-guarded and tested separately
        # (TestOnboardingCompletedWithoutQgis) -- this only confirms save_onboarding_profile
        # actually calls it, patching the function itself rather than the QGIS internals it
        # short-circuits past when QGIS isn't importable (as in this test environment).
        with patch.object(op, "mark_onboarding_completed") as mock_mark:
            op.save_onboarding_profile(
                role="researcher", role_other="", experience="expert", style="detailed",
            )
            mock_mark.assert_called_once()


class TestLoadWithNoFile(OnboardingProfileTestCase):
    def test_returns_none_when_nothing_saved(self):
        self.assertIsNone(op.load_onboarding_profile())


class TestFormattedContext(OnboardingProfileTestCase):
    def test_none_when_no_profile_saved(self):
        self.assertIsNone(op.get_formatted_onboarding_context())

    def test_includes_role_experience_and_style(self):
        op.save_onboarding_profile(
            role="emergency_responder", role_other="", experience="beginner", style="concise",
        )
        ctx = op.get_formatted_onboarding_context()
        self.assertIn("Emergency Responder / Field Operator", ctx)
        self.assertIn("Beginner", ctx)
        self.assertIn("Concise", ctx)
        self.assertTrue(ctx.startswith("## User Profile"))

    def test_other_role_uses_the_free_text_not_the_word_other(self):
        op.save_onboarding_profile(
            role="other", role_other="Freelance surveyor", experience="expert", style="technical",
        )
        ctx = op.get_formatted_onboarding_context()
        self.assertIn("Freelance surveyor", ctx)
        self.assertNotIn("Role: Other", ctx)


class TestOnboardingCompletedWithoutQgis(unittest.TestCase):
    """QGIS_AVAILABLE is False in this test environment (no qgis.core importable) -- confirms
    the module degrades gracefully rather than raising, matching every other QGIS_AVAILABLE-
    guarded module's convention (memory.py, prompt_refiner.py)."""

    def test_is_onboarding_completed_defaults_false_outside_qgis(self):
        self.assertFalse(op.QGIS_AVAILABLE)
        self.assertFalse(op.is_onboarding_completed())

    def test_mark_onboarding_completed_does_not_raise_outside_qgis(self):
        op.mark_onboarding_completed()  # no assertion needed -- just must not raise


class TestLoadRobustnessAgainstGarbledContent(OnboardingProfileTestCase):
    def test_unrecognized_label_falls_back_to_default(self):
        path = op.get_profile_md_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Some file\n- **Role:** Something Nobody Ever Wrote\n")
        profile = op.load_onboarding_profile()
        self.assertEqual(profile["role"], op.DEFAULT_ROLE)
        self.assertEqual(profile["experience"], op.DEFAULT_EXPERIENCE)
        self.assertEqual(profile["style"], op.DEFAULT_STYLE)
