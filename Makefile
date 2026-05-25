.PHONY: check format test install install-dev clean

# Install production dependencies
install:
	uv pip install -e "."
	python -m playwright install chromium

# Install with dev dependencies (linting, type checking, testing)
install-dev:
	uv pip install -e ".[dev]"
	python -m playwright install chromium

# Run all checks: linting + type checking (like `npm run build`)
check:
	@echo "==> Running ruff..."
	.venv/bin/ruff check src tests
	@echo "==> Running mypy..."
	.venv/bin/mypy src/leadforge --ignore-missing-imports
	@echo "==> All checks passed."

# Auto-fix formatting and linting issues
format:
	.venv/bin/ruff check --fix src tests
	.venv/bin/ruff format src tests

# Run tests
test:
	.venv/bin/pytest tests/ -q

# Clean build artifacts and output
clean:
	rm -rf output/ .pytest_cache/ .ruff_cache/ .mypy_cache/ src/*.egg-info
