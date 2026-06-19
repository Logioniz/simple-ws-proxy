"""CLI argument parsing for the simple-ws-proxy server."""

import argparse


def parse_args() -> argparse.Namespace:
    """Parse and return server command-line arguments.

    Returns:
        Namespace with the following attributes:

        - ``host`` (str): Address to bind the WebSocket server to.
        - ``port`` (int): TCP port to listen on.
        - ``workers`` (int): Number of prefork worker processes.
        - ``secret_key`` (str): Shared secret used for authentication and encryption.
        - ``time_window`` (int): Allowed clock-skew in seconds for the ``Time`` header.
    """
    parser = argparse.ArgumentParser(
        prog='simple-ws-proxy-server',
        description='Simple WebSocket proxy server',
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Address to bind to (default: 0.0.0.0)',
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8765,
        help='Port to listen on (default: 8765)',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help='Number of prefork worker processes (default: 1)',
    )
    parser.add_argument(
        '--secret-key',
        required=True,
        help='Shared secret key for authentication and encryption',
    )
    parser.add_argument(
        '--time-window',
        type=int,
        default=5,
        help='Allowed clock-skew in seconds for the Time header (default: 5)',
    )
    parser.add_argument(
        '--proxy-host',
        help='Proxy host to use for SOCKS5 connections. Empty value not use proxy.',
    )
    parser.add_argument(
        '--proxy-port',
        type=int,
        help='Proxy port to use for SOCKS5 connections. Empty value not use proxy.',
    )
    return parser.parse_args()
