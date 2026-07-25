.PHONY: test lint demo install-dev install-full
test:
	mkdir -p .harness && pytest -m "not live" --junitxml=.harness/junit.xml
lint:
	ruff check src tests scripts web
demo:
	python scripts/mechanism_demo.py
install-dev:
	pip install -e ".[dev]"
install-full:
	pip install -e ".[full,dev]"
