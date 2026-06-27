.PHONY: develop lint format test build clean-build

develop:
	uv sync --extra dev
	@echo '#!/bin/sh\nmake lint' > .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit

lint:
	uv run mypy simple_ws_proxy tests
	uv run ruff check simple_ws_proxy tests

format:
	uv run ruff format simple_ws_proxy tests
	uv run ruff check --fix simple_ws_proxy tests

test:
	uv run pytest -v tests

# Standalone binaries (server + client) via PyInstaller.
# PyInstaller does not cross-compile: it always builds for the OS it runs on.
# The output lands in dist/<os>/ (os is auto-detected). To get binaries for
# every platform, run `make build` on each of Linux, Windows and macOS.
build:
	uv run --extra build python packaging/build.py

clean-build:
	rm -rf build dist
