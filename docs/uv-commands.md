# UV Package Manager Quick Reference

This project uses [uv](https://github.com/astral-sh/uv) for fast, reliable Python package management.

## Common Commands

### Initial Setup
```bash
# Install dependencies and create virtual environment
uv sync

# Install with dev dependencies
uv sync --extra dev
```

### Adding Dependencies
```bash
# Add a new dependency
uv add langchain-anthropic

# Add a dev dependency
uv add --dev pytest-mock

# Add with version constraint
uv add "fastapi>=0.104.0"
```

### Removing Dependencies
```bash
# Remove a dependency
uv remove package-name
```

### Running Commands
```bash
# Run Python scripts
uv run python scripts/verify_setup.py

# Run pytest
uv run pytest

# Run with specific Python version
uv run --python 3.11 python script.py
```

### Virtual Environment
```bash
# Activate the virtual environment (optional, uv run handles this)
source .venv/bin/activate

# Deactivate
deactivate
```

### Updating Dependencies
```bash
# Update all dependencies
uv sync --upgrade

# Update specific package
uv add --upgrade package-name
```

### Lock File
```bash
# Generate/update uv.lock
uv lock

# Sync from lock file
uv sync --frozen
```

## Why UV?

- **Fast**: 10-100x faster than pip
- **Reliable**: Deterministic dependency resolution
- **Modern**: Uses pyproject.toml standard
- **Simple**: No need for separate pip, venv, pip-tools
- **Compatible**: Works with existing Python packages

## Project Structure

All dependencies are defined in `pyproject.toml`:
- `[project.dependencies]` - Core dependencies
- `[project.optional-dependencies.dev]` - Development tools

The `uv.lock` file (auto-generated) ensures reproducible installs.
