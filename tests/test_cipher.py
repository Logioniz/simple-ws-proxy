"""Unit tests for simple_ws_proxy.common.cipher.Cipher."""

from simple_ws_proxy.common.cipher import Cipher


class TestCipher:
    """Tests for the XOR stream cipher."""

    def _make(self, secret: str = 'secret', ts: str = '1000000000') -> Cipher:
        return Cipher(secret, ts)

    # ------------------------------------------------------------------
    # session_key
    # ------------------------------------------------------------------

    def test_session_key_is_32_bytes(self) -> None:
        assert len(self._make().session_key) == 32

    def test_same_inputs_produce_same_key(self) -> None:
        assert self._make().session_key == self._make().session_key

    def test_different_secret_produces_different_key(self) -> None:
        assert self._make('secret1').session_key != self._make('secret2').session_key

    def test_different_timestamp_produces_different_key(self) -> None:
        assert self._make(ts='111').session_key != self._make(ts='222').session_key

    # ------------------------------------------------------------------
    # encrypt / decrypt round-trip
    # ------------------------------------------------------------------

    def test_encrypt_decrypt_roundtrip(self) -> None:
        cipher = self._make()
        plaintext = b'Hello, World!'
        assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext

    def test_decrypt_encrypt_roundtrip(self) -> None:
        """decrypt(encrypt(x)) == x and encrypt(decrypt(x)) == x (XOR is symmetric)."""
        cipher = self._make()
        data = b'\x00\xff\xab\x12'
        assert cipher.encrypt(cipher.decrypt(data)) == data

    def test_encrypt_changes_data(self) -> None:
        cipher = self._make()
        plaintext = b'test data'
        assert cipher.encrypt(plaintext) != plaintext

    def test_empty_bytes(self) -> None:
        cipher = self._make()
        assert cipher.encrypt(b'') == b''
        assert cipher.decrypt(b'') == b''

    def test_single_byte(self) -> None:
        cipher = self._make()
        assert cipher.decrypt(cipher.encrypt(b'\x42')) == b'\x42'

    def test_output_length_equals_input_length(self) -> None:
        cipher = self._make()
        data = b'x' * 100
        assert len(cipher.encrypt(data)) == len(data)

    def test_different_ciphers_produce_different_ciphertext(self) -> None:
        c1 = Cipher('key1', '1000')
        c2 = Cipher('key2', '1000')
        plaintext = b'same plaintext'
        assert c1.encrypt(plaintext) != c2.encrypt(plaintext)

    def test_cross_cipher_decrypt_fails(self) -> None:
        """Decrypting with a different key should not recover the plaintext."""
        c1 = Cipher('key1', '1000')
        c2 = Cipher('key2', '1000')
        plaintext = b'secret message'
        assert c2.decrypt(c1.encrypt(plaintext)) != plaintext
