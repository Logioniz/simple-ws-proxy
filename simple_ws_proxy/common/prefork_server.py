"""Generic prefork TCP server.

Uses :mod:`multiprocessing` rather than a bare :func:`os.fork` so the same
code runs on every platform Python supports:

* On Unix the default *fork* start method gives the classic prefork model —
  the listening socket is simply inherited by every child.
* On Windows (and anywhere using the *spawn* start method) the listening
  socket is duplicated into each child by multiprocessing's socket reduction,
  so the workers still share a single bound port.

Because *spawn* re-imports the program and pickles the worker callable and its
arguments, two constraints apply:

* the entry module must be guarded with ``if __name__ == '__main__':``;
* *worker_handler* (and anything it closes over) must be picklable.
"""

import logging
import multiprocessing as mp
import signal
import socket
from collections.abc import Callable, Generator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

WorkerHandler = Callable[[socket.socket], None]


def _run_worker(worker_handler: WorkerHandler, sock: socket.socket) -> None:
    """Child-process entry point: ignore SIGINT, then run the handler.

    SIGINT is left to the parent so that ``Ctrl-C`` triggers a single,
    coordinated shutdown instead of every worker racing to handle it. The
    signal may be absent on some platforms, so it is set defensively.
    """
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError, AttributeError):
        pass
    worker_handler(sock)


class PreforkServer:
    """Binds a TCP socket, spawns *workers* child processes, and manages them.

    Each child process receives the bound socket and calls *worker_handler*
    with it. The parent process waits for all children to finish.

    Usage::

        server = PreforkServer(workers=4)
        with server.start_server(worker_handler, "0.0.0.0", 8080) as srv:
            srv.serve_forever()

    Args:
        workers: Number of worker processes to start.
    """

    def __init__(self, workers: int) -> None:
        self._workers = workers
        self._processes: list[mp.process.BaseProcess] = []
        self._sock: socket.socket | None = None

    @contextmanager
    def start_server(
        self,
        worker_handler: WorkerHandler,
        listen_host: str,
        listen_port: int,
    ) -> Generator['PreforkServer', None, None]:
        """Bind the socket, start workers, and yield *self* as the server object.

        On exit from the context manager all child processes are terminated
        and waited for.

        Args:
            worker_handler: Callable invoked in each child process with the
                            bound :class:`socket.socket` as its sole argument.
                            Must be picklable for the *spawn* start method
                            (e.g. on Windows).
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
        self._sock = sock

        logger.info(
            'Starting %d worker(s) on %s:%d',
            self._workers,
            listen_host,
            listen_port,
        )

        self._processes = []
        for _ in range(self._workers):
            process = mp.Process(target=_run_worker, args=(worker_handler, sock))
            process.start()
            self._processes.append(process)

        try:
            yield self
        finally:
            self._shutdown()

    def serve_forever(self) -> None:
        """Wait for all child processes to finish.

        Handles :exc:`KeyboardInterrupt` by terminating all children and
        waiting for them to exit.
        """
        try:
            for process in self._processes:
                process.join()
        except KeyboardInterrupt:
            logger.info('Shutting down…')
            self._shutdown()

    def _shutdown(self) -> None:
        """Terminate all live children and wait for them."""
        for process in self._processes:
            if process.is_alive():
                process.terminate()
        for process in self._processes:
            process.join()
        self._processes = []

        if self._sock is not None:
            self._sock.close()
            self._sock = None
