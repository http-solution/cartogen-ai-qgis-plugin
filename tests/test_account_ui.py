import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestAccountUiContract(unittest.TestCase):
    def test_account_dialog_exposes_registration_login_and_api_key_flow(self):
        source = (ROOT / 'src' / 'cartogen_ai' / 'core' / 'ui' / 'account_dialog.py').read_text(encoding='utf-8')
        for marker in ('Create account', 'Sign in', 'Open account portal', 'Cartogen AI API key', 'save_account_session'):
            self.assertIn(marker, source)
        self.assertIn('CredentialManager.save_secure_credential("cartogen"', source)
        self.assertIn('password is sent only over HTTPS', source)

    def test_settings_exposes_account_entry_point(self):
        source = (ROOT / 'src' / 'cartogen_ai' / 'core' / 'ui' / 'settings_dialog.py').read_text(encoding='utf-8')
        self.assertIn('Manage account', source)
        self.assertIn('CartogenAccountDialog', source)
        self.assertIn('_open_account_dialog', source)

    def test_session_storage_is_separate_from_provider_key_storage(self):
        source = (ROOT / 'src' / 'cartogen_ai' / 'infrastructure' / 'auth.py').read_text(encoding='utf-8')
        self.assertIn('save_account_session', source)
        self.assertIn('account_session', source)
        self.assertIn('cartogen_ai_auth_id_', source)


if __name__ == '__main__':
    unittest.main()
