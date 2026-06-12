"""Unit tests for simple_ws_proxy.common.auth.Authenticator."""

import time

from simple_ws_proxy.common.auth import AUTH_TYPE, Authenticator


class TestAuthenticator:
    """Tests for header generation and validation."""

    SECRET = 'test-secret'
    WINDOW = 5

    def _auth(self, secret: str = SECRET, window: int = WINDOW) -> Authenticator:
        return Authenticator(secret, window)

    # ------------------------------------------------------------------
    # make_headers
    # ------------------------------------------------------------------

    def test_make_headers_contains_time_and_authentication(self) -> None:
        headers = self._auth().make_headers()
        assert 'Time' in headers
        assert 'Authentication' in headers

    def test_make_headers_time_is_current_timestamp(self) -> None:
        before = int(time.time())
        headers = self._auth().make_headers()
        after = int(time.time())
        ts = int(headers['Time'])
        assert before <= ts <= after

    def test_make_headers_authentication_starts_with_auth_type(self) -> None:
        headers = self._auth().make_headers()
        assert headers['Authentication'].startswith(f'{AUTH_TYPE} ')

    def test_make_headers_token_is_hex(self) -> None:
        headers = self._auth().make_headers()
        token = headers['Authentication'].split(' ', 1)[1]
        int(token, 16)  # should not raise

    # ------------------------------------------------------------------
    # check — success cases
    # ------------------------------------------------------------------

    def test_check_valid_headers(self) -> None:
        auth = self._auth()
        headers = auth.make_headers()
        assert auth.check(headers['Time'], headers['Authentication']) is True

    def test_check_accepts_timestamp_at_window_boundary(self) -> None:
        auth = self._auth(window=5)
        now = int(time.time())
        for delta in (-5, 0, 5):
            ts = str(now + delta)
            # Build a valid token for this timestamp
            token = auth._make_token(ts)
            assert auth.check(ts, f'{AUTH_TYPE} {token}') is True

    # ------------------------------------------------------------------
    # check — failure cases
    # ------------------------------------------------------------------

    def test_check_missing_time_header(self) -> None:
        auth = self._auth()
        headers = auth.make_headers()
        assert auth.check(None, headers['Authentication']) is False

    def test_check_missing_auth_header(self) -> None:
        auth = self._auth()
        headers = auth.make_headers()
        assert auth.check(headers['Time'], None) is False

    def test_check_both_headers_missing(self) -> None:
        assert self._auth().check(None, None) is False

    def test_check_invalid_time_value(self) -> None:
        auth = self._auth()
        headers = auth.make_headers()
        assert auth.check('not-a-number', headers['Authentication']) is False

    def test_check_time_too_old(self) -> None:
        auth = self._auth(window=5)
        old_ts = str(int(time.time()) - 100)
        token = auth._make_token(old_ts)
        assert auth.check(old_ts, f'{AUTH_TYPE} {token}') is False

    def test_check_time_in_future(self) -> None:
        auth = self._auth(window=5)
        future_ts = str(int(time.time()) + 100)
        token = auth._make_token(future_ts)
        assert auth.check(future_ts, f'{AUTH_TYPE} {token}') is False

    def test_check_wrong_secret(self) -> None:
        sender = self._auth('correct-secret')
        receiver = self._auth('wrong-secret')
        headers = sender.make_headers()
        assert receiver.check(headers['Time'], headers['Authentication']) is False

    def test_check_malformed_auth_header_no_space(self) -> None:
        auth = self._auth()
        headers = auth.make_headers()
        assert auth.check(headers['Time'], 'NoSpaceHere') is False

    def test_check_wrong_auth_type(self) -> None:
        auth = self._auth()
        headers = auth.make_headers()
        token = headers['Authentication'].split(' ', 1)[1]
        assert auth.check(headers['Time'], f'Bearer {token}') is False

    def test_check_tampered_token(self) -> None:
        auth = self._auth()
        headers = auth.make_headers()
        tampered = headers['Authentication'][:-1] + '0'
        assert auth.check(headers['Time'], tampered) is False

    # ------------------------------------------------------------------
    # make_cipher
    # ------------------------------------------------------------------

    def test_make_cipher_returns_cipher_with_correct_key(self) -> None:
        from simple_ws_proxy.common.cipher import Cipher

        auth = self._auth()
        ts = str(int(time.time()))
        cipher = auth.make_cipher(ts)
        assert isinstance(cipher, Cipher)
        # Same inputs must produce the same session key
        assert cipher.session_key == auth.make_cipher(ts).session_key

    def test_make_cipher_different_timestamps_different_keys(self) -> None:
        auth = self._auth()
        c1 = auth.make_cipher('1000000000')
        c2 = auth.make_cipher('2000000000')
        assert c1.session_key != c2.session_key
