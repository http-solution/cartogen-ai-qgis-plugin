from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)
from qgis.core import QgsSettings

from ..agent.account import CartogenAccountClient, DEFAULT_ACCOUNT_BASE_URL
from ..agent.auth import CredentialManager
from ..agent.qgis_compat import enum_member

ACCOUNT_URL_KEY = "cartogen_ai/account_base_url"

# QGIS 4.x/Qt6 requires these reached through their enum type
# (QLineEdit.EchoMode.Password, QDialogButtonBox.StandardButton.Close);
# QGIS 3.x/Qt5 exposes them flat. Resolved once here via the same
# enum_member() helper the rest of the codebase uses for this, rather than
# hardcoding one form -- see agent/qgis_compat.py.
_ECHO_PASSWORD = enum_member("Password", QLineEdit)
_BUTTONBOX_CLOSE = enum_member("Close", QDialogButtonBox)


class CartogenAccountDialog(QDialog):
    """Account registration/sign-in UI for hosted Cartogen AI access."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cartogen AI — Account")
        self.setMinimumWidth(460)
        self.settings = QgsSettings()
        self.client = None
        self._build_ui()
        self._refresh_session_state()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Use a Cartogen AI account for hosted API access. Your password is sent only over HTTPS "
            "to the configured Cartogen service and is never saved by the plugin."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.base_url_edit = QLineEdit(self.settings.value(ACCOUNT_URL_KEY, DEFAULT_ACCOUNT_BASE_URL))
        self.base_url_edit.setPlaceholderText(DEFAULT_ACCOUNT_BASE_URL)
        form.addRow("Account service URL:", self.base_url_edit)
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("name@example.org")
        form.addRow("Email:", self.email_edit)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(_ECHO_PASSWORD)
        self.password_edit.setPlaceholderText("At least 12 characters")
        form.addRow("Password:", self.password_edit)
        self.application_key_edit = QLineEdit(CredentialManager.get_credential("cartogen"))
        self.application_key_edit.setEchoMode(_ECHO_PASSWORD)
        self.application_key_edit.setPlaceholderText("Assigned cg_live_… key")
        form.addRow("Cartogen AI API key:", self.application_key_edit)
        self.first_name_edit = QLineEdit()
        form.addRow("First name (registration):", self.first_name_edit)
        self.last_name_edit = QLineEdit()
        form.addRow("Last name (registration):", self.last_name_edit)
        layout.addLayout(form)

        # BUG-2026-09-08-2 fix (2026-09-08): GDPR F2/addendum -- this dialog collects real
        # personal data (email/name/password) with no privacy notice anywhere before today.
        # Short, static, and honest about what this plugin does and doesn't control: it
        # sends the fields to the configured service and doesn't itself retain email/name,
        # but has no visibility into that service's own retention/deletion practice --
        # see docs/GDPR_HOSTED_ACCOUNT_ADDENDUM_2026-09-08.md for the full inventory.
        self.privacy_notice_label = QLabel(
            "Privacy notice: creating an account or signing in sends your email, name, and "
            "password to the Cartogen service at the URL above, to create or authenticate "
            "your account there. This plugin does not store your email or name -- only an "
            "encrypted session token, once you're signed in -- and never logs your password. "
            "How that service itself stores, retains, or lets you delete your account data is "
            "outside this plugin's control; check with whoever operates it. \"Sign out\" "
            "removes the session token stored on this machine."
        )
        self.privacy_notice_label.setWordWrap(True)
        self.privacy_notice_label.setStyleSheet("color: palette(mid); font-size: 90%;")
        layout.addWidget(self.privacy_notice_label)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.register_button = QPushButton("Create account")
        self.register_button.clicked.connect(self._register)
        self.login_button = QPushButton("Sign in")
        self.login_button.clicked.connect(self._login)
        self.portal_button = QPushButton("Open account portal")
        self.portal_button.clicked.connect(self._open_portal)
        self.signout_button = QPushButton("Sign out")
        self.signout_button.clicked.connect(self._sign_out)
        actions.addWidget(self.register_button)
        actions.addWidget(self.login_button)
        actions.addWidget(self.portal_button)
        actions.addWidget(self.signout_button)
        layout.addLayout(actions)

        buttons = QDialogButtonBox(_BUTTONBOX_CLOSE)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_client(self):
        try:
            self.settings.setValue(ACCOUNT_URL_KEY, self.base_url_edit.text().strip())
            return CartogenAccountClient(
                self.base_url_edit.text(),
                session_cookie=CredentialManager.get_account_session(),
            )
        except ValueError as error:
            self._show_error(str(error))
            return None

    def _refresh_session_state(self):
        cookie = CredentialManager.get_account_session()
        if not cookie:
            self.status_label.setText("Not signed in. Create an account or sign in to connect hosted Cartogen AI access.")
            self.signout_button.setEnabled(False)
            return
        self.client = self._make_client()
        if not self.client:
            return
        try:
            user = self.client.current_user()
            self.email_edit.setText(user.get("email", ""))
            name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
            self.status_label.setText(f"Signed in as {name or user.get('email', 'Cartogen account')}.")
            self.signout_button.setEnabled(True)
        except Exception:
            CredentialManager.clear_account_session()
            self.status_label.setText("Saved Cartogen session is no longer valid. Please sign in again.")
            self.signout_button.setEnabled(False)

    def _save_application_key(self):
        key = self.application_key_edit.text().strip()
        if not key:
            return True
        if not CredentialManager.save_secure_credential("cartogen", key):
            raise RuntimeError("QGIS encrypted credential storage is unavailable; the API key was not saved")
        return True

    def _login(self):
        client = self._make_client()
        if not client:
            return
        try:
            client.login(self.email_edit.text(), self.password_edit.text())
            self._save_application_key()
            cookie = client.session_cookie()
            if not cookie or not CredentialManager.save_account_session(cookie):
                raise RuntimeError("QGIS encrypted credential storage is unavailable; the session was not saved")
            self.password_edit.clear()
            self.client = client
            self._refresh_session_state()
        except Exception as error:
            self._show_error(str(error))

    def _register(self):
        client = self._make_client()
        if not client:
            return
        try:
            result = client.register(
                self.email_edit.text(), self.password_edit.text(),
                self.first_name_edit.text(), self.last_name_edit.text(),
            )
            self.password_edit.clear()
            if result["status"] == "verification_required":
                self.status_label.setText(result["message"])
                return
            self.status_label.setText("Account created. Signing in…")
            self._login()
        except Exception as error:
            self._show_error(str(error))

    def _sign_out(self):
        client = self._make_client()
        try:
            if client:
                client.logout()
        except Exception:
            pass
        CredentialManager.clear_account_session()
        self.client = None
        self.status_label.setText("Signed out. Hosted Cartogen AI API access is disconnected.")
        self.signout_button.setEnabled(False)

    def _open_portal(self):
        try:
            url = CartogenAccountClient(self.base_url_edit.text()).base_url
            QDesktopServices.openUrl(QUrl(url))
        except ValueError as error:
            self._show_error(str(error))

    def _show_error(self, message):
        QMessageBox.warning(self, "Cartogen AI account", message)
