"""Generic prefork TCP server."""

import logging
import os
import signal
import socket
from collections.abc import Callable, Generator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

WorkerHandler = Callable[[socket.socket], None]


class PreforkServer:
    """Binds a TCP socket, forks *workers* child processes, and manages their lifecycle.

    Each child process receives the bound socket and calls *worker_handler* with it.
    The parent process waits for all children to finish.

    Usage::

        server = PreforkServer(workers=4)
        with server.start_server(worker_handler, "0.0.0.0", 8080) as srv:
            srv.serve_forever()

    Args:
        workers: Number of worker processes to fork.
    """

    def __init__(self, workers: int) -> None:
        self._workers = workers
        self._pids: list[int] = []

    @contextmanager
    def start_server(
        self,
        worker_handler: WorkerHandler,
        listen_host: str,
        listen_port: int,
    ) -> Generator['PreforkServer', None, None]:
        """Bind the socket, fork workers, and yield *self* as the server object.

        On exit from the context manager all child processes are terminated
        gracefully (SIGTERM) and waited for.

        Args:
            worker_handler: Callable invoked in each child process with the
                            bound :class:`socket.socket` as its sole argument.
            listen_host:    Address to bind to.
            listen_port:    TCP port to listen on.

        Yields:
            This :class:`PreforkServer` instance.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((listen_host, listen_port))
        sock.listen(128)
        sock.set_inheritable(True)

        logger.info(
            'Starting %d worker(s) on %s:%d',
            self._workers,
            listen_host,
            listen_port,
        )

        self._pids = []
        for _ in range(self._workers):
            pid = os.fork()
            if pid == 0:
                signal.signal(signal.SIGINT, signal.SIG_IGN)
                worker_handler(sock)
                os._exit(0)
            self._pids.append(pid)

        try:
            yield self
        finally:
            self._shutdown()

    def serve_forever(self) -> None:
        """Wait for all child processes to finish.

        Handles :exc:`KeyboardInterrupt` by sending SIGTERM to all children
        and waiting for them to exit.
        """
        try:
            for pid in self._pids:
                os.waitpid(pid, 0)
        except KeyboardInterrupt:
            logger.info('Shutting down…')
            self._shutdown()

    def _shutdown(self) -> None:
        """Send SIGTERM to all live children and wait for them."""
        for pid in self._pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for pid in self._pids:
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
        self._pids = []
