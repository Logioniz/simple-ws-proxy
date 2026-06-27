# simple-ws-proxy

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A simple WebSocket proxy with a SOCKS5 frontend. The client exposes a local SOCKS5 listener and tunnels traffic through a WebSocket connection to the server, which forwards it to the target host.

## Installation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it yet, then:

```bash
uv sync
```

For development dependencies (linting, tests):

```bash
make develop
```

## Building standalone binaries

To produce self-contained executables (server and client) that run without a
Python installation, use [PyInstaller](https://pyinstaller.org/) via:

```bash
make build
```

The binaries are written to `dist/<os>/` (e.g. `dist/linux/`), where `<os>` is
detected automatically. PyInstaller does not cross-compile, so run `make build`
on each platform you want to target — Linux, Windows and macOS separately.

## Running the server

```bash
uv run simple-ws-proxy-server --secret-key <key> [options]
```

| Option | Default | Description |
|---|---|---|
| `--secret-key` | *(required)* | Shared secret key for authentication and encryption |
| `--host` | `0.0.0.0` | Address to bind the WebSocket server to |
| `--port` | `8765` | TCP port to listen on |
| `--workers` | `1` | Number of prefork worker processes |
| `--time-window` | `5` | Allowed clock-skew in seconds for the `Time` header |
| `--proxy-host` | *(none)* | Hostname or IP of an upstream SOCKS5 proxy; omit for direct connections |
| `--proxy-port` | *(none)* | TCP port of the upstream SOCKS5 proxy |

**Example:**

```bash
uv run simple-ws-proxy-server --secret-key mysecret --port 8765 --workers 4
```

## Running the client

```bash
uv run simple-ws-proxy-client --server <ws-url> --listen-port <port> --secret-key <key> [options]
```

| Option | Default | Description |
|---|---|---|
| `--server` | *(required)* | WebSocket proxy server URL, e.g. `ws://localhost:8765` |
| `--listen-port` | *(required)* | Local port to listen on for SOCKS5 connections |
| `--secret-key` | *(required)* | Shared secret key (must match the server) |
| `--listen-host` | `127.0.0.1` | Local address to bind the SOCKS5 listener to |
| `--workers` | `1` | Number of prefork worker processes |
| `--client-user` | *(none)* | SOCKS5 username that connecting clients must provide; omit to allow no-auth |
| `--client-password` | *(none)* | SOCKS5 password that connecting clients must provide; omit to allow no-auth |

**Example:**

```bash
uv run simple-ws-proxy-client \
  --server ws://example.com:8765 \
  --listen-port 1080 \
  --secret-key mysecret \
  --client-user alice \
  --client-password s3cr3t
```

After starting the client, configure your application to use `127.0.0.1:1080` as a SOCKS5 proxy with username `alice` and password `s3cr3t`.

## Proxy chaining

The server supports an upstream SOCKS5 proxy via `--proxy-host` / `--proxy-port`.
This makes it possible to chain two (or more) proxy hops so that no single node
sees both the origin and the destination.

### Two-hop example

**Node B** (inner server, closer to the target):

```bash
uv run simple-ws-proxy-server \
  --secret-key keyB \
  --port 8766
```

**Node B client** (exposes a local SOCKS5 port that Node A's server will use):

```bash
uv run simple-ws-proxy-client \
  --server ws://nodeB:8766 \
  --listen-port 1081 \
  --secret-key keyB
```

**Node A server** (receives connections from the user's client and forwards them
through Node B via SOCKS5):

```bash
uv run simple-ws-proxy-server \
  --secret-key keyA \
  --port 8765 \
  --proxy-host 127.0.0.1 \
  --proxy-port 1081
```

**User's client** (local SOCKS5 listener):

```bash
uv run simple-ws-proxy-client \
  --server ws://nodeA:8765 \
  --listen-port 1080 \
  --secret-key keyA \
  --client-user alice \
  --client-password s3cr3t
```

Traffic flow:

```
[Application] --SOCKS5--> [Client] --WS/keyA--> [Server A] --SOCKS5-->
  [Client B] --WS/keyB--> [Server B] --TCP--> [Target]
```

Each WebSocket hop is independently authenticated and encrypted with its own
secret key. See [ARCHITECTURE.md](ARCHITECTURE.md) for a detailed description of
the protocol.
