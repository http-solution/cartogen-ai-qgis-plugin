# -*- coding: utf-8 -*-
"""The plugin-directory build offers only tested providers (settings_keys.ENABLED_PROVIDERS).
Pure-Python checks: no QGIS needed."""
import re
import unittest
from pathlib import Path

from cartogen_ai.infrastructure.settings_keys import (
    DEFAULT_PROVIDER, ENABLED_PROVIDERS, normalize_provider,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "cartogen_ai"


class TestEnabledProviders(unittest.TestCase):
    def test_enabled_set_is_the_agreed_four(self):
        self.assertEqual(set(ENABLED_PROVIDERS), {"openrouter", "gemini", "ollama", "cartogen"})

    def test_default_is_enabled(self):
        self.assertIn(DEFAULT_PROVIDER, ENABLED_PROVIDERS)

    def test_enabled_values_pass_through(self):
        for p in ENABLED_PROVIDERS:
            self.assertEqual(normalize_provider(p), p)

    def test_disabled_or_unknown_saved_value_falls_back(self):
        for stale in ("openai", "claude", "", None, "nonsense"):
            self.assertEqual(normalize_provider(stale), DEFAULT_PROVIDER)

    def test_dock_quick_switcher_lists_only_enabled(self):
        from cartogen_ai.core.ui.dock_constants import PROVIDER_CHOICES
        self.assertEqual({v for _, v in PROVIDER_CHOICES}, {"openrouter", "gemini", "ollama"})

    def test_settings_dialog_filters_providers(self):
        # settings_dialog imports Qt unconditionally, so check the source rather than import it.
        text = (SRC / "core" / "ui" / "settings_dialog.py").read_text(encoding="utf-8")
        self.assertRegex(text, r'PROVIDERS = \[e for e in _ALL_PROVIDERS if e\["value"\] in ENABLED_PROVIDERS\]')

    def test_orchestrator_normalizes_saved_provider(self):
        text = (SRC / "core" / "agent" / "agent_orchestrator.py").read_text(encoding="utf-8")
        self.assertTrue(re.search(r"provider_name = normalize_provider\(", text))


if __name__ == "__main__":
    unittest.main()
