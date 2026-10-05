# -*- coding: utf-8 -*-
"""Offline guard for the live-test list: a live module must run in CI or be excluded with a reason (see tests/_live_modules.py)."""
import unittest

from tests import _live_modules as lm


class TestLiveRegistration(unittest.TestCase):
    def test_every_live_module_runs_or_is_excluded(self):
        names = set(lm.live_module_names())
        for name in lm.discovered():
            self.assertTrue(name in names or name in lm.EXCLUDED, name)

    def test_exclusions_name_real_files_and_give_a_reason(self):
        on_disk = set(lm.discovered())
        for name, reason in lm.EXCLUDED.items():
            self.assertIn(name, on_disk, "stale exclusion: " + name)
            self.assertTrue(reason.strip(), "exclusion without a reason: " + name)

    def test_excluded_modules_do_not_run(self):
        self.assertFalse(set(lm.EXCLUDED) & set(lm.live_module_names()))

    def test_ordered_modules_keep_their_order(self):
        names = lm.live_module_names()
        listed = [n for n in names if n in lm.ORDER]
        self.assertEqual(listed, [n for n in lm.ORDER if n in listed])

    def test_a_new_live_module_is_picked_up_without_editing_a_list(self):
        self.assertIn("test_tool_dispatch_live", lm.live_module_names())

    def test_the_ordered_list_has_no_duplicates(self):
        self.assertEqual(len(lm.ORDER), len(set(lm.ORDER)))


if __name__ == "__main__":
    unittest.main()
