"""SOCKS5 proxy client.

Listens on a local TCP port, performs the SOCKS5 handshake (with mandatory
username/password authentication) with the connecting application, then
tunnels the traffic through the WebSocket proxy server using XOR encryption.
"""

import asyncio
import logging

from simple_ws_proxy.client.args import parse_args
from simple_ws_proxy.client.tunnel import TunnelHandler
from simple_ws_proxy.common.auth import Authenticator
from simple_ws_proxy.common.socks5 import Socks5Server

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


class ProxyClient:
    """SOCKS5 frontend that tunnels connections through a WebSocket proxy.

    Args:
        server_url:    WebSocket proxy server URL.
        listen_host:   Local address to bind the SOCKS5 listener to.
        listen_port:   Local port to listen on.
        authenticator: Shared :class:`~simple_ws_proxy.common.auth.Authenticator`.
        socks5_server: Shared :class:`~simple_ws_proxy.common.socks5.Socks5Server`.
    """

    def __init__(
        self,
        server_url: str,
        listen_host: str,
        listen_port: int,
        authenticator: Authenticator,
        socks5_server: Socks5Server,
    ) -> None:
        self._server_url = server_url
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._authenticator = authenticator
        self._socks5_server = socks5_server

    def run(self) -> None:
        """Start the event loop and the SOCKS5 listener."""
        asyncio.run(self._serve())

    async def _serve(self) -> None:
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

        server = await self._socks5_server.start_server(handler, self._listen_host, self._listen_port)
        async with server:
            await server.serve_forever()


def main() -> None:
    """Parse arguments and start the SOCKS5 proxy client."""
    args = parse_args()
    authenticator = Authenticator(args.secret_key)
    socks5_server = Socks5Server(args.client_user, args.client_password)
    ProxyClient(
        server_url=args.server,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        authenticator=authenticator,
        socks5_server=socks5_server,
    ).run()


if __name__ == '__main__':
    main()
