"""Connect message structure for the WebSocket proxy protocol."""

import msgspec


class ConnectMessage(msgspec.Struct, frozen=True):
    """First message sent by the client to the proxy server.

    Instructs the server to open a TCP connection to *connect*.

    Args:
        connect: Target address in ``"host:port"`` format.
    """

    connect: str
