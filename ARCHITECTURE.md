# WebSocket Proxy — Architecture

## Overview

```
[Application]
     | SOCKS5
     v
[Client (simple-ws-proxy-client)]
     | WebSocket (XOR-encrypted)
     v
[Server (simple-ws-proxy-server)]
     | TCP  (or SOCKS5 → next hop)
     v
[Target host]
```

The client exposes a local SOCKS5 listener. When an application connects and
requests a target host, the client opens a WebSocket connection to the server,
authenticates, and relays all traffic through that tunnel. The server then opens
a TCP connection to the target (or forwards the connection through an upstream
SOCKS5 proxy) and bridges the two streams.

---

## Authentication

Every WebSocket connection from the client carries two HTTP headers:

| Header | Value |
|---|---|
| `Time` | Unix timestamp (seconds) as a string |
| `Authentication` | `SimpleProxy <token>` |

**Token derivation:**

```
session_secret_key = func(secret_key, time)   # any cryptographic function
token              = hmac(SHA-256, time, session_secret_key)
```

`secret_key` is shared between the client and server and is set via `--secret-key`.

**Time window check:**
The server rejects any connection where the `Time` value differs from the server
clock by more than `--time-window` seconds (default: 5). This prevents replay attacks.

---

## Encryption

After authentication the same `session_secret_key` is used to XOR-encrypt every
message exchanged over the WebSocket connection. Because the key is derived from
the timestamp, each session uses a distinct key.

---

## Protocol

The first message sent after the WebSocket handshake is the *connect* request
(JSON, XOR-encrypted):

```json
{"connect": "<host>:<port>"}
```

All subsequent messages carry raw proxied bytes, also XOR-encrypted with the
session key.

---

## Client

The client accepts SOCKS5 connections (with optional username/password
authentication per RFC 1929) and tunnels the traffic to the server over a
WebSocket connection.

When `--client-user` / `--client-password` are omitted, the client accepts
unauthenticated SOCKS5 connections (method `NO AUTHENTICATION REQUIRED`).

---

## Server

The server is a prefork WebSocket server. The main process binds the TCP socket
and forks `--workers` child processes; each worker runs its own `asyncio` event
loop and calls `accept()` on the shared socket.

For each incoming WebSocket connection the server:

1. Validates the `Time` and `Authentication` headers.
2. Decrypts and parses the *connect* message to obtain the target `host:port`.
3. Opens a TCP connection to the target — either directly or through an upstream
   SOCKS5 proxy when `--proxy-host` / `--proxy-port` are provided.
4. Bridges the WebSocket stream and the TCP stream bidirectionally.

---

## Proxy chaining

The `--proxy-host` / `--proxy-port` options on the server enable chaining
multiple proxy hops. A typical two-hop chain looks like this:

```
[Application]
     | SOCKS5
     v
[Client A]  --secret-key keyA  --server ws://serverA:8765
     | WebSocket
     v
[Server A]  --secret-key keyA  --proxy-host 127.0.0.1  --proxy-port 1081
     | SOCKS5
     v
[Client B]  --listen-port 1081  --secret-key keyB  --server ws://serverB:8765
     | WebSocket
     v
[Server B]  --secret-key keyB
     | TCP
     v
[Target host]
```

Each link in the chain can use a different secret key, and the SOCKS5 hop
between Server A and Client B can itself be authenticated.
