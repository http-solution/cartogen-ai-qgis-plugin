# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.auth import CredentialManager
from cartogen_ai.core.agent.deps import verify_dependencies, get_dependency_warning_message


class TestAuthAndDeps(unittest.TestCase):
    def test_credential_manager_fallback(self):
        res = CredentialManager.save_credential("test_provider", "secret_key_123")
        # In non-QGIS test environment, fallback save returns True or False safely
        self.assertIsInstance(res, bool)
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

    def test_save_after_stale_auth_id_failure_returns_new_value_not_old(self):
        # Real bug, reproduced live 2026-09-16 (see commit 7da0112's message):
        # when storeAuthenticationConfig() fails against a stale/broken auth
        # ID left over from an earlier session ("Store config: FAILED because
        # pre-defined config ID %1 is not unique"), save_credential() used to
        # fall through to the plaintext fallback and report success WITHOUT
        # clearing the stale auth_id_{provider} QgsSettings entry.
        # get_credential() checks that entry first, so it kept loading the
        # OLD auth-manager config and returning the OLD key -- silently
        # ignoring the new value actually written to the plaintext fallback.
        store = {"cartogen_ai/auth_id_test_stale_provider": "old-broken-auth-id"}

        class FakeSettings:
            def value(self, key, default=""):
                return store.get(key, default)

            def setValue(self, key, value):
                store[key] = value

            def remove(self, key):
                store.pop(key, None)

        fake_auth_mgr = MagicMock()
        fake_auth_mgr.isDisabled.return_value = False
        fake_auth_mgr.storeAuthenticationConfig.return_value = False  # simulates the collision failure

        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.auth.QgsApplication", create=True) as mock_app, \
             patch("cartogen_ai.core.agent.auth.QgsSettings", side_effect=FakeSettings, create=True), \
             patch("cartogen_ai.core.agent.auth.QgsAuthMethodConfig", create=True):
            mock_app.authManager.return_value = fake_auth_mgr
            result = CredentialManager.save_credential("test_stale_provider", "brand-new-key")

        self.assertTrue(result)
        self.assertTrue(CredentialManager.used_plaintext_fallback("test_stale_provider"))
        # The stale auth_id reference must be cleared, not left dangling.
        self.assertNotIn("cartogen_ai/auth_id_test_stale_provider", store)

        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.auth.QgsApplication", create=True) as mock_app, \
             patch("cartogen_ai.core.agent.auth.QgsSettings", side_effect=FakeSettings, create=True), \
             patch("cartogen_ai.core.agent.auth.QgsAuthMethodConfig", create=True):
            mock_app.authManager.return_value = fake_auth_mgr
            key = CredentialManager.get_credential("test_stale_provider")

        self.assertEqual(key, "brand-new-key")

    def test_save_credential_reuses_existing_auth_id_on_resave(self):
        # Real bug found in a code-review pass (2026-09-20): save_credential() used to build
        # a QgsAuthMethodConfig() with no id() reuse at all, so re-saving/rotating an
        # already-configured provider's key created a brand-new auth-DB entry every time
        # instead of updating the existing one in place -- the old entry was never removed.
        # Confirmed via git log that a `config.setId(existing_auth_id)` call existed before
        # commit 308aaab silently dropped it.
        store = {"cartogen_ai/auth_id_test_resave_provider": "existing-auth-id-abc"}

        class FakeSettings:
            def value(self, key, default=""):
                return store.get(key, default)

            def setValue(self, key, value):
                store[key] = value

            def remove(self, key):
                store.pop(key, None)

        fake_auth_mgr = MagicMock()
        fake_auth_mgr.isDisabled.return_value = False
        fake_auth_mgr.storeAuthenticationConfig.return_value = True
        fake_config = MagicMock()

        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.auth.QgsApplication", create=True) as mock_app, \
             patch("cartogen_ai.core.agent.auth.QgsSettings", side_effect=FakeSettings, create=True), \
             patch("cartogen_ai.core.agent.auth.QgsAuthMethodConfig", return_value=fake_config, create=True):
            mock_app.authManager.return_value = fake_auth_mgr
            result = CredentialManager.save_credential("test_resave_provider", "rotated-key-value")

        self.assertTrue(result)
        fake_config.setId.assert_called_once_with("existing-auth-id-abc")

    def test_get_credential_ollama_falls_back_to_legacy_url_key(self):
        # Real bug found in a code-review pass (2026-09-20): LEGACY_SETTINGS_KEYS['ollama']
        # was renamed from the literal 'cartogen_ai/ollama_url' to the generic
        # 'cartogen_ai/ollama_key' pattern with no migration -- a user who saved an Ollama
        # endpoint URL before the rename would have get_credential('ollama') silently return
        # "" after upgrading, with no error, falling back to the localhost default.
        fake_settings = MagicMock()

        def fake_value(key, default=""):
            if key == "cartogen_ai/ollama_url":
                return "http://my-remote-ollama-host:11434/v1/chat/completions"
            return default

        fake_settings.value.side_effect = fake_value
        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.auth.QgsSettings", return_value=fake_settings, create=True):
            key = CredentialManager.get_credential("ollama")

        self.assertEqual(key, "http://my-remote-ollama-host:11434/v1/chat/completions")

    def test_missing_credential_message_none_outside_qgis(self):
        # QGIS_AVAILABLE is False in this test environment -- no real settings
        # store exists, so the no-client fallback path must return None
        # (never raise, never guess).
        self.assertIsNone(CredentialManager.missing_credential_message())

    def test_missing_credential_message_client_with_empty_key(self):
        # The real path: check the agent's actual client object. Every
        # provider client except Ollama's stores its key as self.api_key
        # (providers/openrouter.py etc.) -- this is the shape a real,
        # unconfigured OpenRouterClient/GeminiClient/... has.
        fake_client = MagicMock(spec=["api_key"])
        fake_client.api_key = ""
        msg = CredentialManager.missing_credential_message(client=fake_client)
        self.assertIsNotNone(msg)
        self.assertIn("Settings", msg)

    def test_missing_credential_message_client_with_real_key(self):
        fake_client = MagicMock(spec=["api_key"])
        fake_client.api_key = "sk-or-v1-real-key"
        self.assertIsNone(CredentialManager.missing_credential_message(client=fake_client))

    def test_missing_credential_message_client_without_api_key_attr_is_left_alone(self):
        # Ollama's client has no api_key attribute at all (it uses
        # endpoint_url instead) -- and so does a test double that doesn't
        # model either shape. Both must be left alone rather than guessed
        # about: this check is a UX nicety, not a security gate, and a false
        # positive here would incorrectly block a working Ollama setup (or,
        # as originally found, silently break every existing UI test that
        # passes a fake agent with a fake client).
        class _NoApiKeyClient:
            pass
        self.assertIsNone(CredentialManager.missing_credential_message(client=_NoApiKeyClient()))

    def test_missing_credential_message_no_client_reads_settings(self):
        fake_settings = MagicMock()
        fake_settings.value.return_value = "openrouter"
        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.auth.QgsSettings", return_value=fake_settings, create=True), \
             patch.object(CredentialManager, "get_credential", return_value=""):
            msg = CredentialManager.missing_credential_message()
        self.assertIsNotNone(msg)

    def test_missing_credential_message_no_client_ollama_never_needs_a_key(self):
        # Ollama's "key" field is a local endpoint URL, not a credential --
        # an empty one still means "the default local server", not "missing".
        fake_settings = MagicMock()
        fake_settings.value.return_value = "ollama"
        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.auth.QgsSettings", return_value=fake_settings, create=True), \
             patch.object(CredentialManager, "get_credential", return_value=""):
            msg = CredentialManager.missing_credential_message(provider="ollama")
        self.assertIsNone(msg)

    def test_verify_dependencies(self):
        deps = verify_dependencies()
        self.assertIn("all_installed", deps)
        self.assertIn("status", deps)
        self.assertIn("missing_packages", deps)
        self.assertIsInstance(deps["status"], dict)

    def test_dependency_warning_message(self):
        msg = get_dependency_warning_message()
        self.assertIsInstance(msg, str)


