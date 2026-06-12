# simple-ws-proxy

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A simple WebSocket proxy with a SOCKS5 frontend. The client exposes a local SOCKS5 listener and tunnels traffic through a WebSocket connection to the server, which forwards it to the target host.

## Installation

```bash
uv sync
```

For development dependencies (linting, tests):

```bash
make develop
```

## Running the server

```bash
simple-ws-proxy-server --secret-key <key> [options]
```

| Option | Default | Description |
|---|---|---|
| `--secret-key` | *(required)* | Shared secret key for authentication and encryption |
| `--host` | `0.0.0.0` | Address to bind the WebSocket server to |
| `--port` | `8765` | TCP port to listen on |
| `--workers` | `1` | Number of prefork worker processes |
| `--time-window` | `5` | Allowed clock-skew in seconds for the `Time` header |

**Example:**

```bash
simple-ws-proxy-server --secret-key mysecret --port 8765 --workers 4
```

## Running the client

```bash
simple-ws-proxy-client --server <ws-url> --listen-port <port> --secret-key <key> --client-user <user> --client-password <password> [options]
```

| Option | Default | Description |
|---|---|---|
| `--server` | *(required)* | WebSocket proxy server URL, e.g. `ws://localhost:8765` |
| `--listen-port` | *(required)* | Local port to listen on for SOCKS5 connections |
| `--secret-key` | *(required)* | Shared secret key (must match the server) |
| `--client-user` | *(required)* | SOCKS5 username that connecting clients must provide |
| `--client-password` | *(required)* | SOCKS5 password that connecting clients must provide |
| `--listen-host` | `127.0.0.1` | Local address to bind the SOCKS5 listener to |

**Example:**

```bash
simple-ws-proxy-client \
  --server ws://example.com:8765 \
  --listen-port 1080 \
  --secret-key mysecret \
  --client-user alice \
  --client-password s3cr3t
```

After starting the client, configure your application to use `127.0.0.1:1080` as a SOCKS5 proxy with username `alice` and password `s3cr3t`.
