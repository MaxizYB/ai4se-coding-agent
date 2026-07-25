from fastapi.testclient import TestClient

from web.app import app


def test_index_returns_form():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200 and "<form" in r.text


def test_run_streams_turns(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    # C2a: fixture body MUST match the OLD block in web/app.py's mock script
    # (`    return a - b`, with spaces). The previous `return a-b` (no spaces)
    # made EditFile fail with "old block not found", so the demo ended in
    # ERROR even after the loop ran.
    (tmp_path / "src" / "foo.py").write_text("def add(a,b):\n    return a - b\n")
    (tmp_path / "tests" / "test_foo.py").write_text(
        "from foo import add\n\ndef test_add():\n    assert add(2,2)==4\n"
    )
    # C2b: ToolDispatcher runs pytest as a subprocess with cwd=project_root
    # and does NOT inject PYTHONPATH; without this conftest `from foo import
    # add` raises ModuleNotFoundError -> pytest collects 0 tests -> the demo
    # can NEVER go green. Mirrors tests/integration/test_agent_loop.py.
    (tmp_path / "conftest.py").write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))\n"
    )
    monkeypatch.setenv("HARNESS_DEMO_REPO", str(tmp_path))
    c = TestClient(app)
    with c.stream("POST", "/run", json={"test": "tests/test_foo.py::test_add"}) as r:
        body = "\n".join(chunk for chunk in r.iter_text())
    # C2c: the demo MUST genuinely reach outcome=SUCCESS (red->green), not just
    # emit a RunTests turn. The old lenient `"SUCCESS" in body or "RunTests"
    # in body` passed even when the demo ended in ERROR because the first
    # (red) RunTests turn put "RunTests" in the body.
    assert '"outcome": "SUCCESS"' in body, (
        f"demo did not reach SUCCESS; stream was:\n{body}"
    )
