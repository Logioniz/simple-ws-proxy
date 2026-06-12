"""CLI argument parsing for the simple-ws-proxy client."""

import argparse


def parse_args() -> argparse.Namespace:
    """Parse and return client command-line arguments.

    Returns:
        Namespace with the following attributes:

        - ``server`` (str): WebSocket server URL, e.g. ``ws://localhost:8765``.
        - ``listen_host`` (str): Local address to bind the SOCKS5 listener to.
        - ``listen_port`` (int): Local port to listen on.
        - ``secret_key`` (str): Shared secret used for authentication and encryption.
        - ``client_user`` (str): SOCKS5 username that clients must supply.
        - ``client_password`` (str): SOCKS5 password that clients must supply.
    """
    parser = argparse.ArgumentParser(
        prog='simple-ws-proxy-client',
        description='Simple WebSocket proxy client (SOCKS5 frontend)',
    )
    parser.add_argument(
        '--server',
        required=True,
        help='WebSocket proxy server URL (e.g. ws://localhost:8765)',
    )
    parser.add_argument(
        '--listen-host',
        default='127.0.0.1',
        help='Local address to bind the SOCKS5 listener to (default: 127.0.0.1)',
    )
    parser.add_argument(
        '--listen-port',
        type=int,
        required=True,
        help='Local port to listen on for SOCKS5 connections',
    )
    parser.add_argument(
        '--secret-key',
        required=True,
        help='Shared secret key for authentication and encryption',
    )
    parser.add_argument(
        '--client-user',
        required=True,
        help='SOCKS5 username that connecting clients must provide',
    )
    parser.add_argument(
        '--client-password',
        required=True,
        help='SOCKS5 password that connecting clients must provide',
    )
    return parser.parse_args()
