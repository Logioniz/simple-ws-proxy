"""WebSocket tunnel handler for a single SOCKS5 connection."""

import asyncio
import logging

import websockets
from websockets.asyncio.client import connect

from simple_ws_proxy.common.auth import Authenticator
from simple_ws_proxy.common.messages.coder import encode
from simple_ws_proxy.common.messages.connect import ConnectMessage

logger = logging.getLogger(__name__)


class TunnelHandler:
    """Handles a single SOCKS5 connection: tunnels via WebSocket.

    The SOCKS5 handshake is performed externally (by
    :meth:`~simple_ws_proxy.common.socks5.Socks5Server.start_server`); this
    class receives the already-resolved *target* and the open stream pair.

    Args:
        local_reader:  Stream reader for the accepted local TCP connection.
        local_writer:  Stream writer for the accepted local TCP connection.
        server_url:    WebSocket proxy server URL.
        authenticator: Shared :class:`~simple_ws_proxy.common.auth.Authenticator`.
    """

    def __init__(
        self,
        local_reader: asyncio.StreamReader,
        local_writer: asyncio.StreamWriter,
        server_url: str,
        authenticator: Authenticator,
    ) -> None:
        self._local_reader = local_reader
        self._local_writer = local_writer
        self._server_url = server_url
        self._authenticator = authenticator

    async def run(self, target: str) -> None:
        """Relay traffic for *target* through the WS proxy.

        Args:
            target: ``"host:port"`` string resolved during the SOCKS5 handshake.
        """
        peer = self._local_writer.get_extra_info('peername')

        logger.info('SOCKS5 connect: %s -> %s via %s', peer, target, self._server_url)

        auth_headers = self._authenticator.make_headers()
        time_value = auth_headers['Time']
        cipher = self._authenticator.make_cipher(time_value)

        try:
            async with connect(self._server_url, additional_headers=auth_headers) as ws:
                # First message: tell the server where to connect (XOR-encrypted)
                connect_payload = encode(ConnectMessage(connect=target))
                await ws.send(cipher.encrypt(connect_payload))

                async def local_to_ws() -> None:
                    try:
                        while True:
                            data = await self._local_reader.read(4096)
                            if not data:
                                break
                            await ws.send(cipher.encrypt(data))
                    except asyncio.CancelledError, ConnectionResetError:
                        pass

                async def ws_to_local() -> None:
                    try:
                        async for message in ws:
                            data = message if isinstance(message, bytes) else message.encode()
                            self._local_writer.write(cipher.decrypt(data))
                            await self._local_writer.drain()
                    except websockets.ConnectionClosed, asyncio.CancelledError:
                        pass

                tasks = [
                    asyncio.create_task(local_to_ws()),
                    asyncio.create_task(ws_to_local()),
                ]
                _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        except Exception as exc:
            logger.error('Tunnel error for %s -> %s: %s', peer, target, exc)
        finally:
            self._local_writer.close()
            logger.info('Connection closed: %s -> %s', peer, target)
