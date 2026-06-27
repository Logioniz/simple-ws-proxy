"""Build standalone binaries for the server and client via PyInstaller.

PyInstaller does **not** cross-compile: to get a binary for a given OS you must
run this module on that OS. The Makefile exposes per-OS targets
(``build-linux``, ``build-windows``, ``build-macos``) that all invoke this
module — each one has to be run on the matching operating system. The
``--target`` option only selects the output sub-directory under ``dist/``; it
does not change the OS the produced binary runs on.

Two single-file executables are produced:

* ``simple-ws-proxy-server`` — from :mod:`simple_ws_proxy.server.main`
* ``simple-ws-proxy-client`` — from :mod:`simple_ws_proxy.client.main`

On Windows PyInstaller appends ``.exe`` automatically.
"""

import argparse
import platform
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent

# Output binary name -> entry-point script.
BINARIES: dict[str, Path] = {
    'simple-ws-proxy-server': ROOT / 'simple_ws_proxy' / 'server' / 'main.py',
    'simple-ws-proxy-client': ROOT / 'simple_ws_proxy' / 'client' / 'main.py',
}

# platform.system() (lower-cased) -> dist sub-directory name.
PLATFORM_DIRS = {
    'linux': 'linux',
    'windows': 'windows',
    'darwin': 'macos',
}


def current_platform() -> str:
    """Return the dist sub-directory name for the host OS."""
    system = platform.system().lower()
    return PLATFORM_DIRS.get(system, system)


def build(target: str) -> None:
    """Build every binary into ``dist/<target>/``.

    Args:
        target: Output sub-directory under ``dist/`` (e.g. ``linux``).
    """
    dist_path = ROOT / 'dist' / target
    work_path = ROOT / 'build' / target
    dist_path.mkdir(parents=True, exist_ok=True)

    for name, entry in BINARIES.items():
        PyInstaller.__main__.run(
            [
                str(entry),
                '--onefile',
                '--clean',
                '--noconfirm',
                '--name',
                name,
                '--distpath',
                str(dist_path),
                '--workpath',
                str(work_path),
                '--specpath',
                str(work_path),
            ]
        )


def main() -> None:
    """Parse arguments and build the binaries for the requested target."""
    parser = argparse.ArgumentParser(description='Build standalone binaries with PyInstaller.')
    parser.add_argument(
        '--target',
        default=current_platform(),
        help='Output sub-directory under dist/ (default: current OS).',
    )
    args = parser.parse_args()
    build(args.target)


if __name__ == '__main__':
    main()
