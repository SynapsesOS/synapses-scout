# Contributing to Synapses-Scout

Thank you for your interest in contributing. This document covers how to get started, the conventions we follow, and what we're looking for.

## Development Setup

**Prerequisites:**
- Python 3.11+
- `make`

```bash
git clone https://github.com/SynapsesOS/synapses-scout.git
cd synapses-scout
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make test
```

## Project Structure

```
src/scout/
    config.py           Configuration loading
    models.py           Pydantic models (ScoutResult, SearchHit, etc.)
    router.py           URL type detection (search vs web vs YouTube)
    cache.py            SQLite cache with TTL
    orchestrator.py     Multi-query fan-out, dedup, scoring
    scout.py            Scout class — unified fetch() interface
    server.py           HTTP API (Starlette)
    cli.py              CLI entrypoint
    searcher/           Search providers (DuckDuckGo, Tavily)
    extractor/          Web extraction (fast-path + browser fallback)
    media/              YouTube extraction (yt-dlp)
    distiller/          Intelligence sidecar client
tests/
    test_*.py           Test files mirror src/ structure
```

**The dependency rule:** `searcher/`, `extractor/`, `media/`, and `distiller/` are independent modules. They import from `models.py` and `config.py` only. `scout.py` orchestrates them. `server.py` and `cli.py` are thin wrappers over `scout.py`.

## Running Tests

```bash
make test          # full suite
make test-short    # skip slow/integration tests
make lint          # ruff check + format check
make format        # auto-format
```

All tests must pass before submitting a PR. Tests should be fast — mock external calls (HTTP, search, extraction) instead of hitting real services.

## Code Style

- Python 3.11+ features are encouraged (`match`, `|` union types, etc.)
- `ruff` for linting and formatting (config in `pyproject.toml`)
- Pydantic for all data models
- `async/await` throughout — no sync blocking in the main path
- Type hints on all public functions

## Pull Request Process

1. Fork the repository and create a feature branch
2. Make your changes with tests
3. Ensure `make test` and `make lint` pass
4. Submit a PR with a clear description of what and why

## What We're Looking For

- New extraction backends (PDF, document parsing)
- Search provider integrations
- Performance improvements to the fast-path extractor
- Better relevance scoring in the orchestrator
- MCP server integration for direct agent access
