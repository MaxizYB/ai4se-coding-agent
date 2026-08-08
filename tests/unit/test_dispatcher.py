from harness.actions.protocol import (
    EditFile,
    ListDir,
    ReadFile,
    RunShell,
    RunTests,
    WriteFile,
)
from harness.config import Config
from harness.tools.dispatcher import ToolDispatcher


def test_read_file(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("hi")
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(ReadFile("src/a.py"))
    assert r.ok and r.stdout == "hi"

def test_write_then_edit(tmp_path):
    (tmp_path / "src").mkdir()
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    assert d.execute(WriteFile("src/a.py", "old\n")).ok
    r = d.execute(EditFile("src/a.py", "old", "new"))
    with open(tmp_path / "src" / "a.py") as f:
        assert r.ok and f.read() == "new\n"

def test_edit_old_not_found(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("x")
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(EditFile("src/a.py", "nope", "new"))
    assert r.ok is False and "not found" in r.stderr.lower()

def test_list_dir(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("x")
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(ListDir("src"))
    assert r.ok and "a.py" in r.stdout


def test_list_dir_file_returns_actionable_error(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("x")
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(ListDir("src/a.py"))
    assert not r.ok and "use read_file" in r.stderr

def test_run_shell(tmp_path):
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(RunShell("echo hello"))
    assert r.ok and "hello" in r.stdout


def test_run_shell_pipes_stdin(tmp_path):
    # Freedom fix: RunShell pipes optional STDIN so the agent can drive
    # interactive CLIs (e.g. feed inputs to a program that reads stdin).
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(RunShell("cat", stdin="hello\nworld\n"))
    assert r.ok and "hello" in r.stdout and "world" in r.stdout


def test_run_tests_captures_junit_with_relative_project_root(tmp_path, monkeypatch):
    # Fix E: a RELATIVE project_root must still capture the junit XML. With a
    # relative path, pytest (cwd=project_root) and the junit reader (process
    # cwd) resolved the junit path differently -> file never found -> empty ->
    # FeedbackEngine misread GREEN runs as UNKNOWN. Absolute tmp_path (all
    # other tests) masked this. Caught only via live GLM smoke.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert 1 == 1\n")
    monkeypatch.chdir(tmp_path.parent)            # process cwd OUTSIDE the repo
    d = ToolDispatcher(Config.default())
    d.config.project_root = tmp_path.name          # RELATIVE repo path
    r = d.execute(RunTests("tests/test_ok.py"))
    assert r.ok                                    # green
    assert "<testsuite" in r.junit_xml             # junit captured, not empty
