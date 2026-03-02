.PHONY: install dev test lint format serve status clean

PYTHON := python3
PORT   ?= 11436

install:
	$(PYTHON) -m pip install -e .

dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/ -v --timeout=30

test-short:
	$(PYTHON) -m pytest tests/ -v --timeout=30 -m "not slow"

lint:
	$(PYTHON) -m ruff check src/ tests/
	$(PYTHON) -m ruff format --check src/ tests/

format:
	$(PYTHON) -m ruff format src/ tests/

serve:
	$(PYTHON) -m scout serve --port $(PORT)

status:
	@curl -s http://localhost:$(PORT)/v1/health | $(PYTHON) -m json.tool

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info __pycache__ .pytest_cache .ruff_cache
