"""Authentication helpers shared between server and client."""

import hashlib
import hmac
import logging
import time

from simple_ws_proxy.common.cipher import Cipher

logger = logging.getLogger(__name__)

AUTH_TYPE = 'SimpleProxy'


class Authenticator:
    """Generates and validates ``Time`` / ``Authentication`` HTTP headers.

    Args:
        secret_key:  Base secret shared between client and server.
        time_window: Allowed clock-skew in seconds (default 5).
    """

    def __init__(self, secret_key: str, time_window: int = 5) -> None:
        self._secret_key = secret_key
        self._time_window = time_window

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def make_headers(self) -> dict[str, str]:
        """Build ``Time`` and ``Authentication`` headers for a new request.

        Returns:
            Dictionary with ``Time`` and ``Authentication`` values.
        """
        time_value = str(int(time.time()))
        token = self._make_token(time_value)
        return {
            'Time': time_value,
            'Authentication': f'{AUTH_TYPE} {token}',
        }

    def check(
        self,
        time_header: str | None,
        auth_header: str | None,
    ) -> bool:
        """Validate the authentication headers sent by the client.

        Checks:
        1. Both headers are present.
        2. ``Time`` is within the configured window around the current time.
        3. The token in ``Authentication`` matches the expected HMAC.

        Args:
            time_header: Value of the ``Time`` request header.
            auth_header: Value of the ``Authentication`` request header.

        Returns:
            ``True`` when authenticated; ``False`` otherwise.
            Failure reasons are written to the module logger at WARNING level.
        """
        if time_header is None:
            logger.warning('Authentication failed: missing Time header')
            return False
        if auth_header is None:
            logger.warning('Authentication failed: missing Authentication header')
            return False

        # --- validate timestamp ---
        try:
            request_time = int(time_header)
        except ValueError:
            logger.warning('Authentication failed: invalid Time header value %r', time_header)
            return False

        now = int(time.time())
        if not (now - self._time_window <= request_time <= now + self._time_window):
            logger.warning(
                'Authentication failed: Time header %d is outside allowed window (now=%d, window=±%ds)',
                request_time,
                now,
                self._time_window,
            )
            return False

        # --- validate token ---
        parts = auth_header.split(' ', 1)
        if len(parts) != 2 or parts[0] != AUTH_TYPE:
            logger.warning('Authentication failed: malformed Authentication header')
            return False

        received_token = parts[1]
        expected_token = self._make_token(time_header)

        if not hmac.compare_digest(received_token, expected_token):
            logger.warning('Authentication failed: invalid token')
            return False

        return True

    def make_cipher(self, time_value: str) -> Cipher:
        """Create a :class:`~simple_ws_proxy.common.cipher.Cipher` for a session.

        Args:
            time_value: Timestamp string from the ``Time`` header.

        Returns:
            A :class:`Cipher` instance keyed to this session.
        """
        return Cipher(self._secret_key, time_value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_token(self, time_value: str) -> str:
        """Compute HMAC-SHA256 token = hmac(session_key, time_value)."""
        session_key = self.make_cipher(time_value).session_key
        return hmac.new(session_key, time_value.encode(), hashlib.sha256).hexdigest()