class TestAuthSystemDiagnostic(unittest.TestCase):
    """CredentialManager.auth_system_status()/get_auth_system_diagnostic_message()
    -- surfaces WHY QgsAuthManager is disabled (and what to do about it)
    instead of leaving the plaintext-fallback warning in
    ui/settings_dialog.py unexplained. Screenshot-confirmed real-world
    trigger: a live QGIS 4.2 session with authManager().isDisabled() True."""

    def test_degrades_outside_qgis(self):
        status = CredentialManager.auth_system_status()
        self.assertIsNone(status["disabled"])
        self.assertEqual(CredentialManager.get_auth_system_diagnostic_message(), "")

    def test_reports_not_disabled_when_auth_manager_is_fine(self):
        fake_auth_mgr = MagicMock()
        fake_auth_mgr.isDisabled.return_value = False
        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True),              patch("cartogen_ai.core.agent.auth.QgsApplication", create=True) as mock_app:
            mock_app.authManager.return_value = fake_auth_mgr
            status = CredentialManager.auth_system_status()
            message = CredentialManager.get_auth_system_diagnostic_message()

        self.assertEqual(status, {"disabled": False})
        self.assertEqual(message, "")

    def test_reports_disabled_with_known_causes(self):
        fake_auth_mgr = MagicMock()
        fake_auth_mgr.isDisabled.return_value = True
        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True),              patch("cartogen_ai.core.agent.auth.QgsApplication", create=True) as mock_app:
            mock_app.authManager.return_value = fake_auth_mgr
            status = CredentialManager.auth_system_status()
            message = CredentialManager.get_auth_system_diagnostic_message()

        self.assertTrue(status["disabled"])
        self.assertEqual(len(status["known_causes"]), 2)
        for cause in status["known_causes"]:
            self.assertIn("cause", cause)
            self.assertIn("fix", cause)
        # The message must make explicit that this plugin's own installer
        # (qpip/requirements.txt) cannot fix this -- the whole reason this
        # diagnostic exists is to correct the assumption that it could.
        self.assertIn("qpip", message)
        self.assertIn("1.", message)
        self.assertIn("2.", message)

    def test_none_auth_manager_is_treated_as_disabled(self):
        # QgsApplication.authManager() returning None is a real possibility
        # (e.g. called too early in QGIS startup) -- must be handled the
        # same as isDisabled() True, not crash on .isDisabled() of None.
        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True),              patch("cartogen_ai.core.agent.auth.QgsApplication", create=True) as mock_app:
            mock_app.authManager.return_value = None
            status = CredentialManager.auth_system_status()

        self.assertTrue(status["disabled"])

    def test_exception_querying_auth_manager_is_handled(self):
        with patch("cartogen_ai.core.agent.auth.QGIS_AVAILABLE", True),              patch("cartogen_ai.core.agent.auth.QgsApplication", create=True) as mock_app:
            mock_app.authManager.side_effect = RuntimeError("boom")
            status = CredentialManager.auth_system_status()
            message = CredentialManager.get_auth_system_diagnostic_message()

        self.assertIsNone(status["disabled"])
        self.assertEqual(message, "")


if __name__ == "__main__":
    unittest.main()
