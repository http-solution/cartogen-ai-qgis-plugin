# -*- coding: utf-8 -*-
"""
Tests for centralized settings_keys module (infrastructure boundary).
"""
import unittest
from cartogen_ai.infrastructure import settings_keys


class TestSettingsKeys(unittest.TestCase):
    def test_namespace_prefix_on_all_constants(self):
        for name in dir(settings_keys):
            if name.startswith("SETTINGS_") or name.startswith("PROJECT_PROPERTY_"):
                val = getattr(settings_keys, name)
                self.assertTrue(
                    val.startswith("cartogen_ai/"),
                    f"Constant {name}='{val}' does not start with 'cartogen_ai/'",
                )

    def test_helper_functions(self):
        self.assertEqual(settings_keys.auth_id_setting_key("gemini"), "cartogen_ai/auth_id_gemini")
        self.assertEqual(settings_keys.fallback_credential_key("gemini"), "cartogen_ai/gemini_key")
        self.assertEqual(settings_keys.provider_model_list_key("gemini"), "cartogen_ai/gemini_model_list")
        self.assertEqual(settings_keys.workflow_preset_key("my_flow"), "cartogen_ai/workflows/my_flow")


if __name__ == "__main__":
    unittest.main()
