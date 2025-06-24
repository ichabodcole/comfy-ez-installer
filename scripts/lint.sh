#!/bin/bash
# Convenience script for linting and formatting with ruff

set -e

echo "🔍 Running ruff linter..."
uv run ruff check .

echo "✨ Running ruff formatter..."
uv run ruff format .

echo "🧪 Running tests to ensure no regressions..."
uv run pytest --tb=line -q

echo "✅ Linting, formatting, and testing complete!" 