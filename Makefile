.PHONY: test lint demo install-dev install-full
test:
	pytest -m "not live"
lint:
	ruff check src tests
demo:
	python scripts/mechanism_demo.py
install-dev:
	pip install -e ".[dev]"
install-full:
	pip install -e ".[full,dev]"
