"""Unit tests for simple_ws_proxy.common.socks5.

Tests use a real asyncio TCP server so that Socks5Server and Socks5Client
exercise the actual network stack (loopback), making the tests realistic
without requiring external infrastructure.
"""

from __future__ import annotations

import asyncio
import struct
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio

from simple_ws_proxy.common.socks5 import (
    SOCKS5_ATYP_DOMAIN,
    SOCKS5_ATYP_IPV4,
    SOCKS5_ATYP_IPV6,
    SOCKS5_AUTH_NO_AUTH,
    SOCKS5_AUTH_USERNAME_PASSWORD,
    SOCKS5_CMD_CONNECT,
    SOCKS5_VERSION,
    Socks5Client,
    Socks5Server,
)

USER = 'testuser'
PASSWORD = 'testpass'


# ---------------------------------------------------------------------------
# Helpers — raw byte builders
# ---------------------------------------------------------------------------


def _greeting(methods: list[int]) -> bytes:
    return bytes([SOCKS5_VERSION, len(methods)] + methods)


def _auth_subneg(username: str, password: str) -> bytes:
    u = username.encode()
    p = password.encode()
    return bytes([0x01, len(u)]) + u + bytes([len(p)]) + p


def _connect_ipv4(ip: bytes, port: int) -> bytes:
    return bytes([SOCKS5_VERSION, SOCKS5_CMD_CONNECT, 0x00, SOCKS5_ATYP_IPV4]) + ip + struct.pack('!H', port)


def _connect_domain(domain: str, port: int) -> bytes:
    d = domain.encode()
    return bytes([SOCKS5_VERSION, SOCKS5_CMD_CONNECT, 0x00, SOCKS5_ATYP_DOMAIN, len(d)]) + d + struct.pack('!H', port)


def _connect_ipv6(addr: bytes, port: int) -> bytes:
    return bytes([SOCKS5_VERSION, SOCKS5_CMD_CONNECT, 0x00, SOCKS5_ATYP_IPV6]) + addr + struct.pack('!H', port)


def _full_raw(
    atyp_bytes: bytes,
    username: str = USER,
    password: str = PASSWORD,
) -> bytes:
    return _greeting([SOCKS5_AUTH_USERNAME_PASSWORD]) + _auth_subneg(username, password) + atyp_bytes


def _full_raw_no_auth(atyp_bytes: bytes) -> bytes:
    return _greeting([SOCKS5_AUTH_NO_AUTH]) + atyp_bytes


# ---------------------------------------------------------------------------
# Socks5Server — unit tests via in-memory streams
# ---------------------------------------------------------------------------


class TestSocks5ServerUnit:
    """Fast unit tests that feed raw bytes directly into Socks5Server.handshake."""

    async def _run(
        self,
        data: bytes,
        user: str | None = USER,
        password: str | None = PASSWORD,
    ) -> str | None:
        reader = asyncio.StreamReader()
        reader.feed_data(data)

        class _FakeTransport(asyncio.Transport):
            def __init__(self) -> None:
                self.written = bytearray()
                self._closing = False

            def write(self, data: bytes | bytearray | memoryview[Any]) -> None:
                self.written.extend(data)

            def close(self) -> None:
                self._closing = True

            def is_closing(self) -> bool:
                return self._closing

            def get_extra_info(self, name: str, default: object = None) -> object:
                return default

        transport = _FakeTransport()
        protocol = asyncio.StreamReaderProtocol(asyncio.StreamReader())
        writer = asyncio.StreamWriter(transport, protocol, reader, asyncio.get_event_loop())
        return await Socks5Server(user, password).handshake(reader, writer)

    @pytest.mark.asyncio
    async def test_wrong_version_returns_none(self) -> None:
        data = bytes([0x04, 1, SOCKS5_AUTH_USERNAME_PASSWORD])
        assert await self._run(data) is None

    @pytest.mark.asyncio
    async def test_no_acceptable_method_returns_none(self) -> None:
        # Server requires username/password; client only offers no-auth → rejected
        assert await self._run(_greeting([SOCKS5_AUTH_NO_AUTH])) is None

    @pytest.mark.asyncio
    async def test_no_auth_mode_no_acceptable_method_returns_none(self) -> None:
        # Server in no-auth mode; client only offers username/password → rejected
        data = _greeting([SOCKS5_AUTH_USERNAME_PASSWORD])
        assert await self._run(data, user=None, password=None) is None

    @pytest.mark.asyncio
    async def test_wrong_username_returns_none(self) -> None:
        data = _full_raw(_connect_ipv4(b'\x7f\x00\x00\x01', 80), username='bad')
        assert await self._run(data) is None

    @pytest.mark.asyncio
    async def test_wrong_password_returns_none(self) -> None:
        data = _full_raw(_connect_ipv4(b'\x7f\x00\x00\x01', 80), password='bad')
        assert await self._run(data) is None

    @pytest.mark.asyncio
    async def test_unsupported_command_returns_none(self) -> None:
        bad_cmd = bytes([SOCKS5_VERSION, 0x02, 0x00, SOCKS5_ATYP_IPV4]) + b'\x7f\x00\x00\x01' + struct.pack('!H', 80)
        data = _greeting([SOCKS5_AUTH_USERNAME_PASSWORD]) + _auth_subneg(USER, PASSWORD) + bad_cmd
        assert await self._run(data) is None

    @pytest.mark.asyncio
    async def test_unsupported_atyp_returns_none(self) -> None:
        bad_atyp = bytes([SOCKS5_VERSION, SOCKS5_CMD_CONNECT, 0x00, 0x99])
        data = _greeting([SOCKS5_AUTH_USERNAME_PASSWORD]) + _auth_subneg(USER, PASSWORD) + bad_atyp
        assert await self._run(data) is None

    @pytest.mark.asyncio
    async def test_ipv4_connect(self) -> None:
        data = _full_raw(_connect_ipv4(b'\x7f\x00\x00\x01', 8080))
        assert await self._run(data) == '127.0.0.1:8080'

    @pytest.mark.asyncio
    async def test_domain_connect(self) -> None:
        data = _full_raw(_connect_domain('example.com', 443))
        assert await self._run(data) == 'example.com:443'

    @pytest.mark.asyncio
    async def test_ipv6_connect(self) -> None:
        ipv6 = b'\x00' * 15 + b'\x01'  # ::1
        data = _full_raw(_connect_ipv6(ipv6, 22))
        result = await self._run(data)
        assert result is not None
        assert ':22' in result
        assert '[' in result

    @pytest.mark.asyncio
    async def test_port_preserved(self) -> None:
        for port in (1, 80, 443, 8080, 65535):
            data = _full_raw(_connect_ipv4(b'\x01\x02\x03\x04', port))
            result = await self._run(data)
            assert result is not None
            assert result.endswith(f':{port}')

    # -- no-auth mode ---------------------------------------------------------

    @pytest.mark.asyncio
    async def test_no_auth_ipv4_connect(self) -> None:
        data = _full_raw_no_auth(_connect_ipv4(b'\x7f\x00\x00\x01', 8080))
        assert await self._run(data, user=None, password=None) == '127.0.0.1:8080'

    @pytest.mark.asyncio
    async def test_no_auth_domain_connect(self) -> None:
        data = _full_raw_no_auth(_connect_domain('example.com', 443))
        assert await self._run(data, user=None, password=None) == 'example.com:443'

    @pytest.mark.asyncio
    async def test_no_auth_ipv6_connect(self) -> None:
        ipv6 = b'\x00' * 15 + b'\x01'  # ::1
        data = _full_raw_no_auth(_connect_ipv6(ipv6, 22))
        result = await self._run(data, user=None, password=None)
        assert result is not None
        assert ':22' in result
        assert '[' in result


