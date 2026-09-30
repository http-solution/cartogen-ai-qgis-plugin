# -*- coding: utf-8 -*-
"""
Tests for ui/reply_vocab.py -- which typed replies may resolve a pending DESTRUCTIVE
confirmation (rc7 smoke test, 2026-09-30, finding F16).

The router card ("Reply to send this") legitimately accepts a casual "yes". A destructive gate
(load_project, field_calculator, the cloud-data override ...) must not: if such a preview is
still pending and the user later answers an unrelated question with "yes"/"ok"/"sure"/"go", the
old shared vocabulary would silently confirm the destructive action.
"""
import datetime
import unittest

from cartogen_ai.core.ui import reply_vocab as rv


class TestGateReply(unittest.TestCase):
    def test_explicit_words_confirm(self):
        for word in ("confirm", "Confirm", "CONFIRM!", " proceed ", "apply", "Apply edit", "confirm and execute"):
            self.assertEqual(rv.gate_reply(word), "confirm", word)

    def test_casual_words_do_not_confirm_a_destructive_action(self):
        for word in ("yes", "y", "yeah", "yep", "ok", "okay", "sure", "go", "go ahead", "send", "send this", "do it"):
            self.assertIsNone(rv.gate_reply(word), word)

    def test_cancel_words_cancel(self):
        for word in ("cancel", "No", "n", "nope", "stop", "abort", "never mind", "nvm"):
            self.assertEqual(rv.gate_reply(word), "cancel", word)

    def test_longer_messages_are_never_a_reply(self):
        self.assertIsNone(rv.gate_reply("confirm that the layer has 3 features"))
        self.assertIsNone(rv.gate_reply("please cancel my earlier request and start again"))

    def test_empty_text_is_not_a_reply(self):
        self.assertIsNone(rv.gate_reply(""))
        self.assertIsNone(rv.gate_reply(None))


class TestRouterReply(unittest.TestCase):
    """The router-card vocabulary is unchanged: casual yes still sends the composed prompt."""

    def test_casual_yes_still_confirms_a_router_card(self):
        for word in ("yes", "ok", "sure", "go ahead", "send this", "confirm"):
            self.assertEqual(rv.router_reply(word), "confirm", word)

    def test_cancel_words_cancel_a_router_card(self):
        self.assertEqual(rv.router_reply("cancel"), "cancel")

    def test_anything_else_is_an_edit(self):
        self.assertIsNone(rv.router_reply("just show me clinics instead"))


class TestPreviewFreshness(unittest.TestCase):
    NOW = datetime.datetime(2026, 9, 30, 12, 0, 0, tzinfo=datetime.timezone.utc)

    def _iso(self, seconds_ago):
        return (self.NOW - datetime.timedelta(seconds=seconds_ago)).isoformat()

    def test_a_recent_preview_is_fresh(self):
        self.assertTrue(rv.preview_is_fresh(self._iso(30), now=self.NOW))

    def test_a_preview_just_inside_the_limit_is_fresh(self):
        self.assertTrue(rv.preview_is_fresh(self._iso(rv.PREVIEW_MAX_AGE_SECONDS - 1), now=self.NOW))

    def test_an_old_preview_is_stale(self):
        self.assertFalse(rv.preview_is_fresh(self._iso(rv.PREVIEW_MAX_AGE_SECONDS + 1), now=self.NOW))

    def test_an_unreadable_timestamp_is_treated_as_stale_not_fresh(self):
        for bad in (None, "", "not a date"):
            self.assertFalse(rv.preview_is_fresh(bad, now=self.NOW), bad)


if __name__ == "__main__":
    unittest.main()
