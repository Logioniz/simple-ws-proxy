"""Prefork WebSocket proxy server."""

import asyncio
import logging
import os
import socket

import websockets
from websockets.asyncio.server import ServerConnection, serve

from simple_ws_proxy.common.auth import Authenticator
from simple_ws_proxy.common.messages.coder import decode
from simple_ws_proxy.common.messages.connect import ConnectMessage
from simple_ws_proxy.common.prefork_server import PreforkServer
from simple_ws_proxy.server.args import parse_args

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(process)d] %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

# WebSocket close codes (RFC 6455)
WS_CLOSE_POLICY_VIOLATION = 1008  # Unauthorized / policy violation
WS_CLOSE_UNSUPPORTED_DATA = 1003  # Unsupported / invalid message format
WS_CLOSE_INTERNAL_ERROR = 1011  # Unexpected server-side error


class ConnectionHandler:
    """Handles a single authenticated WebSocket proxy connection.

    Args:
        ws:            Accepted WebSocket connection.
        authenticator: Shared :class:`~simple_ws_proxy.common.auth.Authenticator`.
    """

    def __init__(self, ws: ServerConnection, authenticator: Authenticator) -> None:
        self._ws = ws
        self._authenticator = authenticator

    async def run(self) -> None:
        """Authenticate, parse the connect request, and relay traffic."""
        ws = self._ws

        # --- authentication ---
        if ws.request is None:
            await ws.close(WS_CLOSE_POLICY_VIOLATION, 'Unauthorized')
            return

        headers = ws.request.headers
        time_header = headers.get('Time')
        auth_header = headers.get('Authentication')

        if not time_header or not auth_header:
            logger.warning('Rejected connection without auth headers from %s', ws.remote_address)
            await ws.close(WS_CLOSE_POLICY_VIOLATION, 'Unauthorized')
            return

        if not self._authenticator.check(time_header, auth_header):
            logger.warning('Rejected unauthenticated connection from %s', ws.remote_address)
            await ws.close(WS_CLOSE_POLICY_VIOLATION, 'Unauthorized')
            return

        cipher = self._authenticator.make_cipher(time_header)
        logger.info('Authenticated connection from %s', ws.remote_address)

        # --- first message: connect request (XOR-encrypted) ---
        try:
            raw = await ws.recv()
            data = raw if isinstance(raw, bytes) else raw.encode()
            connect_msg = decode(cipher.decrypt(data), ConnectMessage)
            target = connect_msg.connect
            host, _, port_str = target.rpartition(':')
            port = int(port_str)
        except Exception as exc:
            logger.warning('Invalid connect message: %s', exc)
            await ws.close(WS_CLOSE_UNSUPPORTED_DATA, 'Invalid connect message')
            return

        # --- open TCP connection to target ---
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except OSError as exc:
            logger.warning('Cannot connect to %s:%d — %s', host, port, exc)
            await ws.close(WS_CLOSE_INTERNAL_ERROR, f'Cannot connect to target: {exc}')
            return

        logger.info('Proxying %s -> %s:%d', ws.remote_address, host, port)

        async def ws_to_tcp() -> None:
            try:
                async for message in ws:
                    data = message if isinstance(message, bytes) else message.encode()
                    writer.write(cipher.decrypt(data))
                    await writer.drain()
            except websockets.ConnectionClosed, asyncio.CancelledError:
                pass
            finally:
                writer.close()

        async def tcp_to_ws() -> None:
            try:
                while True:
                    data = await reader.read(4096)
                    if not data:
                        break
                    await ws.send(cipher.encrypt(data))
            except websockets.ConnectionClosed, asyncio.CancelledError:
                pass

        tasks = [
            asyncio.create_task(ws_to_tcp()),
            asyncio.create_task(tcp_to_ws()),
        ]
        try:
            _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        finally:
            await ws.close()
            logger.info('Connection closed: %s -> %s:%d', ws.remote_address, host, port)


class ProxyServer:
    """WebSocket proxy server that runs in prefork mode.

    Args:
        host:          Address to bind to.
        port:          TCP port to listen on.
        workers:       Number of worker processes to fork.
        authenticator: Shared :class:`~simple_ws_proxy.common.auth.Authenticator`.
    """

    def __init__(
        self,
        host: str,
        port: int,
        workers: int,
        authenticator: Authenticator,
    ) -> None:
        self._host = host
        self._port = port
        self._workers = workers
        self._authenticator = authenticator

    def run(self) -> None:
        """Bind the socket, fork workers, and wait for them to finish."""
        prefork = PreforkServer(self._workers)
        with prefork.start_server(self._worker, self._host, self._port) as srv:
            srv.serve_forever()

    def _worker(self, sock: socket.socket) -> None:
        """Entry point for each forked worker process."""
        authenticator = self._authenticator

        async def _serve() -> None:
            async def handler(ws: ServerConnection) -> None:
                await ConnectionHandler(ws, authenticator).run()

            async with serve(handler, sock=sock) as server:
                logger.info('Worker %d ready', os.getpid())
                await server.serve_forever()

        asyncio.run(_serve())


def main() -> None:
    """Parse arguments and start the proxy server."""
    args = parse_args()
    authenticator = Authenticator(args.secret_key, args.time_window)
    ProxyServer(
        host=args.host,
        port=args.port,
        workers=args.workers,
        authenticator=authenticator,
    ).run()


if __name__ == '__main__':
    main()
