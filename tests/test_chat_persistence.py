# -*- coding: utf-8 -*-
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from cartogen_ai.core.agent.chat_persistence import (
    save_chat_history, load_chat_history,
    _attach_timestamps,
)


@contextmanager
def _simulate_qgis_with_persist_setting(value, project=None):
    """QGIS_AVAILABLE, QgsSettings, and QgsProject are only bound at module
    level when the real `qgis.core` import succeeds -- there's no qgis.core
    in this test environment, so all three are set directly on the module
    object to exercise the opt-in gating and save/load logic without a real
    QGIS install. `project`, if given, is returned by QgsProject.instance()
    -- pass a _FakeProject to exercise the actual save/restore round trip;
    omit it for tests that only care about the opt-in gate itself."""
    import cartogen_ai.core.agent.chat_persistence as cp

    class _FakeSettings:
        def value(self, key, default, type=None):
            return value if key == cp.PERSIST_SETTING_KEY else default

    class _FakeProjectClass:
        _instance = project

        @classmethod
        def instance(cls):
            return cls._instance

    original_available = cp.QGIS_AVAILABLE
    had_settings_attr = hasattr(cp, "QgsSettings")
    original_settings = getattr(cp, "QgsSettings", None)
    had_project_attr = hasattr(cp, "QgsProject")
    original_project = getattr(cp, "QgsProject", None)
    had_helpers = hasattr(cp, "get_project_custom_property")
    original_get = getattr(cp, "get_project_custom_property", None)
    original_set = getattr(cp, "set_project_custom_property", None)

    cp.QGIS_AVAILABLE = True
    cp.QgsSettings = _FakeSettings
    cp.QgsProject = _FakeProjectClass
    cp.get_project_custom_property = lambda proj, key, default="": proj.custom_properties.get(key, default)

    def _fake_set(proj, key, val):
        proj.custom_properties[key] = val
        return True

    cp.set_project_custom_property = _fake_set
    try:
        yield cp
    finally:
        cp.QGIS_AVAILABLE = original_available
        if had_settings_attr:
            cp.QgsSettings = original_settings
        else:
            del cp.QgsSettings
        if had_project_attr:
            cp.QgsProject = original_project
        else:
            del cp.QgsProject
        if had_helpers:
            cp.get_project_custom_property = original_get
            cp.set_project_custom_property = original_set
        else:
            del cp.get_project_custom_property
            del cp.set_project_custom_property


class _FakeProject:
    """Stands in for QgsProject.instance() -- just a dict-backed store, same
    shape get_project_custom_property/set_project_custom_property expect."""
    def __init__(self):
        self.custom_properties = {}
        self.entries = {}          # QgsProject.writeEntry storage, used by the full transcript

    def readEntry(self, scope, key, default=""):
        if (scope, key) in self.entries:
            return self.entries[(scope, key)], True
        return default, False

    def writeEntry(self, scope, key, value):
        self.entries[(scope, key)] = value
        return True

    def removeEntry(self, scope, key):
        self.entries.pop((scope, key), None)
        return True


class TestChatPersistence(unittest.TestCase):
    def test_save_returns_false_outside_qgis(self):
        self.assertFalse(save_chat_history([{"role": "user", "content": "hi"}]))

    def test_load_returns_empty_list_outside_qgis(self):
        self.assertEqual(load_chat_history(), [])

    def test_is_persist_enabled_reflects_the_setting(self):
        # S2: chat history is now opt-in -- verify the gate itself reads the
        # setting correctly in both directions, not just that it exists.
        with _simulate_qgis_with_persist_setting(True) as cp:
            self.assertTrue(cp.is_persist_enabled())
        with _simulate_qgis_with_persist_setting(False) as cp:
            self.assertFalse(cp.is_persist_enabled())

    def test_save_chat_history_skipped_when_not_opted_in(self):
        with _simulate_qgis_with_persist_setting(False) as cp:
            self.assertFalse(cp.save_chat_history([{"role": "user", "content": "hi"}]))

    def test_load_chat_history_skipped_when_not_opted_in(self):
        with _simulate_qgis_with_persist_setting(False) as cp:
            self.assertEqual(cp.load_chat_history(), [])


