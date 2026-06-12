"""XOR cipher using a session key derived from a base secret and a timestamp."""

import hashlib
import hmac


class Cipher:
    """XOR stream cipher keyed by a per-session secret.

    The session key is derived once at construction time via HMAC-SHA256 so
    that every (secret_key, timestamp) pair produces a unique key stream.

    Args:
        secret_key: Base secret shared between client and server.
        time_value: Timestamp string taken from the ``Time`` header.
    """

    def __init__(self, secret_key: str, time_value: str) -> None:
        self._key: bytes = hmac.new(
            secret_key.encode(),
            time_value.encode(),
            hashlib.sha256,
        ).digest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def session_key(self) -> bytes:
        """The derived 32-byte session key (read-only)."""
        return self._key

    def encrypt(self, data: bytes) -> bytes:
        """XOR-encrypt *data* with the session key.

        Args:
            data: Plaintext bytes.

        Returns:
            Ciphertext bytes of the same length.
        """
        return self._xor(data)

    def decrypt(self, data: bytes) -> bytes:
        """XOR-decrypt *data* with the session key.

        XOR is its own inverse, so this is identical to :meth:`encrypt`.

        Args:
            data: Ciphertext bytes.

        Returns:
            Plaintext bytes of the same length.
        """
        return self._xor(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _xor(self, data: bytes) -> bytes:
        key = self._key
        key_len = len(key)
        return bytes(b ^ key[i % key_len] for i, b in enumerate(data))
