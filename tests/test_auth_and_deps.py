# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.auth import CredentialManager
from cartogen_ai.core.agent.deps import verify_dependencies, get_dependency_warning_message


class TestAuthAndDeps(unittest.TestCase):
    def test_credential_manager_fallback(self):
        res = CredentialManager.save_credential("test_provider", "secret_key_123")
        # In non-QGIS test environment, fallback save returns True or False safely
        key = CredentialManager.get_credential("test_provider")
        self.assertIsInstance(key, str)

    def test_plaintext_fallback_flag_set_when_auth_manager_disabled(self):
        # A4: when QgsAuthManager is unavailable/disabled, save_credential
        # falls back to plaintext QgsSettings -- used_plaintext_fallback must
        # report that so the Settings dialog can warn the user, instead of it
        # happening silently.
        fake_auth_mgr = MagicMock()
        fake_auth_mgr.isDisabled.return_value = True  # simulates auth manager unavailable
        fake_settings = MagicMock()
        fake_settings.value.return_value = ""

        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.auth.QgsApplication", create=True) as mock_app, \
             patch("cartogen_ai.core.agent.auth.QgsSettings", return_value=fake_settings, create=True):
            mock_app.authManager.return_value = fake_auth_mgr
            result = CredentialManager.save_credential("test_flagged_provider", "sk-fake-value")

        self.assertTrue(result)
        self.assertTrue(CredentialManager.used_plaintext_fallback("test_flagged_provider"))
        # The actual secret value must never appear in the flag/state itself
        self.assertNotIn("sk-fake-value", str(CredentialManager._plaintext_fallback_providers))

    def test_plaintext_fallback_flag_clears_on_successful_encrypted_save(self):
        fake_auth_mgr = MagicMock()
        fake_auth_mgr.isDisabled.return_value = False
        fake_auth_mgr.storeAuthenticationConfig.return_value = True
        fake_settings = MagicMock()
        fake_settings.value.return_value = ""

        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.auth.QgsApplication", create=True) as mock_app, \
             patch("cartogen_ai.core.agent.auth.QgsSettings", return_value=fake_settings, create=True), \
             patch("cartogen_ai.core.agent.auth.QgsAuthMethodConfig", create=True):
            mock_app.authManager.return_value = fake_auth_mgr
            CredentialManager._plaintext_fallback_providers.add("test_clear_provider")
            result = CredentialManager.save_credential("test_clear_provider", "sk-fake-value")

        self.assertTrue(result)
        self.assertFalse(CredentialManager.used_plaintext_fallback("test_clear_provider"))

    def test_verify_dependencies(self):
        deps = verify_dependencies()
        self.assertIn("all_installed", deps)
        self.assertIn("status", deps)
        self.assertIn("missing_packages", deps)
        self.assertIsInstance(deps["status"], dict)

    def test_dependency_warning_message(self):
        msg = get_dependency_warning_message()
        self.assertIsInstance(msg, str)


if __name__ == "__main__":
    unittest.main()
