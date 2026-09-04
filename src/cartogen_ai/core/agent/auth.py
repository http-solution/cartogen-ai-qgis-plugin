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
    def auth_system_status() -> dict:
        """Reports whether QGIS's encrypted credential store (QgsAuthManager)
        is disabled, and if so, the documented causes and fixes -- so a
        plaintext-fallback save isn't left as an unexplained "wasn't
        available" message (see used_plaintext_fallback above).

        QGIS's own API gives no machine-readable reason for isDisabled()
        (there is no authManager().disabledReason() or similar) -- so this
        cannot diagnose WHICH cause applies on a given machine, only report
        that it IS disabled and list the causes QGIS's own issue tracker
        documents:

        1. A network proxy configured with an authentication-config
           (authcfg) reference disables the whole auth system at startup --
           a regression confirmed on QGIS 3.40.4+
           (github.com/qgis/QGIS/issues/61043), fix submitted as PR #64242.
        2. The QCA OpenSSL backend (qca-ossl / qca-qt6-ossl) that the auth
           database's encryption depends on is missing or failed to load --
           the long-standing, cross-platform root cause predating this
           specific regression (e.g. Red Hat bug 1396818, "QGIS packages
           needs qca-ossl dependency").

        Neither is fixable from inside this plugin's own package: this
        plugin's plugin_dependencies=qpip (see metadata.txt) only installs
        Python packages listed in requirements.txt into QGIS's Python
        environment -- it has no mechanism to install or repair QGIS's own
        native Qt/QCA libraries, or to change its proxy settings. Both
        fixes happen in QGIS itself, not by installing anything for this
        plugin."""
        if not QGIS_AVAILABLE:
            return {"disabled": None}
        try:
            auth_mgr = QgsApplication.authManager()
            disabled = bool(auth_mgr is None or auth_mgr.isDisabled())
        except Exception:
            return {"disabled": None}
        if not disabled:
            return {"disabled": False}
        return {
            "disabled": True,
            "known_causes": [
                {
                    "cause": "A network proxy has an authentication configuration (authcfg) set.",
                    "fix": "Settings -> Options -> Network -> Proxy: clear any saved "
                           "authentication configuration on the proxy entry, then restart QGIS. "
                           "Known QGIS regression since 3.40.4 -- github.com/qgis/QGIS/issues/61043.",
                },
                {
                    "cause": "The QCA OpenSSL plugin (qca-ossl / qca-qt6-ossl) is missing or failed to load.",
                    "fix": "Repair or reinstall QGIS itself (via OSGeo4W Setup, ensure the "
                           "QCA/OpenSSL component is selected; on the standalone Windows "
                           "installer, a clean reinstall usually restores it). This is a QGIS "
                           "dependency, not something a QGIS plugin package can install.",
                },
            ],
        }

    @staticmethod
    def get_auth_system_diagnostic_message() -> str:
        """Formats auth_system_status() into a short, user-facing explanation
        for ui/settings_dialog.py's plaintext-fallback warning. Empty string
        when the auth system isn't disabled (or QGIS/status can't be read) --
        nothing to add to the warning in that case."""
        status = CredentialManager.auth_system_status()
        if not status.get("disabled"):
            return ""
        lines = [
            "This isn't something Cartogen AI's own installer can fix -- it only installs "
            "Python packages (via qpip), never QGIS's native Qt/QCA libraries or its "
            "settings. Two documented causes:"
        ]
        for i, item in enumerate(status["known_causes"], start=1):
            lines.append("%d. %s\n   Fix: %s" % (i, item["cause"], item["fix"]))
        return "\n\n".join(lines)

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
