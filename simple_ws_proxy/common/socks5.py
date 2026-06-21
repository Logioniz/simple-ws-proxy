"""SOCKS5 implementation (RFC 1928 + RFC 1929).

Provides two classes:

* :class:`Socks5Server` — performs the server-side handshake with a
  connecting SOCKS5 application.  Supports both no-authentication and
  username/password auth (RFC 1929).  When credentials are supplied at
  construction, username/password auth is required; otherwise
  no-authentication is accepted.
* :class:`Socks5Client` — performs the client-side handshake when
  connecting *through* a SOCKS5 proxy (useful for testing and for
  chained / double-tunnel scenarios).

Only the CONNECT command is supported.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

SOCKS5_VERSION = 0x05

# Authentication methods
SOCKS5_AUTH_NO_AUTH = 0x00
SOCKS5_AUTH_USERNAME_PASSWORD = 0x02
SOCKS5_AUTH_NO_ACCEPTABLE = 0xFF

# Commands
SOCKS5_CMD_CONNECT = 0x01

# Address types
SOCKS5_ATYP_IPV4 = 0x01
SOCKS5_ATYP_DOMAIN = 0x03
SOCKS5_ATYP_IPV6 = 0x04

# Reply codes
SOCKS5_REP_SUCCESS = 0x00
SOCKS5_REP_GENERAL_FAILURE = 0x01
SOCKS5_REP_CMD_NOT_SUPPORTED = 0x07
SOCKS5_REP_ATYP_NOT_SUPPORTED = 0x08

# Reusable "zero" bind address used in server replies (IPv4 0.0.0.0:0)
_BIND_ADDR = bytes([SOCKS5_ATYP_IPV4]) + b'\x00' * 4 + b'\x00\x00'


# ---------------------------------------------------------------------------
# Socks5Server
# ---------------------------------------------------------------------------

# Type alias for the post-handshake handler callable.
# Receives the resolved "host:port" target and the stream pair.
Socks5Handler = Callable[
    [str, asyncio.StreamReader, asyncio.StreamWriter],
    Awaitable[None],
]


class Socks5Server:
    """Server-side SOCKS5 handshake handler.

    Accepts a connection from a SOCKS5-aware application and returns the
    requested target ``host:port``.

    Two authentication modes are supported:

    * **No authentication** — when *username* and *password* are both
      ``None`` (the default).  The server advertises
      ``NO AUTHENTICATION REQUIRED`` (method 0x00) and skips the RFC 1929
      sub-negotiation entirely.
    * **Username/password** (RFC 1929) — when both *username* and *password*
      are provided.  Credentials are validated against the supplied values.

    Args:
        username: Expected SOCKS5 username, or ``None`` for no-auth mode.
        password: Expected SOCKS5 password, or ``None`` for no-auth mode.
    """

    def __init__(self, username: str | None = None, password: str | None = None) -> None:
        self._username = username
        self._password = password

    async def start_server(
        self,
        handler: Socks5Handler,
        listen_host: str | None = None,
        listen_port: int | None = None,
        *,
        sock: socket.socket | None = None,
    ) -> asyncio.Server:
        """Create a TCP server that performs the SOCKS5 handshake on each
        accepted connection and then delegates to *handler*.

        Exactly one of (*listen_host* + *listen_port*) or *sock* must be
        provided.

        Args:
            handler:     Async callable ``(target, reader, writer) -> None``
                         invoked after a successful handshake.  *target* is
                         the ``"host:port"`` string requested by the client.
            listen_host: Local address to bind the listener to.
            listen_port: Local TCP port to listen on.
            sock:        Optional pre-bound :class:`socket.socket` to use
                         instead of binding a new one.  Pass this in prefork
                         workers so all workers share the same listening socket.

        Returns:
            An :class:`asyncio.Server` instance.  Call
            ``async with server`` / ``await server.serve_forever()`` to
            start accepting connections.
        """
        if sock is None and (listen_host is None or listen_port is None):
            raise ValueError('Either sock or both listen_host and listen_port must be provided')

        async def _connection_cb(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            target = await self.handshake(reader, writer)
            if target is None:
                writer.close()
                return
            await handler(target, reader, writer)

        if sock is not None:
            server = await asyncio.start_server(_connection_cb, sock=sock)
        else:
            server = await asyncio.start_server(_connection_cb, listen_host, listen_port)
        addrs = ', '.join(str(s.getsockname()) for s in server.sockets)
        logger.info('SOCKS5 server listening on %s', addrs)
        return server

    async def handshake(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> str | None:
        """Perform the server-side SOCKS5 handshake.

        Args:
            reader: Stream reader for the client TCP connection.
            writer: Stream writer for the client TCP connection.

        Returns:
            ``"host:port"`` string on success, or ``None`` on failure.
        """
        # ---------------------------------------------------------------- #
        # Greeting                                                          #
        # ---------------------------------------------------------------- #
        header = await reader.readexactly(2)
        version, nmethods = header
        if version != SOCKS5_VERSION:
            logger.warning('SOCKS5 server: unexpected version %d', version)
            return None

        methods = set(await reader.readexactly(nmethods))

        require_auth = self._username is not None or self._password is not None

        if require_auth:
            if SOCKS5_AUTH_USERNAME_PASSWORD not in methods:
                writer.write(bytes([SOCKS5_VERSION, SOCKS5_AUTH_NO_ACCEPTABLE]))
                await writer.drain()
                logger.warning('SOCKS5 server: client did not offer username/password auth')
                return None

            writer.write(bytes([SOCKS5_VERSION, SOCKS5_AUTH_USERNAME_PASSWORD]))
            await writer.drain()

            # ---------------------------------------------------------------- #
            # RFC 1929 sub-negotiation                                         #
            # ---------------------------------------------------------------- #
            sub_ver = (await reader.readexactly(1))[0]
            if sub_ver != 0x01:
                logger.warning('SOCKS5 server: unexpected auth sub-version %d', sub_ver)
                return None

            ulen = (await reader.readexactly(1))[0]
            received_username = (await reader.readexactly(ulen)).decode(errors='replace')

            plen = (await reader.readexactly(1))[0]
            received_password = (await reader.readexactly(plen)).decode(errors='replace')

            if received_username != self._username or received_password != self._password:
                writer.write(bytes([0x01, 0x01]))  # failure
                await writer.drain()
                logger.warning('SOCKS5 server: authentication failed for user %r', received_username)
                return None

            writer.write(bytes([0x01, SOCKS5_REP_SUCCESS]))
            await writer.drain()
        else:
            if SOCKS5_AUTH_NO_AUTH not in methods:
                writer.write(bytes([SOCKS5_VERSION, SOCKS5_AUTH_NO_ACCEPTABLE]))
                await writer.drain()
                logger.warning('SOCKS5 server: client did not offer no-auth method')
                return None

            writer.write(bytes([SOCKS5_VERSION, SOCKS5_AUTH_NO_AUTH]))
            await writer.drain()

        # ---------------------------------------------------------------- #
        # Request                                                           #
        # ---------------------------------------------------------------- #
        req_header = await reader.readexactly(4)
        ver, cmd, _rsv, atyp = req_header

        if ver != SOCKS5_VERSION:
            return None

        if cmd != SOCKS5_CMD_CONNECT:
            writer.write(bytes([SOCKS5_VERSION, SOCKS5_REP_CMD_NOT_SUPPORTED, 0x00]) + _BIND_ADDR)
            await writer.drain()
            logger.warning('SOCKS5 server: unsupported command %d', cmd)
            return None

        host = await self._read_address(reader, writer, atyp)
        if host is None:
            return None

        port_bytes = await reader.readexactly(2)
        port = struct.unpack('!H', port_bytes)[0]

        # Reply: success
        writer.write(bytes([SOCKS5_VERSION, SOCKS5_REP_SUCCESS, 0x00]) + _BIND_ADDR)
        await writer.drain()

        return f'{host}:{port}'

    @staticmethod
    async def _read_address(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        atyp: int,
    ) -> str | None:
        if atyp == SOCKS5_ATYP_IPV4:
            addr_bytes = await reader.readexactly(4)
            return '.'.join(str(b) for b in addr_bytes)
        if atyp == SOCKS5_ATYP_DOMAIN:
            domain_len = (await reader.readexactly(1))[0]
            return (await reader.readexactly(domain_len)).decode()
        if atyp == SOCKS5_ATYP_IPV6:
            addr_bytes = await reader.readexactly(16)
            parts = struct.unpack('!8H', addr_bytes)
            return '[' + ':'.join(f'{p:04x}' for p in parts) + ']'

        writer.write(bytes([SOCKS5_VERSION, SOCKS5_REP_ATYP_NOT_SUPPORTED, 0x00]) + _BIND_ADDR)
        await writer.drain()
        logger.warning('SOCKS5 server: unsupported address type %d', atyp)
        return None


# ---------------------------------------------------------------------------
# Socks5Client
# ---------------------------------------------------------------------------


class Socks5Client:
    """Client-side SOCKS5 connector.

    Connects to a SOCKS5 proxy and requests a tunnel to a target host/port.
    Useful for testing :class:`Socks5Server` end-to-end and for building
    chained (double-tunnel) proxy scenarios.

    Two authentication modes are supported:

    * **No authentication** — when *username* and *password* are both
      ``None`` (the default).  The client advertises only
      ``NO AUTHENTICATION REQUIRED`` (method 0x00).
    * **Username/password** (RFC 1929) — when both *username* and *password*
      are provided.

    Args:
        proxy_host: Hostname or IP of the SOCKS5 proxy.
        proxy_port: TCP port of the SOCKS5 proxy.
        username:   SOCKS5 username, or ``None`` for no-auth mode.
        password:   SOCKS5 password, or ``None`` for no-auth mode.
    """

    def __init__(
        self,
        proxy_host: str,
        proxy_port: int,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        self._username = username
        self._password = password

    async def connect(self, target_host: str, target_port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Open a tunnel through the SOCKS5 proxy to *target_host:target_port*.

        Args:
            target_host: Destination hostname or IP address.
            target_port: Destination TCP port.

        Returns:
            ``(reader, writer)`` connected to the target via the proxy.

        Raises:
            ConnectionError: If the proxy rejects the request.
            OSError:         If the TCP connection to the proxy fails.
        """
        reader, writer = await asyncio.open_connection(self._proxy_host, self._proxy_port)

        try:
            await self._negotiate(reader, writer, target_host, target_port)
        except Exception:
            writer.close()
            raise

        return reader, writer

    async def _negotiate(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        target_host: str,
        target_port: int,
    ) -> None:
        # ---------------------------------------------------------------- #
        # Greeting                                                          #
        # ---------------------------------------------------------------- #
        use_auth = self._username is not None or self._password is not None
        if use_auth:
            writer.write(bytes([SOCKS5_VERSION, 1, SOCKS5_AUTH_USERNAME_PASSWORD]))
        else:
            writer.write(bytes([SOCKS5_VERSION, 1, SOCKS5_AUTH_NO_AUTH]))
        await writer.drain()

        resp = await reader.readexactly(2)
        if resp[0] != SOCKS5_VERSION or resp[1] == SOCKS5_AUTH_NO_ACCEPTABLE:
            raise ConnectionError('SOCKS5 proxy rejected authentication method')

        if use_auth:
            # ---------------------------------------------------------------- #
            # RFC 1929 sub-negotiation                                         #
            # ---------------------------------------------------------------- #
            u = (self._username or '').encode()
            p = (self._password or '').encode()
            writer.write(bytes([0x01, len(u)]) + u + bytes([len(p)]) + p)
            await writer.drain()

            auth_resp = await reader.readexactly(2)
            if auth_resp[1] != SOCKS5_REP_SUCCESS:
                raise ConnectionError('SOCKS5 proxy authentication failed')

        # ---------------------------------------------------------------- #
        # CONNECT request                                                   #
        # ---------------------------------------------------------------- #
        host_bytes = target_host.encode()
        request = (
            bytes([SOCKS5_VERSION, SOCKS5_CMD_CONNECT, 0x00, SOCKS5_ATYP_DOMAIN, len(host_bytes)])
            + host_bytes
            + struct.pack('!H', target_port)
        )
        writer.write(request)
        await writer.drain()

        # ---------------------------------------------------------------- #
        # Response                                                          #
        # ---------------------------------------------------------------- #
        reply_header = await reader.readexactly(4)
        if reply_header[1] != SOCKS5_REP_SUCCESS:
            raise ConnectionError(f'SOCKS5 proxy returned error code {reply_header[1]}')

        # Skip bind address
        bind_atyp = reply_header[3]
        if bind_atyp == SOCKS5_ATYP_IPV4:
            await reader.readexactly(4 + 2)
        elif bind_atyp == SOCKS5_ATYP_DOMAIN:
            dlen = (await reader.readexactly(1))[0]
            await reader.readexactly(dlen + 2)
        elif bind_atyp == SOCKS5_ATYP_IPV6:
            await reader.readexactly(16 + 2)