class TestAttachTimestamps(unittest.TestCase):
    """Pure-function tests for the merge logic behind the fix: a restored
    chat bubble should show its real age, not "just now" -- see
    chat_persistence.py's _attach_timestamps docstring for the live bug
    (a stale Ollama error looking like it just happened) this addresses.

    2026-09-14 (environment-reproducibility report): fixture "old" timestamps below use
    2000-01-01, not a date in the actual current year -- a "fresh" timestamp is real
    datetime.now().isoformat() wall-clock output (_attach_timestamps captures it once via
    _now_iso()), and test_new_messages_appended_after_old_ones_get_a_fresh_timestamp asserts
    that value is NOT one of the hardcoded "old" ones. A same-year fixture date is close
    enough to a real clock reading that a badly-misconfigured system clock in some other
    environment could coincide with it (this was reported as a failure elsewhere, though it
    could not be reproduced here); an unambiguously-past year removes that risk entirely
    without changing what the test actually verifies."""

    def test_all_new_messages_get_the_same_fresh_timestamp(self):
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        result = _attach_timestamps(history, previous_entries=[])
        self.assertEqual(len(result), 2)
        self.assertTrue(all(e["ts"] for e in result))
        self.assertEqual(result[0]["ts"], result[1]["ts"])

    def test_previously_persisted_messages_keep_their_original_timestamp(self):
        previous = [
            {"role": "user", "content": "hi", "ts": "2000-01-01T00:00:00"},
            {"role": "assistant", "content": "hello", "ts": "2000-01-01T00:00:01"},
        ]
        # Same two messages come back unchanged (e.g. re-saved without new turns).
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        result = _attach_timestamps(history, previous)
        self.assertEqual(result[0]["ts"], "2000-01-01T00:00:00")
        self.assertEqual(result[1]["ts"], "2000-01-01T00:00:01")

    def test_new_messages_appended_after_old_ones_get_a_fresh_timestamp(self):
        previous = [
            {"role": "user", "content": "hi", "ts": "2000-01-01T00:00:00"},
            {"role": "assistant", "content": "hello", "ts": "2000-01-01T00:00:01"},
        ]
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "what layers do I have?"},
            {"role": "assistant", "content": "[API error] Ollama connection failed"},
        ]
        result = _attach_timestamps(history, previous)
        self.assertEqual(result[0]["ts"], "2000-01-01T00:00:00")
        self.assertEqual(result[1]["ts"], "2000-01-01T00:00:01")
        # The new turn gets a real fresh timestamp, distinct from the old ones --
        # this is exactly what stops a stale error from looking brand new.
        self.assertNotIn(result[2]["ts"], ("2000-01-01T00:00:00", "2000-01-01T00:00:01"))
        self.assertEqual(result[2]["ts"], result[3]["ts"])

    def test_trimmed_front_of_history_drops_the_oldest_timestamps_too(self):
        previous = [
            {"role": "user", "content": "msg1", "ts": "2000-01-01T00:00:00"},
            {"role": "assistant", "content": "reply1", "ts": "2000-01-01T00:00:01"},
            {"role": "user", "content": "msg2", "ts": "2000-01-01T00:00:02"},
            {"role": "assistant", "content": "reply2", "ts": "2000-01-01T00:00:03"},
        ]
        # agent_orchestrator.py's _trim_history dropped the oldest pair.
        history = [
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "reply2"},
        ]
        result = _attach_timestamps(history, previous)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["ts"], "2000-01-01T00:00:02")
        self.assertEqual(result[1]["ts"], "2000-01-01T00:00:03")

    def test_duplicate_role_content_pairs_consume_timestamps_in_order(self):
        previous = [
            {"role": "user", "content": "ok", "ts": "2000-01-01T00:00:00"},
            {"role": "user", "content": "ok", "ts": "2000-01-01T00:00:05"},
        ]
        history = [{"role": "user", "content": "ok"}, {"role": "user", "content": "ok"}]
        result = _attach_timestamps(history, previous)
        self.assertEqual(result[0]["ts"], "2000-01-01T00:00:00")
        self.assertEqual(result[1]["ts"], "2000-01-01T00:00:05")


