import unittest
from unittest.mock import Mock, patch

from cartogen_ai.core.agent.account import CartogenAccountClient, normalize_account_base_url


class TestCartogenAccountClient(unittest.TestCase):
    def test_normalize_base_url_removes_api_suffix_and_slash(self):
        self.assertEqual(normalize_account_base_url('https://example.test/api/'), 'https://example.test')

    def test_normalize_base_url_rejects_plain_http_for_real_hosts(self):
        # BUG-2026-09-08-1: the account dialog tells the user their password is sent
        # only over HTTPS -- plain http must be rejected for any non-loopback host.
        with self.assertRaises(ValueError):
            normalize_account_base_url('http://cartogen.example.com')

    def test_normalize_base_url_allows_plain_http_for_localhost_dev(self):
        # Local development against the default http://localhost:3000 must keep working.
        self.assertEqual(
            normalize_account_base_url('http://localhost:3000/api'),
            'http://localhost:3000',
        )
        self.assertEqual(
            normalize_account_base_url('http://127.0.0.1:3000'),
            'http://127.0.0.1:3000',
        )

    def test_normalize_base_url_still_accepts_https_for_real_hosts(self):
        self.assertEqual(
            normalize_account_base_url('https://cartogen.example.com/api/'),
            'https://cartogen.example.com',
        )

    @patch('cartogen_ai.core.agent.account.requests.Session.request')
    def test_register_returns_activation_state_without_exposing_secret(self, request):
        request.return_value = Mock(status_code=202, ok=True, json=lambda: {
            'ok': True, 'verification_required': True,
            'message': 'Activate your account before signing in.',
        })
        client = CartogenAccountClient('https://example.test')
        result = client.register('person@example.test', 'password-never-printed', 'Person', 'Example')
        self.assertEqual(result['status'], 'verification_required')
        self.assertNotIn('password-never-printed', str(result))
        request.assert_called_once()
        self.assertEqual(request.call_args.kwargs['json']['password'], 'password-never-printed')

    @patch('cartogen_ai.core.agent.account.requests.Session.request')
    def test_login_returns_session_token_only_in_private_result(self, request):
        request.return_value = Mock(status_code=200, ok=True, json=lambda: {'ok': True, 'access_token': 'secret-token'})
        result = CartogenAccountClient('https://example.test').login('person@example.test', 'password-never-printed')
        self.assertEqual(result['access_token'], 'secret-token')
        self.assertEqual(request.call_args.kwargs['timeout'], 15)

    @patch('cartogen_ai.core.agent.account.requests.Session.request')
    def test_current_user_uses_bearer_session_and_returns_safe_identity(self, request):
        request.return_value = Mock(status_code=200, ok=True, json=lambda: {'data': {'id': 'u1', 'email': 'person@example.test'}})
        result = CartogenAccountClient('https://example.test').current_user('secret-token')
        self.assertEqual(result, {'id': 'u1', 'email': 'person@example.test'})
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'], 'Bearer secret-token')

    @patch('cartogen_ai.core.agent.account.requests.Session.request')
    def test_login_maps_auth_failure_to_safe_error(self, request):
        request.return_value = Mock(status_code=401, ok=False, json=lambda: {'error': 'Invalid credentials'})
        with self.assertRaisesRegex(RuntimeError, 'Invalid credentials'):
            CartogenAccountClient('https://example.test').login('person@example.test', 'wrong')


if __name__ == '__main__':
    unittest.main()
