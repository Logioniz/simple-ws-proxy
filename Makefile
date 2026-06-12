.PHONY: develop lint format

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