class TestSaveLoadRoundTripWithTimestamps(unittest.TestCase):
    """End-to-end (against a fake QgsProject) coverage of the actual bug fix:
    a message restored on a later save/load cycle keeps the timestamp it was
    first written with, and load_chat_history() (the one that feeds straight
    into an LLM `messages` list) never leaks the `ts` key into it."""

    def test_load_chat_history_never_includes_ts(self):
        project = _FakeProject()
        with _simulate_qgis_with_persist_setting(True, project=project) as cp:
            cp.save_chat_history([{"role": "user", "content": "hi"}])
            restored = cp.load_chat_history()
            self.assertEqual(restored, [{"role": "user", "content": "hi"}])
            self.assertNotIn("ts", restored[0])

    def test_load_chat_history_with_timestamps_includes_ts(self):
        project = _FakeProject()
        with _simulate_qgis_with_persist_setting(True, project=project) as cp:
            cp.save_chat_history([{"role": "user", "content": "hi"}])
            restored = cp.load_chat_history_with_timestamps()
            self.assertEqual(len(restored), 1)
            self.assertIn("ts", restored[0])
            self.assertTrue(restored[0]["ts"])

    def test_timestamp_survives_a_second_save_of_the_same_message(self):
        project = _FakeProject()
        with _simulate_qgis_with_persist_setting(True, project=project) as cp:
            cp.save_chat_history([{"role": "user", "content": "hi"}])
            first_ts = cp.load_chat_history_with_timestamps()[0]["ts"]
            # Re-saving the exact same single-message history (e.g. a no-op
            # persistence call) must not stamp a brand-new "now" over it --
            # that would be the same bug in a different guise.
            cp.save_chat_history([{"role": "user", "content": "hi"}])
            second_ts = cp.load_chat_history_with_timestamps()[0]["ts"]
            self.assertEqual(first_ts, second_ts)

    def test_a_new_turn_added_later_gets_its_own_fresh_timestamp(self):
        project = _FakeProject()
        with _simulate_qgis_with_persist_setting(True, project=project) as cp:
            # Keep this test independent of host-clock resolution or a frozen
            # test-runner clock: the behavior under test is that a later save
            # requests a fresh timestamp, not that datetime.now() advances
            # between two rapid calls in every environment.
            # (the full transcript has its own timestamping and is covered separately below)
            with patch.object(cp, "save_chat_transcript"), patch(
                "cartogen_ai.core.agent.chat_persistence._now_iso",
                side_effect=["2000-01-02T00:00:00", "2000-01-02T00:00:01"],
            ):
                cp.save_chat_history([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}])
                first_two = cp.load_chat_history_with_timestamps()
                cp.save_chat_history([
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hello"},
                    {"role": "user", "content": "what now?"},
                    {"role": "assistant", "content": "[API error] Ollama connection failed"},
                ])
                all_four = cp.load_chat_history_with_timestamps()
            self.assertEqual(all_four[0]["ts"], first_two[0]["ts"])
            self.assertEqual(all_four[1]["ts"], first_two[1]["ts"])
            self.assertNotEqual(all_four[3]["ts"], first_two[0]["ts"])
            self.assertNotEqual(all_four[3]["ts"], first_two[1]["ts"])


class TestFullTranscriptThroughSaveChatHistory(unittest.TestCase):
    """F25 option B: save_chat_history also keeps the full transcript, beyond the agent's window."""

    @staticmethod
    def _turn(n):
        return [{"role": "user", "content": f"q{n}"}, {"role": "assistant", "content": f"a{n}"}]

    def test_the_transcript_keeps_every_message_while_the_window_is_trimmed(self):
        project = _FakeProject()
        with _simulate_qgis_with_persist_setting(True, project=project) as cp:
            full = []
            for n in range(1, 9):
                full += self._turn(n)
                cp.save_chat_history(full[-6:])          # the agent only ever holds its last 6 here
            transcript = cp.load_chat_transcript()
            self.assertEqual([m["content"] for m in transcript], [m["content"] for m in full])
            self.assertEqual(len(cp.load_chat_history()), 6)    # the window restore is unchanged

    def test_the_user_message_takes_the_send_time_the_reply_takes_the_save_time(self):
        project = _FakeProject()
        with _simulate_qgis_with_persist_setting(True, project=project) as cp:
            cp.save_chat_history(self._turn(1), user_ts="2026-09-30T01:00:00")
            stored = cp.load_chat_transcript()
            self.assertEqual(stored[0]["ts"], "2026-09-30T01:00:00")
            self.assertNotEqual(stored[1]["ts"], "2026-09-30T01:00:00")

    def test_turned_off_nothing_new_is_added_and_nothing_old_is_removed(self):
        project = _FakeProject()
        with _simulate_qgis_with_persist_setting(True, project=project) as cp:
            cp.save_chat_history(self._turn(1))
        with _simulate_qgis_with_persist_setting(False, project=project) as cp:
            cp.save_chat_history(self._turn(1) + self._turn(2))
            self.assertEqual(len(cp.load_chat_transcript()), 2)

    def test_clear_saved_chat_history_empties_transcript_and_window(self):
        project = _FakeProject()
        with _simulate_qgis_with_persist_setting(True, project=project) as cp:
            cp.save_chat_history(self._turn(1) + self._turn(2))
            result = cp.clear_saved_chat_history()
            self.assertTrue(result["success"])
            self.assertEqual(result["removed"], 4)
            self.assertEqual(cp.load_chat_transcript(), [])
            self.assertEqual(cp.load_chat_history(), [])

    def test_a_corrupt_stored_transcript_reads_as_empty_not_an_error(self):
        project = _FakeProject()
        project.entries[("cartogen_ai", "chat_transcript")] = "{not json"
        with _simulate_qgis_with_persist_setting(True, project=project) as cp:
            self.assertEqual(cp.load_chat_transcript(), [])
            cp.save_chat_history(self._turn(1))        # and saving recovers
            self.assertEqual(len(cp.load_chat_transcript()), 2)


if __name__ == "__main__":
    unittest.main()
