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


class TestAccountClientThroughQgis(unittest.TestCase):
    """Inside QGIS the account client goes through core/net.request (QGIS's proxy/auth/SSL settings) and keeps the session cookie itself.
    net.request is patched here; tests/test_net_live.py covers the real call."""

    def _client(self, **kw):
        with patch('cartogen_ai.core.agent.account.net.QGIS_NETWORK_AVAILABLE', True):
            return CartogenAccountClient('https://example.test', **kw)

    def test_login_sends_json_and_keeps_the_session_cookie_for_the_next_call(self):
        client = self._client()
        replies = [
            (200, [('Content-Type', 'application/json'), ('Set-Cookie', 'cartogen_session=abc123; Path=/; HttpOnly')], b'{"ok": true}'),
            (200, [], b'{"user": {"id": "u1", "email": "p@example.test", "extra": 1}}'),
        ]
        with patch('cartogen_ai.core.agent.account.net.request', side_effect=replies) as req:
            self.assertEqual(client.login('p@example.test', 'pw')['status'], 'authenticated')
            self.assertEqual(client.session_cookie(), 'abc123')
            self.assertEqual(client.current_user(), {'id': 'u1', 'email': 'p@example.test'})
        first, second = req.call_args_list
        self.assertEqual(first.args[0:2], ('POST', 'https://example.test/auth/login'))
        self.assertEqual(first.args[3], b'{"email": "p@example.test", "password": "pw"}')
        self.assertNotIn('Cookie', first.args[2])
        self.assertEqual(second.args[2]['Cookie'], 'cartogen_session=abc123')

    def test_a_stored_cookie_is_sent_and_logout_forgets_it(self):
        client = self._client(session_cookie='stored')
        self.assertEqual(client.session_cookie(), 'stored')
        with patch('cartogen_ai.core.agent.account.net.request', return_value=(200, [], b'{}')) as req:
            client.logout()
        self.assertEqual(req.call_args.args[2]['Cookie'], 'cartogen_session=stored')
        self.assertEqual(client.session_cookie(), '')

    def test_an_emptied_cookie_is_dropped(self):
        client = self._client(session_cookie='stored')
        with patch('cartogen_ai.core.agent.account.net.request',
                   return_value=(200, [('Set-Cookie', 'cartogen_session=; Max-Age=0; Path=/')], b'{}')):
            client.registration_status()
        self.assertEqual(client.session_cookie(), '')

    def test_http_error_status_becomes_a_safe_runtime_error_with_the_status(self):
        client = self._client()
        with patch('cartogen_ai.core.agent.account.net.request', return_value=(401, [], b'{"error": "Invalid credentials"}')):
            with self.assertRaisesRegex(RuntimeError, 'Invalid credentials') as cm:
                client.login('p@example.test', 'wrong')
        self.assertEqual(cm.exception.status_code, 401)

    def test_no_answer_becomes_one_safe_message(self):
        from cartogen_ai.core import net
        client = self._client()
        with patch('cartogen_ai.core.agent.account.net.request', side_effect=net.NetworkError('refused')):
            with self.assertRaisesRegex(RuntimeError, 'could not be reached') as cm:
                client.login('p@example.test', 'pw-never-printed')
        self.assertNotIn('pw-never-printed', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
