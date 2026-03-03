# Contributing to apc

## Setup

```bash
git clone https://github.com/FZ2000/apc-cli.git
cd apc-cli
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest -v
```

## Code Style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
ruff check src/ tests/
ruff format --check src/ tests/

# Auto-fix
ruff check --fix src/ tests/
ruff format src/ tests/
```

Configuration: Python 3.12+, line length 100 (see `pyproject.toml`).

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with clear, focused commits
3. Ensure all tests pass and linting is clean
4. Open a PR with a description of the changes
