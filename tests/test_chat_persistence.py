# -*- coding: utf-8 -*-
import unittest
from contextlib import contextmanager
from cartogen_ai.core.agent.chat_persistence import save_chat_history, load_chat_history


@contextmanager
def _simulate_qgis_with_persist_setting(value):
    """QGIS_AVAILABLE and QgsSettings are only bound at module level when the
    real `qgis.core` import succeeds -- there's no qgis.core in this test
    environment, so both are set directly on the module object to exercise
    the opt-in gating logic without a real QGIS install."""
    import cartogen_ai.core.agent.chat_persistence as cp

    class _FakeSettings:
        def value(self, key, default, type=None):
            return value if key == cp.PERSIST_SETTING_KEY else default

    original_available = cp.QGIS_AVAILABLE
    had_settings_attr = hasattr(cp, "QgsSettings")
    original_settings = getattr(cp, "QgsSettings", None)
    cp.QGIS_AVAILABLE = True
    cp.QgsSettings = _FakeSettings
    try:
        yield cp
    finally:
        cp.QGIS_AVAILABLE = original_available
        if had_settings_attr:
            cp.QgsSettings = original_settings
        else:
            del cp.QgsSettings


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


if __name__ == "__main__":
    unittest.main()
