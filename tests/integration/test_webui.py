from fastapi.testclient import TestClient

from web.app import app


def _demo_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def add(a,b):\n    return a - b\n")
    (tmp_path / "tests" / "test_foo.py").write_text(
        "from foo import add\n\ndef test_add():\n    assert add(2,2)==4\n"
    )
    (tmp_path / "conftest.py").write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))\n"
    )
    return tmp_path


def test_index_returns_form():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200 and "<button" in r.text


def test_run_streams_turns(tmp_path, monkeypatch):
    # C2a: fixture body MUST match the OLD block in web/app.py's mock script
    # (`    return a - b`, with spaces). The previous `return a-b` (no spaces)
    # made EditFile fail with "old block not found", so the demo ended in
    # ERROR even after the loop ran.
    # C2b: ToolDispatcher runs pytest as a subprocess with cwd=project_root
    # and does NOT inject PYTHONPATH; without this conftest `from foo import
    # add` raises ModuleNotFoundError -> pytest collects 0 tests -> the demo
    # can NEVER go green. Mirrors tests/integration/test_agent_loop.py.
    monkeypatch.setenv("HARNESS_DEMO_REPO", str(_demo_repo(tmp_path)))
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


def test_chat_demo_streams_structured_red_green_events(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_DEMO_REPO", str(_demo_repo(tmp_path)))
    c = TestClient(app)
    with c.stream(
        "POST",
        "/api/chat",
        json={"message": "Run the guided demo", "mode": "demo"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"type": "prose"' in body
    assert '"type": "feedback"' in body
    assert '"outcome": "SUCCESS"' in body
    assert (tmp_path / "src" / "foo.py").read_text().endswith("return a - b\n")


def test_bundled_demo_still_exercises_feedback_loop():
    c = TestClient(app)
    with c.stream("POST", "/api/chat", json={"message": "Run the guided demo"}) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"type": "feedback"' in body
    assert '"files_changed": ["src/foo.py"]' in body


def test_public_chat_rejects_arbitrary_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_DEMO_REPO", str(_demo_repo(tmp_path)))
    monkeypatch.delenv("HARNESS_ALLOW_CUSTOM_REPO", raising=False)
    r = TestClient(app).post(
        "/api/chat",
        json={"message": "inspect this", "repo": "/tmp"},
    )
    assert r.status_code == 403
    assert "custom repositories" in r.json()["detail"]


def test_isolated_demo_leaves_source_fixture_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_DEMO_REPO", str(_demo_repo(tmp_path)))
    monkeypatch.setenv("HARNESS_ISOLATE_DEMO", "1")
    c = TestClient(app)
    with c.stream("POST", "/api/chat", json={"message": "Run demo"}) as response:
        body = "".join(response.iter_text())

    assert '"outcome": "SUCCESS"' in body
    assert (tmp_path / "src" / "foo.py").read_text().endswith("return a - b\n")
