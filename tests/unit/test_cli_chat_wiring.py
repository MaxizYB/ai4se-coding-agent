from harness.cli import main


def test_chat_no_creds_returns_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("HARNESS_MASTER_PASSWORD", raising=False)
    rc = main(["chat", "--repo", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "cred" in err.lower() or "key" in err.lower()


def test_chat_wires_chatrunner(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-fake")
    called = {}

    class FakeRunner:
        def __init__(self, *a, **k):
            pass

        def run(self, repo, accept=None):
            called["run"] = (repo, accept)
            return 0

    monkeypatch.setattr("harness.interactive.chat.ChatRunner", FakeRunner)
    rc = main(["chat", "--repo", str(tmp_path), "--accept", "tests/t.py::test_a"])
    assert rc == 0 and called["run"] == (str(tmp_path), "tests/t.py::test_a")


def test_task_wires_chatrunner_failclosed(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-fake")
    called = {}

    class FakeRunner:
        def __init__(self, *a, **k):
            pass

        def run_task(self, repo, goal, accept=None):
            called["run_task"] = (goal, accept)
            return 0

    monkeypatch.setattr("harness.interactive.chat.ChatRunner", FakeRunner)
    rc = main(["task", "--repo", str(tmp_path), "--goal", "fix the bug", "--accept", "tests/t.py::test_a"])
    assert rc == 0 and called["run_task"] == ("fix the bug", "tests/t.py::test_a")