# ---------------------------------------------------------------------------
# Socks5Server + Socks5Client — integration tests over loopback TCP
# ---------------------------------------------------------------------------


class TestSocks5Integration:
    """End-to-end tests: Socks5Client connects to a real Socks5Server listener."""

    async def _make_proxy(
        self,
        username: str | None = None,
        password: str | None = None,
    ) -> tuple[asyncio.Server, str, int, list[str | None]]:
        results: list[str | None] = []
        server_obj = Socks5Server(username, password)

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            target = await server_obj.handshake(reader, writer)
            results.append(target)
            writer.close()

        server = await asyncio.start_server(handler, '127.0.0.1', 0)
        host, port = server.sockets[0].getsockname()
        return server, host, port, results

    @pytest_asyncio.fixture
    async def socks5_proxy(self) -> AsyncGenerator[tuple[str, int, list[str | None]], None]:
        """Start a minimal SOCKS5 server with username/password auth."""
        server, host, port, results = await self._make_proxy(USER, PASSWORD)
        async with server:
            yield host, port, results

    @pytest_asyncio.fixture
    async def socks5_proxy_no_auth(self) -> AsyncGenerator[tuple[str, int, list[str | None]], None]:
        """Start a minimal SOCKS5 server with no authentication."""
        server, host, port, results = await self._make_proxy()
        async with server:
            yield host, port, results

    @pytest.mark.asyncio
    async def test_client_connects_and_server_receives_target(
        self, socks5_proxy: tuple[str, int, list[str | None]]
    ) -> None:
        host, port, results = socks5_proxy
        client = Socks5Client(host, port, USER, PASSWORD)
        try:
            reader, writer = await client.connect('example.com', 80)
            writer.close()
        except Exception:
            pass
        await asyncio.sleep(0.05)
        assert results == ['example.com:80']

    @pytest.mark.asyncio
    async def test_client_wrong_password_raises(self, socks5_proxy: tuple[str, int, list[str | None]]) -> None:
        host, port, _ = socks5_proxy
        client = Socks5Client(host, port, USER, 'wrongpass')
        with pytest.raises(ConnectionError):
            await client.connect('example.com', 80)

    @pytest.mark.asyncio
    async def test_no_auth_client_connects(self, socks5_proxy_no_auth: tuple[str, int, list[str | None]]) -> None:
        host, port, results = socks5_proxy_no_auth
        client = Socks5Client(host, port)
        try:
            reader, writer = await client.connect('example.com', 443)
            writer.close()
        except Exception:
            pass
        await asyncio.sleep(0.05)
        assert results == ['example.com:443']

    @pytest.mark.asyncio
    async def test_no_auth_client_rejected_by_auth_server(
        self, socks5_proxy: tuple[str, int, list[str | None]]
    ) -> None:
        host, port, _ = socks5_proxy
        client = Socks5Client(host, port)  # no credentials
        with pytest.raises(ConnectionError):
            await client.connect('example.com', 80)
