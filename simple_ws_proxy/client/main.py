"""SOCKS5 proxy client.

Listens on a local TCP port, performs the SOCKS5 handshake with the connecting
application, then tunnels the traffic through the WebSocket proxy server using
XOR encryption.

Authentication is optional: when ``--client-user`` and ``--client-password`` are
provided the server requires username/password auth (RFC 1929); otherwise
no-authentication (method 0x00) is accepted.
"""

import asyncio
import logging
import os
import socket

from simple_ws_proxy.client.args import parse_args
from simple_ws_proxy.client.tunnel import TunnelHandler
from simple_ws_proxy.common.auth import Authenticator
from simple_ws_proxy.common.prefork_server import PreforkServer
from simple_ws_proxy.common.socks5 import Socks5Server

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(process)d] %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


class ProxyClient:
    """SOCKS5 frontend that tunnels connections through a WebSocket proxy.

    Supports prefork mode: when *workers* > 1 the listening socket is bound
    in the parent process and each worker child inherits it, so all workers
    share the same port without contention.

    Args:
        server_url:    WebSocket proxy server URL.
        listen_host:   Local address to bind the SOCKS5 listener to.
        listen_port:   Local port to listen on.
        workers:       Number of prefork worker processes.
        authenticator: Shared :class:`~simple_ws_proxy.common.auth.Authenticator`.
        socks5_server: Shared :class:`~simple_ws_proxy.common.socks5.Socks5Server`.
    """

    def __init__(
        self,
        server_url: str,
        listen_host: str,
        listen_port: int,
        workers: int,
        authenticator: Authenticator,
        socks5_server: Socks5Server,
    ) -> None:
        self._server_url = server_url
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._workers = workers
        self._authenticator = authenticator
        self._socks5_server = socks5_server

    def run(self) -> None:
        """Bind the socket, fork workers, and wait for them to finish."""
        prefork = PreforkServer(self._workers)
        with prefork.start_server(self._worker, self._listen_host, self._listen_port) as srv:
            srv.serve_forever()

    def _worker(self, sock: socket.socket) -> None:
        """Entry point for each forked worker process."""

        async def _serve() -> None:
            async def handler(
                target: str,
                reader: asyncio.StreamReader,
                writer: asyncio.StreamWriter,
            ) -> None:
                await TunnelHandler(
                    reader,
                    writer,
                    self._server_url,
                    self._authenticator,
                ).run(target)

            server = await self._socks5_server.start_server(handler, sock=sock)
            logger.info('Worker %d ready', os.getpid())
            async with server:
                await server.serve_forever()

        asyncio.run(_serve())


def main() -> None:
    """Parse arguments and start the SOCKS5 proxy client."""
    args = parse_args()
    authenticator = Authenticator(args.secret_key)
    socks5_server = Socks5Server(args.client_user, args.client_password)
    ProxyClient(
        server_url=args.server,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        workers=args.workers,
        authenticator=authenticator,
        socks5_server=socks5_server,
    ).run()


if __name__ == '__main__':
    main()
