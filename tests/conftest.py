# I2 support: starlette>=1.x deprecated `httpx` in favor of `httpx2` and emits a
# StarletteDeprecationWarning (a UserWarning, NOT a DeprecationWarning subclass)
# at IMPORT time of `fastapi.testclient`. tests/integration/test_webui.py
# imports TestClient at module top, so the warning fires during collection.
#
# pyproject's `filterwarnings = ["error", ... ignore StarletteDeprecation ...]`
# handles it for plain `pytest`. BUT pytest's `-W error` CLI flag is applied
# AFTER ini filters and takes precedence (documented behavior), so a bare
# `pytest -W error` would escalate this third-party import warning to an error
# at collection -- defeating the ini ignore.
#
# This conftest pre-imports fastapi.testclient inside a suppress context BEFORE
# any test module is collected. The import-time warning fires once and is
# swallowed; the module is then cached in sys.modules, so test_webui.py's later
# `from fastapi.testclient import TestClient` is a no-op (no re-fire). No
# dependency change, no CLI change. Guarded for environments without fastapi
# (core-only installs).
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        import fastapi.testclient  # noqa: F401
    except ImportError:
        pass
