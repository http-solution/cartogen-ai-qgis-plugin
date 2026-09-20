# -*- coding: utf-8 -*-
"""
Authentication and Credential Security Manager for Cartogen AI.
Uses QGIS native QgsAuthManager (encrypted keyring storage) with fallback to QgsSettings.
"""

try:
    from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsSettings
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

from ..core.logger import log_warning
from .settings_keys import (
    SETTINGS_PROVIDER, SETTINGS_API_KEY, fallback_credential_key, auth_id_setting_key,
)


class CredentialManager:
    """Manages API keys securely using QgsAuthManager when available."""

    AUTH_KEY_PREFIX = "cartogen_ai_auth_id_"

    # P1 fix, 2026-09-20 audit + explicit product policy decision (strict option
    # chosen over an opt-in plaintext-persist path): providers whose key is held
    # ONLY in this process's memory because QgsAuthManager was unavailable/failed.
    # Never written to disk, never survives a QGIS restart. This is now the ONLY
    # fallback -- save_credential() has no way to persist a new key in plaintext,
    # by design, regardless of user consent. See LEGACY_SETTINGS_KEYS/get_credential
    # below for the separate, retained migration path that only READS/REMOVES
    # plaintext keys written by OLDER versions of this file, before this policy.
    _session_credentials = {}
    _session_only_providers = set()

    @classmethod
    def used_session_only_fallback(cls, provider: str) -> bool:
        return provider in cls._session_only_providers

    # Single canonical mapping of provider -> QgsSettings fallback key, shared by both
    # save_credential and get_credential so they can never drift out of sync with each
    # other (a prior version used two separate, mismatched mappings — a saved OpenRouter/
    # Ollama key would silently land somewhere get_credential never looked).
    LEGACY_SETTINGS_KEYS = {
        "openrouter": SETTINGS_API_KEY,
        "gemini": fallback_credential_key("gemini"),
        "ollama": fallback_credential_key("ollama"),
        "openai": fallback_credential_key("openai"),
        "claude": fallback_credential_key("claude"),
    }

    @staticmethod
    def save_credential(provider: str, key_value: str) -> bool:
        """Saves API key securely into QgsAuthManager, storing auth ID reference in
        QgsSettings. If QgsAuthManager is unavailable or fails, the key is held in
        memory for this session only -- it is NEVER written to disk in plaintext.
        Product policy decision, 2026-09-20 (strict option): there is deliberately
        no way to opt into persistent plaintext storage of a NEW key, even with
        explicit user consent -- the audit's standard ("do not store tokens in
        plain QgsSettings") is treated as a hard requirement, not something
        informed consent can waive. A user without a working QgsAuthManager must
        re-enter their key each QGIS session; see auth_system_status() for why
        QgsAuthManager might be disabled and how to fix that at the QGIS level."""
        if not key_value or not key_value.strip():
            return False

        key_value = key_value.strip()
        CredentialManager._session_only_providers.discard(provider)
        CredentialManager._session_credentials.pop(provider, None)

        if QGIS_AVAILABLE:
            auth_id_setting = auth_id_setting_key(provider)
            try:
                auth_mgr = QgsApplication.authManager()
                if auth_mgr and not auth_mgr.isDisabled():
                    # Create/update QgsAuthMethodConfig
                    settings = QgsSettings()
                    existing_auth_id = settings.value(auth_id_setting, "")
                    config = QgsAuthMethodConfig("Basic")
                    if existing_auth_id:
                        config.setId(existing_auth_id)
                    config.setName(f"cartogen_ai_{provider}")
                    config.setConfig("password", key_value)

                    # QGIS 4.x/Qt6 and QGIS 3.x have slightly different method names
                    save_fn = getattr(auth_mgr, "storeAuthenticationConfig", None) or getattr(
                        auth_mgr, "storeConfig", None
                    )
                    if save_fn and save_fn(config):
                        settings.setValue(auth_id_setting, config.id())
                        CredentialManager._delete_plaintext_fallback(provider)
                        return True

                    # storeAuthenticationConfig failed -- commonly a stale auth ID left
                    # over from an earlier session colliding with the new config (live
                    # QGIS warning: "Store config: FAILED because pre-defined config ID
                    # %1 is not unique"). If we leave the stale auth_id_{provider}
                    # setting in place, get_credential() will find it, successfully load
                    # the OLD auth-manager entry, and return the OLD key -- silently
                    # ignoring the new value we're about to fall back to session-only
                    # storage below. Clear it so get_credential() falls through instead.
                    if existing_auth_id:
                        settings.remove(auth_id_setting)
            except Exception as e:
                log_warning(f"QgsAuthManager save failed, falling back to session-only in-memory storage: {e}", tag="CredentialManager")
                try:
                    QgsSettings().remove(auth_id_setting)
                except Exception as ex:
                    log_warning(f"Could not remove stale auth_id_setting: {ex}", tag="CredentialManager")


        # QgsAuthManager unavailable/failed. Session-only, in-memory storage is the
        # only fallback -- see this method's docstring and the class-level comment
        # above _session_credentials for why persistent plaintext was removed
        # entirely rather than made opt-in.
        CredentialManager._session_credentials[provider] = key_value
        CredentialManager._session_only_providers.add(provider)
        return True

    @staticmethod
    def _delete_plaintext_fallback(provider: str) -> None:
        """Migrates away a stale plaintext key once the encrypted store has taken
        over -- "migrate and delete legacy plaintext keys after secure storage
        succeeds", P1 fix, 2026-09-20 audit. Skips ollama: its fallback key holds
        an endpoint URL, not a secret (see get_credential's ollama recovery path),
        so deleting it would silently reset the configured endpoint for no security
        benefit."""
        if not QGIS_AVAILABLE or provider == "ollama":
            return
        try:
            settings = QgsSettings()
            fallback_setting = CredentialManager.LEGACY_SETTINGS_KEYS.get(
                provider, fallback_credential_key(provider)
            )
            if settings.value(fallback_setting, ""):
                settings.remove(fallback_setting)
            stray_key = fallback_credential_key(provider)
            if stray_key != fallback_setting and settings.value(stray_key, ""):
                settings.remove(stray_key)
        except Exception as e:
            log_warning(f"Could not remove legacy plaintext key: {e}", tag="CredentialManager")

    @staticmethod
    def auth_system_status() -> dict:
        """Reports whether QGIS's encrypted credential store (QgsAuthManager)
        is disabled, and if so, the documented causes and fixes -- so a
        session-only-storage fallback isn't left as an unexplained "wasn't
        available" message (see used_session_only_fallback above).

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
        for ui/settings_dialog.py's session-only-storage notice. Empty string
        when the auth system isn't disabled (or QGIS/status can't be read) --
        nothing to add to the notice in that case."""
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

    _MISSING_KEY_MESSAGE = (
        "**No API key configured for the selected provider.** Open **Settings** "
        "(the ⚙ gear icon, top right) to pick a provider and add its API key "
        "-- or switch to Ollama to run fully locally with no key needed."
    )

    @classmethod
    def missing_credential_message(cls, provider: str = None, client=None) -> str:
        """Returns a friendly, actionable chat message if there's no usable
        credential to send a request with, or None if it's fine to proceed.
        Meant to be checked BEFORE a request goes out, so the user sees this
        instead of the provider's raw 401.

        Prefers checking the real client object when one is given (pass the
        agent's actual `.client`): every provider client except Ollama's
        stores its key as `self.api_key` (see providers/openrouter.py,
        providers/gemini.py, etc.); Ollama has no such attribute at all (it
        uses `self.endpoint_url` instead, and needs no key). An object with
        no `api_key` attribute -- Ollama's client, or one this check doesn't
        recognize, including any test double -- is left alone rather than
        guessed about: this is a UX nicety, not a security gate, so silence
        is the safe default when unsure.

        With no client given, falls back to reading the configured provider
        setting and saved credential directly -- used by the welcome-message
        nudge, which may run before any agent has been constructed yet.
        Outside QGIS there is no real settings store (and no UI to show the
        message in), so this always returns None there -- same
        QGIS_AVAILABLE-guard shape as services/prompt_refiner.py's
        is_prompt_preview_enabled(), never raises."""
        if client is not None:
            if not hasattr(client, "api_key"):
                return None
            return None if client.api_key else cls._MISSING_KEY_MESSAGE

        if not QGIS_AVAILABLE:
            return None
        try:
            settings = QgsSettings()
            if provider is None:
                provider = settings.value(SETTINGS_PROVIDER, "openrouter")
            if provider == "ollama":
                return None
            if CredentialManager.get_credential(provider):
                return None
        except Exception:
            return None
        return cls._MISSING_KEY_MESSAGE

    @staticmethod
    def get_credential(provider: str) -> str:
        """Retrieves API key from QgsAuthManager or fallback QgsSettings."""
        if not QGIS_AVAILABLE:
            return ""

        settings = QgsSettings()
        auth_id_setting = auth_id_setting_key(provider)
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
                log_warning(f"QgsAuthManager load failed: {e}", tag="CredentialManager")

        # Session-only in-memory credential (see save_credential's default fallback
        # path) -- checked before plaintext QgsSettings since it's always the more
        # recently saved value when both exist.
        if provider in CredentialManager._session_credentials:
            return CredentialManager._session_credentials[provider]

        # Fallback to QgsSettings — same mapping save_credential writes to.
        fallback_setting = CredentialManager.LEGACY_SETTINGS_KEYS.get(
            provider, fallback_credential_key(provider)
        )
        value = settings.value(fallback_setting, "")
        if value:
            return value

        # Recovery path: earlier versions of this file wrote OpenRouter/Ollama keys to
        # cartogen_ai/{provider}_key (a name get_credential never read back from), so a
        # key entered before this fix would otherwise appear to have vanished. Check there
        # too rather than forcing a re-entry.
        stray_key = fallback_credential_key(provider)
        if stray_key != fallback_setting:
            value = settings.value(stray_key, "")
            if value:
                return value

        # Second recovery path, Ollama-specific: before the settings-centralization pass
        # (LEGACY_SETTINGS_KEYS moved "ollama" from the literal "cartogen_ai/ollama_url"
        # to fallback_credential_key("ollama") == "cartogen_ai/ollama_key"), any endpoint
        # URL saved under the old literal name is invisible to both lookups above -- the
        # stray_key check just above resolves to the SAME new key for ollama, so it can
        # never reach the old one. Confirmed via a code-review pass (2026-09-20) that no
        # other migration path exists; a user who configured Ollama before this rename
        # would otherwise have get_credential("ollama") silently return "" and OllamaClient
        # fall back to its http://localhost:11434 default with no error at all.
        if provider == "ollama":
            return settings.value("cartogen_ai/ollama_url", "")
        return ""

