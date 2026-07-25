from fastapi.testclient import TestClient

from web.app import app


def test_index_returns_form():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200 and "<form" in r.text


def test_run_streams_turns(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def add(a,b):\n    return a-b\n")
    (tmp_path / "tests" / "test_foo.py").write_text(
        "from foo import add\n\ndef test_add():\n    assert add(2,2)==4\n"
    )
    monkeypatch.setenv("HARNESS_DEMO_REPO", str(tmp_path))
    c = TestClient(app)
    with c.stream("POST", "/run", json={"test": "tests/test_foo.py::test_add"}) as r:
        body = "\n".join(chunk for chunk in r.iter_text())
    assert "SUCCESS" in body or "RunTests" in body
