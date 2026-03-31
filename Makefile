.PHONY: install test lint format typecheck help

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

run-agent:
	python -m src agent

run-server:
	python -m src server

run-demo:
	python -m src demo

run-simulate:
	python -m src simulate

help:
	@echo "Available commands:"
	@echo "  install      Install dependencies in editable mode"
	@echo "  test         Run tests"
	@echo "  lint         Run ruff linting"
	@echo "  format       Format code with ruff"
	@echo "  typecheck    Run mypy type checking"
	@echo "  run-agent    Run the autonomous remediation agent"
	@echo "  run-server   Run the MCP server (stdio transport)"
	@echo "  run-demo     Run the flagship spike->rollback demo"
	@echo "  run-simulate Run the interactive error stream simulator"
