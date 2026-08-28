# -*- coding: utf-8 -*-
"""
Authentication and Credential Security Manager for Cartogen AI.
Uses QGIS native QgsAuthManager (encrypted keyring storage) with fallback to QgsSettings.
"""

import traceback

try:
    from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsSettings
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


class CredentialManager:
    """Manages API keys securely using QgsAuthManager when available."""

    AUTH_KEY_PREFIX = "cartogen_ai_auth_id_"

    # Providers whose most recent save_credential() call fell back to plaintext
    # QgsSettings storage instead of the encrypted QgsAuthManager. Checked by
    # ui/settings_dialog.py after saving, so the user gets a one-time warning
    # instead of the fallback happening silently.
    _plaintext_fallback_providers = set()

    @classmethod
    def used_plaintext_fallback(cls, provider: str) -> bool:
        return provider in cls._plaintext_fallback_providers

    # Single canonical mapping of provider -> QgsSettings fallback key, shared by both
    # save_credential and get_credential so they can never drift out of sync with each
    # other (a prior version used two separate, mismatched mappings — a saved OpenRouter/
    # Ollama key would silently land somewhere get_credential never looked).
    LEGACY_SETTINGS_KEYS = {
        "openrouter": "cartogen_ai/api_key",
        "gemini": "cartogen_ai/gemini_key",
        "ollama": "cartogen_ai/ollama_url",
        "openai": "cartogen_ai/openai_key",
        "claude": "cartogen_ai/claude_key",
    }

    @staticmethod
    def save_credential(provider: str, key_value: str) -> bool:
        """Saves API key securely into QgsAuthManager, storing auth ID reference in QgsSettings."""
        if not key_value or not key_value.strip():
            return False

        key_value = key_value.strip()
        CredentialManager._plaintext_fallback_providers.discard(provider)

        if QGIS_AVAILABLE:
            try:
                auth_mgr = QgsApplication.authManager()
                if auth_mgr and not auth_mgr.isDisabled():
                    # Create/update QgsAuthMethodConfig
                    auth_id_setting = f"cartogen_ai/auth_id_{provider}"
                    settings = QgsSettings()
                    existing_auth_id = settings.value(auth_id_setting, "")

                    config = QgsAuthMethodConfig("Basic")
                    if existing_auth_id:
                        config.setId(existing_auth_id)

                    config.setName(f"Cartogen AI ({provider})")
                    config.setConfig("username", provider)
                    config.setConfig("password", key_value)

                    # storeAuthenticationConfig is the QGIS 4.x name (Qt6 migration renamed
                    # it from saveAuthenticationConfig -- verified against the current
                    # QgsAuthManager API docs, which no longer list saveAuthenticationConfig
                    # at all). Try the new name first, fall back to the old one so this still
                    # works on QGIS 3.x, which this plugin also declares support for.
                    save_fn = getattr(auth_mgr, "storeAuthenticationConfig", None) or getattr(auth_mgr, "saveAuthenticationConfig", None)
                    if save_fn and save_fn(config):
                        settings.setValue(auth_id_setting, config.id())
                        return True
            except Exception as e:
                print(f"[CredentialManager] QgsAuthManager save failed, falling back to QgsSettings: {e}")

        # Fallback to QgsSettings — uses the SAME key mapping get_credential reads from.
        # This path stores the key in plaintext (on Windows, the registry), unlike
        # the encrypted QgsAuthManager path above -- flag it so the UI can warn.
        if QGIS_AVAILABLE:
            try:
                settings = QgsSettings()
                fallback_setting = CredentialManager.LEGACY_SETTINGS_KEYS.get(
                    provider, f"cartogen_ai/{provider}_key"
                )
                settings.setValue(fallback_setting, key_value)
                CredentialManager._plaintext_fallback_providers.add(provider)
                return True
            except Exception as e:
                print(f"[CredentialManager] QgsSettings save failed: {e}")
        return False

    @staticmethod
    def save_secure_credential(name: str, secret: str) -> bool:
        """Persist a credential only through QGIS encrypted auth storage."""
        return CredentialManager._save_auth_secret(name, secret)

    @staticmethod
    def save_account_session(session_cookie: str) -> bool:
        """Persist the Cartogen session cookie only in QGIS encrypted auth storage."""
        return CredentialManager._save_auth_secret("account_session", session_cookie)

    @staticmethod
    def get_account_session() -> str:
        return CredentialManager._get_auth_secret("account_session")

    @staticmethod
    def clear_account_session() -> None:
        CredentialManager._delete_auth_secret("account_session")

    @staticmethod
    def _save_auth_secret(name: str, secret: str) -> bool:
        if not secret or not secret.strip() or not QGIS_AVAILABLE:
            return False
        try:
            auth_mgr = QgsApplication.authManager()
            if not auth_mgr or auth_mgr.isDisabled():
                return False
            settings = QgsSettings()
            setting = f"{CredentialManager.AUTH_KEY_PREFIX}{name}"
            config = QgsAuthMethodConfig("Basic")
            existing = settings.value(setting, "")
            if existing:
                config.setId(existing)
            config.setName(f"Cartogen AI ({name})")
            config.setConfig("username", "cartogen-account")
            config.setConfig("password", secret.strip())
            save_fn = getattr(auth_mgr, "storeAuthenticationConfig", None) or getattr(auth_mgr, "saveAuthenticationConfig", None)
            if not save_fn or not save_fn(config):
                return False
            settings.setValue(setting, config.id())
            return True
        except Exception as e:
            print(f"[CredentialManager] secure account session save failed: {e}")
            return False

    @staticmethod
    def _get_auth_secret(name: str) -> str:
        if not QGIS_AVAILABLE:
            return ""
        try:
            settings = QgsSettings()
            auth_id = settings.value(f"{CredentialManager.AUTH_KEY_PREFIX}{name}", "")
            if not auth_id:
                return ""
            auth_mgr = QgsApplication.authManager()
            if not auth_mgr or auth_mgr.isDisabled():
                return ""
            config = QgsAuthMethodConfig()
            if auth_mgr.loadAuthenticationConfig(auth_id, config, True):
                return config.config("password") or ""
        except Exception as e:
            print(f"[CredentialManager] secure account session load failed: {e}")
        return ""

    @staticmethod
    def _delete_auth_secret(name: str) -> None:
        if not QGIS_AVAILABLE:
            return
        try:
            settings = QgsSettings()
            setting = f"{CredentialManager.AUTH_KEY_PREFIX}{name}"
            auth_id = settings.value(setting, "")
            auth_mgr = QgsApplication.authManager()
            if auth_id and auth_mgr and not auth_mgr.isDisabled():
                remove_fn = getattr(auth_mgr, "removeAuthenticationConfig", None)
                if remove_fn:
                    remove_fn(auth_id)
            settings.remove(setting)
        except Exception as e:
            print(f"[CredentialManager] secure account session delete failed: {e}")

    @staticmethod
    def get_credential(provider: str) -> str:
        """Retrieves API key from QgsAuthManager or fallback QgsSettings."""
        if not QGIS_AVAILABLE:
            return ""

        settings = QgsSettings()
        auth_id_setting = f"cartogen_ai/auth_id_{provider}"
        auth_id = settings.value(auth_id_setting, "")

        if auth_id:
            try:
                auth_mgr = QgsApplication.authManager()
                if auth_mgr and not auth_mgr.isDisabled():
                    config = QgsAuthMethodConfig()
                    if auth_mgr.loadAuthenticationConfig(auth_id, config, True):
                        pwd = config.config("password")
                        if pwd:
                            return pwd
            except Exception as e:
                print(f"[CredentialManager] QgsAuthManager load failed: {e}")

        # Fallback to QgsSettings — same mapping save_credential writes to.
        fallback_setting = CredentialManager.LEGACY_SETTINGS_KEYS.get(
            provider, f"cartogen_ai/{provider}_key"
        )
        value = settings.value(fallback_setting, "")
        if value:
            return value

        # Recovery path: earlier versions of this file wrote OpenRouter/Ollama keys to
        # cartogen_ai/{provider}_key (a name get_credential never read back from), so a
        # key entered before this fix would otherwise appear to have vanished. Check there
        # too rather than forcing a re-entry.
        stray_key = f"cartogen_ai/{provider}_key"
        if stray_key != fallback_setting:
            return settings.value(stray_key, "")
        return ""
